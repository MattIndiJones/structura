# Campagne courte RFQ et cycle de vie — 14/10/2026

Campagne privée fictive `206896a969bf4f28a1cccc641421b11a`, sur GPT-6 Luna :
une reverse convertible, un mois commercial, maturité à douze mois, Kepler
demandeur et cinq répondants. Plafonds : 150 appels modèle, 0,25 $ estimé,
220 actions et 15 minutes par lancement. Aucune facturation métier.

## Résultat vérifié dans les bases privées

La campagne a terminé au mois 13 (`COMPLETED`) après une reprise contrôlée.
Cinq cotations ont été publiées ; les quatre jambes de `CASE-001` sont rapprochées
`COMPLETE` pour 10 M EUR et leurs règlements initiaux portent une référence.
Quarante-deux revues ont créé 52 valorisations natives. Huit versions de fixings
officiels synthétiques sont sourcées, quatre propositions finales sont `APPLIED`.
Les quatre deals sont `échu` avec issue `final` et `realized_payout=1,08` du nominal.
La constatation finale est datée du 13/10/2026, le paiement contractuel du
16/10/2026 ; la dernière revue a eu lieu au 13/11/2026. Aucun événement échu
n'est resté sans fixing validé/appliqué. Les bases privées et ports des acteurs
ont été lus en lecture seule après l'arrêt ; Admin et portail ouverts par ce
pilote ont également été arrêtés.

Ce résultat prouve le calcul du remboursement, la transition native à `échu`
et le suivi au-delà de la date de paiement. Il ne prouve pas un virement réel,
ni une preuve externe de règlement du remboursement. Les quatre propositions
appliquées n'ont pas de `validated_by`/`applied_by` humain : ce scénario ne
qualifie donc pas une seconde validation humaine du cycle de vie. L'Analyse du
risque produit du Pricer n'était pas raccordée ; elle reste non exercée et ne
dispose pas encore d'un indicateur dédié dans la couverture de campagne.

## Incidents et reprise

Le premier lancement s'est arrêté après 23 actions : la réponse BNP a atteint
la limite de 2 000 jetons de sortie. Aucune cotation n'a été publiée par cette
réponse. Le plafond est passé à 4 000 jetons et cette troncature est désormais
un échec de décision réessayable, sans déclarer le fournisseur indisponible.
Sept tests backend ciblés ont réussi. La même campagne a été reprise en
conservant le dossier RFQ et ses preuves ; elle a alors terminé à 94 actions,
67 appels IA et 0,0210054 $ de coût estimé, avec six décisions échouées en tout.

Cinq de ces échecs sont des sorties OpenAI rejetées par le parseur (`Extra data`)
malgré le schéma structuré ; aucune action métier n'a été exécutée par ces
sorties et les décisions suivantes ont repris. Les sept incidents affichés
comprennent ces cinq erreurs, la réponse initiale tronquée et l'incident
de fournisseur induit par le premier arrêt. Leur cause exacte reste à analyser
avant de considérer le format des décisions fiable sur une campagne longue.

Le vérificateur historique `check_workshop_campaign.py` relève correctement les
preuves natives et le rapprochement, mais son verdict global est `FAIL` : il
exige une campagne vierge non reprise, exactement la période commerciale au
dernier mois, toutes les actions issues du modèle et aucun échec. Ces quatre
hypothèses ne correspondent pas à cet essai repris, au suivi postcommercial ni
aux préparations déterministes. Il relève aussi le changement de code entre
les deux lancements. Ne pas présenter `COMPLETED` comme une qualification globale.

Preuves locales : `.runtime/hybrid-saas/admin-workbench/campaigns/206896a969bf4f28a1cccc641421b11a/` ;
`campaign.json`, `lifecycle-export.json`, `lifecycle-resume-export.json` et
`qualification-lifecycle.json`. Aucun commit ni push.
