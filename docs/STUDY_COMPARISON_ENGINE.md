# Study Comparison Engine — Feuille de Route

> **Statut :** Idée validée — implémentation différée (pas de code, sur demande explicite)
> **Priorité :** Haute — motivée par deux cas réels rencontrés en session (voir §Motivation)
> **Prérequis :** Études sauvegardées (existant — `GET /api/amc/studies`, multi-versions par ISIN)

---

## Objectif

Comparer deux études du **même AMC** — typiquement une étude sauvegardée (déjà envoyée à un
client) et une étude fraîchement relancée — pour comprendre **pourquoi** les chiffres ont changé,
sans avoir à ré-enquêter manuellement à chaque écart.

> *"Ce chiffre a changé depuis la dernière fois — est-ce nouveau trading, un changement de méthode,
> ou un paramètre différent ?"*

---

## Motivation (deux cas vécus dans la même session)

1. **P&L FIFO CH1352587724** : le rapport envoyé au client montrait +1.60M USD (écart NAV -3.2%).
   Une étude relancée montre +1.94M USD (écart NAV +23%). Cause réelle : la correction de splits
   boursiers (ServiceNow, Carvana) est désormais complète — l'ancien chiffre reposait sur un vrai
   bug (positions impossibles, masquées par des injections synthétiques). Il a fallu ~2h
   d'investigation manuelle (comparaison des deux captures, recherche web indépendante des dates de
   split, isolation de la contribution par titre) pour trancher.

2. **Matrice conviction × résultat, même AMC** : 15/37/3/39 positions par quadrant dans le rapport
   envoyé → 43/10/33/8 dans une étude relancée. Cause réelle : un bug de classification
   (`weight_pct > 0` empêchait toute position clôturée d'être classée "forte conviction"). Vérifié
   en un coup d'œil car le total (94) était identique des deux côtés — mais seulement parce que
   l'utilisateur a pensé à le vérifier lui-même.

Dans les deux cas, l'écart était **réel et important**, la cause était **un bug déjà identifié et
corrigé dans la session**, et la seule façon de le confirmer a été une investigation manuelle
ad hoc. Un outil de comparaison structuré aurait rendu ce diagnostic immédiat.

---

## Principe de conception : pas un diff JSON générique

Un diff générique du JSON complet de `run_study()` serait bruyant et peu actionnable : la moitié
des champs sont du texte d'interprétation généré (change de formulation sans rien dire
d'important), des identifiants d'ordre, des dates de calcul, etc.

**Approche retenue** : un **tableau de métriques clés côte à côte, curé bloc par bloc** — les
chiffres qui comptent réellement pour un structureur (P&L, scores, comptes de quadrants, alpha/R²),
pas une réflexion automatique sur toute la structure du JSON.

---

## Classification automatique de la cause d'écart

C'est le cœur de la valeur ajoutée de l'outil : ne pas se contenter d'afficher un delta, mais
**expliquer pourquoi** il existe, en trois catégories mutuellement exclusives :

| Catégorie | Condition de détection | Interprétation |
|---|---|---|
| **Nouvelles données** | `meta.as_of` diffère entre les deux études | Écart attendu — nouveau trading depuis la dernière étude. Pas la peine d'investiguer plus loin. |
| **Changement de méthode/code** | `meta.as_of` **identique**, mais métriques différentes | Signal le plus important — quelque chose a changé dans le calcul entre les deux runs (bug fix, refactor). À investiguer/expliquer en priorité. |
| **Paramètres différents** | `meta` diffère sur benchmark_ticker / management_fee_pct / recon_mode / factor_model / ff_series / blocks activés | Explique l'écart sans qu'il y ait de bug — à afficher clairement, pas comme une anomalie. |

Ces trois catégories ne sont pas exclusives dans les faits (un `as_of` différent ET des paramètres
différents peuvent coexister) — l'outil doit les signaler toutes, mais **mettre en avant** le cas
"même `as_of`, chiffres différents" car c'est le seul qui appelle une vraie explication.

---

## Métriques comparées par bloc

| Bloc | Métriques clés à juxtaposer |
|---|---|
| Meta | `as_of`, `nav_start_date`, `nav_current_date`, `n_orders`, paramètres manifest (benchmark, frais, recon_mode, factor_model, ff_series, qty_mode) |
| A — Factoriel | `alpha_ann_pct`, `alpha_tstat`, `r2`, betas par facteur (net et brut) |
| B — Attribution | `total_pnl`, `realized_pnl`, `unreal_pnl`, top5/flop5 (par nom, pas juste le total) |
| C — Trading | `turnover_annualized`, `win_rate_pct`, `profit_factor`, `count` round trips |
| D — Conviction | comptes des 4 quadrants (`conviction_winners`, `tactical_winners`, `stubborn_losers`, `uncertainty`) + P&L par quadrant — **le total des 4 comptes doit être vérifié identique entre les deux études** (sinon la comparaison elle-même est invalide, cf. §Garde-fous) |
| E — Référentiel Inertiel | `bh_perf_pct`, `actual_perf_pct`, `value_added_pct` |
| F — Réplicabilité | `score`, `r2_pct`, `alpha_gap_pct` |
| G — Brinson (si calculé dans les deux) | `active_return_pct`, `allocation_pct`, `selection_pct`, `interaction_pct` |
| H — Timing | `global_score_mean`, `coverage_pct`, `n_trades_analyzed` |
| I — Stock Picking | `score`, `global_alpha_mean`, `coverage_pct` |
| J — Risk Management | `score`, 5 sous-scores |
| K — Chocs de Marché | `n_events_applicable`, activité/flux net par événement |
| Manager Skill Score | `score` global + score par dimension |

---

## Garde-fous

- **Vérifier la comparabilité avant de comparer** : si les deux études n'ont pas le même
  `product.isin`, avertir clairement plutôt que d'afficher un tableau trompeur.
- **Totaux de contrôle** : pour les blocs à comptage (D — quadrants, B — nombre de titres), vérifier
  que les totaux concordent entre les deux études quand le `as_of` est identique — si le total
  diffère (nouveaux titres tradés), le signaler distinctement d'un simple changement de
  classification (exactement la vérification manuelle faite pour le cas conviction ci-dessus,
  automatisée).
- **Ne pas figer un diff comme "anomalie" sans contexte** : toujours accompagner un delta de sa
  catégorie (nouvelles données / méthode / paramètres) plutôt que de le colorer en rouge par défaut.

---

## Intégration Structura prévue

```
Frontend (AmcView.vue ou nouvelle vue)
  └── Dans la liste des études sauvegardées (déjà existante) :
        ├── Sélection de 2 études à comparer (checkbox ou "Comparer à…")
        └── Bouton "Comparer"

Backend
  └── backend/app/core/amc_compare.py
        └── compare_studies(study_a: dict, study_b: dict) -> dict
              ├── détecte la catégorie d'écart (as_of / méthode / paramètres)
              ├── extrait les métriques curées par bloc (tableau ci-dessus)
              └── retourne { comparability_warning, category, rows_by_block }

  └── backend/app/api/amc.py
        └── POST /api/amc/study/compare   { study_a_id, study_b_id } ou { study_a: dict, study_b: dict }

Frontend
  └── Nouvel onglet ou modal "Comparaison"
        ├── Bandeau catégorie d'écart (nouvelles données / méthode / paramètres)
        ├── Tableau par bloc : métrique | étude A | étude B | delta
        └── Highlight des deltas significatifs (seuil à définir par métrique)
```

---

## Points ouverts (à trancher avant implémentation)

- Comparer seulement 2 études à la fois, ou permettre une liste (historique dans le temps) ?
- Seuils de "delta significatif" par métrique — fixes ou proportionnels à la métrique elle-même ?
- Faut-il aussi comparer au niveau *ordre* (un ordre présent dans B mais pas dans A = nouveau
  trading) plutôt que seulement au niveau des métriques agrégées ?

---

*Créé le 2026-07-16, suite à la demande explicite de comparaison d'études et aux deux cas réels
rencontrés en session (P&L CH1352587724, matrice conviction CH1352587724).*
