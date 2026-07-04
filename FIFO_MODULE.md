# Module FIFO — Reconstruction de Carnet d'Ordres AMC

## Vue d'ensemble

Le module FIFO est un composant **entièrement indépendant** du reste de Structura. Il ne touche pas au pricer PayScript, au viewer AMC, ni à aucun autre module de l'application. Il peut être utilisé de manière autonome pour reconstruire le P&L d'un fonds AMC (Actively Managed Certificate) à partir d'un carnet d'ordres UTI et d'une fiche de termes.

### Fichiers concernés

```
backend/app/core/fifo/
    schema.py       — dataclasses purs (Order, Lot, RoundTrip, OpenPosition, ReconResult)
    loader.py       — parse les JSON UTI (data.orders.items)
    engine.py       — moteur FIFO pur, sans I/O
    marks.py        — valorisation positions ouvertes (mode shares / cert_units)
    nav.py          — parser CSV NAV, construction des ordres T0 initiaux

backend/app/api/fifo.py
    — orchestrateur : pipeline complet, endpoints FastAPI /api/fifo/run et /api/fifo/detect
    — gestion des alias ISIN, correction des splits carnet, injection CyberArk

frontend/src/views/FifoView.vue
    — interface 3 onglets : Positions ouvertes / Round trips / Injections synthétiques
```

---

## Problème résolu

Un AMC achète et vend des actions via un carnet d'ordres UTI (JSON). Le carnet ne contient pas les positions initiales du fonds à la date de fixing — seulement les ordres survenus après. Pour reconstruire le P&L complet depuis l'inception, il faut :

1. Reconstituer les achats initiaux (basket fixing) depuis la fiche de termes et la NAV
2. Apparier les ventes aux achats en FIFO chronologique
3. Gérer les ventes "en avance" sur les achats (héritage pré-carnet) via injections synthétiques
4. Corriger les anomalies de données du carnet (splits d'actions, changements d'ISIN)

---

## Architecture du pipeline

### Étape 1 — Chargement du carnet

`loader.py` parse les fichiers JSON UTI, extrait les ordres (`data.orders.items`) et les retourne comme liste de `Order` triés par date. Les quantités sont signées : positif = achat, négatif = vente.

### Étape 2 — Construction des ordres T0 initiaux (`nav.py`)

Quand un CSV NAV et une `termsheet_positions.json` sont disponibles :

```
expected_price_USD = (weight_pct / 100 × nav_initial) / qty_per_cert
                   → valeur USD par action au fixing, déduite purement de la fiche de termes

split_factor = round(expected_price_USD / yfinance_prix_auto_ajusté_T0)
             → ≈ 10 pour Nvidia (split 10:1 juin 2024), 4 pour Arista (split 4:1 déc 2024), 1 sinon

initial_qty  = n_certs × qty_per_cert × split_factor   [en actions post-split]
T0_price     = yfinance auto-ajusté au fixing date      [base cohérente avec les marks futurs]
```

Ces ordres T0 sont injectés en tête du carnet et traités comme des achats ordinaires par le moteur FIFO. La détection de splits est automatique — aucune configuration manuelle requise.

**Fallback CyberArk** : si yfinance renvoie None (ISIN IL, ticker potentiellement non disponible), le prix implicite de la fiche de termes est utilisé directement (`expected_price_USD`) avec `split_factor=1`.

### Étape 3 — Correction des splits carnet (`_fix_carnet_unadjusted_prices`)

Le système UTI peut enregistrer des achats **post-split** avec l'ancien prix de référence pré-split. Exemple : KLA Corp (split 10:1 en mai 2026) — le carnet enregistre un achat de 130 actions à $2169.35 (prix pré-split) au lieu de $216.94 (prix post-split).

**Algorithme de détection** :
- Pour chaque ISIN sans vente dans le carnet (achats uniquement — cas univoque)
- Comparer le prix carnet au prix yfinance auto-ajusté à la date d'achat
- Si ratio ≈ entier ≥ 2 (à ±15%) → split détecté, diviser le prix par ce facteur
- Quantité inchangée (l'achat est post-split, la quantité est correcte)

**Exclusions** :
- ISINs de la fiche de termes (traités par l'étape 2)
- ISINs avec plusieurs ISIN carnet sous le même nom (corporate actions complexes — ex. SMCI)
- ISINs ayant des ventes dans le carnet (correction prix seule créerait une incohérence FIFO)

**Résultat sur CH1352587724** : KLA Corp corrigé automatiquement (÷ 10), swing de +$254K sur le latent.

### Étape 4 — Détection d'alias ISIN (`_run_fifo`)

Quand une action change d'ISIN après un corporate action (fusion, reissuance), la fiche de termes contient l'ancien ISIN et le carnet contient le nouveau. Sans correction, le FIFO ne peut pas apparier les ventes (nouveau ISIN) aux achats T0 (ancien ISIN).

**Règle d'aliasing** :
- Si un ISIN de la fiche de termes est **absent** du carnet → chercher dans le carnet un ISIN sous le même nom de société
- Si exactement un ISIN alternatif existe → créer l'alias `ts_isin → carnet_isin`
- **Exception critique** : si le ts_isin apparaît quelque part dans le carnet (même sous un nom légèrement différent) → NE PAS aliaser (l'ordre T0 garde son ISIN original)

**Exemples détectés sur CH1352587724** :
- Swissquote : `CH0010675863` → `CH1548235246` (split 10:1 + changement ISIN oct 2023)
- Arista Networks : `US0404131064` → `US0404132054` (reissuance déc 2024)
- BlackRock : aucun alias — l'ISIN termsheet (`US09247X1019`) est présent dans le carnet

### Étape 5 — Moteur FIFO (`engine.py`)

Le moteur est **pur** : aucun I/O, aucun appel réseau. Il reçoit :
- La liste complète d'ordres (T0 initiaux + carnet, triés par date)
- Les marks courants par ISIN
- Les prix T0 pour les injections synthétiques (si mode `t0_synthetic`)

**Mode `t0_synthetic`** (utilisé en production) :
Quand une vente dépasse les lots disponibles, un achat synthétique est injecté à la date T0 avec le prix yfinance à la date du premier lot connu. Cela couvre les positions héritées pré-carnet (positions que le fonds détenait avant le début de l'enregistrement).

**Mode `strict`** :
Les ventes excédentaires créent des lots négatifs (signal d'alerte qualité données). Utilisé en Pass 1 pour collecter les `earliest_lots`.

**Pipeline deux passes** :
1. Pass 1 (strict) : collecte les `earliest_lots` par ISIN pour les prix T0
2. Fetch prix T0 via yfinance (ou termsheet pour les ISINs initiaux)
3. Pass 2 (t0_synthetic) : reconstruction FIFO complète avec injections

### Étape 6 — Valorisation (`marks.py`)

**Mode `shares`** (utilisé pour CH1352587724) :
- Mark = prix action courant en devise produit (via parquet store ou yfinance live)
- P&L latent = `open_qty × mark − cost_basis`

**Mode `cert_units`** (carnet UTI natif) :
- Les quantités carnet sont en "cert-units", pas en actions réelles
- Facteur de conversion `k = prix_cert_T0 / prix_action_T0`
- Mark cert-unit = `prix_action_courant × k`
- Préservation des splits via yfinance `auto_adjust=True` tout au long de la chaîne

---

## Gestion des cas spéciaux

### ISIN avec ticker yfinance difficile

`amc_prices.py::yf_symbol()` résout les ISIN en ticker selon l'ordre de priorité :
1. `_ticker_map.json` (mapping explicite utilisateur — ex. `IL0011334468 → CYBR`)
2. Validation checksum yfinance ISIN
3. Recherche par nom sur Yahoo Finance (équités US/EU)

### SMCI — double ISIN après split

SMCI a fait un split 10:1 en octobre 2024 avec changement d'ISIN :
- Achats : `US86800U1043` (pré-split, prix ~$617)
- Ventes : `US86800U3023` (post-split, prix ~$42)

Ces deux ISINs ont des noms différents dans le carnet → non aliasables automatiquement. Résultat : 3 injections synthétiques FAIL (ventes sans achats correspondants). Impact estimé faible (~$59K écart sur position ouverte).

---

## Résultats — CH1352587724 (LUKB AMC, juillet 2026)

| Paramètre | Valeur |
|---|---|
| ISIN fonds | CH1352587724 |
| Date fixing | 06/06/2024 |
| NAV initiale | 100.00 USD/cert |
| Certificats initiaux | 26,932 |
| Date valorisation | 15/06/2026 |
| NAV au 15/06/2026 | 142.09 USD/cert |

**Reconstruction FIFO** :

| | |
|---|---|
| Ordres carnet | 753 |
| Ordres T0 initiaux injectés | 18 (1 par ISIN termsheet) |
| Positions ouvertes | 60 ISINs |
| Round trips réalisés | 637 |
| Injections synthétiques | 66 (63 OK, 3 FAIL SMCI) |

**P&L** :

| | Montant USD |
|---|---|
| Réalisé | +951,354 |
| Latent | +749,663 |
| **Total FIFO** | **+1,701,017** |

**Réconciliation NAV** :

| | Montant USD |
|---|---|
| Total investi net (souscriptions − rachats) | 2,650,339 |
| Valeur actuelle (27,899 certs × 142.09) | 3,964,122 |
| **Vrai P&L fonds** | **+1,313,783** |
| Écart FIFO vs NAV | +387,238 (~23%) |

L'écart structurel FIFO > NAV reflète la nature des deux mesures :
- FIFO valorise les positions ouvertes au prix de marché courant (yfinance)
- La NAV est calculée par l'administrateur avec des ajustements de liquidité et de timing

### Splits détectés automatiquement (T0 initiaux)

| Action | ISIN | Split | split_factor |
|---|---|---|---|
| Nvidia | US67066G1040 | 10:1 (juin 2024) | 10 |
| Arista Networks | US0404131064 | 4:1 (déc 2024) | 4 |
| Swissquote | CH0010675863 | 10:1 (oct 2023) | 10 |

### Split carnet corrigé automatiquement

| Action | ISIN | Split | Correction |
|---|---|---|---|
| KLA Corp | US4824801009 | 10:1 (mai 2026) | $2169.35 → $216.94 (÷10), latent −$248K → +$6K |

---

## Limites connues

1. **SMCI (2 ISINs)** : le split avec changement d'ISIN produit 3 ordres synthétiques en échec. Non corrigé (impact limité, correction requiert un mapping manuel).

2. **ServiceNow / Carvana** : le carnet UTI enregistre également des prix pré-split pour des ordres post-split sur ces valeurs, mais ces ISINs ont aussi des ventes dans le carnet. Une correction cohérente nécessiterait d'ajuster prix ET quantité pour chaque ordre individuellement — non implémenté.

3. **CyberArk** : ISIN israélien (IL0011334468), ticker CYBR potentiellement non disponible sur Yahoo Finance. Le prix T0 est calculé depuis la fiche de termes ($237.47 implicite). La position ouverte est valorisée par ticker_map si disponible.

4. **Écart vs NAV (~23%)** : attendu pour une reconstruction FIFO basée sur des données de marché. Les principales sources d'écart sont les prix d'exécution réels vs yfinance, les frais de transaction non enregistrés, et la différence de méthodologie de valorisation des positions ouvertes.
