# C15 — Taux stochastiques, funding et corrélations

Livraison locale du 21 octobre 2026, sans commit ni push. Les trois constats
M06-01, M06-02 et M06-04 sont corrigés et validés sur le périmètre ciblé.
La dépendance C14 est conservée ; T06 reste partiel jusqu'au raccordement C18.

## Résultat métier

**Le funding est exclu des taux stochastiques et du drift des sous-jacents.**
Seule la courbe sans risque, éventuellement choquée en taux, alimente la
dynamique. Le funding, plat ou en courbe, et son choc de spread multiplient les
facteurs d'actualisation une seule fois. Cette séparation applique la convention
de `CLAUDE.md`, confirmée par Philippe pendant C15.

| Contrôle, valeurs en fraction du nominal | Avant C15 | Après C15 | Référence |
|---|---:|---:|---:|
| PAY 1 à un an, taux 3 %, funding 2 %, sigma_r = 1e-12 | 0,932394 | 0,951229 | exp(-0,05) = 0,9512294245 |
| PAY 1 à un an, sigma_r = 3 %, a_r = 0 | 0,970452 | 0,970452 | exp(-0,03) = 0,9704455335 |
| Même cas, a_r = 1e-4 | 0,970451 | 0,970452 | Continuité vers a_r = 0 |
| Même cas, a_r = 1e-6 | 1,484111 | 0,970452 | Continuité vers a_r = 0 |
| Même cas, a_r = 1e-8 | Non fini | 0,970452 | Continuité vers a_r = 0 |
| Variance du choc mono, rho_rS = 0,8 | 1,639423 | 1,000042 | 1 |
| Corrélation réalisée du choc mono avec le taux | 0,621347 | 0,798549 | 0,8 |

Les mesures avant/après utilisent les sources sauvegardées au début de C15 et
les mêmes tirages. Le premier cas utilise 32 paires antithétiques ; les quatre
cas de continuité à un an, 2 048 paires ; les moments de choc, 16 000 tirages
indépendants à un jour. L'écart du zéro-coupon stochastique à sa courbe est une
erreur Monte Carlo, pas une nouvelle prime de convexité à ajouter.

## Changements et interactions

- **M06-01** : la branche stochastique construit ses forwards depuis
  `rates.df`, avant funding, puis applique les facteurs de funding séparément.
  Les contrôles couvrent les cinq modèles, les spreads plats, une courbe non
  plate, un choc de spread, les deux modes antithétiques, le choc de taux, le
  rebasage à la date valeur et le paiement décalé. Un contrôle direct exige des
  trajectoires de taux et facteurs sans risque strictement identiques avec ou
  sans funding ; les payoffs bruts restent identiques.
- **M06-02** : les cinq simulateurs appliquent le facteur résiduel même en mono.
  Pour un facteur de taux de corrélation rho, le choc action devient
  `sqrt(1-rho²) Z_action + rho Z_taux`. Les cas rho = -1, -0,8, 0, 0,8 et 1
  conservent la variance et la corrélation demandées. Le contrôle d'un panier
  vérifie simultanément les deux corrélations au taux et la corrélation entre
  actions ; une dépendance jointe impossible reste refusée. Le chemin sans
  couplage conserve l'absence de copie supplémentaire des tirages mono.
- **M06-04** : la variance d'innovation OU utilise `expm1` pour éviter la
  soustraction de deux nombres presque égaux. La convexité utilise une récurrence
  de covariance au lieu de sommes géométriques instables. Aucun seuil arbitraire
  ne remplace un petit retour à la moyenne positif par zéro. Les entrées de taux
  invalides et les facteurs non finis ou tombés à zéro sont refusés explicitement.
- **C14** : le pas effectif continue de provenir de l'horizon exact. Les contrôles
  couvrent un jour, un an et trente ans, y compris des prix courts et longs près
  de zéro. Le tri, les rangs, les dates de paiement et l'axe contractuel ne sont
  pas modifiés. Les 25 tests C14 repassent.
- **Valorisation et traçabilité** : les tests de contexte, MtM/VaR et taux bookés
  repassent ; les prix et Greeks du harnais nominal gardent leurs références.
  Le changement de `engine.py` entre dans l'empreinte moteur déjà existante.
  Aucun run archivé, fixing officiel, contrat ou snapshot n'est réécrit.

## Vérification mathématique

Le facteur est `x_k = phi x_(k-1) + eta Z_k`, avec
`phi = exp(-a dt)` et `eta² = sigma_r² (1-exp(-2a dt))/(2a)`.
Sa limite à a = 0 est `sigma_r² dt`, propriété également définie dans la
[transition OU de QuantLib](https://github.com/lballabio/QuantLib/blob/master/ql/processes/ornsteinuhlenbeckprocess.cpp).

La correction suivante est une dérivation pour l'intégrale **discrète de
Structura**, pas une reprise d'un calibrage continu. Pour
`I_k = dt sum_(j=1..k) x_j`, on propage :

```text
V_k = phi² V_(k-1) + eta²
psi_k = phi C_(k-1) + dt V_k / 2
C_k = phi C_(k-1) + dt V_k
```

Ici `V_k = Var(x_k)`, `C_k = Cov(I_k,x_k)` et
`psi_k = (Var(I_k)-Var(I_(k-1)))/(2 dt)`.
Ajouter psi au taux annule donc exactement l'effet de Jensen en espérance sur
les piliers de cette grille gaussienne. Les tests comparent la variance intégrée
à une matrice dense de covariances gaussiennes calculée indépendamment, avec
une tolérance relative de 3e-12, sur chaque pilier à un jour, un an et trente ans.

Le forward prépayé GBM, q = 1 %, rho_rS = 0,8, sigma_r = 3 %, est vérifié sur
quatre réplications indépendantes de 8 192 paires. Chaque estimation est à moins
de cinq erreurs standards de `exp(-0,01)` ; leur moyenne à moins de trois erreurs
standards. Cela contrôle l'identité économique en plus des seuls moments des chocs.

## Validation exécutée

**231 cas backend distincts réussis sur dix fichiers**, dont **105 cas C15**.
Le groupe principal contient 229 cas ; deux cas supplémentaires vérifient les
prix à un jour et trente ans dans la limite a_r vers zéro. La suite backend
complète n'a pas été lancée. Aucun fichier Vue n'a changé.

Le panel C15 principal de 103 cas a aussi été exécuté contre le moteur sauvegardé
avant correction : **89 échecs reproduits et 14 cas déjà corrects**. Ce rejeu
remplace le module en mémoire, sans réécrire les sources du workspace. Les deux
contrôles de prix courts/longs supplémentaires sont des validations après correction.

Un ancien test Hull-White exigeait à tort que le zéro-coupon monte avec la
volatilité malgré la correction de convexité. Il contrôle désormais le
rapprochement avec la courbe dans l'erreur d'échantillonnage ; aucune valeur
attendue du harnais nominal n'a été modifiée.

Les cas, commandes, mesures et empreintes figurent dans
[C15_VALIDATION.json](remediation-lot-0-2026-10-20/C15_VALIDATION.json).
Les JUnit, le garde réseau, les sources de reproduction et leurs sorties sont
dans `.runtime/diagnostic-acceptance/c15-2026-10-21/`.
Les tests utilisent des données synthétiques et des bases temporaires isolées.
Aucun serveur n'a été lancé, aucune base métier n'a été ouverte ou créée et
aucun appel réseau de données de marché n'a été observé par le garde des tests.

## Limites et suite

- **T06 reste partiel** : les invariants C14/C15 du moteur principal sont validés
  localement. L'égalité des contextes prix/probabilités/solveur et la transmission
  complète aux consommateurs restent à traiter en C18. Aucun raccordement élargi
  n'est déclaré livré ici.
- **D04 reste ouvert**, sans approbation implicite. Ces corrections ne qualifient
  pas toutes les combinaisons Heston/SABR/Local Vol/LSV avec taux, leurs martingales,
  les barrières continues, le quanto ou leurs sensibilités. Les contrôles de chocs
  sur cinq modèles ne suffisent pas à cette qualification. C16 et C17 restent ouverts.
- La continuité sur trente ans vérifie la stabilité numérique avec les mêmes
  tirages ; ce petit échantillon ne mesure pas précisément l'espérance d'un
  zéro-coupon de longue durée et forte volatilité des taux.
- Aucun recalcul ou backfill de données réelles n'a été exécuté. Un nouveau
  calcul d'un cas affecté peut changer ; les rapprochements avec les archives
  doivent tenir compte de l'empreinte moteur. La recette graphique et la
  qualification opérationnelle/production restent à faire.
