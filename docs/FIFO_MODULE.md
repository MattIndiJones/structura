# Module FIFO — Reconstruction de Carnet d'Ordres AMC

> Pour l'historique des bugs rencontrés et corrigés en construisant ce module (fausses pistes,
> pièges d'environnement, mécanique de frais...), voir `PORTFOLIO_RECONCILIATION_LESSONS.md`.

## Vue d'ensemble

Le module FIFO reconstruit le P&L d'un fonds AMC (Actively Managed Certificate) à partir d'un
carnet d'ordres UTI et d'une fiche de termes. Il alimente deux points d'entrée qui partagent
**une seule et même implémentation** (`core/fifo/pipeline.py::run_fifo_recon()`) :

- l'onglet FIFO dédié (`FifoView.vue` + `api/fifo.py`, choix manuel du mode quantité)
- l'étude AMC (`amc_study.py`, toujours en mode "actions" — voir §Mode quantité ci-dessous)

### Fichiers concernés

```
backend/app/core/fifo/
    schema.py       — dataclasses purs (Order, Lot, RoundTrip, OpenPosition, ReconResult)
    loader.py       — parse les JSON UTI (data.orders.items)
    engine.py       — moteur FIFO pur, sans I/O
    marks.py        — valorisation positions ouvertes (mode shares / cert_units)
    nav.py          — parser CSV NAV, construction des ordres T0 initiaux
    pipeline.py      — orchestrateur unique (détection alias, correction de splits, 2 passes FIFO)

backend/app/api/fifo.py
    — fine couche REST : délègue entièrement à pipeline.run_fifo_recon(), reshape en JSON

backend/app/core/amc_fifo_adapter.py
    — convertit un ReconResult du pipeline vers le format legacy attendu par amc_blocks.py (Bloc B/C/D)

backend/app/core/amc_study.py
    — étude AMC : appelle run_fifo_recon() en mode "actions", branche le Bloc B sur la
      réconciliation NAV (frais gestion + performance + transaction)

frontend/src/views/FifoView.vue
    — interface 3 onglets : Positions ouvertes / Round trips / Injections synthétiques
```

---

## Problème résolu

Un AMC achète et vend des actions via un carnet d'ordres UTI (JSON). Le carnet ne contient pas les
positions initiales du fonds à la date de fixing — seulement les ordres survenus après. Pour
reconstruire le P&L complet depuis l'inception, il faut :

1. Reconstituer les achats initiaux (basket fixing) depuis la fiche de termes et la NAV
2. Apparier les ventes aux achats en FIFO chronologique
3. Gérer les ventes "en avance" sur les achats (héritage pré-carnet) via injections synthétiques
4. Corriger les anomalies de données du carnet (splits d'actions réels non reflétés dans les prix
   enregistrés, changements d'ISIN)
5. Rapprocher le P&L FIFO (brut de frais) de la NAV publiée (nette de frais) pour valider le résultat

---

## Mode quantité : "actions" toujours, pas d'unité de compte

Une termsheet peut exprimer ses quantités (`qty_per_cert`) en unités de compte plutôt qu'en actions
réelles. Ça n'a **pas d'importance** : la formule du panier T0 —

```
initial_qty = n_certs × (poids% × NAV_initiale) / cours_réel_action_au_fixing
```

— fait que `qty_per_cert` s'annule algébriquement. Le résultat ne dépend que du poids%, de la NAV
et du cours réel, tous fiables, quelle que soit l'unité choisie par la termsheet pour
`qty_per_cert`. Le mode `qty_mode="cert_units"` (facteurs d'échelle, marks dédiés) reste disponible
dans le moteur et l'onglet FIFO autonome pour le jour où un carnet enregistrerait **lui-même** des
quantités non-actions (jamais observé à ce jour), mais l'étude AMC est toujours forcée en mode
`"shares"` — voir §1 de `PORTFOLIO_RECONCILIATION_LESSONS.md` pour le détail de cette
investigation.

---

## Architecture du pipeline (`run_fifo_recon`)

### Étape 1 — Chargement du carnet

`loader.py` parse les fichiers JSON UTI, extrait les ordres (`data.orders.items`) et les retourne
comme liste de `Order`. Les quantités sont signées : positif = achat, négatif = vente. Les prix
carnet sont **toujours** de vrais prix d'actions, même quand la termsheet/Def.txt sont en unité de
compte.

### Étape 2 — Construction des ordres T0 initiaux (`nav.py::build_initial_orders`)

Quand un CSV NAV et une `termsheet_positions.json` sont disponibles, le panier initial est
injecté en tête du carnet et traité comme des achats ordinaires par le moteur FIFO (voir formule
ci-dessus). Le split_factor implicite (`expected_price_USD / yfinance_prix_auto_ajusté_T0`) gère
automatiquement les corporate actions survenues entre la fiche de termes et aujourd'hui — aucune
configuration manuelle requise.

**Fallback CyberArk** : si yfinance renvoie None (ISIN IL, ticker potentiellement non disponible),
le prix implicite de la fiche de termes est utilisé directement, `split_factor=1`.

**⚠️ Bug connu, non corrigé** : le lot T0 est construit avec `fx=1.0` et `price_ccy=prod_ccy`,
alors que son `price_local` est en réalité déjà converti en USD par `build_marks()`. Le P&L total
n'est pas affecté (le calcul utilise `price_prod`, correct), mais la décomposition prix/FX affichée
pour tout round-trip impliquant ce lot est fausse pour les positions en devise non-USD (repéré via
un "Part FX" anormalement élevé sur Swissquote/CHF). Voir §8 de `PORTFOLIO_RECONCILIATION_LESSONS.md`.

### Étape 3 — Correction des splits carnet (`pipeline.py::fix_carnet_splits`)

Le carnet peut enregistrer des ordres avec un prix qui ne reflète pas encore un split survenu entre
temps (ex. KLA Corp, split 10:1 en juin 2026 : le carnet montre un achat à $2169.35 au lieu de
$216.94). Deux mécanismes, tous deux pilotés par le **vrai calendrier d'opérations sur titre**
yfinance (`Ticker(x).actions["Stock Splits"]`) — pas une heuristique de ratio de prix :

1. **Réémission double-ISIN** (ex. SMCI, split 10:1 oct. 2024 avec changement d'ISIN) : détection
   des noms partagés par 2+ ISIN avec des plages de dates disjointes dans le carnet ; l'ancien ISIN
   est ré-étiqueté vers le nouveau.
2. **Split par ordre** : pour chaque ordre (après ré-étiquetage), tous les splits réels survenus
   strictement après sa date et jusqu'à `as_of` (date du dernier ordre du carnet — **pas** la date
   du jour réelle) sont multipliés ensemble et appliqués (`qty × facteur`, `prix ÷ facteur`).

Cette méthode corrige aussi bien les ISIN uniques (KLA, ServiceNow, Carvana, Swissquote, Arista)
que les cas mixtes achats+ventes pré/post-split (ServiceNow, Carvana) qu'une simple correction de
prix ne pouvait pas traiter.

**Important** : la borne `as_of` est cruciale — un split survenu *après* la date de référence de
l'étude ne doit pas être appliqué, sous peine d'incohérence avec les marks (eux-mêmes valorisés à
cette même date).

### Étape 4 — Détection d'alias ISIN termsheet

Quand une action change d'ISIN après un corporate action (fusion, reissuance) **entre la fiche de
termes et le carnet** (différent du cas §3, qui concerne un changement *au sein même* du carnet) :

- Si un ISIN de la fiche de termes est **absent** du carnet → chercher un ISIN alternatif sous le
  même nom de société
- Si exactement un ISIN alternatif existe → créer l'alias `ts_isin → carnet_isin`
- **Exception** : si le ts_isin apparaît quelque part dans le carnet → ne pas aliaser

**Exemple** : Swissquote `CH0010675863` (termsheet) → `CH1548235246` (carnet).

### Étape 5 — Moteur FIFO (`engine.py`)

Le moteur est **pur** : aucun I/O, aucun appel réseau.

**Pipeline deux passes** :
1. Pass 1 (`strict`) : collecte les `earliest_lots` par ISIN pour déterminer les prix T0 des
   injections synthétiques
2. Pass 2 (`t0_synthetic`) : reconstruction FIFO complète — toute vente dépassant les lots
   disponibles déclenche un achat synthétique à la date T0, au prix du premier lot connu

### Étape 6 — Valorisation (`marks.py`)

**Mode `shares`** (utilisé pour l'étude AMC) : mark = prix action courant en devise produit (via
parquet store ou yfinance live), `unreal_pnl = open_qty × mark − cost_basis`.

**Mode `cert_units`** (onglet FIFO autonome uniquement, cas non observé à ce jour) : facteur
d'échelle `k = prix_cert_T0 / prix_action_T0` dérivé de la fiche de termes, `mark_cert_unit =
prix_action_courant × k`.

### Étape 7 — Réconciliation NAV (`amc_blocks.py::_nav_reconciliation`, étude AMC uniquement)

Le P&L FIFO est **brut** de frais ; la NAV publiée est **nette**. Pour comparer les deux, trois
composantes de frais sont modélisées séparément (chacune optionnelle, renseignée dans le manifest
`params.management_fee_pct` / `params.perf_fee_pct` / `params.txn_cost_pct`) :

- **Frais de gestion** : accrual quotidien sur l'AUM (`taux_annuel/252`)
- **Frais de performance** : ⚠️ prélevé **quotidiennement**, uniquement les jours où la NAV atteint
  un **nouveau plus haut historique** (High Water Mark) — pas un accrual continu ni un prélèvement
  annuel. `fee_per_unit = gain_net_au-dessus_du_HWM × taux/(100−taux)`, sommé sur chaque jour de
  nouveau plus-haut × unités en circulation ce jour-là.
- **Coût de transaction** : % du notionnel de chaque ordre du carnet (achat et vente), à chaque
  rebalancement — absent des prix d'exécution, c'est un coût structurel séparé.

Le P&L implicite NAV (vérité indépendante) est calculé uniquement depuis la NAV quotidienne et les
flux de souscription/rachat (`Δ Outstanding × NAV` à chaque mouvement) — sans dépendre du carnet.

---

## Gestion des cas spéciaux

### ISIN avec ticker yfinance difficile

`amc_prices.py::yf_symbol()` résout les ISIN en ticker selon l'ordre de priorité :
1. `_ticker_map.json` (mapping explicite — ex. `IL0011334468 → CYBR`, `CH1548235246 → SQN.SW`)
2. Validation checksum yfinance ISIN
3. Recherche par nom sur Yahoo Finance

### Def.txt : le champ `weight` n'est pas fiable

Vérifié par recoupement contre le factsheet officiel de l'émetteur (LUKB) sur CH1352587724 : le
champ `weight` précalculé de Def.txt peut être significativement faux (33.78% affiché pour une
position dont le vrai poids est ~4%), alors que le champ `position` (quantité) est fiable à chaque
vérification. `load_study_data()` recalcule donc `weight`/`value_prod` depuis
`position × mark_courant / AUM_total` plutôt que de faire confiance au fichier.

---

## Résultats — CH1352587724 (LUKB AMC)

> ⚠️ **Les chiffres ci-dessous dérivent, ne pas les traiter comme figés.** `as_of` = dernière date
> du carnet à l'instant du run ; les marks dépendent du prix courant au moment du calcul. Deux runs
> à des dates différentes donneront des chiffres différents **sans que ce soit un bug** — voir
> `docs/STUDY_COMPARISON_ENGINE.md` pour l'outil prévu qui distinguera automatiquement "nouvelles
> données" de "changement de méthode".

| Paramètre | Valeur |
|---|---|
| ISIN fonds | CH1352587724 |
| Date fixing | 06/06/2024 |
| NAV initiale | 100.00 USD/cert |
| Certificats initiaux | 26,932 |

**Reconstruction FIFO validée le 2026-07-16** (mode `"shares"` — confirmé le bon mode : la
term sheet est en unités de compte mais **le carnet d'ordres est en actions réelles**, ce qui
rend `"cert_units"` structurellement incorrect pour ce fonds — voir §Mode quantité ci-dessus) :

| | Montant USD |
|---|---|
| Réalisé | +1,186,705 |
| Latent | +757,036 |
| **Total FIFO (brut)** | **+1,943,741** |

**⚠️ Chiffre antérieur invalidé** : un rapport envoyé au client montrait +1,601,000 (écart NAV
-3.2%, en apparence excellent). Investigation du 2026-07-16 : ce chiffre reposait sur une
correction de split **incomplète** pour ServiceNow et Carvana, qui produisait des positions
ouvertes **négatives** (-854 et -1530 actions — impossible pour un fonds long-only), masquées par
des injections synthétiques à un prix lui-même faussé. Une fois la correction complète appliquée
(voir §Splits ci-dessous), les positions ouvertes redeviennent positives et plausibles (+42 et
+118). Les deux splits ont été confirmés indépendamment (SEC filings + presse financière), pas
seulement via yfinance. Le nouvel écart de +23% vs la NAV implicite est cohérent avec un
phénomène déjà documenté : chaque split réel supplémentaire correctement appliqué **augmente**
l'écart FIFO-vs-NAV plutôt que de le réduire (voir `PORTFOLIO_RECONCILIATION_LESSONS.md` §9),
signe que cet écart est structurel (marks au marché actuel vs NAV lissée) plutôt qu'un bug restant.

### Splits réels détectés et corrigés

| Action | ISIN | Split | Confirmation |
|---|---|---|---|
| Nvidia | US67066G1040 | 10:1 (juin 2024) | yfinance |
| Arista Networks | US0404132054 | 4:1 (déc 2024) | yfinance |
| Swissquote | CH1548235246 | 10:1 (mai 2026) | yfinance |
| KLA Corp | US4824801009 | 10:1 (juin 2026) | yfinance |
| ServiceNow | US81762P1021 | 5:1 (déc 2025) | **yfinance + SEC 8-K + communiqué officiel** (record 16/12/2025, effectif 17/12, trading ajusté dès 18/12) |
| Carvana | US1468691027 | 5:1 (mai 2026) | **yfinance + SEC + Motley Fool** (effectif 07/05/2026, trading ajusté dès 08/05) |
| Super Micro Computer (SMCI) | US86800U1043→US86800U3023 | 10:1 (oct 2024) | yfinance (double-ISIN) |

### Correction de split — désormais aussi appliquée hors du pipeline FIFO (2026-07-16)

`fix_carnet_splits` (ci-dessus) ne corrigeait que les ordres utilisés par les Blocs B/C/D. Les
Blocs H (Timing), I (Stock Picking) et le module VAG Attribution utilisent une source d'ordres
**séparée** (`amc_orderbook.py::load_orders`) qui n'avait **aucune** correction de split — un même
titre splitté y comparait un prix d'exécution brut (pré-split) à un mark courant auto-ajusté
(post-split), un écart pouvant fausser massivement un score de timing ou un alpha de sélection.
Corrigé via `amc_orderbook.py::apply_split_corrections()`, qui réutilise le même calendrier
yfinance partagé (`amc_prices.get_split_calendar()` / `split_factor_between()`) — factorisé pour
que les deux implémentations (FIFO et orderbook) ne divergent plus.

---

## Limites connues

1. **Décomposition prix/FX du lot T0** : voir le bug `fx=1.0` mentionné à l'étape 2 — n'affecte
   pas le P&L total mais fausse la ventilation prix/FX affichée pour les positions non-USD.
   Toujours pas corrigé.

2. **Écart résiduel de +23% vs NAV implicite (CH1352587724, état du 2026-07-16)** : signal
   structurel probable (positions ouvertes marquées au marché actuel vs NAV lissée par
   l'émetteur), pas un bug identifié restant — mais non prouvé formellement. Chaque correction de
   split supplémentaire a *augmenté* cet écart plutôt que de le réduire, ce qui va dans le sens
   d'un phénomène réel plutôt que d'une erreur résiduelle qui se compenserait par hasard.

3. **Autres AMC non testés** : cette réconciliation complète (splits réels + 3 composantes de
   frais) n'a été validée en détail que sur CH1352587724. Un nouveau fonds peut révéler d'autres
   cas (ISIN dupliqués supplémentaires, mécanique de frais différente) — voir
   `PORTFOLIO_RECONCILIATION_LESSONS.md` pour la méthode et les pièges à éviter.
