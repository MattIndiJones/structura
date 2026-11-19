# Pricing interactif en file : délai et annulation

État local au 19/11/2026. Réponse à P1-4 de l'[audit technique du 16/11](../../audits/AUDIT_GLOBAL_TECHNIQUE_2026-11-16.md)
(A3, F6), et au reste de P0-7 : un script qui ne se termine pas ne bloque plus le serveur.

## Le constat

Le Pricer calculait dans la requête HTTP, sur un fil du serveur. Rien ne bornait sa durée et
rien ne pouvait l'arrêter. Fermer l'onglet n'y changeait rien. Un fil ne se tue pas en Python :
seul un redémarrage du serveur libérait un calcul parti trop loin.

## Ce qui est en place

**Les calculs tournent dans des processus que le serveur peut tuer**
(`core/compute/interactive.py`). Ces processus sont démarrés d'avance. Un processus neuf passe
4 à 7 s à importer l'application avant son premier prix (mesure du 19/11 sur ce poste) ; un
processus déjà chaud reçoit son calcul en 1 ms. Deux processus par défaut
(`STRUCTURA_PRICING_WORKERS`) sont préchauffés au démarrage du serveur, sauf sous pytest et
dans les instances de l'atelier, qui les démarrent au premier calcul.

**Trois issues arrêtent un calcul.** Le processus est alors tué, puis remplacé en arrière-plan
sans toucher aux autres :

| Issue | Déclencheur | Code rendu |
|---|---|---|
| Annulation | bouton « Annuler » du Pricer | 499 |
| Délai dépassé | 600 s de calcul (`STRUCTURA_PRICING_TIMEOUT_SECONDS`), file d'attente non comprise | 504 |
| Abandon | plus aucun écran ne suit le calcul depuis 120 s | 499 |

Le délai d'abandon tient compte des onglets en arrière-plan : le navigateur y ralentit le
suivi jusqu'à une interrogation par minute.

**Les routes** (`api/pricing_jobs.py`) : `POST /api/price/jobs/price`, `/in-life`,
`/implied-funding`, puis `GET` et `DELETE /api/price/jobs/{id}`. La requête est validée avant
d'entrer dans la file : une saisie invalide reste un 422 immédiat. Le calcul appelle la même
fonction que la route synchrone. Le prix en file est donc celui de la route, au 1e-12 près, et
un refus du moteur garde son code et son message. Un calcul n'est visible que de son
utilisateur, et chacun en a au plus quatre en attente ou en cours (429 au-delà). La trace
d'une erreur imprévue va au journal de l'installation, pas à l'écran.

**Le Pricer** passe par la file pour le prix, le prix en cours de vie, les Greeks et le
spread implicite (`frontend/src/utils/pricingJobs.js`). Sous la barre de progression, il
affiche l'attente ou le temps écoulé, avec un bouton « Annuler ». Un calcul que l'écran
remplace est arrêté côté serveur.

**Les routes synchrones restent** pour le booking, l'appel d'offres, les scripts et les tests.

## Ce qui reste

- Les autres analyses du Pricer (profil, trajectoires, probabilités, backtest, solveur,
  grille, MTF) restent synchrones. Elles passeront par la même file avec une entrée par
  fonction dans `execute`.
- Les routes synchrones n'ont toujours ni délai ni annulation.
- Les calculs en file vivent en mémoire : un redémarrage du serveur les perd, comme les
  requêtes qu'ils remplacent.

## Vérification

- 15 tests backend dans `test_pricing_jobs.py`, sur de vrais processus. Ils couvrent :
  - le résultat, le refus 422 et l'erreur 500 dont la trace part au journal ;
  - l'annulation, le délai, l'abandon et un processus qui meurt, tous suivis d'un
    remplacement ;
  - la file d'attente, la propriété des calculs, le plafond par utilisateur et l'arrêt du
    serveur ;
  - un prix identique à la route synchrone, et un script invalide rendu en 422 ;
  - les routes : 202, 404 pour un autre utilisateur, 422 avant la file, 429.
- 275 tests backend réussis : ces 15, plus les fichiers qui chargent `main.py`.
- Côté frontend :
  - 8 tests du protocole de file et 3 tests du store : suivi, annulation, double clic ;
  - les 195 tests front qui pricent restent verts, grâce à un raccord dans `src/test/setup.js`
    qui ramène la file à la route synchrone ;
  - `npm run build` passe.
- Sonde hors pytest dans la configuration de `run.py` (paquet `app`), à 20 000 trajectoires :
  - le premier processus est prêt en 3,1 s ;
  - même prix en file (1,36 s) et en direct (1,21 s) ;
  - un calcul à 200 000 trajectoires s'annule en 0,07 s.
- Le backend réel n'a pas été redémarré.
