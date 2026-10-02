# Projet futur — SA-CCR pour dérivés OTC et portefeuille mixte

**Date :** 29/09/2026  
**Statut :** cadrage, aucun calcul SA-CCR livré  
**Périmètre initial :** dérivés OTC sur actions et indices ; aucun produit de taux dans cette première version.

## Objectif

Donner une vue cohérente du risque de crédit d'un portefeuille qui contient à la fois des notes et des dérivés OTC, puis calculer l'exposition au défaut réglementaire **SA-CCR** des seuls contrats éligibles. La vue doit identifier qui porte le risque, envers quelle entité juridique et selon quel accord. Elle conserve séparément l'exposition économique actuelle, les profils EE/PFE et la CVA du CCR existant.

Pour une note détenue par un client, le risque principal de défaut de l'émetteur est porté par ce client. Une banque qui a émis la note ne détient pas, du seul fait de l'émission, une créance OTC sur l'acheteur. Pour un dérivé OTC, l'exposition de la banque à sa contrepartie dépend notamment du sens du contrat, de son MtM, des flux, du netting opposable et du collatéral. La perspective de calcul doit donc être explicite avant toute agrégation.

SA-CCR produit une **EAD réglementaire** sur son périmètre d'application ; elle ne représente ni une perte probable en euros, ni la PFE 95 % issue de Monte-Carlo. La CVA et les autres mesures économiques gardent leur définition propre. La formule de référence est `EAD = alpha × (RC + PFE_SA-CCR)` ; chaque terme et les règles d'agrégation devront être implémentés selon une version réglementaire identifiée, sans réutiliser la PFE économique du moteur actuel.

## Point de départ dans Structura

- L'onglet Deal possède déjà **Format juridique** (`transaction_format`) et **Instrument** (`instrument_family`) dans `frontend/src/components/DealTab.vue`. Ces valeurs sont enregistrées sur le deal figé dans `backend/app/db/models.py` et `backend/app/api/deals.py`. Elles sont aujourd'hui des textes libres et peuvent être absentes : elles constituent le point d'entrée du classement, pas une preuve suffisante à elles seules.
- Le CCR économique et ses accords, sets de netting, collatéraux et limites sont décrits dans [CCR_IMPLEMENTATION_2026-09-28.md](CCR_IMPLEMENTATION_2026-09-28.md). Il ne calcule actuellement aucune EAD SA-CCR. Sa PFE 95/99 est une projection économique par scénarios, distincte de `PFE_SA-CCR`.
- Le [jeu UAT du compte test](CCR_UAT_TEST_CLIENT_2026-09-29.md) contient 23 deals de notes. Les sets OTC qui y figurent sont simulés et n'intègrent pas ces notes. Lors de l'examen du 29/09/2026, `transaction_format` et `instrument_family` étaient absents sur les 23 deals : un chantier de qualification des historiques est nécessaire avant de s'en servir pour des résultats réglementaires.
- Le référentiel `Counterparty` et le CRM `Client` jouent des rôles distincts. L'identité du client commercial ne suffit pas à déterminer l'obligé juridique, le porteur du risque ou un droit au netting.

## Règles de classement à construire

Créer un classement contrôlé et versionné à partir du couple **format juridique × famille d'instrument**, complété par le sens de la position, l'émetteur ou contrepartie juridique et les termes du contrat. Normaliser les valeurs à la saisie, conserver les valeurs d'origine et expliquer toute correction manuelle.

| Format juridique | Instrument | Traitement attendu |
|---|---|---|
| EMTN ou BMTN | Note ou certificat de dette | Risque de l'émetteur pour le détenteur ; hors moteur SA-CCR OTC. Déterminer explicitement l'émetteur et le détenteur. |
| OTC | Option actions/indices | Candidat SA-CCR « equity », **après** validation du contrat, du prix, des dates, du sens et de la contrepartie juridique. |
| OTC | Swap actions, equity swap ou TRS | Candidat futur, uniquement après modélisation complète des deux jambes, resets, flux, conventions et MtM résiduel. |
| Autre couple ou valeur manquante | Toute famille | `À qualifier` ; conserver la mesure économique disponible, bloquer l'EAD SA-CCR et afficher le motif. Aucune déduction silencieuse depuis le nom du produit. |

Un classement ne doit pas transformer un produit économiquement optionnel mais juridiquement émis comme note en contrat OTC. Les cas hybrides ou atypiques passent en revue manuelle documentée. Une migration des deals historiques établit une liste d'anomalies ; elle ne modifie pas automatiquement les contrats figés. Les nouvelles réservations exigent des codes normalisés et une combinaison cohérente.

## Architecture cible du calcul

1. **Périmètre et perspective.** Fixer l'entité qui calcule, sa position contractuelle, l'obligé juridique, la nature de la créance et la date d'arrêté. Écarter les contrats éteints après paiement, mais garder les flux constatés et non réglés selon leur statut réel.
2. **Voie économique.** Réutiliser le moteur CCR existant pour l'exposition actuelle, EE, PFE 95/99, stress et CVA si ses données de marché et de crédit sont suffisantes. Les scénarios communs et les valorisations figées restent traçables ; des MtM cohérents en date, devise et hypothèses sont nécessaires avant agrégation.
3. **Voie réglementaire OTC.** Sélectionner uniquement les contrats validés SA-CCR ; grouper par entité juridique et set de netting juridiquement opposable. Calculer RC, collatéral reconnu, add-on equity, facteur de maturité, delta prudentiel, multiplicateur, `PFE_SA-CCR`, puis EAD avec les règles de la version retenue. Les contrats non margés et margés ont leurs propres règles. Aucune compensation sur simple égalité de nom ou d'identifiant de contrepartie.
4. **Portefeuille mixte.** Présenter côte à côte le risque émetteur des notes et l'exposition des sets OTC. Fournir une vue de concentration par groupe juridique en gardant la décomposition par origine et métrique. Ne jamais additionner l'EAD réglementaire, une PFE Monte-Carlo et une exposition courante sous l'étiquette d'un unique « risque total ». Toute mesure consolidée nouvelle doit avoir une définition, un horizon et des hypothèses explicites.

Le calcul SA-CCR doit être paramétré par juridiction, texte applicable, version et date d'effet. En l'absence de choix réglementaire validé, livrer au plus une simulation étiquetée **référence Bâle**, sans la présenter comme une EAD prudentielle homologuée. Les données manquantes importantes (qualification du produit, netting opposable, CSA, collatéral, maturité ou paramètres contractuels) donnent un statut explicite `DONNÉES MANQUANTES` ou un calcul autonome sans avantage juridique non prouvé ; elles ne deviennent jamais zéro par défaut.

## Données et audit requis

| Domaine | Données minimales / contrôle |
|---|---|
| Deal | Identifiant figé, format juridique et instrument normalisés, sens banque/client, notionnel et devise, dates, échéancier, sous-jacent, paramètres de valorisation, MtM daté et source. |
| Identités | Entité de la banque, client commercial, contrepartie contractuelle, émetteur et éventuel garant : rôles distincts et liens datés. |
| Accords | ISDA ou autre master agreement, set et périmètre produits, opinion d'opposabilité, dates et statut ; CSA et conditions de marge si applicables. |
| Collatéral | Positions datées, reçu/posté, éligibilité, haircut, devise, seuils, MTA, IM/VM et fréquence. |
| Résultat | Date d'arrêté, périmètre, juridiction et version de règles, empreinte des entrées et du marché, moteur, détail RC/add-on/multiplicateur/PFE/EAD, exclusions motivées, utilisateur et horodatage. |

Le paramétrage CCR UAT actuel est partagé au niveau de l'entité Demo. Les accords et collatéraux simulés devront rester isolés ou clairement identifiés dans un environnement de recette ; ils ne doivent pas influer sur les décisions ou limites réelles.

## Lots de développement et critères de sortie

| Lot | Livraison | Critère d'acceptation |
|---|---|---|
| 0 — Inventaire et décisions | Inventaire des produits réellement bookables/valorisables, des valeurs Deal historiques et des données juridiques ; choix de la juridiction et d'un premier produit OTC actions/indices. | Matrice de couverture signée, écarts chiffrés, aucun historique requalifié implicitement. |
| 1 — Qualification | Codes contrôlés pour format et instrument, validation des combinaisons, rôles juridiques et perspective, workflow de revue des anciens deals. | Un deal ambigu reste visible mais ne produit pas d'EAD ; correction justifiée et auditée. |
| 2 — Portefeuille mixte économique | Vues notes/OTC séparées, agrégation économique aux horizons cohérents, exposition par obligé et groupe, affichage des exclusions. | Un même nom de contrepartie ne crée pas de netting entre note et OTC ; les courbes de portefeuille sont recalculées sur scénarios communs avant quantile. |
| 3 — Produit OTC éligible | Contrat et MtM résiduel d'une première option OTC actions/indices, flux et dates, intégration au set juridique. | Sens et MtM validés pour les deux parties ; rejeu à date figée reproductible. |
| 4 — SA-CCR equity | Moteur réglementaire versionné, RC et PFE SA-CCR, margé/non margé, audit des facteurs et publication séparée de l'EAD. | Cas de référence calculés indépendamment et résultats expliqués jusqu'au deal/set ; aucune PFE économique recyclée. |
| 5 — Extension swaps actions/TRS | Modèle des jambes et flux, resets, MtM et événements de vie ; extension du classement et du moteur seulement après validation. | Scénarios de paiement/reset et sens de créance couverts ; aucun swap de taux ajouté par défaut. |

Des jeux de recette dédiés doivent couvrir au minimum : note achetée par le client, note émise par la banque, option OTC avec MtM positif/négatif, deux OTC dans un set valide, même contrepartie sans accord opposable, CSA valide ou expiré, collatéral reçu/posté, maturité ou métadonnées manquantes, portefeuille note + OTC de la même entité, et rejeu d'un calcul ancien après changement de règles. Chaque écran doit afficher la date, l'horizon, la devise, la perspective et les hypothèses qui expliquent le montant.

## Décisions à trancher avant le lot 4

1. Juridiction réglementaire visée, version locale applicable et niveau de validation attendu : simulation interne ou chiffre destiné à un usage prudentiel.
2. Premier produit OTC actions/indices dont les termes, le booking et le MtM sont effectivement complets.
3. Responsable de la qualification des deals historiques et preuve requise pour l'opposabilité des accords/CSA.
4. Définition souhaitée d'une éventuelle mesure consolidée de concentration pour le portefeuille mixte, distincte de l'EAD SA-CCR.

**Référence normative de départ :** [Basel Framework, CRE52 — Standardised approach to counterparty credit risk](https://www.bis.org/committees/bcbs/basel-framework/standard/cre/52/inforce/2023-01-01/published/2020-06-05). La transposition de la juridiction retenue et sa version à la date de calcul seront à vérifier avant d'implémenter ou de qualifier un résultat réglementaire.
