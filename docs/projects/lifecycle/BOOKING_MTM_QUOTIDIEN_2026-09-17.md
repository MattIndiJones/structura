# Booking : MtM quotidien et progression du calcul — 17/09/2026

## Diagnostic

La page ne calculait pas automatiquement les MtM à son ouverture. Elle appelait
`GET /api/deals/valuation-runs/latest-mtm`, qui renvoyait le dernier run sans
restriction temporelle. `applySavedMtm` restaurait le résultat **et écrasait les
sélecteurs** avec le mode et la date de ce run. Le défaut `realized` existait donc
déjà mais était remplacé par un ancien run `none`. La date locale était également
figée au montage de la page. Pendant un calcul, le seul message disponible était
« Calcul du MTM en cours », sans distinction du chargement de marché.

## Comportement corrigé

- Chaque ouverture propose **Marché actuel** et la **date locale du jour**.
- La restauration automatique exige un calcul créé dans cette journée locale,
  une valorisation à cette même date, le mode `realized`, une fenêtre standard de
  252 rendements, aucune surcharge de taux/sous-jacent et la version contractuelle
  courante. Elle ne modifie jamais les sélecteurs. Un run incompatible plus récent
  n'empêche pas de retrouver le dernier run compatible de la journée.
- Les bornes de la journée sont calculées dans le navigateur puis transmises en
  UTC au serveur, y compris lors des changements d'heure. Les timestamps SQLite
  sans suffixe sont interprétés comme UTC, et non comme heure locale.
- Les résultats visibles expirent à minuit local ; le retour dans un onglet
  suspendu resynchronise également la journée. Un calcul lancé avant minuit ne
  revient pas dans les résultats du lendemain. Il reste conservé dans l'historique.
- Les réponses tardives de restauration ne remplacent ni un choix manuel ni un
  nouveau calcul. Le changement de paramètres et les doubles clics sont bloqués
  pendant le calcul concerné.
- Date de **valorisation**, heure d'**exécution** et indication de **restauration**
  sont affichées séparément. L'historique append-only reste intégralement conservé.

## Progression et données

`POST /api/deals/{id}/mtm?stream=true` émet des messages NDJSON aux étapes réelles :
chargement des cours, chargement/calibration des paramètres (mode réalisé), calcul,
enregistrement. Les erreurs sont aussi transmises dans ce flux. L'appel JSON
existant reste compatible. Le worker possède sa propre session DB, revérifie les
droits et enregistre un seul run par appel explicite.

La correction ne modifie aucune formule ni priorité de source : le cache de prix
existant est réutilisé lorsqu'il est valide (TTL 120 secondes, clé incluant les dates
et la convention ajusté/nu). Les données manquantes sont chargées par les services
existants. Aucun deuxième chargement préliminaire ni recalcul supplémentaire n'est
introduit pour afficher les étapes.

« Marché actuel » utilise les cours disponibles à la date demandée, la volatilité
réalisée, les corrélations et les dividendes courants ; le modèle est GBM. Les taux
et le funding demeurent ceux du booking, conformément au contrat existant affiché
dans l'interface. La date de valorisation ne signifie pas que toutes les places
boursières ont déjà publié une clôture ce jour-là. La provenance et les avertissements
de clôture ancienne restent disponibles.

## Validation et activation

- Frontend : tests de restauration, dates locales/UTC, expiration, course entre
  requêtes, doubles clics, flux fragmenté et erreurs ; build de production effectué.
- Backend : tests en SQLite temporaire, données synthétiques sans appel externe ;
  contrôle d'accès, filtre quotidien, historique préservé, étapes reçues avant la
  fin du calcul, égalité stricte du MtM JSON/stream, un enregistrement par appel et
  absence d'enregistrement sur erreur de marché.
- Le groupe `test_booking_mtm_daily.py`, `test_chaine_pricing_booking_mtm.py`,
  `test_valuation_context.py` passe (16 tests).
- Le fichier historique `test_mtm_explain.py` a 7 échecs liés à ses fixtures sans
  Product canonique (`DEAL_PRODUCT_MISSING`), exigence présente dans les changements
  locaux antérieurs à cette correction. Ces fixtures et cette exigence n'ont pas
  été modifiées dans ce chantier.
- Contrôle du compte test dans le navigateur : anciens MtM absents, sélection
  « Marché actuel », date 17/09/2026 et sélection manuelle du mode booking.
  Au dernier rechargement, le port 8000 refusait la connexion (confirmé également
  par une requête HTTP locale) ; la recette navigateur après redémarrage et la
  vérification en largeur réduite restent à faire.

Le backend local doit être redémarré par son propriétaire pour charger les filtres
serveur et la progression NDJSON, puis la page rechargée. Aucun redémarrage backend
ni calcul de recette écrivant dans la base réelle n'a été lancé par l'agent.
