# Déploiement on-premise chez les clients — notes de discussion

Statut : discussion en cours (2026-07-25), rien d'implémenté. Reprise à prévoir.

## Décisions actées

- **Modèle** : on-premise, **un serveur par client** (pas de SaaS mutualisé) —
  cohérent avec la sensibilité des données (deals réels, confidentiels).
- **Environnement cible** : **Windows**, **un seul trader par serveur/poste**
  pour le moment (pas de LAN partagé, pas de multi-utilisateurs sur une même
  instance).
- **Support** : **pas de VPN/accès distant** dans un premier temps → le
  diagnostic se fera **par remontée de logs**.
- Conséquence réseau : comme c'est un poste unique, `run.py` (déjà bindé sur
  `127.0.0.1`) convient tel quel — pas de reverse proxy / TLS à ajouter tant
  qu'on reste sur ce modèle.

## État actuel de l'app (constats de la session)

- Backend FastAPI (`backend/run.py`), lancé manuellement, `host="127.0.0.1"`,
  `port=8000`, `reload=False`.
- Frontend Vue buildé (`frontend/dist`) servi **par le backend lui-même**
  (`main.py:106-115`, `StaticFiles` + `FileResponse`) — même origine, pas de
  besoin de CORS en théorie.
- Auth JWT (`backend/app/api/auth.py`) : secret en dur dans le code
  (`_SECRET = "structura-jwt-secret-change-in-prod"`), token 7 jours, hash
  bcrypt, comptes semés au boot (`admin`/`admin123`, `test`/`test123`).
- CORS actuellement `allow_origins=["*"]` (main.py:47) — sans intérêt/risque
  réel dans le modèle poste unique, mais à durcir si un jour on s'éloigne de
  ce modèle.
- DB SQLite locale (`backend/data/structura.db`), jamais versionnée.
- Symptôme observé : sur `localhost:8000`, il faut parfois rafraîchir pour
  voir l'appli — probablement un cache navigateur sur `index.html` (pas
  d'en-têtes de cache explicites sur `FileResponse`/`StaticFiles`), peut
  devenir trompeur après un rebuild du frontend.

## Chantiers identifiés (à faire, par priorité)

### Bloquant avant premier déploiement client

1. **Installeur autonome** — packager Python embarqué + venv figé + le
   frontend déjà buildé, livrable en un seul dossier/zip. Le trader n'a ni
   Python ni Node sur sa machine.
2. **Démarrage sans terminal** — enregistrer l'app comme service Windows
   (NSSM) ou tâche planifiée à l'ouverture de session ; le trader ouvre juste
   son navigateur sur `localhost:8000`.
3. **Secret JWT généré à l'installation** — un secret unique par machine
   plutôt que la valeur en dur dans le code (sinon tous les clients partagent
   la même clé).
4. **Fix du souci de cache navigateur** évoqué plus haut, avant livraison.

### Important mais pas bloquant pour le premier client

5. **Sauvegarde de `structura.db`** — un seul poste, un seul disque : à
   prévoir (copie planifiée vers un dossier réseau/cloud déjà utilisé par le
   client). Pas besoin d'infra de backup lourde vu l'échelle (1 trader).
6. **Procédure de mise à jour** — script qui arrête le service, remplace le
   code applicatif, préserve le dossier `data/`, relance. À documenter dès le
   2e client. Comme il n'y a pas de VPN, la livraison des mises à jour
   transitera aussi par un canal manuel (email, clé USB, drive partagé) — le
   cycle bug → fix → livraison sera lent, à annoncer au client.
7. **Logging exploitable sans accès distant** — en service Windows il n'y a
   plus de console visible : écrire dans un fichier avec rotation, à un
   chemin fixe et connu, facile à zipper/envoyer. Contenu à logger :
   exceptions non gérées (stack trace), erreurs métier (pricing, DB),
   démarrage/arrêt + version.
8. **Point sensible à trancher : contenu des logs.** Les erreurs de pricing
   contiennent naturellement des paramètres de deal (sous-jacents, strikes,
   notionnels...). Si ces logs sortent du poste du client vers Philippe, ça
   exporte potentiellement des données confidentielles hors de leur infra.
   Deux options : (a) logs techniques minimalistes, sans valeurs métier, ou
   (b) accepter des logs plus riches mais poser un cadre explicite avec le
   client (canal de transfert sécurisé, accord). Piste privilégiée pour
   l'instant : (a).

### Plus tard / sans urgence dans ce modèle

- CORS `*` et conteneurisation Docker ont peu d'intérêt tant qu'on reste sur
  poste unique Windows sans réseau — à reconsidérer seulement si le modèle
  évolue (LAN multi-trader, ou VPN/accès distant activé).

## Questions ouvertes à trancher à la reprise

- Logs : on part sur la version minimaliste (pas de valeurs de deal) par
  défaut, ou on ouvre la discussion avec le client sur un canal sécurisé pour
  des logs plus riches ?
- Mise à jour : quel canal concret pour livrer les nouvelles versions sans
  VPN (email, drive partagé, clé USB) ? Qui l'exécute chez le client (le
  trader lui-même, ou son IT) ?
- Installeur : packaging Python embarqué + NSSM, ou une autre approche
  (PyInstaller/Nuitka) ? À creuser techniquement.
- Sauvegarde de `structura.db` : vers quel emplacement concret chez le client
  (dépend de leur infra — à demander) ?
- Est-ce que le modèle "un serveur par client / un trader par serveur" est
  amené à évoluer (plusieurs traders par client) à moyen terme ? Ça
  changerait la priorité de LAN/TLS/reverse proxy.
