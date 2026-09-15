# Modèles de produits, éditeur et maturité — note de travail

> **Statut au 14/09/2026 (soir) : lots 1 à 4 codés**, à la demande de Philippe, sur la
> branche `codex/product-workflow` après son commit `553dee6`. **Non commité.** Le détail de
> ce qui a été fait, des choix d'implémentation et des points encore ouverts est au §9.
>
> **Redémarrage du backend nécessaire** (parser et `/api/parse`) : sans lui, le frontend
> fonctionne mais sans le refus d'une maturité antérieure à la dernière année `AT`, et le
> message explicite de `PARAM()` sans valeur n'apparaît pas.
>
> Le mode debug de la note du 11/09 (`EDITEUR_ECONOMICS_DESIGN.md`, lot 3) reste la
> dernière priorité : redemander à Philippe avant de le coder.

Lecture du code faite le 14/09/2026 sur la copie de travail, branche
`codex/product-workflow`, qui porte des modifications non commitées de l'objet Product
(notamment `frontend/src/stores/pricing.js` et `frontend/src/views/HomeView.vue`). Les
références citent des fichiers et des fonctions plutôt que des numéros de ligne, qui
bougent.

Cette note complète `EDITEUR_ECONOMICS_DESIGN.md` (11/09) et en tranche la proposition P1.

---

## 1. Objet

Cinq sujets soulevés par Philippe le 14/09/2026 :

1. Les modèles de scripts Normal et Expert sont-ils à jour ?
2. Ctrl+S ouvre un outil du navigateur et ne fait rien dans le script.
3. Une valeur par défaut modifiée dans le script doit changer dans l'écran.
4. Ce qui a été décidé sur la date de maturité.
5. Une liste de scripts génériques de produits, vides, et un moyen simple d'ouvrir une page
   de pricing correctement complétée.

---

## 2. Décisions de Philippe (14/09/2026)

| # | Décision |
|---|---|
| M1 | **Ctrl+S valide le script.** Aujourd'hui il ouvre la boîte « Enregistrer la page » du navigateur (confirme D5 du 11/09, jamais codé). |
| M2 | **Changer la valeur par défaut d'un PARAM dans le script change la valeur dans l'écran** (Economics). Tranche P1 du 11/09 : la modification du script gagne à la validation. |
| M3 | Un coupon `COUPON × INDEX` payé semestriellement **ne pose pas de problème** : c'est un coupon par période, convention de desk. Aucun changement. |
| M4 | **La date de maturité est toujours éditable** et correspond à la **dernière date de constatation du produit, quels que soient les échéanciers**. Remplace la règle introduite le 13/09 (commit `d638b51`). |
| M5 | Une **liste de scripts génériques de produits, vides**, que l'utilisateur complète. |
| M6 | Un **nouveau module dans le menu de la catégorie Pricing**, nommé **« Modèles de produits »** : on choisit un script dans la liste, un nombre de sous-jacents et un ténor, et le Pricer s'ouvre correctement complété. Pas d'assistant en étapes, pas d'écran de saisie supplémentaire. |
| M7 | **Garder les modes Normal et Expert. Ne pas toucher au masque de pricing.** |
| M8 | Date de départ des calendriers générés : **la date de strike du Pricer** (aujourd'hui par défaut). |
| M9 | Ténors proposés : **6M, 1Y, 18M, 2Y, 3Y, 4Y, 5Y, 7Y, 10Y**, limités selon le produit. |
| M10 | Le catalogue doit permettre **d'ajouter des payoffs dans le temps**. |
| M11 | `PARAM()` : quand la valeur initiale change dans le script, **seules les lignes restées à l'ancienne valeur sont mises à jour** ; les lignes saisies sont conservées. |
| M12 | Une maturité avancée avant la fin d'un échéancier non terminal est **refusée**. |
| M13 | Après ouverture depuis le module, **le calendrier ne suit pas un changement de date de strike** : c'est à l'utilisateur de s'assurer des bonnes dates. |
| M14 | **Un bouton « Valider » s'ajoute** au raccourci Ctrl+S — seule exception à M7. |
| M15 | Branche `codex/product-workflow` : **on n'y touche pas**. Le code de ce chantier attendra que Philippe ait terminé son travail sur cette branche. |

---

## 3. Rappel des décisions antérieures

### 3.1 Éditeur et Economics (11/09, `EDITEUR_ECONOMICS_DESIGN.md`)

- D1 : le script définit le payoff et déclare chaque PARAM avec son unité et une valeur
  initiale.
- D2 : Economics fait foi pour les valeurs ; D3 : tout le reste lit Economics, `M_` compris.
- D4 : `PARAM()` exige une valeur, comme `PARAM`.
- D5 : validation au Ctrl+S ; **Ctrl+S ne fait que valider**, l'enregistrement reste sur le
  bouton « Enregistrer » en haut à droite de l'éditeur.
- D6 : `PARAM COUPON = 8`, Ctrl+S, ajout du `%`, nouveau Ctrl+S → 8 %.

### 3.2 Sauvegarde

- **Script** : pas de sauvegarde automatique (D5).
- **Objet Product** : le 13/09, Philippe demande une action explicite pour garder l'objet en
  le nommant. Une sauvegarde automatique aux gestes engageants (AO « to trade », KID client,
  booking) a été proposée et **n'est pas tranchée**. Le plan du 14/09
  (`docs/projects/platform/PLAN_IMPLEMENTATION_OBJET_PRODUCT.md`, branche `codex/product-workflow`) retient
  « Conserver le produit » comme seule création durable.

### 3.3 Date de maturité, chronologie

| Date | Décision |
|---|---|
| 30/07 | L'horizon d'`AT MATURITY` est la maturité déclarée par le deal, **pas** la fin du calendrier : « 2 ans de coupons sur une note 3 ans » doit rester possible. |
| 27/08 | Maturité = dernière constatation ; paiement à J+3 ouvrés par défaut, modifiable ; axe des temps ancré au strike (`CLAUDE.md`). |
| 10/09 | `INDEX` = rang dans l'échéancier que le bloc nomme ; refusé dans `AT MATURITY`. |
| 13/09 | Commit `d638b51` : maturité éditable seulement sans échéancier ; avec un échéancier, sa dernière date fait foi et le champ se verrouille. |
| 14/09 | **M4** : toujours éditable, égale à la dernière constatation, tous échéanciers confondus. |

---

## 4. Diagnostics

### 4.1 Revue des 35 modèles

Sonde en lecture seule (analyse du script, sans Monte Carlo) sur
`frontend/src/data/payscriptTemplates.js` : les **16 modèles Normal et les 19 Expert
compilent**. Tous déclarent valeur et unité (D1) ; la convention `M_` est en place ; aucun
`PARAM()` sans valeur.

**Faux sans alerte**

- **Normal, durée écrite dans le script** (`AT 1, 2, 3`) alors que la maturité est
  éditable : allonger laisse des années sans observation ; raccourcir laisse une observation
  après la maturité, que le booking refuse.
- **Normal, durée des libellés jamais appliquée** : « Capital Garanti 5 ans » et
  « Reverse Convertible 1 an » se pricent sur la maturité en place (T = 3 par défaut).
  `loadExample` (`PayScriptEditor.vue`) ne touche ni T ni la maturité.
- **« Worst-of 2 actifs »** (Athena, Gear Put, Shark) : `loadExample` n'ajoute aucun
  sous-jacent ; avec le panier par défaut, c'est un mono.
- **Gear Put** : l'Expert fixe le strike sur une moyenne (`CONSTAT STRIKE_FIX AVG`, 10 jours
  pré-remplis), le Normal sur un cours : deux produits sous le même libellé.

**Incohérences**

- Type de barrière non dit : Athena, Phoenix, Gear Put, Reverse Convertible testent `WOF`
  (européenne) ; Worst-of Athena et Twin Win testent `WOF_MIN` (américaine). La référence du
  langage dit qu'une KI est « presque toujours américaine ».
- Gear Put : `M_PUT_STRIKE` n'est jamais comparé ; l'analyse des monitors le rend sans
  observable ni direction, la watchlist ne sait pas le lire.
- Noms trompeurs : `PLANCHER` du Booster n'est pas un plancher (perte 1 pour 1) ; `REBATE`
  de la Digitale est le coupon ; « Reverse Convertible » à barrière 80 % est une BRC.
- Shark worst-of : KO sur `BOF_MAX`, participation sur `WOF` — à confirmer côté métier.

**Sources et couverture**

- `backend/app/core/payscript/templates.py` est généré par
  `backend/scripts/sync_payscript_templates.py` à partir des **seuls** modèles Normal ;
  `backend/tests/test_payscript_templates.py` ne teste donc **aucun modèle Expert**.
- Phoenix mémoire, barrière de rappel dégressive et BRC à KI américaine n'existent que dans
  `backend/app/services/llm/examples_extra.py` (exemples de l'assistant IA).
- `services/uat_generation.py`, `_product_script`, a ses propres scripts qui divergent :
  Athena à coupon non cumulé, « Phoenix Mémoire » sans mémoire, `M_PARTICIPATION` sur une
  participation, reverse convertible dont la date unique s'appelle `OBSERVATIONS`.
- `docs/reference/PAYSCRIPT_REFERENCE.md` (corps du prompt de l'assistant) dit encore que `AT 1, 2, 3`
  compte « depuis aujourd'hui » (l'axe part du strike) et que `PARAM()` a une valeur
  facultative (contraire à D4).

**Les dates des modèles Expert** ne sont pas dans les scripts : elles viennent de
`getExpertConstatDefaults` (`PayScriptEditor.vue`, aujourd'hui + 1, 3 ou 5 ans, calendrier
annuel, fenêtre `STRIKE_FIX` de 10 jours, fenêtre finale de 30 jours) et des défauts du
store (trade, strike et valeur = aujourd'hui).

### 4.2 Ctrl+S

- `PayScriptEditor.vue` n'intercepte que la tabulation (`onEditorTab`) : aucun raccourci
  Ctrl+S ou Cmd+S, le navigateur ouvre sa boîte « Enregistrer la page ».
- La validation part toujours pendant la frappe (pause de 500 ms, `store.parseScript`) :
  le diagnostic 4.1 du 11/09 (états intermédiaires engagés) reste valable.

### 4.3 Valeur du script vers Economics

- `stores/pricing.js`, `_syncParamOverrides` : une valeur n'est semée **qu'à la première
  apparition du nom**. Ensuite la valeur écrite dans le script n'est plus jamais relue :
  une modification du script reste invisible dans Economics.
- L'unité, elle, est relue sur la déclaration courante (`_buildUserParams`) : c'est l'écart
  n° 2 de la note du 11/09.

### 4.4 Maturité, état du code

- `stores/pricing.js`, `_maturityDate` : s'il existe un échéancier, la plus grande
  `end_date` des échéanciers (les CONSTAT uniques sont ignorés) ; sinon un CONSTAT unique
  nommé `MATURITE` ou `MATURITY` ; sinon `globalParams.maturity_date` ; sinon strike + T.
- `maturityDateEditable` est faux dès qu'un échéancier existe ; `setMaturityDate` écrit
  dans le CONSTAT `MATURITE` ou dans `globalParams.maturity_date` ; `syncTenorFromMaturity`
  recalcule T.
- `core/schemas.py` : `maturity_date` est une étiquette ; l'horizon du moteur reste `T`.
- `api/deals.py` : le booking refuse tout événement postérieur à `maturity_date`
  (« Le calendrier contractuel dépasse la maturité du deal »). En mode Normal, les dates
  d'événements valent strike + t × 365,25 jours (`_date_plus_years`), sans ajustement de
  jour ouvré.
- `RfqView.vue`, `detailMaturityDate` : sans calendrier, la maturité du détail d'un AO se
  compte depuis la **date de valeur**, alors que la création et le serveur partent du strike.
- **Cas cassé aujourd'hui, réglé par M4** : échéancier de coupons sur 2 ans et
  `CONSTAT MATURITE` à 3 ans → maturité affichée à 2 ans, T = 2, paiement proposé à 2 ans,
  booking refusé.

---

## 5. Conception proposée

### 5.1 Ctrl+S (M1)

- Ctrl+S (Cmd+S sur Mac) intercepté dans le Pricer : il **valide** le script et
  n'enregistre jamais. Le navigateur n'ouvre plus sa boîte.
- Un bouton « Valider » dans l'éditeur fait la même chose que Ctrl+S (M14). C'est le seul
  contrôle ajouté au masque.
- Plus aucune validation pendant la frappe. L'état « script modifié, non validé » s'affiche
  dans la zone de message existante de l'éditeur.
- Pricer, Greeks et booking valident d'abord et s'arrêtent sur erreur.
- Réponses de validation séquencées : une réponse périmée est ignorée.
- Les chargements (modèle, script enregistré, deal, RFQ, script de l'assistant, module
  « Modèles de produits ») restent validés immédiatement.

### 5.2 Valeur du script vers Economics (M2)

Règle : **la dernière modification explicite gagne.**

1. À chaque validation, tout PARAM dont la **déclaration a changé** (valeur ou unité)
   depuis la validation précédente reporte sa nouvelle valeur dans Economics, même si une
   autre valeur y avait été saisie.
2. Une déclaration **inchangée** ne touche pas Economics : un Ctrl+S n'efface aucune saisie.
3. Au **chargement** (script enregistré, deal, RFQ, déclinaison), les valeurs enregistrées
   s'affichent et deviennent la référence de comparaison.
4. Une valeur saisie remplacée par celle du script est **signalée** dans la zone de message
   (« COUPON : 9 % → 10 % »), pour qu'aucune saisie ne disparaisse sans le dire.
5. `PARAM()` : seules les lignes restées à l'ancienne valeur initiale sont mises à jour ;
   les lignes saisies sont conservées (M11).
6. D6 est couvert : `8`, Ctrl+S, ajout du `%`, Ctrl+S → 8 %.
7. Deal booké : termes figés, rien ne change.

La comparaison se fait à la validation, jamais pendant la frappe : c'est ce qui supprime
la barrière pricée à 6 % au lieu de 60 % (diagnostic du 11/09).

### 5.3 Maturité (M4)

**Définition.** Maturité = dernière date de constatation **effective** (après convention
de jour ouvré), sur l'ensemble des constatations du produit : dates des échéanciers
(`CONSTAT()`, `CONSTAT()()`), CONSTAT uniques avec leur fenêtre de fin, et en mode Normal
les dates `AT` et `AT MATURITY`. `STRIKE_FIX` n'entre pas en compte (fenêtre de départ).

**Toujours éditable**, sauf termes figés d'un deal booké.

**Modifier la maturité**
- Déplace la ou les constatations **terminales**, celles qui tombaient à l'ancienne
  maturité : fin d'échéancier (et date de roll si elle était alignée sur la fin), date d'un
  CONSTAT unique avec sa fenêtre.
- Les échéanciers qui se terminent avant ne bougent pas : « 2 ans de coupons sur une note
  3 ans » reste exprimable.
- Une maturité avancée avant la fin d'un échéancier non terminal est **refusée**, avec un
  message qui nomme l'échéancier (M12).
- T, aperçu des dates et date de paiement proposée (si elle n'a pas été saisie) se
  recalculent aussitôt.
- Une date tombant un jour fermé affiche la date ajustée, comme à la création d'un AO.

**Mode Normal.** Pas de CONSTAT : `AT MATURITY` suit la maturité. Les années `AT` restent
écrites dans le script, donc une maturité antérieure à la dernière année `AT` est refusée
avec un message.

**Plus de reconnaissance par le nom** `MATURITE` / `MATURITY` : la constatation terminale
se calcule.

**Même règle partout** : store et onglet Economics du Pricer ; détail d'un AO (maturité
comptée depuis le strike) ; booking, où le contrôle « calendrier au-delà de la maturité »
devient une garantie ; échéancier figé de l'objet Product ; libellés du Life Cycle.

### 5.4 Catalogue des scripts génériques (M5, M10)

**Source unique, versionnée dans le dépôt** (`frontend/src/data/`, à côté de
`payscriptTemplates.js`), avec une copie serveur synchronisée et testée sur le modèle de
`sync_payscript_templates.py`.

**Une fiche par produit**
- clé, libellé **sans durée ni nombre d'actifs**, famille, description courte ;
- script générique : PARAM avec unité et valeur initiale (D1, D4), CONSTAT **sans date**,
  blocs `AT` ;
- rôle de chaque CONSTAT : observations, maturité, fenêtre de départ ;
- fréquence d'observation par défaut et fenêtres par défaut (longueur de `STRIKE_FIX`,
  fenêtre finale) ;
- nombre de sous-jacents minimum et maximum ;
- ténors autorisés, pris dans la liste M9.

**Indépendant du nombre de titres.** `WOF`, `BOF` et `BASKET` valent pour 1 à N
sous-jacents : un seul « Autocall Athena » couvre mono et worst-of. L'agrégation fait
partie du produit : un Athena sur panier moyen serait une autre fiche.

**Liste initiale proposée** (§6.2, question 3) : Autocall Athena (barrière à maturité),
Autocall Athena KI américaine, Phoenix, Phoenix mémoire, Autocall à barrière de rappel
dégressive, Autocall Gear Put, Autocall à coupon moyenné sur période, Reverse convertible
(barrière à maturité), BRC à KI américaine, Capital garanti, Twin Win, Booster, Shark note,
Call, Put, Call spread, Digitale, Call panier moyenné, Call lookback. Le ZCB reste un modèle
de validation Normal/Expert, hors catalogue.

**Tests** : chaque fiche compile ; price sur un calendrier généré court avec un petit
nombre de chemins (pas de sonde lourde) ; possède une constatation terminale ; respecte ses
bornes de sous-jacents et de ténors.

**Ajouter un payoff** = ajouter une fiche et passer les tests, sans toucher aux écrans.
Plus tard, non planifié : promotion par un admin d'un script de Mes Scripts vers le
catalogue (brouillon → validé → publié).

**Normal et Expert (M7)** restent tels quels dans le Pricer. Les faire lire le catalogue,
avec le corpus de l'assistant et les scripts UAT, éviterait les divergences sans changer le
masque (§6.2, questions 1 et 2).

### 5.5 Module « Modèles de produits » (M6 à M9)

**Entrée** : une carte dans la catégorie Pricing de la page d'accueil (`HomeView.vue`), à
côté de Mes Scripts, du Pricer et de Documentation (et de « Mes Produits » sur la branche
en cours). Route dédiée, bouton retour vers le menu Pricing.

**Page** : sélection simple, sans saisie
- liste des produits du catalogue, groupés par famille (libellé et description courte) ;
- nombre de sous-jacents, borné par la fiche ;
- ténor, dans la liste M9 filtrée par la fiche ;
- bouton « Ouvrir dans le Pricer ».

**Produit, nombre de sous-jacents et ténor choisis** : le Pricer existant s'ouvre, masque
inchangé, avec
- le script générique chargé et validé ;
- N sous-jacents « Sous-jacent 1 … N » aux hypothèses de marché par défaut du Pricer,
  matrice de corrélation N × N ; tickers à choisir, marché à recharger ;
- les calendriers générés depuis la date de strike du Pricer (M8) jusqu'à strike + ténor,
  avec la fréquence et les fenêtres de la fiche ;
- la maturité égale à la dernière constatation (M4), T recalculé, la date de paiement
  proposée à maturité + 3 jours ouvrés du calendrier de la devise ;
- les PARAM aux valeurs initiales du script.

Une fois ouvertes, les dates générées sont indépendantes : changer ensuite la date de
strike **ne déplace pas** le calendrier. C'est à l'utilisateur de s'assurer des bonnes
dates (M13).

**Produit seul** : le Pricer s'ouvre avec le script générique et rien d'autre — calendriers
vides, aucune date inventée, y compris pour la date de strike. L'utilisateur complète
Economics ; les messages d'erreur existants disent ce qui manque au pricing.

**Mécanisme d'ouverture** : un paramètre d'ouverture lu par le Pricer, sur le modèle de
l'ouverture depuis une RFQ. Aucun contrôle ajouté au masque. Si la session du Pricer
contient des modifications non enregistrées, le module le signale avant d'ouvrir.

**Objet Product** : l'ouverture crée une session éphémère, non conservée, cohérente avec
« Conserver le produit ».

---

## 6. Questions

### 6.1 Tranchées le 14/09

`PARAM()`, maturité avancée, calendrier après un changement de strike, bouton « Valider »
et branche en cours : réponses consignées en M11 à M15.

### 6.2 Encore ouvertes

1. Contenu des exemples Normal et Expert : corriger ce que relève le §4.1 (libellés à durée,
   worst-of, Gear Put, type de barrière, noms), sans toucher au masque ?
2. Scripts du générateur UAT et corpus de l'assistant IA : les aligner sur le catalogue ?
3. Liste initiale des fiches du catalogue (§5.4).
4. Hors de ce chantier : sauvegarde automatique de l'objet Product aux gestes engageants
   (§3.2).

---

## 7. Plan d'action

Ordre : les lots 1 et 2 sont indépendants ; le lot 4 dépend du lot 2 (maturité) et du lot 3
(catalogue).

### Lot 0 — Préalables (sans code)

- Attendre que Philippe ait terminé son travail sur la branche `codex/product-workflow`
  (M15).
- Relire alors les fichiers que cette branche a modifiés et que ce chantier touche (store du
  Pricer, accueil Pricing), et remettre à jour les références de cette note.
- Trancher les questions encore ouvertes du §6.2, au moins la liste des fiches.

### Lot 1 — Éditeur (M1, M2)

- `PayScriptEditor.vue` : raccourci Ctrl+S / Cmd+S et bouton « Valider » (M14), fin de la
  validation pendant la frappe.
- `stores/pricing.js` : validation séquencée ; report des déclarations modifiées dans
  Economics selon le §5.2 ; message des valeurs remplacées.
- Parser : `PARAM()` à valeur obligatoire avec message explicite (D4).
- `docs/reference/PAYSCRIPT_REFERENCE.md` et mémo de l'éditeur : origine au strike, `PARAM()`
  obligatoire.

*Vérification :* tests ciblés dans `frontend/src/stores/pricing.test.js` (valeur changée →
Economics ; déclaration inchangée → saisie conservée ; `PARAM()` avec lignes saisies
conservées (M11) ; chargement ; cas D6 ; réponse périmée ignorée),
`backend/tests/test_parser.py` pour D4, puis `npm run build`.

### Lot 2 — Maturité (M4)

- `stores/pricing.js` : `_maturityDate`, `maturityDateEditable`, `setMaturityDate` selon le
  §5.3 ; fin de la reconnaissance par le nom.
- `EconomicsTab.vue` : champ toujours éditable, texte d'aide aligné.
- `RfqView.vue` : maturité du détail comptée depuis le strike.
- `api/deals.py` et objet Product : même définition.

*Vérification :* tests ciblés — 2 ans de coupons et maturité 3 ans (booking accepté) ;
échéancier et CONSTAT unique le même jour ; déplacement de la maturité d'un calendrier
trimestriel ; maturité avancée avant la fin d'un échéancier non terminal refusée (M12) ;
jour fermé ; mode Normal avec maturité antérieure à la dernière année refusée ;
`npm run build`.

### Lot 3 — Catalogue (M5, M10)

- Fichier de catalogue et copie serveur synchronisée.
- Fiches de la liste validée (§6.2, question 3).
- Tests du §5.4.

### Lot 4 — Module « Modèles de produits » (M6 à M9)

- Carte dans la catégorie Pricing de `HomeView.vue`, nouvelle vue et route.
- Génération des calendriers depuis la date de strike, le ténor et la fiche.
- Ouverture du Pricer remplie ou vierge, sur le modèle de l'ouverture depuis une RFQ.

*Vérification :* tests de génération (dates, maturité, nombre de sous-jacents ; changer la
date de strike après ouverture ne déplace pas le calendrier, M13),
`npm run build`, vérification visuelle dans le Chrome de Philippe sans jamais saisir
d'identifiants.

### Lot 5 — Suites, après validation

- Corrections du contenu des exemples Normal et Expert (§6.2, question 1).
- Alignement des scripts UAT et du corpus de l'assistant (§6.2, question 2).
- Guide « ajouter un payoff au catalogue ».

---

## 8. Règles de travail pour ce chantier

- Pas de code tant que Philippe ne l'a pas demandé ; ni commit ni push sans instruction
  explicite.
- Seulement les tests du domaine touché ; la suite complète uniquement sur demande de
  Philippe.
- `npm run build` après toute modification Vue.
- Le redémarrage du backend revient à Philippe.
- Aucune sonde lourde : petits nombres de chemins dans les tests du catalogue.
- Le mode debug de la note du 11/09 reste la dernière priorité.

---

## 9. Implémentation du 14/09/2026 (lots 1 à 4, non commitée)

### 9.1 Lot 1 — Éditeur

- **Ctrl+S / Cmd+S** intercepté partout dans le Pricer (écouteur posé par
  `PayScriptEditor.vue`) : il valide, n'enregistre jamais, et le navigateur n'ouvre plus sa
  boîte. **Bouton « Valider »** dans la barre de l'éditeur (M14).
- **Plus de validation pendant la frappe.** `stores/pricing.js` distingue le texte validé
  (`validatedScript`) du texte de la dernière tentative (`checkedScript`) ;
  `scriptDirty` affiche « Script modifié, non validé » dans la zone de message.
- **Validation séquencée** : une réponse périmée ou arrivée après une frappe est ignorée.
- **Tout calcul valide d'abord** et s'arrête sur erreur : prix, prix en cours de vie,
  Greeks, profil, chemins, probabilités, backtest, comparateur, MtF, solveur, grille,
  scénarios, spread implicite (`_prepareCalculation`, synchrone quand rien n'est à valider),
  ainsi que KID, EMT, comparateur de sous-jacents et comparaison de déclinaisons
  (`ensureScriptValidated`). Le booking est couvert par le contrôle « pricing périmé ».
  Le bouton ▶ Pricer reste actif quand le script a été modifié après une erreur : le clic
  revalide.
- **Report vers Economics (M2, M11)** : `_applyDeclarationChanges`. Rapport affiché dans
  l'éditeur (« COUPON : 7,5 % → 9 % », lignes de `PARAM()` saisies conservées). D6 couvert.
  Les chargements gardent l'ancienne règle (seuls les noms nouveaux sont semés) et
  deviennent la référence ; l'adoption d'un script de l'assistant IA est une validation
  explicite.
- **D4** : `PARAM()` sans valeur refusé par le parser ; `PARAM` sans valeur reçoit le même
  message explicite au lieu d'« instruction inconnue ». Base de Philippe lue en lecture
  seule avant le changement : aucun texte enregistré ne contient `PARAM()`.
- Documentation : `docs/reference/PAYSCRIPT_REFERENCE.md` (valeur obligatoire, années `AT` comptées
  depuis le strike), `docs/projects/pricing/PAYSCRIPT_PARAM_PAR_OBSERVATION.md`, mémo de l'éditeur, règle 10
  du prompt de l'assistant ; `PROMPT_VERSION` passe au 14/09.

### 9.2 Lot 2 — Maturité

- `_maturityDate` : dernière date de toutes les constatations datées (échéanciers et dates
  uniques, `STRIKE_FIX` exclu), années `AT` datées depuis le strike, et date du champ
  Maturité pour `AT MATURITY`. Repli historique strike + T pour un script sans calendrier.
- **Date effective** : une constatation portant une convention de jour ouvré est résolue par
  `/api/calendar/resolve` ; tant que la réponse n'est pas là, la date saisie en tient lieu.
- **Toujours éditable** (sauf termes figés). La saisie se retient **en quittant le champ ou
  sur Entrée** : un champ date émet une date complète à chaque segment tapé, et une année
  intermédiaire aurait déplacé les constatations terminales.
- Refus avec message sous le champ : maturité avant la fin d'un échéancier non terminal
  (M12), ou avant la dernière année `AT` du script (mode Normal).
- Plus de reconnaissance par le nom `MATURITE` : sa carte réapparaît dans Economics
  (fenêtre et convention de nouveau saisissables).
- `/api/parse` expose `at_dates` (années des blocs `AT` littéraux).
- `RfqView.vue` : maturité du détail d'un AO comptée depuis le strike.
- Booking : aucun changement de code ; un test fige que deux ans de coupons sur une note à
  trois ans se bookent, et que l'ancienne dérivation était refusée.

### 9.3 Lot 3 — Catalogue

- Source unique : `frontend/src/data/productCatalogue.json` (script écrit ligne à ligne).
  Copie serveur générée : `backend/app/core/payscript/catalogue.py`, par
  `backend/scripts/sync_product_catalogue.py`.
- **19 fiches, la liste proposée au §5.4** (question 6.2-3 : à confirmer par Philippe).
  Rôles de CONSTAT : `observations`, `maturity`, `strike_window`.
- `backend/tests/test_product_catalogue.py` : synchronisation, libellés sans durée ni nombre
  d'actifs, bornes, rôles, constatation terminale, compilation, pricing à 300 chemins sur le
  ténor le plus court.
- Choix de contenu : Phoenix et Phoenix mémoire à barrière observée à maturité ; gear put
  sans strike moyenné et avec `M_PUT_STRIKE` réellement comparé (la watchlist sait le lire) ;
  Booster sans le faux « plancher » ; coupon de la Digitale nommé `COUPON`.

### 9.4 Lot 4 — Module « Modèles de produits »

- Carte dans la catégorie Pricing de l'accueil, route `/product-models`, vue
  `ProductModelsView.vue`.
- Génération (`frontend/src/utils/productModels.js`) : échéancier du strike à strike +
  ténor, **roll sur le strike**, fréquence de la fiche, **sans convention de jour ouvré ni
  décalage de règlement** (une convention se saisit, elle n'a pas de défaut) ; date unique à
  maturité ; fenêtre `STRIKE_FIX` au strike ; longueurs de fenêtre de la fiche.
- Ouverture par `/pricer?modele=…&sousJacents=…&tenor=…`, lue par `Pricer.vue` comme
  l'ouverture depuis une RFQ. Nombre de sous-jacents par défaut : le minimum de la fiche.
- **Sans ténor** : script seul, aucune date — strike et date de valeur vidés.
- **Session non enregistrée** : le module demande confirmation avant de la remplacer
  (`hasUnsavedSession` compare le produit à l'état du dernier chargement ou enregistrement ;
  le marché, les résultats et la date de paiement proposée n'en font pas partie).

### 9.5 Défauts trouvés en vérifiant, corrigés

Vérification visuelle faite sur le serveur Vite avec l'API simulée dans l'onglet (backend de
Philippe arrêté à ce moment-là) : carte, module, ouverture remplie et vide, Ctrl+S réel,
rapport de valeurs, refus de maturité.

- **Remise à zéro du Pricer** : `_resetInputState` effaçait les valeurs des CONSTAT mais
  laissait les déclarations du produit précédent jusqu'au parse suivant. Economics plantait
  au rendu (`constatOverrides.OBS.frequency`), et le Pricer ne chargeait plus rien ensuite.
  Défaut antérieur (« Nouveau Pricing » après une session à échéancier), rendu fréquent par
  le module. Les déclarations sont désormais vidées avec les valeurs ; test ajouté.
- **Garde de rendu** sur chaque carte CONSTAT : une valeur de mauvaise forme affiche un
  message au lieu de faire planter l'onglet. Le changement de forme lui-même (P2 du 11/09)
  reste à trancher.
- **Proposition de la date de paiement séquencée** : une réponse ancienne ne peut plus
  écraser la proposition faite pour la dernière maturité.

### 9.6 Encore ouvert

- §6.2 questions 1, 2 et 4 ; question 3 à confirmer (liste des fiches codée = proposition).
- P2 du 11/09 (changement de forme d'un CONSTAT) et champ vide bloquant : non traités.
- Vérification visuelle dans l'instance de Philippe, après redémarrage du backend.
