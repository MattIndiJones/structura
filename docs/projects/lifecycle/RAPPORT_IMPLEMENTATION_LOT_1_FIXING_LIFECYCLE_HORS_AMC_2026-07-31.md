# Rapport d’implémentation — Lot 1 fixing et lifecycle

Date : 31 juillet 2026

Branche : `feat/client-test-agent`

Périmètre : RFQ → pricing → booking → fixing → lifecycle

Exclusion explicite : AMC

## 1. Objet

Ce lot ferme les risques opérationnels prioritaires identifiés sur le passage d’une donnée de monitoring à un événement économique officiel. Il ne modifie pas les modèles de pricing eux-mêmes ; il sécurise les conditions dans lesquelles leurs résultats, les quotes, les bookings et les fixings peuvent être consommés par le lifecycle.

Le principe cible est :

```text
RFQ ferme et fraîche
  → booking sur termes et inputs gelés
  → fixing candidat versionné avec pièce source
  → décision d’un Checker indépendant
  → replay officiel
  → réconciliation outcome / trigger / payout
  → autorisation et application atomiques
```

## 2. Corrections livrées

### 2.1 Habilitations et séparation des responsabilités

- ajout du rôle `ops_maker` ;
- accès Maker et Checker limité à l’entité juridique du deal ;
- interdiction au Deal Owner de saisir ses propres fixings, même s’il cumule le rôle `ops_maker` ;
- interdiction au Deal Owner d’autoriser le lifecycle ;
- interdiction au Maker d’une version de valider ou rejeter cette même version ;
- interdiction au Maker d’un fixing consommé d’autoriser la résolution correspondante ;
- contrôles appliqués côté serveur, indépendamment de l’interface.

### 2.2 Registre immuable des fixings

Chaque soumission crée une ligne `OfficialFixingVersion`. Une correction ne modifie jamais la ligne précédente.

Le registre conserve notamment :

- deal, événement et version contractuelle ;
- numéro de version monotone et version remplacée ;
- valeurs par sous-jacent ;
- fournisseur homologué et type de source ;
- référence externe ;
- timestamp d’observation, timestamp de réception et timezone ;
- place/convention et calendrier ;
- Maker, Checker et motifs ;
- hash de la pièce et hash du record ;
- statuts `RECEIVED`, `PARTIAL`, `VALIDATED`, `REJECTED`, `CONTESTED`, `SUPERSEDED` et `APPLIED`.

La chaîne de correction est gouvernée : une seconde correction ne peut pas être soumise tant que le Checker n’a pas validé ou rejeté la correction courante.

### 2.3 Preuve source réellement archivée

Le hash n’est plus une déclaration isolée.

- la pièce source est transmise et archivée avec la version ;
- taille maximale : 5 Mo ;
- nom de fichier et type MIME contrôlés ;
- contenu Base64 validé côté serveur ;
- SHA-256 recalculé à la soumission ;
- taille et SHA-256 revérifiés avant validation ;
- téléchargement réservé aux rôles Ops de la même entité ;
- réponse de téléchargement `no-store`, en pièce jointe et avec `nosniff` ;
- le payload brut n’est jamais exposé dans la réponse JSON du deal.

Le fournisseur n’est plus un texte libre : le Lot 1 utilise une whitelist de codes stables (`BLOOMBERG`, `REFINITIV`, `OFFICIAL_EXCHANGE`, `CALCULATION_AGENT`, `ISSUER_AGENT`, `CUSTODIAN`).

### 2.4 Provenance et cohérence temporelle

La soumission est rejetée si :

- un champ de provenance obligatoire manque ;
- la source n’est pas homologuée ;
- le type de source n’est pas autorisé ;
- la pièce est vide, invalide, trop volumineuse ou incohérente avec son hash ;
- le timestamp n’a pas d’offset ;
- la timezone IANA est inconnue ;
- l’offset du timestamp ne correspond pas à la timezone à la date observée ;
- la date locale ne correspond pas à la date contractuelle de l’événement ;
- l’événement ou le timestamp est futur ;
- une valeur de sous-jacent est absente, inconnue, non finie ou non positive.

L’identité contractuelle, le ticker, la devise/unité et la valeur de chaque sous-jacent sont inclus dans le record hashé et affichés au Checker.

### 2.5 Décision Checker et rejet formel

Le Checker peut désormais :

- ouvrir la provenance complète ;
- voir les valeurs, instruments, source, référence, timestamps, convention, calendrier, Maker, motifs et hashes ;
- consulter l’historique immuable des versions ;
- télécharger la pièce archivée ;
- valider ou rejeter avec un motif obligatoire.

Le rejet d’une première version place celle-ci en `REJECTED`. Le rejet d’une correction remet atomiquement la version officielle précédente en `VALIDATED`, restaure ses valeurs et conserve la correction rejetée dans l’historique.

### 2.6 Replay et réconciliation lifecycle

Le replay officiel ne consomme que des versions :

- complètes ;
- `VALIDATED` ;
- classées `FIXING_OFFICIAL` ;
- dotées d’une provenance versionnée ;
- saisies par une personne distincte du Checker lifecycle.

Les payoffs nécessitant un chemin daily ou continu restent fail-closed si le jeu de fixings événementiels ne suffit pas à prouver le résultat.

Une divergence d’outcome bloque l’autorisation. Une divergence de payout est désormais également bloquante au-delà de la tolérance monétaire :

```text
tolérance monétaire = 0,5 × 10^(-nombre de décimales devise)
tolérance normalisée = tolérance monétaire / nominal booké
```

Ainsi, pour un deal EUR de nominal 1 000 000, la tolérance normalisée vaut `0,005 / 1 000 000 = 5×10⁻9`.

### 2.7 Autorisation et application atomiques

Le bouton séparé « Appliquer » a été supprimé du lifecycle.

Le Checker confirme l’outcome et motive son autorisation. Le système :

1. recalcule le replay officiel ;
2. vérifie le hash des inputs ;
3. autorise la proposition par CAS `PROPOSED → VALIDATED` ;
4. applique exactement ce résultat par CAS `VALIDATED → APPLIED` ;
5. consomme le verrou économique du deal `actif → callé/échu` ;
6. marque les fixings consommés `APPLIED` ;
7. annule les événements futurs si le produit est rappelé ;
8. écrit les audits ;
9. commit l’ensemble dans une seule transaction.

Un échec de l’audit provoque le rollback de l’autorisation, de l’application, du deal et des fixings. Le CAS sur le statut du deal empêche deux propositions concurrentes d’aboutir sur le même deal.

Le chemin de rejet applique également un rollback avant d’écrire l’audit de refus. Une invalidation détectée entre l’autorisation et l’application ne peut donc pas rendre durable un état intermédiaire `VALIDATED` : la proposition revient à `PROPOSED`, le deal reste `actif`, les fixings restent `VALIDATED` et seul l’audit de rejet est conservé.

### 2.8 Messages d’erreur actionnables

Les refus métier utilisent maintenant une structure homogène :

```json
{
  "code": "CODE_STABLE",
  "field": "champ.concerné",
  "message": "cause précise",
  "expected": "valeur ou état attendu",
  "received": "valeur reçue non sensible",
  "action": "correction réalisable",
  "blocking": true
}
```

L’interface agrège les erreurs indépendantes et affiche le champ, l’attendu et l’action. Les hashes complets ne sont pas renvoyés dans les messages d’erreur.

## 3. Contrôles RFQ, pricing et booking préservés

Les contrôles déjà mis en place restent actifs :

- RFQ exécutable uniquement pour une demande `to_trade` ;
- quote sélectionnée, ferme, reçue, non expirée et rattachée à la RFQ ;
- prix modèle présent, récent et calculé sur le hash courant des inputs ;
- correspondance fournisseur/contrepartie ;
- paramètres économiques obligatoires et cohérents ;
- gel des termes, du script et du snapshot marché au booking ;
- unicité structurelle d’un deal par RFQ ;
- audit des rejets de booking.

Le Lot 1 n’a introduit aucune modification de formule de pricing ou de modèle stochastique.

## 4. Tests et UAT

### 4.1 Tests ciblés

La batterie dédiée couvre notamment :

- rôles, entités et Deal Owner ;
- provenance obligatoire ;
- fournisseur homologué ;
- cohérence timezone/offset ;
- pièce archivée intacte et pièce altérée ;
- téléchargement contrôlé ;
- four-eyes ;
- validation, rejet et restauration ;
- correction immuable et correction concurrente ;
- payout hors tolérance ;
- application atomique ;
- double application ;
- rollback si audit indisponible ;
- amendements gouvernés ;
- non-régression RFQ/booking.

Sign-off final :

- `75 passed` sur les deux suites lifecycle dédiées ;
- `179 passed` sur la batterie ciblée workflow/RFQ/admin ;
- `468 passed` sur la suite backend complète ;
- build frontend production : PASS, 108 modules transformés ;
- `git diff --check` : PASS.

### 4.2 Jeu UAT reproductible

Le script UAT recrée une base locale déterministe avec :

- 6 RFQ ;
- 5 quotes ;
- 4 deals ;
- 11 événements ;
- 5 versions de fixing ;
- 2 propositions lifecycle ;
- profils Deal Owner, Ops Maker et Ops Checker séparés.

Le script vérifie la présence des versions, l’intégrité cryptographique de chaque pièce archivée, les scénarios de refus booking, la proposition non appliquée, le fixing partiel et une résolution appliquée.

### 4.3 Smoke test interface

Le parcours Checker a été contrôlé dans l’application locale :

- affichage de la file de deals de l’entité ;
- présence de l’action « Autoriser et appliquer » ;
- actions distinctes « Valider le fixing » et « Rejeter le fixing » ;
- provenance complète visible avant décision ;
- pièce, taille, hashes, instruments, Maker et historique visibles.

### 4.4 Verdict des agents indépendants

- Agent Opérations : 8 scénarios critiques sur 8 PASS ;
- Agent Structuration : GO Lot 1 et GO recette métier contrôlée ;
- Agent Contrôle / QA : PASS Lot 1, GO pour démarrer le Lot 2 ;
- aucun P0 résiduel identifié dans le périmètre fonctionnel du Lot 1.

## 5. Risques résiduels avant production

Les invariants fonctionnels du Lot 1 sont couverts. Les sujets suivants restent des travaux de durcissement production et ne doivent pas être confondus avec une validation de déploiement immédiat :

1. remplacer le stockage Base64 en SQLite par un stockage documentaire chiffré, versionné et soumis à une politique de rétention ;
2. rendre le référentiel de fournisseurs administrable avec workflow d’approbation plutôt que maintenir une whitelist déployée ;
3. tester les CAS et verrous sous le SGBD cible avec charge et vraies transactions concurrentes ;
4. introduire Alembic ou un mécanisme équivalent de migrations versionnées ;
5. ajouter des tests E2E frontend automatisés pour les rôles, les fichiers, les prompts et les erreurs ;
6. définir la politique antivirus/DLP des pièces avant ouverture à des sources externes ;
7. compléter les procédures d’annulation/remplacement d’une résolution déjà appliquée.
8. externaliser le secret JWT actuellement codé en dur avant tout go-live ;
9. supprimer ou sécuriser le mot de passe du compte bootstrap initial avant tout go-live ;
10. alimenter un `correlation_id` bout-en-bout et auditer les changements administratifs de rôles/entités ;
11. tester les migrations d’une base existante, notamment la contrainte du pointeur de version de fixing.

## 6. Conclusion

Le passage fixing candidat → fixing officiel → résolution économique n’est plus fondé sur une saisie libre ou un hash déclaratif. Il est maintenant versionné, prouvé, contrôlé en four-eyes, réconcilié et appliqué atomiquement.

Décision : **GO Lot 1 / GO recette métier contrôlée / GO pour démarrer le Lot 2**. Cette décision ne constitue pas un go-live global tant que les prérequis de sécurité et d’industrialisation ci-dessus ne sont pas fermés.

AMC est resté hors périmètre. Les changements de fichiers générés `frontend/dist` portant un nom AMC proviennent uniquement du recalcul des hashes du bundle Vite ; aucun fichier source AMC n’a été modifié.
