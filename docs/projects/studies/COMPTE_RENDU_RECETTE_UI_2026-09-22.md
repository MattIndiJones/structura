# Recette Studies exécutée dans l’application — 22 septembre 2026

## Périmètre et preuve d’exécution

Nouvelle étude lancée depuis l’interface locale, avec connexion de démonstration Admin, scan du dossier `artifacts/studies/LO_ALL_BLOCKS_2020_2025`, puis calcul des blocs A à K. Aucun code applicatif ni input modifié. Les références sont celles du [plan de recette](RECETTE_LONG_ONLY_2026-09-22.md).

- Méthode : `studies-2.4`.
- Calcul généré le `2026-09-22T15:05:01.369513+00:00`, durée déclarée 52,125 secondes.
- Empreinte du résultat : `c523980c85c6002c6eae5e16552be4824c78ab1cda1103897a76279cce2f43d8`.
- Manifeste : `a037c64ba6f5430a79032434bb9100b38c3be7e332ee5fecb5882f349c04082f`.
- Les empreintes du manifeste, du résultat et des six inputs correspondent au contrôle historique. Après sauvegarde UI (étude id 2), les 85 comparaisons ont été réexécutées sur cette nouvelle sortie : 85/85 conformes. Un contrôle financier complémentaire donne 108/108 conformes : 100 valeurs sur les vingt titres, trois frais cumulés, dividendes cumulés, actif net final, profit net, HWM final et semi-déviation. Total : 193/193, selon les tolérances consignées dans les CSV, sans validation de tous les scénarios possibles.
- Contrôle qualité affiché dans Données IA : `ready`, aucune position divergente, aucun mark manquant, écart NAV `0 bp AUM`.

Les chiffres ci-dessous sont les valeurs réellement restituées. Les contrôles exacts supplémentaires utilisent le résultat de la nouvelle étude sauvegardée, extrait en lecture seule. Les comparaisons financières portent sur les références au centime (tolérance 0,0050001 USD), le HWM à quatre décimales et la semi-déviation à deux décimales en pourcentage.

## Comparaison des écrans

| Écran | Observations de la nouvelle exécution | Verdict numérique |
|---|---|---|
| Configuration | 1 % gestion, actif net précédent ACT/365 ; performance 15 %, annuelle ; transaction 0,05 % ; dividendes fournis, cash ; FIFO strict ; prix du relevé au 31/12/2025 ; FF5+MOM ; benchmark synthétique ; rolling 60 | Conforme |
| Méta | NAV 100 → 138,0652 ; performance 38,07 % ; 1 566 NAV ; 1 540 ordres ; 100 000 parts ; 19 lignes finales ; panier initial 18 titres au 02/01/2020 | Conforme |
| B agrégats | Réalisé 3 777 696 USD, latent 567 572 USD, total hors dividendes 4 345 268 USD dans Données IA ; dividendes 917,7 kUSD ; net 3,81 MUSD ; résiduel 0,0 % et 0 bp AUM | Conforme, confirmé sur le résultat sauvegardé |
| B frais | Gestion 660,1 kUSD ; performance 671,7 kUSD ; transactions 124,6 kUSD ; 3 périodes positives ; HWM final 138,0652 | Cumuls et HWM final conformes ; détail annuel non vérifié |
| B FX | −296 122 USD ; −7,84 % du réalisé signé ; colonne « dont FX réalisé — déjà inclus » | Conforme |
| B vingt titres | Les 20 lignes réalisé/latent/total hors dividendes concordent avec le CSV indépendant à l’arrondi affiché ; dividendes et résultat avec dividendes concordent sur les 20 lignes de l’écran ; titres 01 et 12 conservés avec poids et latent nuls | Conforme, 100/100 comparaisons financières |
| A | Alpha net +3,15 %, t 0,63, p 0,5307, R² 2,93 %, 1 565 observations ; six bêtas et leurs t/p conformes à la référence | Conforme ; alpha non significatif |
| C | 1 341 appariements FIFO ; 59,1 % gagnants ; profit factor 1,72 ; détention moyenne 145,8 jours, médiane 151 ; volume 249,24 MUSD ; turnover période 2 266,1 %, annualisé 382,9 % | Conforme à la référence C |
| D | 521 long terme, 820 tactiques ; 18 titres positifs, 2 négatifs ; cash exclu ; P&L total utilisé | Conforme au calcul descriptif |
| E | B&H 151,99 / +52,06 % ; fonds aligné +38,13 % ; VAG −13,93 points | Conforme au scénario actuel ; net/brut et dividendes différents |
| F | Réplicant +18,64 %, fonds +38,07 %, écart +19,42 points ; score 38 | Conforme ; incohérences textuelles ci-dessous |
| G | Allocation −10,25 ; sélection −4,08 ; interaction +0,79 ; total −13,54 points ; calcul indicatif hors scoring | Conforme |
| H | 1 540 ordres, 782 BUY / 758 SELL ; couverture 100 % ; scores 0,493 / 0,524 / 0,508 ; t global 1,553, p 0,1369 | Conforme aux repères |
| I | Score 43 ; N par horizon 782/761/728/662 ; alpha −0,03/−0,07/+0,00/−0,28 % ; succès 47,70/48,49/49,31/49,70 % dans Données IA | Conforme |
| J | Score 56 ; composantes 40/50/73/80/51 ; Sharpe 0,490, Sortino 0,718, Calmar 0,168 ; IR −1,074 ; TE 3,07 % ; captures 80,1/81,7 % ; DD −31,70 %, 36 épisodes, durée moyenne 58,3 jours ; HHI 0,0644 | Conforme aux repères, sauf champ absent de l’écran |
| K | 5 événements ; nombres d’ordres 24/88/212/2/64 ; ratios 0,69/1,05/1,00/0,06/0,97 ; flux nets +84 090/−574 104/+527 671/−884/−160 494 USD | Conforme à l’arrondi affiché |
| Manager Skill | 53/100 ; six dimensions ; A 30 %, I 25 %, E 20 %, J 15 %, H 7 %, D 3 % ; E disponible, score 44,2 dans Données IA | Conforme |
| Couverture | 100 % explicitement documentaire ; G calculé, 100 %, indicatif et hors scoring ; avertissement distinguant couverture et significativité | Conforme |

## Écarts de restitution et risques à traiter

1. **J : semi-déviation absente de l’écran, mais disponible dans les données.** Écran « — » ; Données IA « Semi-écart ann. +8,25 % ». Le frontend lit `semi_deviation_pct` alors que le moteur fournit `semi_deviation_ann_pct` (`frontend/src/views/AmcView.vue:3421`, `backend/app/core/amc_riskmanagement.py:219`). Il s’agit d’un défaut de restitution, pas d’une absence du calcul.
2. **A/C : deux turnovers annualisés différents sous un libellé proche.** A affiche 365 %, C 382,9 %. A annualise par `252 / nombre de NAV`, C par `365 / jours calendaires entre les ordres` (`amc_engine.py:867`, `amc_blocks.py:329`). L’aide de C annonce pourtant `252 / N jours`. Harmoniser la convention ou expliquer clairement les deux périmètres.
3. **F : la phrase recommandée revendique encore un panier d’ETF.** Elle contredit la réserve correcte précisant qu’aucun portefeuille négociable n’est démontré. Le commentaire affiche aussi +19,43 points, contre +19,42 dans la tuile. Reprendre le chiffre exact et parler de reconstruction factorielle théorique (`AmcView.vue:4171`).
4. **G : avertissements SPDR/snapshot actuel génériques inadaptés au jeu local.** La méthodologie mentionne correctement les secteurs du dossier et les poids du début de période, puis affirme des proxies SPDR et un snapshot actuel. Rendre les réserves dépendantes des sources réellement utilisées (`AmcView.vue:4380`).
5. **B : aides de la réconciliation restées anciennes.** L’aide du net parle seulement de FIFO moins frais de gestion, alors que le résultat intègre aussi dividendes, commissions de performance et transactions. L’aide des frais parle encore d’une borne au dernier ordre. Les montants contrôlés sont cohérents ; ces descriptions ne le sont pas (`AmcView.vue:2179`).
6. **A/D/H/I : formulations de compétence encore trop affirmatives dans les aides.** H appelle 0,5 « trader aléatoire », alors que son interprétation précise justement que ce repère n’est pas un scénario aléatoire simulé. D conserve « Un bon gérant… » et le vocabulaire de positions clôturées malgré une classification par titre incluant le latent. I assimile certains taux de succès à de la compétence. Aligner les aides sur les réserves descriptives déjà présentes.
7. **Données IA : libellé « BRUT (avant frais) » encore présent pour l’ajustement des seuls frais de gestion.** L’écran A est plus précis. Corriger la préparation textuelle (`amc_synthesize.py:462`) pour ne pas propager cette ambiguïté au modèle et au rapport.
8. **E : en-tête au 01/01/2020 malgré une référence au 02/01/2020.** Le corps indique la bonne date et Données IA la performance alignée. Afficher la date effective et une VAG en points de pourcentage. La réserve net/brut est présente ; elle ne signifie pas que les conventions ont été harmonisées.
9. **Configuration : badge « POSITIONS TS non configuré » malgré le panier chargé.** Le scan annonce correctement les 18 titres et les résultats E/G les exploitent. Le badge peut faire croire à tort que le setup est incomplet.
10. **K : arrondis des flux négatifs et absence de devise près des flux.** Le rendu −574 104 pour une référence −574 103,71 et −884 pour −883,54 est compatible avec une précision entière, mais la présentation gagnerait à afficher la devise et une convention d’arrondi homogène.

## Contrôles complémentaires et verdict final

- **Sauvegarde / réouverture : conforme sur les repères contrôlés.** Étude id 2 « Recette UI long only — 22/09/2026 », restaurée par le bouton Charger. NAV 138,0652, 1 566 NAV, 1 540 ordres, panier initial, score 53 et contribution E à 20 % / VAG −13,93 conservés. Il ne s’agit pas d’un second recalcul indépendant.
- **IA : non conforme.** Ollama `qwen2.5-coder:14b` dépasse 180 secondes ; erreur visible. `gemma3:4b` répond en 57 secondes, mais produit 2 992 caractères de JSON de provenance tronqué, sans synthèse d’analyse. L’application l’insère automatiquement et annonce « Synthèse IA intégrée au rapport ». La preuve conserve le prompt français et la réponse ; aucune cause de troncature du contexte n’est démontrée ici. Contrôler la pertinence et la complétude avant insertion, signaler une génération non exploitable.
- **PDF : génération réussie, restitution non conforme.** PDF complet de 127 pages, avec G et K, conservé dans l’archive applicative. Empreinte SHA-256 vérifiée : `3fe5611a206965d02a8598f9116a38016021d6834a26b75aa5b7accaa3a9d6fa`. Export demandé avant le retour IA : ce PDF ne contient pas la mauvaise synthèse. La récupération du fichier depuis le téléchargement automatique du navigateur n’a pas été confirmée ; les octets ont été extraits en lecture seule de l’archive sauvegardée via l’interface.
- **PDF B, page physique 6 : réserve majeure.** Les montants concordent, mais le pont montre +4,35 M de P&L, −1,46 M de frais et +3,81 M net sans afficher les +917 678,53 USD de dividendes nécessaires au rapprochement. Les colonnes dividendes / total avec dividendes de l’écran ne sont pas reprises dans ce tableau. La description affirme un HWM journalier et des prélèvements au nouveau plus-haut, alors que le paramètre est annuel. Corriger le texte et compléter le pont.
- **Autres restitutions PDF.** E inclus dans le score 53 et réserve net/brut présente ; J affiche bien la semi-déviation 8,25 % absente de l’écran. G indique « 21/20 titres », cash inclus dans un compteur mais pas dans l’autre. Des libellés `P&L;` sont visibles. La couverture et la page B ont été rendues et inspectées : petits textes gris peu contrastés. Contrôle textuel des sections principales effectué ; les 127 pages n’ont pas toutes été inspectées visuellement. PDF simplifié non testé dans cette exécution.
- **Frais / HWM annuels : non vérifiés.** Les trois cumuls, trois cristallisations positives et HWM final concordent. Le détail année par année n’est pas exposé dans le résultat contrôlé : on ne déduit pas sa conformité de celle des cumuls.

Une seconde sauvegarde id 3, « Recette UI — preuve échec IA et export PDF — 22/09/2026 », conserve volontairement la mauvaise réponse IA et le PDF exporté auparavant. C’est une preuve d’anomalie, pas un rapport client validé. L’étude id 2 reste la sauvegarde sans cette réponse.

### Priorités de clôture

1. **P1 :** synthèse IA exploitable avec détection de réponse invalide ; PDF cohérent avec les frais paramétrés et les dividendes ; harmonisation du turnover et suppression des revendications méthodologiques contradictoires.
2. **P1 :** contrôle annuel traçable des frais/HWM avant introduction de souscriptions/rachats.
3. **P2 :** semi-déviation affichée, badges et aides actualisés, unités et dates harmonisées, contrastes et libellés PDF.

**Verdict : calculs conformes sur les 193 contrôles exécutés ; recette globale non acceptée.** Les points IA/PDF et la restitution méthodologique empêchent de qualifier le parcours complet de validé. Aucun code applicatif ni input modifié ; pas de commit/push.

### Preuves locales

Dossier `artifacts/studies/RECETTE_UI_2026_09_22/` : `resultat.json`, `checks.csv` (85), `financial_checks.csv` (108), `summary.json`, `preuve_ia.json`, `rapport_complet.pdf`, extraction texte et rendus des pages 1 et 6. Ces fichiers ignorés par Git restent locaux.

Nettoyage de fin de recette : processus Python démarrés pour ce contrôle (19884 et enfant 31180) arrêtés après vérification de leur identité ; aucun listener restant sur le port 8000.
