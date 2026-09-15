# Plan d’implémentation de l’objet Product dans Structura

Date : 14 septembre 2026  
Statut : première tranche implémentée sur la branche `codex/product-workflow`, en attente de revue et de commit.  
Périmètre : Structura, parcours produit hors AMC. Les principes INDEX_STUDIO fournis dans la conversation ne conduisent pas à introduire des concepts d’indices dans cette architecture.

## 0. État de l’implémentation au 14 septembre 2026

Cette branche livre le socle transversal demandé. Les sections suivantes conservent le plan directeur et ses lots de migration progressive ; elles ne signifient pas que toutes les compatibilités historiques ont déjà été retirées.

### Livré dans cette tranche

- Un `Product` Pydantic profondément figé, séparant les termes contractuels des hypothèses de marché et des résultats de calcul.
- Une création durable uniquement sur action « Conserver le produit ». Une session Nouveau Pricing reste sans identité ni ligne en base tant que cette action n’est pas déclenchée.
- Une identité stable, une référence lisible, une version de termes et une révision de dossier avec contrôle optimiste.
- Des tables additives pour l’identité, les versions de termes, les révisions, les calculs datés et l’idempotence des commandes. Les versions, révisions et calculs sont protégés contre `UPDATE` et `DELETE` au niveau SQLite.
- Une API de création, lecture, liste, archivage, révision explicite des termes, composition d’entrées de pricing et conservation de calculs signés.
- Une signature HMAC des reçus émis par les pricings neuf et en vie. Un prix modifié, un reçu non signé ou un calcul portant sur d’autres termes est refusé.
- Une bibliothèque « Mes Produits », une route de réouverture dans le Pricer et une barre de contexte distinguant clairement une session éphémère d’un Product conservé.
- Des termes verrouillés à la réouverture d’un Product. Le serveur recompose le pricing depuis la version de termes attendue et les seules hypothèses de marché transmises.
- Le rattachement Product/version dans RFQ, Booking, Deal, KID, EMT et documents, avec enrichissement du Product dans la transaction métier.
- Le calendrier résolu figé est réutilisé par le pricing, le pricing en vie, le MtM et les calculs dérivés au lieu d’être reconstruit à la date de lecture.
- Le lifecycle du Deal est projeté dans les révisions Product au booking, à la saisie/validation/rejet des fixings, au monitoring, aux exceptions et à l’application d’une résolution. Les observations de marché indicatives ne sont pas embarquées dans les termes du Product.
- Le MtM et la VaR prennent les termes du Product comme autorité pour les deals liés. Les anciens deals sans Product conservent leur chemin de compatibilité.
- L’AMC et Fama-French restent hors périmètre, conformément à la décision prise.

### Limites volontaires de cette tranche

- Aucun backfill automatique des deals, RFQ ou indicatifs historiques. Un lien Product n’est créé que par un parcours explicite et prouvé.
- Les colonnes historiques restent présentes pour les dossiers anciens et comme projections d’exécution. Leur retrait demande la migration contrôlée prévue dans les derniers lots.
- La modification des termes existe par API avant booking, avec création d’une nouvelle version et justification. L’interface de réouverture garde les termes verrouillés afin d’éviter une mutation ambiguë.
- Les analytiques secondaires du Pricer continuent à recevoir la projection locale verrouillée. Le prix principal et le pricing en vie passent par la composition autoritaire de l’API Product ; l’extension du même appel direct à chaque écran analytique reste une étape de consolidation.

### Vérification exécutée

- Tests Product dédiés : conservation sans prix, reçu signé, altération, idempotence, isolation utilisateur, composition marché/termes, repricing daté, RFQ, booking, lifecycle initial, KID, EMT, document et protections SQL.
- Suite backend complète : `1687 passed`; deux tests échouent aussi sur le commit de départ `d638b51` et ne sont pas causés par cette branche (`test_client_affiliations.py` et `test_strike_value_split.py`). Après le durcissement final des reçus et des entrées KID/EMT, les 58 tests directement concernés ont été rejoués avec succès.
- Frontend : `95 passed` puis build Vite de production réussi.
- Toutes les bases utilisées par les tests sont temporaires ; la base réelle `backend/data/structura.db` n’a pas été ouverte ni modifiée.

## 1. Objectif et décisions retenues

Créer un objet Python `Product` qui constitue l’entrée métier commune des modules. Le Pricer, la RFQ, le Booking, le suivi de vie, le Risk et les documents utilisent sa définition du produit. Chaque module apporte ses informations par une opération explicite, conserve les informations des autres modules et restitue un dossier cohérent.

Le parcours demandé est : exploration temporaire → conservation volontaire → RFQ et retours au Pricer → booking → vie du produit et risque. Les allers-retours sont possibles. Le deal apparaît seulement au booking.

### 1.1 Exigences issues des échanges

- Ouvrir Nouveau Pricing et calculer ne crée aucun produit durable, indicatif, RFQ ou deal.
- Le bouton « Conserver le produit » crée l’identité durable. Aucun enregistrement métier automatique avant cette action.
- La bibliothèque des produits reste distincte de Mes Scripts : un script est une source ou un modèle réutilisable ; un produit est un dossier concret.
- Tous les modules prennent `Product` comme entrée pour les informations produit. Les hypothèses de marché et paramètres de calcul sont fournis séparément.
- Le produit conserve les termes contractuels, les faits métier acquis et les références des résultats. Il ne contient pas de bloc de marché courant.
- Avant booking, le bloc exécution est absent. Le préremplissage du formulaire Deal est une intention de transaction, jamais une exécution fictive.
- Les modules enrichissent le dossier sans réécrire silencieusement les termes ou les informations des autres modules.
- L’identité du dossier est stable. Chaque état conservé reste reproductible et les changements matériels sont versionnés.
- Le produit est consultable et utilisable par API après conservation.
- La structure de l’objet peut recevoir de nouveaux attributs, avec une évolution explicite du format et une lecture compatible des anciennes versions.

La non-conservation de l’exploration concerne les dossiers métier et les résultats durables. Les caches techniques de données de marché et les journaux techniques existants ne deviennent pas des produits enregistrés.

### 1.2 Choix de conception proposés

| Sujet | Choix pour cette implémentation |
|---|---|
| Modèle Python | `Product` composé de sous-objets Pydantic v2 figés ; collections immuables, pas de dictionnaire métier modifiable exposé |
| Identité | Identifiant de dossier attribué à la conservation ; identifiant technique entier compatible avec l’audit existant et référence lisible unique |
| Exploration | Même modèle métier construit en mémoire, sans identifiant persistant et sans enregistrement |
| Marché | Contexte externe, transmis au module de calcul ; aucune vol, courbe ou configuration numérique dans les termes de `Product` |
| Résultats | Références et résumés dans le produit ; entrées effectives, résultats détaillés et preuves dans des enregistrements de calcul séparés |
| Stockage | Tables dédiées aux produits, versions des termes et révisions ; réutilisation des tables métier existantes |
| Granularité V1 | Un dossier de négociation et d’exécution, plusieurs versions et plusieurs RFQ possibles, au plus un deal booké par dossier |
| Plusieurs investissements | Dossiers distincts liés par leur origine ; pas de moteur général d’allocations ou de positions multiples dans ce chantier |
| Autorité | Serveur ; le navigateur envoie des intentions et des versions attendues, pas un remplacement du dossier complet |
| Migration | Un domaine à la fois, avec un adaptateur transitoire explicite et une suppression vérifiable de ses reconstructions locales |

La limite d’un deal par dossier est une recommandation de périmètre, pas une affirmation que deux transactions ne peuvent pas porter sur le même instrument. Le modèle permet une extension ultérieure sans modifier les termes historiques. Une même définition peut être copiée dans un nouveau dossier avec un lien d’origine.

## 2. Points d’appui et difficultés constatés dans le code

Cette lecture est ciblée sur les chemins affectés. Aucun comptage exhaustif de blobs, audit de la base réelle ou test d’exécution n’a été réalisé pour ce plan. Les références ci-dessous décrivent le dépôt lu le 14 septembre ; les noms de fichiers nouveaux proposés plus loin ne sont pas encore implémentés.

| Zone actuelle | Constat vérifié | Conséquence pour le chantier |
|---|---|---|
| [api/pricing.py](/C:/Users/admin/GitHub/structura/backend/app/api/pricing.py), `price_endpoint` | Le pricing produit une réponse et un reçu sans créer de deal ; il construit déjà un `ValuationContext` | Conserver le calcul temporaire et extraire son assemblage commun |
| [core/schemas.py](/C:/Users/admin/GitHub/structura/backend/app/core/schemas.py) | Les requêtes transportent ensemble termes, marché et options | Garder une compatibilité API, séparer ces notions derrière la frontière |
| [stores/pricing.js](/C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js) | Plusieurs chargements : script, RFQ, deal, variante ; snapshots et corps de calcul distincts | Introduire un chargement produit commun et un état de marché séparé |
| Même store, `loadFromRfq` | Monitoring remis à `weekly`, courbe de taux désactivée | Remplacer ces reconstructions par le chargement d’un contexte de calcul explicite |
| [stores/rfq.js](/C:/Users/admin/GitHub/structura/frontend/src/stores/rfq.js), `computeModelPrice` | Le navigateur reconstruit la requête, appelle `/api/price`, puis transmet un prix scalaire à la RFQ | Faire calculer et rattacher le résultat par une opération serveur |
| [db/models.py](/C:/Users/admin/GitHub/structura/backend/app/db/models.py), `Indicative` | Un objet avant transaction existe, avec snapshots, mais ne couvre pas tout le dossier et mélange marché et termes | Réutiliser ses liens commerciaux et documentaires ; ne pas renommer simplement Indicative en Product |
| Même fichier, `ValuationRun` | `deal_id` obligatoire, contexte et preuves de calcul conservés | Créer un support de calcul avant booking, sans faux deal |
| [core/valuation_context.py](/C:/Users/admin/GitHub/structura/backend/app/core/valuation_context.py) | JSON canonique, reçu de pricing et adaptateur moteur déjà présents | Réutiliser le contexte et les conversions pour relier chaque résultat à son produit |
| [core/inlife_valuation.py](/C:/Users/admin/GitHub/structura/backend/app/core/inlife_valuation.py) | `InLifeProduct` est indépendant de la base, mais porte un dictionnaire `market` contenant aussi des termes | Séparer produit, état passé et contexte externe, conserver le moteur résiduel |
| [core/deal_valuation.py](/C:/Users/admin/GitHub/structura/backend/app/core/deal_valuation.py), `mtm_core` | Entrée Deal + Session ; sélection de données, état de vie et calcul sont encore imbriqués | Extraire progressivement l’orchestration puis le service de valorisation sur Product |
| [core/var_engine.py](/C:/Users/admin/GitHub/structura/backend/app/core/var_engine.py), `build_deal_scenario_base` | Obtient un contexte MtM puis relit `market_snapshot_json` et d’autres colonnes du deal | Une seule préparation des entrées produit et calcul ; aucun second décodage dans la VaR |
| [api/deals.py](/C:/Users/admin/GitHub/structura/backend/app/api/deals.py) | Booking, échéancier figé, fixings, amendements et audit existent déjà | Les adapter au produit en conservant leurs garanties, sans créer un second workflow parallèle |
| [api/rfq.py](/C:/Users/admin/GitHub/structura/backend/app/api/rfq.py), `_create_rfq`, et `_book_deal` dans deals | Ces fonctions effectuent leur propre commit | Extraire des services sans commit autonome avant de les composer avec l’enregistrement du produit |
| [core/audit.py](/C:/Users/admin/GitHub/structura/backend/app/core/audit.py) | Audit accepté dans la transaction métier ; refus avec commit explicite | Réutiliser le mécanisme et éviter qu’un audit de refus ne valide une mutation partielle |
| [PricerView.vue](/C:/Users/admin/GitHub/structura/frontend/src/views/PricerView.vue) et [Pricer.vue](/C:/Users/admin/GitHub/structura/frontend/src/views/Pricer.vue) | Le premier charge/réinitialise le script ; le second traite notamment `fromRfq` au montage | Unifier la décision de chargement pour éviter reset et restauration concurrents |

Références métier consultées : [CLAUDE.md](/C:/Users/admin/GitHub/structura/CLAUDE.md), [cycle de vie](/C:/Users/admin/GitHub/structura/docs/projects/lifecycle/DEAL_LIFECYCLE_2026-07.md), [valuation explain](/C:/Users/admin/GitHub/structura/docs/projects/lifecycle/EXPLICATION_VALO_DESIGN.md), [gouvernance des amendements](/C:/Users/admin/GitHub/structura/docs/reference/GOUVERNANCE_AMENDEMENTS.md), [constatations sur période](/C:/Users/admin/GitHub/structura/docs/projects/pricing/CONSTATATIONS_PERIODE_DESIGN.md), [paramètres par observation](/C:/Users/admin/GitHub/structura/docs/projects/pricing/PAYSCRIPT_PARAM_PAR_OBSERVATION.md). Les statuts historiques de ces documents ne remplacent pas la lecture du code courant.

## 3. Contrat de l’objet Python

### 3.1 Contenu de Product

| Bloc | Contenu et règles |
|---|---|
| Identité | `product_id`, référence, nom, origine éventuelle, propriétaire/périmètre d’accès ; aucun identifiant de deal nécessaire à la création |
| Version | Version du schéma, révision du dossier, version des termes sélectionnée ; leur rôle est distinct |
| Termes | Script exact, paramètres contractuels effectifs, sous-jacents ordonnés, dates, devise de règlement, conventions, calendrier, qualification contractuelle disponible |
| Description métier | Coupon(s), mécanismes de barrières, fenêtres, mémoire, déclencheurs et limites de description ; calcul commun fondé sur le script et les termes |
| Contexte commercial | Client, mandat, opportunité et références documentaires lorsqu’ils existent ; pas d’obligation de client pour conserver une idée |
| Intention de transaction | Nominal envisagé, sens de notre opération, émetteur/contrepartie envisagés lorsqu’ils sont connus ; versionnée séparément des caractéristiques intrinsèques du payoff |
| RFQ | Références des tours, version des termes sollicitée, réponses, sélection et historique pertinent ; liste vide à la création |
| Exécution | `deal_id`, conditions exécutées, prix traité, date de transaction, portefeuille, politique de fixing et version contractuelle engagée ; absent avant booking |
| Cycle de vie | Faits validés, références des versions de fixing, événements et flux ; les observations indicatives restent identifiées séparément |
| Calculs et documents | Résumés et références immuables avec leur périmètre ; pas de courbes, historiques de cours ou paramètres de modèle embarqués |

Les sous-jacents contractuels ont des identifiants stables et un ordre explicite. Le mapping vers un fournisseur est une donnée de résolution externe dont la version est tracée avec le calcul. Un changement d’actif contractuel n’est pas assimilé à un simple changement d’alias fournisseur.

Le nominal et le sens de position sont disponibles depuis Product pour les modules qui en ont besoin. Leur place dans l’intention puis l’exécution évite d’imposer un nominal traité à une idée ou de créer une transaction avant booking. Si un nominal influence explicitement le payoff, cette dépendance entre aussi dans les termes et dans les entrées du moteur.

L’émetteur et le format juridique ne doivent pas être ignorés lorsqu’ils définissent réellement l’instrument. Une intention d’émetteur non confirmée peut rester commerciale ; les conditions finalement retenues sont cristallisées explicitement avant exécution et liées à la cotation correspondante.

### 3.2 Ce qui reste à l’extérieur

- Spots de valorisation, vols, dividendes prévisionnels, repo, corrélations, courbes et funding.
- Modèle, paramètres de modèle, calibration, nombre de simulations et grille numérique.
- Historiques de cours, sources externes et caches de marché.
- Objets compilés, connexions SQL, objets ORM et fonctions de calcul.
- Détails volumineux des scénarios et preuves binaires.

Un fixing validé est un fait contractuel conservé dans le cycle de vie, même si sa source initiale est un fournisseur de marché. Il ne doit pas disparaître au motif que les données de marché sont externes au produit. Un niveau initial saisi pour une étude de secondaire doit être qualifié comme référence déclarée ou hypothèse, sans devenir automatiquement un fixing officiel.

### 3.3 Propriétés et limites de l’objet

- Objet de données métier et accesseurs communs ; aucune méthode ne consulte implicitement la base ou Yahoo.
- Immuabilité profonde : un sous-objet, une collection ou un cache ne doit pas permettre de modifier des termes déjà reçus.
- Les services reçoivent Product et des entrées complémentaires explicites ; un moteur bas niveau peut recevoir une projection pure préparée par le service commun.
- La compilation est mise en cache hors du modèle sérialisé. La clé dépend du script, des paramètres, du calendrier et de la version du compilateur selon l’artefact concerné ; l’identifiant produit seul ne suffit pas.
- Les lectures d’historique lourd sont paginées par le service de chargement. Une partie non chargée est distinguée d’une partie vide. Un module ne peut pas interpréter « non chargé » comme « aucun fixing ».
- Toute extension d’attribut décrit son propriétaire, son unité, son statut de conservation, ses dépendances et sa compatibilité de schéma. Aucun sac libre `extensions` pour contourner cette obligation.

### 3.4 Sémantique commune du payoff

Réutiliser `CompiledScript.monitors`, les paramètres déclarés et Echeancier. Centraliser une description par mécanisme : rôle, observable, comparateur, seuil ou série, observations applicables et effet contractuel. Pour les coupons : base, fréquence, condition, mémoire et série éventuelle.

La description doit suivre les règles actuelles des PARAM par observation, y compris prolongation de la dernière valeur et indexation à maturité. Ne pas inventer une seconde résolution des tableaux.

Prévoir explicitement : caractéristique connue, absente, non applicable, ou non déterminable. Une description incomplète bloque les actions qui en dépendent, sans nécessairement interdire un pricing dont le moteur sait traiter le script. Aucun module ne déduit seul un rôle de barrière à partir du nom `M_*`.

Séparer observation contractuelle et monitoring numérique : quotidien/continu contractuel et approximation de simulation sont deux informations différentes. La première appartient aux termes ; la seconde au calcul.

### 3.5 Calendrier et maturité

Conserver les conventions et, dès que résoluble, une photographie de l’échéancier avec provenance du résolveur. Un brouillon incomplet peut être conservé avec ses manques identifiés.

Lors du gel pour sollicitation, fixer le calendrier résolu applicable. Le booking conserve exactement la référence retenue. Une mise à jour de bibliothèque de jours fériés ne réécrit pas cet échéancier. Si un recalcul en structuration change les dates, présenter le changement et enregistrer une nouvelle version explicite.

Respecter les axes existants : origine au strike, valeur pour l’expression du prix, maturité pour la dernière constatation et paiement pour l’actualisation. Le ténor contractuel et le temps résiduel à une date donnée sont distincts.

## 4. Marché séparé et conservation des calculs

### 4.1 Trois entrées explicites au service de calcul

1. Le Product et sa version contractuelle.
2. L’état de vie applicable à la valorisation, incluant les faits passés et leur qualification.
3. Un contexte externe : date de valorisation, données/hypothèses effectives, modèle et configuration numérique.

Le service assemble ensuite le `ValuationContext` existant. Il n’appelle pas une propriété `product.market` et ne réintroduit pas les paramètres contractuels dans un snapshot de marché faisant autorité.

La résolution externe utilise d’abord les données déjà disponibles selon la politique demandée. Le rafraîchissement, la restauration d’un ancien contexte et une surcharge manuelle sont trois actions identifiables. Ouvrir Product n’effectue aucun rafraîchissement implicite.

### 4.2 Reprendre un ancien prix

Chaque calcul conservé porte : produit/version/révision d’entrée, date de valorisation, heure de calcul, entrées moteur réellement utilisées, état passé, version du moteur, résultat, diagnostic et provenance matérielle des données.

La date de marché seule est insuffisante pour un rejeu exact : une source peut corriger son historique, et le calcul peut employer une surcharge ou une configuration particulière. Le chargeur actuel de marché comporte notamment un cache à durée limitée ; il ne constitue pas à lui seul un référentiel immuable de tous les contextes historiques.

La V1 conserve donc les entrées effectives dans l’enregistrement de calcul, à l’extérieur de Product. Un stockage par référence à un jeu de marché immuable pourra ensuite éviter les duplications. Il devra offrir la même garantie.

Deux opérations distinctes sont exposées : « Rejouer ce calcul », sans accès fournisseur, et « Revaloriser », avec un nouveau contexte. Les résultats restent rattachés au même produit si les termes sont inchangés.

### 4.3 Conserver un calcul réalisé avant la création du produit

Le résultat d’exploration reste en mémoire jusqu’à « Conserver ». Pour ne pas traiter un résultat modifié par le navigateur comme une preuve serveur, faire évoluer le reçu de pricing : inclure les entrées effectives, le résultat, la version moteur et l’horodatage dans un reçu authentifié par le serveur. Le reçu peut être vérifié sans créer de ligne durable pendant l’exploration.

Une empreinte de données, recalculable par le client, assure une comparaison mais ne prouve pas l’origine serveur du prix. Le reçu actuel ne suffit pas à cette nouvelle garantie. Le mécanisme retenu devra être testé pour altération du prix comme des entrées ; une signature serveur avec gestion/version de clé convient à cette exigence.

Si aucun reçu vérifiable n’est disponible, conserver les termes reste possible ; le résultat importé est qualifié comme tel, ou un nouveau calcul serveur est demandé explicitement avant de l’utiliser dans un contrôle métier. Ne pas recalculer silencieusement un autre prix lors de la sauvegarde.

### 4.4 Après conservation

Un calcul explicitement lancé sur un dossier conservé est enregistré avec ses entrées et rattaché à ce dossier ; ses sous-calculs techniques ne créent pas chacun une révision produit. Une exploration détachée reste disponible via « Essayer une copie temporaire ».

Une réponse reçue après modification du dossier conserve sa version d’entrée. Elle ne devient pas automatiquement le résultat courant du nouvel état. La restitution identifie le prix applicable et son contexte au lieu d’utiliser le dernier résultat par ordre d’arrivée.

## 5. Persistance et source faisant autorité

### 5.1 Tables nouvelles proposées

| Table | Responsabilité |
|---|---|
| `products` | Identité stable, référence, propriétaire/entité, origine, archivage et pointeur de révision courante |
| `product_terms_versions` | Termes canoniques immuables, version, parent, empreinte, schéma, calendrier résolu et motif de changement |
| `product_revisions` | Révision immuable du dossier, parent, version de termes affichée, état des blocs et références exactes des sources, acteur/action/date |
| `product_calculation_runs` | Registre des résultats liés au produit : entrées/résultat avant booking ; après booking, lien explicite vers ValuationRun ou les résultats spécialisés existants |
| `product_commands` | Déduplication des commandes durables : périmètre utilisateur/produit/action, clé d’idempotence, empreinte de demande et références de réponse |

Une même clé d’idempotence avec un autre contenu est refusée. Une réémission de la même commande rend l’opération déjà obtenue. Cette garantie s’applique aussi à « Conserver » avant qu’un product_id existe.

Les révisions stockent un manifeste cohérent et de petites photographies des blocs dont les tables sources sont encore mutables, notamment les réponses RFQ. Une référence vers la ligne RFQ courante ne suffit pas à restituer ce qui a été vu dans une ancienne révision.

Les termes ne sont pas recopiés intégralement dans chaque révision : celle-ci référence une version immuable. Les preuves volumineuses et historiques de marché restent externes. Pas de chargement de tout l’historique à chaque consultation.

### 5.2 Tables existantes conservées

- `rfq_requests` et `rfq_quotes` gardent leurs fonctions opérationnelles et leurs contraintes ; ajout de références produit/version de termes à la RFQ.
- `deals` garde sa fonction d’exécution et de ligne de portefeuille, son identifiant et ses références existantes ; ajout de product_id et de la version exécutée.
- `indicatives`, `KidRecord`, `EmtRecord` et documents reçoivent des liens produit/version sans destruction de leurs rattachements historiques.
- `OfficialFixingVersion`, `DealEvent`, `LifecycleProposal`, `TradeAmendmentRequest`, `DealContractVersion`, `ValuationRun`, `ShockRun`, `ComputeBatch` et `ComputeJob` restent en place.
- `AuditEvent` est réutilisé avec l’identifiant produit, la révision d’entrée/sortie et l’identifiant de commande dans les métadonnées pertinentes.

`ValuationRun.deal_id` ne devient pas facultatif dans le premier lot. Les calculs avant booking utilisent le nouveau registre ; les calculs sur deal continuent à bénéficier du stockage et du rejeu existants, référencés par ce registre. Une entrée du registre précise son type et son stockage cible : les données de calcul ne sont pas maintenues en double dans deux historiques indépendants.

### 5.3 Autorité des données pendant la migration

| Information | Autorité cible | Traitement des anciennes colonnes |
|---|---|---|
| Termes d’un dossier migré | `product_terms_versions` | Projection de compatibilité en lecture, écrite par l’adaptateur commun lorsque nécessaire |
| Faits RFQ | Commandes RFQ et tables RFQ | Révision produit figée dans la même transaction |
| Exécution et position | Services Booking et tables Deal/amendements | Exposées dans Product ; aucune édition alternative du bloc par le navigateur |
| Fixings et cycle de vie | Tables versionnées officielles et commandes de cycle de vie | Références exactes et état cohérent dans la révision |
| Calculs | Enregistrement de calcul immuable et son manifeste d’entrées | Les champs « dernier prix » deviennent des projections |
| Ancien dossier non migré | Stockage historique avec adaptateur identifié | Pas de bascule implicite selon les champs disponibles |

Product est l’interface de lecture commune. Cela n’impose pas de déplacer toutes les preuves et tables opérationnelles dans un seul JSON. La révision constitue la photographie cohérente consultable ; les faits métier sont enregistrés par leur propriétaire. Une seule commande met à jour ces deux représentations ensemble, puis vérifie leur cohérence.

Interdire les mutations d’un produit migré par une ancienne route ou par l’administration générique qui contourneraient l’enregistrement d’une révision. Une ancienne route reste utilisable seulement si elle délègue au service commun.

### 5.4 Chargement et transactions

Le repository charge une révision cohérente, ses termes et les blocs nécessaires. Il peut charger une ancienne révision sans lire les valeurs courantes des tables mutables. Les projections du portefeuille utilisent des requêtes groupées, sans une requête par attribut.

Pour une commande métier : vérifier les droits → charger les versions attendues → valider → produire les changements du module → écrire les faits métier, la révision et l’audit → mettre à jour le pointeur courant avec contrôle de concurrence → commit unique.

Ne pas tenir une transaction d’écriture ouverte pendant un calcul Monte Carlo ou un appel réseau. Figer les entrées, calculer hors transaction, puis rattacher le résultat en vérifiant ses dépendances. Un résultat sur un état dépassé reste consultable sans être promu comme actuel.

En cas d’échec : rollback de la mutation, puis audit du refus selon le mécanisme existant. Les helpers appelés dans l’opération composée ne committent pas de leur propre initiative.

## 6. Versions, transitions et contrôles

### 6.1 Trois versions différentes

- `schema_version` : format de sérialisation ; évolue quand la structure change.
- `terms_version` : version immuable de la définition contractuelle ; nouvelle version lorsque les termes changent.
- `revision` : photographie conservée du dossier ; évolue quand un enrichissement matériel est enregistré.

Le compteur `Deal.contract_version` existant couvre aussi des corrections opérationnelles. Le préserver et enregistrer sa correspondance avec la révision produit. Il ne doit pas être confondu avec terms_version : changer le prix traité n’équivaut pas à changer le payoff.

Deux variantes peuvent avoir le même parent. La version la plus élevée n’est pas nécessairement celle retenue. Chaque RFQ, sélection et exécution porte explicitement sa version de termes. Après booking, les consommateurs officiels utilisent la version exécutée/amendée, jamais la dernière variante explorée.

### 6.2 Transitions

| Action | Entrées/préconditions | Sortie et conservation |
|---|---|---|
| Pricing temporaire | Termes de travail + contexte externe compatibles avec le moteur | Résultat temporaire ; zéro dossier durable |
| Conserver | Nom, termes structurellement valides, identité utilisateur ; résultat facultatif | Produit, termes v1, révision initiale et audit ; exécution absente |
| Enregistrer des termes modifiés | Révision attendue ; distinction brouillon/version déjà sollicitée | Nouvelle version si modification contractuelle ; anciennes cotations liées à l’ancienne version |
| Créer/solliciter une RFQ | Produit conservé, version choisie, intention commerciale et disponibilité RFQ | Nouveau tour rattaché ; gel des éléments sollicités selon les règles existantes |
| Retour RFQ → Pricer | Identifiant produit + RFQ + version concernée | Ouverture du même dossier ; restauration de marché seulement depuis un calcul/contexte explicitement choisi |
| Retenir/revoir une quote | Quote appartenant à la RFQ, contrôles actuels de statut/validité | Sélection auditée ; historique du tour conservé |
| Booker | Version et sélection exactes, conditions exécutées, contrôles métier et idempotence | Deal, calendrier, événements initiaux, provenance, révision et audit atomiques |
| Revaloriser un deal | Version exécutée, état passé et contexte externe | Nouveau résultat lié ; contrat inchangé |
| Corriger un fixing | Politique de validation, version attendue et preuve | Nouvelle version officielle ; état dépendant et résultats concernés identifiés |
| Amender après booking | Workflow gouverné existant et champ autorisé | Nouvelle version opérationnelle ; nouvelle version de termes si nécessaire, par exemple calendrier de paiement |
| Roll | Produit source et définition de la nouvelle opération | Nouveau product_id avec origine ; aucune exécution ni RFQ active héritée |

« Conserver » accepte un brouillon avec des données métier manquantes identifiées. Les règles de disponibilité sont propres à l’action : conserver, pricer, solliciter, booker, rejouer officiellement. Elles rendent des codes et explications ; aucune valeur par défaut cachée n’est utilisée pour franchir une étape.

Conserver la politique métier actuelle de booking : ne pas introduire une nouvelle obligation d’étiquette de fermeté, de client ou de double signature au titre de cette refonte. La validité de quote, la cohérence de contrepartie, les liens de sélection et les politiques d’amendement restent applicables.

Les changements de payoff d’un deal booké ne deviennent pas autorisés par la seule existence d’un versionnement Product. Les limites des amendements existants sont préservées ; une annulation/remplacement étendue reste un chantier distinct.

### 6.3 Empreintes et dépendances

Centraliser la normalisation des unités, nombres, dates, valeurs absentes et ordres significatifs. Conserver plusieurs périmètres : termes, entrées effectives du calcul, entrées du rejeu officiel, et conditions RFQ/exécution. Un hash ne remplace ni un droit, ni un contrôle de validité, ni une preuve d’origine.

Ne pas remplacer `official_input_hash` par la seule empreinte des termes. Préserver ses dépendances aux versions de fixings et à la validation ; documenter aussi toute entrée de rejeu aujourd’hui lue dans le marché historique. Un paramètre de payoff qui dépend d’un taux observé exige une qualification contractuelle explicite, pas sa suppression arbitraire.

| Changement | Effet sur les résultats |
|---|---|
| Coupon/barrière/calendrier contractuel | Nouvelle version ; les résultats précédents restent ceux de leur version |
| Vol/courbe/modèle/N | Même Product et mêmes termes ; nouveau calcul et empreinte d’entrées |
| Quote/prix de banque | Révision RFQ ; contrôle de sélection ; aucune modification automatique du prix modèle |
| Fixing validé corrigé | Nouvelle version officielle ; rejeux, états et résultats dépendants à réévaluer |
| Nominal/prix traité/affectation | Historique de transaction ; recalcul des montants, positions ou agrégations concernés selon leurs dépendances |
| Libellé purement descriptif | Révision descriptive ; aucune invalidation numérique sans dépendance réelle |

## 7. Plan des fichiers à créer ou modifier

Les chemins proposés ci-dessous sont relatifs à la racine du dépôt pour décrire l’implantation future. Ils ne constituent pas du code livré.

### 7.1 Noyau et infrastructure nouveaux

| Fichier proposé | Travail à réaliser |
|---|---|
| `backend/app/core/product/models.py` | Product, Terms, blocs, références et état de chargement ; immuabilité et unités |
| `backend/app/core/product/serialization.py` | JSON canonique, schéma, montées de version ; refus explicite des versions futures inconnues |
| `backend/app/core/product/semantics.py` | Description commune coupon/barrières/observations à partir du parser et des termes |
| `backend/app/core/product/policies.py` | Disponibilité par action, dépendances et décisions d’invalidation |
| `backend/app/core/product/fingerprints.py` | Périmètres de hash documentés et règles de normalisation |
| `backend/app/core/product/valuation.py` | Assemblage produit + état + contexte externe vers les entrées moteur communes |
| `backend/app/services/product_repository.py` | Lecture cohérente, conservation, versions, révisions et chargement groupé |
| `backend/app/services/product_legacy.py` | Adaptateurs depuis Deal, Indicative, RFQ et Script ; rapports d’écarts et projections de compatibilité |
| `backend/app/services/product_commands.py` | Conserver, réviser, dupliquer, rattacher un résultat ; transactions et idempotence |
| `backend/app/services/product_pricing.py` | Orchestration de calcul identifié, preuve serveur, conservation des résultats |
| `backend/app/services/rfq_workflow.py` | Extraction progressive des mutations RFQ composables, sans commit autonome |
| `backend/app/services/booking_workflow.py` | Extraction du booking composable, contrôles existants et sortie produit |
| `backend/app/api/products.py` | Routes produit avec authentification, contrôle de portée, commandes et pagination |
| `backend/app/core/product/api_models.py` | Requêtes/réponses produit typées, erreurs de versions et commandes autorisées |

Le noyau `core/product` n’importe ni `api` ni `db`. Les adaptateurs ORM vivent dans les services. Aucun appel HTTP interne d’un module à un autre pour une fonction Python déjà disponible. Les moteurs PayScript sont conservés et appelés via la préparation commune.

### 7.2 Modifications backend existantes

| Fichiers/zone | Modification ciblée |
|---|---|
| [db/models.py](/C:/Users/admin/GitHub/structura/backend/app/db/models.py), [db/database.py](/C:/Users/admin/GitHub/structura/backend/app/db/database.py) | Tables, clés étrangères, unicités, index et migrations additives compatibles avec `_migrate` |
| [main.py](/C:/Users/admin/GitHub/structura/backend/app/main.py) | Enregistrer le routeur products ; conserver les routes historiques pendant la transition |
| [api/pricing.py](/C:/Users/admin/GitHub/structura/backend/app/api/pricing.py), [api/inlife.py](/C:/Users/admin/GitHub/structura/backend/app/api/inlife.py) | Adaptation des requêtes temporaires vers Product + contexte ; chemin commun pour produit conservé et exploration |
| [core/valuation_context.py](/C:/Users/admin/GitHub/structura/backend/app/core/valuation_context.py) | Préserver les entrées effectives, versions et conversions ; reçu exploitable avant booking |
| [api/rfq.py](/C:/Users/admin/GitHub/structura/backend/app/api/rfq.py), [core/rfq_controls.py](/C:/Users/admin/GitHub/structura/backend/app/core/rfq_controls.py) | Lien produit/version ; remplacer décodages des termes ; calcul serveur du prix modèle ; préserver sélection/last look |
| [api/deals.py](/C:/Users/admin/GitHub/structura/backend/app/api/deals.py) | `_book_deal`, `_deal_product_terms`, `_validate_rfq_booking_identity`, `_figer_echeancier` et `_apply_pricing_receipt` délèguent au chemin commun |
| [core/inlife_valuation.py](/C:/Users/admin/GitHub/structura/backend/app/core/inlife_valuation.py) | Adapter puis retirer InLifeProduct ; conserver le rejeu, la mémoire et la logique de vie restante |
| [core/deal_valuation.py](/C:/Users/admin/GitHub/structura/backend/app/core/deal_valuation.py) | Extraire le calcul depuis `mtm_core` ; chargement DB/marché assuré avant l’entrée dans le service de calcul |
| [core/valuation_runs.py](/C:/Users/admin/GitHub/structura/backend/app/core/valuation_runs.py) | Référencer Product et ses dépendances ; préserver le rejeu hors ligne et les données des runs existants |
| [api/deals.py](/C:/Users/admin/GitHub/structura/backend/app/api/deals.py), [core/lifecycle_controls.py](/C:/Users/admin/GitHub/structura/backend/app/core/lifecycle_controls.py) | Mutations de fixing, validation/application des propositions et amendements enregistrent une révision dans la même transaction |
| [services/lifecycle_alerts.py](/C:/Users/admin/GitHub/structura/backend/app/services/lifecycle_alerts.py) | Automatisation quotidienne via les mêmes commandes ; acteur système et idempotence conservés |
| [core/var_engine.py](/C:/Users/admin/GitHub/structura/backend/app/core/var_engine.py), [api/var.py](/C:/Users/admin/GitHub/structura/backend/app/api/var.py), [api/shocks.py](/C:/Users/admin/GitHub/structura/backend/app/api/shocks.py) | Entrées Product ; préparation commune ; manifeste du portefeuille et des versions ; aucun décodage local du deal |
| [core/compute/pricers/var_scenario.py](/C:/Users/admin/GitHub/structura/backend/app/core/compute/pricers/var_scenario.py) | Charge utile pure JSON produite par le préparateur commun ; compilation locale au worker |
| [api/indicatives.py](/C:/Users/admin/GitHub/structura/backend/app/api/indicatives.py), [api/kid.py](/C:/Users/admin/GitHub/structura/backend/app/api/kid.py), [api/emt.py](/C:/Users/admin/GitHub/structura/backend/app/api/emt.py) | Rattachement produit avant deal ; informations spécifiques aux documents explicites, aucun indicatif factice exigé |
| [core/client_intelligence.py](/C:/Users/admin/GitHub/structura/backend/app/core/client_intelligence.py), [core/client_technical.py](/C:/Users/admin/GitHub/structura/backend/app/core/client_technical.py), [core/deal_valuation_pdf.py](/C:/Users/admin/GitHub/structura/backend/app/core/deal_valuation_pdf.py) | Consommer les caractéristiques et résultats communs ; même résultat à l’écran et dans la note |
| [core/variants.py](/C:/Users/admin/GitHub/structura/backend/app/core/variants.py), [api/variants.py](/C:/Users/admin/GitHub/structura/backend/app/api/variants.py) | Réutiliser deltas et filiation ; préserver le passé pour les simulations d’avenant et créer un nouveau dossier pour un roll conservé |
| [core/admin_registry.py](/C:/Users/admin/GitHub/structura/backend/app/core/admin_registry.py) | Exposer les références utiles en consultation ; aucune édition brute des snapshots/versionnements |

## 8. API et parcours frontend

### 8.1 Routes proposées

Ces routes décrivent le contrat de la cible. Leur livraison suit les lots ; elles ne sont pas présentes aujourd’hui.

| Route | Intention |
|---|---|
| POST `/api/products` | Conserver les termes de travail, le contexte commercial facultatif et un reçu de calcul facultatif |
| GET `/api/products` | Bibliothèque paginée : référence, nom, date, versions et liens métier |
| GET `/api/products/{id}` | Charger le dossier, éventuellement à une révision/version explicite et avec des blocs demandés |
| GET `/api/products/{id}/history` | Chronologie paginée des actions, versions et résultats |
| POST `/api/products/{id}/terms-versions` | Enregistrer une évolution contractuelle autorisée avec parent et motif |
| POST `/api/products/{id}/calculations` | Calculer sur la version explicitement choisie avec un contexte externe et rattacher le résultat |
| GET `/api/products/{id}/calculations/{run_id}` | Lire les preuves/résultats externes au produit après contrôle d’appartenance |
| POST `/api/products/{id}/calculations/{run_id}/replay` | Rejouer les entrées conservées sans fournisseur ; tracer l’environnement de rejeu |
| POST `/api/products/{id}/rfqs` | Créer un tour RFQ sur une version et une intention précises |
| POST `/api/products/{id}/book` | Booker une version et une sélection précises ou un booking direct autorisé |
| POST `/api/products/{id}/copies` | Conserver un nouveau dossier avec origine et sans exécution héritée |
| POST `/api/products/{id}/archive` | Archiver le dossier dans la bibliothèque ; ne termine pas un deal actif |

Les commandes matérielles transmettent les versions attendues et une clé d’idempotence. Les erreurs distinguent donnée invalide, droits, version dépassée, manque de données et indisponibilité d’une action. Réutiliser les conventions 404/409/422 actuelles selon le cas.

Les routes RFQ, Deal et portefeuille actuelles restent les portes des interfaces existantes mais délèguent aux mêmes services. Aucune route « PUT Product complet » permettant au navigateur d’écraser les cotations ou fixings.

Le calcul temporaire `/api/price` et les analyses conservent leur usage existant. Ils normalisent en Product temporaire et contexte externe côté serveur. Toute nouvelle API exige les mêmes contrôles d’utilisateur/entité que les dossiers qu’elle expose ; connaître product_id n’accorde aucun droit.

### 8.2 État du Pricer

Créer `frontend/src/stores/products.js` pour l’identité, la révision chargée, les blocs et les commandes produit. Conserver dans `pricing.js` le formulaire de travail, le contexte de marché et les résultats temporaires. Créer un adaptateur unique `frontend/src/utils/productPricing.js` pour les projections et unités ; il ne définit aucun calendrier ni rôle de barrière.

Le Pricer distingue : nouveau travail temporaire ; produit conservé sans modification locale ; copie de travail modifiée ; contrat booké en revalorisation ; copie temporaire détachée. Modifier le formulaire ne modifie jamais immédiatement la version enregistrée.

« Conserver le produit » crée le dossier. Ensuite « Enregistrer les modifications » conserve les évolutions explicites. Après booking, les termes sont verrouillés dans ce parcours et renvoient vers l’amendement pour les champs autorisés. Les prix de simulation restent distincts du prix traité.

Pour lancer une RFQ depuis un travail temporaire, proposer l’action explicite « Conserver et ouvrir une RFQ ». Les préconditions sont vérifiées avant l’opération composée ; la conservation et la création réussissent ensemble. Pas de popup de confirmation supplémentaire lorsque le libellé exprime déjà l’action. « Conserver et booker » peut couvrir le booking direct lorsque ses conditions sont réunies.

### 8.3 Fichiers frontend

| Zone | Travail |
|---|---|
| `frontend/src/views/ProductsView.vue` — nouveau | Bibliothèque compacte, recherche, version, état du dossier et ouverture dans le module concerné |
| `frontend/src/components/ProductContextBar.vue` — nouveau | Référence produit, version, modifications locales, liens RFQ/deal, accès historique |
| [PricerView.vue](/C:/Users/admin/GitHub/structura/frontend/src/views/PricerView.vue), [Pricer.vue](/C:/Users/admin/GitHub/structura/frontend/src/views/Pricer.vue) | Un seul orchestrateur d’ouverture ; priorité de route explicite ; chargement produit atomique |
| [router/index.js](/C:/Users/admin/GitHub/structura/frontend/src/router/index.js), [AppHeader.vue](/C:/Users/admin/GitHub/structura/frontend/src/components/AppHeader.vue) | Bibliothèque et routes dédiées, par exemple `/products/{id}/pricer`, sans collision avec `/pricer/:id` réservé aux scripts |
| [stores/pricing.js](/C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js) | `loadFromProduct` ; délégation transitoire de loadFromRfq/loadFromDeal ; marché chargé séparément par contexte de calcul |
| [RfqView.vue](/C:/Users/admin/GitHub/structura/frontend/src/views/RfqView.vue), [stores/rfq.js](/C:/Users/admin/GitHub/structura/frontend/src/stores/rfq.js) | Transporter identifiants/version, utiliser les termes communs et le pricing serveur ; supprimer les conversions de calendrier recopiées |
| [DealTab.vue](/C:/Users/admin/GitHub/structura/frontend/src/components/DealTab.vue) | Saisir l’intention/exécution, puis commander le booking du produit ; ne plus renvoyer une autre copie des termes |
| [BookingView.vue](/C:/Users/admin/GitHub/structura/frontend/src/views/BookingView.vue), [EventsTab.vue](/C:/Users/admin/GitHub/structura/frontend/src/components/EventsTab.vue) | Afficher identité produit/version bookée, historique et commandes du cycle de vie |
| [RiskManagementView.vue](/C:/Users/admin/GitHub/structura/frontend/src/views/RiskManagementView.vue), [stores/portfolios.js](/C:/Users/admin/GitHub/structura/frontend/src/stores/portfolios.js) | Afficher les versions effectivement utilisées et les résultats dépassés/exclusions |
| [ScriptsView.vue](/C:/Users/admin/GitHub/structura/frontend/src/views/ScriptsView.vue) | Préserver Mes Scripts ; ouvrir une source comme travail temporaire, sans créer Product automatiquement |

En navigation Pricer → RFQ → Pricer, conserver la copie de travail et son contexte en mémoire tant que la session existe ; après fermeture, charger la dernière révision enregistrée et le contexte d’un calcul choisi. Ne pas inventer une conservation durable des modifications non enregistrées. Au changement d’identifiant, ignorer les anciennes réponses réseau afin qu’elles n’écrasent pas le nouveau dossier.

Le frontend reste en JavaScript. Publier le schéma API pour vérifier les projections et, si utile, produire des déclarations de types ; ne pas faire d’une migration TypeScript un prérequis.

## 9. Ordre de livraison

Chaque lot a une sortie métier observable et un critère de retrait des chemins historiques. Aucun lot ne se termine uniquement parce qu’une nouvelle classe existe.

### Lot 0 — Contrats et cas de référence

- Figer les choix de ce plan dans un dictionnaire des champs, unités, propriétaires et dépendances.
- Définir les projections requises par les consommateurs existants, y compris dates, preuve de pricing, sens, calendrier figé, variantes et fixing policy.
- Constituer des fixtures synthétiques et des références issues des tests existants. Une éventuelle comparaison sur données réelles reste en lecture seule.
- Documenter les champs des anciens snapshots qui sont en réalité contractuels : `user_params`, `constats`, dates, identité des sous-jacents.

Sortie : matrice champ/source/consommateur et jeux de référence couvrant plusieurs payoffs. Les choix de stockage et de transaction sont arrêtés avant toute écriture Product.

### Lot 1 — Product en lecture et préparation commune

- Créer le noyau, sérialisation, sémantique, empreintes et adaptateurs historiques.
- Transformer les entrées du Pricer en Product temporaire + contexte séparé, sans persistance.
- Introduire la frontière commune de préparation ; conserver les moteurs et un adaptateur InLifeProduct transitoire.
- Comparer les descriptions et entrées effectives avec les fixtures ; rendre les divergences explicites.

Sortie : un même dossier est décrit de façon stable depuis ses formats existants. Aucun workflow durable ne dépend encore de la nouvelle persistance.

### Lot 2 — Conservation volontaire et bibliothèque

- Ajouter tables, contraintes, repository, historique, idempotence et API produits.
- Ajouter les calculs avant booking et le reçu serveur vérifiable, rattaché aux termes effectivement pricés.
- Livrer le bouton Conserver, la bibliothèque et le rechargement du produit.
- Séparer formulaire de termes et contexte de marché ; conserver la possibilité d’essai temporaire.

Sortie : explorer puis fermer ne crée aucun dossier ; conserver puis redémarrer permet de retrouver exactement le produit et son résultat choisi. `deal_id` demeure absent.

### Lot 3 — RFQ et allers-retours complets

- Extraire les mutations RFQ composables et les lier au produit/version.
- Remplacer computeModelPrice du navigateur par un calcul serveur rattaché.
- Livrer conservation + création RFQ explicites, retours au Pricer, variantes et nouveaux tours.
- Enregistrer révisions/audit à chaque changement matériel ; ne pas supprimer l’historique d’une quote supprimée de la vue courante.

Sortie : Pricer → RFQ → Pricer conserve produit, calendrier, paramètres et contexte de calcul choisi ; un changement contractuel conserve la RFQ précédente sur sa version. Les fonctions de chargement RFQ historiques délèguent, sans reconstitution autonome.

### Lot 4 — Booking et portefeuille

- Extraire `_book_deal` en service sans commit autonome ; conserver les règles existantes.
- Créer deal, événements, calendrier, provenance et révision produit dans une transaction.
- Faire du deal la représentation d’exécution du dossier et préserver toutes les références externes.
- Adapter booking direct et liens d’indicatifs ; afficher le produit booké dans le portefeuille.
- Brancher les amendements existants sur la révision produit.

Sortie : même product_id avant/après booking, exécution créée une fois, prix modèle et prix traité distincts, contrat exécuté figé. Aucun nouveau booking ne dépend d’un assemblage frontend de snapshots.

### Lot 5 — Cycle de vie, MtM et explain

- Faire recevoir Product et état explicite au service de valorisation résiduelle.
- Migrer fixings, propositions, validation/application et scheduler vers des commandes traçables.
- Préserver mémoire du payoff, réductions par sous-jacent, flux détachés, acquis non réglés et règles des produits résolus.
- Rattacher les ValuationRun et rapports ; distinguer rejeu du calcul d’origine et recalcul avec données corrigées.
- Retirer InLifeProduct lorsque tous ses consommateurs utilisent la projection commune.

Sortie : le Pricer en vie et le MtM utilisent la même définition et le même préparateur ; un fixing corrigé n’altère aucun ancien run ni état officiel sans transition.

### Lot 6 — Risk, documents et consommateurs secondaires

- Migrer VaR, chocs, Greeks, KID/EMT, notes, Client Intelligence et réinvestissement.
- Figer le périmètre d’un calcul portefeuille : produits, versions, positions, devises, FX et contextes utilisés.
- Préserver les exclusions VaR visibles et la distinction produit actif/créance en règlement ; ne pas changer les modèles de risque dans cette migration.
- Remplacer les extracteurs locaux de barrières/coupons par la sémantique commune.
- Étendre la même entrée aux profils, probabilités, trajectoires, MTF, backtests et variantes ; pas de réécriture de leurs algorithmes.

Sortie : chaque module métier prend Product, ou une projection produite exclusivement par le noyau, comme source du produit. Plus de second décodeur par module.

### Lot 7 — Reprise historique et retrait des compatibilités

- Produire un rapport de conversion avant toute migration de dossiers : exact, incomplet, contradictoire, non interprétable.
- Reconstituer les liens déjà prouvés par les clés RFQ/deal/indicatif ; ne jamais fusionner des dossiers parce que leur script ou leur empreinte se ressemble.
- Conserver les snapshots originaux et l’identité des deals. Les anciens calendriers absents restent signalés ; pas de calendrier rétroactivement certifié par une reconstruction actuelle.
- Convertir de façon idempotente, dossier par dossier, avec contrôle d’écarts avant bascule.
- Retirer les anciens décodeurs lorsque tous les consommateurs du domaine sont migrés. Conserver un adaptateur isolé pour les archives qui ne peuvent pas être converties fidèlement.

Sortie : un inventaire final indique les chemins supprimés, les archives encore compatibles et leurs limites. Aucun fallback silencieux d’un dossier migré vers un ancien blob.

### Déploiement et retour arrière

Les migrations de schéma sont additives. Tester sauvegarde/restauration sur une copie ou une base temporaire, sans modifier la base réelle pour la recette.

Une fois un dossier migré et modifié, son mode d’autorité ne rebascule pas automatiquement vers les anciennes colonnes. En cas de défaut, suspendre les écritures du domaine concerné ou corriger la version en place ; un rollback applicatif doit rester capable de lire les nouvelles révisions. Aucun rollback destructif de tables métier.

## 10. Validation prévue

### 10.1 Scénarios indispensables

| Scénario | Résultat attendu |
|---|---|
| Nouveau Pricing, plusieurs calculs, fermeture | Aucun produit/indicatif/RFQ/deal/run métier durable créé |
| Conserver deux fois la même commande | Un produit et une réponse idempotente |
| Conserver après avoir modifié les termes depuis le prix affiché | Termes enregistrables ; ancien prix lié à ses entrées, jamais présenté comme prix des nouveaux termes |
| Produit conservé sans client ni deal | Bibliothèque et reprise utilisables ; contrôles RFQ/Booking appliqués seulement à l’étape concernée |
| Reçu client avec prix ou paramètres altérés | Résultat refusé comme preuve serveur |
| Même calcul par Pricer et RFQ | Identité du produit, du contexte et du résultat dans le même environnement |
| Courbes/monitoring après RFQ → Pricer | Contexte sélectionné restauré sans défaut caché ; Product ne contient pas ces hypothèses |
| Cotation sur v1, variante v2, tentative de booking incohérent | Refus explicite ; l’ancienne cotation reste attachée à v1 |
| RFQ sélectionnée avec même contrat mais prix obsolète | Contrôle de prix applicable fondé sur ses entrées et la politique métier |
| Booking double ou concurrent | Un deal ; aucun événement, révision ou audit de succès orphelin |
| Échec après création du deal mais avant révision produit | Rollback complet ; audit du refus sans validation partielle |
| Modification de jours fériés/résolveur | Aucun déplacement de l’échéancier gelé |
| Fixing corrigé pendant un calcul | Ancien résultat conservé sur son état ; aucun remplacement du résultat courant sans contrôle |
| Produit en vie avec mémoire/barrière/fenêtre | Même passé, même ordre des observations et même reliquat entre consommateurs |
| Produit rappelé, échu ou en règlement | Chemin métier approprié ; pas de simulation active réintroduite par un chargement Product |
| Rejeu ancien puis recalcul corrigé | Les deux résultats sont distingués et expliqués |
| VaR avec dossier exclu ou position modifiée pendant calcul | Périmètre figé et exclusion visible ; résultat non attribué au nouveau portefeuille |
| Ancien dossier incomplet | Lecture qualifiée ; donnée absente jamais remplacée par une valeur actuelle présentée comme historique |
| Lecture d’une ancienne révision après modification RFQ | Anciennes réponses et sélection restituées, indépendamment des lignes courantes |
| Nouvel attribut et ancien JSON | Migration de schéma déterministe ; absence significative explicitée |
| Utilisateur d’une autre entité | Produit, résultats, preuves et liens métier inaccessibles selon les règles existantes |
| Écran/note de valorisation | Même run de référence ; aucune nouvelle interprétation des barrières dans le PDF |

### 10.2 Tests à créer et tests existants à réutiliser

Nouveaux fichiers proposés : `backend/tests/test_product_model.py`, `test_product_serialization.py`, `test_product_semantics.py`, `test_product_persistence.py`, `test_product_commands.py`, `test_product_pricing.py`, `test_product_rfq_booking.py`, `test_product_lifecycle.py` et `test_product_legacy.py`. Chaque lot crée uniquement les tests de ses invariants métier et d’intégration, sans tests qui recopient simplement les attributs du modèle.

Côté frontend : nouveaux tests du store products et de l’adaptateur, compléments de `frontend/src/stores/pricing.test.js` et `deals.test.js` pour navigation, réponses périmées, conservation et verrouillage.

Réutiliser, selon le lot, les tests existants de RFQ, valuation context, chaîne pricing/booking/MtM, inlife pricing, pré-strike, schedule/settlement, fixings, workflow controls/phase2, VaR, explain, PDF et variantes. Les chemins exacts sont dans le répertoire [backend/tests](/C:/Users/admin/GitHub/structura/backend/tests).

Les tests backend se lancent depuis la racine, sur les fichiers concernés. La suite backend complète reste réservée à une demande explicite de Philippe, conformément à CLAUDE.md. Toute modification Vue se termine par `npm run build` dans frontend ; le script actuel inclut Vitest puis Vite. Aucun build ni test n’est requis pour la seule livraison du présent document.

Les calculs de référence utilisent des données injectées, hors réseau. L’égalité au bit près n’est exigée que dans un environnement moteur et numérique maîtrisé ; les comparaisons entre environnements utilisent une tolérance définie, les versions et les écarts sont exposés. Un simple aller-retour JSON ne suffit pas comme preuve métier.

## 11. Critères de fin du chantier

Le chantier est terminé lorsque :

1. La conservation volontaire et le rechargement fonctionnent sans créer un deal.
2. Le même product_id accompagne les tours RFQ, le booking et la vie du dossier.
3. Les termes sont lus uniquement depuis le modèle canonique pour les dossiers migrés.
4. Les modules conservent les blocs qu’ils ne possèdent pas et n’appliquent aucune valeur par défaut locale à un produit chargé.
5. Chaque calcul conservé référence ses termes, faits passés, données et configuration effectifs ; Product reste dépourvu de marché courant.
6. Toute action matérielle produit une trace et une révision cohérentes avec les tables métier, y compris les actions automatisées.
7. Les anciennes RFQ, exécutions, versions de fixing et valorisations restent consultables.
8. Les écritures concurrentes et les répétitions ne provoquent ni perte d’information ni double exécution.
9. Les anciens décodeurs supprimés et les adaptateurs historiques encore nécessaires sont inventoriés, avec raison et périmètre explicites.
10. Ajouter un module consommateur ne nécessite ni lecture de `market_snapshot_json` pour trouver les termes, ni analyse locale des noms de barrières, ni copie d’un chargement depuis Deal.

## 12. Limites assumées

Ce plan ne promet pas de rendre interprétable tout PayScript arbitraire, de reconstruire des preuves historiques jamais conservées ou de garantir un rejeu numérique identique après changement de moteur sans environnement archivé.

Il ne crée pas de nouvelle politique de marché, de nouveau modèle quantitatif, de workflow d’annulation/remplacement complet, de référentiel universel d’instruments ni de gestion multi-allocation. Il prépare les frontières nécessaires pour les ajouter ultérieurement sans casser le dossier produit.

Le premier livrable opérationnel recommandé est le lot 2 : explorer librement, conserver explicitement, retrouver le produit et son prix de référence après fermeture, avec la partie deal vide. Les lots suivants prolongent ce même objet dans chaque module jusqu’au risque et aux documents.
