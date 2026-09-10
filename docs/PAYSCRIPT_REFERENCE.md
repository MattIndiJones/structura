# Référence du langage PayScript

Document unique décrivant tout ce qu'un script a le droit d'écrire. Il sert à
deux usages :

1. documentation pour l'utilisateur ;
2. corps du prompt système de l'assistant IA (`services/llm/prompt.py`).

> **Ce fichier est sous test.** `backend/tests/test_payscript_reference.py`
> compare la section « Vocabulaire » ci-dessous au vocabulaire réellement
> accepté par `parser.py` (`language_vocabulary()`). Un mot ajouté au langage
> sans être documenté ici — ou documenté ici sans exister — fait échouer la
> suite. Sans ce garde-fou, le prompt promettrait au modèle une syntaxe que le
> parser refuse, et l'assistant produirait des scripts systématiquement cassés.

---

## 1. Principes

Un script décrit **les flux d'un produit structuré**, observation par
observation. Le moteur simule des trajectoires de sous-jacents et exécute le
script sur chacune.

- Tous les niveaux sont exprimés **en fraction du niveau initial** : `1.0` = 100 %
  du spot d'origine, `0.6` = 60 %.
- Tout `PAY` est un flux **en fraction du nominal** : `PAY 1` rembourse le pair,
  `PAY 0.08` verse 8 % du nominal.
- L'**indentation** délimite les blocs (comme en Python). Les déclarations et
  les blocs `AT` sont à l'indentation 0 ; leur corps est indenté.
- Les mots-clés sont **insensibles à la casse**, les identifiants sont
  normalisés en majuscules.
- `#` commence un commentaire jusqu'à la fin de la ligne.

---

## 2. Structure d'un script

```
PARAM COUPON = 8%           # déclarations (indentation 0)
PARAM M_AC_BAR = 100%

AT 1, 2, 3:                 # bloc d'observation (indentation 0)
  SET CALL = INDIC(WOF >= M_AC_BAR)     # corps (indenté)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:                # bloc de maturité — toujours en dernier
  SET KI = INDIC(WOF < 0.6)
  PAY (1 - KI) * 1
  PAY KI * WOF
```

**Tout produit doit avoir un bloc `AT MATURITY`** qui le solde. Sans lui, une
trajectoire jamais rappelée ne paie rien.

---

## 3. Vocabulaire

<!-- VOCABULAIRE:DEBUT -->

### 3.1 Niveaux de marché

| Nom | Sens |
|---|---|
| `WOF` | Worst-of : niveau **courant** du plus bas sous-jacent, à cette observation |
| `BOF` | Best-of : niveau courant du plus haut sous-jacent |
| `WOF_MIN` | Minimum **atteint depuis l'origine** par le worst-of (barrière américaine) |
| `BOF_MAX` | Maximum atteint depuis l'origine par le best-of |
| `BASKET` | Moyenne des sous-jacents. `BASKET` ou `BASKET()` = équipondérée ; `BASKET(0.6, 0.4)` = pondérée, **exactement un poids par sous-jacent** |
| `S` | `S[i]` : niveau du sous-jacent *i*, **indicé de 1 à N** |
| `S_MIN` | `S_MIN[i]` : minimum atteint par le sous-jacent *i* depuis l'origine |
| `S_MAX` | `S_MAX[i]` : maximum atteint par le sous-jacent *i* depuis l'origine |
| `S_PREV` | `S_PREV[i]` : niveau du sous-jacent *i* à l'observation **précédente** |

### 3.2 État du contrat

| Nom | Sens |
|---|---|
| `INDEX` | Compteur d'observations, **base 1**. Inchangé pendant `AT MATURITY` (il garde la valeur de la dernière observation) |
| `T` | Temps écoulé depuis l'origine, en années |
| `N` | Nombre de sous-jacents |
| `ACCUM` | Accumulateur alimenté par `ACCRUE` |
| `REALVOL` | Volatilité réalisée annualisée du worst-of depuis l'origine |

### 3.3 Fonctions

| Nom | Sens |
|---|---|
| `MAX` | `MAX(a, b)` — maximum |
| `MIN` | `MIN(a, b)` — minimum |
| `ABS` | Valeur absolue |
| `FLOOR` | Partie entière inférieure |
| `CEIL` | Partie entière supérieure |
| `SQRT` | Racine carrée |
| `LOG` | Logarithme népérien |
| `EXP` | Exponentielle |
| `ROUND` | Arrondi |
| `INDIC` | **Indicatrice** : `INDIC(cond)` vaut 1 si la condition est vraie, 0 sinon. C'est la façon idiomatique d'écrire un payoff sans `IF` |

### 3.4 Logique

| Nom | Sens |
|---|---|
| `AND` | Et logique |
| `OR` | Ou logique |
| `NOT` | Négation |
| `TRUE` | Vrai |
| `FALSE` | Faux |

### 3.5 Déclarations (indentation 0)

| Nom | Sens |
|---|---|
| `PARAM` | `PARAM NOM = valeur[%] ["description"]` — paramètre scalaire, surchargeable depuis l'interface |
| `PARAM()` | `PARAM() NOM [= amorce[%]]` — **une valeur par observation** (barrière dégressive, coupon progressif). Les valeurs se saisissent dans l'interface ; la dernière ligne s'étend aux observations suivantes |
| `CONSTAT` | `CONSTAT Nom [MIN\|MAX\|AVG]` — une date unique, renseignée depuis l'interface |
| `CONSTAT()` | `CONSTAT() Nom [MIN\|MAX\|AVG]` — un calendrier (début / fin / roll / fréquence / stub) |
| `CONSTAT()()` | `CONSTAT()() Nom` — un calendrier dont chaque intervalle est subdivisé. La sous-grille **se recale** sur chaque date principale au lieu de courir en continu — voir §4.2 |
| `MIN` | Réduction d'une constatation sur période — voir §4.1 |
| `MAX` | Réduction d'une constatation sur période — voir §4.1 |
| `AVG` | Réduction d'une constatation sur période — voir §4.1 |
| `PERIOD` | Portée de la fenêtre : la période écoulée, et non une longueur — voir §4.1 |
| `STRIKE_FIX` | Nom de `CONSTAT` réservé : il porte la fenêtre de départ, celle qui fixe `S0` |
| `AT` | `AT 1, 2, 3:` — bloc d'observation à des dates en années. Voir §4 |
| `AT MATURITY` | Bloc exécuté à maturité si le contrat n'a pas été arrêté |
| `SET` | Au niveau 0 : initialise une variable avant toute observation |

### 3.6 Instructions (dans un bloc)

| Nom | Sens |
|---|---|
| `PAY` | `PAY expression ["libellé"]` — verse un flux, en fraction du nominal. Le libellé apparaît dans la table des flux |
| `FLOW` | Synonyme de `PAY` |
| `ACCRUE` | `ACCRUE expression` — ajoute à `ACCUM` sans verser de flux |
| `SET` | `SET NOM = expression` — affecte une variable (mémoire du contrat) |
| `STOP` | Arrête le contrat pour cette trajectoire. **Indispensable à tout rappel anticipé** |
| `IF` | `IF condition:` — bloc conditionnel |
| `ELSE IF` | `ELSE IF condition:` |
| `ELSE` | `ELSE:` |

<!-- VOCABULAIRE:FIN -->

### 3.7 Opérateurs

`+` `-` `*` `/` `(` `)` pour l'arithmétique.

Comparaisons : `>=` `<=` `>` `<` `!=` (ou `<>`) et **`=` qui teste l'égalité**
dans une expression (`IF CALL = 1:`). L'affectation se fait uniquement par `SET`.

---

## 4. Dates d'observation

```
AT 1, 2, 3:              trois dates, en années
AT 0.5, 1, 1.5, 2:       semestriel sur 2 ans
AT 1..5:                 raccourci pour 1, 2, 3, 4, 5
AT 0.25..3:0.25:         de 0,25 à 3 par pas de 0,25 (trimestriel)
AT 1Y, 2Y:               le suffixe Y est accepté et ignoré
```

Les dates sont **strictement positives** (t = 0 est la date de pricing, rien ne
s'y observe) et exprimées en **années depuis aujourd'hui**.

Quand un `CONSTAT` est déclaré, un bloc peut viser son calendrier :

```
AT Observations:          toutes les dates du calendrier
AT Observations.first:    uniquement la première
AT Observations.last:     uniquement la dernière
AT Observations[3]:       uniquement la 3ᵉ (indicé à partir de 1)
AT Observations.last.last: le dernier RELEVÉ de la dernière constatation
```

Un **second** qualificateur descend d'un niveau : du calendrier vers la fenêtre
de constatation. Un seul niveau désigne une constatation, et lit ce que le
CONSTAT déclare — donc la réduction. Deux niveaux désignent un fixing dans sa
fenêtre, et lisent le **cours brut** de ce jour-là. Voir §4.1.

### 4.1 Constatations sur période

Une constatation n'est pas forcément un point. Ajoutez `MIN`, `MAX` ou `AVG`
après le nom d'un `CONSTAT` et chacune de ses dates devient une réduction sur
une **fenêtre** :

```
CONSTAT STRIKE_FIX  AVG      niveau initial = moyenne de la fenêtre de départ
CONSTAT MATURITE    AVG      niveau final   = moyenne des N derniers jours
CONSTAT() OBSERVATIONS MIN   chaque date du calendrier porte sa fenêtre
```

Trois règles, et elles suffisent :

1. **La réduction est toujours par sous-jacent.** Chaque actif est réduit sur sa
   propre fenêtre ; `WOF`, `BOF` et `BASKET` agrègent **ensuite**. Réduire
   l'agrégat au lieu de chaque actif donne un autre produit : `moyenne(min)` et
   `min(moyennes)` ne sont pas la même chose, et l'écart se chiffre en dizaines
   de points de base sur un worst-of.
2. **La longueur de la fenêtre n'est pas dans le script.** Elle se saisit à
   l'écran avec les dates (longueur et fréquence d'échantillonnage), parce que
   c'est une donnée de term sheet : passer de 10 à 30 jours ne doit pas modifier
   un payoff. Ce qui change le payoff — `MIN` contre `AVG` — reste ici.
3. **La fenêtre de départ part de sa date, les autres y arrivent.**
   `STRIKE_FIX` regarde en avant à partir du strike ; toute autre constatation
   regarde en arrière jusqu'à sa date, incluse.

#### Fenêtre de longueur, fenêtre de période

Une fenêtre a par défaut une **longueur** — « les 30 derniers jours de bourse ».
Le mot `PERIOD` en fait la **période écoulée depuis la constatation
précédente** :

```
CONSTAT() OBSERVATIONS AVG PERIOD
```

Trois constatations annuelles, chacune moyennée sur les relevés de son année.
Il n'y a alors pas de longueur à saisir — seulement la fréquence de relevé — et
les bornes sont ouvertes à gauche, fermées à droite, si bien qu'une date de roll
partagée par deux périodes n'est comptée qu'une fois. `PERIOD` suppose un
calendrier : sur une date unique il n'y a pas de période précédente.

#### Quand prendre `CONSTAT()()` — §4.2

`CONSTAT()()` subdivise chaque intervalle du calendrier principal, et **toutes**
les dates obtenues sont des observations. Sa seule propriété propre est que la
sous-grille **repart de chaque date principale** au lieu de courir en continu.

Quand la sous-fréquence divise la fréquence — 3M dans 1Y — elle donne
exactement le même calendrier qu'un `CONSTAT()` en 3M : dans ce cas courant,
`CONSTAT()()` n'apporte rien. Elle se distingue sur une fréquence **non
divisible** : en 1Y sous-fréquencé 5M, les observations repassent par chaque
anniversaire annuel, là où un 5M continu dérive et tombe à des dates
différentes chaque année.

Donc :

| Ce que la grille fine doit faire | À écrire |
|---|---|
| **observer** (chaque date paie ou teste) | `CONSTAT()() Nom` |
| **moyenner** (une constatation par période) | `CONSTAT() Nom AVG PERIOD` |

Les deux ensemble sont refusés : ce serait deux grilles fines pour un seul
calendrier, et l'une serait ignorée sans rien dire.

#### Deux lectures d'une même date

Un coupon constaté sur une moyenne et une protection constatée sur le cours de
clôture tombent le même jour. Le second niveau de qualificateur les sépare :

```
AT OBSERVATIONS:            → la constatation, donc la moyenne
AT OBSERVATIONS.last.last:  → son dernier relevé, donc le cours
```

Deux blocs, un seul calendrier, donc une seule source de dates : deux `CONSTAT`
distincts auraient deux dates à saisir, qui peuvent cesser de coïncider sans que
rien ne le signale.

Après réduction, `WOF`, `BOF`, `BASKET` et `S[i]` valent directement la
performance contre `S0` — il n'y a aucun rapport à écrire à la main.

Tant que la fenêtre de départ n'est pas close, `S0` n'existe pas : les
observations américaines (`WOF_MIN`, `BOF_MAX`, `S_MIN[i]`, `S_MAX[i]`) ne
commencent à accumuler qu'après elle. Il n'y a rien dont une barrière puisse
être le pourcentage avant.

Un call panier à strike moyenné 10 jours et niveau final moyenné 30 jours
s'écrit donc en entier ainsi :

```
PARAM STRIKE = 100%

CONSTAT STRIKE_FIX  AVG
CONSTAT MATURITE    AVG

AT MATURITE:
  PAY MAX(0, BASKET - STRIKE) "Call panier, strike et final moyennés"
```

---

## 5. Pièges de modélisation

Ces points ne sont pas de la syntaxe : ce sont les erreurs qui **produisent un
script valide décrivant un autre produit**. Elles ne lèvent rien et sortent un
prix.

### `WOF` ou `WOF_MIN` — la question la plus importante

- `WOF` = niveau **à la date d'observation**. Barrière **européenne** :
  « le sous-jacent est-il sous 60 % *le jour de la constatation* ? »
- `WOF_MIN` = plus bas **atteint depuis l'origine**. Barrière **américaine** :
  « le sous-jacent est-il *passé* sous 60 % à un moment quelconque ? »

Une barrière knock-in de termsheet est presque toujours américaine (`WOF_MIN`).
Se tromper coûte plusieurs points de nominal, sans aucun symptôme.

### Un rappel sans `STOP` n'est pas un rappel

Si le bloc d'autocall ne contient pas `STOP`, le contrat continue d'observer
après avoir été « rappelé » et paiera aussi à maturité.

### Ne pas rembourser le nominal deux fois

Au rappel, on verse le nominal **et** le coupon :

```
PAY CALL * 1                 # nominal
PAY CALL * COUPON * INDEX    # coupons cumulés
```

`PAY CALL * (1 + COUPON)` est valide et cohérent aussi, mais mélanger les deux
formes dans le même script paie le nominal deux fois.

### Coupon à mémoire

Un coupon mémoire rattrape les coupons non versés. Il faut **mémoriser le
dernier index payé** :

```
PARAM COUPON = 8%
PARAM M_CPN_BAR = 70%

AT 1, 2, 3:
  IF WOF >= M_CPN_BAR:
    PAY COUPON * (INDEX - MEMO) "coupon mémoire"
    SET MEMO = INDEX
```

Sans le `SET MEMO = INDEX`, la mémoire ne mémorise rien.

### Convention `M_`

Un `PARAM` préfixé `M_` est **surveillé par la watchlist** du module Booking.
La direction (à la hausse / à la baisse) et l'observable sont déduites de la
façon dont le script le compare. Utiliser ce préfixe pour les barrières de
rappel et de knock-in.

### Indices

`S[i]` est indicé **de 1 à N**. `S[0]` lève une erreur.

### Noms réservés

Aucun `PARAM`, `PARAM()` ou `SET` ne peut porter un nom du vocabulaire du §3 :
le langage le résoudrait en priorité et le paramètre serait inaccessible.

- `PARAM FLOOR = 100%` → `FLOOR` est la fonction partie entière ; le script
  compile puis échoue au pricing.
- `PARAM T = 3` → `T` est le temps écoulé ; le paramètre **ne lève rien** et
  n'est simplement jamais lu. Valeur plausible, produit faux.

Le parser refuse ces déclarations avec un message explicite. Préférer
`PLANCHER`, `MATU`, `FLOOR_LVL`…

---

## 6. Exemple complet commenté — Autocall Athena 3 ans

```
# Autocall Athena 3 ans
PARAM COUPON = 8%           # coupon annuel, cumulé jusqu'au rappel
PARAM M_AC_BAR = 100%       # barrière de rappel
PARAM M_KI_BAR = 60%        # barrière de perte en capital

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= M_AC_BAR)   # 1 si rappelé, 0 sinon
  PAY CALL * COUPON * INDEX           # coupons cumulés depuis l'origine
  PAY CALL * 1                        # remboursement du nominal
  IF CALL = 1:
    STOP                              # le contrat s'arrête ici

AT MATURITY:
  SET KI = INDIC(WOF < M_KI_BAR)      # 1 si sous la barrière
  PAY (1 - KI) * 1                    # au-dessus : le pair
  PAY KI * WOF                        # en dessous : la performance
```

Lecture : à chaque date annuelle, si le plus bas sous-jacent est au moins à son
niveau initial, l'investisseur reçoit le nominal plus 8 % par année écoulée et le
produit s'arrête. Sinon on continue. À maturité, s'il n'y a pas eu de rappel :
capital garanti tant que le worst-of est au-dessus de 60 %, sinon perte à
hauteur de la baisse.
