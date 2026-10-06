# Revue transversale avant refonte PayScript — 06/10/2026

**État : revue statique et inventaire SQLite en lecture seule ; aucune implémentation,
suppression, exécution de tests ou recette UI.** Complète le
[cadrage de la refonte](../projects/pricing/PAYSCRIPT_STARTDATE_UNDERLYING_DESIGN_2026-10-06.md).

## 1. Méthode et couverture

Inventaire des 40 fichiers Python de `backend/app/api/` (dont `__init__.py`) et
des 34 vues Vue de `frontend/src/views/`, puis recherches transversales dans les
composants, stores, composables, services, moteurs, schémas, scripts utilitaires
et tests. Lecture des chemins sensibles identifiés, notamment les constructions
de `CompiledScript`, défauts PARAM, résolutions de calendriers, rejeux, flux,
snapshots et références aux scripts.

La recherche ne s'est pas limitée aux imports du parser : ont aussi été suivis
les usages de `raw_default`, `stored_val`, `INDEX`, `STRIKE_FIX`, `script_snapshot`,
les copies de calendriers, préremplissages, contrôles textuels et fingerprints.
Ce travail identifie les points à adapter et tester ; il ne prétend pas démontrer
l'absence de toute régression avant le développement.

| Ensemble | Couverture / conséquence |
|---|---|
| Structuring, modèles, bibliothèque, éditeur, Pricer | Langage, panier, paramètres requis, brouillons, configurations, dates, flux et préremplissages. |
| Product, RFQ, indicatifs, Booking | Métadonnées et valeurs contractuelles, validation, aller-retour, preuves de pricing, versions et nettoyage des liens. |
| Profil, chemins, probabilités, backtests, comparateur | Même sémantique temporelle et mêmes fixings que le prix ; base initiale propre à chaque fenêtre historique. |
| Solveurs, grilles, Optimizer, Réinvestissement | Paramètres recherchés distincts des paramètres obligatoires connus ; dates reconstruites pour une nouvelle émission. |
| Événements, fixings, lifecycle, MtM, Greeks, Explain | Initialisation unique, rang préservé, passé réalisé, fenêtres partielles, paiements restant dus et monitoring. |
| Portefeuilles, stress, VaR/ES, CCR, workers | Contrat transporté intégralement et résiduel partagé ; pas de réinitialisation du strike pendant un choc. |
| KID, EMT, notes, PDF, restitution client | Sémantique de payoff et valeurs effectives ; calendrier et flux identiques au calcul sélectionné. |
| Clients, opportunités, RFQ Analysis, accueil | Synthèses et libellés, références Product/deals ; ne pas supprimer leurs référentiels pour nettoyer des produits de test. |
| IA, documentation, génération UAT, outils de démo | Éliminer les anciennes syntaxes actives et les instructions contradictoires, y compris hors catalogue. |
| Compute et traitements quotidiens | Charges de calcul, recompilation, caches et travaux en cours à prendre en compte lors de la bascule/nettoyage. |
| Market Data | Préserver cours nus, identité, devise, ordre des actifs et provenance des fixings ; aucun nouveau fournisseur requis. |
| AMC, Studies, FIFO ; authentification et référentiels | Aucune refonte PayScript directe identifiée dans les chemins inspectés. Préserver données et services partagés ; tester les points communs seulement s'ils sont modifiés. |

## 2. Compléments matériels au plan précédent

### A. Un modèle vierge ne peut pas être représenté comme un produit complet

`core/product/models.py::ContractParameter.value` exige un nombre ou une série,
`ProductTerms.T` une durée positive et `underlyings` au moins un actif. Modifier
seulement le parser ne permettra donc pas de sauvegarder un nouveau modèle sans
saisies économiques.

Prévoir explicitement l'état incomplet du brouillon et sa validation avant calcul,
RFQ exploitable et Booking. Ne pas inventer 0, trois ans ou un actif pour satisfaire
le schéma. Le modèle et la configuration restent distincts du produit complet.
Le solveur injecte sa valeur candidate avant chaque pricing ; il n'exige pas une
valeur préalable du paramètre qu'il cherche si ses bornes sont fournies.

### B. Plusieurs préremplissages échappent au catalogue

`stores/pricing.js::DEFAULT_SCRIPT` contient encore un Athena 3 ans à 8 %, et
`ProductModelsView.vue` construit un calendrier à partir d'aujourd'hui et d'un ténor.
`PayScriptEditor.vue` a son propre préremplissage Expert. Reprendre ouverture,
nouveau script, réinitialisation et changement de modèle, pas seulement les deux
fichiers de modèles. Une nouvelle fiche ne doit pas hériter silencieusement des
valeurs de la précédente. Conserver les saisies pendant une édition syntaxiquement
incomplète et rejeter les réponses asynchrones devenues périmées.

Les configurations doivent identifier modèle/version, valeurs, calendrier et
éventuel panier. Distinguer dates absolues et règles relatives réutilisables ;
résoudre les dates et montrer l'aperçu avant application. Prévoir les droits de
visibilité existants pour une configuration personnelle ou partagée.

### C. L'aperçu a une deuxième exclusion de la première date

En plus du parser, `useObservationPreview.js::chargerCalendrier` applique
`data.dates.slice(1)` et ignore les CONSTAT simples lors de sa collecte. L'API
`schedule/generate` retourne les bornes du générateur, tandis que les aperçus
de fenêtres par période ont une autre forme. Adapter simultanément le contrat
d'API, les aperçus et le moteur. Ne pas corriger seulement l'étiquette « Début ».

Vérifier observations le même jour, conventions ouvrées déplaçant des dates,
périodes courtes/longues, calendrier terminal à une date, fenêtres initiales et
rangs propres à plusieurs calendriers. Un fixing à t=0 doit rester t=0 ; il ne
doit pas être déplacé au premier pas Monte Carlo. Ne pas réordonner arbitrairement
les blocs de même date en raison de leur nom de calendrier.

### D. Réinvestissement et backtests ont leur propre reconstruction temporelle

`api/deals.py::reinvest_roll_endpoint` re-résout le calendrier sauvegardé avec
`anchor=date.today()`. La proposition/scan de réinvestissement et son PDF ont
aussi leurs propres chemins. Il faut reconstruire les dates d'une nouvelle
émission ; changer seulement l'ancre ne déplace pas les dates absolues.

`api/pricing.py::_windowed_backtest`, `engine.py::eval_script_on_history` et les
comparateurs doivent fixer S0 au départ de chaque fenêtre et translater le
calendrier sans lire des cours futurs. Les rolls et avenants restent distincts.
`variants.py` ne décale actuellement que les valeurs CONSTAT sous forme de dict :
la date simple StartDate exige aussi un traitement explicite.

### E. Les contrôles de payoff ne doivent plus dépendre de mots isolés

`lifecycle_controls.py::_PATH_OBSERVABLE` détecte les besoins de chemin par regex
(WOF_MIN, BOF_MAX, etc.). `semantic_maturity_outcome` inspecte la mémoire KI ;
la watchlist, l'EMT et le drilldown MTF ont d'autres analyses textuelles.
Produire les métadonnées d'observables, de dépendances temporelles et de barrières
dans le compilateur, avec indication explicite si une expression n'est pas
classifiable. Conserver le contrôle des données historiques/officielles requises
pour les barrières américaines, fenêtres et volatilité réalisée.

### F. Séparer jambes contractuelles et statistiques de cash

Le moteur historique conserve les flux PAY, mais le MC écarte les montants nuls
dans plusieurs sorties. L'Optimizer lit encore la durée comme la dernière date
de cash par trajectoire. Ajouter une ligne de put nul ne doit pas modifier une
durée, un taux de rappel, un nombre de paiements ou un TRI.

Prévoir identifiant de jambe, date de constat, date de paiement, montant et état
d'exécution ; séparer les dates de terminaison des dates de cash. Plusieurs PAY
au même libellé ou de règlements différents ne doivent pas être fusionnés.
Vérifier la réconciliation coupon + capital + put avec prix et pertes, ainsi que
les moyennes antithétiques et le nombre d'observations indépendantes des IC.

### G. Provenance et validité des calculs

`valuation_runs.py::engine_identity` hache actuellement cinq fichiers dont le
parser et le moteur. Si la sémantique est déplacée vers de nouveaux modules, cette
empreinte doit les couvrir. Les preuves signées de pricing, empreintes Product,
validité UI, caches CCR, versions de calendriers sérialisés et payloads Compute
doivent porter les nouvelles entrées pertinentes. Un prix précédent doit devenir
périmé si StartDate, Basket ou les economics changent.

Les jobs reprennent du texte et certaines voies recréent manuellement
`CompiledScript` : leur constructeur partagé doit conserver toutes les nouvelles
propriétés. Contrôler les tâches en attente et le traitement quotidien lors du
nettoyage, sans interrompre un serveur préexistant pendant cet audit.

### H. Langage, modèles numériques et budget

`Basket` entre en collision avec le mot BASKET historique : réserver un espace
de noms d'objet et des propriétés autorisées. Interdire les attributs arbitraires,
les références de dates non déclarées, les lectures de fixing indisponible et
l'utilisation de yield avant initialisation. Valider panier non vide, dimensions,
valeurs finies et dénominateurs initiaux admissibles.

Conserver le bon niveau de spot sous GBM, Heston, SABR, Local Vol et LSV, ainsi que
les conventions quanto/FX. Pour des Greeks ou un stress après fixing, S0 reste
fixe ; avant fixing, il est simulé selon le contrat. Ajouter des contrôles ciblés
des chemins concernés sans recalibrer ni changer les modèles pour cette refonte.
Les limites de `compute_budget.py` doivent compter les nouveaux fixings et dates
développées ; éviter de construire un objet Python par actif/pas/trajectoire.

### I. Les anciens scripts se trouvent aussi dans les outils et les tests

Outre `services/uat_generation.py`, `scripts/generate_demo_deals.py` fabrique de
nombreux anciens payoffs, `eval_script_assistant.py` attend WOF/WOF_MIN et les
scripts de synchronisation décrivent encore des défauts PARAM obligatoires.
Le store de tests frontend simule lui-même un parser simplifié : l'adapter avec
les contrats de réponse, plutôt que faire passer des tests contre une grammaire
fictive. Reprendre fixtures/exemples actifs ; conserver les archives historiques
identifiées comme telles. Mettre à jour CLAUDE/skills/manual/aides au moment de
la livraison, sans annoncer une syntaxe supportée avant qu'elle le soit.

## 3. Inventaire réel de la base locale

Lecture avec `sqlite3`, URI `mode=ro` et `PRAGMA query_only=ON`, sans import du
module d'initialisation de l'application. Fichier : `backend/data/structura.db`,
chemin confirmé dans `db/database.py`. État observé le 06/10/2026 ; recompter au
moment d'une suppression, car l'application peut avoir évolué entre-temps.

| Table / objet | Nombre observé |
|---|---:|
| Scripts sauvegardés | 0 |
| Indicatifs | 0 |
| Deals, tous avec script_snapshot | 42 |
| RFQ, toutes avec script_snapshot | 41 |
| Cotations RFQ | 82 |
| Products / versions de termes | 42 / 42 |
| Révisions Product | 543 |
| Calculs Product / commandes Product | 122 / 120 |
| Événements de deals | 316 |
| Versions de fixings officiels | 115 |
| Propositions lifecycle | 26 |
| Valorisation runs / stress runs | 78 / 8 |
| Notes de valorisation | 2 |
| Alertes / appartenances à des portefeuilles | 29 / 7 |
| Jobs / lots Compute | 0 / 0 |

La base comporte 64 tables. Les cinq racines scripts/deals/RFQ/indicatifs/Products
et leurs dépendances déclarées couvrent 24 tables, avec des clés étrangères
`NO ACTION` sur les liens inspectés. Il existe aussi des références dans des JSON
et des journaux : le seul graphe SQL ne suffit pas. Par exemple, 1 266 audit_events
et 8 scheduler_runs sont présents ; ces nombres ne signifient pas qu'ils doivent
être supprimés. Les tables CCR inventoriées sont vides à cette date.

**Conséquence :** la bibliothèque est déjà vide, mais les anciens scripts existent
dans les snapshots. Préparer un nettoyage cohérent des données de test autorisées,
de leurs dépendances et des résultats devenus sans objet. Il reste à déterminer,
enregistrement par enregistrement pour les liens hors deals/scripts, lesquels sont
inclus dans ce nettoyage. Ne pas transformer l'autorisation de supprimer les deals
et scripts en autorisation implicite de vider les clients, référentiels ou études.
Pas de migration de deals à prévoir.

## 4. Recette ciblée à prévoir pendant l'implémentation

| Invariant | Points d'appui existants |
|---|---|
| Syntaxe, unités, modèles génériques et documentation cohérente | `test_parser.py`, `test_payscript_reference.py`, `test_payscript_templates.py`, `test_product_catalogue.py` |
| Dates identiques dans aperçu/prix/Booking, fixing exclu des rangs | `test_pricing_anchor.py`, `test_schedule_model.py`, `test_schedule_settlement.py`, `test_constatations_periode.py` |
| Modèle vierge sauvegardable, calcul incomplet refusé, solveur autorisé pour sa variable cible | `test_products.py`, `test_product_analysis.py`, `test_pricing_validation_lot5.py`, tests frontend pricing/products/RFQ |
| Cash et état contractuel conservés en vie, rappel terminal sans doublon | `test_chaine_pricing_booking_mtm.py`, `test_inlife_pricing.py`, `test_lifecycle_fenetres.py`, `test_fixings_releves.py` |
| Workers/prix direct cohérents, stress nul, Greeks et MTF | `test_compute.py`, `test_greeks_stateful.py`, `test_mtf_fenetres.py`, `test_mtf_drilldown.py`, tests CCR ciblés |
| Historique et nouvelles émissions correctement ancrés | `test_backtest_oracle.py`, tests variantes roll/avenant/comparaison ; ajouter les cas Réinvestissement manquants |
| Documents et synthèses à valeurs effectives | `test_kid_mrm.py`, `test_emt.py`, `test_valuation_notes.py`, `test_valuation_pdf.py`, tests assistant IA |
| Suppression ciblée et absence de références cassées | Base temporaire représentant les relations inventoriées ; contrôle après nettoyage réel, pas de tests destructifs sur la base locale |

Exécuter les tests concernés au fil des lots, avec chemins déterministes et données
synthétiques ; build frontend après changements Vue. La suite backend complète
reste soumise à une demande explicite de Philippe. Les fichiers cités sont une
carte de couverture, pas une affirmation que les nouveaux cas existent déjà.

## 5. Points à préciser sans masquer un choix de payoff

La refonte demandée est définie pour un panier Economics et un fixing initial
ponctuel. Pour reprendre les produits avancés existants, préciser la syntaxe des
réductions de fixing initial et des observables de chemin : un CONSTAT() StartDate
seul ne choisit pas une moyenne, un min ou un max. Distinguer aussi moyenne dans
le temps et moyenne entre actifs. Les configurations à dates relatives devront
indiquer clairement leur date d'ancrage avant application.

Ces points entrent dans la spécification du langage avant leurs lots respectifs.
Ils ne justifient pas de conserver les anciens deals ni de préremplir les nouveaux
modèles. La prochaine étape est l'implémentation suivant ce périmètre, lorsque
Philippe demande de la commencer.
