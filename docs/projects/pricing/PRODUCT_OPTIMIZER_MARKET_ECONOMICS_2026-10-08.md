# Product Optimizer — marché et économie d’émission, 08/10/2026

État : **implémenté localement, tests ciblés et build réussis**, sans commit ni
push. Suite du [lot quantitatif](PRODUCT_OPTIMIZER_QUANT_VALIDATION_2026-10-08.md).
Le périmètre demeure Athena européen mono-actif / worst-of sous GBM. Philippe
a retenu l’Optimizer avant le Copilot ; la conservation des recherches vient ensuite.

## Comportement livré

Le bouton **Reprendre le marché du Pricer** copie explicitement les entrées de
la session : panier, devise, date d’hypothèses, volatilités constantes, dividendes,
corrélations, courbe de taux et funding. Il ne lance pas de téléchargement.
Les paramètres structurels restent saisis dans l’Optimizer. La date copiée devient
la date de strike et de valeur de cette recherche à l’émission.

La copie exige GBM, taux déterministes, 1 à 3 tickers distincts actifs dans le
référentiel, même devise et aucune correction FX/quanto ou basis active. Un marché
Heston/Local Vol/LSV n’est pas converti implicitement en GBM. Une devise modifiée
après la copie exige un nouveau marché de cette devise, côté interface et API.

Les valeurs peuvent ensuite être modifiées. Chaque champ conserve sa valeur de
référence, sa date, son origine et la valeur effectivement utilisée. Les nouvelles
hypothèses ajoutées après import sont identifiées comme manuelles. Les corrélations
restent attachées aux paires de tickers lors d’un retrait ou d’un changement d’ordre ;
une nouvelle paire reçoit l’hypothèse affichée de 0,5. Le panier de référence et
son ordre sont conservés dans l’audit, distinctement du panier utilisé.

Au lancement, une copie profonde de la requête et un snapshot de marché sont
figés. Leur empreinte SHA-256 permet d’identifier les entrées. Le même marché
alimente résolution du coupon, repricing, validation indépendante N/2N et
diagnostic d’incertitude du coupon, en séquentiel comme dans les processus de calcul.
Le résultat et l’export JSON comprennent le snapshot et l’économie d’émission.

## Conventions financières

**Budget du payoff = prix d’émission brut − frais initiaux − marge de structuration.**

Les frais et la marge sont des points du nominal, prélevés initialement. Exemple :
émission à 100 %, frais de 0,5 point et marge de 0,5 point donnent un budget de 99 %.
Ils ne sont pas calculés en pourcentage du prix d’émission et ne sont pas retranchés
des flux contractuels de l’investisseur. Le solveur et les filtres de prix ciblent
ce budget net ; le classement utilise aussi l’écart au budget net. La probabilité
de perte reste calculée sur les flux non actualisés comparés au prix d’émission brut.

La courbe de taux existante alimente **drift et actualisation**. Le funding
alimente **uniquement l’actualisation**, selon la convention du moteur existant.
Il n’y a pas de modèle de défaut, de recouvrement ni de corrélation au crédit émetteur.
Les coûts ne sont déduits qu’une fois ; le funding intervient déjà dans le PV.

| Entrée | Interface | API et moteur | Convention |
|---|---|---|---|
| Volatilité, dividende, taux plat | % | Fraction | 20 % devient 0,20 |
| Taux / dividendes / funding en courbe | Années et % par nœud | `[années, fraction]` | Maximum 30 nœuds |
| Funding plat | bps | Fraction | 100 bps devient 0,01 |
| Frais initiaux / marge | Points de nominal % | Fraction du nominal | 0,5 point devient 0,005 ; chacun 0 à 10 points |
| Corrélations | Coefficient | Matrice de coefficients | Symétrique, diagonale unité, définie positive ; aucune réparation |

La saisie des courbes se fait dans des tableaux. Les courbes de taux et de funding
reprennent les conventions d’interpolation/extrapolation du moteur. Le taux plat
devient un repli quand une courbe de taux est utilisée ; les deux sont conservés
dans l’audit avec leur statut actif. Une courbe de funding exclut un spread plat
non nul. Une courbe vide de taux ou de dividendes sélectionne l’hypothèse plate.

Les dividendes reprennent les buckets annuels consécutifs dégressifs du Pricer,
avec un premier rendement égal à `q` et prolongement du dernier bucket. La copie
conserve exactement les nœuds existants : elle ne régénère pas une nouvelle
décroissance pour les maturités plus longues explorées par l’Optimizer. Cette
extrapolation doit donc être examinée dans les hypothèses de recherche.

## Qualification et provenance

`PRICER_SESSION` signifie **copie d’hypothèses de session**. Les origines par champ
sont `PRICER_ASSUMPTION` ou `USER_ASSUMPTION`. Le Pricer peut avoir utilisé une
estimation historique de volatilité ou une saisie manuelle ; cet import ne les
transforme pas en volatilités implicites observées ou calibrées. La date conservée
est celle des hypothèses du Pricer, sans certification de la date du fournisseur
sous-jacent. Les références antérieures à la date choisie sont signalées ; des
références futures sont refusées.

Le contrat d’import exige les références de chaque champ, la devise, les tickers
de référence et un timestamp avec fuseau. Les champs inconnus, valeurs non finies,
formes incohérentes des références, courbes invalides et funding ambigu sont refusés.
L’audit permet de distinguer référence et override, hypothèse active et repli.
L’empreinte identifie les entrées déclarées, sans certifier leur source externe.

La classification action/indice demeure déclarative. Un snapshot de marché
qualifié par fournisseur, les sources implicites et la classification du référentiel
restent à traiter. Il n’y a aucune création de booking ni persistance des runs.

## Vérifications effectuées

**95 tests backend ciblés distincts réussis** : 65 tests Optimizer/orchestration/
validation quantitative ; 24 tests marché et économie ; 6 tests du solveur partagé.
Les derniers contrôles de forme des références ont été exécutés après leur ajout.
Aucune suite backend complète lancée.

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_product_optimizer.py backend/tests/test_product_optimizer_parallel.py backend/tests/test_product_optimizer_validation.py -q
.venv/Scripts/python.exe -m pytest backend/tests/test_product_optimizer_market.py backend/tests/test_simulation.py -q
.venv/Scripts/python.exe -m pytest backend/tests/test_product_optimizer_market.py -q -k 'reference_shapes or reference_contract or snapshot or currency'
```

Les calculs réels vérifient l’effet des courbes sur le prix et les trajectoires,
un coupon résolu plus faible après coûts, la perte rapportée au prix brut et
l’équivalence des defaults sans coûts. À coupon fixe, un spread de funding
réduit le prix et laisse les flux non actualisés strictement identiques ; un
funding plat et sa courbe constante reproduisent le même prix. Le diagnostic
de coupon reconstruit le PV avec courbes et dates de paiement, et reste disponible.

Un calcul complet avec courbes, funding et coûts reproduit les mêmes candidats,
classement et empreinte de marché en séquentiel et avec deux processus Windows.
Les tests API vérifient l’export ; la copie profonde est contrôlée en modifiant
la requête et des tableaux après la capture.

`npm run build` dans `frontend/` : **299 tests frontend réussis**, build réussi.
Les tests comprennent copie sans alias, unités, refus de modèles/FX incompatibles,
export des entrées du store Pricer sans script ni réseau, remappage des corrélations
et rendu serveur des tableaux de courbes. Avertissements préexistants TestClient/
httpx et imports dynamiques sans incidence sur le succès.

La recette visuelle complète dans un navigateur n’a pas été effectuée pour ce lot.
Aucun serveur applicatif lancé, aucun téléchargement de marché ni modification
de base réelle. Les bundles versionnés `frontend/dist/` sont régénérés par le build.

## Suite

La validation de la grille temporelle à quelques bps reste ouverte : ces tests
qualifient la transmission cohérente des entrées, sans certifier l’erreur de modèle
ou de discrétisation. Le [smile actions URGENT](SMILE_ACTIONS_URGENT_2026-10-08.md)
reste différé. La prochaine extension prévue est Phoenix, puis Phoenix mémoire,
avec qualification des flux de coupons et métriques avant activation.

**Suite livrée le même jour :** [payoffs et champs dynamiques](PRODUCT_OPTIMIZER_PAYOFFS_2026-10-08.md),
avec Phoenix, mémoire, Athena dégressif et reverse convertible européenne.
