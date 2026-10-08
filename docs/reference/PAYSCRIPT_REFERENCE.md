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
UNDERLYING Basket

# Autocall Athena — barrière de protection observée à maturité
PARAM COUPON
PARAM M_AC_BAR
PARAM M_KI_BAR

CONSTAT StartDate
CONSTAT() ObservationDates

AT StartDate:
  Basket.spot0 = Basket.spot@StartDate

AT Date FROM ObservationDates:
  SET PERF = WORSTOF(Basket.yield)
  IF PERF >= M_AC_BAR:
    PAY COUPON * INDEX "Coupons cumulés"
    PAY 1 "Capital — remboursement au rappel"
    STOP

AT ObservationDates.last:
  SET KI = INDIC(WORSTOF(Basket.yield) < M_KI_BAR)
  PAY 1 "Capital — remboursement à maturité"
  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put vendu — perte en capital"
```

Le dernier bloc solde le produit à `ObservationDates.last`. `STOP` empêche
un second remboursement lorsque le rappel a lieu à cette dernière date.

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
| `INDEX` | **Rang de la date dans l'échéancier que le bloc nomme**, base 1 — voir §4.3. Refusé dans `AT MATURITY`, qui ne nomme aucun échéancier |
| `T` | Temps écoulé depuis l'origine, en années |
| `N` | Nombre de sous-jacents |
| `ACCUM` | Accumulateur alimenté par `ACCRUE` |
| `REALVOL` | Volatilité réalisée annualisée du worst-of depuis l'origine |

### 3.3 Fonctions

| Nom | Sens |
|---|---|
| `WORSTOF` | `WORSTOF(Basket.yield)` : minimum des ratios individuels |
| `BESTOF` | `BESTOF(Basket.yield)` : maximum des ratios individuels |
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
| `UNDERLYING` | `UNDERLYING Basket` lie le panier aux sous-jacents Economics, dans leur ordre contractuel |
| `PARAM` | `PARAM NOM [= valeur[%]] ["description"]` — sans valeur : pourcentage obligatoire dans Economics ; avec valeur : défaut explicite, brut si sans `%` |
| `PARAM()` | `PARAM() NOM [= valeur[%]]` — une valeur par observation. Sans défaut, série obligatoire dans Economics ; la dernière ligne s’étend aux observations suivantes |
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

## Objet Basket et Economics (version du 06/10/2026)

`Basket.yield` est le vecteur des ratios individuels spot courant / spot initial.
110 sur un strike de 100 donne **1,10**, et non 0,10. L’agrégation est explicite :
`WORSTOF`, `BESTOF` ou `AVG` (moyenne équipondérée). Le panier ne choisit jamais
un ticker lui-même : son identité et son ordre viennent d’Economics.

`CONSTAT StartDate` et `AT StartDate: Basket.spot0 = Basket.spot@StartDate`
fixent une seule fois les références individuelles. Ce bloc ne verse aucun flux
et ne consomme aucun rang INDEX. Pour une fenêtre initiale, écrire
`CONSTAT StartDate AVG`, `MIN` ou `MAX` et saisir sa longueur et sa fréquence.
`CONSTAT() StartDate` est refusé : réinitialiser les strikes à chaque date serait
un autre contrat. La première observation doit suivre le fixing initial, et ne
peut pas précéder la fin de sa fenêtre.

StartDate reçoit la date effective du fixing. Si une convention de jour ouvré
déplacerait cette date, le moteur demande de saisir la date effective plutôt
que de déplacer silencieusement l'origine de simulation.

`AT Date FROM ObservationDates:` exécute le bloc à chaque date. Dans le bloc,
`Basket.spot@Date` désigne le fixing courant. Les références futures ou à des
dates arbitraires sont refusées. `Basket.spot / Basket.spot0` est équivalent à
`Basket.yield`. Les cours absolus nécessitent des références individuelles
explicites ; leur absence n’est jamais remplacée par des cours fictifs de 1.
Pour un payoff en pourcentages, aucun cours en devise n’est nécessaire au
pricing initial : la normalisation du moteur suffit, y compris pour
`Basket.spot / Basket.spot0`. Par exemple, un cours courant de 45 pour un fixing
initial de 50 donne `Basket.yield = 0.90`, soit 90 % du niveau initial.
Si le payoff lit les cours absolus, le Pricer propose une hypothèse de cours
initial par actif dans Economics, sous « Cours en devise —
scripts spécifiques ». Cette saisie de simulation n’enregistre pas un fixing
contractuel dans Events.
En cours de vie, les fixings contractuels et leur historique fournissent ces
références ; un choc de marché ne les réinitialise pas.

Les calendriers utilisent `first_observation_date` **incluse**, `end_date`,
`frequency`, le roll facultatif et les conventions de règlement. La date de
strike est portée exclusivement par StartDate, jamais par le début d’un
échéancier. Pour `PERIOD`, `period_start_date` ouvre la première période ; sans
saisie distincte, c’est StartDate. Les périodes suivantes commencent à
l’observation précédente. Aucun coupon n’est dû au début de période.

`PARAM COUPON` n’a aucun défaut. 8 dans Economics signifie 8 %, soit 0,08 dans
le moteur. `COUPON * 100` fournit 8 si le calcul attend une quantité brute.
`PARAM MULTIPLIER = 1.5` déclare au contraire une valeur brute avec un défaut
explicite. Les paramètres manquants bloquent les calculs ; les brouillons peuvent
rester incomplets. `COUPON * INDEX` cumule un coupon **par observation**, sans
annualisation implicite.

Les modèles génériques ne portent ni durée, ni dates, ni valeurs de paramètres.
L’éditeur est unique, sans sélecteur Normal/Expert. Les réglages de roll et de
stub restent accessibles sous « Réglages avancés du calendrier », dans le
Pricer comme dans la RFQ. Les cours en devise apparaissent lorsqu’un script
lit des cours absolus ou qu’un cours initial a déjà été saisi.

« Exemples préremplis… » propose 15 jeux de termes : Autocall 3Y/4Y/5Y,
Autocall à barrière américaine 3Y, Autocall dégressif 5Y, Phoenix et Phoenix
mémoire trimestriels 3Y/5Y, Reverse Convertible 1Y, Capital garanti 5Y,
Twin Win 3Y, Call/Put/Call Spread 1Y. Le script reste celui du modèle générique ;
les exemples fournissent les paramètres et les dates dans Economics. Leur
aperçu annonce les termes remplacés, la convention « jour ouvré suivant » et
le règlement J+3 ouvrés selon la devise. StartDate et date de valeur sont
proposées au départ ajusté ; la première observation est ultérieure. Le panier
et les hypothèses de marché sont conservés. Tous ces termes sont modifiables.

Une configuration conserve séparément une
version du script, les valeurs, les dates et, facultativement, le panier.
« Sauvegarder » conserve un modèle sans ses saisies Economics. Utiliser
« Mes configurations enregistrées… » pour conserver puis appliquer un jeu de termes
prérempli ; son aperçu annonce les données qui seront remplacées.

Chaque `PAY` représente une jambe distincte : coupon, capital, put vendu.
Une perte s’écrit `PAY -KI * MAX(1 - PERF, 0)` après `PAY 1`, ce qui sépare la
protection du remboursement nominal. Les lignes nulles restent dans la
décomposition et ne créent pas de paiement dans les statistiques de durée.

Les notations historiques `AT 1, 2`, `WOF`, `BASKET` et `STRIKE_FIX` restent
acceptées pour les calculs et scripts techniques. Les exemples historiques
ci-dessous expliquent ces primitives ; les nouveaux modèles utilisent Basket
et StartDate comme dans le script complet ci-dessus.

## 4. Dates d'observation

```
AT 1, 2, 3:              trois dates, en années
AT 0.5, 1, 1.5, 2:       semestriel sur 2 ans
AT 1..5:                 raccourci pour 1, 2, 3, 4, 5
AT 0.25..3:0.25:         de 0,25 à 3 par pas de 0,25 (trimestriel)
AT 1Y, 2Y:               le suffixe Y est accepté et ignoré
```

Les dates sont **strictement positives** et exprimées en **années depuis la date
de strike** : t = 0 est la constatation du niveau initial, rien d'autre ne s'y
observe. La maturité du produit ne peut pas précéder la dernière date `AT`.

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

### 4.3 `INDEX` — le rang, pas un compteur

`INDEX` est le **rang de la date dans l'échéancier que le bloc nomme**. `AT
OBSERVATIONS:` sur un calendrier de trois dates donne 1, 2, 3 — et les relevés
d'une constatation sur période n'y changent rien : ce sont des relevés, pas des
observations.

| écriture | `INDEX` |
|---|---|
| `AT OBSERVATIONS:` | 1, 2, 3 |
| `AT OBSERVATIONS.last:` | **3** — le rang dans le calendrier, pas dans le bloc |
| `AT OBSERVATIONS[2][1]:` | **2** — celui de la constatation parente, pas du relevé |
| `AT 1, 2, 3:` | 1, 2, 3 — l'échéancier est la liste du bloc |
| `AT MATURITY:` | **refusé** — ce bloc ne nomme aucun échéancier |

Deux conséquences qui comptent :

**Le rang est indépendant par échéancier.** Si un `CONSTAT MATURITE` tombe le
même jour que la dernière date d'`OBSERVATIONS`, alors `AT OBSERVATIONS:` y voit
3 et `AT MATURITE:` y voit 1. Deux façons d'écrire la même date, deux
sémantiques, et c'est le nom du calendrier qui tranche. Pour l'idiome Athena —
dernier coupon `COUPON * INDEX` — c'est `AT OBSERVATIONS.last:` qu'il faut.

**Le rang appartient à la date, pas à l'exécution.** La troisième constatation
porte 3 qu'on price le produit neuf ou à mi-vie : rien n'est à réamorcer quand
un deal est valorisé en cours de vie. Un script qui veut compter autre chose —
coupons effectivement versés, observations sous barrière — l'écrit avec `SET` :

```
SET PASSAGE = 0

AT OBSERVATIONS:
  SET PASSAGE = PASSAGE + 1
```

`PARAM()` suit la même règle : « une valeur par observation » désigne les
observations du calendrier que le bloc nomme. Un `PARAM()` lu depuis deux
calendriers différents est refusé — son nombre de lignes ne serait plus défini.

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

## 6. Exemple complet — Autocall Athena

```
UNDERLYING Basket

# Autocall Athena — barrière de protection observée à maturité
PARAM COUPON
PARAM M_AC_BAR
PARAM M_KI_BAR

CONSTAT StartDate
CONSTAT() ObservationDates

AT StartDate:
  Basket.spot0 = Basket.spot@StartDate

AT Date FROM ObservationDates:
  SET PERF = WORSTOF(Basket.yield)
  IF PERF >= M_AC_BAR:
    PAY COUPON * INDEX "Coupons cumulés"
    PAY 1 "Capital — remboursement au rappel"
    STOP

AT ObservationDates.last:
  SET KI = INDIC(WORSTOF(Basket.yield) < M_KI_BAR)
  PAY 1 "Capital — remboursement à maturité"
  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put vendu — perte en capital"
```

Les valeurs et le calendrier se renseignent dans Economics. Le coupon est payé
au rappel, y compris à la dernière observation si la barrière de rappel est
atteinte. Sinon, seul le capital diminué du put éventuel est versé.
