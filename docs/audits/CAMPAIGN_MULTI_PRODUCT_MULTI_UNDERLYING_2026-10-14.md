# Campagne historique multi-produits et multi-sous-jacents — 14 octobre 2026

## Périmètre préparé

- Fenêtre : 14/10/2021 au 14/10/2026, arrêt strict à la date finale.
- Douze mois actifs répartis sur cinq ans, trois RFQ par mois actif : 36 RFQ prévues. Les autres mois servent au suivi des books et aux échéances.
- Kepler et Leonteq demandent des RFQ ; BNP Paribas, Société Générale, Citi et UBS répondent. Leonteq répond également aux RFQ de Kepler. Les décisions commerciales restent soumises aux contrôles natifs.
- Reverse Convertible : AIR.PA / MC.PA ; Phoenix : AIR.PA / SAN.PA ; Athena : AIR.PA / MC.PA / SAN.PA. Nominal de 10 M€ par dossier, courbes de funding et marges propres aux répondants.
- Historiques locaux conservés, sans spot synthétique. Les trois caches s'arrêtent au 29/07/2026 ; le dernier cours connu est repris ensuite et la provenance est signalée. Le cache ne distingue pas de close brut.
- OpenAI GPT-6 Luna, plafond API 2 $, 260 appels maximum, limite réelle 210 minutes. Estimation avant départ : 234 appels, 0,0819 $ au centre et 0,2047 $ en borne haute ; durée indicative 91,3 minutes au centre et 182,6 minutes en borne haute. Ce ne sont pas des résultats observés.

## Exécution et preuves

1. `eeb655ed08994f18af19357657696427` : arrêt à la première cotation BNP. La configuration acceptait 500 trajectoires, tandis que `/api/price` exige au moins 1 000 (`HTTP 422`). Une RFQ Kepler a été envoyée ; aucun deal. Le signalement est qualifié `HARNESS`. Coût IA : 0,0002478 $.
2. `8ee6a17456cc40918102cd98e7ed29c4` : bases transactionnelles neuves, 1 000 trajectoires. Huit cotations, offre et acceptation client obtenues. Arrêt avant booking : le contrôleur transmettait `reason` à `Tools.accept_quote`, qui attend `justification`. Signalement `CONFIRMED_BUG`, preuve conservée. Coût IA : 0,0029357 $.
3. `b567dd8d1ad84d9fa74823796ca23858` : bases neuves après correction ciblée et deux tests ciblés réussis. Premier mois terminé avec trois RFQ, treize cotations et **trois deals complets de 10 M€**. Chaque dossier a quatre écritures cohérentes, sans jambe manquante ni doublon selon `check_books`. L'une des RFQ de Kepler a reçu une cotation de Leonteq ; les rôles combinés ont donc été exercés. Le début du deuxième mois a produit trois nouveaux dossiers et neuf cotations supplémentaires, puis arrêt avant la cotation SG du `CASE-0006` : réponse OpenAI non décodable (`Extra data: line 2 column 1`). Il s'agit d'un arrêt fournisseur/atelier, sans écriture de cotation pour cette sollicitation et sans retry automatique. Coût IA : 0,008805 $ pour 25 appels ; 27 pricings, 12 MtM et cinq rapports quantitatifs comptabilisés.

Les trois essais ont coûté environ **0,0119885 $** d'API au total. Le troisième s'est arrêté au 15/11/2021, soit un mois historique achevé sur soixante. Les mois suivants, les échéances contractuelles ultérieures et les contrôles visuels des écrans restent non testés par cette relance. Les succès constatés sont des preuves API et de rapprochement natif, pas une validation exhaustive de l'ergonomie ni du pricing.

Les états complets, versions de code, caches figés et journaux de campagne sont dans `.runtime/hybrid-saas/admin-workbench/campaigns/<id>/`. Les captures et prévisions de cette relance sont dans `.runtime/diagnostic-acceptance/multi-product-multi-underlying-20261014/`. Les installations appartenant aux campagnes sont fermées ; le portail et Structura Admin restent accessibles.

## Points à reprendre

1. Préserver et diagnostiquer la réponse IA mal formée sans inventer de décision. Une reprise ponctuelle, bornée et tracée peut être envisagée après vérification du parsing et de l'absence d'effet métier ; ne pas répéter les 24 décisions déjà appliquées ni les bookings existants.
2. Vérifier la cohérence du suivi financier d'un appel IA dont la sortie est invalide et conserver une preuve exploitable de la réponse brute dans le périmètre privé de campagne.
3. Reprendre le deuxième mois à partir des données existantes seulement après ce contrôle ; confirmer ensuite au moins deux deals complets par mois actif, sans forcer les refus commerciaux attendus.
4. Continuer jusqu'au cutoff ou au prochain blocage ; distinguer explicitement succès API, contrôle visuel, refus attendu, bug Structura et arrêt fournisseur.

Aucun commit ni push n'a été effectué.
