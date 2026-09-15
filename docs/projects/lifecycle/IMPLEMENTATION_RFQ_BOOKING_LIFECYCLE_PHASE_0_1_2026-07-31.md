# Rapport de mise en œuvre — sécurisation RFQ → pricing → booking → lifecycle

Date : 31 juillet 2026
Branche de travail : `feat/client-test-agent`
Base de départ : `fa72043`
Périmètre : RFQ, intégrité du pricing utilisé au booking, booking, fixings et lifecycle
Hors périmètre : AMC, refonte générale du moteur de pricing, moteur complet d’amendement maker-checker

## 1. Conclusion exécutive

> Mise à jour : les priorités de rejeu officiel, sémantique KI/final,
> amendement maker-checker et consultation de l’audit ont été traitées dans
> `IMPLEMENTATION_RFQ_BOOKING_LIFECYCLE_PHASE_2_2026-07-31.md`. Les limites
> décrites en section 10 restent l’état de la phase 0/1, pas l’état courant.

La tranche Phase 0 + fondations Phase 1 est mise en œuvre.

La chaîne ne repose plus sur la seule cohérence de l’interface : les contrôles critiques sont exécutés côté domaine/backend, les refus sont explicites et persistés, et les décisions lifecycle terminales ne peuvent plus être appliquées à partir de données Yahoo.

Les invariants désormais imposés sont les suivants :

1. une RFQ indicative ne peut pas être bookée ;
2. une quote doit être sélectionnée, reçue, ferme et encore valide ;
3. le fournisseur doit être relié à une contrepartie éligible et cohérente avec le booking ;
4. le prix modèle doit être présent, positif, récent et rattaché par hash au snapshot exact des inputs ;
5. les termes RFQ et les termes du deal doivent être identiques ;
6. Yahoo est une source de monitoring `INDICATIVE`, jamais une source de fixing officiel ;
7. une résolution suit obligatoirement `PROPOSED → VALIDATED → APPLIED` ;
8. tous les fixings nécessaires doivent être officiels, complets et validés avant validation d’une résolution ;
9. l’outcome proposé doit être confirmé explicitement par l’utilisateur ;
10. l’application d’une résolution est atomique et exactement une fois ;
11. un fixing validé ou appliqué ne peut plus être écrasé ;
12. un deal booké ne peut plus être modifié directement, y compris par le registre d’administration ;
13. une correction post-booking est enregistrée comme demande d’amendement `PENDING`, sans mutation du deal ;
14. l’échec de l’audit empêche la persistance de l’action critique.

## 2. Architecture cible mise en place

### 2.1 Séparation des responsabilités

| Composant | Responsabilité |
|---|---|
| `core/workflow.py` | Vocabulaire canonique des statuts RFQ, fixing, lifecycle et catégories de données |
| `core/rfq_controls.py` | Readiness RFQ, identité contractuelle, hash des inputs de pricing et booking gate central |
| `core/audit.py` | Écriture transactionnelle de l’audit métier persistant |
| `api/rfq.py` | Transitions RFQ/quote, capture fermeté-validité, audit des actions RFQ |
| `api/deals.py` | Booking gate, saisie/validation fixing, propositions lifecycle, validation/application, immutabilité post-booking |
| `services/lifecycle_alerts.py` | Monitoring indicatif planifié, sans droit d’appliquer un outcome |
| `core/admin_registry.py` | Consultation administrative ; refus audité de toute correction directe d’un deal booké |

### 2.2 Flux métier effectif

```text
RFQ DRAFT/READY
    ↓ sollicitation
SENT → QUOTING → SELECTED
    ↓ booking gate complet
EXECUTED / Deal actif
    ↓
Fixing EXPECTED → RECEIVED/PARTIAL → VALIDATED
    ↓                    ↑
Monitoring indicatif → Résolution PROPOSED
                         ↓ confirmation humaine + fixings officiels
                      VALIDATED
                         ↓ application atomique
                      APPLIED → Deal appelé/échu
```

Les anciens statuts RFQ restent stockés pour compatibilité. Une fonction unique les projette vers le vocabulaire cible. Une quote sélectionnée arrivée à expiration est exposée en `EXPIRED`, même si la ligne historique legacy reste `retenue`.

## 3. Contrôle RFQ et intégrité du pricing

### 3.1 Readiness RFQ

Une RFQ `to_trade` doit contenir :

- un script contractuel exploitable ;
- au moins un sous-jacent avec nom, ticker et devise ;
- un nominal strictement positif ;
- une devise ISO à trois lettres ;
- des dates de strike et de valeur valides ;
- une maturité `T` strictement positive ;
- un calendrier contractuel résolvable.

Une RFQ incomplète ne peut pas solliciter de fournisseur lorsqu’elle est `to_trade`.

### 3.2 Quote exécutable

Une quote retenue doit respecter simultanément :

- prix présent ;
- statut `recu` ;
- fermeté `FIRM` ;
- `valid_until` renseigné ;
- `valid_until` postérieur à l’heure courante ;
- fournisseur non remplacé par un last look ;
- fournisseur relié à une contrepartie active ;
- contrepartie demandée identique à la contrepartie résolue.

Les quotes historiques migrent en `UNKNOWN` pour la fermeté. Elles ne sont donc jamais considérées exécutables par supposition.

### 3.3 Prix modèle

Le booking exige :

- un prix modèle positif ;
- un timestamp ;
- un âge inférieur au TTL configurable ;
- un hash SHA-256 identique au hash recalculé sur le script et tous les paramètres persistés.

Le TTL par défaut est de 60 minutes. Il peut être configuré avec `STRUCTURA_RFQ_MODEL_PRICE_MAX_AGE_MINUTES`.

Toute modification d’input de pricing invalide automatiquement le prix modèle, son timestamp et son hash. Le système ne conserve donc plus un prix scalaire après changement des hypothèses qui l’ont produit.

### 3.4 Booking gate

Le contrôle renvoie toutes les défaillances indépendantes en une seule réponse structurée :

```json
{
  "code": "BOOKING_GATE_FAILED",
  "message": "Booking refusé : certains contrôles d'exécution ont échoué.",
  "failures": [
    {"code": "QUOTE_NOT_FIRM", "message": "..."},
    {"code": "MODEL_PRICE_STALE", "message": "..."}
  ]
}
```

Les principaux codes couvrent notamment :

- `RFQ_NOT_EXECUTABLE` ;
- `RFQ_STATUS_INVALID` ;
- `QUOTE_NOT_SELECTED` ;
- `QUOTE_PRICE_MISSING` ;
- `QUOTE_STATUS_INVALID` ;
- `QUOTE_NOT_FIRM` ;
- `QUOTE_VALIDITY_UNKNOWN` ;
- `QUOTE_EXPIRED` ;
- `PROVIDER_COUNTERPARTY_UNMAPPED` ;
- `COUNTERPARTY_MISMATCH` ;
- `MODEL_PRICE_MISSING` ;
- `MODEL_PRICE_TIMESTAMP_MISSING` ;
- `MODEL_PRICE_STALE` ;
- `MODEL_INPUT_HASH_MISSING` ;
- `MODEL_INPUTS_CHANGED` ;
- les erreurs de termes, dates, nominal, devise, sous-jacents et calendrier.

Le refus est audité avant le retour de l’erreur. La création du deal, l’allocation d’une référence et la création du portefeuille par défaut n’interviennent qu’après tous les contrôles susceptibles de rejeter le booking.

## 4. Fixings et lifecycle

### 4.1 Classification de la donnée

Les catégories explicites sont :

- `INDICATIVE` ;
- `PRICING` ;
- `FIXING_OFFICIAL` ;
- `SETTLEMENT` ;
- `UNKNOWN`.

`DealEvent.spots_json` contient uniquement le fixing officiel/candidat.
`DealEvent.indicative_spots_json` contient uniquement le monitoring indicatif.

Un refresh Yahoo :

- écrit dans `indicative_spots_json` ;
- n’écrit jamais dans `spots_json` ;
- ne passe jamais un événement en fixing officiel ;
- ne change jamais directement le statut terminal d’un deal ;
- journalise la source, les dates de prix utilisées et tout fallback de calendrier ;
- produit une erreur et une alerte visibles si la donnée est vide, partielle ou indisponible.

### 4.2 Statuts fixing

Les fondations supportent :

`EXPECTED`, `RECEIVED`, `VALIDATED`, `APPLIED`, `MISSING`, `PARTIAL`, `CONTESTED`, `OVERRIDDEN`, `MANUAL_REVIEW_REQUIRED`.

Dans cette tranche :

- une saisie manuelle complète devient `RECEIVED` ;
- une saisie incomplète devient `PARTIAL` ;
- une validation contrôle la date, la source officielle, l’exhaustivité des sous-jacents et des valeurs numériques strictement positives ;
- un fixing validé devient `VALIDATED` et l’événement `observé` ;
- l’application d’une résolution passe les fixings consommés en `APPLIED` ;
- toute tentative d’écrasement d’un fixing `VALIDATED` ou `APPLIED` est refusée, auditée et signalée par une alerte.

### 4.3 Proposition, validation et application

Le résultat calculé à partir du monitoring crée une `LifecycleProposal` immuable et dédupliquée.

La validation exige :

- un deal encore actif ;
- une proposition au statut `PROPOSED` ;
- aucune résolution validée/appliquée concurrente ;
- tous les événements nécessaires avec fixings officiels complets et `VALIDATED` ;
- une confirmation explicite de l’outcome (`callé`, `ki` ou `final`) ;
- un motif de validation.

La validation ne change pas le deal : elle passe uniquement la proposition en `VALIDATED`.

L’application :

- effectue une transition compare-and-set `VALIDATED → APPLIED` ;
- refuse une seconde application ou une application concurrente ;
- applique l’outcome au bon événement ;
- annule les événements ultérieurs en cas de rappel anticipé ;
- passe le deal à `callé` ou `échu` ;
- persiste le payout réalisé ;
- passe les fixings consommés à `APPLIED` ;
- audite le tout dans la même transaction.

## 5. Immutabilité post-booking et amendements

`PATCH /api/deals/{id}` est désormais une frontière de refus. Tout champ fourni est conservé par le schéma de requête afin d’éviter qu’un champ inconnu soit silencieusement ignoré.

Sont notamment bloqués :

- nominal ;
- devise ;
- contrepartie ;
- prix traité et fair value de booking ;
- sens ;
- statut ;
- dates ;
- maturité `T` ;
- sous-jacents ;
- calendrier/temps d’observation ;
- script et snapshot de marché ;
- RFQ ou quote retenue ;
- tout futur champ contractuel non reconnu.

La voie de correction directe du registre d’administration est également fermée et auditée.

Une structure `TradeAmendmentRequest` et un endpoint de création permettent d’enregistrer :

- le deal ;
- le champ ;
- l’ancienne valeur ;
- la nouvelle valeur ;
- le motif ;
- le demandeur ;
- le statut `PENDING`.

Cette demande ne modifie pas le deal. La validation maker-checker et l’application d’un amendement sont volontairement reportées à la phase suivante.

## 6. Audit métier persistant

La nouvelle table `audit_events` est distincte du journal technique historique `AdminAuditLog`.

Elle conserve :

- action ;
- type et identifiant de l’objet ;
- acteur et type d’acteur ;
- résultat `SUCCESS`, `REJECTED` ou `ERROR` ;
- état avant ;
- état après ;
- motif ;
- source de donnée ;
- corrélation ;
- métadonnées ;
- timestamp.

Les actions couvertes incluent :

- création RFQ ;
- sollicitation fournisseur ;
- mise à jour de quote ;
- mise à jour des inputs RFQ ;
- enregistrement du prix modèle ;
- sélection/désélection de quote ;
- booking accepté/refusé ;
- donnée indicative et fallback ;
- fixing reçu, validé, appliqué ou rejeté ;
- proposition, validation et application de résolution ;
- erreurs lifecycle ;
- tentative d’écrasement ;
- tentative de modification post-booking ;
- demande d’amendement.

L’audit d’une action acceptée appartient à la transaction métier. Pour un refus, l’événement de rejet est committé avant l’erreur. Si l’écriture d’audit échoue, l’action métier n’est pas persistée.

## 7. Migration

La migration est additive et idempotente.

| Table | Ajout | Traitement historique |
|---|---|---|
| `rfq_requests` | `model_input_hash` | `NULL` : prix historique non prouvable, donc non bookable sans repricing |
| `rfq_quotes` | `firmness`, `valid_until` | `UNKNOWN`, validité absente |
| `deal_events` | `indicative_spots_json` | `{}` |
| `deal_events` | `fixing_status` | `MANUAL_REVIEW_REQUIRED` |
| `deal_events` | `data_category` | `UNKNOWN` |
| `deal_events` | validation/application | champs vides |
| nouvelles tables | `audit_events`, `lifecycle_proposals`, `trade_amendment_requests` | créées par `create_all` avant les ALTER |

Aucune fermeté, validité ou qualité de fixing historique n’est inventée.

## 8. Interface minimale livrée

### RFQ

- qualification `À qualifier / Indicative / Ferme` ;
- date-heure de validité ;
- affichage structuré des blocages backend ;
- statut métier `EXPIRED` quand la quote retenue est périmée.

### Lifecycle

- statut du deal en lecture seule ;
- distinction visuelle entre fixing officiel et spot indicatif ;
- statut de fixing ;
- bouton de validation du fixing ;
- affichage des propositions lifecycle ;
- actions séparées `Valider` et `Appliquer` ;
- motif obligatoire ;
- confirmation de l’outcome lors de la validation.

Cette interface est volontairement compacte. Elle ne simule ni écran d’amendement complet, ni workflow maker-checker non implémenté.

## 9. Tests et vérifications

La couverture ajoutée comprend notamment :

- RFQ indicative ;
- mauvais statut ;
- absence de sélection ;
- prix manquant ;
- quote non reçue ;
- quote non ferme ;
- validité inconnue ;
- quote expirée ;
- fournisseur non mappé ;
- contrepartie incohérente ;
- nominal, devise, sous-jacents, dates et maturité invalides ;
- prix modèle absent, sans timestamp, périmé, sans hash ou avec inputs modifiés ;
- chemin de booking conforme ;
- fixing partiel/complet ;
- refus de validation ;
- audit avant/après ;
- audit fail-closed ;
- non-écrasement d’un fixing validé ;
- séparation Yahoo/officiel ;
- erreur de provider visible ;
- déduplication des propositions ;
- validation avec fixings officiels ;
- confirmation explicite de l’outcome ;
- séparation validation/application ;
- application exactement une fois ;
- blocage des champs post-booking, y compris champ futur inconnu ;
- blocage du contournement admin ;
- demande d’amendement sans mutation ;
- migration legacy idempotente et prudente.

Commandes de validation :

```text
python -m pytest -q backend/tests
npm run build
python -m compileall -q backend/app
git diff --check
```

Résultats finaux :

- backend : **441 tests passés** ;
- tests ciblés RFQ/workflow/admin : **152 tests passés** ;
- frontend : **build Vite réussi** ;
- compilation Python : **réussie** ;
- contrôle du diff : **aucune erreur d’espace ou de patch**.

### 9.1 Base UAT locale reproductible

La base locale de test a été réinitialisée et remplacée par un jeu de recette déterministe, généré par :

```text
.venv\Scripts\python.exe backend\scripts\seed_workflow_uat.py --reset-test-db
```

Le script refuse par défaut de travailler sur une base contenant déjà des RFQ ou des deals. L’option destructive vérifie explicitement que la cible est l’unique SQLite locale `backend/data/structura.db` avant de recréer le schéma.

Jeu créé :

- 2 utilisateurs de démonstration ;
- 6 RFQ ;
- 5 quotes ;
- 4 deals ;
- 11 événements ;
- 2 propositions lifecycle ;
- 29 événements d’audit ;
- 1 demande d’amendement `PENDING`.

Scénarios disponibles :

- RFQ ferme exécutée avec succès ;
- quote expirée ;
- quote indicative ;
- validité inconnue ;
- quote non sélectionnée ;
- RFQ d’exploration indicative ;
- résolution proposée mais non appliquée ;
- fixing partiel ;
- amendement sans mutation du deal ;
- résolution déjà appliquée.

Le générateur exécute des assertions métier après création et échoue si un scénario n’expose pas le blocage attendu.

## 10. Risques résiduels et prochaines priorités

### P1 — Rejeu officiel du payoff

La proposition est calculée sur l’historique indicatif, puis confirmée humainement après validation des fixings officiels. Pour les produits path-dependent ou à barrières continues, les seuls fixings événementiels ne suffisent pas à reconstruire mathématiquement tout le chemin officiel.

La prochaine phase doit définir par type de produit :

- la source officielle de chaque observation ;
- la convention de monitoring continu ;
- le snapshot opposable ;
- le moteur de rejeu officiel ;
- la comparaison automatique entre outcome indicatif et outcome officiel.

La protection actuelle reste prudente : aucune application automatique et confirmation explicite de l’outcome.

### P1 — Sémantique du label KI/final

Le moteur existant qualifie encore le résultat de maturité par une heuristique de payout inférieur à 99,5 % du nominal. Le montant est conservé et l’outcome doit être confirmé humainement, mais la prochaine phase doit extraire la sémantique du payoff plutôt que l’inférer du montant.

### P1 — Amendement maker-checker

La demande est persistée mais ne peut pas encore être approuvée/appliquée. Il faut ajouter :

- rôle maker/checker distinct ;
- contrôle quatre-yeux ;
- version contractuelle ;
- recalcul des événements si calendrier modifié ;
- annulation/remplacement plutôt que réécriture ;
- impact documents, valorisation, comptabilité et reporting.

### P2 — Consultation de l’audit

La piste est persistante mais ne dispose pas encore d’un écran métier de recherche, filtre et export.

### P2 — États RFQ physiques

Le vocabulaire cible est projeté de façon compatible au-dessus des statuts legacy. Une migration physique complète vers le nouvel automate pourra être réalisée lorsque tous les consommateurs historiques auront été adaptés.

### P2 — Paramétrage opérationnel du TTL

Le TTL est configurable globalement. Une évolution peut le rendre spécifique au produit, au marché, au fournisseur ou au canal d’exécution.

## 11. Décision de livraison

La tranche est techniquement livrable sur une branche dédiée après revue du diff et validation métier des conventions suivantes :

1. TTL modèle de 60 minutes par défaut ;
2. nécessité d’un mapping fournisseur → contrepartie active ;
3. confirmation humaine de l’outcome proposé ;
4. absence d’application d’amendement dans cette phase ;
5. maintien temporaire des statuts RFQ legacy avec projection vers le vocabulaire cible.

La tranche doit rester dans un commit isolé sur sa branche jusqu’à validation de la recette métier. Aucun merge ni push n’est implicite.
