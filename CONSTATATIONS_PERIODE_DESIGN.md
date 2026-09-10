# Constatations sur période — note de conception

**Date** : 2026-09-10 · **État** : **codée**, backend + frontend + tests
(§11 pour ce qui a divergé de la conception à l'implémentation ;
§12 pour la seconde vague — fenêtre de période, deux lectures d'une date,
aperçu des dates)
**Origine** : un call panier 3 sous-jacents, strike moyenné 10 jours, niveau final
moyenné 30 jours. Le produit n'est pas exprimable aujourd'hui.

---

## 1. La règle

Pour chaque sous-jacent *i*, **séparément** :

| | |
|---|---|
| `S0_i` | `MIN` / `MAX` / `AVG` de ses cours sur la **fenêtre de départ** |
| `SF_i` | `MIN` / `MAX` / `AVG` de ses cours sur la **fenêtre d'observation** |
| `yield_i` | `SF_i / S0_i` |

**Ensuite seulement**, l'agrégation : `WOF = min(yield_i)`, `BOF = max(yield_i)`,
`BASKET = moyenne(yield_i)`.

La réduction est **toujours par sous-jacent**, jamais sur l'agrégat. C'est le point
qui fait toute la conception : `min` et `moyenne` ne commutent pas, et le moteur
actuel fait la moyenne du worst-of là où le contrat demande le worst-of des moyennes.

## 2. Ce que fait le moteur aujourd'hui

Le tenseur `S[t, i, p] = spot_i(t) / spot_i(0)` est **déjà normalisé par
sous-jacent**, et `WOF = S[1:].min(axis=1)` agrège **déjà** sur l'axe des actifs.
L'agrégation par actif est donc correcte et ne bouge pas.

Ce qui est câblé en dur, c'est que **les deux termes du rapport sont des points** :
le dénominateur est `spot_i(0)`, le numérateur à une observation est `spot_i(t)`.

**Le comportement actuel est le cas dégénéré de la règle, fenêtre = 1 point.** Il n'y
a donc pas deux mécanismes à faire cohabiter : il y en a un, dont l'actuel est le cas
trivial.

Le contournement en place — `CONSTAT() STRIKE_FIX` + `FIX_MIN`/`FIX_MAX`/`FIX_AVG`,
puis `SET REF = FIX_AVG` et `PERF = WOF / REF` — n'existe que parce que le
dénominateur est figé, et il réduit le **worst-of** au lieu de chaque actif. Il
disparaît.

## 3. Syntaxe

### 3.1 Ligne de partage

**Ce qui change le payoff est dans le script. Ce qui change les dates est dans le
CONSTAT, saisi à l'écran.**

`MIN` et `AVG` ne sont pas le même produit → script.
10 jours ou 30 jours est une donnée de term sheet, au même titre qu'une date de
maturité → panneau CONSTAT.

Conséquence directe : passer une fenêtre de 10 à 30 jours **ne touche pas une ligne
du script**, et deux deals issus du même template peuvent porter des fenêtres
différentes. Avec la longueur écrite en dur dans le script, ils auraient été deux
scripts distincts — ce qui aurait cassé les templates et le RFQ.

### 3.2 Dans le script

La réduction se pose **sur la date de constatation**, parce que c'est elle qui porte
les dates et qu'un autocall doit pouvoir donner une fenêtre propre à chaque
observation :

```
CONSTAT   STRIKE_FIX   AVG        # S0_i = moyenne de la fenêtre de départ
CONSTAT   MATURITE     AVG        # SF_i = moyenne de la fenêtre finale
CONSTAT() OBSERVATIONS MIN        # chaque date du calendrier porte sa fenêtre
```

Réduction absente = un point, comportement actuel inchangé.

`STRIKE_FIX` reste le nom réservé qui produit `S0_i`.

La réduction se pose **uniquement sur un `CONSTAT`**, jamais sur un bloc `AT`
littéral : `AT 3 AVG:` n'aurait aucun endroit où porter la longueur de sa
fenêtre, puisque celle-ci se saisit dans le panneau du CONSTAT. Un produit à
constatation sur période déclare donc toujours un CONSTAT — ce qui est de toute
façon ce que fait un term sheet.

### 3.3 Le produit qui a lancé le chantier

```
PARAM STRIKE = 100%

CONSTAT STRIKE_FIX  AVG
CONSTAT MATURITE    AVG

AT MATURITE:
  PAY MAX(0, BASKET - STRIKE) "Call panier, strike et final moyennés"
```

À l'écran : fenêtre de départ 10 jours ouvrés, fenêtre finale 30 jours ouvrés.
`BASKET` vaut la moyenne des `SF_i/S0_i`. Remplacer `BASKET` par `WOF` ou `BOF` donne
le worst-of ou le best-of, sans rien changer d'autre. Remplacer `AVG` par `MIN` sur la
première ligne donne un strike lookback.

### 3.4 Sens des fenêtres

- La fenêtre de **départ part** de la date de strike et va vers l'avant.
- Toute autre fenêtre **arrive** à sa date de constatation, incluse, en regardant vers
  l'arrière.

On regarde en avant au départ, en arrière à l'arrivée. L'origine de l'axe des temps
reste le **strike**, premier jour de la fenêtre de départ : la convention des quatre
dates du `CLAUDE.md` n'est pas touchée.

### 3.5 Dans le panneau CONSTAT (UI)

Une fenêtre de constatation **est un mini-calendrier**, décrit avec les champs que le
panneau sait déjà afficher :

| champ | exemple |
|---|---|
| longueur | `10D`, `3M`, `1Y` |
| fréquence d'échantillonnage | `1D`, `1W`, `1M` |
| convention de jour ouvré | héritée du CONSTAT, référentiel `core/calendars.py` |

Longueur et fréquence sont **deux champs distincts** : « les 3 derniers mois relevés
chaque jour » et « les 3 derniers mois relevés chaque mois » sont deux produits, et il
faut pouvoir dire lequel. C'est cette séparation qui lève l'ambiguïté du suffixe — `M`
comme longueur et `M` comme fréquence ne se rencontrent jamais dans le même champ.
Toutes les unités `D`/`W`/`M`/`Y` sont acceptées des deux côtés.

Un CONSTAT sans fenêtre saisie reste une date ponctuelle.

## 4. Sémantique moteur — les substitutions

Quatre points d'accroche, et rien d'autre ne bouge.

**(a) Dénominateur.** `_fixer_le_strike_sur_les_trajectoires(S, k)` divise déjà tout
le tenseur par `S[k]`, une référence par chemin et par actif — écrit pour le
forward-start mono-date. Il faut qu'il divise par la **réduction de la fenêtre de
départ** au lieu du point `S[k]`. La forme de l'opération ne change pas.

**(b) Numérateur.** À une observation portant une fenêtre, le vecteur de spots passé à
l'évaluateur devient la réduction de cette fenêtre, par actif, calculée **avant** la
boucle par chemin. `WOF`/`BOF`/`BASKET`/`S[i]` s'appliquent ensuite sans savoir qu'une
réduction a eu lieu.

**(c) Extrema.** `WOF_MIN`, `BOF_MAX`, `S_MIN[i]`, `S_MAX[i]` ne commencent à
accumuler qu'à la **fin de la fenêtre de départ** : sans `S0`, une observation
américaine n'a pas de sens — il n'y a rien à comparer. Le paramètre existe déjà, c'est
`state_start_step`, aujourd'hui alimenté par `strike_step`.

**(d) Bump différé.** Déjà conforme : `_apply_delayed_bump` applique le ratio de bump à
partir de `fix_end_step = max(_strike_fix_steps(...))`, donc après la fermeture de la
fenêtre. C'est ce qui empêche le bump de se simplifier dans `SF/S0` et de rendre un
delta nul. Rien à refaire, seulement à rebrancher sur la nouvelle fenêtre.

**Ordre des opérations.** La réduction vient **après** la simulation, jamais pendant —
même raison que pour le fixing forward-start : les vols locales doivent avoir été lues
aux vrais niveaux, faute de quoi le delta de smile disparaît.

## 5. Granularité — mesuré, pas supposé

La grille de simulation est hebdomadaire (`SY = 52`). Une fenêtre de 10 jours ouvrés
tombe sur 2 pas, une de 30 jours sur 6.

**Sonde** (call panier 3 actifs, σ 25 %, r 3 %, 1 an, ρ 0,5, K = 100 %, GBM, CRN) :

| | prix | effet |
|---|---|---|
| constatations ponctuelles | 9,58 % | — |
| strike moyenné 10j seul | 9,40 % | −17 bps |
| final moyenné 30j seul | 9,16 % | −42 bps |
| **10j + 30j** | **8,98 %** | **−60 bps** |
| le même, échantillonné sur la grille hebdo | 9,00 % | **+2 bps** |

**L'écart de grille est de 1 à 2 bps.** La grille hebdomadaire suffit : le raffinement
local (grille non uniforme, refactor de tout ce qui fait `round(d * SY)`) est
**écarté**.

> Ces chiffres sont des **mesures d'instance**, pas des constantes — même
> avertissement que pour les quatre magnitudes requalifiées le 08/09/2026. Ils valent
> pour ce panier, cette vol, cette maturité. Ce qui se généralise, ce sont les règles,
> pas les nombres.

Deux ordres de grandeur à garder pour se repérer, mesurés sur les mêmes sondes :

- **agrégation ≫ moyennage.** Mêmes fenêtres, ρ 0,5 : worst-of 3,28 %, panier 8,98 %,
  best-of 19,85 %. Le choix `WOF`/`BASKET`/`BOF` est du premier ordre, le moyennage du
  troisième.
- **la commutativité protège le panier, pas le worst-of.** Sur un panier, moyenner
  puis agréger ou l'inverse donne 1 bp d'écart. Sur un worst-of 2 actifs, 60 à 122 bps
  selon la corrélation, avec un **biais systématique** : `moyenne(min) ≤ min(moyennes)`
  toujours, donc le call ressort trop cher et le put trop bon marché. C'est le défaut
  que la conception ferme par construction.

## 6. Fenêtre trop courte : avertir, pas refuser

Une fenêtre de moins d'une semaine se réduit à un seul pas de grille. **On ne refuse
pas la compilation** — un moyennage 3 jours se vend, et bloquer un produit réel est
absurde.

L'erreur commise est **bornée par l'effet du moyennage lui-même**, qui tend vers zéro
quand la fenêtre raccourcit : 10 jours valent −17 bps sur la sonde ci-dessus, 3 jours
sont sous les 10 bps. Ce n'est pas un prix faux qui se cache, c'est un effet qui n'a
pas eu lieu.

**Message exigé** : le nombre de points **réellement retenus**, affiché pour toutes les
fenêtres et pas seulement les courtes —

> Fenêtre 3 jours ouvrés → **1 point de grille retenu sur 3 demandés**

Une alerte générique se clique sans lire ; un décompte se lit. La règle A7 du
`CLAUDE.md` s'applique ici : ce qui doit se voir, c'est qu'un fil est débranché.

**Pont brownien — second temps, et sur `MIN`/`MAX` seulement.** Le moteur en a déjà un
pour les barrières (`barrier_monitoring="continuous"`, `bridge_min`/`bridge_max`) et il
calcule exactement l'extrême entre deux pas : ce serait la réponse juste à peu de
frais. Il ne sert à rien pour `AVG` — un pont donne un min et un max, pas une moyenne ;
il faudrait en intégrer la loi, exacte sous GBM, approchée sous Heston et Dupire. À
savoir avant de s'y engager : **le Mark-to-Future refuse déjà les barrières continues**
(`_mtf_reject_unsupported`), donc ce chemin rendrait ces produits non-MTF-ables.

## 7. Ce qui disparaît, et la migration

Sortent du langage : `FIX_MIN`, `FIX_MAX`, `FIX_AVG`.

Deux templates les portent et doivent être réécrits — `autocall_gear_put` et
`autocall_gear_put_worst_of`. Ils perdent `SET REF = FIX_AVG` et
`SET PERF = WOF / REF` : `WOF` **est** la performance.

Le second corrige au passage un vrai défaut de prix : son put vendu est aujourd'hui
sous-évalué d'environ 100 bps sur un worst-of 2 actifs, donc son coupon sort trop
généreux.

**Rétrocompatibilité non requise** — ce qui est booké est du test. Cela autorise à
redéfinir la sémantique de `spots` plutôt qu'à empiler une option, ce qui est ce qui
rend toute la conception petite. En contrepartie il faut assumer explicitement :

- les **goldens** sont à regénérer, et il faut dire lesquels ont bougé et de combien ;
- les magnitudes citées dans `CLAUDE.md` et les rapports d'audit qui reposent sur
  `FIX_*` ne valent plus.

## 8. Points de contact

**Backend — `core/payscript/parser.py`**
- `Constat` (l. 170) : ne porte que `name` et `kind` → ajouter la réduction.
- `MARKET_VARS` (l. 73) : retirer les trois `FIX_*`. `RESERVED_NAMES` en dépend.
- `resolve_constats` (l. 809, 924) : résout `strike_fix_dates` → doit résoudre une
  fenêtre par constatation, pas seulement celle du strike.
- `CompiledScript.strike_fix_dates` (l. 194) → structure de fenêtres.

**Backend — `core/payscript/engine.py`**
- `_strike_fix_steps` (l. 1120), `_compute_strike_fix` (l. 1131) → réduction par actif.
- `_fixer_le_strike_sur_les_trajectoires` (l. 1207) : substitution (a).
- `_running_state` / `_RunningState` (l. 1195-1240) : `state_start_step` pour (c).
- `_eval_paths` (l. 1335) et `_eval_paths_detailed` (l. 1594) : les **deux**
  évaluateurs, qui ont déjà divergé une fois sur l'héritage d'état.
- `_apply_delayed_bump` (l. 1962) : rebrancher sur la fin de fenêtre.
- `_mtf_realized_fix` (l. 2937) : split de la fenêtre au mark, par actif.
- `eval_script_on_history` (l. 3745-3830) : rejeu in-life, grille **quotidienne**
  (`SY_H = 252`). Les séries par actif y sont déjà disponibles à côté de `wof_vals`.

**Backend — divers**
- `core/inlife_valuation.py:481` : `residual_fix`, split passé/futur de la fenêtre.
- `core/schedule.py` : `parse_tenor`, `generate_schedule` — longueur **et** fréquence.

**Frontend**
- `components/DealTab.vue` (l. 397-490) : panneau CONSTAT, champs de fenêtre.
- `stores/pricing.js` : `_constatsFrom` — forme stockée `{value, unit}` vers la forme
  serveur `"1M"`. Le même piège attend les champs de fenêtre.
- `components/PayScriptEditor.vue` (l. 450, 470) : aide du langage.
- `data/payscriptTemplates.js` : les deux gear put, plus les nouveaux templates.

**Documentation et garde-fous**
- `docs/PAYSCRIPT_REFERENCE.md` : sous **test anti-dérive** — un mot ajouté sans
  documentation, ou documenté sans exister, casse la construction.
- Prompt de l'assistant IA : même vocabulaire.

**Tests existants qui portent sur `FIX_*`**
- `backend/tests/test_engine.py` (l. 1286, 1350) : fenêtres réalisées, totale et
  partielle.
- `backend/tests/test_spot_baseline.py` : l'oracle du bump différé — un payoff en ratio
  est indépendant du niveau de seeding. **À conserver tel quel** : il reste vrai et il
  protège le delta.
- `backend/tests/test_mtf_audit_2026_08_03.py` (l. 144).

## 9. Tests exigés

**Règle A7 : écrire des tests qui exigent que le prix BOUGE.** Un test qui ne vérifie
qu'une valeur ne voit pas un fil débranché — et cette conception ajoute exactement le
genre d'hypothèse qui a déjà été saisissable sans effet sur le prix.

1. `MIN`, `MAX` et `AVG` sur la même fenêtre donnent **trois prix distincts**, dans
   l'ordre attendu pour un call : `MIN` > `AVG` > `MAX` (le strike le plus bas vaut le
   call le plus cher).
2. Allonger une fenêtre **déplace** le prix, et dans le bon sens.
3. **Non-commutativité sur worst-of** : réduire par actif puis agréger diffère de
   l'inverse, l'écart est du bon signe (`moyenne(min) ≤ min(moyennes)`), et il
   **s'annule** sur un panier. C'est le test qui protège la règle centrale.
4. Fenêtre = 1 point : le prix est **identique** au comportement actuel. C'est le test
   de non-régression du cas dégénéré.
5. Extrema : une barrière franchie **pendant** la fenêtre de départ n'a **aucun** effet
   sur le prix.
6. Le décompte de points retenus est exposé, et il vaut le nombre demandé sur une
   fenêtre normale, moins que demandé sur une fenêtre trop courte.
7. In-life : une fenêtre à moitié réalisée combine passé et futur avec le bon poids —
   pas de double comptage, pas de retour au neutre `1.0`.

Portée pytest : `backend/tests/test_engine.py`, `test_spot_baseline.py`,
`test_mtf_audit_2026_08_03.py` et le fichier neuf. **Pas la suite complète** sans
demande explicite.

## 10. Reste ouvert

- **Poids du panier** : `BASKET(w1, w2, w3)` existe déjà et s'applique aux `yield_i`
  sans rien changer. Rien à décider, à confirmer seulement.
- **Fenêtre de départ et date de valeur** : la fenêtre part du strike, le prix
  s'exprime à la date de valeur. Rien ne change, mais à re-vérifier une fois codé —
  l'ancrage sur le strike plutôt que sur la value date est l'erreur qui est revenue
  cinq fois en une session.
- **Pont brownien `MIN`/`MAX`** : second temps, si le besoin de fenêtres courtes se
  présente réellement.

---

## 11. Ce que l'implémentation a appris

**Le golden asiatique n'a pas bougé, et c'est la meilleure validation qu'on
pouvait avoir.** `test_prix_inchange_fenetre_strike_fix` reprend au bit près sa
valeur d'avant le chantier (0.988224). Sur un mono sous-jacent, réduire chaque
actif puis agréger et faire l'inverse coïncident : le rebasage par le moteur
reproduit donc exactement ce que le script faisait à la main avec
`WOF / FIX_AVG`. L'écart n'apparaît qu'à partir de deux sous-jacents — c'est-à-dire
exactement là où était le défaut.

**Un décalage d'indice a failli passer.** La réduction héritait de l'ancien code
son indexation en `k-1` : elle réduisait sur `WOF`, qui part du pas 1, là où le
tenseur `S` a le pas `k` en rangée `k`. Toute fenêtre lisait donc une semaine
trop tôt. Ce qui l'a attrapé n'est ni une relecture ni un test de valeur, mais
le test du **cas dégénéré** — une fenêtre d'un seul point doit rendre exactement
le prix ponctuel. Un test qui n'aurait vérifié qu'un prix plausible n'aurait
rien vu.

**Deux tenseurs, pas un.** Les niveaux constatés et la trajectoire réelle vivent
séparément (`S_obs` et `S`). Les extrema courants et la vol réalisée continuent
de lire le chemin : une barrière américaine regarde des cours, pas des moyennes,
et `REALVOL` calculé sur une série lissée serait artificiellement basse.

**Les corrections annexes, prises au passage :**
- `resolve_constats` perdait les `monitors` du script — la watchlist Booking
  reposait dessus.
- `_shift_events_for_mtf` ne décalait pas les fenêtres avec leurs dates, ce qui
  aurait repricé toute observation résiduelle comme un point.

**Ce qui n'a pas été fait :** le pont brownien pour `MIN`/`MAX` sur fenêtre
courte, laissé au second temps comme prévu au §6.

---

## 12. Seconde vague — période, double lecture, aperçu

Trois manques apparus à l'usage, une fois la première vague en main.

### 12.1 La constatation appartient à l'événement, pas au pas de temps

La première vague attachait le niveau constaté au **pas de grille** : un seul
niveau par date, et deux blocs `AT` tombant le même jour avec des conventions
différentes étaient refusés. Or c'est un produit parfaitement ordinaire —
**coupon sur la moyenne, protection sur le cours de clôture**, même date.

Le niveau est désormais porté par l'événement, aligné index par index sur
`step_map` exactement comme `pay_map` l'est déjà. Chaque bloc pose son niveau
juste avant de s'exécuter ; `None` veut dire « le cours du jour », ce qui est le
cas de l'écrasante majorité des événements et ne coûte rien. Effet de bord
bienvenu : on ne recopie plus le tenseur entier, seules les rares entrées à
fenêtre matérialisent un tableau `(n, N)`.

### 12.2 `PERIOD` — la fenêtre est la période, pas une longueur

```
CONSTAT() OBSERVATIONS AVG PERIOD
```

Trois constatations annuelles, chacune moyennée sur les relevés de son année.
Il n'y a pas de longueur à saisir : le calendrier la porte, seule la fréquence
de relevé reste à l'écran.

**Pourquoi pas `CONSTAT()()`.** La première idée était de détourner la
sous-fréquence d'un `CONSTAT()()`. Rejetée sur objection de Philippe, et il
avait raison : le sens de la sous-fréquence aurait dépendu d'un mot écrit trois
tokens plus loin, et un lecteur voyant « calendrier sous-fréquencé » n'aurait
pas deviné que la sous-fréquence *était* la moyenne. `CONSTAT()()` garde donc
son sens intact — la sous-fréquence y produit des observations — et `PERIOD`
dit ce qu'il fait. Deux mots pour deux choses.

**Bornes** : ouvertes à gauche, fermées à droite. Une date de roll appartient à
la période qui s'achève, jamais aux deux, sinon elle pèserait double dans la
moyenne. Le start du calendrier n'entre dans aucune fenêtre — c'est le bon
comportement : la moyenne d'une période porte sur ses relevés, pas sur le cours
du jour d'émission.

**Un piège évité de justesse** : construire la fenêtre en remontant pas à pas
depuis la date de constatation donne un résultat faux, parce que cette date est
déjà roulée sur un jour ouvré — remonter de 3M depuis un lundi qui était un
dimanche décale toute la fenêtre, et le décalage se propage. Mesuré : une
période sortait à 5 relevés au lieu de 4. `period_windows` bâtit donc la
fenêtre sur la grille du calendrier lui-même, qui roule d'abord sur les dates
brutes puis ajuste — l'ordre du marché, et le seul qui garde un trimestriel
trimestriel.

### 12.3 Deux lectures d'une même date

```
AT OBSERVATIONS:            → la constatation, donc la moyenne
AT OBSERVATIONS.last.last:  → son dernier relevé, donc le cours
```

Un **second** qualificateur descend du calendrier vers la fenêtre. Un niveau
désigne une constatation et lit ce que le CONSTAT déclare ; deux désignent un
fixing et lisent le cours brut.

L'alternative était deux `CONSTAT` distincts. Écartée pour une raison concrète :
ce sont alors **deux dates saisies séparément**, qui peuvent cesser de coïncider
sans que rien ne le signale. Le besoin n'était pas deux dates, c'était deux
lectures d'une même date. Deux `CONSTAT` restent nécessaires dans le seul cas où
les dates diffèrent réellement — un PDI constaté à maturité quand le dernier
rappel l'est quelques jours avant.

Le `STOP` du bloc de rappel court-circuite le bloc de relevé au même pas : si le
produit est rappelé, le PDI ne s'évalue pas. C'est le mécanisme déjà en place
pour deux blocs à la même date, et c'est le comportement voulu.

Mesuré sur un autocall 3 ans worst-of 2 actifs, coupon sur moyenne trimestrielle :
PDI sur moyenne **92,33 %**, PDI sur clôture **90,77 %** — **156 bps**, dans le
bon sens, le PDI sur clôture n'étant lissé par rien.

### 12.4 L'aperçu des dates

`POST /api/schedule/window` rend les dates qu'une fenêtre retient réellement, et
le panneau CONSTAT les affiche en clair : « du 10/09/2026 au 23/09/2026 ·
10 relevés ». Un term sheet dit « du 10 au 20 septembre », l'écran attend une
longueur en jours ouvrés, et les deux ne tombent pas au même endroit — 10 jours
ouvrés depuis le 10/09 vont jusqu'au 23, parce qu'ils sautent deux week-ends.
Convertir de tête est une erreur silencieuse ; l'aperçu la supprime.

À ne pas confondre avec le décompte publié **après** pricing
(`constatation_windows`), qui répond à une autre question : ce que la grille
hebdomadaire du moteur a effectivement su représenter.

### 12.5 Deux défauts d'écran, et une leçon de vérification

**Le champ qui disparaissait.** La condition d'affichage du bloc de fenêtre
testait `window_length` — précisément la valeur qui vaut `null` en mode
période. Le seul champ à saisir dans ce mode était donc masqué par la condition
censée l'afficher. La condition porte maintenant sur `window_frequency`, qui est
toujours présente.

**L'échéancier qui ne se régénérait plus.** Le watcher surveillait un getter
renvoyant un **tableau littéral** : Vue compare le retour avec `Object.is`, et
deux tableaux distincts ne sont jamais égaux, si bien que le watcher se
déclenchait à chaque invalidation réactive et relançait sans fin son debounce de
400 ms. L'appel ne partait jamais. La signature est redevenue scalaire, et
l'ouverture recharge désormais quand les paramètres ont bougé depuis le dernier
calcul — se fier à la seule présence de données laissait afficher un échéancier
périmé, dont les relevés ne correspondaient plus aux constatations affichées
juste au-dessus.

**La leçon** : la première vérification de cet échéancier avait été faite en
forçant `details.open = true` puis en dispatchant un `toggle` — donc sans jamais
emprunter le chemin de l'utilisateur. Le rendu était juste et le bug invisible.
Une vérification qui contourne l'interaction ne vérifie pas l'interaction. Le
second passage a cliqué, replié, modifié une date, redéplié : c'est là que le
défaut est apparu.

### 12.6 Ce qui reste ouvert

Inchangé depuis le §10, plus deux points. Le front n'a **pas** de tests de
composants (tout est testé au niveau des stores et des composables) : les deux
défauts ci-dessus sont donc couverts par un commentaire dans le code et par la
vérification manuelle, pas par un test. Et `.first`/`.last` désignent la première
et la dernière **constatation** d'un calendrier, jamais son `start_date` — qui
n'est pas une observation. Un yield « depuis le strike » ne s'écrit donc pas
`WOF / REF` avec `REF` posé au `.first`, mais directement `WOF - 1`, puisque le
moteur exprime déjà tout en pourcentage de `S0`.

---

## 13. `INDEX` par échéancier — **codé**

Décisions prises avec Philippe le 10/09/2026, appliquées le même jour. Les trois
défauts ci-dessous ont d'abord été figés en tests `xfail(strict=True)` dans
`test_caracterisation_echeancier.py` ; la correction les a rendus verts, et
`strict` a fait échouer la suite jusqu'à ce que les marqueurs soient retirés.

### 13.1 Les défauts, mesurés avant correction

`INDEX` s'incrémente aujourd'hui une fois par **pas de grille portant un
événement**, et non par constatation. Deux mesures sur un `PAY INDEX` :

| situation | attendu | réel |
|---|---|---|
| deux calendriers (coupons 1Y + suivi 6M) | 1 · 2 · 3 | **2 · 4 · 6** |
| un bloc ajouté sur une sous-date (`AT OBS[2][1]`) | 1 · 2 · 3 | **1 · 3 · 4** |

Le second calendrier double le compteur du premier ; un bloc posé sur un relevé
décale toutes les constatations suivantes. Un `COUPON * INDEX` paie faux, et un
`PARAM()` par observation lit la mauvaise ligne. Rien ne le signale.

Le premier cas n'a **rien à voir** avec les constatations sur période : il est
là depuis que deux calendriers peuvent coexister.

### 13.2 La règle

> `INDEX` est le **rang de la date dans l'échéancier que le bloc nomme**.

`AT OBSERVATIONS:` boucle sur les dates **principales** — les sous-dates sont
des relevés qui alimentent une réduction, jamais des observations. Trois dates
principales donnent 1, 2, 3, que ces dates portent ou non des relevés.

**Le rang est une propriété de la DATE, pas un compteur d'exécution.** Il est
figé à la résolution du calendrier et voyage avec la date. Conséquence directe :
`index_offset` disparaît. Le MtM résiduel n'a plus de compteur à hériter — la
troisième date porte le rang 3, qu'on la price neuve ou à mi-vie —, et avec lui
s'en va la classe de bugs de l'héritage manquant (un autocall qui payait 5 % au
lieu de 15 %).

### 13.3 Les cas tranchés

| écriture | `INDEX` | pourquoi |
|---|---|---|
| `AT OBSERVATIONS:` | 1, 2, 3 | rang dans le calendrier |
| `AT OBSERVATIONS.last:` | **3** | rang dans le CALENDRIER, pas dans le bloc — sinon l'idiome Athena (dernier coupon `COUPON * INDEX`) casse |
| `AT OBSERVATIONS[2][1]:` | **2** | le rang de la constatation parente : le bloc parle du 2ᵉ coupon même s'il lit un relevé |
| `AT 1, 2, 3:` (mode normal) | 1, 2, 3 | le calendrier est la liste de dates du bloc |
| `AT MATURITY:` (mot-clé) | **refusé** | ce bloc ne nomme aucun échéancier, donc n'a pas de rang. Aucun script du corpus n'y lit `INDEX` : autant fermer le trou plutôt que le documenter. Le message renvoie vers `AT <Calendrier>.last:` |

**`INDEX` est indépendant par échéancier.** Si `MATURITE` (date unique) tombe le
même jour que la 3ᵉ date d'`OBSERVATIONS`, alors `AT OBSERVATIONS:` y voit 3 et
`AT MATURITE:` y voit 1. Deux façons d'écrire la même date, deux sémantiques, et
c'est le nom du calendrier qui tranche.

### 13.4 Ce qui en découle

**`PARAM()` doit être refusé s'il est lu depuis deux calendriers différents.**
« Une valeur par observation » n'a plus de nombre de lignes défini si le même
paramètre sert dans deux blocs rattachés à des échéanciers de tailles
différentes. Refuser à la compilation, avec un message qui dit quoi faire
(dupliquer le paramètre, ou passer par `.last`), plutôt que deviner. Une syntaxe
explicite — `PARAM(OBSERVATIONS) BARRIERE` — reste possible si le besoin se
présente vraiment.

**Pas de compteur de passages dans le langage.** L'idée d'une seconde variable
s'incrémentant à chaque exécution a été écartée : elle vaudrait la même chose
qu'`INDEX` dans le cas courant et divergerait précisément là où ça coûte cher —
elle repart à 1 en vie résiduelle (le bug `index_offset` sous un autre nom),
compte double quand deux blocs partagent une date, et vaut 1 sur un bloc
qualifié là où `INDEX` vaut 3. Deux variables presque toujours égales sont pires
qu'une seule. Un script qui veut compter autre chose — coupons versés,
observations sous barrière — l'écrit avec `SET`, où l'auteur dit explicitement
ce qu'il compte ; c'est déjà possible et vérifié.

**Deux CONSTAT pour une même date restent déconseillés.** Quand la maturité EST
la dernière observation, `AT OBSERVATIONS.last:` vaut mieux qu'un CONSTAT
séparé : deux CONSTAT, ce sont deux dates saisies indépendamment, qu'un roll ou
une convention peuvent faire diverger sans que rien ne le signale. Même argument
que pour `.last.last` contre deux CONSTAT au §12.3.

---

## 14. Ordre de réalisation

Arrêté avec Philippe le 10/09/2026. Le moteur Monte-Carlo reste **hors
périmètre** tant qu'un test ne démontre pas un défaut précis.

1. ~~**Tests de caractérisation**~~ — **fait**. Le comportement actuel, figé avant
   toute modification. Partir de `backend/tests/test_constatations_periode.py`, qui
   couvre déjà le ponctuel contre fenêtre d'un point, MIN/MAX/AVG, la réduction
   par sous-jacent avant worst-of et les deux lectures d'une même date. À
   ajouter : `INDEX` à deux calendriers, `INDEX` avec un bloc sur une sous-date,
   un événement sur une sous-date ne coïncidant avec aucune constatation, et un
   `STOP` entre deux blocs du même jour. **Les deux premiers échoueront** — c'est
   ce qui autorise à ouvrir le moteur, et rien d'autre.
2. ~~**`INDEX` par échéancier**~~ (§13) — **fait**, avec la suppression de
   l'héritage de compteur qu'il rend inutile.
3. ~~**Représentation unique des dates**~~ — **fait**, voir §16. L'échéancier
   résolu est un objet de premier ordre : par date, son rôle (relevé,
   constatation, ou les deux), son rang, sa réduction, les blocs qu'elle
   déclenche, sa date de paiement, son lien parent-enfant.
4. ~~**Backtest**~~ — **fait**, voir §17. L'oracle le moins cher : il rejoue un
   script sur un historique réel, donc un cycle de vie sans fixings officiels ni
   booking, et il vérifie « mêmes décisions » **avant** le modèle de fixings.
5. ~~**Figement au booking**~~ — **fait**, voir §18.
6. ~~**Fixings et agrégats officiels**~~ — **fait**, voir §19.
7. ~~**Lifecycle**~~ — **fait**, voir §20.
8. Puis Events, vie résiduelle, KIDs.

**L'invariant « mêmes décisions » est à affaiblir**, et à publier tel quel : le
lifecycle et le backtest travaillent sur des dates réelles, le moteur sur une
grille hebdomadaire. Deux relevés d'une même semaine sont deux fixings d'un côté
et un pas de l'autre. Formulation retenue : *mêmes décisions à la résolution de
la grille près*, le décompte de points retenus disant laquelle. Traiter la grille
elle-même reste écarté (§5) — l'écart mesuré est de 1 à 2 bps sur le moyennage —
mais la question redevient ouverte le jour où une sous-date porte un événement.

**Trois manques relevés dans le plan, à instruire le moment venu** : une
dérogation tracée au blocage d'une fenêtre incomplète (férié imprévu, source
indisponible, titre suspendu — sinon un produit se bloque sans recours) ; les
opérations sur titres, qui rendent non homogènes les relevés d'une fenêtre à
cheval sur un split ; et une dégradation propre des deals bookés sans échéancier
figé, qui doivent s'afficher comme tels plutôt que casser Events.

---

## 15. `INDEX` — ce que l'implémentation a appris

**Un troisième défaut est sorti de l'écriture des tests.** `PARAM()` étant
indexé par `INDEX`, il héritait de sa dérive : sur deux calendriers, une
**barrière dégressive** lisait les lignes 2, 4, 6 de son propre tableau au lieu
de 1, 2, 3. Personne ne l'avait vu, et c'est un produit courant. Ce n'est pas la
relecture qui l'a trouvé mais le fait d'écrire le cas à deux calendriers.

**`index_offset` n'est plus lu.** Trois tests le mettaient en scène — un
autocall à coupon progressif, une barrière dégressive, un delta de mi-vie — et
tous vérifiaient la même chose : que transmettre le compteur changeait le prix.
Ils ont été réécrits pour vérifier la propriété inverse, plus forte : **le prix
correct sort sans qu'aucun état ne soit transmis**, parce que le rang voyage
avec la date à travers `_shift_events_for_mtf`. Oublier de transmettre un état
ne peut donc plus produire un prix faux silencieux.

`index_offset` reste dans les signatures pour l'instant : le retirer touche six
fichiers hors moteur (`deals.py`, `inlife.py`, `shocks.py`, `var_scenario.py`,
`scenario_grid.py`) et mérite son propre passage. À ne pas confondre avec
`state["index"]`, qui reste **utile** : c'est le nombre d'observations déjà
passées, affiché à l'écran comme information métier.

**Deux pièges d'outillage, notés pour ne pas les refaire.** Un heredoc Python a
transformé `` en caractère backspace dans une regex : la fonction se lisait
juste, ne matchait rien, et `inspect.getsource` affichait le bon code puisqu'il
lit le fichier. Et un `__pycache__` périmé a masqué la correction suivante. Sur
du code écrit par script, vérifier le comportement — pas seulement relire.

---

## 16. L'échéancier contractuel — `schedule_model.py`

**Ce qui n'existait pas.** « Ce que le produit observe » ne vivait nulle part
comme objet : l'information se dispersait entre `CompiledEvent.dates`,
`.window_dates`, `.payment_dates`, `.ranks` et `CompiledScript.strike_fix_dates`,
puis se reconstituait différemment dans chaque consommateur — `step_map` côté
Monte Carlo, une autre boucle côté rejeu historique, une troisième côté
Mark-to-Future. C'est ainsi que trois chemins finissent par décrire trois
produits légèrement différents.

**Trois notions, et leurs rôles ne se confondent pas.** Une **constatation** est
ce que le contrat observe : rang, réduction éventuelle, date de paiement, blocs
qui s'y exécutent dans l'ordre du script. Un **relevé** alimente la réduction
d'une constatation — il ne paie rien et ne compte pas dans le rang — sauf si un
bloc le vise (`AT OBS[2][1]`), auquel cas il porte les deux rôles et la structure
le dit. La **fenêtre de départ** fixe `S0` et n'est pas une constatation : rien
ne s'y déclenche.

**Les dates sont portées sous deux formes**, et les deux sont nécessaires : la
year-fraction, sur laquelle le moteur travaille, et la date calendaire, seule
opposable — c'est elle qu'un term sheet porte et qu'un deal booké figera. C'est
pourquoi l'échéancier est bâti **dans `resolve_constats`** : c'est le dernier
endroit où les dates calendaires existent encore. Après lui, tout est en
year-fractions, et les reconstruire supposerait de re-choisir une origine —
l'erreur d'ancrage qui est revenue cinq fois en une session.

**Une conséquence sur le contrat du parser** : `constat_ref` survit désormais à
la résolution. Il était effacé, les dates suffisant au moteur ; sans lui, rien
ne rattache un bloc à son calendrier une fois les dates converties. Un test qui
vérifiait l'effacement a été retourné pour vérifier la conservation.

**Le mode normal aussi.** `resolve_constats` sortait par un raccourci quand il
n'y avait rien à résoudre — dates écrites en dur. L'échéancier s'y construit
maintenant également : un produit en mode normal se booke, se suit et s'affiche
comme les autres.

**Ce que la structure ne fait pas.** Le moteur n'en dépend pas : il garde ses
tables. Elle existe pour que les autres chemins — booking, cycle de vie, Events,
backtest — cessent de reconstruire chacun la leur. Le raccordement est le point
suivant du §14.

---

## 17. Le backtest comme oracle — et ce qu'il a trouvé

**Le dispositif.** Une **série plate** rend le rejeu et le Monte-Carlo
comparables : à cours constant, le niveau constaté vaut 1,0 partout, quelle que
soit la fenêtre et quelle que soit la grille. Ce qui reste comparable est
précisément ce qui nous intéresse — les décisions : quels blocs se déclenchent,
avec quel rang, où tombe le `STOP`.

**Ce qu'il a trouvé du premier coup.** Le rejeu historique comptait ses propres
passages là où le moteur lit désormais le rang porté par la date. Sur un script
à deux calendriers, il lisait **2, 4, 6** quand le pricing lisait **1, 2, 3** :
le même produit se décidait autrement selon qu'on le pricait ou qu'on le
rejouait. C'est exactement ce que l'invariant du §11 interdit, et c'est le genre
d'écart qu'aucune relecture ne trouve — il fallait faire tourner les deux
chemins côte à côte sur la même trajectoire.

La correction est la même que côté moteur : un rang par événement, aligné sur
`step_map`. Le rejeu et le pricing lisent maintenant la même chose, et deux
tests le figent — sur le rang, et sur la ligne de `PARAM()` que ce rang
sélectionne.

**Les six cas du plan sont couverts** : événement sur agrégat, événement direct
sur une sous-date, même fixing consommé dans les deux rôles, `STOP`
intermédiaire, plusieurs sous-jacents, historique insuffisant — plus l'absence
totale d'historique, qui doit renoncer proprement et non lever.

**La convention de transposition est figée sans être jugée.** Le rejeu convertit
les year-fractions en séances à 252 par an ; un test l'enregistre telle quelle.
La changer déplacerait toutes les constatations de tout backtest existant, donc
elle mérite d'être visible avant d'être discutée.

**Ce que l'invariant ne peut pas être.** Le rejeu travaille sur 252 séances, le
moteur sur 52 pas : les tests ne comparent jamais des dates au jour près, mais
des décisions et des rangs. C'est la formulation affaiblie du §14, et elle est
maintenant appliquée plutôt qu'annoncée.

---

## 18. Le figement au booking

**Ce qui n'allait pas.** Les dates d'un deal booké se reconstruisaient à chaque
valorisation, depuis ses CONSTAT et son ancrage. Une convention de jour ouvré
modifiée, un référentiel de fériés mis à jour, ou simplement un changement dans
la génération de calendrier déplaçaient donc **rétroactivement** les
constatations d'un contrat déjà signé. Ce que le term sheet dit ne peut pas
dépendre d'un code exécuté plus tard.

**Ce qui est figé** : `Deal.schedule_json`, alimenté au booking depuis
l'échéancier du §16 — par constatation, sa date calendaire, son rang, sa
réduction, ses relevés datés, et les blocs du script qu'elle déclenche dans
l'ordre contractuel. Plus la fenêtre de départ, à part, puisqu'elle n'est pas
une constatation.

**La résolution est faite une seule fois** : `_resoudre_pour_booking` a été
extraite pour que les temps d'observation et l'échéancier figé viennent du même
calcul. Deux résolutions séparées, ce sont deux calendriers qui peuvent diverger
— exactement ce que le figement doit empêcher.

**Dégradation assumée.** Un script qu'on ne sait pas résoudre laisse le champ
vide, et le booking passe : `{}` se lit comme « pas d'échéancier figé », ce qui
est la vérité, plutôt que d'enregistrer un calendrier partiel. Les deals
antérieurs au champ sont dans le même cas — aucune migration n'est prévue, comme
convenu, et l'API rend `schedule: null` pour qu'un écran puisse le dire.

**Un défaut préexistant trouvé en passant, et réparé.** Sept tests de
`test_rfq.py` — tout le booking en mode expert — échouaient déjà avant ce
chantier : une `value_date` écrite en dur au 2026-09-03, devenue antérieure à
`date.today()`. Le booking expert n'était donc plus testé depuis cette date. La
date est maintenant relative au strike, comme `T` l'était déjà juste à côté — et
le commentaire de `T` disait précisément pourquoi : « une constante deviendrait
fausse dès le lendemain ».

---

## 19. Fixings des relevés, et agrégats officiels

**Le modèle de fixings existait déjà**, et il couvre le cahier des charges :
valeur indicative séparée de l'officielle (`indicative_spots_json` contre
`spots_json`), provenance, statut, versions immuables avec `supersedes_id`,
preuve (`evidence_sha256`), validation à quatre yeux. Rien à reconstruire.

**Ce qui manquait** : les `DealEvent` ne couvraient que les **constatations**.
Sur un produit à moyenne, les quatre relevés trimestriels d'une constatation
n'avaient aucune ligne — donc ni fixing officiel, ni provenance, ni preuve, et
l'agrégat n'avait rien à lire. Le booking crée désormais une ligne par relevé,
rattachée à sa constatation par `parent_event_id`, la constatation portant sa
règle d'agrégation dans `reduction`.

**L'invariant « aucun fixing compté deux fois » est tenu par construction.** Le
dernier relevé d'une fenêtre EST la constatation : il n'est pas dédoublé, donc
un cours servant deux usages ne produit qu'un seul fixing officiel — et donc une
seule vérité. C'est une propriété du schéma, pas une vérification à faire tourner.

**L'agrégat officiel** (`core/agregats_officiels.py`) réduit une fenêtre en un
niveau **par sous-jacent** ; l'agrégation panier vient après, dans le payoff.
Il refuse plutôt qu'il n'approxime :

- **fenêtre incomplète** → pas d'agrégat, et la liste nommée des relevés
  manquants. Une moyenne partielle qui se présente comme une moyenne est
  exactement le chiffre faux qui ne se signale pas ;
- **un sous-jacent sans cours sur toute la fenêtre** → blocage aussi. Le réduire
  sur les seules dates où il en a le comparerait à ses pairs sur une autre base,
  dans le calcul même du worst-of ;
- **réduction inconnue** → refus.

**La neutralisation, seule issue au blocage.** Un férié imprévu, une source
indisponible, un titre suspendu bloqueraient sinon un produit que personne ne
pourrait débloquer. Un relevé peut être écarté — mais jamais silencieusement :
motif et auteur voyagent avec le calcul et ressortent dans sa sérialisation.

**Périmé par version, pas par valeur.** Un agrégat retient les versions de
fixing qui l'ont produit. Une correction en crée une nouvelle, et l'agrégat
devient périmé — **même si la correction rend le même cours**. Comparer les
valeurs laisserait passer une correction sans effet numérique, que l'auditeur
doit pourtant voir.

---

## 20. Le cycle de vie face aux fenêtres

**La machinerie existait**, et elle est solide : rejeu officiel depuis les
fixings validés, propositions séparées des validations, Maker/Checker, refus
explicite d'un payoff qui dépend du chemin entre les constatations. Rien à
reconstruire ici non plus.

**Une référence morte de ce chantier y traînait.** `path_dependency_reasons`
bloquait le rejeu officiel sur `FIX_MIN|FIX_MAX|FIX_AVG` — un vocabulaire
supprimé au §7. Le retirer ne fait pas que nettoyer : une constatation sur
période se prouve désormais depuis les fixings de ses relevés, donc la bloquer
reviendrait à refuser un produit parfaitement rejouable. Les barrières
américaines (`WOF_MIN`, `S_MIN[i]`, `REALVOL`) restent refusées, elles lisent
bien le chemin.

**Le rejeu marchait déjà**, à une condition près. Il reconstitue une série à
252 pas depuis **tous** les événements fixés : les relevés créés au §19 y entrent
donc naturellement, chacun posant son cours à sa date, et la moyenne d'une
fenêtre devient exacte.

**Le trou, et il était dangereux.** Si les relevés d'une fenêtre n'ont pas leurs
fixings, la série reste constante par morceaux entre les constatations — et la
moyenne se calcule alors sur des valeurs **reportées**, pas sur les cours du
contrat. Le rejeu rendait un nombre parfaitement plausible, et rien ne disait
qu'il était faux. C'est précisément le silence que la règle « aucune moyenne
partielle silencieuse » interdit.

**La décision : report, pas refus.** Bloquer ferait qu'on n'aurait jamais rien —
arbitrage de Philippe, et il a raison sur l'usage. Le rejeu aboutit donc
toujours : un relevé sans fixing hérite du dernier cours connu, ce qui est la
convention de place pour un jour sans cotation. Ce qui n'est pas négociable,
c'est le silence : `releves_sans_fixing` **nomme les dates reportées**, et
l'avertissement `OFFICIAL_WINDOW_CARRIED_FORWARD` voyage AVEC le résultat, pas à
côté. Un cours à zéro ou absent ne compte pas comme un fixing — c'est l'état d'un
événement créé au booking et jamais saisi.

**L'avertissement n'est pas générique, parce que le report ne coûte pas la même
chose partout.** Sur `AVG`, un cours reporté pèse 1/N : l'erreur est bornée. Sur
`MIN` ou `MAX`, elle ne l'est pas — si le cours manquant était justement
l'extrême de la fenêtre, le niveau constaté ressort faux **dans le sens
favorable**, et le produit ne knock-in pas. Ce n'est plus une imprécision, c'est
un basculement de décision : `peut_renverser_la_decision` le porte
explicitement.

**Le backtest avait le défaut inverse**, et personne ne l'avait vu : quand un
cours manquait, il le **sautait** au lieu de le reporter. La moyenne portait
alors sur trois relevés au lieu de quatre, sans que rien ne le dise — la
« moyenne partielle silencieuse », au backtest plutôt qu'en vie. Il reporte
désormais, et remonte `releves_reportes` dans son résultat.

**Reste ouvert** : la séparation proposition / application (point 7 du plan) —
voir le résultat probable avec report, mais exiger le fixing ou une
neutralisation motivée avant qu'un montant parte chez le client. Et l'idée de
l'**encadrement** : un cours manquant n'est pas inconnu, il est borné ; si la
décision est la même dans tout l'encadrement, elle est certaine malgré le trou,
et seuls les cas où le manque change l'issue mériteraient d'être bloqués.

**Ce qui n'est pas concerné** : un produit ponctuel ne déclare aucune fenêtre, et
un deal booké avant l'échéancier figé n'en déclare pas non plus. Les deux
continuent de vivre exactement comme avant — la dégradation reste propre, et un
échéancier illisible ne fait pas tomber le cycle de vie d'un deal.
