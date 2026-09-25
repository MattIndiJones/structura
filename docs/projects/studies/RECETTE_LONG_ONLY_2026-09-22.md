# Recette utilisateur Studies — Long only 2020–2025

Exécutée le 22 septembre 2026. **Statut : 193 contrôles numériques conformes ; recette globale non acceptée (IA, PDF et restitution).** Voir le [compte rendu de la nouvelle exécution](COMPTE_RENDU_RECETTE_UI_2026-09-22.md), qui fait foi pour les observations et les limites. Les tableaux ci-dessous restent la grille de référence, sans substitution des résultats détaillés du compte rendu. Aucun code applicatif ni input modifié.

## 1. Ce que cette recette valide

Vérifier les calculs et leur restitution sur le scénario long only existant avant de passer aux souscriptions et rachats. La réussite de ce cas ne valide pas le long/short, toutes les conventions de frais ou tous les instruments.

Trois statuts à utiliser : **Conforme**, **Écart à examiner**, **Non vérifié**. Pour une différence de convention identifiée, noter **Conforme au calcul actuel — réserve méthodologique** ; ne pas la présenter comme une validation économique générale.

La dernière sortie sauvegardée porte la méthode `studies-2.4`, générée le 2026-09-21T13:18:13.566848+00:00. Son contrôle contient 85/85 comparaisons conformes. Le 22 septembre, les empreintes des six fichiers d’entrée référencés ont été comparées à celles de cette sortie : toutes sont identiques. Cela ne prouve pas qu’une nouvelle exécution est identique. Le manifeste doit également correspondre aux paramètres ci-dessous.

## 2. Procédure — aucun script nécessaire

1. Ouvrir AMC → Étude. Si le backend n’a pas été redémarré depuis les dernières corrections, le redémarrer, puis actualiser la page avec Ctrl+F5.
2. Dans Sources, saisir le dossier ci-dessous, puis cliquer **Scanner le dossier**.
3. Vérifier les paramètres du tableau. Garder le benchmark synthétique et les marchés du dossier.
4. Lancer une **nouvelle étude complète**, puis conserver son identifiant, la date du calcul et la version de méthode. Ne pas utiliser une ancienne étude sauvegardée.
5. Suivre les contrôles dans l’ordre : Méta → B → frais/HWM → A → C/D → E/F/G → H/I/J/K → Manager Skill → synthèse/PDF.
6. Pour chaque écart, conserver la valeur exacte/exportée, une capture de l’écran complet, le paramétrage et la date du calcul. Ne pas modifier les inputs pour faire correspondre le résultat.

```text
C:\Users\Admin\GitHub\structura\artifacts\studies\LO_ALL_BLOCKS_2020_2025
```

| Paramètre | Valeur de cette recette |
|---|---|
| Période du fonds | 01/01/2020–31/12/2025 |
| Devise | USD |
| Capital initial / nombre de parts | 10 000 000 USD / 100 000 parts |
| Flux investisseurs | Apport initial uniquement ; aucun flux ultérieur |
| Gestion | 1 % ; NAV précédente ; ACT/365 |
| Performance | 15 % ; HWM ; cristallisation annuelle |
| Transactions | 0,05 % |
| Dividendes | Fournis, conservés en cash ; pas de réinvestissement automatique du fonds |
| Valorisation / carnet | Composition au 31/12/2025 ; quantités déjà ajustées des splits ; FIFO strict |
| Facteurs | Developed_5F_MOM ; FF5+MOM |
| Benchmark | SYNTH_BENCH20_USD |
| Fenêtre glissante | 60 observations |
| E / G | Panier du 02/01/2020 : 18 titres et 15,9647 % de cash net |
| Marchés / blocs | market_data.json ; A à K activés |

Le fonds commence en cash le 01/01. Les premiers achats ont lieu le 02/01 : le panier E/G représente la fin de cette journée. Ne pas injecter ces positions une seconde fois dans le FIFO.

## 3. Tolérances et unités

- Les nombres de NAV, ordres, lots, titres et épisodes doivent correspondre exactement.
- Comparer à la précision affichée : 0,005 pour une valeur arrondie à deux décimales ; 0,05 à une décimale ; 0,0005 à trois décimales. Pour le contrôle automatique, appliquer les tolérances explicites de `checks.csv`, pas une tolérance inventée.
- Un affichage « 4,35 M » ne suffit pas à valider un montant au centime : vérifier le détail ou l’export. Si indisponible, marquer le contrôle détaillé Non vérifié.
- Un écart de performance s’exprime en **points de pourcentage**. Un ratio décimal de 0,0293 correspond à un R² de 2,93 %.
- Seuil indicatif du rapprochement NAV : 1 bp de l’AUM final = environ 1 380,65 USD. Ici la référence vise un écart nul aux arrondis près ; un petit écart sous 1 bp mérite encore d’être expliqué.

## 4. Méta et pont comptable — priorité 1

| Contrôle | Attendu | Observé / verdict |
|---|---:|---|
| NAV initiale | 100,00 | À relever |
| NAV finale | 138,065178 (138,07 si 2 décimales) | À relever |
| AUM net final | 13 806 517,80 USD | À relever |
| Performance cumulée depuis le 01/01 | +38,065178 % | À relever |
| NAV / rendements | 1 566 / 1 565 | À relever |
| Ordres / titres négociés sur six ans | 1 540 / 20 | À relever |
| Lignes finales, cash compris | 19 = 18 actions + USD | À relever |
| Cash final / valeur des actions | 2 033 000,23 / 11 773 517,57 USD | À relever |

| Pont du capital initial à l’actif net final | USD |
|---|---:|
| Capital initial | 10 000 000,00 |
| P&L réalisé, change inclus | +3 777 696,13 |
| P&L latent, change inclus | +567 572,09 |
| Dividendes nets | +917 678,53 |
| Frais de gestion | −660 069,40 |
| Commissions de performance | −671 738,44 |
| Frais de transaction | −124 621,11 |
| **Actif net final** | **13 806 517,80** |

Le P&L prix/change réalisé + latent vaut **4 345 268,22 USD**. Avec les dividendes : **5 262 946,75 USD** avant frais. Après frais : **3 806 517,80 USD**, égal à l’augmentation de l’actif net. Les termes arrondis séparément peuvent différer d’un centime de la somme calculée à pleine précision.

**FX réalisé : −296 121,97 USD, soit −7,84 % du P&L réalisé signé.** La colonne « dont FX » est incluse dans le réalisé : ne pas l’ajouter une seconde fois. Le FX total du journal économique, réalisé et latent, est −140 413,60 USD : ce n’est pas le même périmètre. Le montant FX réalisé est confirmé par la sortie Studies sauvegardée et la convention documentée ; il n’est pas un contrôle supplémentaire des 85 lignes indépendantes.

### Frais et HWM — contrôle annuel de référence

Ces lignes viennent du journal indépendant, pas du moteur Studies. Si l’interface n’expose pas le détail annuel, le contrôle reste Non vérifié tant qu’un export ou un détail adapté n’est pas disponible.

| Année | NAV finale | Rendement annuel % | HWM final par part | Gestion USD | Performance USD | Observé / verdict |
|---|---:|---:|---:|---:|---:|---|
| 2020 | 102,546460 | 2,55 | 102,546460 | 97 910,06 | 44 937,52 | À relever |
| 2021 | 131,288967 | 28,03 | 131,288967 | 112 595,52 | 507 220,73 | À relever |
| 2022 | 99,221101 | -24,43 | 131,288967 | 103 920,09 | 0,00 | À relever |
| 2023 | 113,924092 | 14,82 | 131,288967 | 105 980,34 | 0,00 | À relever |
| 2024 | 110,766476 | -2,77 | 131,288967 | 110 265,21 | 0,00 | À relever |
| 2025 | 138,065178 | 24,65 | 138,065178 | 129 398,18 | 119 580,19 | À relever |

**Point décisif :** 2023 est une année positive, mais aucune commission de performance n’est due, car la NAV reste sous le HWM de 2021. Le HWM reste à 131,288967 de fin 2021 à fin 2024. Il remonte à 138,065178 fin 2025. Les très faibles résidus numériques proches de zéro dans le fichier de référence ne sont pas des frais négatifs.

## 5. B — Les 20 sous-jacents

Valeurs indépendantes en USD, calculées à partir de `fifo_by_asset.csv`. **La colonne total du fichier source inclut les dividendes** : ci-dessous le total prix/change est explicitement réalisé + latent. Les frais du fonds ne sont pas répartis dans ce tableau.

| Titre fictif | Réalisé | Latent | Total prix/change | Dividendes | Total avec dividendes | Verdict |
|---|---:|---:|---:|---:|---:|---|
| 01 | 354 978,82 | 0,00 | 354 978,82 | 36 509,10 | 391 487,92 | À relever |
| 02 | 82 266,85 | 112 574,11 | 194 840,96 | 44 626,76 | 239 467,72 | À relever |
| 03 | 490 428,44 | 125 931,37 | 616 359,80 | 43 907,06 | 660 266,87 | À relever |
| 04 | 74 412,73 | -926,96 | 73 485,77 | 49 812,58 | 123 298,35 | À relever |
| 05 | 404 494,20 | 3 097,39 | 407 591,59 | 53 963,97 | 461 555,56 | À relever |
| 06 | 318 632,18 | -5 807,87 | 312 824,31 | 36 696,83 | 349 521,13 | À relever |
| 07 | 469 953,64 | 40 633,52 | 510 587,17 | 44 408,41 | 554 995,57 | À relever |
| 08 | -226 216,03 | -7 966,54 | -234 182,57 | 44 969,99 | -189 212,58 | À relever |
| 09 | 28 987,90 | 4 610,02 | 33 597,92 | 48 114,10 | 81 712,02 | À relever |
| 10 | 184 623,75 | 47 705,14 | 232 328,89 | 55 811,52 | 288 140,41 | À relever |
| 11 | 294 287,25 | 53 027,50 | 347 314,75 | 39 004,39 | 386 319,14 | À relever |
| 12 | 245 384,78 | 0,00 | 245 384,78 | 40 771,95 | 286 156,73 | À relever |
| 13 | 36 754,48 | -9 632,02 | 27 122,46 | 45 902,14 | 73 024,60 | À relever |
| 14 | 212 047,86 | 13 799,60 | 225 847,47 | 50 016,19 | 275 863,65 | À relever |
| 15 | 128 504,95 | 13 263,73 | 141 768,68 | 52 272,63 | 194 041,31 | À relever |
| 16 | 315 493,75 | -26 965,18 | 288 528,57 | 39 087,14 | 327 615,71 | À relever |
| 17 | 105 479,61 | 106 485,52 | 211 965,13 | 44 712,65 | 256 677,78 | À relever |
| 18 | 122 829,39 | 35 915,17 | 158 744,56 | 43 625,45 | 202 370,01 | À relever |
| 19 | 309 336,97 | 17 694,62 | 327 031,59 | 49 358,66 | 376 390,25 | À relever |
| 20 | -174 985,39 | 44 132,97 | -130 852,42 | 54 107,02 | -76 745,40 | À relever |

Vérifier les titres 01 et 12 : position finale nulle, mais P&L réalisé conservé. Ne pas confondre poids final et poids historique. Les sommes des lignes arrondies peuvent présenter un écart de quelques centimes par rapport aux totaux à pleine précision.

## 6. A — Fama-French + Momentum

Lire la version **nette** pour cette comparaison. La vue ajustée des seuls frais de gestion n’est pas une NAV brute comptable.

| Mesure | Attendu indépendant | Verdict |
|---|---:|---|
| Rendements alignés | 1 565 ; 02/01/2020–31/12/2025 | À relever |
| Alpha quotidien | 0,000124942581 | À relever |
| Alpha annualisé linéaire | +3,148553 % (affichage +3,15 %) | À relever |
| R² | 0,0292913 = 2,92913 % | À relever |
| t-stat alpha / p-value | 0,627019 / 0,530739 | À relever |

| Facteur | Bêta | t-stat HAC 5 | p-value |
|---|---:|---:|---:|
| Mkt-RF | 0,1073 | 4,987 | 6.81932e-07 |
| SMB | 0,2403 | 3,885 | 0.000106609 |
| HML | -0,0977 | -1,848 | 0.0647299 |
| RMW | 0,1764 | 2,398 | 0.016583 |
| CMA | 0,0488 | 0,653 | 0.513899 |
| MOM | -0,0062 | -0,244 | 0.807255 |

**Interprétation attendue :** alpha positif mais non significatif au seuil de 5 %. Un Manager Skill Score publié ne doit pas effacer cette réserve. Les t-stats et p-values sont des contrôles manuels complémentaires : le contrôle automatique historique ne compare pas toutes ces statistiques.

## 7. C et D — Trading et comportement

| Bloc / indicateur | Attendu | Verdict |
|---|---:|---|
| C — Appariements FIFO | 1 341 | À relever |
| C — Taux gagnant / profit factor | 59,1 % / 1,72 | À relever |
| C — Durée moyenne / médiane | 145,8 / 151 jours | À relever |
| C — Notionnel brut échangé | 249 242 222,38 USD | À relever |
| C — AUM moyen | 10 998 557,45 USD | À relever |
| C — Turnover période / annualisé | 2 266,14 % / 382,93 % | À relever |
| D — Lots long terme / tactiques | 521 / 820 | À relever |
| D — Titres gagnants / perdants | 18 / 2 ; cash exclu | À relever |

Ne pas comparer les 20 titres de D aux 1 341 lots de C : ce sont des granularités différentes. Les autres cases de la matrice D doivent être nulles pour ce scénario. Le classement poids courant OU durée maximale, fondé sur le résultat, ne constitue pas un test d’alpha de conviction.

## 8. E, F et G — Référentiels

| Bloc / indicateur | Attendu | Verdict |
|---|---:|---|
| E — NAV initiale du panier | 99,955261 au 02/01/2020 | À relever |
| E — NAV passive finale | 151,990058 → 151,99 | À relever |
| E — Performance passive / fonds même période | +52,06 % / +38,13 % | À relever |
| E — VAG | −13,93 points | À relever |
| F — Performance réplicant / fonds aligné | +18,64 % / +38,07 % | À relever |
| F — Écart / score | +19,42 points / 38 | À relever |
| G — Allocation / sélection / interaction | −10,25 / −4,08 / +0,79 point | À relever |
| G — Retour actif | −13,54 points | À relever |

- **E :** le fonds est net de frais avec dividendes en cash, le panier passif est brut avec dividendes réinvestis. Valider le calcul sous ces conventions, pas une mesure pure de la valeur ajoutée du gérant. Le +38,13 % commence au 02/01, le +38,07 % au 01/01.
- **F :** ajustement sur le même échantillon ; portefeuille théorique non directement investissable. La sensibilité au R² n’est pas un intervalle de confiance du talent.
- **G :** attribution statique du panier de référence, non attribution dynamique du fonds géré. −10,254506 −4,081614 +0,791343 = −13,544777 points à pleine précision. Calcul disponible sur proxies, portée indicative, exclu du scoring : une fiabilité nulle pour le score n’implique pas que le calcul n’existe pas.

## 9. H et I — Timing et sélection

| H — Mesure | Attendu | Verdict |
|---|---:|---|
| Ordres analysés / couverture | 1 540 / 100 % | À relever |
| Score moyen entrées / sorties | 0,4930 / 0,5241 | À relever |
| Score moyen global | 0,5083 | À relever |

Le score descriptif H de 51,7/100 utilisé dans le Manager Skill Score est une transformation distincte de cette moyenne : ne pas attendre automatiquement 50,83/100. Lire le test statistique séparément ; 20 titres ne représentent pas 1 540 observations indépendantes.

| I — Horizon | Achats évaluables | Surperformance moyenne % | Taux de succès % | Verdict |
|---|---:|---:|---:|---|
| 1M | 782 | -0,0330 | 47,70 | À relever |
| 3M | 761 | -0,0691 | 48,49 | À relever |
| 6M | 728 | 0,0012 | 49,31 | À relever |
| 12M | 662 | -0,2778 | 49,70 | À relever |

I : **782 achats**, score global **43/100**. Le nombre évaluable diminue avec l’horizon, car les derniers achats n’ont pas tous un historique futur suffisant à l’arrêté.

## 10. J — Gestion du risque

| Mesure | Attendu | Verdict |
|---|---:|---|
| Score global / sous-scores | 56 ; performance ajustée 40, drawdown 50, risque baissier 73, concentration 80, facteurs 51 | À relever |
| Drawdown maximal / Ulcer index | −31,70 % / 15,35 % | À relever |
| Épisodes / durée moyenne | 36 / 58,3 jours calendaires | À relever |
| Sharpe / Sortino / Calmar | 0,490 / 0,718 / 0,168 | À relever |
| Volatilité annualisée | 12,08 % | À relever |
| Information ratio / tracking error | −1,074 / 3,07 % | À relever |
| Capture hausse / baisse | 80,1 % / 81,7 % | À relever |
| VaR 95 % / ES 95 % quotidiennes | −1,22 % / −1,54 % | À relever |
| Pire jour / 5 observations / 21 observations | −2,44 % / −8,28 % / −20,39 % | À relever |
| Lignes / poids maximal | 19, cash inclus / 14,7249 % | À relever |
| HHI / nombre effectif | 0,0644 / 15,53 | À relever |

Les cinq pires épisodes du tableau ne sont pas le nombre total : on attend 36. Les rendements sont annualisés sur 252 observations et le taux sans risque des ratios descriptifs J est nul. Le CAGR 252 observations est 5,3311 %, contre 5,5244 % en ACT/365,25 : cette différence de convention n’est pas un bug.

## 11. K — Chocs historiques

| Événement | Ordres | Notionnel brut USD | Flux net USD | Ratio d’activité | Verdict |
|---|---:|---:|---:|---:|---|
| covid_2020 | 24 | 2 703 507,52 | 84 090,34 | 0,69 | À relever |
| china_2021 | 88 | 14 870 373,33 | -574 103,71 | 1,05 | À relever |
| bear_2022 | 212 | 32 474 563,00 | 527 670,52 | 1,00 | À relever |
| svb_2023 | 2 | 87 470,17 | -883,54 | 0,06 | À relever |
| china_property_2023 | 64 | 10 243 374,52 | -160 494,27 | 0,97 | À relever |

On attend cinq événements applicables. Décrire l’activité observée sans transformer ces chiffres en preuve de discipline ou de sur-réaction.

## 12. Manager Skill, couverture, synthèse et PDF

Score global indépendant attendu : **53/100**. Le détail ci-dessous est la restitution sauvegardée de la politique descriptive 2.4, à vérifier dans l’interface ; ce tableau n’est pas un nouvel oracle indépendant.

| Dimension | Poids effectif % | Sous-score /100 | Disponible |
|---|---:|---:|---|
| Alpha Fama-French (A) | 30 | 63,1 | Oui |
| Stock Picking (I) | 25 | 43,0 | Oui |
| Référentiel Inertiel / VAG (E) | 20 | 44,2 | Oui |
| Risk Management (J) | 15 | 56,0 | Oui |
| Timing Score (H) | 7 | 51,7 | Oui |
| Taux de titres gagnants (D) | 3 | 90,0 | Oui |

- [ ] VAG disponible, poids 20 %, sous-score 44,2 : pas de suppression ni de renormalisation silencieuse.
- [ ] Brinson calculé mais qualifié d’indicatif sur proxies et non intégré au scoring ; même information dans G, couverture et PDF.
- [ ] FX réalisé négatif, −296 121,97 USD et −7,84 % du réalisé, jamais +6,80 % « du réalisé ».
- [ ] Dimension D intitulée taux de titres gagnants ou explication équivalente, sans preuve d’alpha de conviction.
- [ ] Alpha A non significatif ; scores descriptifs ; réserves E/F/G conservées.
- [ ] Sauvegarder puis rouvrir l’étude : mêmes chiffres, mêmes sources et mêmes calculs complémentaires.
- [ ] Si G est recalculé, cohérence du bloc, de sa couverture et de la version du résultat ; ne pas conserver une synthèse rattachée à un ancien calcul.
- [ ] Si l’IA est activée, produire une synthèse pour cette exécution : chiffres cohérents, aucune donnée inventée, aucune certification du talent. Sa rédaction peut varier ; on valide les faits et réserves, pas un texte mot pour mot.
- [ ] Générer un nouveau PDF : comparer la période, B, E, G, J, Manager Skill et les réserves aux écrans. Les anciens PDF ne s’actualisent pas.

## 13. Journal de recette — voir le compte rendu exécuté

| Étape | Observé / capture / export | Verdict | Action |
|---|---|---|---|
| Paramètres et version | studies-2.4 ; nouveau calcul du 22/09 | Conforme |  |
| Méta et pont comptable | Actif net 13 806 517,80 USD ; écart nul | Conforme |  |
| B — 20 sous-jacents | 100 comparaisons réalisé/latent/total/dividendes | Conforme |  |
| Frais / HWM annuel | Cumuls et HWM final conformes ; détail annuel non exposé | Non vérifié annuellement | Contrôle annuel à clore |
| A | Alpha p=0,5307 ; facteurs conformes | Conforme numériquement | Revoir textes |
| C / D | Valeurs conformes ; turnover A/C divergent | Écart à examiner | Harmoniser convention et aides |
| E / F / G | Repères conformes sous conventions actuelles | Réserves méthodologiques | Revoir textes F/G et unités E |
| H / I | Repères conformes | Conforme numériquement | Revoir aides |
| J / K | Repères conformes ; semi-déviation UI absente | Écart à examiner | Corriger restitution |
| Manager Skill / couverture | 53 ; E inclus à 20 % ; couverture documentaire 100 % | Conforme |  |
| Sauvegarde et réouverture | id 2 restauré ; repères conservés | Conforme sur repères contrôlés |  |
| Synthèse IA | 14B timeout ; 4B JSON tronqué accepté | Non conforme | Détection de sortie invalide |
| PDF | 127 pages exportées ; frais/dividendes mal expliqués | Non conforme | Aligner avec écran et paramètres |

**Critère de passage au scénario suivant :** pont comptable expliqué, aucune anomalie de calcul non résolue sur les contrôles réalisés, réserves méthodologiques visibles et résultats cohérents entre écrans/export/synthèse. Un contrôle non exposé ou non exécuté reste explicitement Non vérifié. Le HWM et les frais devront être clos avant d’ajouter les flux investisseurs.

## 14. Sources et limites du contrôle sauvegardé

- Référence indépendante tous blocs : [summary.json](C:/Users/Admin/GitHub/structura/artifacts/studies/LO_ALL_BLOCKS_2020_2025/RESULTATS_ATTENDUS/summary.json)
- Repères par écran : [expected_by_screen.csv](C:/Users/Admin/GitHub/structura/artifacts/studies/LO_ALL_BLOCKS_2020_2025/RESULTATS_ATTENDUS/expected_by_screen.csv)
- Référence financière indépendante : [summary.json](C:/Users/Admin/GitHub/structura/artifacts/studies/LO_BASE_2020_2025_V1/reference/summary.json)
- Frais et HWM annuels : [annual_results.csv](C:/Users/Admin/GitHub/structura/artifacts/studies/LO_BASE_2020_2025_V1/reference/annual_results.csv)
- P&L par titre : [fifo_by_asset.csv](C:/Users/Admin/GitHub/structura/artifacts/studies/LO_BASE_2020_2025_V1/reference/fifo_by_asset.csv)
- Coefficients factoriels : [A_coefficients.csv](C:/Users/Admin/GitHub/structura/artifacts/studies/LO_EXTENDED_BLOCKS_2020_2025_V1/reference/A_coefficients.csv)
- Chocs : [K_events.csv](C:/Users/Admin/GitHub/structura/artifacts/studies/LO_EXTENDED_BLOCKS_2020_2025_V1/reference/K_events.csv)
- Comparaison historique : [checks.csv](C:/Users/Admin/GitHub/structura/artifacts/studies/LO_ALL_BLOCKS_2020_2025/RESULTATS_ATTENDUS/CONTROLE_OUTIL/checks.csv)
- Sortie Studies historique, **pas l’oracle** : [resultat.json](C:/Users/Admin/GitHub/structura/artifacts/studies/LO_ALL_BLOCKS_2020_2025/RESULTATS_ATTENDUS/CONTROLE_OUTIL/resultat.json)

Le contrôle sauvegardé couvre 85 métriques sélectionnées. Il ne constitue pas une validation exhaustive des écrans, des frais annuels, des 20 lignes de P&L, de toutes les statistiques, de l’IA ou du PDF. Les contrôles manuels ci-dessus complètent ce périmètre. Les fichiers dans `artifacts/` restent locaux : copier le dossier complet pour reproduire la recette sur un autre ordinateur.
