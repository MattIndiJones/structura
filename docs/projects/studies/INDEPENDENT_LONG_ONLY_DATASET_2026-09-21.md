# Fonds fictif long only — données et référence indépendantes

Version : `LO_BASE_2020_2025_V1`, 21 septembre 2026.

## Objet et périmètre

Ce jeu permet à Philippe d'importer un historique fictif dans Studies puis de comparer les résultats avec une comptabilité calculée séparément. **Le générateur et le vérificateur n'importent aucun code de Studies.** Ils utilisent exclusivement la bibliothèque standard de Python. Les schémas d'import et la documentation Studies ont été consultés pour produire les fichiers d'échange ; aucune formule du module n'a été réutilisée.

Cette livraison produit les données, la référence et leurs contrôles internes. Elle ne lance pas Studies, ne modifie pas son code, ne peuple pas ses caches et n'effectue pas encore sa recette ou son débogage. Une NAV fournie à Studies est une donnée d'entrée : retrouver cette NAV dans l'écran ne démontre pas que le module a reconstruit sa comptabilité.

Le dossier livré est `artifacts/studies/LO_BASE_2020_2025_V1/`, accompagné de l'archive `artifacts/studies/LO_BASE_2020_2025_V1.zip`. Le dossier `artifacts/` est ignoré par Git : conserver le ZIP pour déplacer ce jeu sur une autre machine. Le ZIP contient les scripts, les données FX figées et une copie de ce document.

## Hypothèses figées

| Paramètre | Convention |
|---|---|
| Période | 01/01/2020 au 31/12/2025 inclus ; 1 566 valorisations |
| Capital initial | 10 000 000 USD, 100 000 parts de NAV 100 |
| Démarrage | 100 % cash au 01/01 ; premiers achats le 02/01/2020 |
| Univers | 20 entreprises fictives, identifiants `SYNTH_LO_01` à `SYNTH_LO_20` |
| Devises titres | USD, EUR, CHF et JPY ; cinq titres par devise |
| Gestion | Long only, quantités fractionnaires ; cash et positions jamais négatifs |
| Allocation | Cible mensuelle de 84 % investis, deux exclusions tournantes ; ajustements tactiques certains 20 du mois |
| Calendrier | Du lundi au vendredi, y compris les jours fériés des marchés réels : bourses fictives |
| Cash | Centralisé en USD, non rémunéré ; conversion immédiate des achats, ventes et dividendes |
| Exécution | Prix de clôture synthétique et FX de référence disponible ; règlement immédiat |
| Transactions | 5 points de base du notionnel absolu ; pas de spread FX supplémentaire ni de slippage |
| Gestion | 1 % annuel sur l'actif net précédent, ACT/365 fixe, paiement mensuel |
| Performance | 15 %, sans hurdle ; provision réversible et cristallisation annuelle |
| HWM | 100 USD au départ ; par part, permanent ; mis à jour après frais à la cristallisation |
| Flux investisseurs | Aucun après le financement initial ; nombre de parts constant |
| Autres frais et fiscalité | Dépositaire, administration, retenues fiscales et impôts à zéro |
| Opérations sur titres | Dividendes trimestriels, deux splits et un regroupement d'actions |
| Précision | Calculs sans arrondi quotidien au centime ; décimales conservées dans les CSV |

Les frais de gestion sont constatés pour le nombre de jours calendaires écoulés depuis la valorisation précédente, y compris week-ends et années bissextiles, avec dénominateur 365. Le premier jour n'a pas de frais. Cela représente 2 191 jours écoulés. Les paiements mensuels et la cristallisation annuelle ont lieu à la dernière valorisation de la période. Si une fin de mois/année tombe un week-end, les jours suivants cette dernière valorisation sont provisionnés lors de la prochaine valorisation et rattachés à cette nouvelle période. Ainsi les arrêtés annuels 2022 et 2023 sont respectivement les 30 et 29 décembre. Ce n'est pas une convention de clôture comptable quotidienne au 31 décembre non ouvré.

Les trajectoires combinent un facteur commun, cinq facteurs sectoriels et des chocs propres aux titres, avec une graine fixe `20200921`. Les régimes comprennent une baisse rapide en février-mars 2020, une reprise, une année 2022 défavorable et des phases ultérieures de reprise. Les poids cibles sont déterministes et ne consultent pas les prix futurs. Il s'agit d'un scénario de recette, pas d'un backtest d'une stratégie réelle ni d'une calibration statistique aux marchés historiques.

## FX réel et sens des conversions

Source unique : [historique des cours de référence de la BCE](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html). Le ZIP téléchargé est conservé intact dans `sources/`, avec sa provenance et son SHA-256. Les cours locaux existants USD/EUR et CHF/EUR ont été vérifiés ; la version livrée utilise la BCE pour toutes les devises afin de disposer d'un seul référentiel cohérent, incluant JPY.

Les cotations BCE sont exprimées en unités de devise pour un euro. La colonne `usd_per_local` signifie toujours **USD pour une unité de devise locale** :

```text
USD par USD = 1
USD par EUR = cotation BCE USD
USD par CHF = cotation BCE USD / cotation BCE CHF
USD par JPY = cotation BCE USD / cotation BCE JPY
Valeur USD = quantité × prix local × usd_per_local
```

Les dates de publication sont conservées. Pour chaque valorisation, seul le dernier cours publié à cette date ou avant est retenu ; ancienneté maximale de sept jours calendaires. Aucun remplissage par une observation future. Le sous-ensemble utilisé est limité au 20/12/2019–31/12/2025, même si l'archive brute contient d'autres dates. Aucun accès réseau n'est nécessaire pour régénérer le jeu.

Les références BCE servent ici de proxy de valorisation et, par hypothèse de simulation, de conversion des transactions. Ce ne sont pas des prix d'exécution historiques bid/ask. Les prix des actions sont entièrement fictifs ; seuls les changes sont historiques.

## Ordre exact des opérations et frais

À chaque date : appliquer les splits aux positions d'ouverture, calculer les cours, encaisser les dividendes sur les quantités d'ouverture ajustées, exécuter les ventes puis les achats au cours de clôture, constater les frais, calculer la NAV, régler les provisions échues. Les frais de gestion utilisent la NAV nette précédente ; leur calcul peut donc être effectué avant les transactions sans changer cette assiette.

Notations : `N` nombre de parts, `H` HWM courant par part, `G` titres au marché + cash avant règlement des frais, `Lmg` provision de gestion cumulée non réglée.

```text
Charge de gestion du jour = actif net précédent × 1 % × jours écoulés / 365
Actif avant commission de performance = G − Lmg
Provision de performance cible = 15 % × max(0, actif avant performance − N × H)
Charge de performance du jour = provision cible − provision en début de journée
Actif net = G − Lmg − provision de performance cible
NAV nette = actif net / N
```

La charge de performance peut être négative : il s'agit d'une reprise de provision, pas du remboursement de frais déjà cristallisés. À la cristallisation, la provision est payée, puis remise à zéro et `H = max(H précédent, NAV nette après frais)`. Un paiement diminue simultanément le cash et la dette de frais du même montant : **il ne diminue pas la NAV une seconde fois**. Les frais de gestion suivent le même principe de règlement.

Exemple par part : actif avant performance 120, HWM 100 → provision 3, NAV nette 117. Si l'actif retombe à 110 avant cristallisation, la provision devient 1,50 et une reprise de 1,50 est constatée. Si 3 ont été cristallisés à 120, le nouveau HWM est 117 ; une période ultérieure sous 117 ne déclenche pas de nouveaux frais de performance.

## Dividendes, splits et attribution

Dividendes : premier jour de semaine à partir du 16 mars, juin, septembre et décembre. Le montant par action est fixé à 0,35 % à 0,47 % du cours précédent ajusté du split, selon le titre. Les dividendes sont détachés du prix, encaissés à la date ex-dividende et convertis en USD ; pas de créance différée ni de retenue fiscale.

Splits : `SYNTH_LO_01` 2 pour 1 le 15/06/2021 ; `SYNTH_LO_08` 3 pour 1 le 15/09/2023 ; `SYNTH_LO_16` 1 pour 5 le 15/03/2024. Les quantités sont multipliées par le ratio, les prix unitaires et coûts des lots divisés par ce ratio. Aucun cash n'est créé.

Les prix nus d'exécution, les indices de rendement total et les événements sont distincts. L'indice total return local inclut le dividende une seule fois : `TR(t) / TR(t−1) = ratio_split × (prix(t) + dividende(t)) / prix(t−1)`.

Le rapprochement quotidien est :

```text
Variation d'actif net = P&L prix + P&L FX + dividendes
                      − frais de transaction − charge de gestion − charge de performance
```

L'effet prix utilise les positions d'ouverture ajustées du split et le FX courant ; l'effet change utilise le prix précédent et la variation du FX. Le terme croisé prix/change est donc attribué à l'effet prix. Les opérations sont à la clôture ; elles n'ont pas de P&L intrajournalier.

La référence FIFO fournit les lots appariés et les résultats réalisés/latents par titre, hors frais. Les dividendes sont ajoutés séparément. La somme réalisé + latent + dividendes rejoint le gain de NAV augmenté des frais. Les totaux de fees ne constituent pas à eux seuls la performance d'un portefeuille contrefactuel sans frais : un tel portefeuille devrait être simulé séparément.

## Fichiers et dictionnaire de lecture

Tous les CSV sont UTF-8, séparateur virgule, point décimal ; dates ISO sauf le CSV NAV d'import Studies. Les montants suffixés `_usd` sont en USD, les colonnes `_local` dans la devise de la ligne. Les pourcentages suffixés `_decimal` et les poids sont des fractions : `0.15` = 15 %. Les identifiants fictifs ne doivent pas être remplacés par ceux de titres réels.

| Fichier dans le dossier livré | Contenu et clé |
|---|---|
| `assumptions.json` | Conventions figées ; descriptif de cette version, pas un fichier de paramétrage lu par le générateur |
| `inputs/assets.csv` | Référentiel des 20 titres ; clé `asset_id` |
| `inputs/trades.csv` | 1 540 transactions originales ; clé `trade_id`, achats positifs, ventes négatives ; prix, FX, notionnel, frais et NAV nette de clôture du fonds le même jour |
| `inputs/prices_daily.csv` | 31 320 cours ; clé `(date, asset_id)` ; prix nus, FX, dividende, split et indice total return local |
| `inputs/fx_daily.csv` | 6 264 lignes ; clé `(date, currency)` ; quote normalisée, date source et ancienneté |
| `inputs/corporate_actions.csv` | 480 dividendes annoncés et trois événements de split ; clé `(date, asset_id, type)` |
| `inputs/cash_events.csv` | Financement initial, dividendes encaissés, règlements de frais ; les achats/ventes sont dans `trades.csv`, ne pas les compter deux fois |
| `reference/positions_daily.csv` | Composition de clôture de chaque titre, y compris les positions nulles ; cash et dettes de frais dans `nav_daily.csv` |
| `reference/nav_daily.csv` | NAV nette, actif net, titres, cash, provisions, charges, paiements, HWM avant/après, P&L et jours de frais |
| `reference/monthly_results.csv` | 72 périodes ; NAV initiale/finale, rendement composé, charges, paiements et P&L |
| `reference/annual_results.csv` | Six périodes annuelles, mêmes conventions |
| `reference/summary.csv` et `.json` | Principaux indicateurs sur toute la période |
| `reference/fifo_matches.csv` | 1 341 appariements FIFO ; quantités dans les unités de la date de vente, prix/FX hors frais |
| `reference/fifo_by_asset.csv` | Quantités finales, coûts résiduels, P&L réalisé/latent, dividendes par titre |
| `reference/verification.json` | Résultats de la reconstruction indépendante en arithmétique Decimal |
| `reference/reproduction.json` | Régénération identique et détection de trois altérations volontaires |
| `checksums.sha256` | Empreinte de chaque fichier du package, hors fichier d'empreintes lui-même |

`fund_closing_nav_usd` dans les trades est la NAV de fin de journée **après tous les trades et frais** ; ce n'est pas une NAV immédiatement après chaque transaction. `positions_daily.csv` et `nav_daily.csv` se joignent sur `date` pour obtenir la composition complète, cash et dettes inclus. Aucune NAV à inventer entre les dates publiées.

## Résultats de référence

| Année | NAV nette de clôture | Rendement net | Performance fees payées, USD | HWM après clôture |
|---|---:|---:|---:|---:|
| 2020 | 102,546460 | +2,5465 % | 44 937,52 | 102,546460 |
| 2021 | 131,288967 | +28,0288 % | 507 220,73 | 131,288967 |
| 2022 | 99,221101 | −24,4254 % | 0,00 | 131,288967 |
| 2023 | 113,924092 | +14,8184 % | 0,00 | 131,288967 |
| 2024 | 110,766476 | −2,7717 % | 0,00 | 131,288967 |
| 2025 | 138,065178 | +24,6453 % | 119 580,19 | 138,065178 |

Au 31/12/2025 : actif net **13 806 517,80 USD**, dont titres **11 773 517,57 USD** et cash **2 033 000,23 USD** ; provisions de frais soldées. Performance cumulée **+38,065178 %**, CAGR calendaire **5,524350 %**, drawdown maximal **−31,700488 %**. Frais de gestion cumulés **660 069,40 USD**, performance **671 738,44 USD**, transactions **124 621,11 USD**, dividendes **917 678,53 USD**.

Le rendement annuel est `NAV fin / NAV dernière valorisation précédente − 1`. CAGR calendaire : `(NAV fin / NAV début)^(365,25 / jours écoulés) − 1`. La version annualisée sur 252 observations est aussi fournie et diffère, car le calendrier synthétique comprend tous les jours de semaine. Volatilité : écart-type échantillon des rendements simples, multiplié par racine de 252. Sharpe et Sortino : moyenne quotidienne annualisée, taux sans risque nul ; downside calculé sur toutes les observations avec cible zéro. Calmar : CAGR calendaire divisé par la valeur absolue du drawdown maximal. Comparer des conventions identiques, pas seulement des noms de ratios.

Les résidus proches de `1e-12` dans les sommes CSV sont des effets d'arithmétique flottante ; ils ne représentent pas des paiements négatifs effectifs. Les données restent non arrondies pour les comparaisons.

## Import dans Studies : premier passage

1. Ouvrir le dossier `studies_import/` dans le sélecteur de dossier Studies, avec les droits habituels d'accès. Utiliser `manifest.json` et vérifier la date d'arrêté au 31/12/2025, devise USD et 100 000 parts.
2. Les trois fichiers sélectionnés sont `LO_BASE Def.txt` (composition finale), `LO_BASE timeseries.csv` (NAV) et `LO_BASE Data.json` (carnet complet). Les taux dans le manifeste sont exprimés en pourcentage : gestion `1`, performance `15`, transaction `0.05`.
3. Conserver le mode strict et **le panier initial vide** : le fonds débute en cash et tous les achats initiaux sont déjà dans le carnet. Injecter en plus les mêmes titres comme panier initial doublerait l'exposition de départ.
4. Le manifeste demande B, C, D et J pour le premier passage. E, H, I, A, F et K sont désactivés : ce jeu ne fournit pas de référence factorielle, de benchmark synthétique ou de score de talent. J peut demander un benchmark réel pour ses sous-analyses ; celles-ci ne sont pas couvertes par cette référence. Aucun score global attendu n'est inventé.
5. Comparer d'abord identifiants/nombre d'ordres, quantité finale par titre, marks, P&L FIFO hors frais, cash, rendement et drawdown. Puis examiner les écarts avec le grand livre de référence. Conserver les résultats et avertissements de Studies pour la phase ultérieure de diagnostic.

Le carnet JSON d'import contient **toutes les transactions**, mais exprimées dans les unités du 31/12/2025 : quantités multipliées par les splits ultérieurs de la période, prix divisés par ces mêmes facteurs. Chaque notionnel et chaque FX est conservé. Ce retraitement est documenté pour rendre l'import exploitable sans demander à une source de marché réelle les splits d'identifiants fictifs. Les CSV originaux restent en unités de leur date : utiliser ceux-ci pour un futur test du traitement natif des splits. **Ne pas appliquer une deuxième fois les splits au JSON retraité.** Cette variante d'import vise l'arrêté final ; pour un arrêté plus ancien, préparer un export exprimé dans les unités de cet arrêté.

Le schéma actuel du carnet ne transporte pas les dividendes, les frais effectivement payés, ni toute la politique de cristallisation. Ces éléments sont livrés séparément. Un écart de rapprochement avec la NAV peut donc révéler une limite de prise en charge, pas une erreur du jeu. Les taux seuls du manifeste ne suffisent pas à imposer toute la convention HWM de cette référence. Le module n'a pas été exécuté pour valider ce premier passage.

## Séries de marché complémentaires

`market_import/total_return/` contient vingt JSON `{date, close}` pour les rendements totaux locaux, rebasés au prix terminal. `market_import/execution_price/` contient vingt JSON de cours nus ajustés uniquement des splits jusqu'à l'arrêté final. Les deux variantes portent les mêmes identifiants, mais ont des usages différents.

L'upload manuel actuel de prix conserve une seule colonne `close`. **Ne pas charger successivement les deux variantes sous la même clé : la seconde écraserait la première.** Il ne suffit pas non plus à transporter automatiquement la devise et les deux bases de prix nécessaires à tous les blocs. C'est pourquoi H et I restent désactivés dans le manifeste fourni. Le jeu complet nécessaire à une intégration ultérieure est dans `inputs/prices_daily.csv` et `inputs/fx_daily.csv` ; aucun de ces fichiers n'a été installé dans les caches partagés.

Les identifiants `SYNTH_*` sont volontairement fictifs. Une récupération Yahoo ne peut pas fournir leurs cours : un avertissement de donnée indisponible doit être conservé. La prise en charge de ces séries pour les blocs supplémentaires sera traitée lors du test utilisateur et du diagnostic convenu, sans substituer des historiques réels aux prix fictifs.

## Vérification et reproduction

Depuis le dossier décompressé, avec Python 3.11 ou ultérieur et sans aucune installation de dépendance :

```powershell
python generator/generate.py
python generator/verify.py
python generator/check_reproduction.py
python generator/package.py
```

`generate.py` lit uniquement le ZIP BCE figé et recrée les fichiers. Les paramètres économiques de cette version sont définis dans le script et décrits dans `assumptions.json`. Pour un nouveau scénario, copier le dossier sous un nouvel identifiant avant de changer le script ; ne pas écraser la référence acceptée.

`verify.py` relit les CSV sérialisés et reconstruit les quantités, les lots, le cash, les frais et le HWM en Decimal. Il vérifie les identifiants, calendriers, prix/FX, dividendes, splits, NAV quotidienne, agrégats mensuels/annuels, indicateurs, FIFO et exports. Il ne réutilise pas les fonctions du générateur. Le contrôle livré passe **278 518 comparaisons numériques**, avec une tolérance monétaire de **0,00001 USD** et un écart maximal observé d'environ **9,24 × 10⁻⁹** parmi les comparaisons. Ce nombre est celui des assertions, pas celui de scénarios indépendants.

`check_reproduction.py` travaille exclusivement dans un dossier temporaire : régénération identique octet par octet, puis trois altérations volontaires — FX de trade JPY, cash final, HWM annuel — qui doivent toutes faire échouer le vérificateur. Cela contrôle le jeu produit ; ce ne sont pas des tests de non-régression de Studies.

`package.py` met à jour les empreintes et produit le ZIP dans le dossier parent. L'empreinte du ZIP lui-même est écrite à côté. Les fichiers générés n'utilisent aucun secret, aucune base utilisateur et aucun cache applicatif.

## Suite convenue

Philippe teste ce premier fonds et compare aux fichiers de référence. Le diagnostic d'écarts et les modifications éventuelles de Studies interviennent ensuite. Le deuxième scénario ajoutera les souscriptions et rachats avec une convention explicite de traitement des investisseurs et d'égalisation ; le long/short viendra dans une version distincte, avec emprunt de titres, financement et traitement des dividendes courts. La suite de non-régression du module sera construite après ces validations, à partir des références acceptées.
