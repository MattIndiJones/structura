# Diagnostic d'une installation : journaux, erreurs absorbées, santé

État local au 19/11/2026. Réponse à P1-9 de l'[audit technique du 16/11](../../audits/AUDIT_GLOBAL_TECHNIQUE_2026-11-16.md),
section 6.3.

## Le constat

- Aucune configuration de journalisation. Les écritures `INFO` du code (couverture de
  l'ordonnanceur, calendriers de place, échecs fournisseur) se perdaient. Seuls les
  avertissements et les erreurs atteignaient la console, par le gestionnaire de dernier recours
  de Python.
- Les traces d'appel des erreurs de requête partaient sur les journaux d'uvicorn, qui ne
  remontent pas au journal racine.
- Le lanceur redirige la console de chaque installation dans `logs/server.log`, sans rotation.
- `/health` ne touchait pas la base.

## Ce qui est en place

**Un journal par installation** (`backend/app/logging_setup.py`). Au démarrage, l'application
écrit dans `<dossier de données>/logs/structura.log`, rotation à 5 Mo, cinq copies, niveau
`INFO` ou `STRUCTURA_LOG_LEVEL`. La console garde son comportement d'avant : `WARNING` et plus.
Les journaux d'uvicorn reçoivent le même fichier, donc la trace d'une erreur de requête y
arrive. Le journal d'accès, une ligne par requête, en reste exclu. Les bibliothèques qui
journalisent chaque appel HTTP (`httpx`, `yfinance`…) sont ramenées à `WARNING`. En mode
consultation, aucun fichier n'est écrit dans l'installation lue.

**`server.log` tourne au lancement** (`hybrid/deployment.py`) au-delà de 10 Mo, trois copies. Il
ne peut pas tourner pendant que le serveur y écrit.

**Les tâches de fond** (ordonnanceur du cycle de vie, transport RFQ) journalisent l'exception
qui les arrêterait, avec sa trace. Le cycle de transport interrompu garde désormais la sienne.

**Les erreurs absorbées sur les chemins d'exploitation** écrivent leur trace avant d'être
rendues comme message :

| Chemin | Module |
|---|---|
| Refresh d'un deal par l'ordonnanceur | `services/lifecycle_alerts.py` |
| P&L explain et barrières du portefeuille, deal par deal | `api/portfolios.py` |
| Calcul de la file en échec (trace du processus fils) | `core/compute/executor.py` |
| Historique fournisseur en échec | `services/market_data.py` |
| Change de reporting et téléchargement des cours AMC | `core/amc_prices.py` |
| Échéancier non figé au booking | `api/deals/common.py` |
| Constatations, valorisation et Greeks du générateur UAT | `services/uat_generation.py` |
| Script du snapshot client illisible, mode FIFO | `core/client_technical.py`, `api/fifo.py` |

**La santé contrôle la base.** `/health` vérifie que le schéma est lisible (table `users`) et que
les clés étrangères sont appliquées, en deux secondes au plus. SQLite crée une base vide à la
connexion : un `SELECT 1` aurait répondu « ok » sur une base absente ou mal située. Les
lanceurs et l'atelier identifient leur instance sur cette route et exigent un 200 : une base en
défaut y donne donc `status: "degraded"` et le détail dans `database`. La nouvelle route
`/health/ready` renvoie 503 dans ce cas, pour un superviseur.

## Ce qui reste

- **Sur 99 blocs qui absorbent une erreur sans rien écrire**, 13 sont traités ci-dessus.
  Ceux qui restent :
  - les replis de formatage voulus ;
  - les blocs de l'étude AMC (`core/amc_*`), à reprendre lors de son passage sous QISTRA ;
  - l'atelier, qui consigne déjà ses incidents ;
  - le travailleur de transcription, qui rend son erreur en JSON à son parent ;
  - le parseur PayScript, qui transforme l'erreur en diagnostic de script.

  Le recensement se refait avec un parcours de l'AST : `except Exception` ou nu, sans `raise`
  ni appel de journal.
- Les processus du pool de calcul ne configurent pas de journal. Leur trace remonte par le
  parent quand le calcul échoue.
- Pas de métriques ni d'alerte : c'est P2-6.

## Vérification

- 13 tests ajoutés dans `test_process_logging.py` :
  - fichier d'installation, idempotence, niveau ;
  - trace d'uvicorn avec ou sans sa configuration ;
  - consultation, tâche de fond, rotation ;
  - santé sur une base saine, sans schéma, sans contrainte, muette ou inaccessible.
- 1 082 tests des 49 fichiers consommateurs, lanceurs et atelier compris, réussis.
- Sonde hors pytest sur un dossier de données temporaire : le fichier se crée au démarrage,
  `/health` répond `SCHEMA_ABSENT` et `/health/ready` renvoie 503 sur la base vide.
- Le backend réel n'a pas été démarré.
