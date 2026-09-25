# Organisations, admission des utilisateurs et droits d'accès

Date : 24/09/2026.

**Statut : cadrage pour un développement ultérieur. Aucun code de ce chantier
n'est implémenté dans cette session.** Cette note conserve la discussion avec
Philippe ; elle distingue les décisions explicites des propositions à arbitrer.

## 1. Objectif et origine

Permettre à une organisation cliente de Structura d'admettre ses collaborateurs,
de maîtriser leurs habilitations et de conserver ses données indépendamment de
la vie des comptes individuels. Le parcours doit couvrir une plateforme commune
à plusieurs sociétés et une installation séparée chez chaque client.

Déclencheur : lors d'une recette, le formulaire « Créer un compte » affiche
« Inscription publique désactivée. Contactez un administrateur. » après saisie.
Le serveur désactive effectivement l'inscription publique par défaut, tandis que
le frontend présente toujours le formulaire comme utilisable.

Exemple métier demandé : Philippe travaille chez Leonteq au desk Structuration.
Il demande un accès qui doit être autorisé et rattaché à la bonne organisation.
Philippe envisage une clé transmise par l'administrateur Structura au responsable
du compte client, puis un mécanisme d'autorisation des collaborateurs.

## 2. Décisions actées par Philippe

### 2.1 Deux modes de déploiement

- Plateforme commune à plusieurs organisations.
- Installation séparée chez chaque client.

La note [Déploiement on-premise](DEPLOIEMENT_ONPREM.md) décrit un cadrage antérieur
limité à un serveur/poste par client. La demande du 24/09 élargit la cible aux
deux modes ; elle ne signifie pas que le SaaS ou le multi-utilisateur sont déjà
livrés.

### 2.2 Propriété des données : règle centrale

**Les deals, RFQ, produits, scripts, documents et autres données métier
appartiennent à l'organisation, jamais à leur créateur.**

- Le créateur, les auteurs de modifications et les validateurs sont conservés
  pour la traçabilité, sans conférer de propriété personnelle.
- Le départ, la suspension ou le retrait d'accès d'un utilisateur laisse les
  données dans l'organisation.
- Un changement d'employeur ne transfère aucune donnée et ne modifie pas le
  rattachement des travaux historiques.
- Les collègues y accèdent selon leurs habilitations et le partage entre desks.
- Un transfert inter-organisations est une opération distincte, explicitement
  autorisée et tracée. Sa disponibilité et sa procédure restent à définir.

Un espace ou un desk est un périmètre interne d'accès ; **il ne remplace pas
l'organisation comme propriétaire**. Un brouillon réservé à son auteur reste
une donnée de l'organisation.

### 2.3 Admission contrôlée

La demande d'un utilisateur doit aboutir à un rattachement autorisé à une
organisation. La possession d'un compte personnel ou la saisie d'un nom
d'entreprise ne doit pas suffire à ouvrir l'accès à ses données.

Le partage exact des approbations entre Structura et l'administrateur client
reste à arbitrer : la délégation proposée ci-dessous n'a pas été validée comme
une décision définitive.

## 3. Constats sur l'existant, relevés le 24/09

- `backend/app/api/auth.py` : `/register` renvoie un HTTP 403 si
  `STRUCTURA_ALLOW_REGISTRATION` n'est pas activé.
- Lorsque cette inscription est activée, le nom saisi sélectionne ou crée une
  entité ; un champ vide sélectionne « Demo ». Aucun parcours d'approbation ou de
  vérification de l'adresse n'intervient dans cette inscription.
- `frontend/src/views/LoginView.vue` : le formulaire reste accessible et propose
  explicitement le rattachement à Demo si le champ entité est vide.
- `backend/app/db/models.py` : l'utilisateur porte actuellement une seule
  `entity_id` et un rôle global. Ce modèle ne représente pas les habilitations
  multiples ni la distinction administrateur Structura / administrateur client.
- `backend/app/api/admin.py` : l'administration actuelle permet de créer et de
  modifier les utilisateurs et leur entité, via un administrateur global.
- `backend/app/api/scripts_db.py` : certains contrôles de partage s'appuient sur
  l'entité actuelle de l'auteur. Cette dépendance doit être remplacée par le
  rattachement stable des données à leur organisation.

Ces observations sont ciblées, pas un audit exhaustif de l'isolation. Ne pas
résoudre le chantier en réactivant simplement l'inscription publique.

La correction précédente des appels authentifiés du pricer est un chantier
distinct : [note du 24/09](../pricing/PRICING_AUTHENTIFICATION_2026-09-24.md).

## 4. Modèle fonctionnel proposé

| Notion | Exemple | Responsabilité |
|---|---|---|
| Organisation | Leonteq | Propriétaire des données ; compte client Structura |
| Espace de travail | Structuration Paris | Périmètre d'accès au sein de l'organisation |
| Équipe / desk | Structuration | Regroupement de collaborateurs ; cloisonnement selon politique |
| Identité utilisateur | Philippe | Personne authentifiée, avec adresse vérifiée |
| Habilitation | Philippe, structureur, espace Paris | Actions autorisées, périmètre, état et éventuelle échéance |
| Installation | Plateforme ou serveur client | Hébergement ; distinct de l'identité et des droits |

Une organisation abonnée à Structura est distincte d'une fiche du module Clients
(prospect, société couverte, contrepartie). Créer une fiche commerciale ne doit
jamais accorder un accès à l'application.

Prévoir des habilitations par organisation, même si la première interface limite
l'utilisateur à un seul espace actif. En installation isolée, ne pas supposer
qu'une identité est automatiquement fédérée avec les autres installations.

## 5. Responsabilités et droits proposés

| Responsable | Pouvoirs proposés |
|---|---|
| Administrateur Structura | Valider l'organisation, l'installation/abonnement et le responsable initial |
| Responsable du compte client | Représenter l'organisation, nommer les administrateurs, organiser la succession |
| Administrateur client | Traiter les admissions et habilitations dans les périmètres délégués |
| Responsable de desk | Gérer un périmètre limité, si délégation explicite |
| Utilisateur | Exercer les actions métier autorisées ; demander des droits supplémentaires |

Séparer l'administration des accès des permissions métier : lecture,
structuration/pricing, booking, préparation opérationnelle, validation, exports.
Un administrateur d'utilisateurs n'obtient pas automatiquement le droit
d'approuver un fixing ou un amendement. Préserver la séparation maker/checker.

Interdire l'auto-approbation et l'auto-élévation des droits. Ne pas réutiliser le
rôle global `admin` actuel pour les administrateurs clients. Proposer une
authentification renforcée pour les administrateurs et les opérations sensibles.

## 6. Parcours proposés

### 6.1 Première ouverture d'une organisation

1. Demande d'ouverture avec désignation d'un responsable.
2. Vérification par Structura de l'organisation et de l'autorité du responsable
   auprès d'un interlocuteur identifié, indépendamment du simple formulaire.
3. Validation de l'organisation et de ses périmètres initiaux.
4. Invitation nominative du responsable par Structura.
5. Vérification de son adresse, configuration de l'authentification et acceptation.
6. Admission des collaborateurs et désignation d'un suppléant.

Le premier inscrit ne devient pas administrateur par ordre d'arrivée. Il peut
devenir le responsable initial après vérification. Le domaine professionnel est
un indice d'orientation, jamais une preuve suffisante de pouvoir représenter
l'organisation.

### 6.2 Invitation d'un collaborateur

L'administrateur client choisit l'adresse, l'espace, les droits et éventuellement
une date de fin. Le destinataire se connecte ou crée son identité, vérifie son
adresse et accepte l'invitation. L'invitation porte l'approbation de son émetteur ;
elle ne doit pas permettre au destinataire d'élargir les droits proposés.

### 6.3 Demande spontanée

Philippe vérifie son adresse puis demande à rejoindre Leonteq / Structuration.
La demande est dirigée vers le responsable habilité. Celui-ci accepte, refuse
ou demande un complément, et détermine les droits réellement accordés.

Dans l'attente, Philippe peut consulter son profil et le statut de sa demande,
mais n'accède à aucune donnée ou opération métier de l'organisation.
Ne pas exposer un annuaire public des organisations ou de leurs membres.

### 6.4 Circuit d'approbation à arbitrer

Proposition : Structura valide l'organisation et son premier responsable ; le
client valide ensuite ses collaborateurs. Une double approbation Structura et
client peut être exigée selon la politique retenue. Dans ce cas, aucune
activation avant les deux décisions.

### 6.5 Écran d'entrée

Proposer « Se connecter », « Accepter une invitation » et « Demander un accès »,
en fonction des possibilités réelles de l'installation. Afficher clairement
l'état et la prochaine intervention attendue. Supprimer le rattachement
automatique à Demo ; les essais utilisent un espace explicitement isolé.

## 7. Clés et invitations

| Mécanisme | Autorisation |
|---|---|
| Activation initiale | Prise en charge de l'organisation par le responsable nommé |
| Invitation personnelle | Acceptation de droits déterminés par une personne précise |
| Code de rattachement partagé, si retenu | Dépôt d'une demande uniquement, sans accès aux données |
| Licence / activation d'installation | Activation du logiciel ; ne vaut pas habilitation individuelle |

Proposition pour les invitations : jeton imprévisible, lié au destinataire,
à l'organisation, au périmètre et aux droits ; usage unique, expiration et
révocation ; stockage protégé sans journaliser le secret. Durée de 72 heures
proposée, non actée. Une réémission invalide l'ancien lien.

La simple ouverture du lien, notamment par un outil de contrôle de messagerie,
ne doit pas consommer l'invitation : l'acceptation nécessite une action explicite.
Recontrôler les droits de l'émetteur et l'état de l'organisation à l'acceptation.
Une invitation ancienne ne doit pas rétablir des droits retirés entre-temps.

Éviter une clé permanente d'organisation ouvrant directement les données à
toute personne qui la possède. Si un lien est remis manuellement, conserver
les mêmes contrôles de destinataire et d'approbation.

## 8. États à distinguer

Ne pas condenser toute la vie du compte dans un seul indicateur « actif ».

- Identité : adresse à vérifier, vérifiée, suspendue, désactivée.
- Demande : soumise, en examen, approuvée, refusée, retirée, expirée.
- Invitation : en attente, acceptée, expirée, révoquée.
- Habilitation : en attente d'activation, active, suspendue, expirée, révoquée.
- Organisation : en validation, active, suspendue, fermée/archivée.

Ces états sont une proposition à affiner. L'accès métier exige simultanément
une identité utilisable, une organisation autorisée, une habilitation active et
le droit d'exécuter l'action sur la ressource concernée.

## 9. Cas particuliers à couvrir

| Cas | Comportement cible proposé |
|---|---|
| Société inconnue ou homonyme | Validation manuelle ; aucun rattachement par simple égalité de nom |
| Domaine professionnel reconnu | Orientation seulement ; aucune admission automatique |
| Consultant externe | Invitation nominative, périmètre et durée limités |
| Invitation transférée | Refus si le destinataire authentifié ne correspond pas |
| Invitation expirée, révoquée ou utilisée | Message clair ; renvoi contrôlé ; aucun droit supplémentaire |
| Demandes répétées | Une demande active par identité et périmètre |
| Décisions simultanées de deux administrateurs | Transition atomique ; une seule décision effective et traçable |
| Refus ou retrait de demande | Aucun accès ; nouvelle demande selon la politique retenue |
| Identité déjà existante | Connexion puis ajout d'habilitation ; pas de compte dupliqué |
| Plusieurs desks ou organisations | Droits indépendants ; espace actif visible ; aucune réunion implicite des données |
| Changement de desk | Révision des droits ; dossiers conservés dans leur périmètre sauf opération autorisée |
| Changement d'employeur | Ancienne habilitation retirée, nouvelle approuvée ; aucun transfert de travaux |
| Départ du collaborateur | Révocation des sessions et accès ; données et historique conservés par l'organisation |
| Retour du collaborateur | Nouvelle approbation ; pas de restauration automatique des anciens droits |
| Changement d'adresse ou adresse réattribuée | Nouvelle vérification ; aucun transfert d'identité ou d'historique par simple égalité d'adresse |
| Départ du dernier administrateur | Succession préalable ; récupération contrôlée si personne n'est disponible |
| Mot de passe ou second facteur perdu | Récupération de l'identité sans élargissement des droits |
| Organisation suspendue ou fermée | Politique explicite d'accès, de restitution et d'archivage ; pas de suppression automatique |
| Courriel non reçu / messagerie indisponible | État d'attente, renvoi ou remise contrôlée ; pas de contournement |
| Limite de licences atteinte | Demande en attente de capacité ; attribution cohérente en cas de concurrence |
| Retrait des pouvoirs de l'émetteur | Réexamen/invalidation de ses invitations encore pendantes |
| Accès support Structura | Autorisé, limité, temporaire et tracé ; pas d'accès métier permanent implicite |
| Fusion, scission ou transfert d'activité | Projet de migration séparé ; aucune fusion automatique par renommage |

## 10. Plateforme commune et installation client

Les règles d'appartenance et d'autorisation restent identiques.

Sur la plateforme commune, Structura exploite le service d'admission ; chaque
organisation administre son périmètre. L'isolation doit couvrir les API, fichiers,
exports, recherches, caches, assistants IA et tâches de calcul en arrière-plan.
L'identifiant d'organisation fourni par le navigateur ne constitue jamais une
autorisation.

Chez le client, Structura initialise le responsable ; l'administration courante
fonctionne localement, avec la messagerie ou l'annuaire du client si disponible.
Prévoir un parcours contrôlé sans messagerie sortante. Aucun accès distant
permanent de Structura n'est nécessaire.

Une installation déconnectée ne peut pas recevoir instantanément une révocation
centrale. Définir l'autorité locale et les règles de synchronisation avant de
promettre une gestion centralisée multi-installations. Le SSO, le provisioning
par annuaire et la fédération d'identité sont des extensions à arbitrer.

## 11. Migration et sécurité des données existantes

1. Inventorier les propriétaires et contrôles actuels dans chaque module, y
   compris les objets rattachés uniquement à un utilisateur.
2. Établir le rattachement stable de chaque objet métier à son organisation.
3. Préserver séparément auteur, contributeurs, valideurs et historique.
4. Traiter explicitement les objets sans organisation, les comptes Demo et les
   rattachements ambigus ; aucun classement automatique en cas de doute.
5. Ne pas déduire aveuglément l'organisation historique d'un objet de l'entité
   actuelle de son auteur.
6. Préparer sauvegarde, simulation de migration, rapport des écarts et retour
   arrière avant toute application sur les données réelles.
7. Vérifier les sessions existantes et recalculer les autorisations après toute
   suspension, révocation ou modification de rôle.

Tracer qui demande, invite, approuve, refuse, modifie et révoque, avec date,
périmètre et état avant/après. Ne pas enregistrer mots de passe ou clés en clair.

## 12. Découpage de développement proposé

| Lot | Livrable attendu |
|---|---|
| 0 — Arbitrages | Vocabulaire, frontières d'organisation/espace/desk, matrice des droits et circuit d'approbation |
| 1 — Propriété et habilitations | Rattachement organisationnel stable, identité séparée, migration préparée et contrôles d'accès |
| 2 — Première ouverture | Organisation, vérification du responsable, activation, suppléance et récupération |
| 3 — Admission quotidienne | Invitations, demandes, approbations, notifications et écran de suivi |
| 4 — Administration du cycle de vie | Suspension, départ, changements de périmètre, audit et révocation des accès |
| 5 — Déploiements et recette | Variantes plateforme/client, fonctionnement hors ligne et recette complète |

Ne pas ouvrir le nouveau parcours aux utilisateurs avant que les contrôles
d'accès aux données soient effectifs. Une nouvelle interface d'inscription ne
suffit pas à rendre l'application multi-organisations.

## 13. Recette d'acceptation à préparer

Jeu dédié : deux organisations fictives, plusieurs desks/périmètres, un
responsable par organisation, un suppléant, un structureur, un valideur, un
consultant externe et une identité en attente. Aucune donnée réelle nécessaire.

- Ouverture de l'organisation et nomination contrôlée du premier responsable.
- Invitation, demande spontanée, refus, retrait, expiration, réémission et
  acceptations concurrentes.
- Compte en attente : profil/statut accessibles, aucune API métier autorisée.
- Isolation entre organisations et desks, y compris par appel direct à une
  ressource connue, export, fichier ou résultat de calcul.
- Chaîne pricing → produit conservé → RFQ → booking → cycle de vie selon les
  droits, avec séparation préparateur/valideur.
- Départ/changement d'employeur : accès ancien retiré, travaux et historique
  conservés dans l'organisation initiale.
- Retrait d'accès pendant une session et pendant un calcul : aucun résultat
  confidentiel remis après révocation.
- Transfert des responsabilités du dernier administrateur et récupération.
- Parcours local sans messagerie, reprise après indisponibilité et licences.
- Migration : aucun objet perdu, transféré implicitement ou rendu visible à une
  organisation non autorisée.

## 14. Arbitrages ouverts pour la reprise

- Approbation des collaborateurs par le client seul ou double approbation avec
  Structura ? Exceptions et limites de délégation ?
- Quelle granularité d'espace et de desk ; partage par défaut à l'intérieur de
  l'organisation ; traitement des filiales ?
- Une personne peut-elle avoir plusieurs organisations actives dès la V1 ?
- Quels droits composent les profils métier et qui peut les attribuer ?
- Durée des invitations, durée maximale des accès externes et politique MFA ?
- Messagerie disponible, SSO/annuaire requis, procédure d'installation hors ligne ?
- Politique de licences, suspension, restitution et conservation des données ?
- Vérification initiale du responsable, procédure de récupération et contrôle des
  changements sensibles d'administration ?
- Quels objets existants nécessitent une décision manuelle de rattachement ?

**Prochaine étape : reprendre cette note, arbitrer le lot 0 avec Philippe, puis
établir les spécifications et la migration avant de développer.** La présente
demande porte uniquement sur la conservation du cadrage pour plus tard.

## 15. Références

- [Isolation entre organisations — OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html)
- [Jetons temporaires à usage unique — OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

Références consultées lors du cadrage du 24/09. Les durées et circuits proposés
ci-dessus sont des choix de conception à valider, pas des exigences attribuées
à ces références.
