# Bilan de la campagne réelle arrêtée le 12 octobre 2026

La campagne `2c09009e5b984e43aaabef795ba26561` est **STOPPED**, à la demande de Philippe. Elle a terminé cinq dossiers mensuels et atteint le début du sixième mois, au 12 mars 2026 dans le calendrier simulé. L'année complète n'est pas qualifiée. Aucune nouvelle campagne n'est lancée après cette demande.

Les cinq installations Structura privées sont fermées, leurs cinq ports sont libres et leurs dix PID de lancement/serveur ne sont plus présents. La base utilisateur `backend/data/structura.db` conserve exactement son empreinte SHA-256 relevée avant les essais : `afeef093c4ac7ed1d8a97a4c9db9084b270561dd84ba5b0633abed70842b5f78`.

Les décisions utilisent Ollama et `qwen2.5-coder:7b`. Les agents possèdent chacun leur compte et leur base Structura. Les opérations passent par les écrans ou les API natives : notamment `/api/price`, `/api/trading/book-note`, le règlement des executions, `/api/deals/{id}/mtm` et `/api/ccr/calculate`. Les données de marché sont synthétiques, explicitement identifiées. Il s'agit de books de recette isolés.

Les résultats ci-dessous viennent de requêtes SQLite en lecture seule après fermeture et du rapprochement des contrats natifs. Ils ne reposent pas uniquement sur les compteurs du pilote.

| Installation | Deals / écritures natives | Règlements SETTLED | MtM archivés | Fixings officiels | Calculs CCR |
| --- | ---: | ---: | ---: | ---: | ---: |
| Hector | 10 | 10 | 50 | 10 | 4 |
| BNP | 5 | 5 | 30 | 5 | 5 |
| Crédit Agricole | 0 | 0 | 0 | 0 | 0 |
| Société Générale | 0 | 0 | 0 | 0 | 5 |
| Client | 5 | 5 | 25 | 5 | 0 |
| Total | 20 | 20 | 105 | 20 | 14 |

Cela représente **cinq dossiers de 10 M€, soit 50 M€ de volume client**. Les vingt écritures correspondent aux quatre jambes de chaque dossier : vente banque, achat Hector, vente Hector, achat client. Leurs identifiants, sens, contreparties, nominaux, prix et empreintes contractuelles sont rapprochés dans les bases natives. Tous les deals ont un lien Product et une version de termes. Les cinq dossiers sont COMPLETE ; le sixième est PENDING, sans booking.

Les cinq dossiers sont des reverse convertibles, tous exécutés avec BNP. SG a coté et calculé du risque, sans gagner les opérations. La relation Crédit Agricole est volontairement incomplète : le refus natif protège le workflow. Les acceptations, marges et choix de banque n'ont pas été injectés manuellement. Le code métier est resté identique pendant cet essai, sans reprise de campagne ; l'arrêt demandé est une commande opérationnelle explicite.

Le journal contient 187 tours et 192 actions : 191 SUCCESS, un EXPECTED_REFUSAL et zéro FAILED. Aucun incident technique n'a été enregistré. Ce constat ne certifie pas la justesse de tous les textes générés ni celle du moteur quant.

Une limite d'audit est identifiée : le refus de cotation Crédit Agricole à l'action 28 conserve la décision, son motif et sa durée, mais le gestionnaire d'exception remplace les métadonnées du modèle par la seule durée. Les 191 autres actions portent le modèle et les compteurs de tokens. Le vérificateur refuse donc à juste titre une qualification exhaustive de provenance modèle. Cette trace ancienne n'est pas reconstituée artificiellement.

Les 105 MtM et les fixings officiels prouvent l'utilisation du suivi natif. En revanche, aucun produit n'avait encore atteint une échéance payée lors de l'arrêt : zéro proposition de lifecycle appliquée et zéro résolution finale démontrée par cette campagne. La revue du client reste à février, alors qu'Hector et BNP ont commencé mars. L'arrêt explique cette revue de période incomplète. Les fixings observés ne démontrent pas des coupons ou des remboursements à maturité.

Pour les analyses de risque, les quatorze calculs archivés sont des **calculs CCR sur des calls OTC hypothétiques**, dans un périmètre séparé des notes. Ils ne constituent pas une analyse de risque produit des notes bookées. L'« Analyse du risque » du Pricer n'a pas été appelée ; aucun stress natif n'est enregistré dans `shock_runs`. Ces fonctionnalités restent à qualifier.

La durée est excessive pour un jeu de simulation utilisable : environ 66 minutes entre la première et la dernière action, puis la fermeture des installations. Les durées modèle cumulées représentent environ 62 minutes ; la médiane est de 16,16 secondes, le 95e percentile de 38,91 secondes. L'exécution séquentielle appelle le modèle même pour de nombreuses tâches administratives. On compte notamment 32 wait, 22 mail et 50 actions sans modification des faits métier. Une partie des communications est utile, mais ce volume augmente fortement le délai. Les essais et relances de diagnostic précédents ont également allongé le temps total de cette intervention ; une recette courte aurait dû précéder l'essai annuel.

Le discours commercial du modèle reste insuffisant : il répète parfois qu'une barrière à 60 % peut plafonner la perte à 40 %. Cette affirmation est fausse pour ces structures et ne figure pas comme protection dans les contrats ou le payoff natif. Le superviseur ne la corrige pas de façon fiable. Les choix se répètent également : un seul type de produit et une seule banque gagnante sur cet essai.

Les blocages précédemment corrigés concernent le démarrage à froid du modèle, les anciens conseils d'erreur réinjectés après rétablissement, les chemins API inventés, les boucles passives et la dérive de coupon entre fraction moteur et pourcentage utilisateur. Les 57 tests backend ciblés passaient avant cet essai. Aucun changement du code métier n'est effectué pendant le bilan.

La reprise devrait être organisée en lots courts, avec les validations suivantes :

1. **P0 — Recette courte du cycle complet.** Un ou deux dossiers, puis avance explicite du calendrier jusqu'au paiement final. Vérifier les quatre jambes natives, tous les règlements, les MtM, les fixings échus, les flux et la clôture. Enregistrer la durée réelle et fixer un budget avant toute campagne annuelle. Impact : démontrer rapidement l'autonomie et limiter le coût des diagnostics.
2. **P0 — Risque produit et qualité du discours.** Faire utiliser le module d'analyse de risque du Pricer sur le payoff et les résultats natifs ; distinguer commentaire IA, Greeks/stress et CCR. Exiger une preuve liée au produit et à sa version, et détecter les fausses protections de capital dans les messages. Impact : empêcher une campagne techniquement réussie de donner une interprétation métier erronée.
3. **P1 — Réduction des appels au modèle.** Réserver les décisions IA aux choix commerciaux et aux anomalies ; orchestrer explicitement les tâches administratives prêtes et les changements de date. Conserver les autorisations, les préconditions et les reçus de chaque API native. Mesurer appels sans avancement, temps modèle, temps API et temps total sur la même recette avant/après. Impact : rendre le module interactif et prévisible.
4. **P1 — Audit exhaustif.** Conserver les métadonnées de la décision quand une API refuse l'action. Valider un refus métier réel avec modèle, tokens, décision et reçu natif ; ne pas compléter les traces anciennes. Impact : permettre une qualification vérifiable de chaque action, y compris les refus.
5. **P1 — Diversité et couverture métier.** Qualifier séparément reverse convertible, Phoenix, rappel, absence de rappel et scénario défavorable. Distinguer fonctionnalités exercées et résultats validés ; ne pas afficher « suivi complet » sans flux appliqués. Impact : éviter de généraliser une réussite sur un scénario unique.
6. **P2 — Lisibilité du pilotage.** Afficher phase, dossier, dernière preuve native, durée et prochaine échéance ; rendre visibles les états incomplets et le délai de fermeture. Valider arrêt, reprise et suppression d'une ancienne campagne sans toucher aux autres books. Impact : permettre un pilotage autonome compréhensible dans l'admin.

Les preuves détaillées sont conservées dans `backend/data/agent_workshop/2c09009e5b984e43aaabef795ba26561/bilan_evidence.json`, avec les bases isolées et le journal de campagne. Le vérificateur refuse la qualification annuelle : arrêt avant la fin, commande humaine d'arrêt, métadonnées incomplètes sur un refus, revue client incomplète à mars, sixième dossier ouvert et absence de résolution lifecycle appliquée. Ce refus est cohérent avec le résultat observé.
