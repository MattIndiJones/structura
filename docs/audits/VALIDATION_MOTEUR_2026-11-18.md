# Validation du moteur — 18/11/2026

Reprise du point P1-3 de l'[audit technique du 16/11](AUDIT_GLOBAL_TECHNIQUE_2026-11-16.md) :
« aucune preuve externe de justesse ». L'audit déclarait SABR, Local Vol, LSV et les Greeks
« non sondés ». C'était trop sévère : la [validation du 07/10](VALIDATION_MODELES_VOL_2026-10-07.md)
et le [benchmark sur cible commune](AUTOCALL_SURFACE_COMMUNE_2026-10-07.md) les avaient
recoupés. Mais ces deux études tournaient **en scripts**, hors de pytest et de la CI. Une
régression sur ces modèles serait passée sans bruit.

Ce lot transforme ces contrôles en **tests**, et comble les trous qu'aucune étude ne couvrait.
Chaque référence est une formule fermée, une quadrature ou une EDP écrite hors du moteur.
Chaque test confronte le modèle à une propriété qu'il doit respecter par construction, plutôt
qu'à une valeur figée.

## Ce qui est testé

| Fichier | Contrôle | Référence | Tolérance |
|---|---|---|---|
| `test_validation_probes.py` | A. Call GBM 80/100/120 % | Black-Scholes | 3 ET + 0,1 pb |
| | B. Reproductibilité | même graine = même prix au dernier chiffre ; autre graine ≠ | exacte |
| | C. Heston QE, hebdomadaire, 90/100/110 % | inversion de Fourier | 3 ET + 2 pb |
| | D. Put down-and-in 100 % / 70 %, mode continu | formule fermée de Reiner-Rubinstein, elle-même testée sur ses deux limites | 3 ET + 1 pb |
| | D. Même put, mode hebdomadaire | correction de Broadie-Glasserman-Kou ; et hebdomadaire < continu | 3 ET + 8 pb |
| | E. Funding sur un forward | le spread n'échelonne que l'actualisation ; le taux laisse le forward à `e^(−qT)` | 2·10⁻⁶ |
| | E. Funding sur un autocall worst-of 3 ans | 100 pb de spread coûtent au moins 50 pb de plus que 100 pb de taux | — |
| `test_validation_smile_models.py` | SABR, smile à 3 mois sans drift, 90/100/110 % | formule de Hagan (2002), réécrite dans le test | 3 ET + 0,05 pt de vol |
| | SABR, calls 1 an et 4 ans | EDP spot indépendante du 07/10, maillage fin | 3 ET + 1 pb + écart entre maillages |
| | Local Vol sur SSVI sans arbitrage, 1 et 2 ans, 80/100/120 % | vol implicite SSVI recalculée dans le test (Gatheral-Jacquier) | 3 ET + 1 pb |
| | LSV sur la même SSVI, avec une variance sans rapport (xi 50 %, rho −0,8) | idem | 3 ET + 1,5 pb |
| | LSV sans vol de vol | trajectoires Local Vol, mêmes tirages | 10⁻⁵ relatif |
| `test_validation_greeks.py` | Delta, gamma, vega, rho d'un call 100 % et 110 % | dérivées de Black-Scholes | 1 % à 6 % relatif selon le Greek |
| | Delta, vega, rho du put down-and-in continu | formule fermée bumpée exactement comme le moteur | 3 % à 6 % |
| | Signes du put down-and-in | delta < 0 < vega, rho < 0 | — |
| | Forward : rho et sensibilité au spread | rho nul ; crédit = −T × PV | 0,3 % |

Les tolérances des Greeks viennent de la dispersion observée sur trois graines (42, 17, 93),
avec une marge. **47 tests**, environ 2 min en séquentiel, répartis entre les processus de la suite
parallèle. Les tests de référence figés du moteur (`test_engine_golden.py`) et la
validation du 07/10 (`test_vol_model_validation.py`) passent inchangés.

## Écarts mesurés

Graine 42, sauf mention. Ce sont des **mesures d'instance**, pas des tolérances générales.

| Contrôle | Écart | Erreur standard |
|---|---|---|
| GBM, calls 80 / 100 / 120 % | +2,80 / +2,89 / +2,75 pb | 1,6 / 2,3 / 1,6 pb |
| Heston, calls 90 / 100 / 110 % | +0,15 / +0,13 / +0,33 pb | 1,5 / 1,3 / 1,0 pb |
| Barrière continue contre formule fermée (5,012 %) | +2,3 pb | 2,4 pb |
| Barrière hebdomadaire contre Broadie-Glasserman-Kou (4,525 %) | +5,6 pb | 2,4 pb |
| SABR 3 mois, 416 pas/an, contre Hagan | −0,03 à +0,04 pt de vol | 0,04 pt |
| Local Vol sur SSVI, 208 pas/an | −0,8 à +1,6 pb | 0,8 à 3,0 pb |
| LSV sur SSVI, 208 pas/an | −4,6 à +1,9 pb | 1,7 à 4,9 pb |

Les trois écarts GBM ont le même signe parce qu'ils partagent le même tirage ; c'est
1,2 à 1,8 erreur standard, comme dans la sonde A de l'audit.

## Ce que ce lot a trouvé : le pas de 52 par an

Deux biais de discrétisation, invisibles dans les tests existants, qui tournent tous au pas de
production :

- **SABR, smile court aplati.** À 52 pas par an, soit 13 pas sur 3 mois, le 90 % sort de 0,10 à
  0,15 point de vol trop bas et le 110 % de 0,13 à 0,23 point trop haut, sur deux graines
  (jusqu'à 5,7 erreurs standards). À 416 pas, l'écart à Hagan tombe sous 0,05 point. Ce n'est
  pas Hagan : son erreur diminuerait avec la maturité, et elle ne bouge pas.
- **Local Vol, call en dehors de la monnaie.** Sur la SSVI, le call 120 % à 1 an sort de +2 à
  +5 pb au-dessus de la cible à 52 pas, sur toutes les graines (erreur standard 0,85 pb). Le
  biais tombe à +1,1 pb à 104 pas, et dans le bruit à 208 et 416 pas : la vol locale est figée
  sur une semaine. Le LSV montre le même ordre de grandeur.

C'est cohérent avec le choix de 208 pas par an du benchmark du 07/10, et avec la note de la
[grille de diffusion](../projects/pricing/SIMULATION_GRID_2026-11-05.md). Les tests de
reproduction tournent à 208 pas et le test Local Vol **échoue** à 52 pas (+3,95 pb pour 3,5
admis) : il sait voir le biais. Le test LSV, plus tolérant à cause des particules en
interaction, ne le voit pas (+7,5 pb pour 8,6).

**Conséquence pratique** : sur un produit court à smile prononcé, ou sensible aux options en
dehors de la monnaie (digitales, barrières proches), pricer en SABR, Local Vol ou LSV au pas
de 52 coûte de l'ordre de quelques points de base. Les grilles 104 et 208 existent pour cela.

**Décision du 18/11 (Philippe) : le défaut reste à 52 pas**, les grilles plus fines étant trop
longues en pricing courant. À la place, tout prix SABR, Local Vol ou LSV calculé à 52 pas
porte un avertissement : champ `grid_notice` de `/api/price` et du pricing en cours de vie,
affiché en encadré dans le panneau de résultats du Pricer (`core/simulation_grid.smile_grid_notice`,
testé dans `test_simulation_grid.py` et `ResultsPanel.test.js`). Les autres modèles et les
grilles 104 et 208 n'en portent pas.

**Le gamma d'une barrière n'est pas fiable par bump.** Sur le put down-and-in, à ±3 % de spot
et 40 000 trajectoires, le gamma s'écarte de la formule de +0,2 % à +23 % selon la graine.
Delta, vega et rho restent à 4 % près. Le test ne contrôle donc pas ce gamma.

## Ce qui reste hors champ

- **Recoupement contre des cotations de banques** sur cinq structures : il faut les cotations.
- **Quanto** : ni sondé ni testé.
- **Calibrations Heston et SABR à un smile** : le benchmark du 07/10 a montré qu'elles
  restent approximatives (Heston) ou insuffisantes (SABR à paramètres constants). Ce lot
  valide les simulateurs, pas la qualité d'ajustement.
- **Taux stochastiques Hull-White** : non repris ici ; `test_stochastic_rate_integrity.py`
  existe, non relu.
- **Greeks hors GBM** : le vega Heston et LSV a un périmètre partiel, déjà déclaré par
  `vega_scope`. Il n'est pas comparé à une formule.

## Reproduction

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_validation_probes.py backend/tests/test_validation_smile_models.py backend/tests/test_validation_greeks.py -q --basetemp=<dossier temporaire>
```

Les mesures de discrétisation ci-dessus viennent de scripts de session, non versionnés ;
elles se refont en changeant le pas des fixtures (`STEPS_PER_YEAR`, `steps`).
