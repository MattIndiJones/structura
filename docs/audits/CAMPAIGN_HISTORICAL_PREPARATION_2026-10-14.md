# Préparation du rejeu historique et recette courte — 14/10/2026

## Résultat et périmètre

Le scénario **Diagnostic historique — RC, Phoenix, Athena — 2021–2026** est enregistré depuis Simulation, campagne `eeb655ed08994f18af19357657696427`, en état `DRAFT` : zéro action, zéro appel IA et aucun processus d'acteur. La campagne complète n'a pas démarré. Aucun commit, push ou merge.

La recette courte est un essai isolé des installations manuelles et de la base métier principale. Les comptes, desks et contreparties du socle de simulation sont réutilisés. Ses six services sont fermés et leurs six ports sont libres. Structura Admin et le portail restent ouverts pour consulter les paramètres ; aucune IA n'agit.

## Comportement livré

- Les nouveaux scénarios utilisent les historiques locaux, par défaut du **14/10/2021 au 14/10/2026**. La date finale est stricte, y compris si des contrats restent actifs ou si leur règlement est ultérieur. Ils restent ouverts avec une valorisation résiduelle ; aucune maturité artificielle.
- Les cours explicitement renseignés alimentent le spot initial contractuel. Sinon, le lecteur prend le dernier cours déjà connu **à la date rejouée ou avant**. Un trou ou une fin de cache ne bloque pas un dossier disposant d'un cours antérieur. Aucun téléchargement et aucune trajectoire de spot inventée. Sans aucun cours antérieur ni valeur explicite, il reste impossible de valoriser ce sous-jacent : le scénario signale ce cas.
- Le fichier de marché fige les observations existantes, leur origine, leur colonne et l'empreinte du cache. Le report au jour rejoué conserve la date réelle de publication. Le circuit natif de décision sourcée conserve les fixings et leurs preuves ; ces valeurs ne sont pas présentées comme des clôtures brutes fraîchement téléchargées.
- Une décision IA est demandée par cotation, offre au client et acceptation client. L'envoi RFQ, la confirmation et les bookings utilisent les contrôles natifs déterministes. Les décisions sont enregistrées avant l'écriture métier, puis réutilisées en cas de reprise ; une réponse invalide ou une issue incertaine ne déclenche pas une série de nouveaux appels.
- Les contrôles de confirmation, validité, rapprochement et prévention des doubles bookings sont conservés. Les mois sans RFQ avancent et chaque demande d'un même mois possède son identité.
- Les observations utilisent la convention native `modified_following`, avec leur paiement à J+3 ouvrés. Une Athena cinq ans possède cinq rangs annuels ; le coupon de rappel utilise le rang contractuel correspondant. Les anniversaires RFQ tombant un jour non ouvré sont reportés au jour ouvré suivant.
- Le rejeu des exceptions consomme les observations validées dans l'ordre et s'arrête au premier rappel démontré. Il ne réclame plus les constatations postérieures à ce rappel. Le résultat officiel porte la date et le cash du rappel, distincts de la date de paiement finale contractuelle. Le cash certain reste `en_reglement` jusqu'à sa date effective et n'est pas envoyé au Monte Carlo.
- Le suivi ne sollicite pas une IA pour chaque mois ni pour commenter le risque. Les MtM restent à la cadence prévue et au cutoff final ; les books fermés ne génèrent plus de suivi répétitif. Le comptage des positions relit l'état natif après les transitions.
- Les captures attendent la route demandée, le titre de l'écran et la fin du chargement. Un succès API, un scénario exercé et une vérification visuelle restent des preuves distinctes.

## Historique effectivement disponible

Le cache réutilisé est `backend/data/underlying_prices/AIR.parquet`, ticker `AIR.PA`, source conservée `yahoo:AIR.PA`, devise EUR. Il contient des observations du 03/09/2001 au **29/07/2026**. La colonne disponible est `close`, sans colonne `price_close` distincte : base de prix **STORED_CLOSE**, dont le caractère brut/non ajusté n'est pas certifié.

Au-delà du 29/07/2026, le dernier cours connu est reporté avec cette date effective visible. Aucun futur postérieur à une date rejouée n'est consommé. L'empreinte après recette reste `cde16dc48391aeff424b497cd8deb97a51175bdd6d24d4d027b2bfbf07238ba3`. Le cache source et les données d'essais manuels n'ont pas été nettoyés.

Les hypothèses de modèle, funding et marge restent celles du scénario de diagnostic, distinctes de l'historique du spot. Cela ne reconstitue pas une surface de volatilité implicite ni une courbe de crédit historique.

## Recette et incidents conservés

L'essai utilise un premier mois vide, puis deux demandes au deuxième mois et une au troisième : Reverse Convertible par Leonteq, Phoenix et Athena par Kepler. BNP, SG et Citi répondent. **Trois RFQ, neuf cotations, douze bookings sur quatre jambes par opération**, rapprochés sans doublon ; funding non vide dans les calculs natifs. Aucun appel IA payant.

Les refus attendus ont été exercés sur les relations existantes : relation BNP suspendue, puis limite de notionnel Citi abaissée temporairement dans la base privée de recette. Le booking refusé renvoie 422 et ne crée aucune écriture. Les paramètres sont restaurés avant la suite.

Deux arrêts ont été conservés avant reprise sur copie :

1. Import local de date dans le script de recette, arrêt avant toute RFQ ; correctif du script.
2. Constatation `EXPECTED` après un préfixe démontrant déjà un rappel : le contrôle natif refusait une résolution d'exception sur une ligne qui n'en était pas une. Correctif du rejeu ordonné et du suivi après fermeture. Les services ont été fermés avant correction ; la copie reprend les trois dossiers terminés sans refaire leurs cotations ni bookings.

La reprise termine la vérification courte en **66 secondes**, avec 0 appel IA. Elle ne rejoue pas soixante mois de tâches : un point trimestriel représentatif et le cutoff final suffisent à cette recette. Douze MtM sont conservés dans l'état cumulé de l'essai. Le contrôle SQLite final en lecture seule constate **quatre positions échues et huit rappelées**, aucune position active. Le compteur `remaining_active` du premier export était issu d'une liste antérieure à la transition ; `native-final-state.json` rectifie ce constat, et le code courant relit désormais les deals.

Les tests ciblés vérifient séparément le paiement à J+3 du rappel Athena et son coupon de rang 1 (108 %), le règlement du cash certain sans attendre la maturité, et un contrôleur qui s'arrête au cutoff en conservant une position active. Le règlement bancaire réel est hors périmètre.

Le contrôle visuel a chargé dix routes natives : Clients, Produits, Pricer, RFQ envoyées, RFQ reçues, Booking, Risk, CCR, Optimizer et Administration. La configuration occupe **1 392 px** à une fenêtre de 1 440 px, sans colonne latérale de paramètres ; commandes visibles dans une fenêtre de 900 × 780. L'estimation réagit à 0 puis 5 RFQ du mois 1 sans appel IA ni démarrage.

Validation finale : **46 tests backend ciblés validés** (45 réussites dans le groupe final, puis le dernier nœud après mise à jour de son attente de dimanche vers lundi). Aucun lancement de suite backend complète. Build frontend requis effectué : **437 tests frontend réussis et compilation Vite réussie** ; avertissement de mélange d'imports statique/dynamique du store Pricing déjà présent.

## Paramètres du brouillon et estimation

| Paramètre | Valeur enregistrée |
|---|---|
| Fenêtre | 14/10/2021 → 14/10/2026, arrêt strict |
| Mois 1 | Leonteq, RC, BNP/SG/Citi |
| Mois 2 | Kepler, Phoenix, SG |
| Mois 3 | Leonteq, Athena, BNP ; Kepler, RC, BNP/SG/Citi |
| Ensuite | Aucune nouvelle demande, suivi des contrats |
| Produits | RC 12 mois, Phoenix 36 mois, Athena 60 mois ; AIR.PA ; nominal 10 000 000 € |
| Coupons | RC/Athena 8 %, Phoenix 2 % par observation trimestrielle |
| Surveillance / MtM | Mensuelle / trimestrielle, plus MtM au cutoff |
| IA | GPT-6 Luna, graine 42, délai 90 s, plafond 60 appels |
| Budgets | API 2 $, durée réelle 60 minutes |
| Charge estimée | 4 RFQ, 8 cotations, 20 pricings, jusqu'à 192 MtM et 366 rapports quantitatifs |
| Décisions IA estimées | 16, sans retry automatique |
| Coût API estimé | Bas 0,0034 $, central 0,0056 $, haut 0,014 $ |
| Durée indicative | 13,7 / 27,5 / 55 minutes (bas / central / haut) |

L'estimation est gratuite : calcul local à partir des paramètres, du catalogue de tarifs daté du 14/10/2026 et des mesures précédentes. Elle constitue une prévision, pas une promesse de durée ni une facture. Les bornes supposent les contrats survivants pour estimer la charge maximale ; les rappels peuvent la réduire.

## Limites et suite

- Cette recette ne certifie pas l'ensemble de Structura ni la validité économique exhaustive de ses moteurs.
- Pas de nouveau test API GPT payant : le nombre de sollicitations et leur dédoublonnage sont vérifiés avec une réponse simulée ; le prochain lancement exercera le modèle réel.
- CCR quantitatif sur OTC, Valo Explain entre deux valorisations et branches contractuelles non empruntées restent à qualifier. La recette porte ici sur les notes ; le contrôle juridique de relation et la limite de notionnel ne constituent pas une validation complète ISDA/CSA.
- La preuve visuelle porte sur le chargement correct des écrans et les erreurs JavaScript, pas sur chaque saisie ou modalité ergonomique.
- AMC, FIFO, inscription et double validation restent exclus de la couverture demandée. Les contrôles de production existants ne sont pas supprimés.
- Prochaine action : lancer explicitement le brouillon depuis Simulation. En cas de blocage, arrêter, conserver les preuves, qualifier et corriger après arrêt ; reprendre sur copie seulement si les books sont cohérents.

## Preuves

- Premier arrêt : `.runtime/diagnostic-acceptance/73722b569b47445c87758ce77aa9ab74/6be955222390440f87fb8a736c0be496/`.
- RFQ, refus et arrêt lifecycle : sous-dossier `verified-copy/6be955222390440f87fb8a736c0be496/` du même dossier.
- Reprise : sous-dossier `recall-copy/6be955222390440f87fb8a736c0be496/`, avec `acceptance-result.json`, `native-final-state.json`, `final-port-check.json`, bases isolées, logs et captures.
- Paramètres du brouillon : `.runtime/hybrid-saas/admin-workbench/campaigns/eeb655ed08994f18af19357657696427/campaign.json`.
- Capture utilisateur : `.runtime/diagnostic-acceptance/historical-draft-2026-10-14.jpg`.

Cette note complète le [bilan du précédent essai synthétique](CAMPAIGN_DIAGNOSTIC_5Y_BILAN_2026-10-14.md), sans réécrire ses résultats. L'arbitrage utilisateur de report au dernier cours connu remplace la proposition initiale de blocage sur toute donnée historique manquante.
