# Tester tous les blocs avec un seul dossier

Le dossier prêt à utiliser est **LO_ALL_BLOCKS_2020_2025**. Il est déjà décompressé et contient tous les inputs. Cette procédure remplace celle du ZIP et de l’import E séparé.

## Procédure dans l’outil

1. **Redémarrer le backend une fois**, puis actualiser la page avec Ctrl+F5. La prise en charge du fichier de marché a été ajoutée au moteur ; une instance déjà ouverte ne la connaît pas.
2. Ouvrir **AMC → Étude**, puis la configuration, section **Sources**. Choisir la saisie libre du dossier si le raccourci UTI est sélectionné.
3. Dans **Chemin du dossier ISIN**, coller :

   ```text
   C:\Users\Admin\GitHub\structura\artifacts\studies\LO_ALL_BLOCKS_2020_2025
   ```

4. Cliquer **Scanner le dossier**. Le manifeste renseigne les fichiers, frais, dividendes, facteurs, benchmark et les onze blocs A à K. Ne pas remplacer le benchmark synthétique par un ETF réel.
5. Cliquer **Lancer l’étude**. Le calcul complet a pris environ une minute lors de la vérification. Consulter ensuite les onglets ; **G est déjà calculé**.

Il n’y a ni ZIP à importer, ni script à lancer, ni cours à télécharger. Si le projet est déplacé sur un autre ordinateur, copier ce dossier entier et utiliser son nouveau chemin dans l’application.

## Repères à vérifier après le scan

| Champ | Valeur |
|---|---|
| Devise et arrêté | USD — 31/12/2025 |
| Gestion | 1 % ; NAV précédente ; ACT/365 |
| Performance | 15 % ; cristallisation annuelle ; HWM |
| Transactions | 0,05 % |
| Dividendes du fonds | Fournis, conservés en cash, pas de réinvestissement automatique |
| Valorisation | Relevé de composition à la même date |
| Carnet | Déjà ajusté des splits |
| Facteurs | Developed_5F_MOM ; Mkt-RF, SMB, HML, RMW, CMA, MOM |
| Benchmark | Personnalisé : SYNTH_BENCH20_USD |
| Fenêtre glissante | 60 observations |
| Panier de référence E / G | 18 titres au 02/01/2020 |
| Données de marché du dossier | market_data.json |

Le fonds commence le **01/01/2020 en cash**, avec une NAV de 100. Ses premiers achats sont exécutés le 02/01/2020. E et G utilisent la composition de fin de cette deuxième journée : NAV 99,9552614247, 18 actions et **15,9647 % de cash net**. Ce panier n’est pas injecté dans le FIFO : les achats figurent déjà dans le carnet. Les autres blocs conservent la période complète du fonds.

## Premiers chiffres à comparer

| Onglet | Résultat attendu à l’affichage |
|---|---|
| Méta | 1 566 NAV ; 1 540 ordres ; NAV finale 138,065178 ; performance depuis le 01/01/2020 : +38,065178 % |
| B | P&L prix 4 345 268,22 USD ; dividendes 917 678,53 USD ; rapprochement NAV : 0 bp |
| C | 1 341 appariements FIFO ; taux gagnant 59,1 % ; profit factor 1,72 ; médiane 151 jours |
| E | NAV passive 151,99 ; performance passive +52,06 % ; fonds sur la même période +38,13 % ; écart −13,93 points |
| G | Panier passif +52,06 % ; benchmark +65,60 % ; retour actif −13,54 points |
| G — effets | Allocation −10,25 ; sélection −4,08 ; interaction +0,79 point |
| H | 1 540 ordres analysés ; score moyen environ 0,5083 |
| I | 782 achats ; score 43 |
| J | Score 56 ; 36 épisodes ; drawdown maximal −31,70 % |
| Manager Skill | Score 53 ; VAG inclus à 20 %, sous-score 44,2 |

Tous les résultats indépendants détaillés sont dans **RESULTATS_ATTENDUS/expected_by_screen.csv** et **summary.json**. Ils sont conservés comme références et ne sont jamais lus par le moteur pour calculer l’étude.

**CONTROLE_OUTIL/resultat.json** contient la sortie du moteur vérifiée après assemblage. **CONTROLE_OUTIL/checks.csv** compare 85 indicateurs à la référence indépendante. Il faut distinguer cette sortie de contrôle des résultats théoriques indépendants.

Les trois écarts antérieurs sont corrigés en méthode 2.4 :

- F : écart de performance **19,42 points**, calculé sans arrondis intermédiaires.
- J : information ratio **−1,074**, avec le premier rendement du benchmark conservé.
- J : **36 épisodes** au total ; seuls les cinq plus profonds sont détaillés. Durée moyenne : **58,3 jours calendaires** (41,5 observations sous le plus-haut). Score drawdown : **50**, score J : **56**.

Le panier E est calculé en rendement total avec dividendes réinvestis localement, alors que le **fonds géré** conserve ses dividendes en cash. E reste une comparaison panier passif brut / fonds net : l’écart ne mesure pas uniquement les décisions du gérant. G est une attribution **statique** de ce panier ; son benchmark est initialisé au 02/01/2020 pour comparer la même période. Le benchmark des autres blocs commence au 01/01/2020.

La méthode descriptive 2.4 inclut le VAG dans le score et distingue couverture documentaire et portée indicative de G. Le ratio FX réalisé est désormais −7,84 % du P&L réalisé signé. Voir [les corrections méthodologiques](STUDIES_METHODOLOGY_2026-09-21.md).

## Contenu et traçabilité

Le dossier comporte : manifeste de paramétrage, relevé final, NAV quotidiennes, carnet complet, registre de trésorerie, événements de dividendes et fichier de marché autonome. Ce dernier contient les cours hors dividendes pour le timing et les prix d’exécution, les indices de rendement total pour les comparaisons, les splits, le FX historique, les facteurs, le benchmark et sa ventilation sectorielle.

Les données fictives et les résultats de référence proviennent du générateur indépendant antérieur. `setup_unified.py` les assemble sans importer le moteur Studies. Les données de marché sont limitées à cette étude, identifiées par leur empreinte et ne modifient pas les caches partagés. Une source locale absente ne déclenche pas de recherche de faux titres sur Internet.

Pour les développeurs uniquement, depuis la racine du dépôt :

```powershell
.venv/Scripts/python.exe scripts/studies_reference/setup_unified.py
.venv/Scripts/python.exe scripts/studies_reference/verify_unified.py
.venv/Scripts/python.exe -m pytest backend/tests/test_studies_market_bundle.py backend/tests/test_amc_studies.py backend/tests/test_studies_reconciliation.py backend/tests/test_studies_dividends.py -q
```

La vérification complète utilise le scanner et le moteur standards, sans remplacement des chargeurs de marché, avec les accès réseau interdits. Elle exige tous les blocs disponibles et les 85 indicateurs conformes aux tolérances documentées. La validation visuelle dans le navigateur utilisateur reste à effectuer.
