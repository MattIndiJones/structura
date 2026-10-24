# C17 — Surfaces, calibration et diagnostics

Livraison locale du 21 octobre 2026, sans commit ni push. Les cinq constats
M07-01, M07-03, M07-04, M07-05 et M07-06 sont traités sur le périmètre décrit
ci-dessous. Les contrôles ciblés des dépendances C11, C14, C10, C06, C15 et C16
sont conservés. Cette livraison ne qualifie pas tous les modèles en production.

## Décision et résultat métier

Philippe a fixé les erreurs maximales à **5 pb du nominal pour les vanilles** et
**10 pb pour les digitales**, sur les points de contrôle publiés. Ces seuils
sont distincts des 10 pb du panel de barrières C16.

Un solveur convergé n'est plus assimilé à une calibration qualifiée. Le résultat
doit converger, respecter les deux seuils et couvrir le contexte annoncé. Un
résultat hors seuil ou non convergé reste consultable, avec ses diagnostics,
sans remplacer les paramètres du modèle. Un résultat exploratoire n'efface pas
une preuve historique précédente et ne permet pas de lancer automatiquement un
nouveau prix comme s'il était qualifié.

| Situation | Comportement |
|---|---|
| Heston, seuils respectés, horizon entièrement couvert, taux/dividende plats sans quanto | Application automatique possible aux hypothèses contrôlées ; la qualification porte sur les points publiés. |
| Non-convergence ou dépassement de l'un des seuils | Résultat exploratoire et diagnostics conservés à l'écran ; paramètres non appliqués. |
| Horizon demandé supérieur à dix ans ou à l'horizon de la surface | Couverture et exclusions publiées ; pas de qualification de l'horizon complet. |
| SABR | Ajustement MC exploratoire : bruit et discrétisation non qualifiés indépendamment. Aucune application automatique. |
| LSV | Ajustement de la composante Heston seulement ; aucune qualification implicite du LSV complet ni application automatique. |
| Hypothèses manuelles explicites | Conservées ; leur saisie ne constitue pas une calibration qualifiée. |
| Local Vol/LSV legacy avec densité, variance calendaire ou volatilité inadmissible | Refus explicite ; aucun remplacement silencieux par la volatilité implicite. |

## Corrections et interactions

**M07-01 — piliers matériels.** L'objectif contient tous les piliers ATM situés
dans l'horizon ajusté, les échéances de référence et l'horizon lui-même. Le pilier
7 ans n'est plus absent d'un ajustement 10 ans. Le dossier publie maturités,
strikes exprimés en multiples du spot, poids de l'objectif, prix cibles et prix
du modèle. Les piliers au-delà de l'horizon sont explicitement exclus. Il s'agit
d'un contrôle sur cette grille finie, sans revendication sur tous les strikes.

**M07-03 — Local Vol legacy.** Les dérivées de la variance totale du polynôme
historique sont calculées analytiquement. Les substitutions en volatilité
implicite à très courte maturité, en cas de densité invalide ou d'échec numérique
sont supprimées, ainsi que les plafonnements cachés de cette inversion. La
volatilité implicite doit rester dans `(0, 200 %]`, la volatilité locale dans
`(0, 300 %]` et les dérivées de Dupire doivent être admissibles sur la grille
consommée. La grille legacy garde ses bornes historiques de strike : 20–300 %
du spot. Cela ne constitue pas un certificat global d'absence d'arbitrage.

Cette correction change délibérément la convention d'inversion sur les smiles
legacy non plats. Les archives et paramètres enregistrés restent lisibles ;
aucune migration vers SSVI ni modification de portefeuille n'est exécutée.
Repricer un ancien smile désormais refusé demande une requalification explicite.
Les références nominales plates restent inchangées, sans modification des
valeurs attendues des tests historiques.

**M07-04 — convergence et qualification.** Le dossier sépare l'état du solveur,
son statut, son message, le nombre d'évaluations, le coût et l'optimalité des
erreurs économiques vanilles/digitales. L'interface montre la convergence, les
deux écarts et leurs seuils, les raisons de refus, la grille et les exclusions.
Les protections C10 empêchent toujours une réponse ancienne ou hors contexte de
remplacer les paramètres courants ; elles sont exercées dans les tests frontend.

Les taux et dividendes restent des scalaires plats de référence pour cet
ajustement. L'application automatique à un prix comportant une courbe de taux,
une courbe de dividende, une décroissance, des taux stochastiques ou un ajustement
quanto est refusée. Le passage manuel explicite reste disponible. Le funding
n'entre pas dans la calibration du sous-jacent ; la séparation de C15 entre
drift et actualisation reste inchangée.

**M07-05 — Fourier Heston.** L'intégration fixe à 256 points sur `[0, 300]` est
remplacée par une intégration adaptative sur `[0, +∞)`, avec une variable de
contrôle Black-Scholes dont la variance est l'espérance de la variance intégrée
Heston. Les expressions sont stabilisées aux petites différences. L'échec
d'intégration ou un dépassement matériel des bornes d'arbitrage entraîne un refus.
Seules les corrections d'arrondi compatibles avec l'erreur numérique sont
admises ; leur amplitude maximale est publiée. Le cas sans vol-of-vol utilise
exactement la limite Black-Scholes à variance déterministe.

Les paramètres d'intégration et son estimation d'erreur figurent dans le dossier.
Cette estimation n'est ni une borne mathématique absolue ni l'incertitude du
Monte Carlo de production. L'algorithme est confronté à une référence indépendante
résolvant les équations de Riccati par ODE, intégrée sur deux domaines Fourier,
et à des limites Black-Scholes fermées.

**M07-06 — conservation de la preuve.** L'API émet un dossier signé par le serveur,
avec version et empreinte du code de calibration, versions NumPy/SciPy,
cible, contexte, grille, poids, méthode numérique, initialisation, bornes et
tolérances du solveur,
paramètres, convergence, prix et erreurs, seuils et qualification. Un domaine de
signature distinct de celui des reçus de prix empêche d'interchanger les preuves.
La signature utilise la sérialisation stable au transport JSON déjà employée par
les reçus Product.

Avant un prix automatique, le serveur vérifie la signature, la version de
méthode, la convergence et les seuils courants, puis rapproche cible, niveau ATM,
paramètres, modèle, taux, dividende et horizon effectif C14. Une simple affirmation
du navigateur ne suffit pas. Les anciens produits automatiques sans preuve
doivent être recalibrés ou passés explicitement en hypothèses manuelles.

Le dossier accompagne les entrées du prix, son reçu signé et le snapshot de
marché. Une conservation volontaire du calcul Product le stocke en SQLite ; le
test relit le dossier complet via l'API après expiration de la session ORM. Les
snapshots et entrées résiduelles le transportent sans conversion de pourcentage.
Le dossier archivé décrit une calibration passée ; il ne qualifie pas une
nouvelle date de MtM ou un scénario. Le raccordement de ces usages reste C18.
Un essai de calibration non conservé reste transitoire : l'API ne crée pas une
archive serveur pour chaque essai exploratoire.

## Mesures reproductibles

Le panel ci-dessous utilise une cible synthétique à ATM plat de 30 %,
`rho = -0,75`, `eta = 0,85` sauf le cas plat (`eta = 0`), taux 3 %, dividende 2 %,
et les piliers 0,25 / 0,5 / 1 / 2 / 3 / 5 / 7 / 10 ans.

| Cible Heston | Convergence | Écart maximal vanille | Écart maximal digitale | Qualification aux points |
|---|---|---:|---:|---|
| Plate, 2 ans | Oui | 0,0597 pb | 0,3053 pb | Oui |
| Smile standard, 4 ans | Oui | 47,0064 pb | 131,4467 pb | Non |
| Smile standard, 10 ans | Oui | 163,7599 pb | 214,8771 pb | Non |
| ATM 7 ans porté à 35 %, horizon 10 ans | Oui | 307,2509 pb | 299,3051 pb | Non |

L'édition 7 ans déplace le call cible ATM de **401,2405 pb** et change les
paramètres ajustés. Ce chiffre décrit cette fixture, pas une constante générale.
Les quatre dossiers complets sont dans
`.runtime/diagnostic-acceptance/c17-2026-10-21/measurements.json`.

Sur le cas faible variance `v0 = theta = 0,0001`, `kappa = 1`, `xi = 0,01`,
`rho = -0,7`, un an, les calls à strikes 120 % et 150 % valent respectivement
environ `4,69e-10` et `9,84e-8` pb du nominal. Le test compare deux précisions
d'intégration sur 31 strikes et vérifie positivité, monotonie et convexité.
Sur le cas Heston indépendant à deux ans, l'écart à la référence Riccati et
l'écart entre ses deux domaines d'intégration sont inférieurs à `2e-8` du
nominal aux cinq strikes contrôlés. Ce panel ciblé ne vaut pas qualification
universelle des paramètres Heston.

## Validation et limites de couverture

**323 cas backend distincts réussis dans 12 fichiers**, dont **41 cas C17**.
Les passages incluent les surfaces éditables, Dupire, les références communes,
la calibration réalisée C11, le contexte de valorisation, les références figées
du moteur, les tests C14/C15/C16, les régressions de modèles et les calculs Product.
La première passe avait une assertion de nouveau test placée sur un strike
admissible ; le test a été corrigé sur le point réellement invalide, puis repassé.
Aucune référence nominale historique n'a été assouplie.

**643 tests frontend réussis**, dont les réponses tardives et chevauchées,
la conservation des paramètres manuels, le refus d'application des résultats
exploratoires et le transport de la preuve. Compilation Vue/Vite réussie dans
un répertoire temporaire ; `frontend/dist` préexistant est préservé. Le premier
lancement npm avait perdu l'option du répertoire de sortie sous PowerShell ;
la compilation Vite a été relancée avec l'argument explicite.

Les preuves détaillées sont dans [C17_VALIDATION.json](remediation-lot-0-2026-10-20/C17_VALIDATION.json).
Les tests utilisent des données synthétiques, des bases isolées et un blocage
des appels HTTP externes via requests/curl_cffi. Aucun serveur n'a été lancé,
aucune donnée métier ni aucun fixing n'a été modifié.

T11 est validé localement sur les composants exercés ; sa recette graphique de
chaîne reste à faire. La convergence temporelle du Monte Carlo de production,
le SABR hors échantillon, le LSV complet, les payoffs à barrières et les contextes
non plats/quanto demeurent hors qualification C17. C18 doit rapprocher les
consommateurs et leurs contextes avant élargissement. Les décisions C16, les
seuils de fraîcheur C11 et les règles de finalité C13 sont inchangés.

## Références numériques

- [SciPy — intégration adaptative vectorielle `quad_vec`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.quad_vec.html) : précision absolue/relative, norme, convergence et diagnostics.
- [QuantLib — moteur analytique Heston](https://github.com/lballabio/QuantLib/blob/master/ql/pricingengines/vanilla/analytichestonengine.cpp) : référence de mise en œuvre pour la fonction caractéristique et les variables de contrôle. Structura ne dépend pas de QuantLib.
