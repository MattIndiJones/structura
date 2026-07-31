# Rapport d’implémentation — phase 2 RFQ → pricing → booking → lifecycle

Date : 31 juillet 2026
Branche : `feat/client-test-agent`
Périmètre : rejeu officiel lifecycle, sémantique du résultat, amendements maker-checker et consultation de l’audit
Hors périmètre : AMC

## 1. Résultat exécutif

Cette tranche ferme trois risques résiduels de la phase 0/1 :

1. une résolution n’est plus appliquée à partir du seul calcul indicatif ;
2. le label `ki`/`final` n’est plus déduit arbitrairement d’un payout inférieur à 99,5 % ;
3. une correction post-booking peut suivre un workflow maker-checker versionné sans rouvrir l’endpoint de modification directe.

La piste d’audit est également consultable dans le workflow deal, filtrable par résultat et exportable en CSV.

Le principe de sécurité est fail-closed : lorsqu’un payoff dépend d’un chemin daily ou continu que les seuls fixings événementiels ne permettent pas de prouver, la validation est refusée avec le code `OFFICIAL_PATH_REQUIRED`.

## 2. Rejeu officiel lifecycle

### 2.1 Chaîne de décision

La chaîne cible est désormais :

`monitoring indicatif → proposition → fixings officiels validés → rejeu officiel → comparaison → validation → application`

Le monitoring Yahoo reste strictement indicatif. Il peut créer une proposition mais ne peut ni la valider ni l’appliquer.

### 2.2 Rejeu depuis les fixings opposables

Pour un payoff qui ne lit que les observations contractuelles :

- les fixings requis jusqu’à l’événement déclencheur doivent être complets ;
- chaque fixing doit être `VALIDATED` ;
- chaque fixing doit être catégorisé `FIXING_OFFICIAL` ;
- le script figé au booking est recompilé ;
- les `user_params`, calendriers `constats`, taux et dates figés au booking sont réutilisés ;
- le payoff est rejoué sur une grille déterministe correspondant aux observations officielles ;
- le résultat officiel est persisté dans la proposition lifecycle.

Le résultat officiel contient notamment :

- l’outcome ;
- sa base sémantique ;
- l’événement déclencheur ;
- le payout réalisé ;
- la nature des inputs utilisés.

### 2.3 Hash des inputs officiels

Le hash SHA-256 couvre :

- l’identifiant et la version du contrat ;
- le script contractuel ;
- les paramètres PayScript ;
- les calendriers ;
- les dates et le tenor ;
- chaque fixing officiel, son statut et sa catégorie.

Le hash est gelé à la validation puis recalculé avant l’application. Une divergence produit `OFFICIAL_REPLAY_STALE` et bloque l’application.

### 2.4 Comparaison indicatif/officiel

Deux statuts sont exposés :

- `MATCH` : outcome et payout concordent ;
- `OUTCOME_MATCH_PAYOUT_DIFFERENCE` : l’outcome concorde mais le payout officiel diffère.

Une divergence d’outcome produit `OFFICIAL_INDICATIVE_OUTCOME_MISMATCH`. La proposition indicative ne peut alors pas être validée comme si les deux calculs concordaient.

À l’application, le deal reçoit exclusivement l’outcome et le payout du rejeu officiel. Le résultat indicatif n’est plus utilisé pour muter le deal.

### 2.5 Produits path-dependent

Les observables suivants déclenchent actuellement un besoin de chemin officiel :

- `WOF_MIN` ;
- `BOF_MAX` ;
- `S_MIN[i]` ;
- `S_MAX[i]` ;
- `REALVOL` ;
- `FIX_MIN`, `FIX_MAX`, `FIX_AVG`.

Les fixings événementiels ne permettent pas de prouver une barrière touchée entre deux observations, une volatilité réalisée ou une fenêtre de strike averaging. La validation est donc refusée plutôt que de construire artificiellement un chemin.

La prochaine intégration nécessaire est un snapshot officiel daily/continu, versionné, sourcé et opposable. Pour une barrière continue intraday, des extrema certifiés ou un événement de breach officiel seront requis ; une simple série de clôtures daily ne suffira pas.

## 3. Sémantique KI/final

L’ancienne règle `maturity_payout < 99,5 % → ki` a été supprimée.

Le moteur inspecte désormais l’état explicite produit par le script :

- variables `KI` ;
- variables `KNOCK_IN` ;
- variables `BREACH` ou `BREACHED` ;
- variantes explicites équivalentes.

Les paramètres contractuels de type `M_KI_BAR` sont exclus de cette lecture afin de ne pas confondre un niveau de barrière avec un état réalisé.

Si un état explicite de breach est actif, l’outcome est `ki`. Sinon, l’outcome de maturité est `final`, quel que soit le montant payé. Un produit optionnel ou capital-protégé peut donc payer moins que le nominal sans être faussement étiqueté knock-in.

## 4. Amendements maker-checker

### 4.1 Rôles et périmètre d’accès

Les rôles applicatifs sont maintenant :

- `user` : maker standard ;
- `checker` : contrôle opérations ;
- `admin` : administration et capacité checker.

Un checker non administrateur ne voit que les deals de sa propre entité juridique. Le maker ne peut jamais approuver ou appliquer sa propre demande, même s’il possède aussi un rôle permettant le contrôle.

Le non-respect des quatre yeux produit `FOUR_EYES_VIOLATION` et un audit persistant.

### 4.2 Automate

L’automate est :

`PENDING → APPROVED → APPLIED`

ou :

`PENDING → REJECTED`

Seule la transition attendue est admise. Les doubles applications et les traitements concurrents sont refusés.

### 4.3 Contrôle de concurrence

Chaque deal possède un `contract_version` monotone.

La demande d’amendement capture :

- la version de départ ;
- l’ancienne valeur ;
- la nouvelle valeur ;
- le maker ;
- le motif.

L’approbation et l’application vérifient que :

- la version du deal n’a pas changé ;
- la valeur de départ est toujours identique ;
- le statut de la demande autorise la transition ;
- le checker est distinct du maker.

L’application utilise un compare-and-set sur la version du deal et sur le statut de la demande.

### 4.4 Snapshots contractuels

La table `deal_contract_versions` conserve des snapshots immuables :

- version avant amendement ;
- version après amendement ;
- demande source ;
- utilisateur ayant créé le snapshot ;
- date de création.

La ligne opérationnelle du deal reste la version courante, mais l’historique contractuel complet n’est pas perdu.

### 4.5 Modifications applicables en place

Les champs suivants sont autorisés après contrôle :

- nominal strictement positif ;
- contrepartie non vide ;
- prix traité strictement positif ;
- date de paiement ISO non antérieure à la maturité.

Une application crée une alerte imposant la revue des documents, de la valorisation, de la comptabilité et du reporting.

### 4.6 Changements imposant un rebooking

Les champs qui modifient l’économie, le calendrier ou le modèle sont bloqués avec `AMENDMENT_REBOOK_REQUIRED`, notamment :

- devise ;
- statut ;
- trade date, strike date, value date ou maturité ;
- script PayScript ;
- snapshot de marché.

Ces changements doivent suivre un futur workflow d’annulation/remplacement : nouveau contrat, nouveaux événements, nouveaux documents et lien explicite avec la version annulée. Ils ne sont volontairement pas appliqués en place.

## 5. Consultation de la piste d’audit

Le endpoint `GET /api/deals/{deal_id}/audit` rassemble les audits liés :

- au deal ;
- à la RFQ source ;
- aux événements/fixings ;
- aux propositions lifecycle ;
- aux amendements.

Filtres disponibles :

- `action` ;
- `result` ;
- `limit`, borné entre 1 et 1 000.

L’interface deal affiche :

- date ;
- action ;
- résultat ;
- objet ;
- motif.

Le filtre de résultat et l’export CSV UTF-8 sont disponibles dans l’écran métier.

## 6. Interface amendement

L’écran deal affiche :

- la version contractuelle courante ;
- le formulaire maker pour les champs amendables ;
- l’ancienne et la nouvelle valeur ;
- le statut de la demande ;
- la version de base ;
- les boutons approuver, rejeter et appliquer pour les checkers autorisés.

L’administration des utilisateurs permet d’attribuer le rôle `checker`.

## 7. Migration de données

Les migrations sont additives et idempotentes.

Ajouts sur `deals` :

- `contract_version`, valeur historique par défaut `1`.

Ajouts sur `lifecycle_proposals` :

- `official_result_json` ;
- `official_input_hash` ;
- `official_replayed_at` ;
- `comparison_status`.

Ajouts sur `trade_amendment_requests` :

- `base_contract_version` ;
- motifs et timestamps de décision ;
- acteur et timestamp d’application ;
- version contractuelle appliquée.

Nouvelle table :

- `deal_contract_versions`.

Les propositions historiques déjà `APPLIED` ne sont pas réinterprétées automatiquement. Le jeu UAT recréé contient un exemple appliqué avec rejeu officiel et hash cohérents.

## 8. Tests et recette

Résultats :

- 450 tests backend passés ;
- 73 tests ciblés workflow/admin passés ;
- build frontend Vite réussi ;
- recette UAT locale réussie après reset explicite.

Les tests nouveaux couvrent notamment :

- payout inférieur au nominal sans faux label KI ;
- état KI explicite ;
- blocage des payoffs path-dependent sans chemin officiel ;
- gel du rejeu officiel ;
- application du payout officiel ;
- divergence indicatif/officiel ;
- quatre yeux ;
- cloisonnement par entité ;
- application exactement une fois ;
- snapshots des versions 1 et 2 ;
- obligation de rebooking pour un changement de script ;
- timeline d’audit filtrable et cloisonnée.

Commande de recette :

```powershell
.\.venv\Scripts\python.exe backend\scripts\seed_workflow_uat.py --reset-test-db
```

## 9. Risques résiduels et prochaine tranche

### P1 — Source officielle de chemin

Le blocage est sûr mais rend inapplicable automatiquement un payoff dépendant du chemin. Il faut intégrer un format d’import officiel comprenant source, calendrier, convention de marché, contrôles de complétude, hash et validation humaine.

### P1 — Annulation/remplacement

Le moteur bloque correctement les amendements qui nécessitent un nouveau contrat, mais ne crée pas encore automatiquement le deal de remplacement ni le lien de filiation.

### P1 — Propagation aval

L’alerte de revue aval est créée, mais la régénération/version des confirmations, la notification comptable et le reporting ne sont pas encore orchestrés automatiquement.

### P2 — File checker dédiée

Le endpoint `/api/deals/amendment-requests/pending` existe. Une vue transverse dédiée améliorerait le traitement en masse ; le workflow reste déjà utilisable depuis le deal concerné.
