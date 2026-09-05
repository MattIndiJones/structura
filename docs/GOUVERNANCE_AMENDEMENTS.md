# Amendement d'un deal booké — mécanisme et gouvernance

**Statut** : mécanisme complet et testé. La **deuxième signature est désactivée par
défaut** depuis le 07/08/2026 (poste mono-opérateur, outil tactique). Tout le reste du
dispositif est actif et inconditionnel.

Ce document existe pour une raison précise : le contrôle à quatre yeux n'a pas été
supprimé, il a été **désarmé**. Il doit rester réarmable sans archéologie le jour où le
desk se dédouble.

---

## 1. Ce que le mécanisme permet — et ce qu'il ne permet pas

Un deal booké est immuable par construction : `PATCH /api/deals/{id}` est une frontière
de refus qui audite toute tentative et renvoie 409 (`POST_BOOKING_IMMUTABLE`), et la
table `deals` n'a **aucun** `editable_fields` dans `core/admin_registry.py` — un
administrateur ne peut pas la corriger davantage. L'amendement gouverné est donc le
**seul** chemin de correction d'un trade.

Il ne couvre que quatre champs (`api/deals.py:_IN_PLACE_AMENDMENT_FIELDS`) :

| Champ | Contrôle de valeur |
|---|---|
| `nominal` | numérique, strictement positif |
| `price_traded` | numérique, strictement positif |
| `contrepartie` | chaîne non vide |
| `payment_date` | date ISO, jamais antérieure à la maturité |

Tout le reste — `script_snapshot`, `market_snapshot`, `devise`, `trade_date`,
`strike_date`, `value_date`, `maturity_date`, `status` — est refusé avec
`AMENDMENT_REBOOK_REQUIRED` : « ce changement affecte le contrat, le pricing ou le
calendrier, il doit être traité par annulation/remplacement contrôlé ».

> ⚠ **Ce mécanisme d'annulation/remplacement n'existe pas.** Aucun endpoint ne pose le
> statut `résilié`, et il n'y a pas de flux « re-booker depuis ce deal ». Un deal booké
> avec un mauvais script, de mauvaises dates ou un mauvais snapshot marché n'a donc
> **aucun** chemin de correction — quelle que soit la politique de signature.
> C'est un manque connu, pas une conséquence du désarmement ; voir
> `AUDIT_FRONT_TO_RISK_2026-08-07.md` §7.

## 2. Machine à états

```
                    request_amendment          approve_amendment
   (rien)  ──────────────────────────▶ PENDING ──────────────────▶ APPROVED
                 propriétaire du deal      │                           │
                 motif ≥ 10 caractères     │ reject_amendment          │ apply_amendment
                 valeur ≠ valeur bookée    ▼                           ▼
                 pas de demande active   REJECTED                   APPLIED
                 sur le même champ                            (deal muté, contract_version++,
                                                               DealContractVersion figée)
```

## 3. Garanties inconditionnelles

Elles ne dépendent **pas** de la politique de signature et ne doivent jamais en dépendre :

- **Motif obligatoire** — 10 caractères minimum à la demande comme à la décision.
- **Versionnement contractuel** — `Deal.contract_version` est monotone. Chaque
  application fige un `DealContractVersion` (snapshot immuable, `dedup_key` UNIQUE).
- **Refus sur base périmée** — `AMENDMENT_VERSION_STALE` si le contrat a bougé depuis
  l'approbation, `AMENDMENT_BASE_VALUE_CHANGED` si la valeur de départ n'est plus celle
  de la demande. Une demande concurrente ne peut pas écraser un état plus récent.
- **Application exactement une fois** — seule une demande `APPROVED` s'applique ; une
  seconde tentative renvoie `AMENDMENT_STATUS_INVALID`.
- **Pas de demande en double** — une seule demande active (`PENDING`/`APPROVED`) par
  champ et par deal.
- **Piste d'audit append-only** — `AMENDMENT_REQUESTED`, `AMENDMENT_APPROVED`,
  `AMENDMENT_REJECTED`, `AMENDMENT_APPLIED`, plus les refus
  (`AMENDMENT_*_REJECTED`), avec acteur, motif, avant/après.
- **Frontière de propriété** — un utilisateur d'une autre entité reste refusé en 404,
  en mode signature simple comme en mode quatre yeux.

## 4. Ce que le drapeau gouverne — et rien d'autre

`core/workflow.py:amendment_four_eyes_enabled()`, lu à **chaque appel** (jamais figé
dans une constante de module, pour qu'un déploiement ou un test puisse le basculer sans
surprise d'ordre d'import).

| | Désarmé (défaut) | Armé |
|---|---|---|
| Qui approuve et applique | quiconque a accès au deal — son propriétaire compris | rôle `checker` ou `admin` **uniquement** |
| Le demandeur peut-il décider ? | **oui** | non → 409 `FOUR_EYES_VIOLATION` + `AMENDMENT_FOUR_EYES_REJECTED` en audit |
| Portée entité | inchangée | inchangée |
| Tout le §3 | inchangé | inchangé |

**Pourquoi désarmé.** Sur une installation à un seul compte, la séparation des tâches
n'a personne à séparer : le propriétaire ouvrait une demande que personne ne pouvait
jamais clore. Le seul chemin de correction d'un trade devenait une impasse.

### Réarmer

```bash
STRUCTURA_AMENDMENT_FOUR_EYES=1
```

Valeurs acceptées : `1`, `true`, `yes`, `on` (insensible à la casse). Toute autre valeur,
ou l'absence de variable, laisse le contrôle désarmé. Le frontend s'aligne seul : la
politique est remontée par `GET /api/auth/me` (`amendment_four_eyes`), et
`EventsTab.vue` en dérive les libellés et l'affichage des boutons Approuver / Rejeter /
Appliquer.

**Prérequis avant de réarmer** : au moins un utilisateur de rôle `checker` dans l'entité
du deal, **distinct** de son propriétaire (Administration → Utilisateurs). Sans cela, le
mode armé reproduit exactement l'impasse qu'il a fallu lever.

## 5. Tests

`backend/tests/test_workflow_phase2.py` couvre les deux modes, délibérément :

| Test | Mode |
|---|---|
| `test_amendment_is_carried_through_by_its_own_maker_by_default` | désarmé — le maker ouvre, approuve, applique ; version 2, rejeu refusé, audit écrit |
| `test_single_signature_mode_still_refuses_a_foreign_user` | désarmé — la frontière d'entité tient toujours |
| `test_amendment_requires_four_eyes_and_applies_exactly_once` | **armé** via la fixture `four_eyes_armed` |
| `test_amendment_checker_is_entity_scoped` | portée entité |
| `test_pricing_or_calendar_amendment_requires_rebooking` | champs hors périmètre |

La fixture `four_eyes_armed` est ce qui empêche le mode armé de pourrir en silence : sans
elle, un contrôle désactivé cesse d'être testé et n'est plus réarmable de confiance.

## 6. Distinguer des deux autres « quatre yeux »

Le nom est employé pour trois dispositifs indépendants. **Seul le premier a été
désarmé** :

| Dispositif | Où | Statut |
|---|---|---|
| Amendement d'un deal booké | `_checker_request` | **désarmé par défaut** (ce document) |
| Fixing officiel `FOUR_EYES` | `Deal.fixing_policy`, `_ops_deal` | intact — exige `ops_maker` **et** `checker`, tous deux distincts du propriétaire |
| Validation d'une proposition lifecycle | `_owned_proposal` | intact — exige `checker` distinct du propriétaire |

Les deux derniers restent bloquants sur une installation mono-compte : un deal booké en
`FOUR_EYES` ne peut y être résolu (`AUDIT_FRONT_TO_RISK_2026-08-07.md` P1-06). La
politique par défaut, `AUTO_YAHOO`, se dénoue seule et n'est pas concernée.
