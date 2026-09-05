# Audit de la chaîne RFQ → Booking → MtM → Greeks → Portefeuille → Risk

**Date** : 7 août 2026
**Révision** : `0ed2067` (« Structura »), branche `feat/client-test-agent`, **worktree non
propre** — 8 fichiers backend et 9 fichiers frontend modifiés non commités (dont
`deals.py`, `lifecycle_controls.py`, `uat_generation.py`, `BookingView.vue`).
**Périmètre** : le flux d'exécution de bout en bout, ses identifiants, ses statuts, ses
conventions d'unités, sa piste d'audit, son cloisonnement et son coût. AMC/INDEX_STUDIO,
FIFO, KID/PRIIPs et la méthodologie VaR restent hors périmètre.
**Mode opératoire** : lecture seule. Aucun fichier du dépôt modifié hors ce rapport,
aucun serveur lancé, `structura.db` jamais ouvert. Les constats reposent sur **10 sondes
exécutables** écrites dans le scratchpad (SQLite en mémoire, handlers appelés
directement, Yahoo monkeypatché) et sur 23 tests ciblés existants rejoués.

**Relation aux audits antérieurs.** Ce document ne réécrit ni
`AUDIT_COMPLET_2026-08-02.md` (moteur, modèles, cloisonnement) ni
`AUDIT_CHAINE_RFQ_2026-07-30.md` (amont RFQ). Il ouvre le volet que ni l'un ni l'autre
n'a couvert : **l'aval du booking** — ce qui se passe entre le deal en base et le chiffre
de risque à l'écran. Trois bloquants du 2 août sont vérifiés **fermés** au passage : le
secret JWT (désormais variable d'environnement, fichier généré, refus de la valeur
publiée — `auth.py:31-80`), le FX à parité (`fx_rate_to` renvoie `None` et les appelants
excluent et nomment la position), et le *backward fill* (`market_data.py:130-149`,
`frame.dropna()` après `ffill`).

---

## 1. Synthèse exécutive

### État général

**L'amont est solide, l'aval ne l'est pas encore.** Le chemin RFQ → sélection → booking
est le mieux tenu de l'application : les termes contractuels sont figés dès la première
sollicitation, la piste de best-ex est gelée sur le deal, le gate de booking impose huit
contrôles indépendants (cotation ferme, validité non expirée, prix modèle frais de moins
de 60 minutes, hash d'inputs, contrepartie résolue, identité produit terme à terme), et
tout refus est audité avant d'être renvoyé. Le cycle de vie est gouverné avec la même
rigueur : l'indicatif propose, seul l'officiel valide, les transitions passent par des
`UPDATE ... WHERE status = ...` (compare-and-swap) qui rendent l'application idempotente.

**Le maillon faible est la couche d'agrégation.** Elle est arithmétiquement correcte mais
repose sur des entrées hétérogènes qu'elle ne contrôle pas, exclut des positions qui
portent encore du risque, inclut des positions qui n'en portent aucun, et ne restitue
aucune valorisation de book. Trois hypothèses structurantes ne sont vraies nulle part
ailleurs dans l'application :

- les Greeks agrégés sont sommés **quelle que soit la date et le marché de leur calcul** ;
- l'exposition contrepartie s'arrête au statut `actif`, donc **au dénouement économique
  et non au règlement** ;
- aucun filtre ne sépare les données de test générées par l'administration des positions
  réelles.

### Principaux risques

| # | Risque | Sévérité |
|---|---|---:|
| 1 | Un `r = 0 %` figé au booking est valorisé à **3 %** — silencieusement, sur 5 chemins de code dont le replay **officiel** du lifecycle | P1 |
| 2 | Les deals **UAT** générés par l'administration entrent dans l'exposition contrepartie, le HHI et les contrôles de limite du book réel | P1 |
| 3 | Entre maturité et règlement, la créance sur l'émetteur **n'est ni valorisée ni comptée** | P1 |
| 4 | Le **Mode Démo ne masque rien** sur Booking, RFQ, Events et Risk Management | P1 |
| 5 | Le job quotidien **n'a aucune reprise** : un redémarrage après 23 h saute la journée sans trace | P1 |
| 6 | Un deal booké en `FOUR_EYES` est **définitivement irrésoluble** sur une installation mono-compte | P1 |

### Verdict sur la fiabilité Front-to-Risk

| Usage | Verdict | Motif déterminant |
|---|---|---|
| RFQ → sélection → booking | **GO** | Gate à 8 contrôles, termes figés, provenance gelée, refus audités |
| MtM résiduel d'un deal actif | **GO sous contrôle** | Correct et reproductible, sauf `r = 0` ; aucune valorisation hors statut `actif` |
| Greeks d'un deal | **GO sous contrôle** | Stateful, CRN, conventions documentées ; aucun intervalle de confiance publié |
| **Agrégation Greeks du book** | **NO-GO** | Somme de sensibilités calculées à des dates et sous des marchés différents |
| **Exposition et limites contrepartie** | **NO-GO** | Deals UAT inclus, deals échus non réglés exclus |
| Chocs de marché (spot/vol/taux/corr) | **GO sous contrôle** | Reprice complet avec état hérité, correct ; ni FX ni dividende choquables |
| **Valorisation du portefeuille (MtM, P&L latent)** | **ABSENT** | Aucun endpoint ne l'expose |
| **Confidentialité en démonstration** | **NO-GO** | Le badge est affiché, les données ne sont pas masquées |
| Exploitation quotidienne non surveillée | **NO-GO** | Scheduler sans reprise ni journal exploitable |

### Notation

| Domaine | Note /10 | Appréciation |
|---|---:|---|
| Workflow RFQ et sélection | 8,5 | Le point fort de l'application ; contrôles centralisés et testés |
| Intégrité du booking | 8,0 | Immuable, tracé, calendrier dérivé du contrat et non d'un pricing |
| Gouvernance du cycle de vie | 8,0 | Maker/checker, CAS, hash d'inputs, replay officiel séparé de l'indicatif |
| MtM résiduel | 6,5 | Machinerie juste ; trous de couverture aux bornes (mature, échu, callé) |
| Greeks (deal) | 6,5 | Conventions documentées ; pas d'IC, corrélation en différence avant |
| **Agrégation portefeuille** | **4,0** | Arithmétique correcte sur des entrées non homogènes ; périmètre d'inclusion faux |
| **Risk Management** | **4,5** | Chocs justes mais incomplets ; pas de FX, pas de dividende, pas de MtM book |
| Identifiants et jointures | 7,5 | Contraintes d'unicité en place, provenance gelée, pas d'orphelin détecté |
| Piste d'audit | 6,5 | Append-only et riche sur le lifecycle ; trous sur suppressions et rattachements |
| **Confidentialité / Mode Démo** | **2,0** | Couvre le Pricer et l'AMC, aucun écran de la chaîne Front-to-Risk |
| Performance sur book réaliste | 4,0 | Un fetch Yahoo + N Monte Carlo par deal, séquentiel, endpoint bloquant |
| Couverture de tests de la chaîne | 4,5 | 600 tests, mais **aucun** de bout en bout, et 3 sur l'agrégation portefeuille |
| **Global Front-to-Risk** | **5,8** | **Amont fiable, aval à consolider avant tout usage de pilotage** |

---

## 2. Cartographie du workflow

### 2.1 Chaîne nominale

```
┌─ RFQ ────────────────────────────────────────────────────────────────────┐
│ RfqView.vue ──▶ POST /api/rfq                      api/rfq.py:_create_rfq │
│   • kind=to_trade impose un calendrier CONSTAT réel (_is_expert_script)   │
│   • réf. RFQ-AAAAMMJJ-nnn allouée par core/references.py (max, pas count) │
│ POST /api/rfq/{id}/quotes         ── une ligne par fournisseur, casefold  │
│ PATCH .../quotes/{qid}            ── prix, firmness, valid_until, last    │
│                                      look (enfant lié, doit améliorer)    │
│ PATCH /api/rfq/{id}               ── selected_quote_id ⇒ statut "retenue" │
│   statut DÉRIVÉ des faits (_derive_status), jamais posé par l'appelant    │
└──────────────────────────────────────────────────────────────────────────┘
                                    │  rfq_id
                                    ▼
┌─ BOOKING ────────────────────────────────────────────────────────────────┐
│ DealTab.vue ──▶ POST /api/deals                    api/deals.py:_book_deal │
│   1. _validate_economics          nominal>0, FV≠0, dates ordonnées, ISO   │
│   2. booking_gate_failures        core/rfq_controls.py — 8 contrôles      │
│   3. _validate_rfq_booking_identity  sens inversé, cpty, termes ≡ figés   │
│   4. _derive_observation_times    calendrier CONSTAT résolu sur value_date│
│   5. _rfq_provenance              piste de best-ex GELÉE (JSON sur Deal)  │
│   ⇒ Deal + DealEvent[0..n] + AuditEvent(BOOKING_ACCEPTED)                 │
│   ⇒ RfqRequest.status = "clos" ; portfolio_id = portefeuille par défaut   │
└──────────────────────────────────────────────────────────────────────────┘
                                    │  deal.id
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌─ LIFECYCLE ─────────┐   ┌─ MtM ──────────────┐   ┌─ SURVEILLANCE ────────┐
│ scheduler 23h /     │   │ POST /{id}/mtm     │   │ GET /api/deals/       │
│ POST /alerts/       │   │  _mtm_core :       │   │       watchlist       │
│      refresh-book   │   │  replay passé      │   │ build_watchlist_row   │
│ ↳ AUTO_YAHOO :      │   │  + MC résiduel     │   │ ↳ barrières M_ ou     │
│   fixing auto +     │   │  + état hérité     │   │   heuristique de nom  │
│   application       │   │ (MTM_RESIDUEL_     │   │ ↳ 1 fetch Yahoo/deal  │
│ ↳ FOUR_EYES :       │   │  DESIGN.md)        │   └───────────┬───────────┘
│   proposition seule │   └─────────┬──────────┘               │
│ ↳ LifecycleProposal │             │ ctx                      │
│   PROPOSED→VALIDATED│             ▼                          │
│   →APPLIED (CAS)    │   ┌─ GREEKS ───────────┐               │
└─────────┬───────────┘   │ POST /{id}/greeks  │               │
          │               │ compute_greeks CRN │               │
          │               │ ⇒ Deal.greeks_json │               │
          │               │   (écrasé, sans    │               │
          │               │    historique)     │               │
          │               └─────────┬──────────┘               │
          ▼                         ▼                          ▼
┌─ PORTEFEUILLE / RISK ────────────────────────────────────────────────────┐
│ RiskManagementView.vue + stores/portfolios.js                            │
│  GET  /api/portfolios/risk-global | /{id}/risk    _aggregate_risk         │
│       ↳ Σ greeks_json × sign × nominal × FX      (arithmétique pure)      │
│  GET  /api/portfolios/exposure-by-counterparty   nominal EUR, HHI, limite │
│  GET  /api/portfolios/barriers-global            build_watchlist_row × N  │
│  POST /api/portfolios/{shock|shock-global}       _mtm_core + run_mc × N   │
│  POST /api/portfolios/pnl-explain-global         _explain_core × N        │
│  POST /api/portfolios/var-global                 ComputeBatch asynchrone  │
│  ⚠ filtre unique partout : user_id == moi ET status == "actif"            │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Tables et dépendances

| Table | Rôle dans la chaîne | Clés entrantes |
|---|---|---|
| `rfq_requests` | AO, script figé, prix modèle + hash d'inputs | `script_id`, `selected_quote_id` |
| `rfq_quotes` | une ligne par fournisseur ; `parent_quote_id` = last look | `rfq_id` |
| `deals` | contrat booké, snapshots script/marché, provenance gelée | `rfq_id` **UNIQUE**, `indicative_id`, `portfolio_id`, `script_id`, `uat_batch_id` |
| `deal_events` | calendrier contractuel + fixings | `deal_id`, `current_fixing_version_id` |
| `official_fixing_versions` | preuves immuables (SHA-256, pièce jointe) | `deal_id`, `deal_event_id` |
| `lifecycle_proposals` | résultat proposé → validé → appliqué | `deal_id`, `event_id`, `dedup_key` UNIQUE |
| `portfolios` | bucket d'agrégation, un défaut non supprimable par user | `user_id` |
| `shock_runs` | historique append-only des scénarios | `deal_id` \| `portfolio_id` |
| `audit_events` | piste métier append-only | `object_type` + `object_id` (pas de FK) |
| `alerts` | alertes lifecycle/barrière, `dedup_key` à vie | `deal_id` |

**Aucun objet orphelin détecté** : `delete_rfq` refuse si un deal pointe dessus,
`delete_portfolio` réaffecte au défaut, `admin_registry` bloque la suppression d'un deal
porteur de KID/EMT, et `deals` n'a **aucun** `editable_fields` (correction admin
impossible par construction).

---

## 3. Constats classés par sévérité

> **P0** — aucun constat de niveau P0 n'a été établi. Aucun chemin conduisant à une
> perte de données, à un double booking ou à une double application d'un événement
> économique n'a résisté aux sondes : les contraintes d'unicité (`Deal.rfq_id`,
> `LifecycleProposal.dedup_key`, `DealContractVersion.dedup_key`) et les
> compare-and-swap du lifecycle tiennent.

---

### P1-01 — Un taux figé à 0 % est valorisé à 3 %

| | |
|---|---|
| **Sévérité** | P1 — défaut confirmé |
| **Domaine** | MtM, Greeks, chocs, P&L explain, replay officiel du lifecycle |

**Preuve.** Le motif `(market.get("r", 3.0) or 3.0) / 100.0` apparaît à cinq endroits :
[deals.py:3015](backend/app/api/deals.py:3015) (`_evaluate_lifecycle`),
[deals.py:5351](backend/app/api/deals.py:5351) et
[deals.py:5459](backend/app/api/deals.py:5459) (réinvestissement),
[deals.py:5750](backend/app/api/deals.py:5750) (`_mtm_core`) et
[lifecycle_controls.py:178](backend/app/core/lifecycle_controls.py:178)
(`replay_official_fixings`). En Python, `0 or 3.0` vaut `3.0` : la valeur zéro, qui est
une donnée parfaitement légitime, est indistinguable de l'absence de donnée.

Sonde 1 (zéro-coupon `AT MATURITY / PAY 1`, série de prix plate, T résiduel 0,9993 an) :

```
MtM deal booké à r = 0 %  : 0.970446   (attendu : 1.000000)
MtM deal booké à r = 3 %  : 0.970446   (attendu : 0.970466)
market_used.r du deal r=0 : 3.0 %
```

**Reproduction.** Booker un deal dont le snapshot marché porte `r: 0`, puis
`POST /api/deals/{id}/mtm`. Le champ `market_used.r` de la réponse renvoie `3.0`.

**Impact métier.** Environ **3 points de nominal par année de maturité résiduelle**
d'erreur de valorisation, dans le sens défavorable au porteur. Sur un 5 ans : ~14 points.
L'erreur se propage à tous les Greeks (le rho est calculé autour du mauvais point), à
tous les chocs de taux (le choc s'ajoute à 3 % au lieu de 0 %) et au P&L explain. Le plus
grave est le cinquième site : `replay_official_fixings` est le calcul **officiel** qui
détermine le `realized_payout` inscrit en base à la résolution du deal.

**Cause racine probable.** Un idiome de valeur par défaut écrit pour couvrir `None`, qui
capture aussi `0`. Le `get(clé, défaut)` était déjà correct — le `or` est redondant et
nuisible.

**Correction recommandée.** Remplacer les cinq occurrences par une lecture explicite :
`raw = market.get("r"); r_frac = (3.0 if raw is None else float(raw)) / 100.0`.
Mieux : centraliser dans un helper `market_rate(market)` et interdire le motif par un test
de garde-fou statique (le dépôt en possède déjà un pour la référence de langage PayScript).

**Tests nécessaires.** Un test par site : deal à `r = 0` → `market_used.r == 0.0` et
`mtm ≈ 1.0` sur un ZC ; deal à `r = -0.5` (taux négatif, aujourd'hui correct) → non
régressé ; deal sans clé `r` → 3,0 conservé.

**Risque de régression.** Faible et borné. Le seul comportement qui change est celui des
snapshots portant exactement `0`. À vérifier : aucun deal existant ne s'appuie sur
l'ancien comportement (requête `SELECT reference FROM deals WHERE json_extract(
market_snapshot_json,'$.r') = 0`).

---

### P1-02 — Les deals UAT entrent dans le risque et les limites du book réel

| | |
|---|---|
| **Sévérité** | P1 — défaut confirmé |
| **Domaine** | Portefeuille, Risk Management, contrôle de limite contrepartie |

**Preuve.** `Deal.uat_batch_id` marque explicitement les données synthétiques
([models.py:157](backend/app/db/models.py:157)) et les références portent un préfixe
`UAT-DEAL-…` ([uat_generation.py:814](backend/app/services/uat_generation.py:814)). Mais
`grep -rn "uat_batch_id" backend/app/api/` ne renvoie **que les deux sites d'écriture** :
aucune lecture, donc aucun filtre. Tous les agrégats filtrent uniquement sur
`Deal.user_id == current.id, Deal.status == "actif"`
([portfolios.py:294](backend/app/api/portfolios.py:294),
[portfolios.py:656](backend/app/api/portfolios.py:656),
[portfolios.py:621](backend/app/api/portfolios.py:621),
[shocks.py:263](backend/app/api/shocks.py:263)).

Sonde 2 (1 deal réel 1 M€ face à BNP, 1 deal UAT 50 M€ face à « UAT Bank ») :

```
Nominal total exposé  : 51 000 000 EUR
Contreparties listées : ['UAT Bank', 'BNP']
Nominal risk-global   : 51 000 000 EUR
```

**Reproduction.** Administration → Générateur UAT, cibler son propre compte, mode
`BOOKED_ONLY`. Ouvrir Risk Management → Contreparties.

**Impact métier.** Le HHI, le top-3, le `pct_of_book` et surtout le drapeau
`limit_breached` sont calculés sur une population contaminée. Deux erreurs symétriques :
une limite peut être déclarée franchie par du faux nominal, et une limite réellement
franchie peut être diluée sous son seuil relatif. Sur l'onglet Greeks, un lot UAT de
grande taille écrase visuellement les contributions réelles. Rien à l'écran ne distingue
un deal UAT d'un deal réel : ni couleur, ni badge, ni colonne.

**Cause racine probable.** Le champ a été ajouté comme **frontière de suppression** (« le
seul périmètre qu'une purge peut balayer », cf. la docstring de `UatGenerationBatch`) et
non comme frontière de lecture. Le besoin d'exclusion en aval n'a jamais été formulé.

**Correction recommandée.** Trois niveaux, à trancher (cf. §7, question 2) :
1. *a minima* — exposer `uat_batch_id` dans `_deal_row` et le rendre visible à l'écran
   (badge « UAT ») ;
2. *recommandé* — exclure par défaut des six agrégats, avec un paramètre
   `include_uat: bool = False` et un compteur `deals_uat_excluded` dans la réponse, sur
   le même modèle que `deals_missing_fx` déjà en place ;
3. *le plus sûr* — cibler par défaut un utilisateur technique dédié dans le générateur.

**Tests nécessaires.** `test_portfolio_uat_isolation.py` : un deal réel + un deal UAT →
`exposure-by-counterparty` ne renvoie que le réel ; `include_uat=True` renvoie les deux ;
`risk-global`, `barriers-global`, `shock-global` et `pnl-explain-global` suivent la même
règle.

**Risque de régression.** Moyen sur les habitudes de recette : si des lots UAT sont
aujourd'hui utilisés pour peupler les écrans en démonstration, l'exclusion par défaut les
fera disparaître. D'où la question de §7.

---

### P1-03 — Aucune valorisation ni exposition entre maturité et règlement

| | |
|---|---|
| **Sévérité** | P1 — défaut confirmé (fonctionnel + risque) |
| **Domaine** | MtM, exposition contrepartie, statuts |

**Preuve.** `_mtm_core` refuse trois états sur quatre
([deals.py:5705](backend/app/api/deals.py:5705) et
[deals.py:5712](backend/app/api/deals.py:5712)). Sonde 3 :

```
mature non résolu (actif, maturité J-10) → 422 « Échéance atteinte — lancer le refresh »
échu (statut échu, règlement J+3)        → 422 « Deal échu — plus d'optionnalité »
callé (statut callé)                     → 422 « Deal callé — plus d'optionnalité »
```

Et sonde 4 (1 deal actif BNP 1 M€, 1 deal échu SG 9 M€ dont le règlement est à J+4) :

```
Exposition retournée : [('BNP', 1 000 000)]
HHI                  : 1.0
```

**Reproduction.** Résoudre un deal dont la `payment_date` est postérieure à la
`maturity_date` (le cas nominal : `_validate_economics` autorise explicitement
`payment_date >= maturity_date`). Consulter Risk Management → Contreparties.

**Impact métier.** Deux problèmes distincts.
*Économiquement* : un produit dont l'optionnalité est éteinte a toujours une valeur — le
montant de remboursement, actualisé jusqu'au règlement. Le refuser est défendable
(l'optionnalité a disparu), mais ne rien afficher du tout ne l'est pas : le book perd la
position de son bilan entre les deux dates.
*En risque de contrepartie* : c'est exactement la période où l'exposition émetteur est
**maximale et non couverte** — la créance est certaine, le cash n'est pas arrivé. Elle
sort de l'exposition, du HHI, du top-3 et du contrôle de limite. Un book qui déboucle
plusieurs positions le même mois voit sa concentration mesurée sur ce qu'il en reste.

**Cause racine probable.** `Deal.status` mélange deux axes orthogonaux : le **dénouement
économique** (actif / callé / échu) et le **cycle de règlement** (non réglé / réglé).
`payment_date` existe sur le deal mais n'est lue nulle part dans la chaîne de risque
(`grep -n "payment_date" backend/app/api/portfolios.py` : aucun résultat).

**Correction recommandée.** Ne pas ajouter de statut : dériver. Introduire un prédicat
`is_settled(deal, today) = deal.status != "actif" and deal.payment_date <= today` et
l'utiliser comme critère d'inclusion dans `_aggregate_exposure_by_counterparty` — le
nominal exposé devient « actif **ou** dénoué non réglé », avec une colonne « dont en
attente de règlement ». Pour le MtM, exposer une valeur résiduelle simple
`realized_payout × df(payment_date)` plutôt qu'un 422, sur un chemin séparé de
`_mtm_core` (aucun Monte Carlo nécessaire).

**Tests nécessaires.** Deal échu règlement futur → présent dans l'exposition ; deal échu
réglé → absent ; MtM d'un deal échu non réglé → `realized_payout` actualisé, pas de 422.

**Risque de régression.** Faible sur le MtM (chemin nouveau). Moyen sur l'exposition : le
nominal total change, donc tous les pourcentages, le HHI et les drapeaux de limite. À
annoncer explicitement à l'écran lors du déploiement.

---

### P1-04 — Le Mode Démo ne masque rien sur la chaîne Front-to-Risk

| | |
|---|---|
| **Sévérité** | P1 — défaut confirmé (confidentialité) |
| **Domaine** | Confidentialité, présentation |

**Preuve.** Recensement exhaustif des consommateurs du store
(`grep -rln "demoMode\|SensitiveValue" frontend/src`) : 22 fichiers, tous dans le
périmètre **Pricer / AMC**. Comptage ciblé sur les écrans de la chaîne :

| Écran | Occurrences `demoMode` / `SensitiveValue` |
|---|---:|
| `views/RiskManagementView.vue` | **0** |
| `views/BookingView.vue` | **0** |
| `views/RfqView.vue` | **0** |
| `components/EventsTab.vue` | **0** |
| `views/AdminCounterpartiesView.vue` | **0** |
| `views/AdminUatGeneratorView.vue` | **0** |
| `views/ReinvestView.vue` | **0** |

Le badge, lui, est bien global : `DemoModeToggle` est monté dans `AppHeader.vue:22`,
donc présent sur **toutes** les pages. Extraits de ce qui reste lisible en mode démo
actif : `RiskManagementView.vue:1123` affiche `d.contrepartie` et `d.nominal` en clair
dans la composition du portefeuille, `:147-149` les Greeks en euros par sous-jacent
nommé, l'onglet Contreparties le nom de chaque banque avec son nominal et sa limite.

**Reproduction.** Activer le Mode Démo, aller sur `/risk` ou `/booking`.

**Impact métier.** Le badge « DEMO MODE » constitue une **assurance fausse** : il indique
que les données sont masquées alors qu'elles ne le sont que sur les écrans de pricing. Un
partage d'écran ou une capture de l'onglet Contreparties expose les noms de contreparties,
les nominaux, les limites et le degré de concentration du book. C'est précisément
l'inverse de l'objectif de la fonctionnalité.

**Cause racine probable.** Le Mode Démo a été conçu pour le Pricer (démonstration produit)
et n'a pas suivi la construction ultérieure de Booking, RFQ et Risk Management. Il n'existe
aucun mécanisme structurel — pas de directive globale, pas de wrapper de layout — qui
force un nouvel écran à s'y conformer.

**Correction recommandée.** Deux temps.
*Court terme* — envelopper les valeurs sensibles des quatre écrans dans le composant
`SensitiveValue` existant (contrepartie, nominal, prix traité, fair value, Greeks en EUR,
limites) et appliquer `underlyingLabel()` aux noms de sous-jacents.
*Structurel* — inverser la charge de la preuve : une directive `v-sensitive` ou un
composant de cellule par défaut, plus un test de garde-fou qui échoue si un nouveau
`.vue` de la chaîne affiche `contrepartie`, `nominal` ou `_eur` hors wrapper.

**Tests nécessaires.** Test frontend (aujourd'hui inexistant, cf. §5) montant chaque vue
avec `demoMode.enabled = true` et assertant qu'aucun nom de contrepartie ni nominal brut
n'apparaît dans le DOM rendu.

**Risque de régression.** Faible fonctionnellement (couche présentation, jamais lue par le
pricing — c'est explicite dans la docstring du store). Réel en ergonomie : masquer les
contreparties rend l'écran Risk difficilement utilisable **en mode démo**, ce qui est
l'intention.

---

### P1-05 — Le job quotidien n'a aucune reprise après interruption

| | |
|---|---|
| **Sévérité** | P1 — défaut confirmé (exploitation) |
| **Domaine** | Lifecycle, exploitation |

**Preuve.** [main.py:65-76](backend/app/main.py:65) : boucle `asyncio` en processus,
`next_run = now.replace(hour=23…)`, `if next_run <= now: next_run += 1 jour`. Aucune
persistance d'un « dernier passage », aucun rattrapage, aucune alerte d'absence.
`run_scheduled_refresh` ne journalise qu'au niveau `INFO` sur le logger
`structura.lifecycle`, sans écriture en base (`lifecycle_alerts.py:119-131`).

**Reproduction.** Redémarrer le backend à 23 h 30. La passe du jour est perdue et rien ne
le signale ; le lendemain à 23 h, `refresh_book` repart sur l'état courant.

**Impact métier.** Le rattrapage fonctionne *économiquement* — `refresh_deal_core` rejoue
l'historique complet depuis le strike, donc un fixing manqué est retrouvé au passage
suivant. Ce qui est perdu, ce sont les **alertes** : `_alert_once` déduplique sur
`dedup_key`, mais une alerte jamais créée n'est jamais rattrapée si la condition a
disparu entre-temps (un franchissement de barrière transitoire, un rappel qui se dénoue
avant la passe suivante). Sur une installation où le backend est redémarré à chaque
modification — le mode de travail documenté dans `CLAUDE.md` —, la probabilité de sauter
une passe est loin d'être négligeable.

**Cause racine probable.** Choix assumé (« Safe as a plain in-process task »), correct sur
l'axe concurrence, incomplet sur l'axe durabilité.

**Correction recommandée.** Persister le dernier passage réussi (une ligne
`ReferenceCounter`-like, ou un `AuditEvent` `LIFECYCLE_DAILY_RUN`), et au démarrage : si
le dernier passage réussi date de plus de 24 h, déclencher un rattrapage immédiat. Ajouter
un indicateur « dernière passe : … » dans l'entête, à côté du compteur d'alertes.

**Tests nécessaires.** Simuler un dernier passage à J-2 → le démarrage déclenche une passe.
Dernier passage il y a 3 h → pas de passe. Deux démarrages consécutifs → une seule passe.

**Risque de régression.** Faible. Attention à ne pas déclencher le rattrapage pendant les
tests (`init_db()` est appelé au boot).

---

### P1-06 — Un deal booké en FOUR_EYES est irrésoluble sur une installation mono-compte

| | |
|---|---|
| **Sévérité** | P1 — défaut confirmé (blocage fonctionnel) |
| **Domaine** | Lifecycle, rôles |

**Preuve.** Le choix est offert au booking :
[DealTab.vue:81](frontend/src/components/DealTab.vue:81) — « Produit contrôlé —
validation à quatre yeux ». Résoudre un tel deal exige ensuite :

| Étape | Rôle exigé | Contrainte supplémentaire |
|---|---|---|
| Capture du fixing officiel | `ops_maker` | `deal.user_id != current.id` ([deals.py:2208](backend/app/api/deals.py:2208)) |
| Validation du fixing | `checker` | — ([deals.py:2470](backend/app/api/deals.py:2470)) |
| Validation de la proposition | `checker` | `deal.user_id != current.id` ([deals.py:4695](backend/app/api/deals.py:4695)) |
| Application | `checker` | — |

`_ops_deal` ([deals.py:749](backend/app/api/deals.py:749)) **n'accepte pas le rôle
`admin`** : `if getattr(current, "role", None) not in allowed_roles` → 403. Il exige de
surcroît `current.entity_id is not None and == entity du deal`, sinon **404 « Deal
introuvable »** sur son propre deal.

**Reproduction.** Booker en FOUR_EYES depuis le compte `admin` seed. Onglet Events →
soumettre un fixing officiel → 403 rôle. Créer un compte `ops_maker` : il faut qu'il ne
soit pas le propriétaire. Créer un `checker` : idem. Trois comptes minimum.

**Impact métier.** Sur l'installation de Philippe (un utilisateur réel), tout deal booké
en FOUR_EYES est **définitivement bloqué** : ni fixing officiel, ni proposition validée,
ni résolution, ni archivage. Il restera `actif` au-delà de sa maturité, donc exclu du MtM
(P1-03) mais inclus dans les agrégats de nominal. Le message d'erreur (« Votre rôle ne
permet pas cette action ») est correct mais ne dit pas ce qu'il faut faire.

**Cause racine probable.** La séparation des tâches a été conçue pour un desk réel. Le cas
mono-opérateur n'a pas de porte de sortie, et le rôle `admin` — qui est le
super-utilisateur partout ailleurs, y compris pour lire tous les deals — a été
volontairement exclu ici pour éviter qu'il ne contourne le quatre-yeux. Cohérent en
principe, ingérable en pratique sur une installation seule.

**Correction recommandée.** Une des deux, à trancher (§7, question 3) :
1. griser l'option FOUR_EYES à l'écran de booking tant qu'il n'existe pas, dans l'entité,
   au moins un `ops_maker` et un `checker` distincts du propriétaire — et le dire ;
2. ou introduire un basculement gouverné `FOUR_EYES → AUTO_YAHOO` via le workflow
   d'amendement existant (`fixing_policy` n'est pas dans la liste des champs amendables
   aujourd'hui), avec motif obligatoire et trace d'audit.

L'option 1 est la bonne première marche : elle empêche de créer le problème. L'option 2
est nécessaire pour les deals déjà dans cet état.

**Tests nécessaires.** Deal FOUR_EYES, entité sans `ops_maker` → l'API de booking refuse
(ou l'UI grise) ; parcours complet à trois comptes → résolution nominale ; propriétaire
== ops_maker → refus tracé.

**Risque de régression.** Faible. Vérifier qu'aucun deal existant n'est déjà en
FOUR_EYES bloqué (`SELECT reference, status, maturity_date FROM deals
WHERE fixing_policy='FOUR_EYES'`).

---

### P2-01 — Les Greeks du book somment des sensibilités calculées à des dates et sous des marchés différents

**Domaine** : Portefeuille, Risk Management · **Sévérité** : P2

**Preuve.** `_aggregate_risk` ([portfolios.py:195](backend/app/api/portfolios.py:195))
lit `json.loads(d.greeks_json)` — le dernier résultat persisté par
`POST /api/deals/{id}/greeks`, écrasé à chaque calcul, sans historique
([models.py:233-236](backend/app/db/models.py:233)). Chaque calcul utilise le **snapshot
de booking du deal** (σ, q, corr, courbe figés à sa date de trade) sauf recalibrage
explicite, et le spot du jour où il a été lancé. Le seul garde-fou est
`deals_stale` : plus de **7 jours** ([portfolios.py:26](backend/app/api/portfolios.py:26)).
Deux deals calculés à 6 jours d'intervalle sont sommés sans le moindre signal.

**Impact métier.** Le delta du book n'est pas le delta du book à une date. C'est une somme
d'instantanés. Sur un portefeuille d'autocalls proches de barrières — où le gamma est
quasi digital, ce que l'infobulle de l'écran reconnaît elle-même —, deux jours d'écart
suffisent à changer un delta de signe. La `Recalculer` de l'écran
([RiskManagementView.vue:1049](frontend/src/views/RiskManagementView.vue:1049)) rétablit
la cohérence de date, mais reste séquentielle avec 400 ms de pacing, donc rarement lancée
sur un book fourni — et elle ne rétablit pas la cohérence de **marché** (chaque deal garde
sa vol de booking).

**Correction recommandée.** Estampiller l'agrégat plutôt que de le corriger : ajouter
`spread_hours = (plus récent − plus ancien)` et un drapeau
`consistent: bool` (tous les calculs dans la même journée ouvrée), affichés en tête de
l'onglet Greeks. Puis, à terme, un mode « recalcul cohérent » qui impose la même date de
valorisation et le même jeu d'hypothèses (`recalibrate: "realized"`) à tous les deals du
scope.

**Tests** : deux deals calculés à 3 jours d'écart → `consistent = false` malgré
`deals_stale` vide. **Risque de régression** : nul (champs additifs).

---

### P2-02 — Aucun agrégat de valorisation du portefeuille

**Domaine** : Portefeuille · **Sévérité** : P2 (fonctionnalité absente)

**Preuve.** Inventaire complet des endpoints d'agrégation : `risk-global`, `{id}/risk`,
`exposure-by-counterparty`, `barriers-global`, `{id}/barriers`, `pnl-explain-global`,
`{id}/pnl-explain`, `shock`, `shock-global`, `var-global`. **Aucun** ne renvoie le MtM
total, le P&L latent, le P&L réalisé ni le P&L journalier. Le seul chiffre de valorisation
agrégé est `delta_mtm_eur` à l'intérieur du P&L explain, qui exige par deal deux
valorisations complètes plus quatre revalorisations intermédiaires.

**Impact métier.** La question la plus élémentaire d'un book — « combien vaut-il
aujourd'hui, combien ai-je gagné » — n'a pas de réponse à coût raisonnable. Le périmètre
demandé (MtM total, P&L, P&L journalier, realized/unrealized) n'est couvert qu'au prix
d'un calcul de plusieurs minutes.

**Correction recommandée.** Un `GET /api/portfolios/{id}/valuation` qui somme les MtM
**persistés** — ce qui suppose d'abord de les persister : aujourd'hui aucun MtM n'est
stocké (`Deal.fair_value` est écrit une seule fois, au booking, et `DealUpdate` refuse de
le modifier). La brique manquante est une table `deal_valuations` (une ligne par deal et
par date), qui débloque d'un coup le MtM du book, le P&L journalier et l'historique de
valorisation — c'est exactement ce que `DEAL_LIFECYCLE_2026-07.md` §3 identifiait comme
absent, et qui ne l'est toujours pas.

**Tests** : à définir avec la conception. **Risque de régression** : nul (ajout).

---

### P2-03 — Ni le FX ni les dividendes ne sont choquables

**Domaine** : Risk Management · **Sévérité** : P2

**Preuve.** `ShockRequest` ([shocks.py:39-50](backend/app/api/shocks.py:39)) expose
`spot_shock_pct`, `vol_shock_pts`, `rate_shock_bp`, `corr_shock_pts` — et rien d'autre.
Le taux de change est lu **hors** du scénario, au taux courant, dans les deux branches :
`fx_rate = fx_rate_to(deal.devise, "EUR")` à
[shocks.py:134](backend/app/api/shocks.py:134), appliqué au `delta_pts` non choqué. Le
dividende n'est ni un paramètre de `ShockRequest` ni un `**bump` transmis à `run_mc`.

**Impact métier.** Un book multi-devises n'a **aucune** mesure de son risque de change :
c'est pourtant la seule exposition qui frappe toutes les positions d'une devise
simultanément. Le préréglage « Crise systémique » (spot −30 %, vol +20, taux −100 bp,
corr +20) omet le mouvement de change qui accompagne toute crise réelle. Côté dividende,
un autocall long est significativement sensible au taux de distribution : la sensibilité
n'est ni mesurée (pas de Greek), ni stressée.

*Point vérifié et correct au passage* : le choc de taux `dr` est un **vrai** décalage
parallèle de toute la courbe zéro, pas seulement du taux plat —
`_build_rate_term(yield_curve, ts, dt, r, dr)` applique `df * exp(-dr·t)` et redérive les
forwards depuis les `df` ([engine.py:950-973](backend/app/core/payscript/engine.py:950)).
L'actualisation, la dérive et la calibration du smile bougent ensemble.

**Correction recommandée.** Ajouter `fx_shock_pct` (global, ou par devise) appliqué au
`fx_rate` **avant** le calcul de `delta_eur` et dans le dénominateur `nominal_total_eur` ;
ajouter `div_shock_pts` transmis à `run_mc` via un `q_add` par sous-jacent (le moteur
accepte déjà une courbe de dividendes par actif, donc le décalage y est mécanique).

**Tests** : book EUR + USD, choc FX −10 % → seul le sous-book USD bouge, du bon montant ;
choc dividende +1 pt sur un autocall long → impact du signe attendu.
**Risque de régression** : faible, paramètres additifs de valeur nulle par défaut.

---

### P2-04 — Corrélation absente du snapshot : identité silencieuse

**Domaine** : MtM, Greeks, chocs · **Sévérité** : P2

**Preuve.** [deals.py:5808](backend/app/api/deals.py:5808) :
`corr = market.get("corrMatrix") or [[1.0 if i==j else 0.0 …]]`. Même motif à
[deals.py:5326](backend/app/api/deals.py:5326) (réinvestissement). Sonde 6, deal
worst-of à deux sous-jacents dont le snapshot ne porte pas `corrMatrix` :

```
corr effectivement utilisée : [[1.0, 0.0], [0.0, 1.0]]
```

**Impact métier.** Sur un worst-of, la corrélation est le paramètre le plus cher du
produit. La supposer nulle surévalue systématiquement la dispersion, donc **sous-évalue**
le worst-of. `market_used.corr` restitue bien l'identité utilisée — donc l'information est
disponible —, mais rien ne signale qu'il s'agit d'un défaut et non d'une donnée figée au
booking. Contraste net avec le traitement du FX manquant, exemplaire, qui refuse d'inventer
et nomme la position.

**Correction recommandée.** Appliquer la doctrine `fx_rate_to` : sur un deal **à plusieurs
sous-jacents**, l'absence de `corrMatrix` doit lever un 422 explicite (« corrélation non
persistée sur ce deal — re-booker ou fournir un override »), pas retomber sur l'identité.
Sur un seul sous-jacent, `[[1.0]]` reste légitime.

**Tests** : deal mono-actif sans corrMatrix → inchangé ; deal 2 actifs sans corrMatrix →
422 nommant le deal. **Risque de régression** : moyen — des deals existants peuvent être
dans ce cas. Requête de contrôle préalable indispensable.

---

### P2-05 — La composition affichée et les agrégats calculés décrivent des populations différentes (compte admin)

**Domaine** : Portefeuille, cloisonnement · **Sévérité** : P2

**Preuve.** `list_deals` ne filtre **pas** pour le rôle `admin`
([deals.py:1381](backend/app/api/deals.py:1381)) — sonde 7 :

```
list_deals(user 'phil')  → ['PHIL-001']
list_deals(role 'admin') → ['AUTRE-001', 'PHIL-001']
contreparties visibles par l'admin : ['Contrepartie confidentielle du user 2', 'BNP']
```

Or l'onglet Portefeuilles construit sa composition côté client :
`members = dealsStore.deals.filter(d => d.status === 'actif')`
([portfolios.js:66](frontend/src/stores/portfolios.js:66)), alimenté par `GET /api/deals`,
tandis que `/risk-global` et `/exposure-by-counterparty` filtrent `Deal.user_id ==
current.id`. Sur un compte admin, le tableau « Composition — Tous portefeuilles » liste les
deals de **tous** les utilisateurs, mais les tuiles au-dessus n'agrègent que les siens.

**Impact métier.** Divergence silencieuse entre ce qui est listé et ce qui est totalisé,
sur le seul compte qui a une vue globale. Un administrateur qui utilise l'écran comme
tableau de bord lit un nominal et une exposition qui ne correspondent pas aux lignes
affichées. Le bouton « Recalculer » itère par ailleurs sur `pf.members`, donc sur des deals
d'autres utilisateurs. Accessoirement : cette lecture croisée n'écrit **aucun**
`AuditEvent`.

**Correction recommandée.** Trancher le périmètre du rôle admin (§7, question 4), puis
l'appliquer **au même endroit** côté serveur : soit `list_deals` se restreint comme les
agrégats, soit les agrégats s'élargissent comme `list_deals` — jamais un mélange décidé
côté client.

**Tests** : admin avec un deal d'un autre user → cardinalité de `members` == cardinalité
des `deals_included` de `/risk-global`. **Risque de régression** : moyen, selon
l'arbitrage retenu.

---

### P2-06 — Barrières des scripts anciens : le niveau affiché est le défaut du script, pas le terme négocié

**Domaine** : Surveillance, Risk Management, alertes · **Sévérité** : P2

**Preuve.** `build_watchlist_row` gère deux branches. Avec des paramètres `M_`, le niveau
passe par `_level_for()` qui lit `user_params` en priorité
([deals.py:1574-1582](backend/app/api/deals.py:1574)) — correct. Sans `M_` (branche
héritée, [deals.py:1609-1618](backend/app/api/deals.py:1609)), le niveau est
`p.stored_val`, **le défaut compilé du script**, et `user_params` est ignoré. Or la même
fonction alimente les trois consommateurs : `GET /api/deals/watchlist`,
`/api/portfolios/barriers*` et le moteur d'alertes quotidien
([lifecycle_alerts.py:88](backend/app/services/lifecycle_alerts.py:88)).

Deux défauts annexes de la même fonction :
- `_classify_param_barrier` ([deals.py:1401](backend/app/api/deals.py:1401)) teste
  `"AC" in n` en sous-chaîne : un `PARAM TRACKER`, `FACTEUR` ou `PLACEMENT` dont la valeur
  tombe dans `[0.2, 3.0]` est classé **barrière d'autocall**. Symétriquement, un
  `NIVEAU_RAPPEL` ou un `SEUIL` n'est jamais détecté ;
- le tri de proximité utilise `abs(gap_pts)` ([deals.py:1622](backend/app/api/deals.py:1622)),
  donc mélange les directions : un deal 3 points **au-dessus** de son autocall (situation
  favorable) remonte en tête devant un deal 10 points de son KI. `_barrier_severity`
  ([portfolios.py:547](backend/app/api/portfolios.py:547)) traite bien la direction pour la
  **couleur**, mais pas pour l'**ordre**.

**Impact métier.** Un deal ancien dont le KI a été négocié à 60 % alors que le script porte
70 % par défaut affiche 70 % en Surveillance, 70 % dans l'onglet Barrières, et déclenche
son alerte de franchissement 10 points trop tôt. Les faux positifs de nom polluent le
compteur « critique » de l'écran Risk.

**Correction recommandée.** Utiliser `_level_for()` dans les deux branches (correctif d'une
ligne). Remplacer la sous-chaîne par une correspondance de segment
(`re.search(r"(?:^|_)(AC|CALL)(?:$|_)", n)`). Trier sur un gap **signé et orienté** (la
sévérité, puis le gap) plutôt que sur sa valeur absolue.

**Tests** : script hérité + `user_params` divergent → le niveau retourné est celui de
`user_params` ; `PARAM TRACKER = 1.0` → non classé barrière ; tri : KI à 10 pts avant
autocall à 3 pts au-dessus. **Risque de régression** : les gaps affichés bougent sur les
deals hérités — c'est l'objet du correctif, à annoncer.

---

### P2-07 — Une alerte de barrière ne se déclenche qu'une fois dans la vie du deal

**Domaine** : Lifecycle, alertes · **Sévérité** : P2

**Preuve.** `dedup_key = f"deal:{deal.id}:barrier:{b['name']}"`
([lifecycle_alerts.py:102](backend/app/services/lifecycle_alerts.py:102) et
[:109](backend/app/services/lifecycle_alerts.py:109)) — ni date, ni observation, ni
direction. `_alert_once` renvoie `False` si la clé existe déjà, **pour toujours**.

**Impact métier.** Sur un autocall mensuel, l'alerte « au-dessus de la barrière de rappel,
rappel probable dans N jours » se déclenche à la première observation approchée et **plus
jamais** pour les onze suivantes. Le franchissement d'un KI qui se répare puis se reproduit
n'alerte qu'une fois. Deux barrières homonymes (`ki` et `autocall` portant le même nom
`M_BAR`) se neutralisent mutuellement, la première créée gagnant.

L'intention de déduplication est saine et documentée (« une résolution ou un
franchissement alerte une fois »), mais elle est appliquée à la mauvaise granularité :
la clé décrit *la barrière*, alors que le fait à dédupliquer est *cette barrière à cette
observation*.

**Correction recommandée.** Intégrer l'observation à la clé :
`deal:{id}:barrier:{name}:{kind}:{next_event.event_date}`. La déduplication intra-passe
reste garantie, le ré-armement à chaque nouvelle constatation devient naturel.

**Tests** : deux passes le même jour → une alerte ; deux passes de part et d'autre d'une
observation → deux alertes ; `ki` et `autocall` de même nom → deux alertes distinctes.
**Risque de régression** : un pic d'alertes au premier passage après déploiement (les
nouvelles clés ne correspondent à rien d'existant). À purger ou à annoncer.

---

### P2-08 — Un seul deal au `sens` invalide rend tout l'écran Risk inaccessible

**Domaine** : Portefeuille, robustesse · **Sévérité** : P2

**Preuve.** `position_sign` lève délibérément sur une valeur inattendue
([models.py:567](backend/app/db/models.py:567)) — le choix est bon et argumenté (un risque
simplement inversé « a l'air entièrement plausible »). Mais `_aggregate_risk` l'appelle
dans une boucle sans capture ([portfolios.py:193](backend/app/api/portfolios.py:193)).
Sonde 5 :

```
risk-global → ValueError: Sens de position inconnu sur le deal 'PROBE-…' : 'Vente'
```

soit un HTTP 500 sur l'écran complet.

Le chemin d'entrée d'un mauvais `sens` est aujourd'hui étroit : `DealCreate.sens` est un
`Literal`, `update_deal` refuse tout, `deals` n'a aucun `editable_fields` admin. Restent
les lignes anciennes et l'écriture directe en base.

**Impact métier.** Défaut de robustesse plutôt que d'exactitude : le mode de dégradation
est global (page morte) alors que toute la couche est par ailleurs conçue en dégradation
**par deal** — `deals_missing_fx`, `deals_missing_greeks`, `deals_missing_theta`,
`skipped`, `errors`. C'est la seule exception, et c'est celle qui casse.

**Correction recommandée.** Envelopper l'appel et alimenter une liste
`deals_invalid_sens`, restituée et affichée comme les cinq autres listes d'exclusion.
Même traitement dans `_run_shock_on_book` et `_run_explain_on_book`.

**Tests** : book de 3 deals dont 1 au sens corrompu → les 2 autres agrégés, le troisième
nommé. **Risque de régression** : nul.

---

### P2-09 — Trous de piste d'audit sur les suppressions et le rattachement au portefeuille

**Domaine** : Auditabilité · **Sévérité** : P2

**Preuve.** Inventaire des actions émises
(`grep -rno 'action="[A-Z_]*"' backend/app/api backend/app/services`, 48 actions
distinctes) croisé avec les mutations existantes. Manquent :

| Mutation | Endpoint | Audit |
|---|---|---|
| Déplacer un deal de portefeuille | `PATCH /api/deals/{id}/portfolio` | **aucun** — sonde 8 : 0 événement avant, 0 après |
| Supprimer une cotation | `DELETE /api/rfq/{id}/quotes/{qid}` | **aucun** (l'ajout et la mise à jour le sont) |
| Supprimer une RFQ | `DELETE /api/rfq/{id}` | **aucun** |
| Créer / renommer / supprimer un portefeuille | `api/portfolios.py` | **aucun** |
| Lecture croisée d'un admin | `GET /api/deals` | **aucun** |

**Impact métier.** Le rattachement au portefeuille détermine dans quel agrégat de risque
un deal apparaît : le changer sans trace revient à modifier une frontière de risque
anonymement. Côté RFQ, la protection `_refuse_if_booked` couvre tout **après** le booking,
mais avant, une cotation concurrente peut être supprimée sans laisser d'empreinte — or
c'est précisément le geste qui embellirait rétroactivement une best execution.

**Correction recommandée.** Quatre `record_audit_event` (`DEAL_PORTFOLIO_REASSIGNED`,
`QUOTE_DELETED`, `RFQ_DELETED`, `PORTFOLIO_DELETED`) avec `before`/`after`. L'infrastructure
existe et est déjà append-only.

**Tests** : chaque mutation → un `AuditEvent` du bon `object_type`/`object_id`.
**Risque de régression** : nul.

---

### P2-10 — Coût : un fetch Yahoo et N Monte Carlo par deal, en séquentiel, sur un endpoint bloquant

**Domaine** : Performance · **Sévérité** : P2

**Preuve.** Quatre opérations de l'écran Risk sont en O(N deals) × (1 appel réseau + k MC) :

| Opération | Par deal | N=30 (ordre de grandeur) |
|---|---|---|
| `barriers-global` | 1 `load_hist_prices` (sans cache) | 30 requêtes yfinance |
| `shock-global` | 1 `_mtm_core` (fetch + replay + MC 20k) + 1 `run_mc` | 30 fetches + 60 MC |
| `pnl-explain-global` | 2 `_mtm_core` + 4 revalorisations | 60 fetches + ~180 MC |
| « Recalculer » (client) | 1 `POST /greeks` = 1 `_mtm_core` + ~10 reprices à N/4 | 30 fetches + ~330 MC, plus 400 ms de pacing |

Aucun cache de prix : le commentaire de `_aggregate_barriers`
([portfolios.py:544](backend/app/api/portfolios.py:544)) le dit explicitement. Les trois
premiers sont des endpoints synchrones sans pagination ni budget de temps ; un
`shock-global` sur un book fourni est une requête HTTP de plusieurs minutes. Seule la VaR
a été sortie en asynchrone (`ComputeBatch` + worker), preuve que le motif est connu.

**Impact métier.** Au-delà de l'attente, c'est un risque d'exploitation : rien ne borne la
durée, rien ne reprend un calcul interrompu, et yfinance peut throttler sous la rafale —
auquel cas les deals concernés atterrissent dans `errors` et les totaux deviennent
partiels sans que la cause soit lisible.

**Correction recommandée.** Par ordre de rendement : (1) un cache mémoire de
`load_hist_prices` à clé `(ticker, start, end)` sur la durée de la requête — supprime à lui
seul la redondance intra-appel et entre `barriers` et `shock` ; (2) `shock-global` et
`pnl-explain-global` bascule sur `ComputeBatch`, comme la VaR ; (3) « Recalculer » en
parallèle borné (4 en vol) plutôt qu'en séquentiel + `sleep`.

**Tests** : mesure de référence sur 20 deals synthétiques avant/après (1 seul appel Yahoo
par ticker et par requête). **Risque de régression** : cache mal invalidé → prix périmés.
Le borner à la durée de la requête, pas au processus.

---

### P2-11 — CORS ouvert avec credentials

**Domaine** : Sécurité · **Sévérité** : P2 (constat rappelé de l'audit du 2 août, non traité)

**Preuve.** [main.py:47-53](backend/app/main.py:47) : `allow_origins=["*"]`,
`allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`.

**Impact métier.** Nul tant que l'application est servie sur `127.0.0.1` et que le jeton
vit dans le `localStorage` (la politique d'origine identique le protège). Devient réel dès
la première exposition réseau. La combinaison `*` + `credentials` est de surcroît rejetée
par les navigateurs, donc la configuration ne fait pas ce qu'elle annonce.

**Correction recommandée.** Liste blanche explicite alimentée par
`STRUCTURA_ALLOWED_ORIGINS`, défaut `http://localhost:5173,http://127.0.0.1:8000`.
**Risque de régression** : un poste de développement sur un autre port cesse d'appeler
l'API tant que la variable n'est pas renseignée.

---

### P2-12 — Notions absentes du modèle : client, statut d'annulation, archivage

**Domaine** : Modèle de données · **Sévérité** : P2

**Preuve.** `Deal` n'a **aucun champ client** (`grep -n "client" backend/app/db/models.py`
ne remonte que des commentaires, plus `EmtRecord.client_type` qui est une catégorie
réglementaire retail/professionnel, pas une identité). `Deal.status` vaut
`actif | callé | échu | résilié` — ni `annulé`, ni `archivé`, ni `pending`.

**Impact métier.** Trois demandes du périmètre restent sans support :
- « portefeuille par client », « risques par client », « masquage des clients » — il n'y a
  pas de client dans le modèle. `contrepartie` désigne la **banque émettrice**, pas
  l'investisseur final. Pour un usage family office / distributeur, c'est la dimension
  d'agrégation manquante ;
- pas d'annulation : un deal booké par erreur n'a pas de sortie propre (`résilié` existe
  dans le modèle mais n'est posé par aucun chemin de code) ;
- pas d'archivage : un deal résolu reste indéfiniment dans les listes ; le seul filtre est
  `status == "actif"`, ce qui vide la mémoire du book aussitôt qu'un deal se dénoue.

**Correction recommandée.** Ce sont des décisions de conception, pas des correctifs —
cf. §7, question 5. La plus urgente est le **client**, parce qu'elle conditionne quatre
axes d'agrégation demandés et le masquage en mode démo.

---

### P2-13 — Aucune incertitude publiée sur les Greeks

**Domaine** : Greeks · **Sévérité** : P2

**Preuve.** `compute_greeks` ([engine.py:1857](backend/app/core/payscript/engine.py:1857))
renvoie des scalaires arrondis, jamais d'intervalle. `N_g = max(1000, N // 4)` —
**5 000 chemins** pour un MtM par défaut à 20 000. Le gamma divise une différence seconde
par `0.0009` ([engine.py:1937](backend/app/core/payscript/engine.py:1937)), soit une
amplification de l'erreur d'échantillonnage d'environ 1 100 ×. Les nombres communs
aléatoires (CRN) et le `seed=42` fixe absorbent l'essentiel — c'est la bonne construction
—, mais un seed **fixe et identique pour tous les deals** signifie aussi que le biais
résiduel ne se diversifie pas dans l'agrégat : sur un book de produits proches, les erreurs
s'additionnent au lieu de se compenser.

L'infobulle de l'écran le reconnaît à demi-mot (« peut être très élevé et bruité près
d'une barrière autocall/KI »), ce qui est honnête mais ne remplace pas un chiffre.

**Correction recommandée.** Publier l'`ic95` du prix de référence à côté des Greeks
(`run_mc` le renvoie déjà) ; à terme, une estimation de l'erreur par répétition sur 3
seeds pour le gamma seul, le plus fragile. Rendre `N_g` paramétrable.

**Risque de régression** : nul (champs additifs).

---

### P3-01 — Le Greek de corrélation est une différence avant, tous les autres sont centrés

`greeks[f"corr_{i}_{j}"] = (price(corr_delta=+0.05) - base_g) / 0.05`
([engine.py:1976](backend/app/core/payscript/engine.py:1976)) : différence **avant**,
biais d'ordre O(bump), avec un bump de **5 points** de corrélation. Delta (±1 %), gamma
(±3 %), vega (±1 pt), rho (±1 pt) et theta sont tous centrés, donc d'ordre O(bump²).
Sur un worst-of, la convexité en corrélation n'est pas négligeable à 5 points.
→ Passer en différence centrée (`±0,025`) ou justifier l'asymétrie dans la docstring.

### P3-02 — Docstring de `/watchlist` périmée et trompeuse

[deals.py:1436](backend/app/api/deals.py:1436) affirme : « Uses the script's PARAM
defaults — user overrides typed in the UI at pricing time are not persisted on the deal
(known limitation) ». C'est **faux** depuis la persistance de `market_snapshot.user_params` :
`build_watchlist_row` les lit bien ([deals.py:1554](backend/app/api/deals.py:1554)) — sauf
dans la branche héritée (cf. P2-06). Une docstring qui annonce un contrôle absent alors
qu'il est présent (et inversement) est plus dangereuse que pas de docstring.

### P3-03 — Le plancher de maturité résiduelle n'est pas restitué

`T_remaining = max(1/52, (maturity - today).days / 365.25)`
([deals.py:5716](backend/app/api/deals.py:5716)) : un deal à 2 jours de sa maturité est
valorisé comme s'il en restait 7. La réponse expose `T_remaining` arrondi, donc la valeur
plancher est visible — mais rien ne dit qu'elle a été plafonnée.
→ Ajouter `T_remaining_floored: bool` au payload.

### P3-04 — Le booking n'offre pas le choix du portefeuille

`_book_deal` assigne systématiquement `get_or_create_default_portfolio`
([deals.py:1234](backend/app/api/deals.py:1234)) ; `DealCreate` ne porte pas de
`portfolio_id`. Tout deal doit être déplacé après coup, geste qui n'est par ailleurs pas
audité (P2-09). → Ajouter `portfolio_id: Optional[int]` à `DealCreate`, validé comme dans
`assign_deal_portfolio`.

### P3-05 — Conventions d'unités des Greeks hétérogènes (documentées, mais hétérogènes)

Delta, gamma et vega sont publiés **par 100 %** de mouvement ; rho et corrélation sont
rééchelonnés `×0,01` pour être **par 1 point** ; theta est **par jour calendaire**. Chaque
convention est correctement expliquée dans l'infobulle correspondante
([RiskManagementView.vue:132](frontend/src/views/RiskManagementView.vue:132),
[:197](frontend/src/views/RiskManagementView.vue:197),
[:254](frontend/src/views/RiskManagementView.vue:254)) — le constat n'est donc pas une
erreur, mais un coût de lecture : trois échelles dans le même tableau.
→ Choix à acter (§7, question 6), sinon ne rien changer.

### P3-06 — 404 « Deal introuvable » indistinguable pour trois causes différentes

Sonde 10 : un deal appartenant à un autre utilisateur et un identifiant inexistant
renvoient exactement le même message. La non-divulgation est **correcte** et doit être
conservée côté API. En revanche, `_ops_deal` renvoie le même 404 pour un motif tout autre
— `current.entity_id is None` — sur un deal parfaitement accessible par ailleurs
([deals.py:761](backend/app/api/deals.py:761)). C'est la principale cause de « deal
introuvable » inexplicable identifiée par cet audit.
→ Conserver le 404 côté API, mais journaliser la cause réelle (`AuditEvent` ou log serveur)
pour rendre l'incident diagnosticable.

---

## 4. Matrices de cohérence

### 4.1 Statuts du cycle de vie

**Statuts existants** : `Deal.status ∈ {actif, callé, échu, résilié}` ·
`DealEvent.status ∈ {futur, observé, callé, ki, final, annulé}` ·
`LifecycleProposal.status ∈ {PROPOSED, VALIDATED, APPLIED, REJECTED, STALE}` ·
`RfqRequest.status ∈ {draft, envoye, quote, retenue, clos, sans_suite}`.

**Transitions autorisées du deal** :

| De | Vers | Déclencheur | Garde |
|---|---|---|---|
| — | `actif` | `_book_deal` | Toutes les validations amont |
| `actif` | `callé` | `apply_lifecycle_proposal`, résultat `callé` | CAS `WHERE status='actif'` + proposition `VALIDATED` + hash d'inputs officiels inchangé |
| `actif` | `échu` | idem, résultat `ki` ou `final` | idem |
| `actif` | `actif` | passe quotidienne sans événement terminal | — |
| `callé`/`échu` | — | **aucune sortie** | `_mtm_core` refuse, agrégats excluent |
| — | `résilié` | **jamais posé par aucun code** | — |

**Cohérence vérifiée (par lecture et sonde)** :

| Propriété | Verdict |
|---|---|
| Un événement appliqué deux fois | **Impossible** — CAS sur `LifecycleProposal.status` puis sur `Deal.status`, `dedup_key` UNIQUE |
| Une résolution concurrente | **Refusée et tracée** — `rowcount != 1` → `RESOLUTION_APPLICATION_REJECTED` |
| Statut impossible | **Aucun** — les quatre valeurs sont exhaustives et posées à un seul endroit |
| Deal mature encore `actif` | **Possible et fréquent** — voir P1-03 et P1-06 ; aucune détection, aucune alerte |
| Deal sans prochaine action | **Possible** — un FOUR_EYES sans rôles disponibles (P1-06) n'a aucune issue |
| Divergence statut / dates / événements | **Non détectée** — rien ne compare `status`, `maturity_date` et le statut du dernier `DealEvent` |
| Fuseaux horaires | **Traités** — `_utc_iso` réattache le `Z` ; dates métier en ISO local, `observed_at` en UTC |
| Jours ouvrés | **Non traités** — convention « dernier close ≤ date », pas de calendrier de place (constat antérieur, `AUDIT_COMPLET_2026-08-02.md`) |

**Lacune à retenir** : il n'existe **aucun contrôle de cohérence** signalant un deal
`actif` dont la maturité est dépassée. C'est le symptôme observable commun de P1-03 et
P1-06, et il est invisible partout dans l'application.

### 4.2 Identifiants

| Identifiant | Type | Unicité | Utilisé comme clé de jointure | Risque |
|---|---|---|---|---|
| `Deal.id` | int PK | oui | **oui**, partout | — |
| `Deal.reference` | str | **UNIQUE + index** | non (affichage, PDF, alertes) | — |
| `Deal.rfq_id` | int FK | **UNIQUE** (un AO ⇒ un trade) | oui | — |
| `Deal.indicative_id` | int FK | non contrainte | oui | Plusieurs deals depuis un indicatif : possible, non bloqué |
| `Deal.portfolio_id` | int FK nullable | non | oui | Nullable seulement pour le backfill au boot |
| `Deal.uat_batch_id` | int FK | non | **jamais lu** | **P1-02** |
| `RfqRequest.reference` | str | UNIQUE | non | — |
| `RfqQuote.parent_quote_id` | int FK | non | oui (last look) | Chaînes imbriquées refusées depuis le 30/07 |
| `LifecycleProposal.dedup_key` | str | **UNIQUE** | non | — |
| `Alert.dedup_key` | str | index, **non unique** | non | Granularité trop grossière — **P2-07** |
| `AuditEvent.object_id` | int | index | **polymorphe, sans FK** | Assumé (append-only, l'objet peut disparaître) |
| `DealEvent.event_index` | int | non | non | Ordre logique ; le tri se fait sur `t_years` puis `event_index` |

**Conversions et jointures fragiles** — recherchées, une seule trouvée :
`stores/portfolios.js:106` envoie `Number(rawValue)` depuis la valeur d'un `<select>`
(chaîne), correctement converti côté client et revalidé côté serveur par Pydantic.
Aucune comparaison `id` / `reference` croisée détectée. Aucun cache clé-par-référence.

### 4.3 Données nécessaires au MtM

| Donnée | Source | Absence → | Verdict |
|---|---|---|---|
| `script_snapshot` | figé au booking | 422 | ✅ |
| `market.constats` | figé au booking (depuis 19/07) | 422 explicite « re-booker » | ✅ |
| `market.r` | snapshot | défaut 3 % — **et `0` aussi** | ❌ **P1-01** |
| `market.corrMatrix` | snapshot | identité silencieuse | ❌ **P2-04** |
| `market.underlyings[].sigma/q` | snapshot | `validate_model` refuse | ✅ |
| `market.yieldCurve` | snapshot | taux plat `r` | ✅ (documenté) |
| `S₀` (event t=0) | saisi / Yahoo | 422 « Spot/S₀ manquant » | ✅ |
| Historique Yahoo | `load_hist_prices` | 422 ; dates alignées `dropna()` | ✅ |
| Taux de change | `fx_rate_to` | `None` → position exclue et **nommée** | ✅ exemplaire |
| `deal.status == actif` | base | 422 | ❌ **P1-03** |
| `today < maturity` | calcul | 422 | ❌ **P1-03** |

### 4.4 Conventions des Greeks

| Greek | Bump | Différence | Unité publiée | Agrégation |
|---|---|---|---|---|
| Delta | ±1 % **relatif au spot courant** | centrée | fraction de nominal **par 100 %** de spot | `× sign × nominal × FX` |
| Gamma | ±3 % relatif | centrée (3 points) | **par 100 %²** | idem |
| Vega | ±1 pt de vol **absolu** | centrée | **par 100 pts** de vol | idem |
| Theta | 1 pas de grille (1 semaine) | avant, ÷ 7 | **par jour calendaire** | idem, `None` si observation franchie |
| Rho | ±1 pt, décalage parallèle de **toute la courbe** | centrée | **par 100 pts**, rééchelonné `×0,01` | idem |
| Corrélation | **+5 pts**, une paire | **avant** ❌ | par 100 pts, rééchelonné `×0,01` | idem, groupé par paire canonique |

**Invariants respectés** : bump multiplicatif autour de `spot_base` (et non de 1,0) — un
deal à 130 % du strike est choqué de 1 % de là où il est ; les extrema réalisés, la mémoire
de coupons et les fixings **ne bougent pas** sous un bump (ce sont des faits) ; `wof0` est
dérivé du vecteur bumpé, ce qui interdit d'oublier le retour fantôme sur `REALVOL` ;
CRN sur tous les termes, centre inclus.
**Non respecté** : symétrie du bump de corrélation (P3-01) ; publication d'une incertitude
(P2-13) ; portée du vega sous Heston/LSV — correctement **étiquetée** par `vega_scope`
mais non corrigée, et l'agrégat somme des vegas de portées différentes.

### 4.5 Règles d'inclusion dans l'agrégation portefeuille

| Population | Greeks | Nominal | Exposition cpty | Barrières | Chocs | P&L explain |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| `actif` avec Greeks frais | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `actif` sans Greeks | ❌ nommé | ✅ | ✅ | ✅ | ✅ | ✅ |
| `actif`, Greeks > 7 j | ✅ **+ nommé** | ✅ | ✅ | ✅ | ✅ | ✅ |
| `actif`, Greeks 1–7 j | ✅ **silencieux** | ✅ | ✅ | ✅ | ✅ | ✅ | 
| `actif`, FX inconnu | ❌ nommé | ❌ | ❌ nommé | ✅ | ❌ nommé | ❌ nommé |
| `callé` / `échu` **réglé** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `callé` / `échu` **non réglé** | ❌ | ❌ | ❌ **P1-03** | ❌ | ❌ | ❌ |
| mature mais `actif` | ✅ | ✅ | ✅ | ✅ | ❌ erreur | ❌ ignoré |
| `résilié` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **UAT** | ✅ **P1-02** | ✅ **P1-02** | ✅ **P1-02** | ✅ | ✅ | ✅ |
| deal d'un autre user (compte admin) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ — mais **listé** dans la composition **P2-05** |

**Ni oublié ni compté deux fois** : aucun double comptage détecté (un deal appartient à
exactement un portefeuille, jamais NULL, et `risk-global` parcourt par `user_id` et non par
portefeuille — donc pas de double passage). Les oublis sont ceux des deux lignes rouges
ci-dessus.

### 4.6 Scénarios de risque

| Facteur | Choc disponible | Appliqué à | Non choqué |
|---|---|---|---|
| Spot | ✅ global + override par sous-jacent, **relatif au spot courant** | tenseur simulé | — |
| Volatilité | ✅ additive en points | `vol_add` par actif | portée réduite sous Heston/LSV |
| Taux | ✅ parallèle, **toute la courbe zéro** (actualisation + dérive + smile) | `dr` | pas de choc non parallèle (pentification) |
| Corrélation | ✅ décalage uniforme hors diagonale, clippé ±0,99 | matrice complète | pas de choc par paire |
| **FX** | ❌ | — | **taux courant réutilisé dans le scénario — P2-03** |
| **Dividendes** | ❌ | — | **P2-03** |
| Scénarios historiques | via VaR (`ComputeBatch`), **jamais testé en réel** | — | hors périmètre de cet audit |
| Gap risk / saut | ❌ | — | monitoring hebdo par défaut, pont brownien en continu |

**Vérification demandée** — « le scénario choqué est-il appliqué à toutes les données
pertinentes, aucune donnée non choquée réutilisée silencieusement ? » : **oui pour
spot/vol/taux/corr**, l'état de cycle de vie hérité étant explicitement repris dans la
jambe choquée (`wof_min_init`, `memo_init`, `index_offset`, `fix_state_init` — c'était un
correctif antérieur documenté dans le code). **Non pour le FX**, qui est la donnée non
choquée réutilisée silencieusement.

---

## 5. Analyse des tests

### 5.1 Couverture existante — 36 fichiers, ~600 tests

| Domaine | Fichiers | Tests | Appréciation |
|---|---|---:|---|
| Moteur / payoffs | `test_engine`, `test_engine_golden`, `test_parser`, `test_payscript_*` | 145 | Solide, avec harnais golden |
| RFQ | `test_rfq` | **73** | Le mieux couvert de l'application |
| Workflow / lifecycle | `test_workflow_controls`, `test_workflow_phase2`, `test_garde_fous` | 77 | Solide, maker-checker inclus |
| Greeks | `test_greeks_stateful`, `test_curve_consistency`, `test_dividend_curve` | 33 | Bon (état hérité vérifié) |
| Mark-to-Future | `test_mtf_audit_2026_08_03`, `test_mtf_drilldown` | 26 | Bon |
| Remédiation quant | `test_remediation_2026_08_02` | 38 | Bon |
| **Agrégation portefeuille** | `test_portfolio_pnl`, `test_portfolio_corr_greek`, `test_portfolio_barriers` | **11** | **Insuffisant** |
| **Chocs** | `test_shocks` | **8** | **Insuffisant** |
| **Booking** | (uniquement via `test_rfq`) | **0 fichier dédié** | **Insuffisant** |
| **MtM résiduel** | (uniquement via `test_mtm_explain`) | **0 fichier dédié** | **Insuffisant** |
| **Frontend** | — | **0** | **Absent** |
| **Intégration API / auth** | — | **0** | **Absent** (déjà relevé le 02/08) |

### 5.2 Tests exécutés pour cet audit

```
backend/tests/test_portfolio_pnl.py  test_portfolio_corr_greek.py
backend/tests/test_portfolio_barriers.py  test_shocks.py  test_position_sign.py
→ 23 passed in 22.27s
```

Sélection délibérément étroite : ce sont les seuls fichiers dont le contenu couvre le
périmètre aval. **Ils passent tous** — les constats de ce rapport sont donc des **lacunes
de couverture**, pas des régressions.

**Non exécuté, et pourquoi** : la suite complète (`backend/tests`, ~600 tests) — l'audit
n'a modifié aucun code, la relancer n'aurait rien prouvé et coûte plusieurs minutes.
`test_llm_scripting` (dépend d'Ollama), `test_var_engine` et `test_compute` (multi-process,
coût mémoire), `test_valuation_pdf` (génération PDF). Aucun test frontend : il n'y en a
pas.

### 5.3 Tests coûteux et risques mémoire

| Test | Coût | Observation |
|---|---|---|
| `test_var_engine` (13) | `ProcessPoolExecutor`, un processus par worker, chacun recompilant le script | Le plus lourd du dépôt ; `max_workers` non borné par les cœurs disponibles |
| `test_compute` (21) | idem | idem |
| `test_shocks` (8) | 2 MC complets par test | Acceptable en l'état |
| `test_mtf_*` (26) | tenseurs `(ts, n, N)` en `float64` — 52×2×20000 ≈ 17 Mo par run | Reste raisonnable ; un `N` accru dans un futur test ferait grimper vite |
| `test_llm_scripting` (28) | dépendance externe (Ollama) | À marquer `@pytest.mark.external` pour être exclu par défaut |

**Aucune fuite mémoire détectée** : chaque test construit son moteur en mémoire et le
laisse au ramasse-miettes. Le seul objet volumineux conservé entre appels est le cache
parquet de `amc_prices`, hors périmètre.

### 5.4 Tests à ajouter — par ordre de valeur

| # | Test | Couvre |
|---|---|---|
| 1 | `test_market_rate_zero.py` — `r = 0` sur les 5 sites | P1-01 |
| 2 | `test_portfolio_uat_isolation.py` — UAT exclu des 6 agrégats | P1-02 |
| 3 | `test_portfolio_inclusion_matrix.py` — la matrice §4.5 ligne à ligne | P1-03, P2-08 |
| 4 | `test_chain_e2e.py` — **RFQ → quote ferme → booking → MtM → Greeks → risk-global → choc**, en un seul test, Yahoo monkeypatché | Le trou le plus large : aucun test ne traverse la chaîne |
| 5 | `test_demo_mode_masking.spec.js` — montage de chaque vue en mode démo | P1-04 (impose d'introduire Vitest) |
| 6 | `test_scheduler_recovery.py` — dernier passage à J-2 → rattrapage | P1-05 |
| 7 | `test_barrier_levels.py` — script hérité + `user_params`, faux positifs de nom, ordre de tri | P2-06 |
| 8 | `test_alert_dedup_per_observation.py` | P2-07 |
| 9 | `test_audit_completeness.py` — chaque mutation écrit son `AuditEvent` | P2-09 |
| 10 | Banc de performance sur 20 deals — nombre d'appels `load_hist_prices` | P2-10 |

### 5.5 Tests à remplacer

`test_portfolio_corr_greek.py` est aujourd'hui le **seul** test à toucher
`_aggregate_risk`, et il n'en vérifie qu'une facette (le regroupement canonique des paires).
Il devrait devenir un cas particulier du test #3, qui couvrirait la matrice d'inclusion
complète.

---

## 6. Plan d'action

### Quick wins — 1 journée, gain immédiat, risque quasi nul

| Ordre | Action | Constat | Effort |
|---|---|---|---|
| 1 | Corriger `or 3.0` sur les 5 sites + test de garde-fou | P1-01 | 30 min |
| 2 | `_level_for()` dans la branche héritée des barrières | P2-06 | 10 min |
| 3 | Capturer `position_sign` → `deals_invalid_sens` | P2-08 | 20 min |
| 4 | 4 `record_audit_event` manquants | P2-09 | 45 min |
| 5 | `dedup_key` d'alerte enrichie de la date d'observation | P2-07 | 20 min |
| 6 | Correspondance de segment au lieu de sous-chaîne (`"AC" in n`) | P2-06 | 15 min |
| 7 | Corriger la docstring de `/watchlist` | P3-02 | 5 min |
| 8 | CORS en liste blanche par variable d'environnement | P2-11 | 20 min |

> Dépendances : aucune entre elles. Tous testables isolément.
> **Anti-régression** : avant le lot, exécuter la requête de contrôle du §7 (question 1)
> pour recenser les deals à `r = 0` et à `corrMatrix` absente.

### Corrections prioritaires — sprint 1 (les six P1)

| Ordre | Chantier | Dépend de | Effort |
|---|---|---|---|
| 1 | **Isolation UAT** — champ exposé, exclusion par défaut, `include_uat`, badge UI | décision §7 q.2 | 1 j |
| 2 | **Périmètre d'inclusion** — `is_settled()`, exposition « actif ou dénoué non réglé », valorisation résiduelle d'un deal dénoué | — | 2 j |
| 3 | **Mode Démo sur la chaîne** — 4 écrans enveloppés + directive structurelle | — | 2 j |
| 4 | **Garde-fou FOUR_EYES** — option grisée sans rôles disponibles + message explicite | décision §7 q.3 | 0,5 j |
| 5 | **Reprise du scheduler** — dernier passage persisté + rattrapage au boot + indicateur UI | — | 1 j |
| 6 | **Test de bout en bout** (#4 du §5.4) | 1, 2 | 1 j |

> **Ordre imposé** : 1 avant 2 (l'exclusion UAT change la population sur laquelle 2 se
> vérifie), 1 et 2 avant 6 (le test de bout en bout fige le comportement cible).
> 3, 4 et 5 sont indépendants et parallélisables.

### Sprint 2 — cohérence et lisibilité du risque

1. **Cohérence temporelle des Greeks** — `spread_hours` + drapeau `consistent`, puis mode
   « recalcul cohérent » à date et hypothèses imposées (P2-01).
2. **Choc FX et dividende** (P2-03) — le FX d'abord, c'est le plus structurant.
3. **Corrélation manquante → 422** sur un multi-actifs (P2-04), après requête de contrôle.
4. **Périmètre du rôle admin** unifié serveur (P2-05), après la décision §7 q.4.
5. **`ic95` publié à côté des Greeks** (P2-13) ; corrélation en différence centrée (P3-01).
6. Tests #1, #2, #3, #7, #8, #9 du §5.4.

### Chantiers structurels — au-delà

| Chantier | Débloque | Prérequis |
|---|---|---|
| **Table `deal_valuations`** (une ligne par deal et par date) | MtM du book, P&L latent, P&L journalier, historique de valorisation (P2-02) — quatre demandes du périmètre d'un coup | Décision : à la demande ou en fin de journée par le scheduler |
| **Notion de client sur le deal** | Agrégation par client, risque par client, masquage démo des clients (P2-12) | Décision §7 q.5 ; migration de schéma |
| **Asynchronisation `shock-global` / `pnl-explain-global`** | Utilisation sur book réaliste (P2-10) | `ComputeBatch` existe déjà (VaR) — c'est un portage, pas une conception |
| **Cycle de vie d'un deal résolu** : annulation, archivage, filtre par défaut | Mémoire du book, sortie propre d'un booking erroné (P2-12) | Décision §7 q.5 |
| **Tests frontend (Vitest)** | P1-04 et toute la couche présentation, aujourd'hui non testée | Introduction de l'outillage |

### Stratégie anti-régression

1. **Avant tout correctif touchant la valorisation** (P1-01, P2-04), exécuter les requêtes
   de recensement du §7 q.1 : on doit savoir combien de deals réels changent de prix.
2. **Figer une photo de référence** : lancer `POST /{id}/mtm` et `/greeks` sur chaque deal
   actif et archiver les résultats en JSON dans le scratchpad **avant** le lot. Après, les
   rejouer et n'expliquer que les écarts attendus. Le seed fixe (`seed=42`) rend cette
   comparaison exacte au bit près : c'est l'atout majeur du dépôt et il faut s'en servir.
3. **Le test de bout en bout (#4) avant les chantiers structurels**, pas après — c'est le
   filet qui manque.
4. **Un lot, une nature** : ne pas mêler correctifs de valorisation (les prix bougent) et
   correctifs de périmètre (la population bouge) dans le même déploiement. Les deux
   déplacent les mêmes chiffres à l'écran, et on ne saurait plus lequel a fait quoi.
5. Après chaque lot, `pytest backend/tests` **complet** — c'est un cas explicitement prévu
   par `CLAUDE.md` (changement transversal touchant le moteur partagé et le lifecycle).

---

## 7. Décisions qui te reviennent avant toute implémentation

**1. Requêtes de recensement — à lancer avant tout le reste.** Trois chiffres conditionnent
la sévérité réelle de P1-01, P2-04 et P1-06 sur *tes* données. Je ne les ai pas exécutées
(la base n'a jamais été ouverte) :

```sql
SELECT reference, maturity_date FROM deals
 WHERE json_extract(market_snapshot_json, '$.r') = 0;

SELECT reference FROM deals
 WHERE json_array_length(underlyings_json) > 1
   AND json_extract(market_snapshot_json, '$.corrMatrix') IS NULL;

SELECT reference, status, maturity_date, fixing_policy FROM deals
 WHERE fixing_policy = 'FOUR_EYES' OR (status = 'actif' AND maturity_date < date('now'));
```

Veux-tu que je les lance en lecture seule, ou préfères-tu les passer toi-même ?

**2. Deals UAT — quel comportement par défaut ?** Exclusion par défaut avec
`include_uat=true` en option (ma recommandation), ou simple badge visuel sans changer les
agrégats ? L'exclusion est la bonne réponse en risque, mais si tu peuples aujourd'hui tes
écrans de démonstration avec des lots UAT, elle les videra.

**3. FOUR_EYES sur installation mono-compte.** Griser l'option au booking tant que les
rôles n'existent pas (empêche de créer le problème), ou permettre le basculement gouverné
`FOUR_EYES → AUTO_YAHOO` via le workflow d'amendement (répare l'existant) ? Les deux sont
compatibles — question de priorité, et il faut d'abord savoir si des deals sont déjà
bloqués (requête 3 ci-dessus).

**4. Périmètre du rôle admin.** Aujourd'hui il lit tous les deals de tous les utilisateurs
(`list_deals`, `get_deal`, `watchlist`, alertes) mais aucun agrégat de risque, et sa lecture
n'est jamais tracée. Deux cohérences possibles : admin = **exploitant technique** (ne voit
que ses propres deals métier, garde ses pouvoirs d'administration), ou admin =
**superviseur** (voit tout, y compris les agrégats, avec journalisation de ses lectures).
La deuxième est plus lourde à implémenter mais correspond mieux à un desk.

**5. Modèle de données — client, annulation, archivage.** Trois demandes de ton périmètre
n'ont aucun support. Le **client** est la plus structurante : sans lui, « portefeuille par
client », « risque par client » et « masquage des clients en démo » restent hors d'atteinte.
Est-ce un champ libre sur le deal (comme `contrepartie`), une table `Client` avec catalogue
Admin, ou l'`Entity` existante détournée ? Et faut-il un statut `annulé` distinct de
`résilié` (qui existe dans le modèle mais n'est posé nulle part) ?

**6. Conventions d'unités des Greeks.** Trois échelles cohabitent dans le même tableau
(par 100 %, par 1 pt, par jour). Chacune est documentée par infobulle, donc rien n'est faux.
Uniformiser « tout par 1 point » serait plus lisible mais déplacerait tous les chiffres
affichés d'un facteur 100 sur delta/gamma/vega. À trancher — je ne le ferais pas sans ton
accord explicite.

**7. Priorité du chantier `deal_valuations`.** C'est le seul chantier de ce rapport qui
débloque quatre demandes du périmètre à lui seul (MtM total, P&L latent, P&L journalier,
historique). Il est identifié comme manquant depuis le 17 juillet
(`DEAL_LIFECYCLE_2026-07.md` §3) et ne l'est toujours pas. Le monter avant ou après le
sprint 1 ?

---

*Aucun code n'a été modifié, aucun commit ni push effectué, la base de données n'a jamais
été ouverte. Les sondes vivent dans le scratchpad de session, hors dépôt.*
