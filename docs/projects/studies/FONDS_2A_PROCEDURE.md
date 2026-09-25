# Fonds 2A — souscriptions et rachats

## Où se trouve le dossier ?

Le dossier prêt à importer est :

```text
C:\Users\Admin\GitHub\structura\artifacts\studies\LO_FLOWS_2A_2020_2025
```

**Utiliser ce dossier directement. Il n'y a pas de ZIP à décompresser ni de script à lancer pour tester l'application.** La génération n'a pas lancé d'étude et ne constitue pas encore une validation du module.

## Procédure dans l'application

1. Ouvrir AMC → Étude → Sources de données.
2. Renseigner le chemin du dossier ci-dessus et cliquer **Scanner le dossier**. Sélectionner ce dossier racine, pas `sources` ni `RESULTATS_ATTENDUS`.
3. Vérifier le nom **Fonds 2A — long only avec souscriptions et rachats** et les paramètres du tableau ci-dessous.
4. Conserver les cours, facteurs et benchmark du dossier. Créer une **nouvelle étude**, sans écraser l'étude du premier fonds.
5. Comparer d'abord **Méta → B Attribution/réconciliation → frais → C Trading → J Risque**. Laisser la partie IA pour plus tard.
6. Conserver l'identifiant de l'étude, ses paramètres et les valeurs détaillées en cas d'écart. Les CSV de référence ne doivent pas être adaptés aux résultats de l'application.

| Paramètre | Valeur |
|---|---|
| Période | 01/01/2020 au 31/12/2025 |
| Devise | USD |
| Capital initial | 10 000 000 USD / 100 000 parts à 100 USD |
| Parts / certificats à l'émission (`params.n_certs`) | **100 000** ; ne pas saisir le nombre final dans ce champ |
| Frais de gestion | 1 % ; actif net précédent ; ACT/365 ; paiement mensuel |
| Frais de transaction | 0,05 % du montant absolu de chaque achat/vente |
| Commission de performance | **0 %** |
| HWM de commission | Sans objet ; le plus-haut de NAV sert uniquement à situer les événements |
| Dividendes | Fournis ; conservés en cash ; aucune retenue |
| Nombre de parts | Variable dans le CSV de NAV ; 110 533,57791513814 à la clôture finale |
| Valorisation | Composition finale ; ordres ajustés des splits |
| Frais de souscription/rachat, swing pricing | Aucun |
| Référentiel initial | Portefeuille du 02/01/2020, après les premiers achats |

La fréquence de commission de performance du manifeste vaut `daily` : c'est une valeur technique inactive à **0 %**, choisie pour éviter la demande d'une convention d'égalisation annuelle. Elle ne simule aucune commission. Les parts émises ou rachetées participent aux frais de gestion à partir de la période quotidienne suivante.

## Les six événements à vérifier

Les apports indiqués excluent le capital de départ de 10 M USD.

| Date | Opération | Montant USD | NAV d'exécution | Contexte |
|---|---|---:|---:|---|
| 16/06/2021 | Souscription | +2 000 000 | 111,25613242 | Nouveau plus-haut |
| 04/04/2022 | Souscription | +1 500 000 | 110,15686449 | Drawdown de −20,359 % |
| 20/01/2023 | Rachat | −3 000 000 | 106,05311706 | Avant récupération ; ventes pour financer le rachat |
| 18/04/2025 | Souscription | +1 000 000 | 138,35454969 | Récupération du plus-haut |
| 20/11/2025 | Souscription | +750 000 | 136,01826360 | Même jour que le rachat suivant |
| 20/11/2025 | Rachat | −750 000 | 136,01826360 | Flux net nul, deux événements conservés |

Les opérations utilisent la NAV de clôture **après les transactions, leurs coûts, les dividendes et la provision de gestion**. Ensuite, parts créées ou annulées = montant USD / NAV. Il n'y a donc pas de saut de NAV provoqué par le seul apport ou retrait.

Pour financer un rachat, les ventes éventuelles sont proportionnelles aux positions ; leurs frais sont supportés par le fonds avant la NAV d'exécution. Les souscriptions restent en cash jusqu'aux transactions prévues par la stratégie. Le calendrier de rééquilibrage et les cours sont ceux du premier fonds ; les quantités et résultats changent avec l'encours et l'absence de commission de performance.

## Chiffres de référence à l'écran

Les montants ci-dessous sont en USD, sauf précision. Les références exactes sont dans les CSV/JSON, sans arrondi d'affichage.

| Écran / mesure | Attendu |
|---|---:|
| Méta — NAV initiale | 100,00 |
| Méta — NAV finale | **145,30326861** |
| Méta — performance cumulée par part | **+45,30326861 %** |
| Méta — actif net final | **16 060 890,16** |
| Méta — parts finales | **110 533,57791514** |
| Méta — observations NAV / ordres | 1 566 / 1 684 |
| Flux — souscriptions cumulées hors départ | +5 250 000,00 |
| Flux — rachats cumulés | −3 750 000,00 |
| Flux — apport net hors départ | +1 500 000,00 |
| B — P&L réalisé FIFO, avant frais et dividendes | +3 768 692,58 |
| B — P&L latent, avant frais et dividendes | +644 904,55 |
| B — réalisé + latent | +4 413 597,13 |
| B — dont FX réalisé (déjà inclus dans le réalisé) | −415 927,47 |
| B — dividendes encaissés | +1 033 971,92 |
| Frais — gestion cumulée | −745 821,29 |
| Frais — transactions cumulées | −140 857,60 |
| Frais — commission de performance | 0,00 |
| B — résultat net, après frais/dividendes, hors flux investisseurs | **+4 560 890,16** |
| C — appariements FIFO clôturés | 1 484 |
| C — hit rate des appariements | 60,30997305 % |
| C — profit factor avant frais | 1,61895150 |
| C — durée médiane des appariements | 151 jours calendaires |
| J — drawdown maximal | −31,51573757 % |
| J — volatilité annualisée (échantillon, 252 observations) | 12,58197213 % |
| J — Sharpe à taux sans risque nul, 252 observations | 0,54108755 |

Les « appariements FIFO » sont des fractions de lots achetés puis vendus, pas nécessairement des positions entièrement fermées. Les références de risque et trading indiquent leurs conventions : un autre périmètre ou taux sans risque doit être rapproché avant de conclure à une erreur.

Le contrôle central est :

```text
10 000 000,00 de capital initial
+1 500 000,00 d'apports nets ultérieurs
+4 560 890,16 de résultat net
=16 060 890,16 d'actif net final
```

**La hausse de l'encours n'est pas la performance.** La performance de +45,3033 % se mesure sur la NAV par part ; les apports nets sont exclus du résultat de gestion. Le FX réalisé est une composante du P&L réalisé, à ne pas additionner une seconde fois.

| Année | NAV de fin | Performance annuelle | Apports nets USD |
|---|---:|---:|---:|
| 2020 | 102,96337273 | +2,96337273 % | 0 |
| 2021 | 136,64769557 | +32,71485961 % | +2 000 000 |
| 2022 | 103,73657600 | −24,08465026 % | +1 500 000 |
| 2023 | 119,13699061 | +14,84569397 % | −3 000 000 |
| 2024 | 115,83488880 | −2,77168476 % | 0 |
| 2025 | 145,30326861 | +25,43998627 % | +1 000 000 |

## Fichiers et limites de cette étape

À la racine, `manifest.json`, `LO_2A Def.txt`, `LO_2A timeseries.csv`, `LO_2A Data.json`, `cash_events.csv`, `dividends.json` et `market_data.json` constituent les entrées de l'application. Le manifeste comporte aussi le panier initial pour E ; les données de marché/facteurs/benchmark nécessaires aux autres blocs sont incluses.

Dans `RESULTATS_ATTENDUS` :

- `nav_daily.csv` : NAV, parts, encours, cash, provisions et pont quotidien de P&L.
- `investor_flows.csv` : les six opérations distinctes, leurs NAV, parts avant/après et contexte de marché.
- `trades.csv` : carnet brut, frais et motif, dont les ventes de financement du rachat.
- `positions_daily.csv` : toutes les positions et valorisations quotidiennes.
- `pnl_by_asset.csv` : réalisé, FX réalisé, latent, dividendes et frais par titre.
- `fifo_matches.csv` : détail des appariements clôturés.
- `annual_results.csv` et `summary.json` : résultats annuels et totaux.

Le fichier `cash_events.csv` importé contient le capital initial, les règlements de frais et les encaissements de dividendes. Les mêmes dividendes sont documentés dans `dividends.json` avec les dates et quantités éligibles : l'application rapproche les deux registres et comptabilise le revenu une seule fois. Un registre de trésorerie fourni sans ces encaissements est rejeté comme contradictoire. **Les mouvements investisseurs sont transmis à l'application par le nombre de parts quotidien**, car le lecteur actuel de `cash_events.csv` refuse les types souscription/rachat. Leur registre détaillé reste dans `RESULTATS_ATTENDUS/investor_flows.csv`. Le 20/11/2025, les deux flux opposés sont invisibles dans la seule variation nette des parts : cette recette ne prétend donc pas valider leur restitution brute dans l'application.

Le générateur et le vérificateur sont indépendants du code Studies. Le vérificateur refait la comptabilité avec des nombres décimaux à partir des cours et du carnet, contrôle les exports, l'absence de dilution et les scénarios. Les tests vérifient également la reproduction à l'identique et le rejet d'une NAV altérée ou d'une opération supprimée.

Cette étape fournit les données pour les blocs A à K, mais **les résultats indépendants du fonds 2A couvrent les mesures comptables, les flux et les mesures trading/risque listées ci-dessus**. Elle ne fournit pas encore un oracle complet de tous les scores A à K, ni de Manager Skill. Ne pas réutiliser les chiffres du premier fonds pour ces blocs. Les comparaisons Buy & Hold restent soumises aux conventions de frais et de dividendes déjà identifiées.

La commission de performance avec égalisation, plusieurs classes de parts, réinvestissement automatique des dividendes, décalage de règlement, fiscalité et long/short ne sont pas couverts par 2A.

## Régénération et vérification (usage technique uniquement)

Depuis la racine du dépôt, avec un interpréteur Python disponible :

```powershell
python scripts/studies_reference/build_flows_2a.py --output artifacts/studies/LO_FLOWS_2A_2020_2025
python scripts/studies_reference/verify_flows_2a.py artifacts/studies/LO_FLOWS_2A_2020_2025
python -m unittest discover -s scripts/studies_reference -p test_flows_2a.py -v
```

Une copie portable du générateur et du vérificateur se trouve dans `generator`. Les sources gelées se trouvent dans `sources`, avec leurs empreintes SHA-256 dans `source_hashes.json`. Aucun téléchargement ni appel à l'application n'est nécessaire. `hypotheses.json` conserve les conventions de calcul. Les fichiers volumineux sous `artifacts` restent locaux conformément au `.gitignore` du projet.

Tolérances conseillées pour la comparaison sur exports : 0,01 USD sur les montants, 10⁻⁸ sur la NAV et 10⁻⁶ sur les parts. Un écran arrondi en milliers de dollars ne permet pas de vérifier ces tolérances.
