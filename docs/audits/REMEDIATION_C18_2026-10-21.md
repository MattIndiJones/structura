# C18 — Contexte commun de valorisation et sémantique

Livraison locale du 21 octobre 2026, sans commit ni push. Les sept constats
M06-07, M06-08, M06-09, M13-07, M14-05, M15-07 et M17-01 sont traités sur
le périmètre décrit ci-dessous. Les décisions et domaines C13–C17 sont conservés.
Aucune qualification générale des modèles ou de la production n'est prononcée.

## Résultat métier

Le prix, les probabilités et les trajectoires utilisent le même moteur Monte
Carlo et une construction commune du contexte daté : sous-jacents et paramètres,
modèle, corrélations, courbes, funding, taux stochastiques, antithétiques,
conventions de paiement, date de valeur, calendrier et état résiduel.

À contexte, tirages et graine identiques, les trois calculs donnent le même
centre de valorisation. Un échantillon réduit reste possible pour une analyse ;
sa taille effective, le nombre de trajectoires et les antithétiques sont publiés.
Une réduction de l'échantillon ne retire aucun paramètre financier.

| Contrôle | Résultat local |
|---|---|
| Cinq modèles, antithétiques activés/désactivés, courbes et taux stochastiques | Égalité exacte des prix arrondis entre moteur, probabilités et trajectoires, sur les fixtures communes. |
| PAY 1 à trois ans, taux nul, funding de 10 % | Les trois calculs donnent **0,740818**, contre `exp(-0,3) = 0,7408182207`. |
| Avant strike | Le prix résiduel et les analyses simulent la même attente du fixing initial ; aucun historique futur n'est demandé. |
| Panier continu de copies GBM | Même payoff dans les consommateurs ; refus des configurations hors domaine C16 maintenu. |
| PAY 10 % certain | **100 % de flux positifs**, **0 % de flux nuls** ; le remboursement reste sous le pair, ce qui constitue une autre mesure. |
| Coupon détaché de 100 kEUR payable dans six jours, taux 3 %, funding 2 %, choc de taux +100 pb | PV **99 917,8982 → 99 901,4859 EUR**, soit **−16,4123 EUR**, séparément de l'optionalité. |

Ces chiffres décrivent les fixtures synthétiques de cette livraison, pas des
constantes générales ni des résultats observés sur le portefeuille.

## Corrections et interactions

**M06-07 — analyses raccordées au prix.** Les deux chaînes de simulation propres
aux trajectoires et aux probabilités sont remplacées par une collecte optionnelle
dans le moteur du prix. La diffusion, les extrema, le fixing initial et
l'évaluation des flux utilisent ainsi les mêmes fonctions. L'état réalisé,
la mémoire, les références de spot et les conventions de paiement ne sont plus
reconstitués dans un deuxième évaluateur.

`valuation_context_from_request` construit le contexte partagé du prix initial,
du prix en cours de vie et des analyses. La graine API reste 42. Les probabilités
utilisent entre 2 000 et 10 000 tirages indépendants ; les trajectoires gardent
leur échantillon visuel dédié. Les métadonnées précisent le nombre demandé et
effectif, le nombre de trajectoires et les antithétiques. L'empreinte du contexte
est retournée par les analyses.

Le routage traite aussi une valorisation antérieure au strike. Un produit déjà
rappelé ne retombe plus silencieusement sur une analyse de produit neuf. Le
profil de payoff demeure un diagramme nominal à niveaux constants, distinct
d'une espérance Monte Carlo ; sa convention de chemin plat est conservée.

**Dépendances C14/C15/C16.** Le moteur existant conserve son axe temporel, son
actualisation aux paiements, le couplage des taux et le funding appliqué une
seule fois en actualisation. Le funding ne rejoint pas les taux stochastiques
ni le drift du sous-jacent. Les analyses héritent des refus et diagnostics des
barrières C16 ; aucun basculement automatique vers le monitoring hebdomadaire.

**M06-08 — Greeks.** L'API transmet le choix d'antithétiques du prix aux Greeks.
La sensibilité de corrélation demande toujours un choc de cinq points, mais
utilise un choc signé réellement admissible : sens inverse près d'une borne,
réduction si nécessaire pour préserver la matrice PSD et le domaine C16.
La différence de prix est divisée par cette amplitude effective. Une paire
sans perturbation isolée admissible est indisponible (`null`), avec raison,
plutôt que présentée comme une sensibilité nulle. Amplitude et sens figurent
dans `corr_bumps`, séparément des montants agrégés.

Le calcul du vega LSV est conservé : décalage additif de la volatilité locale
effective, processus de variance figé, sans recalibration. Son ancien libellé
« jambe indépendante » et sa couverture `1-rho²` étaient erronés pour ce moteur.
Le type `effective_local_vol` possède désormais son libellé et son compartiment
de risque. Il n'est pas additionné implicitement au vega total GBM ou à celui
de la jambe indépendante Heston. Aucun nouveau vega de marché n'est introduit.
D12 reste partiellement ouvert pour de nouveaux choix métier et les budgets C20.

**M06-09 — statistiques.** Le signe de la somme des flux nominaux, le retour au
pair, la perte face au prix payé et les quantiles actualisés sont distincts.
Le graphique générique décrit des flux positifs, nuls ou négatifs, sans déduire
ITM/OTM de la comparaison au pair. La classification historique `ki` reste
compatible dans l'API mais signifie « sous le pair sans STOP » ; elle ne prouve
pas le franchissement d'une barrière contractuelle. L'écran l'indique.
La tuile `var5` devient « Quantile 5 % actualisé », la médiane est également
qualifiée d'actualisée et `n_eff` est libellé « Tirages indépendants ».

**M13-07/M14-05 — source effective.** Le run archive `effective_source` à partir
du résultat réellement calculé. Historique des MtM et Valo Explain partagent
une seule lecture des sources : booking, booking avec surcharges, réalisé,
réalisé avec surcharges et créance connue. Une requête vide ou absente ne
transforme plus un calcul booking en marché actualisé. Une archive sans source
effective connue reste « Source non renseignée » ; aucune source historique
n'est inventée et aucune ancienne ligne n'est réécrite.

Le mode réalisé est libellé « Volatilités réalisées, dividendes actualisés » :
il ne signifie pas que les taux, le funding ou tous les dividendes forward
proviennent d'observations de marché nouvelles. Les sources C11 restent distinctes.

**M15-07 — coupons détachés.** Le contexte du MtM conserve les créances impayées
avec leur montant et leur temps exact jusqu'au paiement. Le choc de taux
réactualise cette composante avec les mêmes courbes et le même funding que la
base. Les contributions avant/après et leur différence sont séparées dans le
résultat du choc. Un ancien contexte sans dates de créance ne reçoit pas un
choc fictivement nul : la réactualisation est refusée si elle serait nécessaire.
Les faits de fixing et de paiement ne sont pas modifiés.

**M17-01 — scan et solveur.** Le scan hérite du modèle du booking lorsqu'aucun
modèle n'est explicitement choisi. L'interface propose un choix explicite de
GBM avec volatilité réalisée. Le contexte commun transporte taux, funding,
antithétiques, taux stochastiques, monitoring, dates de paiement et de valeur
jusqu'au solveur et aux probabilités. La réponse conserve les paramètres
effectifs et la taille d'échantillon.

Le solveur et la grille de PARAM du Pricer utilisent également ce contexte complet,
y compris le funding, les paiements et le choix des antithétiques ; leur contexte
de base est publié. Le solveur conserve ses conventions de bissection et ses CRN. La proposition
utilise le même chemin de calcul que le scan. La calibration d'un autre
sous-jacent n'est pas présentée comme celle du candidat : une cible automatique
Heston/SABR/LSV transférée est refusée. Le GBM choisi explicitement et les
hypothèses manuelles déclarées restent des choix distincts d'une calibration
qualifiée. C17 et ses seuils 5/10 pb ne sont pas élargis.

## Validation et préservation

**479 cas backend distincts réussis dans 17 fichiers**, dont **35 cas C18**.
Les fichiers de départ du registre ont été exercés, ainsi que les Greeks
stateful, le solveur, les chocs, le pricing en vie, les agrégats de risque,
les références figées et les dépendances C13/C15/C16/C17.

**652 tests frontend réussis dans 74 fichiers**, compilation Vue/Vite réussie
dans un dossier temporaire. Les tests vérifient notamment le transport des
paramètres de taux et d'antithétiques et la lecture des sources effectives.
Le répertoire `frontend/dist` préexistant est préservé.

Les premières passes et leurs échecs restent dans les preuves. Deux défauts
d'implémentation intermédiaires ont été corrigés : forme des événements dans
les métadonnées de probabilités et argument absent du calcul de budget.
Des fixtures anciennes ont ensuite été adaptées sans affaiblir leurs assertions :

- utilisateurs de test dotés d'un rôle valide, conformément à C01 ;
- exemples Local Vol utilisant un smile admissible ou une cible SSVI explicite,
  au lieu d'un polynôme refusé depuis C17 ;
- horizon d'un test avant strike conservant la dernière observation roulée,
  conformément à C14.

Les trois reproductions quantitatives représentatives échouent également sur
le moteur sauvegardé avant C18. Les valeurs attendues des références nominales
figées n'ont pas été changées. Les tests utilisent des données synthétiques,
des bases isolées et un blocage des appels HTTP externes requests/curl_cffi.

La [preuve machine C18](remediation-lot-0-2026-10-20/C18_VALIDATION.json) détaille
les passages, résultats, mesures et contrôles de préservation. Les logs,
reproductions antérieures et différences par rapport à l'état d'entrée sont
dans `.runtime/diagnostic-acceptance/c18-2026-10-21/`.

## Limites et suite

Cette livraison vérifie la cohérence locale des calculs, sans qualifier la
précision absolue de tous les modèles ou payoffs. La taille dédiée d'une analyse
peut laisser un bruit Monte Carlo différent de celui du prix principal.
Les domaines de C16/C17 et leurs limites de production restent inchangés.

T06/T07 sont raccordés localement sur les contextes exercés. T08/T09/T13/T16
restent partiels : invalidations et archives/PDF C19, couverture et CVA C21,
paiements/P&L C22 et coûts/récupération/propositions C25 sont encore nécessaires.
Le MtM Deal conserve les faits officiels C13 ; les analyses d'un formulaire
utilisent les mêmes entrées que son propre prix résiduel. La recette graphique
de chaîne complète reste à réaliser.

Aucun inventaire d'impact sur le portefeuille réel, recalcul historique,
migration d'archives, modification de fixing ou lancement de serveur n'a été
effectué. Aucun commit ni push.
