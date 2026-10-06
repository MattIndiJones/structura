# PayScript — UNDERLYING, StartDate et paramètres Economics

**État au 06/10/2026 : audit statique et proposition, sans implémentation.**
Demande de Philippe : examiner l'existant avant de coder, reprendre les modèles
Normal/Expert, déclarer les paramètres sans valeur obligatoire, rendre le fixing
initial explicite et séparer les flux coupon, capital et put.

Philippe précise que les deals actuels sont des tests destinés à être supprimés :
aucune migration de ces deals n'est requise pour ce chantier. Cet audit ne supprime
aucune donnée ; cette précision ne vaut pas instruction de vider toute la base
(scripts personnels, RFQ, études, référentiels, etc.).

## 1. Contrat demandé et conventions proposées

- `UNDERLYING Basket` référence la composition sélectionnée dans Economics.
  Ce n'est pas un deuxième panier à saisir dans le script. L'identité et l'ordre
  des actifs appartiennent aux termes du Product ; les hypothèses de marché
  demeurent dans le contexte de calcul.
- `PARAM COUPON` déclare un paramètre requis, en pourcentage par défaut.
  Une saisie de 8 dans Economics donne 0,08 au moteur. Sans saisie, le produit
  peut rester un brouillon mais ne peut pas être pricé, coté ou booké.
  Une déclaration explicite telle que `PARAM GEARING = 1.5` conserve une valeur
  brute ; `PARAM COUPON = 8%` reste une déclaration avec défaut explicite.
  Une multiplication par 100 dans une expression reste une opération arithmétique.
  Étendre la même convention aux paramètres par observation `PARAM()`.
- `CONSTAT StartDate` reçoit une date dans Economics. Le bloc `AT StartDate`
  initialise `Basket.spot0 = Basket.spot@StartDate`, une fois par actif.
  La déclaration de calendrier et l'affectation déterminent le rôle de fixing ;
  éviter une nouvelle dépendance cachée à la seule orthographe « StartDate ».
- Proposition de sémantique : `Basket.spot` représente les cours au constat,
  `Basket.spot0` les cours initiaux, `Basket.yield` leurs ratios actif par actif.
  Ainsi 105 / 100 donne 1,05, et non 0,05. `WORSTOF`, `BESTOF`, `AVG`
  agrègent ces ratios ; `AVG` est équipondéré. Ne pas moyenner des cours bruts.
  Le moteur peut conserver ses trajectoires normalisées en interne : ne pas
  exposer un cours normalisé comme un cours brut dans la trace utilisateur.
- `AT Date FROM ObservationDates` parcourt les observations. `Date` est locale
  au bloc et `INDEX` commence à 1 à la première observation, hors fixing initial.
- La dernière observation exécute le bloc de rappel avant le bloc terminal,
  conformément à l'ordre du script. `STOP` empêche tout deuxième remboursement.
  Conserver des lignes de flux distinctes, y compris une ligne de put de valeur
  nulle, et leurs propres dates de paiement.
- Pour le script proposé, `COUPON * INDEX` signifie coupon par observation
  cumulé au rappel. Ce n'est pas automatiquement un taux annualisé proratisé.
  Le cas sans rappel ne paie pas de coupon terminal sauf instruction explicite.
- Un fixing initial sur plusieurs dates exige une réduction explicite et la
  définition de la disponibilité du strike. Un simple `CONSTAT() StartDate`
  ne doit pas réinitialiser S0 à chaque relevé. Préserver les produits à fenêtre
  initiale existants avec une sémantique explicite, sans inventer cette réduction.

## 2. Ce qui existe, vérifié dans les sources

| Domaine | Existant vérifié | Modification prévue |
|---|---|---|
| Langage | `parser.py` refuse les PARAM sans défaut. Aucun objet UNDERLYING ; expressions et identifiants sont traduits par le compilateur. BASKET est déjà du vocabulaire réservé. | Déclarations avec défaut facultatif, objet sous-jacent dans un espace de noms défini, accès autorisés aux propriétés et fixings, boucle Date FROM ; aucune évaluation arbitraire d'attributs. |
| API de parsing | `api/pricing.py` renvoie paramètres, calendriers, dates littérales et monitors, sans rôle explicite de fixing initial. | Retourner les paramètres requis/unités/défauts facultatifs, les liaisons de sous-jacents et les rôles de calendrier pour piloter les masques. |
| Economics | `EconomicsTab.vue` et `stores/pricing.js` possèdent le panier, une date de strike globale et des calendriers dynamiques. Des consommateurs se replient sur `raw_default`. | Un seul champ éditable « StartDate / fixing initial », relié au calendrier ; validation de toutes les valeurs requises côté UI et serveur, conversion % à une frontière unique. |
| RFQ | `RfqParamsEditor.vue` génère PARAM/CONSTAT depuis le parsing, mais `RfqView.vue` conserve ses propres dates de strike, conversions, restaurations et paniers. L'éditeur de PARAM n'offre qu'une saisie scalaire ; les fenêtres ne sont pas reprises comme dans Economics. | Partager le contrat de formulaire et les conversions avec Economics ; création, détail et duplication doivent préserver scalaires, tableaux, fenêtres, StartDate et panier. Éviter deux strikes éditables. |
| Calendriers | `resolve_constats::_resolve_full` retire `dates[0]` et `payments[0]` des calendriers générés. Le champ start_date est une borne de début de période, pas la première observation. `buildModelCalendars` le remplit avec le strike. | Séparer fixing initial, première observation incluse, fin/fréquence/roll et début d'accumulation des produits à période. Adapter ensemble prévisualisation et résolution. |
| Moteur | `payscript/engine.py` possède des mécanismes de strike différé et de fenêtre STRIKE_FIX. Les événements ordinaires sont souvent ramenés au pas 1 minimum. | Compiler l'initialisation en un événement de fixing dédié, à t=0 quand approprié, sans la transformer en observation au premier pas de simulation. Raccorder les branches de calcul et le rejeu. |
| Product | `product/inputs.py` sépare identités contractuelles et contexte de marché ; `pricing_input` exige le même nombre et ordre d'actifs. `terms_from_input` matérialise encore les défauts du script. | Réutiliser ce propriétaire contractuel ; enregistrer la liaison Basket, les valeurs effectives et un calendrier résolu cohérent. Le champ technique strike_date peut subsister comme projection contrôlée de StartDate. |
| Booking | `api/deals.py` crée manuellement un DealEvent « Strike / Fixing S₀ » d'index 0 et des relevés supplémentaires pour une fenêtre de départ. L'aperçu Economics ajoute aussi sa ligne de strike. | Consommer le fixing du calendrier canonique et dédupliquer l'événement ; geler S0 par actif, indépendamment des observations de coupon/rappel. |
| Flux | `FluxDecomposition.vue` affiche plusieurs lignes par couple constat/paiement. Le moteur ignore actuellement les flux nuls et sa clé de regroupement utilise temps + libellé. | Identifier la jambe PAY et son règlement, préserver les zéros pour la décomposition, distinguer présence de la ligne et fréquence d'activation du put. Réconcilier la somme des PV au prix. |
| Monitoring | `_analyze_monitors` recherche des comparaisons textuelles avec les observables connues. | Suivre la définition de PERF jusqu'à WORSTOF/BESTOF/AVG ; ne pas perdre les barrières M_ de la watchlist à cause de l'alias. |
| Normal/Expert | `PayScriptEditor.vue` sélectionne deux bibliothèques ; son aide précise que le bouton ne convertit pas le script. Les préremplissages Expert ont leur propre logique de dates. | Même payoff et même fixing dans les deux modes ; Normal expose les champs usuels, Expert les fenêtres, périodes et réglages détaillés. Centraliser les préremplissages. |
| Catalogue/Optimizer | Les sources sont `productCatalogue.json` et `payscriptTemplates.js`, leurs copies Python sont générées. L'Optimizer construit encore OBSERVATIONS avec start_date = strike_date. | Reprendre tout le catalogue et les deux bibliothèques, régénérer les copies Python, adapter l'Optimizer et ses transferts au Pricer. |

Les chemins ci-dessus sont sous `backend/app/` ou `frontend/src/` selon leur domaine.
Les fonctions et composants ont été lus ; aucun test ni parcours navigateur n'a
été exécuté pour cet audit. Les anomalies signalées restent des constats statiques.

## 3. Organisation des dates et des masques

Proposition pour un autocall annuel :

| Champ ou événement | Exemple | Effet |
|---|---|---|
| StartDate / fixing initial | 06/10/2026 | S0 par actif ; aucun rang de coupon |
| Première observation | 06/10/2027 | INDEX = 1 ; premier coupon/rappel possible |
| Fréquence | 1 an | Génération des échéances suivantes |
| Dernière observation | 06/10/2029 | INDEX = 3 ; rappel prioritaire puis maturité si survivant |
| Date de valeur et règlements | Saisies séparées | Cash et actualisation, sans déplacer le fixing |

Le contrat de calendrier doit distinguer les dates prévues et les dates ajustées
selon la convention saisie, sans ajouter de convention ouvrée silencieuse.
Ne pas supprimer globalement le découpage `dates[1:]` : les produits à moyenne
sur période ont encore besoin d'une borne de début d'accumulation distincte.
Lorsqu'un utilisateur déplace StartDate, les dates explicitement saisies ne doivent
pas changer silencieusement ; les champs issus d'un générateur identifié peuvent
être recalculés ensemble, avec aperçu des dates effectivement retenues.

Pricer, RFQ et Booking doivent lire la même représentation Product et le même
résultat de résolution. Le RFQ ne doit pas copier l'état mutable du Pricer :
il reçoit les termes du produit et conserve son contexte de marché propre.
À la réouverture, les dates et paramètres chargés font foi ; aucun retour aux
défauts du catalogue ou à la date du jour.

## 4. Ordre d'implémentation proposé

1. **Contrat du langage et Product.** Métadonnées PARAM, liaison UNDERLYING,
   fixing initial, observation et rang ; validation des entrées et persistance.
2. **Compilateur, calendriers et exécution.** Initialisation, expressions panier,
   priorité des blocs, STOP, fenêtres, scénarios déterministes et flux séparés.
   Adapter également sérialisation du calendrier, voies optimisées, simulations,
   solveur, grilles, pré-strike et valorisation résiduelle.
3. **Masques partagés.** Economics, RFQ création/détail/duplication, aperçu des
   événements et Booking : un seul strike et une première observation incluse.
   Harmoniser erreurs de parsing, états incomplets et conversions de PARAM().
4. **Catalogue complet et modes.** Reprendre les 19 fiches génériques et les
   exemples Normal/Expert, y compris options sans capital et produits à fenêtres.
   Décomposer le payoff de chaque famille sans ajouter de capital à une option
   pure ni changer implicitement la convention de coupon. Adapter l'Optimizer.
5. **Chaîne aval et documentation.** Fixings officiels, rejeu, MtM, watchlist,
   sensibilités et consommateurs du produit ; manuel PayScript, aide éditeur,
   prompt IA et skills devenus obsolètes. Le debug reste hors de ce chantier.

Pas de couche de migration des deals de test ni de contrainte de compatibilité
qui imposerait de conserver des ambiguïtés dans les nouveaux modèles. La suppression
future des données concernées doit respecter leurs liens ; elle est distincte de
la présente revue et ne nécessite pas une remise à zéro de toute la base.

## 5. Vérifications à réaliser lors du développement

- PARAM bare requis : 8 affiché devient 0,08 ; absence refusée, zéro explicite
  accepté, brut explicite préservé, tableaux conservés entre Pricer et RFQ.
- Deux actifs de cours initiaux différents donnent les bons ratios individuels ;
  changer leur ordre ne désolidarise pas identités, S0 et corrélations.
- StartDate initialise une seule fois ; première observation incluse au rang 1 ;
  périodes irrégulières, fenêtres, roll et règlement donnent les mêmes dates
  dans l'aperçu, le prix, la RFQ et le deal.
- Rappel aux première et dernière observations, absence de rappel, égalités
  aux barrières, perte terminale : coupon/capital/put attendus, nominal payé une
  seule fois, STOP effectif ; put nul visible sans faux taux d'activation.
- Normal/Expert équivalents à termes identiques ; dates et paramètres inchangés
  après chargement, duplication RFQ et Booking.
- Produit avant strike, au fixing puis en vie : S0 futur simulé ou fixing officiel
  connu selon le contexte, jamais recalé sur la première observation survivante.
- Tests ciblés des domaines modifiés et build frontend après changement Vue ;
  bases temporaires pour les tests. Pas de suite backend complète automatique.

## 6. Portée documentaire

La décision de Philippe remplace, pour le chantier à venir, l'obligation de défaut
PARAM des anciennes décisions D1/D4 et l'interdiction historique de modifier le
masque de pricing (M7). Elle ne signifie pas que la nouvelle syntaxe fonctionne
déjà. Le manuel `docs/reference/PAYSCRIPT_REFERENCE.md` et les skills décrivent
encore le langage livré : les modifier avec l'implémentation correspondante.

## 7. Précisions de Philippe après le premier cadrage

- Les modèles sont génériques et sans préremplissage économique : « Athena »,
  « Phoenix mémoire », etc., sans durée dans leur nom.
- Une configuration enregistrée porte séparément les valeurs à appliquer à un
  modèle/version. Action secondaire « Appliquer une configuration… », aperçu des
  valeurs remplacées ; accès identique en Normal et Expert, sans multiplier les
  copies de scripts. Les déclarations avec défaut explicite restent disponibles
  pour les scripts rédigés à la main.
- Refaire le lexique, le manuel Reference PayScript, les aides et les instructions
  de génération IA avec le nouveau langage.
- Supprimer les anciens scripts sauvegardés et remplacer les anciens modèles.
  Leur suppression et celle des deals de test sont demandées, mais pas exécutées
  pendant le cadrage. Inventorier leurs dépendances avant le nettoyage ; ne pas
  assimiler cette demande à la suppression générale de toutes les données métier.

## 8. Revue transversale complémentaire des consommateurs

**Méthode et limite :** recherche des dépendances dans les sources backend/frontend
et lecture des chemins sensibles identifiés. Ce contrôle cartographie les impacts ;
il ne constitue ni une recette de tous les modules, ni un inventaire des lignes de
la base utilisateur, ni une garantie de non-régression avant implémentation.

| Module / parcours | Dépendance vérifiée et traitement à prévoir |
|---|---|
| Solveur et grille de paramètres | `SolverPanel.vue::prefillBounds` et `PriceGridHeatmap.vue` centrent leurs bornes sur `raw_default`. Utiliser la valeur effective ou des bornes saisies. Dans un solveur, le paramètre recherché peut être absent au départ si les bornes sont explicites ; tous les autres paramètres requis doivent être fournis. La valeur candidate est injectée avant chaque pricing. Même principe pour les axes d'une grille et le coupon de l'Optimizer. |
| Analyses du Pricer | `api/pricing.py`, `api/simulation.py`, `api/scenarios.py` recompilent/résolvent les scripts pour profils, probabilités, chemins et scénarios. Leur transmettre les mêmes rôles de fixing, liaisons de panier et calendriers que le prix. |
| Calcul parallèle, stress et VaR/ES | `core/compute/pricers/{payscript,scenario_grid,var_scenario}.py` reconstruisent le compilé depuis du texte et certains reconstruisent explicitement `CompiledScript`. Transporter les nouvelles métadonnées et le strike réalisé ; partager la construction du résiduel pour éviter de perdre des champs ou de réinitialiser S0 dans un worker. `api/shocks.py` consomme aussi le contexte résiduel. |
| CCR / expositions futures | `core/ccr/service.py` dépend du compilateur, du Mark-to-Future et de la reconstruction résiduelle du worker VaR. Vérifier StartDate, état déjà réalisé, événements restants et fin d'exposition après remboursement. La réforme ne change pas la méthodologie de crédit. |
| In-life, fixings, alertes et portefeuille | `core/inlife_valuation.py`, `core/lifecycle_controls.py`, `core/deal_valuation.py` et les consommateurs Booking/Risk doivent conserver le fixing initial et le rang contractuel. Vérifier l'alimentation des agrégats et des alertes à partir des flux et événements canoniques. |
| Variantes, avenants et rolls | `core/variants.py` décale des dates CONSTAT et la date de strike pour un roll ; `params_moteur` convertit les unités. Adapter les champs de calendrier. Un roll initialise un nouveau produit ; un avenant conserve le strike historique et l'état passé. |
| KID et EMT | `api/kid.py` simule le payoff compilé ; `api/emt.py` analyse aussi le texte et les paramètres effectifs. Revoir la détection WORSTOF/BESTOF/AVG et des protections : changer la syntaxe ne doit pas modifier la qualification affichée du produit. |
| Notes de valorisation et Valo Explain | `core/valuation_note_support.py` lit calendrier et niveaux de barrières avec repli sur `stored_val`. Utiliser les valeurs effectives, distinguer fixing initial et observations, restituer les jambes séparées et les bons règlements. Les reconstructions résiduelles utilisées par Explain font partie du changement. |
| Clients, opportunités et indicatifs | `core/client_technical.py` déduit coupons et protections du script et de ses overrides ; `useProductSummary.js` décrit les calendriers. Préserver la synthèse commerciale et les liens Product/documents en utilisant les nouveaux paramètres et métadonnées. |
| Assistant de scripting | `services/llm/prompt.py` exige actuellement des défauts et des dates AT strictement positives. `_strip_fences` dans `validate.py` ne reconnaît pas UNDERLYING parmi les premières instructions et peut le retirer d'une réponse sans balises. Refaire prompt, extraction, exemples supplémentaires, validation et explication du payoff. |
| Administration / génération UAT | `services/uat_generation.py` fabrique ses propres scripts à PARAM chiffrés et calendriers OBSERVATIONS. Le raccorder aux nouveaux modèles et fournir explicitement ses economics de test ; éviter qu'il recrée les anciens scripts après nettoyage. |
| Persistance / calculs enregistrés | `product/calendar.py` sérialise explicitement les champs du compilé ; les versions Product et calculs enregistrés contiennent des snapshots. Mettre à jour sérialisation, restauration et invalidation des résultats devenus incompatibles. |
| Bibliothèque et suppression | `Script.parent_id` relie les variantes ; Deal, Indicative et RFQ ont un `script_id` et un `script_snapshot`. Les termes/révisions Product conservent également leur définition. Le DELETE de `scripts_db.py` traite les variantes mais ne nettoie pas toute cette chaîne. Préparer un inventaire des références et un nettoyage cohérent ; supprimer seulement `scripts` ne retire pas l'ancien langage des snapshots. |
| AMC / Studies / FIFO | Aucun appel direct au parser ou moteur PayScript identifié dans les routes et moteurs inspectés (`api/amc.py`, `api/amc_studies.py`, `api/fifo.py`, `core/amc_engine.py`, `core/fifo/`). Pas de refonte métier prévue pour eux ; préserver les référentiels et données partagés pendant le nettoyage. Cela ne dispense pas d'un contrôle des points communs effectivement modifiés. |

### Conséquences sur le plan

Centraliser trois opérations : résolution des valeurs effectives, compilation du
produit daté et construction de son état résiduel. Les modules et workers doivent
consommer ces opérations plutôt que recopier des conversions ou reconstruire
partiellement les nouveaux objets.

Ajouter aux critères de recette : prix direct/cohérence workers à entrées identiques,
stress nul cohérent avec le MtM, solveur fonctionnel sans défaut textuel, avenant
sans nouveau strike, roll avec nouveau fixing, documents cohérents avec le produit,
génération IA/UAT dans la nouvelle syntaxe, absence de références cassées après
nettoyage. Tests ciblés par domaine ; aucune suite backend complète automatique.

L'[audit transversal complémentaire](../../audits/AUDIT_TRANSVERSAL_PAYSCRIPT_2026-10-06.md)
ajoute l'inventaire en lecture seule : 0 script sauvegardé, 42 deals, 41 RFQ et
42 Products, avec leurs dépendances. Recompter avant toute suppression et qualifier
les liens concernés. Les RFQ/indicatifs/versions Product ne doivent pas
être effacés par simple supposition : traiter leurs liens et snapshots selon le
périmètre des données de test retenu, sans introduire une migration des deals.
