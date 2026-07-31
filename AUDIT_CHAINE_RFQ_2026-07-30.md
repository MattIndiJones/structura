# Audit de la chaîne RFQ → pricing → booking

**Date :** 2026-07-30 · **Branche :** `feat/client-test-agent`

> Rédigé d'abord comme un pur constat (aucun correctif). Les **9 constats ont
> ensuite été corrigés le même jour** — chacun porte son encadré « Correctif
> appliqué ». Ne subsistent que les mineurs du § 10 et un résiduel de pricing
> signalé au constat 1.

Cet audit succède à [AUDIT_RFQ_2026-07-29.md](AUDIT_RFQ_2026-07-29.md), dont les
6 constats ont été traités dans la journée. Il porte sur le code **tel qu'il est
maintenant**, correctifs du jour inclus — et il en remet un en cause (constat n°1
ci-dessous).

---

## Méthode

Banc d'essai isolé : SQLite en mémoire, appels directs aux fonctions d'endpoint
(même approche que `backend/tests/test_rfq.py`). **Aucune écriture dans la base
de Philippe.** Une cinquantaine de sondes couvrant la création d'AO, les
cotations, le prix modèle, le booking, les mutations d'après-trade, les
catalogues et le calendrier. Chaque constat ci-dessous est un comportement
**observé**, pas déduit d'une lecture de code — le verdict des sondes est cité.

**Non couvert :** les parcours purement visuels (le serveur de Philippe n'a pas
redémarré, il tourne avec le backend de ce matin) ; la concurrence multi-onglets
et multi-utilisateurs simultanés ; le rendu des écrans.

---

## 1. MAJEUR — Maturité fantôme : le deal se résout 4 jours après sa maturité — ✅ CORRIGÉ

**Où :** `deals.py:_derive_observation_times` (ajouté aujourd'hui), `parser.py:effective_T_max`

Un script Athena écrit avec `AT MATURITY:` (construction courante) et un
calendrier CONSTAT de 3 ans, booké avec le **T par défaut du formulaire (3.0)** :

```
idx=0  t=0.0      2026-08-30  « Strike / Fixing S₀ »
idx=1  t=0.9884   2027-08-30  « Obs. 1 (0.99Y) »
idx=2  t=1.9904   2028-08-30  « Obs. 2 (1.99Y) »
idx=3  t=2.9897   2029-08-30  « Obs. 3 (2.99Y) »   ← le vrai dernier constat
idx=4  t=3.0      2029-09-03  « Maturité »          ← n'existe pas au contrat
```

`AT_MATURITY` n'a pas de date propre : il tombe à `effective_T_max(script, T)`
= `max(T, fin de calendrier)`. Avec T=3.0 et une fin de calendrier à 2.9897, le
remboursement est simulé **4 jours après** la dernière observation. Conséquences
mesurées :

- une **cinquième ligne de constatation** apparaît, alors que le produit en a
  quatre ;
- le vrai dernier constat est rétrogradé en « Obs. 3 » et la ligne « Maturité »
  pointe une date qui n'est dans aucun document ;
- `deal.maturity_date` (saisi au booking) dit **2029-08-30**, le dernier event
  dit **2029-09-03** : le deal se résout après sa propre maturité.

**Deux cas ne sont pas touchés**, ce qui explique que ça ait échappé jusqu'ici :
un script en `AT OBSERVATIONS.last:` (l'autre construction courante, celle des
deals déjà bookés par Philippe) n'a pas d'`AT_MATURITY` du tout ; et un deal
booké depuis une RFQ dont le ténor a été dérivé du calendrier (T=2.9897) tombe
juste.

**Honnêteté sur l'origine :** c'est un défaut du correctif appliqué cet
après-midi. Avant, l'échéancier venait de la table de flux, qui produisait le
même événement fantôme **plus** un décalage de 3 jours sur toutes les autres
dates — le nouveau code est meilleur, il n'est pas juste.

**Piste :** ancrer `AT_MATURITY` sur la fin de calendrier quand le script en a
une, plutôt que sur le T du formulaire — ou faire dériver T de la fin de
calendrier au booking, comme la RFQ le fait déjà depuis ce matin.

### Correctif appliqué

Ni l'un ni l'autre : **l'horizon est la maturité que le deal lui-même déclare**
(`_derive_observation_times` lit `body.maturity_date`, plus `body.T`). Ancrer
sur la fin de calendrier aurait été faux dans l'autre sens — 2 ans de coupons
sur une note à 3 ans est un produit parfaitement normal, et c'est la note qui
dit quand elle rembourse. Les trois constructions donnent maintenant le même
échéancier de 4 lignes finissant au 2029-08-30, et le dernier event coïncide
avec `deal.maturity_date` (écart mesuré : 0 jour).

**Résiduel assumé, à trancher séparément :** la *fair value* a pu être calculée
sur un horizon de 3,00 ans alors que le produit rembourse à 2,99 — 4 jours
d'actualisation en trop. Le fermer suppose de faire dériver le T du **Pricer**
du calendrier, ce qui déplacerait tous les prix : c'est un arbitrage qui
revient à Philippe, pas un correctif à glisser. Le chemin RFQ, lui, dérive
déjà son ténor depuis ce matin et n'a pas ce résiduel.

---

## 2. MAJEUR — La piste de best execution reste réécrivable après le trade — ✅ CORRIGÉ

**Où :** `rfq.py:update_rfq`, `update_quote`, `delete_quote`

Sur une RFQ **déjà bookée**, cinq mutations sont acceptées sans réserve. Toutes
testées, toutes passantes :

| Mutation | Effet observé |
|---|---|
| Désélectionner la cotation gagnante | `won` retombe à `False` **pour tout le monde** — le hit ratio perd son gagnant, la RFQ reste « Bookée » |
| Supprimer la cotation gagnante | Elle disparaît de `/history` ; plus aucun gagnant sur cet AO |
| Changer son prix (98,0 → 1,0) | Accepté ; l'écran Analyse affiche désormais un fournisseur qui aurait coté 1,0 |
| Changer le sens de l'AO | Tous les `edge_bps` s'inversent (+200 → −200) sans qu'aucun prix ne bouge |
| Reclasser « sans suite » | Accepté — un AO qui a produit un trade est classé comme n'ayant pas abouti |

Le `rfq_provenance_json` figé sur le deal survit à tout ça (vérifié : il tient
toujours « UBS 98,0 » après que la cotation a été passée à 1,0) — c'est
exactement ce pour quoi il a été introduit. **Mais l'écran Analyse Contreparties
lit la RFQ vivante, pas la provenance.** La statistique qui sert à décider qui
mettre en concurrence demain est donc modifiable après coup, sans trace.

**Piste :** geler les mutations structurantes (sélection, prix des cotations,
sens) dès que la RFQ est `clos`, ou faire lire `/history` sur la provenance
figée pour les AO bookés.

### Correctif appliqué

`rfq.py:_refuse_if_booked` — **409** sur toute mutation portant la preuve dès
que la RFQ est `clos`, en nommant le deal concerné : réponse retenue, prix ou
statut d'une cotation, ajout ou suppression d'une cotation, sens de l'AO, prix
modèle, statut de la RFQ. Les sept mutations testées plus haut sont refusées.

**Ce qui reste modifiable, volontairement :** le nom de l'AO et les **notes**
sur les cotations. Une note documente (« confirmé par téléphone à 14h20 »),
elle ne fait pas preuve — la geler empêcherait de compléter un dossier sans
rien protéger.

`sans_suite` n'est pas gelé : un AO classé sans suite peut légitimement être
rouvert (`"auto"`), c'est une décision réversible. Seul `clos` — un trade a eu
lieu — est irréversible.

---

## 3. MAJEUR — Un calendrier incohérent produit un deal sans cycle de vie, en silence — ✅ CORRIGÉ

**Où :** `deals.py:_derive_observation_times` (le `except` de repli), `schedule.py:generate_schedule`

Calendrier dont la date de fin précède la date de début : `generate_schedule`
lève, la dérivation retombe sur la liste envoyée par le client — vide si aucun
pricing n'a été lancé. Résultat observé :

```
[(0.0, '2026-08-30')]      ← le strike, et rien d'autre
```

Le deal est booké **sans aucune constatation**. Ni surveillance de barrière, ni
MtM résiduel, ni résolution automatique, et aucun message. C'est la même famille
que le défaut trouvé ce matin sur `DEMO-20260730-002`, dont le correctif ne
couvre pas ce cas : il rend l'échéancier indépendant du pricing, il ne refuse
toujours pas un calendrier impossible.

**Piste :** refuser le booking quand le script déclare un CONSTAT et qu'aucun
échéancier n'a pu en être tiré. Un deal sans constatation n'est pas un deal.

### Correctif appliqué

**422** quand aucune constatation ne peut être établie, ni par le script ni par
la liste du client, avec **la cause exacte reprise dans le message** :

> Ce deal n'a aucune constatation — il ne pourrait être ni surveillé, ni
> valorisé, ni dénoué. Le calendrier du script est inexploitable :
> end_date doit être strictement après start_date.

Le contrôle est fait **avant** la création du deal, donc rien n'est écrit. Le
repli sur la liste du client reste ouvert quand elle existe (snapshot legacy,
valeurs de CONSTAT absentes) : mieux vaut un échéancier approché que pas
d'échéancier.

---

## 4. MOYEN — Aucune validation économique côté serveur au booking — ✅ CORRIGÉ

**Où :** `deals.py:book_deal`, `schemas.py:DealCreate`

Tout ce qui suit est **accepté** et persisté :

| Saisie | Résultat |
|---|---|
| Nominal `0` | Deal booké à 0 |
| Nominal `−5 000 000` | Deal booké en négatif |
| Fair value `0` | Deal booké, base de P&L à zéro |
| Date de valeur **avant** la date de strike | Accepté |
| Maturité au **2020-01-01** (passée, avant la value date) | Accepté |
| Contrepartie vide | Accepté |
| Contrepartie hors catalogue | Accepté |

Le formulaire bloque une partie (contrepartie, nominal, prix traité, fair
value) — mais l'API est la vraie frontière, et elle ne bloque rien. Un nominal
négatif entre ensuite dans l'agrégation de risque et dans l'exposition par
contrepartie (`portfolios.py`), où il **réduit** l'exposition mesurée.

### Correctif appliqué

`deals.py:_validate_economics`, appelé **avant** toute écriture. Refusé en 422,
avec le détail de ce qui cloche : contrepartie vide, nominal nul ou négatif,
fair value nulle ou négative, prix traité nul ou négatif, date de valeur
antérieure au strike, maturité non postérieure à la date de valeur, règlement
antérieur à la maturité.

**Laissé passer volontairement :** une contrepartie hors catalogue (le champ est
une chaîne libre par conception — l'historique doit rester lisible après un
renommage) et un strike loin dans le passé (booker un trade après coup est
légitime).

---

## 5. MOYEN — Cotations sans garde-fou — ✅ CORRIGÉ

**Où :** `rfq.py:update_quote`, `add_quote`

Acceptés sans réserve : prix **négatif** (−50), prix **nul**, prix **10 000 %**,
et un **même fournisseur inscrit deux fois** sur le même AO. Ce dernier point
est le plus gênant : la banque pèse alors double dans la moyenne des écarts, et
le mécanisme de last look — dont toute la logique de remplacement repose sur
« une ligne = une réponse d'un fournisseur » — devient ambigu.

Un prix nul fait par ailleurs passer la RFQ en « Cotée » : le statut dérivé
compte une cotation qui n'en est pas une.

### Correctif appliqué

`_validate_quote_price` : **422** sur un prix nul ou négatif (« pour un
fournisseur qui ne répond pas, laissez le prix vide et passez son statut à
Décliné ») et au-delà de **1000 % du nominal** — la borne haute n'est pas une
limite de marché, c'est un filet à faute de frappe (9850 saisi pour 98,50, ou
un montant en devise dans un champ en pourcentage).

`add_quote` refuse en **409** un fournisseur déjà sollicité sur le même AO, en
renvoyant vers la ligne existante ou vers le last look. La contre-cote de last
look, elle, continue de créer sa seconde ligne du même fournisseur — elle ne
passe pas par là.

---

## 6. MOYEN — Un last look qui dégrade le prix efface la meilleure cotation — ✅ CORRIGÉ

**Où :** `rfq.py:superseded_quote_ids`, `update_quote`

Le last look, c'est « le fournisseur voit le marché et s'aligne, ou garde son
prix ». Une contre-cote **pire** que la cotation initiale n'a pas de sens métier.
Elle est pourtant acceptée, et elle **remplace** l'originale. Testé sur un AO
d'achat, prix modèle 98,0 :

```
UBS  prix=97.0  edge=+102.0 bps  remplacée=True    ← la bonne cotation, écartée
UBS  prix=99.0  edge=-102.0 bps  remplacée=False   ← la contre-cote, retenue
statistique du fournisseur : [-102.0]
```

UBS avait coté 102 bps en notre faveur ; l'analyse retiendra 102 bps contre
nous. Le mécanisme introduit ce matin pour empêcher un fournisseur de compter
deux fois retient systématiquement la contre-cote, sans vérifier qu'elle
améliore quoi que ce soit.

**Piste :** refuser (ou signaler) une contre-cote défavorable au sens de l'AO,
et conserver la meilleure des deux comme réponse finale.

### Correctif appliqué

**422** sur une contre-cote qui n'améliore pas, lue dans le sens de l'AO (plus
bas si on achète, plus haut si on vend) — s'aligner exactement reste permis,
c'est littéralement « garder son prix ». Message explicite : si le fournisseur
revient moins bien, sa cotation initiale reste sa réponse, il faut annuler le
last look.

C'est l'interprétation stricte de la convention : un last look, c'est
« s'aligner ou garder son prix ». Un fournisseur qui revient plus cher parce que
le marché a bougé, ce n'est pas un last look, c'est un nouvel AO.

---

## 7. MOYEN — `sens` et `kind` ne sont pas validés — ✅ CORRIGÉ

**Où :** `rfq.py:RfqCreate`, `models.py:RfqRequest`

`sens="lateral"` et `kind="n_importe_quoi"` sont acceptés et persistés. Or
`_edge_bps` teste `sens == "achat"` et retombe **sinon** sur la branche vente :
un sens invalide inverse donc silencieusement la lecture de tous les écarts, la
meilleure réponse et la coloration de l'écran. Un `kind` invalide contourne au
passage le contrôle « to trade exige un calendrier CONSTAT ».

### Correctif appliqué

Motif Pydantic sur `RfqCreate.sens` / `.kind` et `RfqUpdate.sens` —
`^(achat|vente)$` et `^(indicatif|to_trade)$`. La validation est refusée à
l'entrée, avant que quoi que ce soit ne touche la base.

---

## 8. MOYEN — Le rapprochement fournisseur → contrepartie casse sans alerte — ✅ CORRIGÉ

**Où :** `rfq.py:_counterparty_by_provider`

Le rapprochement par nom identique, qui couvre le cas courant sans rien
configurer, se rompt dès qu'on touche au catalogue — testé :

| Action | Effet |
|---|---|
| Renommer « BNP Paribas » en « BNP Paribas SA » | Le fournisseur « BNP Paribas » ne résout plus |
| Désactiver la contrepartie « UBS » | Le fournisseur « UBS » ne résout plus |

Le booking laisse alors le champ vide en signalant le fournisseur — le
comportement de repli fonctionne. Mais rien n'avertit l'administrateur qu'un
renommage vient de rompre un rapprochement, et le desk le découvre au moment de
booker.

### Correctif appliqué

**Le renommage ne casse plus rien** : `admin.py:update_counterparty` rattache
par id, avant que le nom ne change, les fournisseurs RFQ qui tenaient par ce
nom. Le lien devient explicite au moment exact où le rapprochement par nom
allait être perdu.

**La désactivation reste exclue** — c'est le comportement voulu : désactiver
une contrepartie, c'est la rendre inéligible, et le formulaire de booking ne
propose que les actives. Ce qui manquait, c'est la visibilité : l'écran
Administration → Fournisseurs RFQ affiche désormais, sur chaque fournisseur
sans rapprochement, « ⚠ aucune contrepartie — le booking laissera le champ
vide ».

---

## 9. MOYEN — Prix modèle négatif accepté — ✅ CORRIGÉ

`model_price = −5,0` est persisté ; les `edge_bps` se calculent dessus. Un
`model_price = 0` exclut en revanche proprement les cotations de l'analyse
(`edge_bps = None`), et l'écran affiche déjà le nombre de cotations écartées —
ce cas-là est correctement traité.

### Correctif appliqué

**422** sur un prix modèle strictement négatif. Zéro reste accepté : il est
déjà traité proprement en aval, et c'est une valeur qu'un moteur peut
légitimement renvoyer sur un produit très hors de la monnaie.

---

## 10. Mineurs

| Constat | Détail |
|---|---|
| Nom d'AO vide accepté côté serveur | Seul le formulaire l'interdit |
| Script vide ou non compilable accepté à la création | On obtient une RFQ qu'on ne pourra jamais pricer |
| Détection « mode Expert » = présence de la chaîne `CONSTAT` | Le mot dans un commentaire suffit à passer le contrôle « to trade » |
| Devise de cotation libre (« XYZ » accepté) et jamais affichée | Colonne morte, déjà relevée le 29/07 |
| Références numérotées globalement, pas par utilisateur | Deux desks le même jour → RFQ-…-001 puis RFQ-…-003 pour le premier, série trouée |
| « Convertir en RFQ to trade » crée une RFQ neuve sans lien | L'historique concurrentiel est coupé en deux, l'indicatif reste « Cotée » à vie |
| Ajouter une cotation après booking | Accepté ; sans effet sur le deal, mais pollue l'analyse |

---

## Ce qui tient

Vérifié explicitement, tout passe :

- les garde-fous ajoutés aujourd'hui — **422** sans réponse retenue, **409** au
  double booking (en nommant le deal existant), **409** à la suppression d'une
  RFQ bookée, **404** sur toute RFQ d'un autre utilisateur ;
- l'échéancier dérivé du script sans dépendre d'un pricing préalable ;
- la **provenance figée** sur le deal, qui résiste à toutes les mutations
  d'après-trade testées — c'est aujourd'hui la seule pièce fiable du dossier de
  best execution ;
- le rapprochement fournisseur → contrepartie (lien explicite et nom identique),
  et le refus de proposer une contrepartie inactive ;
- la reproductibilité du prix de bout en bout : prix modèle RFQ → fair value
  bookée → repricing du deal rouvert donnent **97,97 %** au même centième.

---

## État au 2026-07-30, fin de journée

**Les 9 constats sont corrigés** — 3 majeurs et 6 moyens, chacun avec son
encadré « Correctif appliqué ». 33 tests de non-régression ajoutés dans
`backend/tests/test_rfq.py` § 15 et § 16, dont trois cas paramétrés (les sept
mutations d'après-trade, les sept saisies économiques refusées, les trois prix
de cotation aberrants). Suite complète : **308/308**.

Trois tests antérieurs ont dû être réécrits : ils exerçaient précisément les
mutations désormais refusées. Celui qui prouvait l'immutabilité de la
provenance passe maintenant par une écriture directe en base — la démonstration
en sort renforcée : la provenance tient même si un futur chemin d'écriture
contournait le garde-fou de l'API.

**Reste ouvert :**

- les **mineurs du § 10** — nom d'AO vide côté serveur, script vide ou non
  compilable accepté à la création, détection « mode Expert » par simple
  présence de la chaîne `CONSTAT`, devise de cotation morte, numérotation des
  références globale et non par utilisateur, conversion indicatif → to trade
  sans lien avec l'AO d'origine, cotation ajoutable après booking ;
- le **résiduel de pricing du constat 1** : le ténor du **Pricer** ne dérive
  pas du calendrier, donc la fair value d'un deal booké hors RFQ peut porter
  quelques jours d'actualisation en trop. C'est un arbitrage de pricing —
  le fermer déplacerait tous les prix de l'écran — pas un défaut à corriger
  d'office.
