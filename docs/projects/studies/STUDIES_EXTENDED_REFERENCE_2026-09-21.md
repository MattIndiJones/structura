# Studies — jeu de référence étendu A à K

> Procédure remplacée : utiliser désormais le [setup complet en un seul dossier](STUDIES_SETUP_COMPLET_2026-09-21.md). Les instructions d’import E ci-dessous décrivent l’ancien banc technique.

## Livraison et limites de la validation

Le package `artifacts/studies/LO_EXTENDED_BLOCKS_2020_2025_V1` complète le fonds long only validé. Son ZIP permet de le déplacer sur une autre machine ; `artifacts/` n’est pas versionné. Les générateurs et contrôles sont versionnés dans `scripts/studies_reference/` et copiés dans le ZIP.

Le fonds original n’est pas modifié : 1 566 NAV, 1 540 transactions, NAV finale 138,065178031842 USD. Les sources copiées, facteurs et résultats sont munis d’empreintes SHA-256.

Deux opérations sont distinctes :

1. **Référence indépendante** : scripts sans import de Studies, calculs numériques avec NumPy/Pandas/SciPy et vérification séparée des CSV en Decimal. Les conventions et formats publics du module ont été consultés, mais ses fonctions ne produisent aucune valeur attendue. Les agrégats C/D utilisent les appariements FIFO de la référence V1 déjà reconstruite indépendamment.
2. **Comparaison du module** : un autre script importe Studies comme système testé et lui fournit les cours, changes, facteurs et benchmark en mémoire. Aucun moteur applicatif n’a été modifié, aucun serveur lancé ou redémarré, aucun cache partagé remplacé. Les téléchargements sont désactivés. Les résultats observés sont exclusivement dans `comparison/`, séparés de `reference/`.

Le banc mesure **85 comparaisons**, dont **82 conformes** aux tolérances d’arrondi déclarées et trois écarts conservés. Il ne valide pas l’import de tous ces types de données dans l’interface actuelle : celle-ci ne sait pas encore charger un package complet de prix nus/TR, devises, benchmark, secteurs et facteurs personnalisés en une opération.

## Tester d’abord le bloc E dans l’interface

Le fonds commence le 01/01/2020 en cash. Les 18 achats initiaux sont le 02/01/2020. **Ne pas ajouter ces mêmes titres comme stock initial au carnet complet** : cela risquerait de doubler les positions et les dividendes éligibles.

Un dossier séparé `studies_import_E_ONLY` est fourni pour E seul, avec la première NAV au **02/01/2020 après les achats et frais du jour**. Il comprend une TS de 18 titres, 100 000 parts et un cash résiduel net de la dette de gestion déjà constatée. Le fichier de composition ne fournit que les métadonnées USD ; il ne prétend pas décrire un portefeuille final fictif. Les autres blocs sont désactivés dans ce dossier.

Les cours d’import E sont des **proxies total return en USD**, sous les identifiants distincts `SYNTH_E_USD_*`. Ils combinent exactement les cours fictifs, les dividendes réinvestis localement et le FX historique. Ainsi, E ne recherche pas de faux tickers sur Yahoo et ne reconvertit pas les devises une deuxième fois. Ces séries servent exclusivement au rendement passif E, jamais au FIFO ni au timing. Les données économiques originales en devises locales sont conservées dans `inputs/termsheet_economic.json`.

Depuis PowerShell à la racine du dépôt, charger les 18 séries E une seule fois :

```powershell
.venv/Scripts/python.exe scripts/studies_reference/install_e_prices.py artifacts/studies/LO_EXTENDED_BLOCKS_2020_2025_V1 --store backend/data/underlying_prices
```

Ce chargement n’a pas été exécuté pendant la génération. Il ne crée que les identifiants réservés E : un fichier identique est laissé en place, une collision avec un contenu différent interrompt l’opération avant toute écriture. Aucun cours existant n’est remplacé. Le script requiert Pandas et le support Parquet, disponibles dans l’environnement backend.

Ensuite :

1. Ouvrir **Configuration & données**.
2. Scanner `artifacts/studies/LO_EXTENDED_BLOCKS_2020_2025_V1/studies_import_E_ONLY`.
3. Vérifier : USD, arrêté 31/12/2025, 100 000 parts, 18 positions TS, **E seul activé**.
4. Lancer, puis ouvrir **E — Référentiel inertiel**.

| Champ | Résultat attendu |
|---|---:|
| Date initiale | 02/01/2020 |
| NAV initiale | 99,955261424658 |
| Actif net initial | 9 995 526,14 USD |
| Cash initial net des dettes déjà constatées | 1 595 756,28 USD |
| Poids cash | 15,9647 % |
| NAV passive finale, dividendes réinvestis | **151,99** |
| Performance passive | **52,06 %** |
| NAV réelle finale | **138,065178** |
| Performance réelle depuis le 02/01 | **38,13 %** |
| Écart réel − passif | **−13,93 points** |

La performance réelle diffère des 38,0652 % du dossier original parce que la date initiale change. Le portefeuille passif est brut de frais futurs et le fonds réel est net : `comparable_costs=false`. E doit donc rester exclu du score Manager Skill dans cette comparaison.

La variante passive **dividendes conservés en cash USD** termine à **148,555647** de NAV. Elle figure dans `reference/E_daily.csv` pour isoler l’effet de la politique de dividendes ; ce n’est pas la convention actuellement calculée par E. Le passif réinvesti reçoit les dividendes proportionnels à ses propres positions, sans réutiliser les paiements du fonds activement géré.

## Autres données et résultats fournis

| Bloc | Référence | Convention et usage |
|---|---|---|
| A | `A_coefficients.csv`, `A_aligned_data.csv`, `A_rolling60.csv` | FF5+MOM Developed figé, rendements USD, OLS, covariance HAC 5 retards, p-values Student ; 1 565 rendements |
| B | Copie de la référence V1 dans `sources/original/reference` | Réalisé/latent/dividendes déjà validés ; pas de nouvelle comptabilité du fonds |
| C | `summary.json`, `expected_by_screen.csv` | 1 341 appariements ; hit ratio 59,1350 % ; profit factor 1,723768 ; détention médiane 151 jours |
| D | `D_classification.csv` | 18 gagnants de conviction et 2 perdants de conviction ; cash exclu ; seuils 4 % / 180 jours |
| E | `E_daily.csv`, TS économique et manifeste séparé | Départ après les achats initiaux ; cash explicite ; deux politiques de dividendes |
| F | `F_daily.csv` et résumé | Réplicant ajusté dans l’échantillon, RF + facteurs × bêtas ; score 38 |
| G | `G_sector_attribution.csv` | Brinson statique sur la TS du 02/01 ; cinq secteurs et cash ; effets totalisant exactement l’écart au benchmark sectoriel |
| H | `H_by_trade.csv` | Prix nus ajustés des splits, fenêtres ±30 jours calendaires ; 1 540 trades analysables ; moyenne 0,5083245 |
| I | `I_by_purchase_horizon.csv` | Rendements totaux USD à 21/63/126/252 observations, dates communes, horizons incomplets exclus ; score 43 |
| J | `J_daily_drawdown.csv`, `J_drawdown_episodes.csv`, résumé | RF nul pour Sharpe/Sortino descriptifs ; drawdown −31,700488 % ; score 55 selon la politique des sous-scores |
| K | `K_events.csv` | Cinq fenêtres applicables ; volumes signés, volumes bruts et activité rapportée aux jours calendaires hors événements |
| Manager Skill | `summary.json` | Score indépendant 55 ; cinq composantes, 80 % des poids de base disponibles, E exclu |

Les formules de scores reprennent les **conventions de notation explicites** du produit, implémentées séparément ; ce n’est pas une validation économique ou statistique de ces conventions. Les métriques de référence conservent leur précision jusqu’aux scores des composantes, tandis que certains calculs Studies utilisent des valeurs déjà arrondies.

Le benchmark `SYNTH_BENCH20_USD` place un montant identique dans chacun des vingt titres au 01/01, conserve ces positions avec réinvestissement local des dividendes et convertit les valeurs en USD. Ses poids dérivent ensuite avec les cours : aucune sélection a posteriori ni rééquilibrage quotidien implicite. Il représente l’univers fictif, pas un indice réel négociable.

Pour **G seulement**, le benchmark équipondéré est réinitialisé au 02/01, pour partager l’instant initial de la TS. `inputs/brinson_benchmark.csv` donne les poids et rendements sectoriels de cette convention. Ne pas lui substituer le benchmark global du 01/01 : ses poids ont déjà dérivé au 02/01. G explique le panier initial conservé, pas l’ensemble des décisions de gestion du fonds.

Les facteurs sont une copie figée du fichier local `Developed_5F_MOM.parquet`, limitée à 2020–2025. Leur provenance et l’empreinte du fichier d’origine sont dans `sources/factor_provenance.json`. Aucune nouvelle certification externe du téléchargement historique n’a été effectuée. Le FX reste celui du jeu BCE figé initial.

## Écarts conservés pour le diagnostic

| Bloc | Référence indépendante | Studies | Lecture |
|---|---:|---:|---|
| F — écart de performance | 19,4205078 points | 19,43 points | Arrondis des bêtas en entrée de F puis soustraction des performances déjà arrondies ; la référence à pleine précision s’affiche à 19,42 |
| J — ratio d’information | −1,074109 | −1,073 | Le benchmark est réindexé sur les dates des rendements avant son `pct_change` : le premier rendement comparable est perdu |
| J — nombre total de drawdowns | **36** | **5** | Le module renvoie les cinq épisodes les plus profonds puis utilise leur longueur comme compteur global |

La référence de notation drawdown utilise les cinq pires épisodes, conformément à la politique existante, mais les distingue du **nombre total**. Les durées affichées comme « jours » sont des **nombres d’observations**, pas des jours calendaires. Le score global de risque reste 55 dans ce scénario.

Ces écarts sont listés dans `comparison/checks.csv` avec leurs valeurs et tolérances ; ils ne sont ni masqués ni corrigés dans les données. Le contenu des narratifs automatiques et les libellés qualitatifs ne sont pas couverts par les 85 comparaisons.

## Reproduction et petits cas

Le générateur exige Python, NumPy, Pandas, SciPy et, pour le seul amorçage des facteurs, un lecteur Parquet. L’environnement `.venv` du dépôt les possède. Le runtime documentaire fourni ne possède pas SciPy, d’où l’usage de cet environnement pour cette référence numérique, sans import applicatif.

Depuis la racine du dépôt :

```powershell
.venv/Scripts/python.exe scripts/studies_reference/build_extended.py --output artifacts/studies/LO_EXTENDED_BLOCKS_2020_2025_V1
.venv/Scripts/python.exe scripts/studies_reference/verify_extended.py artifacts/studies/LO_EXTENDED_BLOCKS_2020_2025_V1
.venv/Scripts/python.exe scripts/studies_reference/test_reference.py
```

Le vérificateur relit les données sérialisées et contrôle notamment les empreintes, la NAV passive en Decimal, les poids initiaux avec cash, l’identité Brinson, les horizons I et les volumes K. Il n’importe pas le générateur. Les petits cas couvrent prix constants, change seul, détachement du dividende, réinvestissement, split, portefeuille sans trade et bons/mauvais achats/ventes de timing ; ils sont dans `small_cases/` et accompagnés de dix tests unitaires du générateur. Deux tests supplémentaires vérifient dans des dossiers temporaires l’idempotence du chargeur E et son refus d’écraser des données différentes. Ce ne sont pas de nouveaux tests de l’application Studies.

Pour répéter la comparaison, **séparément de la génération** :

```powershell
.venv/Scripts/python.exe scripts/studies_reference/compare_studies.py artifacts/studies/LO_EXTENDED_BLOCKS_2020_2025_V1
.venv/Scripts/python.exe scripts/studies_reference/report_comparison.py artifacts/studies/LO_EXTENDED_BLOCKS_2020_2025_V1
```

Le banc mémorise les résultats de la fonction de lecture FX originale sur les séries figées, afin d’éviter de refaire les mêmes recherches des millions de fois dans I. Il ne remplace pas les formules d’analyse. Les résultats observés ne sont jamais utilisés pour ajuster les valeurs attendues.

## Étape suivante

Après recette E dans l’interface, décider du traitement des trois écarts, puis prévoir l’import explicite d’un package de marchés complet pour A/F/G/H/I/J/K. Le banc isolé prouve qu’on peut alimenter ces calculs avec les données fournies ; il ne crée pas ce parcours d’import dans l’application. Les souscriptions/rachats et le long/short restent des scénarios ultérieurs distincts.
