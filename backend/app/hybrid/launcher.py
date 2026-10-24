"""Shared launcher controller and a small French desktop menu."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json
import queue
import threading
import time
import webbrowser
from uuid import uuid4

from .control_services import prepare_controls
from .deployment import ROOT, prepare, start, stop, probe, stop_candidate


ACTION_HELP = {
    "admin": ("Structura complet — Admin", "Ouvre l’application complète avec le compte admin : accueil, produits, pricing, RFQ, clients, administration et simulation.\n\nCet espace possède sa propre base de développement, séparée des six organisations. Aucune campagne IA ne démarre à l’ouverture."),
    "simulation": ("Écran de simulation", "Ouvre l’écran de simulation dans Structura Admin. Vous pouvez configurer une campagne, consulter les résultats et les erreurs.\n\nOuvrir cet écran ne lance aucun agent. Les agents démarrent uniquement lorsque vous lancez explicitement une campagne depuis cet écran. Ils créent leurs propres comptes et bases, séparés des essais manuels."),
    "all": ("Les six organisations", "Démarre le portail et les six installations : BNP Paribas, Société Générale, Citi, UBS, Leonteq et Kepler Cheuvreux Solutions.\n\nLe navigateur affiche leurs cartes. Choisissez une organisation pour ouvrir son super utilisateur ; les profils Front, Opérations et Contrôleur sont disponibles dans le sélecteur. Chaque organisation garde sa propre base. Les sessions sont indépendantes par onglet."),
    "platform": ("Console SaaS", "Ouvre l’annuaire central et l’état des installations. Vous pouvez y ouvrir une organisation et accéder aux fonctions de supervision disponibles.\n\nPour travailler dans l’application métier complète, utilisez Structura Admin. Le registre RFQ et la facturation restent à développer."),
    "organization": ("Une organisation", "Démarre seulement l’organisation sélectionnée et le portail nécessaire à sa connexion. Ouvre son super utilisateur.\n\nLes autres organisations ne sont pas démarrées par ce choix. Les services déjà actifs sont réutilisés."),
    "status": ("État des services", "Indique quelles installations sont actives ou arrêtées. Cette action ne démarre aucun service et ne lance aucun agent.\n\nLes détails affichent les services et leurs ports."),
    "stop": ("Arrêter Structura", "Arrête en parallèle les services ouverts depuis cette fenêtre du lanceur, ainsi que les services qu’ils ont démarrés. Les installations non ouvertes ici et les services inactifs sont ignorés.\n\nSi vous avez lancé une campagne IA dans cet espace, une demande d’arrêt propre lui est envoyée ; sa fermeture peut prendre plus longtemps. Les données enregistrées sont conservées et le lanceur reste ouvert."),
}


class Launcher:
    def __init__(self, runtime_root=None, base_port=8100):
        self.root = Path(runtime_root or ROOT / ".runtime" / "hybrid-saas").resolve()
        self.configs = prepare(self.root, base_port)
        self.platform = next(config for config in self.configs if config.kind == "platform")
        self.controls = prepare_controls(self.platform)
        self.launcher_id = str(uuid4())
        self.opened = {}
        self.progress = lambda message: None

    @contextmanager
    def command(self):
        from ..services.agent_workshop.lease import CampaignLease
        directory = self.root / "launcher-lock"
        directory.mkdir(exist_ok=True)
        try:
            lease = CampaignLease(directory)
        except ValueError as exc:
            raise RuntimeError("Une autre action du lanceur est en cours. Attendez sa fin.") from exc
        try:
            yield
        finally:
            lease.close()

    def launch(self, action="admin", organization=None, open_browser=True):
        if action not in {"all", "admin", "platform", "organization", "simulation"}:
            raise ValueError("Choix de lancement inconnu.")
        selected = [self.controls["admin-workbench"], self.platform] if action in {"admin", "simulation"} else [self.platform]
        if action == "all":
            selected += [c for c in self.configs if c.kind == "organization"]
        elif action == "organization":
            match = next((c for c in self.configs if c.key == organization and c.kind == "organization"), None)
            if not match:
                raise ValueError("Organisation inconnue.")
            selected.append(match)
        started, results, warnings = [], [], []
        with self.command():
            try:
                for config in selected:
                    self.progress(f"Démarrage : {config.name}…")
                    result = start(config, developer_access=True, launcher_id=self.launcher_id)
                    results.append(result)
                    if result["started"]:
                        started.append(config)
                self.opened.update({config.key: config for config in selected})
            except BaseException:
                for config in reversed(started):
                    stop(config, timeout_seconds=240 if config.service in {"simulation_controller", "admin_workbench"} else 40)
                raise
        url = self.platform.public_descriptor()["url"] + "/#/login"
        if action == "organization":
            url += "?organization=" + organization
        elif action in {"admin", "simulation"}:
            url = self.controls["admin-workbench"].public_descriptor()["url"] + "/#/login?development_admin=1&next=" + (
                "/agent-workshop" if action == "simulation" else "/")
        elif action == "platform":
            url += "?console=1&next=/platform"
        if open_browser:
            webbrowser.open(url)
        return {"url": url, "services": results, "warnings": warnings}

    def status(self):
        rows = []
        configs = [*self.configs, *self.controls.values()]
        with ThreadPoolExecutor(max_workers=len(configs)) as pool:
            healths = list(pool.map(probe, configs))
        for config, health in zip(configs, healths):
            rows.append({"key": config.key, "name": config.name, "port": config.port,
                         "running": health is not None, "pid": health.get("process_id") if health else None})
        return rows

    def stop(self, only=None):
        configs = only if only is not None else [self.controls["simulation"], self.controls["admin-workbench"],
            *(c for c in self.configs if c.kind == "organization"), self.platform]
        results, errors = [], []
        with self.command():
            if only is None:
                configs = [config for config in configs if config.key in self.opened or self.owns(config)]
                if configs:
                    with ThreadPoolExecutor(max_workers=len(configs)) as pool:
                        active = list(pool.map(stop_candidate, configs))
                    configs = [config for config, pending in zip(configs, active) if pending]
            if not configs:
                self.progress("Aucun service ouvert par ce lanceur à arrêter.")
            if configs:
                with ThreadPoolExecutor(max_workers=len(configs)) as pool:
                    pending = {}
                    for config in configs:
                        self.progress(f"Arrêt du service actif : {config.name}…")
                        future = pool.submit(stop, config, timeout_seconds=240 if config.service in {"simulation_controller", "admin_workbench"} else 40)
                        pending[future] = config
                    for future in as_completed(pending):
                        config = pending[future]
                        try:
                            result = future.result()
                            results.append(result)
                            if result.get("stopped"):
                                self.opened.pop(config.key, None)
                            self.progress(f"Arrêt confirmé : {config.name}.")
                        except (RuntimeError, OSError) as exc:
                            errors.append(f"{config.name} : {exc}")
        if errors:
            raise RuntimeError("\n".join(errors))
        return results

    def owns(self, config):
        record = config.data_dir / ".process.json"
        if not record.exists():
            return False
        metadata = json.loads(record.read_text(encoding="utf-8"))
        return metadata.get("launcher_id") == self.launcher_id and metadata.get("installation_id") == str(config.installation_id)


class LauncherWindow:
    def __init__(self, root, controller):
        import tkinter as tk
        from tkinter import ttk
        from .launcher_widgets import BACKGROUND, INK, RoundedButton, icon, rounded
        self.root, self.controller = root, controller
        self.events = queue.Queue()
        self.busy = False
        self.close_after_stop = False
        self.tooltip = None
        self.details_visible = False
        self.descriptions = []
        self.card_titles = []
        root.title("Structura — Votre espace de travail")
        width, height = min(980, root.winfo_screenwidth() - 80), min(820, root.winfo_screenheight() - 100)
        root.geometry(f"{width}x{height}+{max(0, (root.winfo_screenwidth() - width) // 2)}+{max(0, (root.winfo_screenheight() - height) // 2 - 25)}")
        root.minsize(min(width, 660), min(height, 540))
        root.configure(background=BACKGROUND)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background=BACKGROUND)
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("TLabel", background=BACKGROUND, foreground=INK, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background="#ffffff")
        style.configure("Title.TLabel", background="#ffffff", font=("Segoe UI", 12, "bold"))
        style.configure("Description.TLabel", background="#ffffff", foreground="#58677b", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=(14, 9), borderwidth=0, background="#e7edf5", foreground="#15375a")
        style.map("TButton", background=[("active", "#dbe5f1")], foreground=[("disabled", "#94a0b0")])
        style.configure("Primary.TButton", background="#15375a", foreground="#ffffff")
        style.map("Primary.TButton", background=[("active", "#244c76"), ("disabled", "#b6c3d1")], foreground=[("disabled", "#ffffff")])
        style.configure("Stop.TButton", background="#fce9e9", foreground="#a32b35")
        style.map("Stop.TButton", background=[("active", "#f8d8db")])
        style.configure("Help.TButton", background="#edf2f8", foreground="#315e88", padding=(7, 3), font=("Segoe UI", 10, "bold"))
        style.configure("TCombobox", padding=(10, 7), font=("Segoe UI", 10), fieldbackground="#f4f7fb", arrowcolor="#54708c", bordercolor="#dce5ef", lightcolor="#f4f7fb", darkcolor="#f4f7fb")
        style.map("TCombobox", fieldbackground=[("readonly", "#f4f7fb"), ("disabled", "#edf1f6")], foreground=[("readonly", INK), ("disabled", "#98a6b7")], selectbackground=[("readonly", "#f4f7fb")], selectforeground=[("readonly", INK)])
        style.configure("Horizontal.TProgressbar", background="#5f92bb", troughcolor=BACKGROUND, borderwidth=0, thickness=3)
        style.configure("Vertical.TScrollbar", background="#d4deea", troughcolor=BACKGROUND, borderwidth=0, arrowsize=10)
        frame = ttk.Frame(root, padding=26)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 22))
        icon(header, "admin", background=BACKGROUND).pack(side="left", padx=(0, 13))
        brand = ttk.Frame(header)
        brand.pack(side="left")
        ttk.Label(brand, text="Structura", font=("Segoe UI", 24, "bold")).pack(anchor="w")
        ttk.Label(brand, text="Choisissez votre espace de travail", foreground="#7c8da1", font=("Segoe UI", 10)).pack(anchor="w", pady=(1, 0))
        badge = tk.Canvas(header, width=156, height=28, background=BACKGROUND, highlightthickness=0)
        badge.pack(side="right", anchor="center")
        rounded(badge, 1, 1, 154, 26, 13, fill="#e5f1ed", outline="")
        badge.create_oval(13, 11, 19, 17, fill="#4b927a", outline="")
        badge.create_text(89, 14, text="DÉVELOPPEMENT", fill="#3e7c69", font=("Segoe UI", 8, "bold"))
        content = ttk.Frame(frame)
        content.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(content, orient="vertical", style="Vertical.TScrollbar")
        self.body_scrollbar = scrollbar
        scrollbar.pack(side="right", fill="y")
        self.canvas = tk.Canvas(content, background=BACKGROUND, highlightthickness=0, yscrollcommand=self.update_scrollbar)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas)
        self.body_window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self.resize_body)
        root.bind("<MouseWheel>", self.scroll_body, add="+")
        self.buttons = []
        self.card("Structura Admin", "Produits, pricing, RFQ, clients et administration.\nVotre application complète dans un espace dédié.", "admin")
        ttk.Label(self.body, text="ACCÈS RAPIDES", font=("Segoe UI", 9, "bold"), foreground="#8494a8").pack(anchor="w", padx=4, pady=(17, 10))
        self.secondary = ttk.Frame(self.body)
        self.secondary.pack(fill="x")
        for column in (0, 1):
            self.secondary.columnconfigure(column, weight=1, uniform="cards")
        for row in (0, 1):
            self.secondary.rowconfigure(row, weight=1, uniform="cards")
        for title, description, action in (
            ("Simulation avec agents", "Configurer et consulter les campagnes. Aucun agent lancé à l’ouverture.", "simulation"),
            ("Les six organisations", "Démarrer les six installations privées et ouvrir leur portail.", "all"),
            ("Console SaaS", "Consulter l’annuaire et superviser les installations.", "platform"),
        ):
            self.card(title, description, action)
        organization_row = self.card("Une organisation", "Accéder à son super utilisateur, dans sa propre installation.", "organization")
        self.organizations = [c for c in controller.configs if c.kind == "organization"]
        self.organization = ttk.Combobox(organization_row, state="readonly", values=[c.name for c in self.organizations])
        self.organization.current(0)
        self.organization.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 9))
        controls = ttk.Frame(frame)
        controls.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        for text, action in (("État des services", "status"), ("Arrêter Structura", "stop")):
            button = RoundedButton(controls, text=text, command=lambda choice=action: self.execute(choice), background=BACKGROUND,
                                   fill="#fbe9ea" if action == "stop" else "#e7edf5", foreground="#ac4752" if action == "stop" else INK,
                                   hover="#f6dce0" if action == "stop" else "#dbe6f2", width=168 if action == "stop" else 156)
            button.pack(side="left")
            self.buttons.append(button)
            self.help_button(controls, action).pack(side="left", padx=(5, 12))
        self.details_button = RoundedButton(controls, text="Détails ▾", command=self.toggle_details, background=BACKGROUND, fill=BACKGROUND, hover="#e7edf5", width=98)
        self.details_button.pack(side="right")
        status = ttk.Frame(frame)
        status.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.message = tk.StringVar(value="Prêt à travailler")
        self.status_dot = tk.Canvas(status, width=14, height=20, background=BACKGROUND, highlightthickness=0)
        self.status_dot.pack(side="left", padx=(0, 5))
        self.dot = self.status_dot.create_oval(3, 7, 9, 13, fill="#66a28c", outline="")
        ttk.Label(status, textvariable=self.message, wraplength=700, foreground="#718399", font=("Segoe UI", 9)).pack(side="left", anchor="w")
        self.activity = ttk.Progressbar(status, mode="indeterminate")
        self.activity.pack(fill="x", pady=(8, 0))
        self.activity.pack_forget()
        output_frame = ttk.Frame(frame)
        output_frame.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self.output_frame = output_frame
        scrollbar = ttk.Scrollbar(output_frame)
        scrollbar.pack(side="right", fill="y")
        self.output = tk.Text(output_frame, height=5, wrap="word", state="disabled", yscrollcommand=scrollbar.set,
                              font=("Segoe UI", 9), relief="flat", background="#eaf0f7", foreground="#62768e", padx=14, pady=12)
        self.output.pack(fill="both", expand=True)
        scrollbar.configure(command=self.output.yview)
        output_frame.grid_remove()
        root.protocol("WM_DELETE_WINDOW", self.close)
        controller.progress = lambda message: self.events.put(("progress", message))
        root.after(100, self.poll)

    def card(self, title, description, action):
        import tkinter as tk
        from .launcher_widgets import INK, RoundedPanel, RoundedButton, icon, rounded
        hero = action == "admin"
        surface = "#183c60" if hero else "#ffffff"
        panel = RoundedPanel(self.body if hero else self.secondary, fill=surface, border=surface if hero else "#e1e8f0", padding=23 if hero else 18)
        if hero:
            panel.pack(fill="x")
        else:
            row, column = {"simulation": (0, 0), "all": (0, 1), "platform": (1, 0), "organization": (1, 1)}[action]
            panel.grid(row=row, column=column, sticky="nsew", padx=(0, 7) if column == 0 else (7, 0), pady=(0, 12))
        card = panel.body
        card.columnconfigure(1 if not hero else 0, weight=1)
        if hero:
            tk.Label(card, text="VOTRE ACCÈS PRINCIPAL", background=surface, foreground="#90c6bb", font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w")
            tk.Label(card, text=title, background=surface, foreground="#ffffff", font=("Segoe UI", 23, "bold")).grid(row=1, column=0, sticky="w", pady=(6, 4))
            label = tk.Label(card, text=description, background=surface, foreground="#c4d4e4", font=("Segoe UI", 10), justify="left", anchor="w", wraplength=450)
            label.grid(row=2, column=0, sticky="w", pady=(0, 15))
            self.help_button(card, action).grid(row=0, column=1, sticky="ne")
            graphic = tk.Canvas(card, width=125, height=95, background=surface, highlightthickness=0)
            graphic.grid(row=1, column=1, rowspan=3, padx=(15, 7))
            for x, y, color in ((30, 6, "#305577"), (17, 18, "#3e6989"), (4, 30, "#537e9c")):
                rounded(graphic, x, y, 78, 51, 8, fill=color, outline="")
            graphic.create_line(18, 51, 48, 51, fill="#a9d5d0", width=3, capstyle="round")
            graphic.create_line(18, 61, 64, 61, fill="#d3e4ed", width=2, capstyle="round")
            self.descriptions.append((label, 1, 210))
        else:
            icon(card, action).grid(row=0, column=0, sticky="w", padx=(0, 10))
            title_label = tk.Label(card, text=title, background=surface, foreground=INK, font=("Segoe UI", 12, "bold"), anchor="w", justify="left", wraplength=230)
            title_label.grid(row=0, column=1, sticky="w")
            self.card_titles.append(title_label)
            self.help_button(card, action).grid(row=0, column=2, sticky="e", padx=(8, 0))
            label = tk.Label(card, text=description, background=surface, foreground="#7a8b9e", font=("Segoe UI", 10), justify="left", anchor="w", wraplength=310)
            label.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 12))
            self.descriptions.append((label, 2, 58))
        button = RoundedButton(card, text="Entrer dans Structura  →" if hero else "Ouvrir  →", command=lambda: self.execute(action),
                               background=surface, fill="#ffffff" if hero else "#edf2f8", foreground=INK,
                               hover="#e6f2f3" if hero else "#e1eaf5", width=225 if hero else 118, height=41 if hero else 35)
        button.grid(row=3 if hero or action == "organization" else 2, column=0, columnspan=1 if hero else 3, sticky="w")
        self.buttons.append(button)
        return card

    def help_button(self, parent, action):
        from .launcher_widgets import BACKGROUND, RoundedButton
        background = BACKGROUND if parent.winfo_class() == "TFrame" else parent.cget("background")
        dark = action == "admin"
        button = RoundedButton(parent, text="?", command=lambda: self.show_help(action), background=background,
                               fill="#315677" if dark else "#f0f4f9", foreground="#c9dce9" if dark else "#69849f",
                               hover="#416b8e" if dark else "#e0eaf5", width=29, height=29, radius=15)
        button.bind("<Enter>", lambda event: self.show_tooltip(button, action), add="+")
        button.bind("<FocusIn>", lambda event: self.show_tooltip(button, action), add="+")
        button.bind("<Leave>", self.hide_tooltip, add="+")
        button.bind("<FocusOut>", self.hide_tooltip, add="+")
        return button

    def show_help(self, action):
        from tkinter import messagebox
        self.hide_tooltip()
        title, description = ACTION_HELP[action]
        messagebox.showinfo(title, description, parent=self.root)

    def show_tooltip(self, button, action):
        import tkinter as tk
        self.hide_tooltip()
        self.tooltip = tk.Toplevel(self.root)
        self.tooltip.overrideredirect(True)
        x = min(button.winfo_rootx(), max(0, self.root.winfo_screenwidth() - 330))
        y = min(button.winfo_rooty() + button.winfo_height() + 5, max(0, self.root.winfo_screenheight() - 160))
        self.tooltip.geometry(f"+{x}+{y}")
        tk.Label(self.tooltip, text=ACTION_HELP[action][1].split("\n\n")[0] + "\nCliquez sur ? pour les détails.", wraplength=300,
                 background="#15375a", foreground="#ffffff", font=("Segoe UI", 10), justify="left", padx=12, pady=10).pack()

    def hide_tooltip(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

    def resize_body(self, event):
        self.canvas.itemconfigure(self.body_window, width=event.width)
        for label, columns, margin in self.descriptions:
            label.configure(wraplength=max(160, event.width // columns - margin))
        for label in self.card_titles:
            label.configure(wraplength=max(95, event.width // 2 - 148))

    def update_scrollbar(self, first, last):
        self.body_scrollbar.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            self.body_scrollbar.pack_forget()
        elif not self.body_scrollbar.winfo_manager():
            self.body_scrollbar.pack(side="right", fill="y", before=self.canvas)

    def scroll_body(self, event):
        if event.widget not in {self.output, self.organization}:
            self.canvas.yview_scroll(-int(event.delta / 120), "units")

    def toggle_details(self):
        self.details_visible = not self.details_visible
        if self.details_visible:
            self.output_frame.grid()
        else:
            self.output_frame.grid_remove()
        self.details_button.configure(text="Détails ▴" if self.details_visible else "Détails ▾")

    def log(self, message):
        self.output.configure(state="normal")
        self.output.insert("end", message + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def execute(self, action):
        if self.busy:
            return
        self.busy = True
        for button in self.buttons:
            button.configure(state="disabled")
        self.organization.configure(state="disabled")
        self.activity.pack(fill="x", pady=(8, 0))
        self.activity.start(12)
        self.status_dot.itemconfigure(self.dot, fill="#6695ba")
        self.message.set("Traitement en cours…")
        organization = self.organizations[self.organization.current()].key

        def worker():
            started_at = time.monotonic()
            try:
                if action == "status":
                    result = self.controller.status()
                elif action == "stop":
                    result = self.controller.stop()
                else:
                    result = self.controller.launch(action, organization)
                self.events.put(("done", (action, result, time.monotonic() - started_at)))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=worker, name="Structura launcher command", daemon=False).start()

    def poll(self):
        from tkinter import messagebox
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress":
                    self.message.set(payload)
                    self.log(payload)
                    continue
                self.busy = False
                self.activity.stop()
                self.activity.pack_forget()
                self.status_dot.itemconfigure(self.dot, fill="#66a28c")
                self.organization.configure(state="readonly")
                for button in self.buttons:
                    button.configure(state="normal")
                if kind == "error":
                    self.status_dot.itemconfigure(self.dot, fill="#c76a75")
                    self.close_after_stop = False
                    self.message.set("Action non terminée. Consultez le détail ci-dessous.")
                    self.log(payload)
                    if not self.details_visible:
                        self.toggle_details()
                    messagebox.showerror("Structura", payload, parent=self.root)
                else:
                    action, result, elapsed = payload
                    duration = f"{elapsed:.1f}".replace(".", ",")
                    self.message.set((f"Services arrêtés en {duration} s." if result else "Aucun service ouvert par ce lanceur à arrêter.") if action == "stop" else "Espace ouvert dans le navigateur.")
                    if action == "status":
                        count = sum(row['running'] for row in result)
                        self.message.set(f"{count} service(s) actif(s). Consultez les détails pour la liste.")
                        if not self.details_visible:
                            self.toggle_details()
                        for row in result:
                            self.log(f"{row['name']} : {'actif' if row['running'] else 'arrêté ou indisponible'} · port {row['port']}")
                    elif action == "stop":
                        self.log(f"Arrêt terminé en {duration} s. Les données enregistrées sont conservées.")
                    else:
                        self.log("Navigateur ouvert : " + result["url"])
                        for warning in result["warnings"]:
                            self.log(warning)
                    if self.close_after_stop:
                        self.root.destroy()
                        return
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def close(self):
        from tkinter import messagebox
        if self.busy:
            messagebox.showinfo("Structura", "Attendez la fin de l'action avant de fermer le lanceur.", parent=self.root)
            return
        choice = messagebox.askyesnocancel("Fermer le lanceur", "Arrêter les espaces ouverts depuis ce lanceur avant de fermer ?\n\nOui : arrêter ces services.\nNon : les laisser disponibles.\nAnnuler : garder le lanceur ouvert.", parent=self.root)
        if choice is True:
            self.close_after_stop = True
            self.execute("stop")
        elif choice is False:
            self.root.destroy()


def main():
    import tkinter as tk
    from tkinter import messagebox
    import os
    import traceback
    from .deployment import atomic_json
    root = tk.Tk()
    status_path = ROOT / ".runtime" / "hybrid-saas" / "launcher-ui.json"
    failures = []

    def report_error(error_type, error, trace):
        failures.append(str(error))
        atomic_json(status_path, {"pid": os.getpid(), "ready": False, "error": str(error)})
        with (status_path.parent / "launcher-ui.log").open("a", encoding="utf-8") as output:
            traceback.print_exception(error_type, error, trace, file=output)

    root.report_callback_exception = report_error
    try:
        controller = Launcher()
        LauncherWindow(root, controller)
        root.update_idletasks()
        if not failures:
            atomic_json(status_path, {"pid": os.getpid(), "ready": True, "error": None})
    except Exception as exc:
        if status_path.parent.exists():
            atomic_json(status_path, {"pid": os.getpid(), "ready": False, "error": str(exc)})
        root.title("Structura — lancement impossible")
        messagebox.showerror("Structura — lancement impossible", str(exc), parent=root)
        root.destroy()
        return
    root.mainloop()
