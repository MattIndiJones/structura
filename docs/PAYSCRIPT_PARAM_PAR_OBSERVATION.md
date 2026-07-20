# PARAM à valeurs multiples, une par observation — IMPLÉMENTÉ

> Statut : **implémenté le 2026-07-18**, avec un design différent de l'idée initiale ci-dessous :
> pas de littéral tableau dans le script, mais une déclaration `PARAM() NOM [= seed%]` (symétrie
> avec `CONSTAT()`) dont les valeurs se saisissent dans l'UI sous le script, une ligne par
> observation. Règles : la dernière ligne s'étend aux observations suivantes (une ligne = valeur
> constante, équivalent exact d'un PARAM scalaire — vérifié au tick près en MC), les lignes en
> trop sont ignorées, `AT MATURITY` prend la ligne de la dernière observation (INDEX inchangé).
> Résolution au lookup (`_pobs` dans parser.py) — un seul point, hérité par MC/greeks/backtest/
> replay historique. Implémenté en même temps : la convention `M_` (PARAM préfixé = surveillé par
> la watchlist Booking, direction et observable déduits de l'usage réel dans le script — voir
> `_analyze_monitors`), la migration de tous les templates, et le gel des `user_params` dans le
> snapshot de booking (`market_snapshot.user_params`, unités stockées). Tests dans
> `test_parser.py` (§ PARAM() & convention M_). Le texte d'origine est conservé ci-dessous pour
> l'historique de la décision.

## Constat

Aujourd'hui, un `PARAM` dans un script (`PARAM AC_BAR = 100%`, `PARAM COUPON = 8%`, `PARAM KI_BAR
= 60%`...) est une seule valeur scalaire, appliquée identiquement à chaque observation `AT`. Or
sur un vrai termsheet, il est courant que ces paramètres varient d'une observation à l'autre :

- barrière de rappel autocall **dégressive** (105% → 100% → 95%... plus facile à atteindre avec le
  temps)
- coupon **progressif** (6% → 7% → 8%... plus généreux à mesure qu'on avance)
- barrière de KI qui peut elle aussi différer d'une fenêtre d'observation à l'autre sur certains
  produits

Le moteur actuel n'a aucun moyen d'exprimer ça — il faudrait dupliquer la logique `AT` à la main
avec une constante différente à chaque bloc, ce qui casse l'usage de `PARAM` (plus de surcharge
possible depuis l'UI, plus de lisibilité).

## Idée proposée

Permettre à **n'importe quel** `PARAM` d'être déclaré comme une liste plutôt qu'un scalaire,
résolue positionnellement par index d'observation (dans l'ordre des `AT` du script) :

```
PARAM AC_BAR = [105%, 100%, 95%]
PARAM COUPON = [6%, 7%, 8%]
```

À l'observation `AT 1`, le moteur utiliserait `AC_BAR[0]` et `COUPON[0]` ; à `AT 2`,
`AC_BAR[1]`/`COUPON[1]` ; etc. Un `PARAM` resterait scalaire (comportement actuel inchangé) si sa
valeur n'est pas un littéral tableau — pas de rupture pour les scripts existants.

## Ce que ça toucherait (à creuser le moment venu)

- **Parser** (`core/payscript/parser.py`) : nouvelle syntaxe de littéral tableau pour `PARAM`,
  validation de la longueur (doit correspondre au nombre d'observations `AT`, ou lever une erreur
  claire sinon).
- **Moteur** (`core/payscript/engine.py`) : résolution de la valeur du `PARAM` par index
  d'observation au lieu d'une valeur unique injectée dans `ctx["memo"]`.
- **UI** (`PayScriptEditor.vue`, bloc "Paramètres du script") : les inputs dynamiques de `PARAM`
  devraient afficher un champ par observation quand le paramètre est de type liste, plutôt qu'un
  seul input — implique aussi de repenser `paramOverrides` (aujourd'hui `{name: valeur}`, il
  faudrait `{name: [valeurs...]}` pour ces cas-là).
- **Backtest / historique** (`eval_script_on_history`) : doit lire la bonne valeur du tableau à
  chaque étape rejouée, pas juste la valeur scalaire actuelle.

## Pourquoi ce n'est pas fait maintenant

Le chantier en cours (booking, cycle de vie, évaluation automatique callé/KI/final, page
Booking) est prioritaire et sans lien direct avec cette fonctionnalité — mélanger les deux
augmenterait le risque de régression sur ce qui vient d'être stabilisé. Cette idée n'a pas
vocation à être perdue, juste à attendre son tour.
