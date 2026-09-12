# Éditeur PayScript et Economics — note de travail

> **Statut au 11/09/2026 : analyse et plan, aucun code.** Rien n'est implémenté ; on ne
> code pas tant que Philippe ne le demande pas.
>
> **Le mode debug (lot 3) est la dernière priorité. Avant de le coder, redemander à
> Philippe s'il faut le faire.**

Lecture du code faite le 11/09/2026 sur la branche `codex/structura-bugfix-hardening`
(des modifications non commitées y sont en cours, sans rapport avec les mécanismes
décrits ici). Les références citent des fichiers et des fonctions plutôt que des
numéros de ligne, qui bougent.

---

## 1. Objet

Quatre sujets soulevés par Philippe le 11/09/2026 :

1. En passant `CONSTAT X` en `CONSTAT() X` dans le script, l'onglet Economics devient blanc.
2. La validation du script se déclenche pendant la frappe et casse des déclarations.
3. Le besoin d'un mode debug montrant la valeur des variables à chaque cycle du pricer.
4. Qui fait foi pour la valeur d'un PARAM : le script ou Economics.

---

## 2. Décisions de Philippe (11/09/2026)

| # | Décision |
|---|---|
| D1 | Le script définit le payoff et déclare chaque PARAM avec son **unité** (`%` ou non) et une **valeur initiale**. |
| D2 | **Economics fait foi** pour les valeurs : 8 % dans le script, 9 % saisi dans Economics → 9 %. |
| D3 | **Tout le reste lit Economics, `M_` compris** : watchlist, Client Intelligence, EMT, solveur, grille, notes. |
| D4 | `PARAM()` exige une valeur, comme `PARAM`. La forme `PARAM() NOM` sans valeur (convention du 18/07/2026) disparaît. |
| D5 | La validation se déclenche au **Ctrl+S** ou par un bouton, et Ctrl+S ne fait **que** valider. L'enregistrement reste sur le bouton « Enregistrer » en haut à droite de l'éditeur. |
| D6 | Une unité oubliée se corrige simplement : `PARAM COUPON = 8`, Ctrl+S, ajout du `%`, nouveau Ctrl+S → 8 %. |
| D7 | Les deals actuellement en base sont des tests que Philippe supprimera : aucun traitement particulier des deals bookés avant le gel des valeurs. |
| D8 | Mode debug : dernière priorité ; redemander avant de le coder. |

---

## 3. Propositions en attente de confirmation

### P1 — Origine des valeurs Economics (nécessaire à D6, compatible avec D2)

1. **Valeur venue du script, jamais saisie dans Economics** : elle suit la déclaration à
   chaque Ctrl+S, valeur et unité. Le `8` de D6 devient 8 %.
2. **Valeur saisie dans Economics, ou rechargée depuis la base** (script enregistré, deal,
   RFQ) : elle fait foi, quoi que dise le script.
3. **Valeur saisie, puis unité changée dans le script** : on ne devine pas. Le champ passe
   « à vérifier », le pricing est bloqué jusqu'à confirmation, et le nombre affiché sert de
   proposition (9 saisi → 9 % proposé).

Economics affiche l'origine de chaque valeur (« du script » / « saisie »).

*Écartée :* « Economics conserve la valeur économique, la déclaration ne change que
l'affichage ». Un `8` validé sans `%` vaut 8,0 et deviendrait 800 % après l'ajout du `%`,
contraire à D6.

### P2 — Changement de forme d'un CONSTAT

- Ne reporter que les champs qui gardent le même sens : fenêtre, convention, délai de
  règlement.
- Ne jamais inventer de date : une date unique ne dit ni le début ni le roll d'un
  calendrier, et une date de début devinée pricerait faux sans alerte.
- Garder l'ancienne forme de côté pour qu'un aller-retour restitue exactement la saisie
  (règle actuelle du store : « on complète, on ne supprime pas »).

### P3 — Renommage d'un CONSTAT (facultatif)

Si, dans une même validation, un calendrier disparaît et qu'un autre de même forme
apparaît, reprendre les valeurs et l'annoncer dans un bandeau.

### P4 — Règle du scénario saisi du mode debug

Ne concerne que le lot 3, en attente (D8). Détail au §5, lot 3.

---

## 4. Diagnostics

### 4.1 La validation engage des états intermédiaires

- `PayScriptEditor.vue`, `onInput` : chaque pause de 500 ms relance `store.parseScript()`,
  donc `/api/parse`.
- `stores/pricing.js`, `parseScript` : un script qui **ne parse pas** est ignoré (dernière
  lecture valide gardée, testé dans `pricing.test.js`). Un script qui **parse** est engagé
  comme définitif : `_syncParamOverrides` et `_syncConstatOverrides` écrivent dans les
  valeurs Economics.
- `_syncParamOverrides` sème une valeur **une seule fois**, à la première apparition du
  nom. Ensuite, la valeur écrite dans le script n'est plus jamais relue.
- **Conséquence.** `PARAM M_KI_BAR = 60%` interrompu après le `6` : `PARAM M_KI_BAR = 6`
  parse, Economics reçoit 6, puis le `%` est lu sur la déclaration finale
  (`_buildUserParams`). Barrière pricée à **6 %**, sans alerte. Même chose pour `8.25%`
  interrompu sur `8.2`.
- Un `SET` n'est pas concerné : il n'a aucun état à l'écran, le serveur relit le texte à
  chaque pricing. Seules les déclarations qui ont un état côté écran (PARAM, CONSTAT)
  cassent.
- Les réponses de `/api/parse` ne sont pas séquencées : une réponse ancienne peut arriver
  après une récente et laisser une erreur obsolète. Or le bouton Pricer est désactivé tant
  que `parseError` est renseigné.

### 4.2 Onglet Economics blanc sur changement de forme d'un CONSTAT

`_syncConstatOverrides` gère le gain ou la perte d'une réduction MIN/MAX/AVG, mais pas le
changement de **forme** d'un nom qui existe déjà. `EconomicsTab.vue` lit ensuite
`constatOverrides[nom].frequency.value` et `.sub_frequency.value` sans garde.

| Script avant → après | Valeur restée en place | Effet |
|---|---|---|
| `CONSTAT OBS` → `CONSTAT() OBS` | une chaîne (la date) | `.frequency.value` sur une chaîne → exception au rendu |
| `CONSTAT OBS AVG` → `CONSTAT() OBS AVG` | `{date, fenêtre}` sans `frequency` | même exception |
| `CONSTAT() OBS` → `CONSTAT()() OBS` | `sub_frequency: null` | `.sub_frequency.value` sur null → exception |
| `CONSTAT() OBS` → `CONSTAT OBS` | l'objet calendrier | pas d'exception, mais champ date vide et objet envoyé sans `date` |

- En Vue 3, une exception pendant le rendu remplace le composant **entier** par un nœud
  vide : c'est tout l'onglet qui disparaît. `EconomicsTab` est monté en `v-show`, donc le
  crash survient dès la fin du parse, même depuis l'onglet Script. Revenir à la forme
  précédente le fait réapparaître.
- `ConstatWindowFields.vue` se protège déjà contre une valeur de mauvaise forme ; la carte
  parente ne le fait pas.
- Aucun test front ne couvre `single` ni `nested_schedule`. `@vue/test-utils` n'est pas
  installé : pas de test de montage sans ajouter la dépendance.

### 4.3 Lecteurs qui contournent Economics (contraire à D2 et D3)

| # | Où | Ce qui est lu | Effet |
|---|---|---|---|
| 1 | `stores/pricing.js`, `_buildUserParams` | un champ vidé | PARAM en % vidé → pricé à **0** ; tableau `PARAM()` vidé → valeur du script. Rien ne bloque le pricing. |
| 2 | `stores/pricing.js`, `_buildUserParams` | l'unité `is_pct` de la déclaration courante | `8%` → `0.08` dans le script transforme 9 % Economics en 900 %. Traité par P1. |
| 3 | `api/emt.py`, `_detect_features` ; `core/emt_synthesize.py`, `build_emt_payload` (alimenté par `store.scriptParams` depuis `EmtPanel.vue`) | `stored_val`, `raw_default` | Levier de l'EMT et texte envoyé au modèle de rédaction calculés sur les valeurs du script. GEARING à 100 % dans le script, 150 % dans Economics → « pas d'effet de levier ». |
| 4 | `core/client_intelligence.py`, `_niveaux_du_deal` → `core/client_technical.py`, `niveaux_du_script` | `stored_val`, **y compris pour les `M_`** ; cache `_CACHE_NIVEAUX` par texte de script | Coupon et barrières d'un deal lus dans le script, jamais dans les valeurs bookées. Deux deals du même modèle bookés à 8 % et 9 % affichent le même coupon. |
| 5 | `api/deals.py`, watchlist (branche des scripts sans `M_`) et `_script_flags` | `stored_val` ; `_classify_param_barrier` exige une valeur entre 0,2 et 3,0 | Niveau, écart et classement des barrières calculés sur le script. |
| 6 | `SolverPanel.vue`, `prefillBounds` ; `PriceGridHeatmap.vue`, `prefillX` / `prefillY` | `raw_default` | Bornes centrées sur la valeur du script. Un PARAM à 0 % donne une fourchette de 0 à 1 % qui n'encadre pas la valeur Economics. |

**Déjà conforme :** pricing et analytiques (corps commun `_baseBody` → `user_params`), KID
(`req.user_params`), moteur (défauts du script écrasés par `user_params`), branche `M_` de
la watchlist, `_monitor_levels`, barrières du drill-down MTF.

### 4.4 Syntaxe des déclarations (parser)

- `PARAM X = 8` → nombre brut 8 ; `PARAM X = 8%` → 0,08 ; `PARAM X = 0.08` → 0,08.
- `PARAM X` sans valeur → refusé, avec le message « instruction inconnue au niveau 0 », qui
  ne dit pas qu'il manque la valeur.
- `PARAM() X` sans valeur → accepté, **en % par défaut**. À supprimer (D4).
  - Aucun modèle ni script du dépôt n'utilise cette forme.
  - `backend/tests/test_parser.py` la teste (cas `PARAM() M_BAR`).
  - Elle est présentée comme facultative dans `docs/PAYSCRIPT_REFERENCE.md` (tableau des
    déclarations), `docs/PAYSCRIPT_PARAM_PAR_OBSERVATION.md` et le mémo de l'éditeur
    (`PayScriptEditor.vue`).

---

## 5. Plan d'action

Ordre : d'abord ce qui fausse un prix sans alerte, puis ce qui fausse un document, enfin
l'outil de debug. Les lots 1 et 2 sont indépendants.

### Lot 0 — Écrire la règle (documentation seule)

- Ajouter D1 à D3 aux conventions non négociables de `CLAUDE.md`.
- Spécifier le test transversal qui la prouve : script à 8 %, Economics à 9 % ; prix,
  watchlist, fiche Client Intelligence, EMT et bornes du solveur doivent tous montrer 9 %.
  C'est la règle « un test qui exige que ça bouge » de `CLAUDE.md`, appliquée aux lecteurs.

### Lot 1 — Du script vers Economics (front et parser)

1. **Validation explicite (D5).**
   - Ctrl+S intercepté (le navigateur n'ouvre pas « Enregistrer la page sous ») et bouton
     « Valider ».
   - Plus aucune validation pendant la frappe ; un état « modifié, non validé » à la place.
   - Pricer, Greeks et booking valident d'abord et s'arrêtent sur erreur.
   - Réponses de validation séquencées : une réponse périmée est ignorée.
   - Les chargements (modèle, script enregistré, deal, RFQ, script de l'assistant) restent
     validés immédiatement, comme aujourd'hui.
2. **Report des déclarations dans Economics à la validation seulement**, selon P1.
3. **Champ vide bloquant** (« valeur requise »), scalaire comme tableau, sans repli sur 0 ni
   sur le script.
4. **`PARAM()` à valeur obligatoire (D4).**
   - Parser : message explicite, valable aussi pour `PARAM` sans valeur (« PARAM attend une
     valeur par défaut, ex. `= 60%` »).
   - Reprendre `test_parser.py`, `docs/PAYSCRIPT_REFERENCE.md`,
     `docs/PAYSCRIPT_PARAM_PAR_OBSERVATION.md`, le mémo de l'éditeur et ce que l'assistant IA
     sait du langage.
   - Les scripts de la bibliothèque (base non versionnée, non inspectée) qui déclareraient un
     `PARAM()` sans valeur afficheront l'erreur au chargement.
5. **CONSTAT qui change de forme**, selon P2 ; garde de rendu sur chaque carte (forme
   vérifiée avant affichage) ; filet `onErrorCaptured` par onglet pour qu'une erreur de
   rendu s'affiche au lieu d'une page blanche.
6. **Rapport de validation** : erreurs cliquables vers la ligne, résumé des déclarations,
   changements d'unité et valeurs « à vérifier ». Le libellé « Déclaré » d'Economics devient
   « Valeur initiale du script ».

*Vérification :* tests ciblés dans `frontend/src/stores/pricing.test.js` (transitions
PARAM et CONSTAT, état intermédiaire jamais engagé, cas D6, réponse périmée ignorée),
`backend/tests/test_parser.py` pour D4, puis `npm run build`.

### Lot 2 — Tous les lecteurs sur Economics (backend et deux écrans)

1. **Client Intelligence** : coupon et barrières lus dans `market_snapshot.user_params` de
   chaque deal ; revoir le cache, dont la clé ne peut plus être le seul texte du script.
2. **EMT** : levier et texte de rédaction calculés sur les valeurs de la requête
   (`user_params`).
3. **Watchlist des scripts sans `M_`** et `_script_flags` : niveau, écart et classement sur
   la valeur bookée.
4. **Solveur et grille** : bornes centrées sur la valeur Economics.

*Vérification :* tests des domaines touchés et test transversal du lot 0 ; redémarrage du
backend par Philippe.

### Lot 3 — Mode debug : EN ATTENTE

> **Dernière priorité. Ne pas coder sans avoir redemandé à Philippe s'il faut le faire.**

Conception à reprendre si le chantier est relancé.

**Principe : tracer le pricing lui-même**, dans `engine._eval_paths` (mêmes tirages, mêmes
courbes, même règlement), jamais une nouvelle simulation.
- `run_mc_paths` refait ses propres tirages (500 chemins par défaut) à taux plat : ce ne
  sont pas les chemins qui ont fait le prix.
- Le backtest (`eval_script_on_history`) est un autre interpréteur.
- Le modèle à suivre est le drill-down MTF, qui rejoue les mêmes tirages et réconcilie au
  centime.

**Pourquoi c'est peu invasif.** `_eval_paths` boucle chemin par chemin avec un contexte
explicite (`ctx` : spots, S_PREV, S_MIN/S_MAX, WOF_min/BOF_max, REALVOL, rang, `memo` =
PARAM + SET, accum, flux, STOP) et exécute chaque bloc par `ev.fn(ctx, st)`. Un cycle = un
bloc exécuté à une date. On capture l'état avant et après, pour les seuls chemins suivis ;
éteint par défaut.

**Contenu d'une ligne de trace** (chemin × date × bloc) :
- date (comptée depuis le strike, depuis la date de valorisation en cours de vie), `t`,
  `t_pay`, bloc et rang lu ;
- niveaux lus par ce bloc après réduction MIN/MAX/AVG (deux blocs du même jour peuvent lire
  deux niveaux différents), WOF/BOF, S_PREV, extrêmes (« extrême de pont » en surveillance
  continue) ;
- valeur de chaque `PARAM()` au rang lu, via `_pobs`, jamais recalculée à part ;
- variables SET avant et après ;
- flux (montant, facteur d'actualisation à la date de paiement, PV), STOP ;
- en cours de vie, une première ligne « état hérité du passé ».

**Lignes exécutées.** `parser._compile_body` génère le Python instruction par instruction :
une compilation debug peut poser un marqueur de ligne, surligné dans l'éditeur. Une erreur
d'exécution indiquerait chemin, date, ligne et variables au moment de l'échec.

**Étapes :**
1. Scénario saisi à la main (un seul chemin).
2. Chemins du vrai Monte Carlo, un représentant par issue, avec le jumeau antithétique.
3. Vue agrégée sur tous les chemins : moyenne, min/max, % vrai, % encore vivants.

**Garde-fous :**
- prix identique au bit avec et sans trace ;
- script compilé en debug identique au script normal ;
- sur un petit N, moyenne des PV tracés = prix affiché ;
- chemins suivis plafonnés (ne pas saturer la machine), passage par le budget de calcul ;
- une seule boucle instrumentée : `_eval_paths_detailed` est une copie de la même boucle.

**P4 — Règle du scénario saisi (proposée, à confirmer).** `WOF_MIN`, `S_MIN`/`S_MAX`, les
fenêtres MIN/MAX/AVG et `REALVOL` dépendent du trajet **entre** les dates, que deux niveaux
ne déterminent pas. Exemple : KI américaine à 60 %, 95 % à l'obs 1 puis 70 % à l'obs 2 ; le
cours a pu toucher 55 % entre les deux. Règle proposée :
1. le niveau saisi est exactement ce que la constatation lit (une fenêtre de moyenne est à
   ce niveau) ;
2. ligne droite entre deux dates ;
3. colonnes facultatives « plus bas atteint » et « plus haut atteint » par période, pour
   tester une barrière américaine ou un lookback ;
4. `REALVOL` saisie directement.

---

## 6. Règles de travail pour ce chantier

- Pas de code tant que Philippe ne l'a pas demandé ; ni commit ni push sans instruction
  explicite.
- Seulement les tests du domaine touché ; la suite complète uniquement sur demande de
  Philippe.
- `npm run build` après toute modification Vue.
- Le redémarrage du backend revient à Philippe.
