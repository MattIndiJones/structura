# Spécification de remédiation — Vague 1 lifecycle

**Date :** 31 juillet 2026
**Projet :** STRUCTURA
**Périmètre :** booking → fixings → replay officiel → décision lifecycle → application
**Hors périmètre :** AMC, modification du moteur de pricing, refonte générale de l’interface
**Nature du document :** spécification fonctionnelle, contrôles et recette ; aucune implémentation

## 1. Décision exécutive

La Vague 1 doit fermer les risques P0 identifiés par l’audit avant toute mise en production :

1. le même utilisateur ne doit jamais pouvoir saisir puis valider un fixing officiel ;
2. le propriétaire du deal ne doit jamais pouvoir autoriser seul son outcome lifecycle ;
3. une saisie manuelle ne doit pas devenir « officielle » sans preuve opposable ;
4. le replay ne doit jamais inventer de données postérieures au dernier fixing officiel disponible ;
5. un rappel anticipé doit être rattaché à l’événement contractuel exact qui l’a déclenché ;
6. une seule résolution terminale doit pouvoir être autorisée et appliquée par deal ;
7. l’application doit utiliser exclusivement le résultat officiel autorisé et rester atomique et auditable.

La cible proposée repose sur **deux humains minimum** et un processus système :

`Ops Maker → Ops Checker → application atomique par le système`

Le système peut calculer, comparer et appliquer, mais il ne peut ni fabriquer une preuve officielle ni s’auto-autoriser.

## 2. Situation actuelle constatée

Les fondations existantes sont solides :

- séparation entre monitoring indicatif et fixing candidat/officiel ;
- statuts de fixing ;
- propositions lifecycle immuables ;
- replay à partir de fixings validés ;
- hash des inputs officiels ;
- protection compare-and-set lors de l’application d’une proposition ;
- audit métier dans la transaction ;
- blocage fail-closed des produits nécessitant un chemin daily ou continu.

Les contrôles restent toutefois insuffisants sur quatre points :

- les actions fixing et lifecycle sont accessibles au propriétaire du deal ;
- la même personne peut saisir et valider le fixing ;
- la catégorie `FIXING_OFFICIAL` est attribuée à une saisie manuelle avant vérification de sa provenance ;
- le replay événementiel étend le dernier fixing jusqu’à la maturité, ce qui peut créer un faux rappel anticipé sur certaines structures à barrière évolutive.

## 3. Principes non négociables

### 3.1 Séparation des responsabilités

- La propriété économique du deal ne confère aucun droit d’autorisation lifecycle.
- L’administration technique ne confère pas un droit de bypass métier.
- Le Maker d’un fixing ne peut jamais en être le Checker.
- Le Checker lifecycle ne peut pas autoriser une résolution utilisant un fixing qu’il a lui-même saisi.
- Une délégation ou un rôle multiple ne neutralise jamais le contrôle four-eyes.
- Un accès break-glass éventuel produit une exception, pas une validation normale.

### 3.2 Donnée officielle

- « Officiel » qualifie une donnée prouvée, et non son mode de saisie.
- Une source indicative ne peut jamais être promue automatiquement en source officielle.
- Une correction ne remplace jamais silencieusement une donnée validée : elle crée une nouvelle version et conserve l’ancienne.
- Une donnée partielle, future, non positive ou sans preuve reste non validable.

### 3.3 Replay

- Le replay officiel n’utilise que les observations opposables disponibles.
- Aucune donnée officielle ne peut être forward-fillée vers un événement contractuel futur.
- L’absence de donnée produit un blocage explicite, jamais une hypothèse silencieuse.
- Un produit dépendant d’un chemin daily ou continu reste bloqué sans chemin officiel adapté.
- Le résultat officiel est déterministe et reproductible à partir du contrat et des preuves gelées.

### 3.4 Application

- Une autorisation humaine doit être suivie d’une application système atomique.
- Le deal, la proposition, l’événement déclencheur, les événements futurs, les fixings consommés et l’audit doivent être mis à jour dans une même transaction logique.
- Toute divergence ou concurrence fait échouer l’ensemble de l’opération.

## 4. Modèle opérationnel cible

### 4.1 Acteurs

| Acteur | Responsabilité | Autorisé | Interdit |
|---|---|---|---|
| Structurer / Deal Owner | Origination et suivi du deal | Consulter, commenter, contester | Saisir ou valider un fixing officiel, autoriser ou appliquer l’outcome |
| Ops Maker | Capture de la donnée opposable | Créer un candidat, joindre les preuves, soumettre | Valider son propre fixing, autoriser une résolution qui le consomme |
| Ops Checker | Contrôle indépendant | Valider/rejeter un fixing, autoriser/rejeter la résolution | Modifier la donnée contrôlée, valider une donnée qu’il a saisie |
| Système | Monitoring, calcul et exécution | Proposer, rejouer, comparer, appliquer après autorisation | Inventer une preuve, transformer seul une donnée indicative en officielle |
| Administrateur | Administration technique | Gérer les habilitations, consulter l’audit | Bypasser le workflow métier en fonctionnement normal |

### 4.2 Règle four-eyes minimale

Pour chaque fixing consommé par une résolution :

- `entered_by` est renseigné ;
- `validated_by` est renseigné ;
- `entered_by ≠ validated_by` ;
- le validateur possède le rôle Ops Checker dans l’entité juridique du deal ;
- le validateur de la résolution n’est le Maker d’aucun fixing consommé ;
- le propriétaire du deal ne peut pas être le validateur de la résolution.

La règle s’applique sur les identités utilisateur réelles, même si un utilisateur cumule plusieurs rôles.

### 4.3 Application après autorisation

La cible recommandée est :

1. le Checker examine et autorise la résolution ;
2. le système recalcule le hash officiel et les contrôles de concurrence ;
3. si tous les contrôles passent, le système applique immédiatement la résolution dans la même unité de travail ;
4. si un contrôle échoue, rien n’est appliqué et la résolution devient une exception visible.

Un bouton manuel séparé « Appliquer » ne doit être conservé que si l’organisation exige une fenêtre opérationnelle distincte. Dans ce cas, l’Applier doit être habilité Ops, distinct de tout Maker consommé, et ne peut modifier aucun résultat autorisé.

## 5. Registre de fixing officiel

### 5.1 Statuts cibles

```text
EXPECTED
  → RECEIVED
  → VALIDATED
  → APPLIED
```

Branches d’exception :

```text
RECEIVED → REJECTED
RECEIVED ou VALIDATED → CONTESTED
VALIDATED → SUPERSEDED par une nouvelle version validée
```

Un statut `PARTIAL` ou `MANUAL_REVIEW_REQUIRED` ne peut jamais être consommé par un replay officiel.

### 5.2 Preuves obligatoires

Un fixing candidat doit porter au minimum :

| Champ | Exigence |
|---|---|
| Fournisseur officiel | Référentiel contrôlé, pas de texte libre seul |
| Type de source | API, message, fichier, plateforme, agent de calcul ou autre type autorisé |
| Référence externe | Identifiant unique du message, fichier, batch ou publication |
| Date/heure d’observation | Timestamp de marché avec timezone |
| Date/heure de réception | Timestamp système |
| Place ou convention | Marché, heure de clôture ou convention contractuelle applicable |
| Calendrier | Calendrier contractuel utilisé et règle d’ajustement |
| Valeurs | Une valeur strictement positive par sous-jacent requis |
| Identité instrument | Identifiant contractuel du sous-jacent, pas uniquement un ticker d’affichage |
| Unité et devise | Explicites lorsque pertinentes |
| Preuve | Pièce ou payload archivé avec hash cryptographique |
| Maker | Utilisateur ayant capturé la donnée |
| Motif | Obligatoire pour toute saisie ou correction manuelle |
| Version | Numéro monotone par événement et sous-jacent |

La simple valeur `source = manuel` n’est jamais une preuve suffisante.

### 5.3 Validation Checker

Le Checker doit confirmer explicitement :

- identité du contrat et de l’événement ;
- date et heure contractuelles ;
- identité de chaque sous-jacent ;
- exhaustivité des valeurs ;
- conformité de la source au référentiel autorisé ;
- cohérence devise/unité/place ;
- authenticité du hash ou de la pièce ;
- absence de correction plus récente ;
- distinction d’identité avec le Maker.

Une validation globale sans affichage de ces éléments n’est pas acceptable.

### 5.4 Correction et dispute

Une donnée `VALIDATED` ou `APPLIED` reste immuable.

En cas d’erreur :

1. une contestation est ouverte avec motif et preuve ;
2. le fixing courant devient `CONTESTED` pour les décisions non encore appliquées ;
3. une nouvelle version candidate est créée ;
4. un Maker et un Checker distincts traitent la correction ;
5. toute proposition dépendante de l’ancienne version devient `STALE` ;
6. si une résolution a déjà été appliquée, une procédure d’annulation/remplacement ou d’événement compensatoire est requise.

Aucune suppression physique n’est autorisée dans le registre officiel.

## 6. Replay officiel cible

### 6.1 Détermination des événements requis

Les événements requis sont dérivés du calendrier contractuel gelé, pas uniquement de l’événement indiqué par la proposition indicative.

Pour un rappel anticipé officiel à l’observation `k` :

- tous les fixings officiels des observations `0…k` sont requis ;
- le script est évalué successivement sur ces observations ;
- la première instruction terminale `STOP` détermine l’événement exact ;
- aucune observation postérieure à `k` n’est créée ou évaluée.

Pour une échéance sans rappel :

- toutes les observations contractuelles jusqu’à la maturité sont requises ;
- l’absence d’une observation bloque la résolution finale.

Si la proposition indicative pointe sur `k`, mais que le replay officiel ne rappelle pas à `k` :

- la proposition indicative est rejetée comme divergente ;
- le système ne prolonge pas le fixing de `k` jusqu’à la maturité ;
- une nouvelle proposition pourra être produite uniquement lorsque de nouvelles observations officielles seront disponibles.

### 6.2 Construction du chemin événementiel

Pour les produits observation-date only :

- le moteur reçoit les valeurs exactes de chaque observation officielle ;
- les valeurs peuvent être maintenues techniquement entre deux observations uniquement si le script ne lit aucune variable de chemin sur cet intervalle ;
- la série s’arrête au dernier événement officiel nécessaire ;
- elle ne s’étend jamais jusqu’à une maturité future non observée ;
- les dates de la grille respectent le calendrier contractuel et non une approximation `t × 252` utilisée comme source de vérité.

L’utilisation d’un index numérique reste possible en interne, mais l’identité d’un événement est son identifiant contractuel et sa date ajustée.

### 6.3 Produits path-dependent

Les produits lisant notamment `WOF_MIN`, `BOF_MAX`, `S_MIN`, `S_MAX`, `REALVOL`, `FIX_MIN`, `FIX_MAX` ou `FIX_AVG` restent en `OFFICIAL_PATH_REQUIRED` tant qu’un chemin opposable n’est pas disponible.

Pour les rendre éligibles, le snapshot officiel devra préciser :

- fréquence contractuelle ;
- calendrier et timezone ;
- fournisseur ;
- valeurs ou extrema certifiés ;
- politique de jours manquants ;
- corporate actions ;
- version et hash du dataset ;
- période exacte couverte.

Une série de clôtures daily ne prouve pas une barrière continue intraday.

### 6.4 Résultat officiel minimal

Le résultat gelé doit contenir :

- outcome ;
- base sémantique de l’outcome ;
- identifiant de l’événement déclencheur ;
- date contractuelle et date ajustée ;
- index d’observation ;
- fixing(s) déclencheur(s) ;
- niveau(x) de barrière applicable(s) ;
- état du coupon/mémoire si pertinent ;
- payout normalisé non arrondi ;
- montant monétaire arrondi selon la devise ;
- liste et versions des preuves consommées ;
- version du contrat ;
- hash des inputs ;
- version du moteur de replay ;
- timestamp du calcul.

### 6.5 Comparaison indicatif/officiel

La comparaison porte obligatoirement sur :

| Dimension | Règle |
|---|---|
| Outcome | Égalité obligatoire |
| Événement déclencheur | Même identifiant contractuel |
| Date de trigger | Égalité obligatoire après convention contractuelle |
| Payout non arrondi | Égalité à la précision déterministe du moteur |
| Montant monétaire | Écart maximal égal à une demi-unité monétaire minimale de la devise |
| Fixings et barrières | Valeurs affichées et réconciliées |
| Version du contrat | Égalité obligatoire |

Une différence de payout supérieure à la tolérance devient **bloquante**. Le statut informatif `OUTCOME_MATCH_PAYOUT_DIFFERENCE` ne suffit pas pour autoriser l’application.

### 6.6 Statuts de proposition

Automate cible :

```text
PROPOSED
  → OFFICIAL_REPLAYED
  → AWAITING_CHECKER
  → AUTHORIZED
  → APPLIED
```

États terminaux ou d’exception :

- `REJECTED` : rejet humain motivé ;
- `STALE` : contrat, fixing, preuve ou replay modifié ;
- `CONTESTED` : donnée officielle contestée ;
- `ERROR` : échec technique sans mutation du deal.

Une proposition `STALE`, `CONTESTED`, `REJECTED` ou `ERROR` n’est jamais applicable.

## 7. Concurrence et atomicité

### 7.1 Invariants

- Au plus une proposition `AUTHORIZED` ou `APPLIED` par deal.
- Au plus une version `VALIDATED` courante par fixing contractuel.
- Une proposition capture la version du contrat et la version de chaque fixing.
- Toute transition critique vérifie son statut et sa version attendus.
- Une modification concurrente rend la proposition `STALE`.
- Deux Checkers agissant simultanément ne peuvent jamais produire deux décisions terminales.

### 7.2 Transaction d’autorisation/application

La transaction logique doit :

1. verrouiller ou contrôler la version du deal ;
2. contrôler le statut et la version de la proposition ;
3. vérifier l’unicité de la résolution terminale ;
4. recalculer le hash officiel ;
5. revérifier la séparation Maker/Checker ;
6. appliquer l’outcome officiel à l’événement exact ;
7. annuler uniquement les événements strictement postérieurs à un rappel officiel ;
8. marquer les fixings réellement consommés ;
9. mettre à jour le statut du deal et le payout ;
10. écrire l’audit corrélé ;
11. committer l’ensemble ou ne rien persister.

## 8. Audit obligatoire

Chaque action doit produire :

- un `correlation_id` de bout en bout ;
- l’acteur réel et son rôle au moment de l’action ;
- l’entité juridique ;
- l’objet et sa version ;
- l’état avant/après ;
- le motif ;
- la décision et les codes de rejet ;
- la source et le hash des preuves ;
- le hash officiel du replay ;
- le timestamp UTC ;
- l’identifiant de session ou de requête.

Actions minimales auditées :

- réception, soumission, validation, rejet, contestation et correction d’un fixing ;
- création, rejeu, divergence, autorisation, staleness et application d’une proposition ;
- tentative four-eyes interdite ;
- tentative concurrente ou doublon ;
- utilisation break-glass ;
- erreur d’audit ou rollback métier.

L’échec d’écriture de l’audit doit rester fail-closed.

## 9. Interface minimale cible

La Vague 1 ne nécessite pas une refonte générale. Quatre vues compactes suffisent :

1. **Inbox Fixings — Maker**
   événements attendus, saisie/import, source, preuve, anomalies et soumission ;
2. **Validation Fixings — Checker**
   comparaison contrat/source, preuve, valeurs, maker, motif et décision ;
3. **Exceptions Lifecycle — Checker**
   indicatif vs officiel, trigger, payout, divergences, hash et autorisation ;
4. **Timeline Audit — lecture**
   chaîne corrélée, acteurs, preuves, versions, décisions et rejets.

Règles d’interface :

- ne jamais préremplir la confirmation d’outcome comme si elle avait été contrôlée ;
- ne jamais afficher « prêt à appliquer » avant la fin de tous les contrôles ;
- masquer ou désactiver une action non autorisée, tout en maintenant le refus serveur ;
- afficher clairement pourquoi un produit est bloqué `OFFICIAL_PATH_REQUIRED` ;
- présenter les différences, pas seulement deux résultats bruts ;
- demander un motif non vide pour toute décision humaine.

### 9.1 Norme transverse des messages bloquants

Cette norme s’applique à toute la chaîne RFQ → pricing → booking → lifecycle. Un message générique tel que « Booking impossible », « Contrôle échoué » ou un code technique seul est insuffisant.

L’écran doit commencer par un résumé orienté action :

> **Booking impossible — 4 éléments sont à corriger.**
> Aucun deal n’a été créé. Corrigez les points ci-dessous puis relancez le booking.

Chaque erreur affichée doit répondre à six questions :

1. **Où ?** section, objet et libellé du champ ;
2. **Quoi ?** valeur absente ou valeur reçue, si elle peut être affichée sans risque ;
3. **Attendu ?** format, valeur ou état attendu ;
4. **Pourquoi ?** raison métier du blocage ;
5. **Comment corriger ?** action exacte à effectuer ;
6. **Où corriger ?** champ à cibler ou étape du workflow à ouvrir.

Le code de contrôle reste disponible pour le support et l’audit, mais il est secondaire pour l’utilisateur.

### 9.2 Contenu fonctionnel d’une erreur

Chaque anomalie doit transporter les informations suivantes :

| Élément | Utilité |
|---|---|
| Code stable | Support, audit et automatisation des tests |
| Titre utilisateur | Formulation courte et compréhensible |
| Section | RFQ, quote, pricing, booking, calendrier, contrepartie ou lifecycle |
| Champ(s) | Chemin précis du ou des champs concernés |
| Libellé | Nom affiché dans l’interface |
| Valeur reçue | Valeur actuelle, masquée si sensible |
| Valeur attendue | Format, état ou valeur de référence |
| Explication | Impact métier concret |
| Remédiation | Instruction exacte et réalisable |
| Action proposée | Focus champ, retour RFQ, recalcul, nouvelle quote, mapping ou contact Ops |
| Blocage | Toujours explicite : bloquant ou avertissement |
| Correlation ID | Référence à communiquer au support |

Les valeurs de script, hashes, secrets ou données appartenant à une autre entité ne doivent jamais être exposés intégralement dans un message.

### 9.3 Présentation des erreurs

- Remonter **toutes les erreurs indépendantes en une seule réponse**, pas uniquement la première.
- Regrouper les erreurs par section dans l’ordre du workflow réel.
- Afficher en premier les erreurs que l’utilisateur peut corriger directement.
- Mettre en évidence les champs concernés dans le formulaire.
- Placer le focus sur le premier champ modifiable invalide.
- Conserver la liste complète tant que tous les blocages ne sont pas résolus.
- Après correction, indiquer les contrôles résolus et ceux qui restent ouverts.
- Ne jamais proposer de modifier un champ gelé : orienter vers le bon processus, par exemple nouvelle RFQ, nouveau pricing ou amendement.
- Distinguer clairement une erreur de saisie, un état de workflow, un défaut d’habilitation et une erreur technique.
- En cas d’erreur technique, confirmer si aucune donnée n’a été créée ou si l’état précédent reste intact.

### 9.4 Catalogue minimal pour le booking

| Contrôle | Champ/étape à indiquer | Message actionnable attendu |
|---|---|---|
| RFQ indicative | Type de RFQ | « Cette RFQ est indicative et ne peut pas être exécutée. Créez ou convertissez-la en RFQ ferme avant de solliciter des quotes. » |
| Script absent | Termes → Script contractuel | « Le script contractuel est vide. Ajoutez ou sélectionnez un script valide, puis recalculez le prix modèle. » |
| Sous-jacent absent | Termes → Sous-jacents | « Aucun sous-jacent n’est défini. Ajoutez au moins un sous-jacent avec nom, ticker et devise. » |
| Sous-jacent incomplet | Sous-jacent N → champ exact | « Sous-jacent 2 incomplet : ticker et devise manquants. Complétez ces deux champs. » |
| Nominal invalide | Économique → Nominal | « Nominal reçu : 0. Saisissez un montant strictement positif. » |
| Devise invalide | Économique → Devise | « Devise reçue : “CHFEUR”. Sélectionnez un code ISO à trois lettres, par exemple CHF ou EUR. » |
| Date invalide | Calendrier → date concernée | « Date de maturité absente/invalide. Saisissez une date ISO postérieure à la date de valeur. » |
| Ordre des dates | Deux champs concernés | « La date de règlement 30/07/2026 précède la maturité 31/07/2026. Modifiez la date de règlement pour qu’elle soit égale ou postérieure à la maturité. » |
| Calendrier inexploitable | Calendrier/CONSTAT concerné | « Le calendrier contractuel ne peut pas être résolu : CONSTAT_2 est absent. Complétez CONSTAT_2 puis relancez le pricing. » |
| Quote non sélectionnée | RFQ → Quotes | « Aucune quote n’est sélectionnée. Sélectionnez une quote reçue, ferme et encore valide. » |
| Prix de quote absent | Quote retenue → Prix | « La quote retenue ne contient pas de prix final. Demandez ou saisissez le last look final avant booking. » |
| Quote non ferme | Quote retenue → Fermeté | « La quote retenue est indicative. Obtenez une confirmation ferme de la contrepartie avant booking. » |
| Quote expirée | Quote retenue → Validité | « La quote a expiré le 31/07/2026 à 10:32 UTC. Demandez un nouveau last look, puis sélectionnez la quote actualisée. » |
| Quote remplacée | RFQ → Quotes | « Cette quote a été remplacée par un last look plus récent. Sélectionnez la dernière quote ferme disponible. » |
| Mapping absent | Administration → Fournisseurs RFQ | « Le fournisseur retenu n’est relié à aucune contrepartie active. Complétez son mapping avant booking. » |
| Contrepartie divergente | Booking → Contrepartie | « Contrepartie reçue : X ; contrepartie attendue d’après le fournisseur retenu : Y. Sélectionnez Y ou corrigez le mapping fournisseur si celui-ci est erroné. » |
| Prix modèle absent | Pricing RFQ | « Aucun prix modèle positif n’est disponible. Lancez le pricing RFQ avant booking. » |
| Prix modèle expiré | Pricing RFQ | « Le prix modèle a dépassé sa durée de validité de 60 minutes. Recalculez-le avec les inputs actuels. » |
| Inputs modifiés | Pricing RFQ | « Les inputs ont changé depuis le dernier pricing : [liste des champs modifiés]. Recalculez le prix modèle avant booking. » |
| Fair value absente | Booking → Fair value | « La fair value est absente. Reprenez la valeur issue du pricing approuvé ou relancez le pricing. » |
| Prix traité invalide | Booking → Prix traité | « Prix traité reçu : 0. Saisissez le prix final de la quote retenue ou documentez l’override autorisé. » |
| Termes divergents | Champs réellement différents | « Le deal diffère de la RFQ sur : nominal, date de maturité et sous-jacent 1. Rechargez les termes depuis la RFQ ; pour un produit différent, créez une nouvelle RFQ. » |
| RFQ déjà bookée | RFQ / deal existant | « Cette RFQ est déjà liée au deal [référence]. Ouvrez ce deal ; un second booking n’est pas autorisé. » |
| Limite contrepartie | Risque pré-trade | « Le booking dépasserait la limite de X de Y [devise]. Réduisez le nominal ou obtenez l’approbation Risque requise. » |
| Droit insuffisant | Habilitation | « Votre rôle ne permet pas cette action. Le booking doit être effectué par [rôle autorisé] dans votre entité. » |

Les dates, valeurs et noms entre crochets sont dynamiques. L’écran ne doit pas afficher une valeur attendue provenant d’une autre entité ou inaccessible à l’utilisateur.

### 9.5 Exemples de restitution

Exemple avec plusieurs erreurs :

> **Booking impossible — 3 éléments sont à corriger. Aucun deal n’a été créé.**
>
> **Quote retenue — expirée**
> Expirée le 31/07/2026 à 10:32 UTC. Demandez un nouveau last look puis sélectionnez la quote actualisée.
>
> **Prix modèle — obsolète**
> Calculé il y a 84 minutes ; maximum autorisé : 60 minutes. Relancez le pricing RFQ.
>
> **Contrepartie — incohérente**
> Valeur reçue : UBS ; valeur attendue pour le fournisseur retenu : Goldman Sachs. Sélectionnez Goldman Sachs ou corrigez le mapping du fournisseur.
>
> Référence support : `correlation_id`.

Exemple lifecycle :

> **Résolution non autorisable — 2 contrôles bloquants.**
>
> **Fixing du 30/07/2026 — preuve officielle absente**
> Ajoutez la référence externe et la pièce source, puis soumettez à un Ops Checker différent du Maker.
>
> **Replay officiel — chemin incomplet**
> Le payoff utilise `WOF_MIN`. Les fixings d’observation ne prouvent pas une barrière continue. Importez un chemin officiel certifié ou maintenez le deal en revue manuelle.

### 9.6 Critères d’acceptation des messages

- Aucun refus fonctionnel ne se résume à un message générique.
- 100 % des erreurs de champ désignent le ou les champs concernés.
- 100 % des erreurs corrigibles fournissent une action réalisable.
- Les erreurs indépendantes sont restituées ensemble.
- Les erreurs de termes gelés orientent vers le workflow approprié et non vers une modification impossible.
- Les messages restent cohérents entre API, interface et audit.
- Le code stable et le `correlation_id` sont accessibles au support.
- Les tests vérifient le contenu métier des erreurs, pas seulement le statut HTTP.
- Aucun message ne révèle de secret, de hash complet ou de donnée d’une autre entité.

## 10. Backlog de remédiation

| ID | Priorité | Objet | Critère de sortie |
|---|---|---|---|
| LC-P0-01 | P0 | Habilitations lifecycle par rôle et entité | Le Deal Owner ne peut plus saisir/valider/appliquer seul |
| LC-P0-02 | P0 | Four-eyes sur chaque fixing | Maker et Checker distincts, contrôle serveur et audit |
| LC-P0-03 | P0 | Provenance officielle structurée | Aucune validation sans métadonnées et preuve obligatoires |
| LC-P0-04 | P0 | Versionnement/correction des fixings | Aucun écrasement ; correction par nouvelle version |
| LC-P0-05 | P0 | Replay borné aux observations officielles | Aucun forward-fill vers un événement futur |
| LC-P0-06 | P0 | Trigger contractuel exact | Event ID/date du STOP officiel utilisés à l’application |
| LC-P0-07 | P0 | Divergence payout bloquante | Tolérance monétaire explicite et rejet au-delà |
| LC-P0-08 | P0 | Autorisation et application atomiques | Aucun état intermédiaire applicable ou double clic métier |
| LC-P0-09 | P0 | Unicité de résolution par deal | Deux propositions concurrentes ne peuvent aboutir |
| LC-P0-10 | P0 | Staleness automatique | Toute modification d’input invalide la proposition |
| LC-P1-01 | P1 | Workflow dispute/correction | Cycle complet contestation → correction → revalidation |
| LC-P1-02 | P1 | Correlation ID systématique | 100 % des actions de la chaîne corrélées |
| LC-P1-03 | P1 | Écran Ops compact | Maker et Checker disposent de files de travail distinctes |
| LC-P1-04 | P1 | Chemin officiel path-dependent | Produits whitelistés uniquement après preuve de chemin adaptée |
| UX-P0-01 | P0 | Erreurs bloquantes structurées | Chaque refus indique champs, valeurs, attendu et remédiation |
| UX-P0-02 | P0 | Restitution agrégée | Toutes les erreurs indépendantes sont affichées en une fois |
| UX-P1-01 | P1 | Navigation corrective | Focus champ ou lien vers l’étape exacte à corriger |

## 11. Critères d’acceptation métier

### 11.1 Fixings

- Un Maker peut soumettre un fixing complet avec preuve.
- Le même Maker reçoit `FOUR_EYES_VIOLATION` s’il tente de le valider.
- Un Checker de la même entité peut le valider après contrôle.
- Un Checker d’une autre entité ne voit ni ne valide le fixing.
- Une source indicative, un timestamp futur ou une preuve absente bloque la validation.
- Une valeur validée ne peut pas être modifiée en place.
- Une correction crée une nouvelle version et invalide les propositions dépendantes.

### 11.2 Replay

- Un autocall avec fixings officiels jusqu’à l’observation 1 rappelle exactement à l’observation 1 si la condition y est satisfaite.
- Si la condition n’est pas satisfaite à l’observation 1, le système n’utilise pas ce fixing pour simuler les observations 2…N.
- Une barrière dégressive ne peut pas créer de faux rappel sur une date future non observée.
- Le trigger officiel doit correspondre à un événement contractuel exact, jamais à l’événement « le plus proche ».
- Un payoff path-dependent sans chemin officiel est bloqué.
- Une donnée manquante produit un code de blocage explicite.

### 11.3 Décision et application

- Le Deal Owner ne peut pas autoriser sa propre résolution.
- Le Maker d’un fixing consommé ne peut pas autoriser la résolution.
- Le Checker voit outcome, trigger, payout, fixings, barrières, preuves et différences.
- Une divergence de trigger, outcome ou payout hors tolérance bloque l’autorisation.
- Une proposition dont le hash change devient `STALE`.
- Deux validations concurrentes ne produisent qu’un seul résultat terminal.
- L’échec de l’audit provoque le rollback de l’application.
- Une application répétée reste idempotente et ne crée aucun nouvel événement économique.

## 12. Matrice de tests confiée aux agents

### Agent Structuration

- cohérence du contrat et des calendriers ;
- exactitude outcome/trigger/payout ;
- autocalls à barrières constantes et dégressives ;
- maturité, KI explicite et coupons mémoire ;
- divergences indicatif/officiel.

### Agent Operations

- parcours Maker/Checker ;
- fixing incomplet, contesté, corrigé et superseded ;
- files de travail et habilitations par entité ;
- application et annulation des événements futurs ;
- audit de chaque décision.

### Agent Contrôle / QA

- contournement des rôles ;
- utilisateur multi-rôle ;
- concurrence multi-session ;
- staleness et compare-and-set ;
- altération de preuve ou de hash ;
- rollback en cas d’échec audit ;
- idempotence et unicité structurelle ;
- exhaustivité, précision, non-divulgation et stabilité des messages d’erreur.

## 13. Données de recette

La base actuelle contenant uniquement des données de test, aucun backfill fonctionnel n’est requis pour cette vague.

La recette repartira d’un jeu de données contrôlé comprenant au minimum :

- un autocall simple observation-date only ;
- un autocall à barrière dégressive démontrant le risque de faux trigger ;
- un produit arrivant à maturité sans rappel ;
- un produit avec KI explicite ;
- un produit path-dependent devant rester bloqué ;
- deux entités juridiques ;
- au moins un Deal Owner, deux Ops Makers, deux Ops Checkers et un administrateur ;
- des preuves officielles valides, absentes, corrompues, futures et corrigées ;
- deux propositions concurrentes sur un même deal.

Les données doivent être reproductibles et identifiées comme fixtures UAT, sans dépendance à une source externe volatile.

## 14. Gate de sortie de Vague 1

La Vague 1 est terminée uniquement si :

- tous les tickets `LC-P0-*` sont clos ;
- les tickets `UX-P0-*` sont clos ;
- aucun utilisateur ne peut réaliser seul la chaîne complète ;
- aucun fixing n’est officiel sans preuve et validation indépendante ;
- aucun replay ne propage une valeur officielle vers le futur ;
- le trigger appliqué est celui du replay officiel exact ;
- toute divergence matérielle bloque l’application ;
- les tests multi-session démontrent l’unicité de la résolution ;
- l’audit est complet, corrélé et fail-closed ;
- les trois agents rendent un avis convergent ;
- aucun P0 ou P1 nouveau n’est ouvert sur le périmètre.

Le franchissement de cette gate autorise la Vague 2 RFQ → pricing → booking. Il ne constitue pas à lui seul une autorisation de mise en production globale.

## 15. Décisions proposées à valider

Les choix suivants sont recommandés comme baseline :

1. application système atomique immédiatement après autorisation Checker ;
2. interdiction pour le Deal Owner d’être Checker lifecycle de son propre deal ;
3. tolérance monétaire limitée à une demi-unité monétaire minimale après arrondi devise ;
4. correction de fixing uniquement par nouvelle version ;
5. blocage systématique des produits path-dependent sans chemin officiel ;
6. suppression de tout forward-fill au-delà du dernier événement officiel prouvé ;
7. réinitialisation de la base de test et création de fixtures UAT conformes plutôt qu’une migration des données de démonstration.

Ces décisions privilégient l’auditabilité, la sécurité opérationnelle et la simplicité du workflow réel.
