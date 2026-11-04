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
        from .launcher_widgets import (
            BACKGROUND, INK, MUTED, BORDER, NAVY, COPPER, BrandPanel, RoundedButton,
        )
        self.root, self.controller = root, controller
        self.events = queue.Queue()
        self.busy = False
        self.close_after_stop = False
        self.tooltip = None
        self.details_visible = False
        self.descriptions = []
        self.card_titles = []
        self.panels = []
        root.title("Structura — Votre espace de travail")
        width = min(1100, root.winfo_screenwidth() - 80)
        height = min(820, root.winfo_screenheight() - 100)
        root.geometry(f"{width}x{height}+{max(0, (root.winfo_screenwidth() - width) // 2)}+{max(0, (root.winfo_screenheight() - height) // 2 - 25)}")
        root.minsize(min(width, 720), min(height, 610))
        root.configure(background=BACKGROUND)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background=BACKGROUND)
        style.configure("TLabel", background=BACKGROUND, foreground=INK, font=("Segoe UI", 10))
        style.configure("TCombobox", padding=(9, 6), font=("Segoe UI", 10),
                        fieldbackground="#f7f8f5", arrowcolor=MUTED, bordercolor=BORDER,
                        lightcolor=BORDER, darkcolor=BORDER)
        style.map("TCombobox", fieldbackground=[("readonly", "#f7f8f5"), ("disabled", "#ecefeb")],
                  foreground=[("readonly", INK), ("disabled", "#98a39f")],
                  selectbackground=[("readonly", "#f7f8f5")], selectforeground=[("readonly", INK)])
        style.configure("Horizontal.TProgressbar", background=COPPER, troughcolor=BACKGROUND,
                        borderwidth=0, thickness=3)
        style.configure("Vertical.TScrollbar", background="#d8ddd7", troughcolor=BACKGROUND,
                        borderwidth=0, arrowsize=10)
        self.shell = tk.Frame(root, background=BACKGROUND)
        self.shell.pack(fill="both", expand=True)
        self.shell.columnconfigure(1, weight=1)
        self.shell.rowconfigure(0, weight=1)
        self.brand_panel = BrandPanel(self.shell)
        self.brand_panel.grid(row=0, column=0, sticky="ns")
        frame = tk.Frame(self.shell, background=BACKGROUND, padx=30, pady=24)
        frame.grid(row=0, column=1, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        header = tk.Frame(frame, background=BACKGROUND)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text="BIENVENUE DANS STRUCTURA", background=BACKGROUND,
                 foreground=MUTED, font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w")
        self.heading = tk.Label(header, text="Votre espace de travail", background=BACKGROUND,
                                foreground=INK, font=("Segoe UI", 22, "bold"), anchor="w")
        self.heading.grid(row=1, column=0, sticky="w", pady=(5, 0))
        tk.Label(header, text="DÉVELOPPEMENT", background="#eeebe3", foreground="#8a765b",
                 font=("Segoe UI", 7, "bold"), padx=9, pady=5).grid(row=0, column=1, sticky="e")
        content = tk.Frame(frame, background=BACKGROUND)
        content.grid(row=1, column=0, sticky="nsew")
        self.body_scrollbar = ttk.Scrollbar(content, orient="vertical", style="Vertical.TScrollbar")
        self.body_scrollbar.pack(side="right", fill="y")
        self.canvas = tk.Canvas(content, background=BACKGROUND, highlightthickness=0,
                                yscrollcommand=self.update_scrollbar)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body_scrollbar.configure(command=self.canvas.yview)
        self.body = tk.Frame(self.canvas, background=BACKGROUND)
        self.body_window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self.resize_body)
        root.bind("<MouseWheel>", self.scroll_body, add="+")
        root.bind("<Configure>", self.resize_window, add="+")
        self.buttons = []
        self.card("Structura Admin", "Produits, pricing, RFQ et suivi de vie.\nVotre application complète.", "admin")
        section = tk.Frame(self.body, background=BACKGROUND)
        section.pack(fill="x", pady=(18, 11))
        tk.Label(section, text="EXPLORER LES ESPACES", background=BACKGROUND,
                 foreground=MUTED, font=("Segoe UI", 8, "bold")).pack(side="left")
        tk.Label(section, text="Choisissez votre accès", background=BACKGROUND,
                 foreground="#929b9e", font=("Segoe UI", 8)).pack(side="right")
        self.secondary = tk.Frame(self.body, background=BACKGROUND)
        self.secondary.pack(fill="x")
        for column in (0, 1):
            self.secondary.columnconfigure(column, weight=1, uniform="cards")
        for row in (0, 1):
            self.secondary.rowconfigure(row, weight=1, uniform="cards")
        for title, description, action in (
            ("Simulation avec agents", "Préparer et consulter vos campagnes.\nAucun agent lancé à l’ouverture.", "simulation"),
            ("Les six organisations", "Retrouver les installations privées\net leur portail commun.", "all"),
            ("Console SaaS", "Consulter l’annuaire et superviser\nles installations.", "platform"),
        ):
            self.card(title, description, action)
        organization_row = self.card("Une organisation", "Ouvrir directement son espace.", "organization")
        self.organizations = [c for c in controller.configs if c.kind == "organization"]
        self.organization = ttk.Combobox(organization_row, state="readonly", width=15,
                                        values=[c.name for c in self.organizations])
        self.organization.current(0)
        self.organization.grid(row=2, column=0, columnspan=2, sticky="ew", padx=(0, 10))
        controls = tk.Frame(frame, background=BACKGROUND)
        controls.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        tk.Frame(controls, background=BORDER, height=1).pack(fill="x", pady=(0, 13))
        actions = tk.Frame(controls, background=BACKGROUND)
        actions.pack(fill="x")
        for text, action in (("État des services", "status"), ("Arrêter Structura", "stop")):
            button = RoundedButton(actions, text=text, command=lambda choice=action: self.execute(choice),
                                   background=BACKGROUND, fill=BACKGROUND, border=BORDER,
                                   foreground="#9a5354" if action == "stop" else INK,
                                   hover="#f8eeeb" if action == "stop" else "#eaeee9", width=151, height=35,
                                   font=("Segoe UI", 9))
            button.pack(side="left", padx=(0, 7))
            self.buttons.append(button)
            self.help_button(actions, action).pack(side="left", padx=(0, 12))
        self.details_button = RoundedButton(actions, text="Détails ▾", command=self.toggle_details,
                                            background=BACKGROUND, fill=BACKGROUND, hover="#eaeee9",
                                            width=87, height=35, font=("Segoe UI", 9))
        self.details_button.pack(side="right")
        status = tk.Frame(frame, background=BACKGROUND)
        status.grid(row=3, column=0, sticky="ew", pady=(11, 0))
        self.message = tk.StringVar(value="Prêt à travailler")
        self.status_dot = tk.Canvas(status, width=12, height=18, background=BACKGROUND, highlightthickness=0)
        self.status_dot.pack(side="left", padx=(0, 5))
        self.dot = self.status_dot.create_oval(2, 6, 8, 12, fill="#6f9d88", outline="")
        self.status_label = tk.Label(status, textvariable=self.message, background=BACKGROUND,
                                     wraplength=600, foreground=MUTED, font=("Segoe UI", 9), justify="left")
        self.status_label.pack(side="left", anchor="w")
        self.activity = ttk.Progressbar(frame, mode="indeterminate")
        output_frame = tk.Frame(frame, background=BACKGROUND)
        output_frame.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self.output_frame = output_frame
        scrollbar = ttk.Scrollbar(output_frame)
        scrollbar.pack(side="right", fill="y")
        self.output = tk.Text(output_frame, height=5, wrap="word", state="disabled", yscrollcommand=scrollbar.set,
                              font=("Consolas", 9), relief="flat", background="#eeefe9",
                              foreground="#637580", padx=14, pady=12)
        self.output.pack(fill="both", expand=True)
        scrollbar.configure(command=self.output.yview)
        output_frame.grid_remove()
        root.protocol("WM_DELETE_WINDOW", self.close)
        controller.progress = lambda message: self.events.put(("progress", message))
        root.after(100, self.poll)

    def resize_window(self, event):
        if event.widget is not self.root:
            return
        if event.width < 1000:
            self.brand_panel.grid_remove()
        else:
            self.brand_panel.grid()

    def card(self, title, description, action):
        import tkinter as tk
        from .launcher_widgets import INK, MUTED, NAVY, RoundedPanel, RoundedButton, icon
        hero = action == "admin"
        surface = "#ffffff"
        panel = RoundedPanel(self.body if hero else self.secondary, fill=surface, padding=20 if hero else 16)
        self.panels.append(panel)
        if hero:
            panel.pack(fill="x")
        else:
            row, column = {"simulation": (0, 0), "all": (0, 1), "platform": (1, 0), "organization": (1, 1)}[action]
            panel.grid(row=row, column=column, sticky="nsew", padx=(0, 6) if column == 0 else (6, 0), pady=(0, 12))
        card = panel.body
        card.columnconfigure(0 if hero else 1, weight=1)
        if hero:
            tk.Label(card, text="APPLICATION COMPLÈTE", background=surface, foreground="#a07d50",
                     font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w")
            tk.Label(card, text=title, background=surface, foreground=INK,
                     font=("Segoe UI", 20, "bold")).grid(row=1, column=0, sticky="w", pady=(5, 5))
            label = tk.Label(card, text=description, background=surface, foreground=MUTED,
                             font=("Segoe UI", 10), justify="left", anchor="w")
            label.grid(row=2, column=0, sticky="ew")
            self.help_button(card, action).grid(row=0, column=1, sticky="ne")
            self.descriptions.append((label, 1, 300))
        else:
            icon(card, action).grid(row=0, column=0, sticky="nw", padx=(0, 10))
            title_label = tk.Label(card, text=title, background=surface, foreground=INK,
                                   font=("Segoe UI", 11, "bold"), anchor="w", justify="left", wraplength=220)
            title_label.grid(row=0, column=1, sticky="w")
            self.card_titles.append(title_label)
            self.help_button(card, action).grid(row=0, column=2, sticky="ne", padx=(6, 0))
            label = tk.Label(card, text=description, background=surface, foreground=MUTED,
                             font=("Segoe UI", 9), justify="left", anchor="w")
            label.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 10))
            card.rowconfigure(2, weight=1)
            self.descriptions.append((label, 2, 50))
        button = RoundedButton(card, text="Entrer dans Structura  →" if hero else "Ouvrir  →",
                               command=lambda: self.execute(action), background=surface,
                               fill=NAVY if hero else "#eef2f3", foreground="#ffffff" if hero else INK,
                               hover="#254c64" if hero else "#e1e9ec", width=230 if hero else 108,
                               height=40 if hero else 33, font=("Segoe UI", 10 if hero else 9, "bold"))
        if hero:
            button.grid(row=1, column=1, rowspan=2, sticky="se", padx=(18, 0))
        elif action == "organization":
            button.grid(row=2, column=2, sticky="e")
        else:
            button.grid(row=2, column=0, columnspan=3, sticky="sw")
        self.buttons.append(button)
        return card

    def help_button(self, parent, action):
        from .launcher_widgets import BACKGROUND, RoundedButton
        background = BACKGROUND if parent.winfo_class() == "TFrame" else parent.cget("background")
        button = RoundedButton(parent, text="?", command=lambda: self.show_help(action), background=background,
                               fill="#f3f3ee", foreground="#7a868c",
                               hover="#e8ece6", width=27, height=27, radius=14,
                               font=("Segoe UI", 9))
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
        self.status_label.configure(wraplength=max(260, event.width - 45))
        for label, columns, margin in self.descriptions:
            label.configure(wraplength=max(160, event.width // columns - margin))
        for label in self.card_titles:
            label.configure(wraplength=max(95, event.width // 2 - 140))

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
        self.activity.grid(row=5, column=0, sticky="ew", pady=(8, 0))
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
                self.activity.grid_remove()
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
