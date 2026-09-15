# Audit des conventions de pricing — 08/09/2026

Vérification, règle par règle, que les conventions écrites dans `CLAUDE.md` et
`REPRISE_2026-08-27.md` sont **réellement implémentées**.

**Aucune modification de code.** Cet audit constate, mesure et consigne.

---

## Méthode

Deux niveaux de preuve, et le second seul fait foi :

1. **Lecture** — la mécanique existe-t-elle dans le code, et au bon endroit ?
2. **Mesure** — l'hypothèse **fait-elle bouger le prix**, dans le bon sens et
   dans le bon ordre de grandeur ?

Le second niveau est celui qu'impose `CLAUDE.md` lui-même : *« un test qui ne
vérifie qu'une valeur ne voit pas un fil débranché »*. Une convention peut être
codée et n'être jamais appelée.

**Protocole de mesure.** Même script, même graine (`seed=11`), 40 000 chemins,
une seule hypothèse changée à la fois. Les trajectoires sont alors identiques et
l'écart de prix est imputable à cette hypothèse et à elle seule.

**Produit témoin.** Worst-of autocall 3 ans sur trois sous-jacents
(σ = 15,2 / 12,8 / 28,9 %, ρ = 0,60), constatations annuelles, rappel à 100 %,
coupon 8 %, barrière de perte 60 % en continu, r = 3 %. Prix de référence
**86,5313 %**.

---

## Synthèse

| # | Règle | Source | Lecture | Mesure |
|---|---|---|---|---|
| A1 | Origine de l'axe = strike date | CLAUDE.md | ✅ | ✅ |
| A2 | Actualisation à la date de **paiement** | CLAUDE.md | ✅ | ✅ |
| A3 | Rebasage du PV sur la **value date** | REPRISE | ✅ | ✅ |
| A4 | Value date antérieure au strike gérée | REPRISE | ✅ | ✅ |
| A5 | Échéancier : `dates` / `raw_dates` / `payment_dates` | REPRISE | ✅ | — |
| A6 | Convention de jour ouvré saisie, jamais par défaut | CLAUDE.md | ✅ | — |
| A7 | En cours de vie, origine = date de valorisation | CLAUDE.md | ✅ | — |
| B1 | Courbe de taux → drift **et** actualisation | CLAUDE.md | ✅ | ✅ |
| B2 | Funding → actualisation **seule** | CLAUDE.md | ✅ | ✅ |
| C1 | Fixings en cours **nus** par défaut | CLAUDE.md | ✅ | — |
| C2 | `dividend_profile` : deux voies + `suspect` | CLAUDE.md | ✅ | — |
| C3 | Courbe de dividende atteint le moteur | CLAUDE.md | ✅ | ✅ |
| C4 | Décroissance q₁ × (1−decay)^(n−1) | CLAUDE.md | ✅ | ✅ |
| D1 | Tests exigeant que le prix bouge | CLAUDE.md | ✅ | ✅ |

**Aucune règle n'est débranchée.** Les quatre écarts relevés portent tous sur la
**documentation**, pas sur le code — voir la dernière section.

---

## A — Les quatre dates

### A1 · A3 — Origine strike, prix exprimé à la value date

`engine.py:2025` :

```python
pv_rebase = (1.0 / _df_at_time(df_arr, value_date_t, dt, ts, r_eff)
             if value_date_t else 1.0)
```

Appliqué à chaque flux (`disc * pv_rebase`, lignes 1448, 1488, 1676, 1695), y
compris dans l'évaluateur détaillé. La chaîne complète est donc :

```
prix = [ Σ E[CF_i] × DF(strike → paiement_i) ] / DF(strike → value)
```

Le numérateur vit sur l'axe du moteur, origine strike ; le dénominateur ramène
l'ensemble à la date de valeur.

**Mesuré :**

| value date | prix | écart |
|---|---|---|
| strike + 0 j | 86,5313 % | référence |
| strike + 2 j | 86,5455 % | **+1,42 bps** |
| strike + 5 j | 86,5668 % | **+3,55 bps** |
| strike + 30 j | 86,7449 % | **+21,36 bps** |

Linéaire à **0,71 bps/jour**. Contrôle analytique : 86,53 % × 3 % / 365 =
0,711 bps/jour. **Exact.**

### A4 — Value date antérieure au strike

`_df_at_time` documente le cas : *« Vaut aussi pour t < 0 : exp(+r|t|) > 1, on
capitalise en arrière »*.

**Mesuré :** value date à strike − 5 j → **−3,56 bps**, symétrique parfait du
+3,55 bps à +5 j. La branche fonctionne.

### A2 — Actualisation à la date de paiement

`disc_ev = (disc if t_pay is None else pay_df[t_pay]) * pv_rebase`

**Mesuré**, en décalant le règlement final :

| règlement | prix | écart |
|---|---|---|
| maturité + 0 j | 86,5313 % | référence |
| maturité + 3 j | 86,5226 % | **−0,87 bps** |
| maturité + 4 j | 86,5197 % | **−1,16 bps** |
| maturité + 10 j | 86,5025 % | **−2,88 bps** |

Sens correct : un cash qui tombe plus tard vaut moins. ⚠️ La magnitude ne
reproduit pas les **5,7 bps** annoncés — voir *Écarts*, point 1.

### A5 — Échéancier

`schedule.py:218-225` rend bien `dates`, `raw_dates` et `payment_dates`, ces
dernières construites par `add_business_days(d, settlement_lag, currency)`.
`_dedupe` existe (ligne 230).

### A6 — Convention de jour ouvré

`calendars.py` définit `UnsupportedCurrency(ValueError)` et la lève (ligne 61)
plutôt que de retomber sur « week-ends seulement ». Conforme.

### A7 — Origine en cours de vie

`inlife_valuation.py` porte `realized_flows` et l'ancrage est commenté
explicitement : *« L'ancrage au strike est non négociable : c'est l'origine de
l'axe »*, avec la distinction passé/vie restante (lignes 121, 127, 299, 345).

---

## B — Funding

### B1/B2 — Séparation drift / actualisation

La signature de `run_mc` porte le commentaire décisif :

```python
# Spread emetteur. Actualisation SEULE — voir _funding_df_arr pour
# pourquoi il ne doit surtout pas rejoindre la courbe de taux.
funding_curve=None,
funding_spread: float = 0.0,
```

**Mesuré**, +100 bps sur chacun des deux canaux :

| hypothèse | prix | écart |
|---|---|---|
| référence (r = 3 %, spread 0) | 86,5313 % | — |
| **taux** r = 4 % | 86,1196 % | **−41,17 bps** |
| **spread émetteur** +100 bps | 84,7251 % | **−180,62 bps** |

**C'est la preuve que la séparation tient.** Si le funding rejoignait la courbe
de taux, ses +100 bps produiraient l'effet du taux : −41 bps. Il produit
−181 bps, soit de l'actualisation pure sur une duration d'environ deux ans.

L'écart entre les deux — **+139 bps** — est exactement la contribution du drift
que le taux apporte et que le funding n'apporte pas. Les deux canaux sont
mesurablement distincts.

⚠️ En revanche le **sens** annoncé dans `CLAUDE.md` ne se reproduit pas — voir
*Écarts*, point 2.

---

## C — Dividendes et cours

### C1 — Fixings en cours nus

`market_data.py:131` : `adjusted: bool = False` — le défaut est bien le cours
nu, et la docstring explique que les deux répondent à des questions
différentes. Conforme.

### C2 — Profil de dividende à deux voies

`market_data.py:391-466` calcule `yield_declared` (dividendes réellement
détachés) et `yield_implied` (lu dans l'écart ajusté/nu), puis leur `ecart`.
Conforme.

### C3/C4 — Courbe de dividende et décroissance

**Mesuré :**

| hypothèse | prix | écart |
|---|---|---|
| q = 0, aucune courbe | 86,5313 % | référence |
| q plat 2 % | 83,5725 % | −295,88 bps |
| q plat 4 % | 80,3899 % | −614,14 bps |
| q plat 8 % | 73,2816 % | −1 324,97 bps |
| courbe q₁ = 8 %, decay 0 % | 73,2816 % | −1 324,97 bps |
| courbe q₁ = 8 %, decay 10 % | 74,3790 % | −1 215,23 bps |

Trois constats :

1. **La courbe atteint le moteur** — c'est précisément le fil qui avait été
   trouvé débranché.
2. **Une courbe plate à 8 % donne exactement le même prix qu'un q plat à 8 %**
   (−1 324,97 dans les deux cas) : la courbe est honorée, pas ignorée au profit
   du scalaire.
3. **La décroissance est exacte** — nœuds calculés `[1 → 0,0800]`,
   `[2 → 0,0720]`, `[3 → 0,0648]`, soit q₁ × 0,9^(n−1). L'écart de +110 bps par
   rapport à la courbe plate est cohérent avec un dividende moyen plus faible.

⚠️ La magnitude ne reproduit pas les **−491,6 bps** annoncés — voir *Écarts*,
point 3.

---

## D — « Vérifier qu'une hypothèse PART »

Le principe est appliqué. Exemple type, `test_inlife_pricing.py:222` :

> *« Le prix doit bouger — sinon la courbe est saisie pour rien. »*

D'autres tests raisonnent en mouvement plutôt qu'en valeur :
`test_analytics_calendrier.py:96` (*« si la convention était perdue, ces deux
nombres bougeraient »*), `test_cache_prix.py:82`, `test_calendars.py:70`,
`test_engine_golden.py:116` et `:201` (*« c'est le canari du refactoring »*).

---

## Écarts relevés — tous documentaires

Le code tient. Ce sont **quatre affirmations de la documentation** qui ne
résistent pas à la mesure, et elles se ressemblent : des mesures faites sur **un
produit précis** — la note Marex — écrites comme des faits généraux.

### 1. « L'actualisation au règlement vaut 5,7 bps »

Mesuré ici : **0,87 bps** pour un décalage de 3 jours ouvrés.

Explication probable : la note Marex a un calendrier `CONSTAT` où **chaque
observation** porte sa propre date de règlement, alors que le produit témoin n'a
de décalage que sur le remboursement final. Le chiffre n'est pas faux — il n'est
pas généralisable.

### 2. « Monter la courbe de taux fait MONTER le prix »

Mesuré ici : monter le taux fait **baisser** le prix, de 41 bps pour 100 bps.

| r | prix |
|---|---|
| 2 % | 86,9417 % |
| 3 % | 86,5313 % |
| 4 % | 86,1196 % |
| 5 % | 85,7146 % |

Sur cet autocall, le gain de forward ne compense pas le coût d'actualisation :
le payoff est **plafonné** (pair + coupon au rappel), donc la hausse du forward
augmente la probabilité de rappel sans augmenter le montant reçu, tandis que
l'actualisation frappe tous les flux.

**Ce que cela ne remet pas en cause :** la règle de séparation. L'argument de
`CLAUDE.md` — *« les fondre donnerait le signe inverse »* — est un raccourci
propre à la note Marex. La démonstration générale est celle des **magnitudes**
(−41 contre −181 bps), pas des signes.

### 3. « Une courbe de dividende à 8 % vaut −491,6 bps »

Mesuré ici : **−1 325 bps**, soit 2,7 fois plus. Même cause : dépendance au
produit (maturité, probabilité de rappel, niveau des barrières).

### 4. « Le spread émetteur vaut −0,48 pt / 100 bps »

Mesuré ici : **−1,81 pt / 100 bps**. L'écart s'explique par la duration : −0,48 pt
correspondrait à une duration d'environ six mois, cohérente avec une note en
cours de vie proche de l'échéance ; le produit témoin a une vie espérée de
2,27 ans.

---

## Ce qui n'a pas été vérifié par la mesure

Faute de pouvoir isoler l'hypothèse sans monter un cas complet :

- **A5** — le dédoublonnage `_dedupe` de deux dates qui s'ajustent sur le même
  jour ouvré. Lu, non mesuré.
- **A6** — le comportement de `UnsupportedCurrency` sur une devise absente du
  référentiel. Lu, non mesuré.
- **A7** — le décalage d'origine en cours de vie et le rôle de
  `past.realized_flows`. Lu, non mesuré ; c'est le point le plus coûteux à
  vérifier et le plus exposé, puisqu'il combine les deux axes de temps.
- **C1/C2** — la lecture réelle d'un fixing nu et la levée de `suspect` sur une
  divergence entre les deux rendements. Lu, non mesuré.

---

## Recommandations

1. **Requalifier les quatre chiffres de `CLAUDE.md` en mesures d'instance.**
   Les écrire comme « sur la note Marex, … » plutôt que comme des constantes.
   Un chiffre présenté comme général qu'on ne retrouve pas fait douter de la
   règle qu'il illustre — alors que les quatre règles sont justes.

2. **Reformuler la justification du funding.** Remplacer l'argument du signe par
   celui des magnitudes : *un spread de 100 bps doit coûter nettement plus qu'un
   taux de 100 bps, puisqu'il n'apporte aucun drift.* Cet argument-là est
   général, vérifiable sur n'importe quel produit, et il reste vrai quand les
   deux effets sont de même signe.

3. **Couvrir A7 par une mesure.** L'origine en cours de vie est la seule règle
   non négociable qui ne soit vérifiée que par lecture, et c'est celle qui a
   produit le plus d'erreurs pendant le chantier des 26-27/08 — cinq fois dans
   une seule session, selon `CLAUDE.md`.
