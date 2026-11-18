# KID : méthode de Catégorie 3 — 18/11/2026

Reprise du constat F5 / P1-2 de l'[audit technique du 16/11](../../audits/AUDIT_GLOBAL_TECHNIQUE_2026-11-16.md).
Texte de référence : règlement délégué (UE) 2017/653 consolidé au 01/01/2023 (modifications
de 2021/2268 incluses), lu sur EUR-Lex le 18/11/2026. Les numéros de points ci-dessous
renvoient à ce texte.

**Statut : non commité, toujours `INDICATIVE_NON_PRIIPS`.** La méthode est en place ; le KID
n'est pas conforme pour autant tant que les limites listées plus bas subsistent et qu'aucune
validation indépendante n'a eu lieu.

## Ce qui a changé

| Sujet | Avant | Maintenant | Où |
|---|---|---|---|
| Distribution | MC risque-neutre du modèle de pricing | Bootstrap de 5 ans de cours nus quotidiens, une même date tirée pour tous les sous-jacents, ≥ 10 000 simulations (annexe II, points 19-22) | `core/priips_bootstrap.py`, `run_mc(path_simulator=…)` |
| VaR / VEV | `sqrt(−2·ln(p1)/T)` | VaR 97,5 % en espace de prix, actualisée sans risque sous drift risque-neutre ; VEV = (√(3,842 − 2 ln VaR) − 1,96)/√T, T = vie de l'issue retenue si rappel (points 16-17) | `core/priips.py` |
| Table SRI | Transposée et décalée | Lignes CRM, colonnes MRM (point 52) : **MRM 5 / CRM 3 sort en SRI 5, plus 4** | `priips.SRI_TABLE` |
| CRM | Saisi | Note de l'émetteur → rang de qualité de crédit ajusté à la maturité → CRM (points 39-45) ; sans note : 3 si établissement régulé, 5 sinon ; saisie manuelle conservée | `priips.crm_from_credit` |
| Scénarios | Percentiles risque-neutres | P10/P50/P90 sous drift historique observé (annexe IV, point 25) | `api/kid.py` |
| Tension | P1 de la même distribution | Bootstrap sous volatilité stressée (fenêtres 21/63, 99ᵉ/95ᵉ centile), P1 à un an ou moins, P5 au-delà, plafonné au défavorable (points 18, 20, 26-27) | `priips_bootstrap.stressed_volatility` |
| Périodes intermédiaires | Mi-RHP | 1 an si RHP entre 1 et 10 ans ; 1 an et la moitié arrondie au-delà (points 32-34) | `priips.intermediate_periods` |
| Rendement affiché | Annualisé partout | (V/I)^(1/T) − 1 au-delà d'un an, non annualisé en deçà (points 44-45) | `priips.scenario_return` |
| Montants | Bruts | Arrondis à 10 € (point 42), valeur exacte conservée à côté | `priips.round_amount` |
| Coûts | (entrée + sortie) + courants × T | Tableau 1 de l'annexe VII sur le scénario modéré : coûts totaux et réduction de rendement ; tableau 2 simplifié | `priips.costs_over_time`, `cost_composition` |

La simulation risque-neutre reste disponible (`simulation = "risk_neutral_model"`) pour un
produit sans historique exploitable ; le résultat l'affiche alors comme indicatif.

## Contrôle sur données réelles

Autocall worst-of 3 ans sur ^STOXX50E / ^GDAXI (rappel 100 %, coupon 7 %, KI 60 %, émetteur A,
frais d'entrée 1 %, courants 0,5 %), historique Yahoo du 18/11/2021 au 18/11/2026 :
1 256 séances communes, volatilités 17,5 % et 17,3 %.

| | Bootstrap | Risque-neutre |
|---|---|---|
| VEV | 19,59 % | 21,35 % |
| MRM / CRM / SRI | 4 / 2 / 4 | 5 / 2 / 5 |
| Durée | 56 s | 26 s |

En bootstrap, ligne RHP : tension 3 780, défavorable 9 750, modéré 10 540 (rappel à un an),
favorable 11 170. Coûts : 160 €, 1,6 %. **Ce sont des mesures d'instance**, pas des ordres de
grandeur à retenir : le classement MRM 4 / 5 se joue ici à 0,4 point de VEV sous le seuil de 20 %.

Alignement de l'historique vérifié : seules les séances communes sont gardées, sans report de
cours. Sur ^STOXX50E / ^GSPC (calendriers différents), 1 222 dates et aucun rendement nul
injecté.

## Limites — ce qui empêche de parler de conformité

- **Quanto** : la correction du point 22 n'est pas codée ; un sous-jacent dans une autre devise
  que le règlement est refusé en bootstrap (422).
- **Sous-jacents de type courbe** (taux) : non traités.
- **Composition des coûts** : entrée, sortie, courants seulement ; coûts de transaction et
  accessoires non modélisés.
- **Périodes intermédiaires** : scénarios extérieurs à 2 000 × 250 intérieurs, sous les
  10 000 simulations du point 19.
- **Réduction de rendement d'un scénario modéré rappelé** : mesurée sur la vie de ce scénario
  (un an, non annualisée).
- **Aucune validation indépendante** et aucun recoupement contre des KID publiés.

## Tests

`test_priips_rules.py` (arithmétique réglementaire, VEV à la main), `test_priips_bootstrap.py`,
`test_kid_bootstrap.py` (le drift déplace les scénarios mais pas la VaR, la volatilité fait
monter le MRM, ticker manquant → 422, percentile et plafond de la tension, coûts), plus
`test_kid_mrm.py` et les deux fichiers de revue du 24/10 réalignés. 106 tests sur les trois
nouveaux fichiers ; frontend 997 et build.
