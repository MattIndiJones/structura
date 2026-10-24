# Bilan de la campagne de cinq ans — 14 octobre 2026

## Conclusion et arrêt

La campagne `0280f37ec90643628b9a14780614d323` est terminée, mais elle **ne valide pas le rejeu historique demandé**. Elle a utilisé un marché entièrement synthétique du 14 octobre 2025 au 19 décembre 2030. La fenêtre attendue par Philippe est désormais explicitement le **14 octobre 2021 au 14 octobre 2026**, sans observation de marché au-delà de la date finale.

Le choix du scénario synthétique et de la date initiale n'a pas été correctement cadré avant le lancement. Le statut technique `COMPLETED` ne signifie pas que cet objectif métier a été atteint. La campagne est à conserver comme recette mécanique sur données fictives, sans la présenter comme une validation historique de Structura.

Elle s'était déjà terminée avant la demande d'arrêt. Les six installations privées sont fermées : vérification des douze PID enregistrés (lanceurs et services) et des six ports, aucun processus ni écoute restant. Aucune reprise ou nouvelle campagne lancée. L'application admin et le portail commun restent ouverts pour consultation. Aucun code applicatif modifié, test relancé, commit ou push pendant ce bilan.

## Comment le marché a été construit

`scenario_market.create_market` génère une trajectoire quotidienne GBM reproductible, graine **42**, niveau de départ **100**. Les paramètres sont fixes : taux **2,5 %**, dividende **2 %**, volatilité **23 %**. Le hasard porte sur les chocs quotidiens de spot, pas sur ces paramètres. Les observations générées sont des jours de semaine, avec un pas numérique de 1/252.

Le fichier `synthetic_market.json` porte explicitement le fournisseur `SYNTHETIC_SCENARIO` et la méthode « Synthetic GBM scenario, r=2.5%, q=2%, sigma=23%; not historical data ». Il contient 3 289 observations fictives AIR.PA, du 14/10/2024 au 21/05/2037. La campagne n'en a consommé qu'une partie ; cette étendue du fichier n'est pas une période historique téléchargée.

AIR.PA est ici un identifiant de scénario : même les cours avant le 14 octobre 2026 ne proviennent pas de l'historique réel d'Airbus. Le spot initial du premier dossier, par exemple, est 159,13026754, obtenu sur cette trajectoire générée. Les taux, dividendes et volatilités utilisés ne sont pas des calibrations historiques à chaque date.

Les courbes de funding sont des trajectoires privées prédéfinies dans le scénario, interpolées entre dates et maturités. Les marges commerciales sont choisies dans les politiques enregistrées ; les huit décisions de cotation ont retenu les cibles BNP 35 bps, SG 45 bps et Citi 25 bps. L'IA ne génère pas les cours ni les calculs de prix. Le moteur Monte Carlo existant effectue les valorisations.

Cette source synthétique convient à une recette reproductible de mécanismes. Elle ne remplace pas des spots et fixings historiques. Une simulation Monte Carlo du futur pour calculer un MtM à une date donnée est un autre usage : elle ne doit pas être confondue avec les observations servant au rejeu historique.

## Exécution obtenue

| Mesure | Résultat |
|---|---:|
| Durée réelle | 34 min 48 s |
| Période du scénario | 14/10/2025–19/12/2030 |
| RFQ / cotations publiées | 4 / 8 |
| Dossiers rapprochés | 4 |
| Nominal final client fictif | 40 000 000 EUR |
| Écritures de booking | 16 |
| Actions enregistrées | 928, toutes `SUCCESS` |
| Actions par API / échanges internes | 924 / 4 |
| Actions métier par écran | 0 |
| Appels HTTP | 4 288 |
| Pricings initiaux et bookings | 20 |
| MtM archivés | 120 |
| Rapports quantitatifs | 374 |
| Appels IA | 48 |
| Jetons entrée / sortie | 151 759 / 4 437 |
| Coût IA calculé au tarif enregistré | 0,0173944 USD |
| Coûts IA inconnus signalés | 0 |
| Incidents détectés automatiquement | 0 |

Le montant IA est un calcul local de consommation, pas une confirmation de facture fournisseur. Le plafond était de 2 USD. Aucune facturation client Structura ni transaction financière réelle n'est activée.

440 actions `settle` et 440 actions `review` représentent l'essentiel des 928 actions. Elles sont pilotées par le contrôleur sans appel IA. Un compteur d'actions élevé ne représente donc pas autant de décisions IA ni autant de règlements réellement nouveaux.

## Les quatre opérations et leurs issues fictives

Chaque dossier porte 10 000 000 EUR et AIR.PA. Les écritures banque, demandeur acheteur/vendeur et client ont été rapprochées.

| Dossier | Demandeur / produit | Destinataires | Émetteur retenu | Issue observée |
|---|---|---|---|---|
| CASE-0001 | Leonteq / RC 12 mois | BNP, SG, Citi | Citi | Maturité 14/10/2026 ; paiement prévu 19/10/2026 ; payout contractuel enregistré 108 % |
| CASE-0002 | Kepler / Phoenix 36 mois, coupon trimestriel 2 % | SG | SG | Rappel dès le 14/02/2026 ; payout enregistré 102 % |
| CASE-0003 | Leonteq / Athena 60 mois | BNP | BNP | Maturité 16/12/2030 ; paiement prévu 19/12/2030 ; perte de capital, payout enregistré 35,035332 % |
| CASE-0004 | Kepler / RC 12 mois | BNP, SG, Citi | Citi | Maturité 15/12/2026 ; paiement prévu 18/12/2026 ; payout enregistré 108 % |

Ces payouts sont des résultats du scénario fictif, pas des performances réelles ou des paiements bancaires constatés. Les six bases, ouvertes en lecture seule pour l'audit, contiennent exactement **16 deals : 12 échus et 4 rappelés**. Tous les derniers suivis indiquent zéro deal actif. Les 16 exécutions de règlement initial sont `SETTLED` avec références de recette.

Les événements utilisent le circuit natif d'exception manuelle auditée : source déclarée et référence identifiant le marché synthétique. Ils ne sont pas présentés comme fixings Yahoo. L'application des fixings et des résolutions a abouti, mais aucun relevé ou acquittement bancaire externe ne prouve les versements finaux.

Pour le Phoenix rappelé, les quatre deals ont `realized_payout=1.02`, mais `settlement_amount` reste nul et `payment_date` conserve la date contractuelle finale de 2028. Cela ne suffit pas à conclure à un bug de paiement ; le suivi et la preuve du règlement spécifique au rappel doivent être qualifiés séparément. `SETTLED` concerne ici les exécutions DvP de recette du booking.

## Fonctions exercées et limites

| Domaine | Preuve obtenue | Ce qui reste non validé |
|---|---|---|
| Comptes et isolation | Six installations privées ; identités et relations préparées ; fermeture vérifiée | Rejeu des écrans d'inscription volontairement exclu ; qualité de l'expérience utilisateur non démontrée |
| Clients / Product / catalogue | CRM natif, dossiers et versions de termes reliés aux RFQ et deals ; lectures du catalogue | Création/édition complète par un utilisateur, tous les scripts et modèles du catalogue |
| RFQ | 4 demandes, 8 cotations, sélection, acceptation et confirmations explicites ; 16 bookings rapprochés | Refus, révisions, retraits, expiration, rupture de transport et reprise délibérément provoqués |
| Pricing / funding / marges | Moteur existant, trois payoffs, courbes de funding et marges privées ; 20 calculs enregistrés | Calibration historique et qualité numérique exhaustive, tous les modèles, tous les sous-jacents |
| Cycle de vie | Fixings déclarés, rappel Phoenix et maturités RC/Athena ; états terminaux cohérents | Paiements externes ; preuve complète de règlement du rappel ; tous les cas de coupons/barrières |
| MtM / risque | 120 runs MtM, surveillance périodique ; recette représentative Greeks, exposition et stress | Stress historiques divers, franchissements de limites et toutes les configurations de risque |
| Juridique / CCR | 27 relations préparées ; calcul d'un call OTC hypothétique face à BNP, distinct des notes | Refus juridiques, nuances full/partiel/absent, marges de collateral, défaut de contrepartie et limites violées |
| Documents | Calcul KID/EMT et archive KID sur un dossier représentatif | Relecture humaine de conformité et toutes les variantes |
| Valo Explain | Deux runs existants et une note générée | Justesse exhaustive de l'attribution économique et tous les scénarios |
| Réinvestissement | Scan d'une alternative, sans nouveau RFQ ou booking | Parcours complet de réinvestissement et comparaison historique |
| Optimizer | Une recherche Athena à un candidat, enregistrée puis relue | Exploration large, autres objectifs et parcours utilisateur complet |
| Administration | Lectures comptes, desks et contreparties | Ensemble des opérations administratives et droits en situation contradictoire |
| Écrans | Dix captures et textes conservés | Recette visuelle fiable et parcours saisis par un utilisateur : collecte trop précoce constatée |

AMC, FIFO, inscription et double validation restent exclus conformément au périmètre. Le contrôle ordinaire des confirmations et des doublons n'a pas été supprimé. Aucun doublon n'est observé ; une tentative volontaire de double booking n'a pas été exécutée dans cette campagne.

## Défauts identifiés par le bilan, malgré zéro incident automatique

1. **Priorité 0 — objectif historique non atteint.** Date initiale 2025 au lieu de 2021, marché synthétique avant et après aujourd'hui, poursuite jusqu'en 2030. L'affichage du scénario n'a pas empêché ce cadrage erroné. Il faut une fenêtre historique explicitement bornée et un précontrôle de provenance des données.
2. **Priorité 1 — validation visuelle trop faible.** La recette attend du texte non vide, sans attendre le bon écran chargé. Le texte enregistré pour `/pricer` est celui de « Mes Produits » ; celui de `/booking` est celui des RFQ reçues ; le fichier de `/products` montre encore « Chargement… ». La ligne « écrans : EXERCISED » ne vaut donc pas validation d'utilisabilité. Les 0 actions métier par écran confirment que les RFQ et bookings ont été faits par API.
3. **Priorité 1 — couverture métier surestimable.** Tous les dossiers ont réussi, sans solliciter les branches de refus, de limite, de validité expirée ou de transport en panne. Un unique call OTC face à BNP ne valide pas l'ensemble du CCR et du cadre juridique. Le statut terminé et les 14 lignes `EXERCISED` indiquent des recettes représentatives, pas « tout Structura est validé ».
4. **À qualifier — règlement après rappel.** Payout Phoenix enregistré, mais absence de montant et de date propres au règlement du rappel dans les colonnes auditées. Revoir le circuit de preuve avant de considérer le paiement final validé.
5. **Priorité 2 — estimation de charge incomplète.** 374 rapports quantitatifs contre une borne annoncée de 315 ; 34 min 48 s contre une fourchette de 8–32 min et un central de 16 min. Coût IA proche du central : 0,0173944 USD contre 0,0168 USD. Le temps est principalement dans les appels locaux et la surveillance, pas dans 48 appels IA.
6. **Priorité 2 — suivi répétitif et lecture de couverture.** 880 commandes de règlement/suivi, souvent sans nouvel événement ni règlement. Leur utilité et leur fréquence devront être rationalisées sans perdre la couverture métier. Les marqueurs historiques et la matrice représentative divergent notamment sur « réinvestissement » ; leurs périmètres doivent être rendus explicites.
7. **Priorité 1, à qualifier — calendrier contractuel produit.** Le calendrier enregistré du Phoenix porte un rappel le samedi 14/02/2026. Celui de l'Athena comporte une observation le dimanche 15/12/2030, puis une sixième observation finale le lundi 16/12/2030 pour un produit de 60 mois. Le script paie le coupon cumulé avec `COUPON * INDEX` au rappel : l'effet d'un rang 6 sur cinq années doit être vérifié. Cette trajectoire n'a pas rappelé l'Athena et n'a donc pas exercé ce cas de coupon. Distinguer le calendrier d'observation, l'ajustement des paiements et le stub final avant de conclure à un défaut du moteur. La présence des deux dates et du rang 6 est vérifiée dans la base ; leur conformité aux termes voulus reste à qualifier. Preuve : `calendar-audit.json`.

Ces constats sont consignés dans ce bilan, sans réécrire le journal original ni changer artificiellement le statut de la campagne. Il n'y a pas de bug d'exécution bloquant enregistré sur les parcours effectivement empruntés. Il y a en revanche un défaut majeur de cadrage et des preuves insuffisantes pour l'objectif historique et l'usage humain.

## Cadre de la prochaine correction — aucun code effectué ici

1. Définir clairement le mode **rejeu historique**, du 14/10/2021 au 14/10/2026, avec arrêt strict à la date finale et provenance visible dans Simulation.
2. Réutiliser les historiques déjà en base/cache, valider dates disponibles, prix non ajustés pour les fixings, calendriers et opérations sur titres. Aucun remplacement silencieux par un scénario synthétique ; une donnée obligatoire absente bloque le départ.
3. À chaque date rejouée, utiliser seulement des observations déjà disponibles à cette date. Les hypothèses de pricing, funding et marge gardent leur provenance et leur caractère éventuellement simulé ; la trajectoire historique du spot ne doit pas être inventée.
4. Préserver la vraie vie contractuelle. Une Athena cinq ans émise au troisième mois ne peut pas être forcée à maturité avant le 14/10/2026 dans cette fenêtre : elle reste active au cutoff, avec MtM résiduel. Si l'on veut tester sa maturité, prévoir un dossier contractuellement échu dans la fenêtre. Même une émission au premier jour peut avoir un règlement J+3 après la date finale : le montrer, sans prolonger l'historique au-delà d'aujourd'hui.
5. Fiabiliser l'attente du bon écran, les assertions d'état et les preuves humaines ; distinguer succès API, scénario exercé, scénario non testé et bug.
6. Qualifier les calendriers d'observation et le comptage du coupon Athena, le règlement après rappel et les branches juridiques/limites retenues, puis revoir les commandes répétitives et l'estimation de durée. Une recette courte précède le prochain lancement complet.

## Preuves conservées

- Dossier original : `.runtime/hybrid-saas/admin-workbench/campaigns/0280f37ec90643628b9a14780614d323/` : journal, configuration figée, manifeste de code, six bases, logs, marché synthétique et dix captures.
- Export demandé depuis Simulation : `C:/Users/phili/Downloads/recette-0280f37e.json`, recopié dans `.runtime/diagnostic-acceptance/five-year-0280f37e/`.
- Copie d'état final : `final-state.json`, SHA-256 `98bfb1f41c809f0a0502816073843c1b0ded98c0020c98ff9cd0fdabef85bc8b`.
- Audit SQLite en lecture seule : `readonly-database-audit.json`, SHA-256 `384e5d14bb1443a9a39ae18cb2e4235b875c0fab0b4d87ae2ca8e2c215fe37f4`.
- Capture de fin et vérification des processus/ports conservées avec cet export. Aucune base d'essai manuel ou base principale nettoyée ou réutilisée pour cet audit.
