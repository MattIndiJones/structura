# Propriété et habilitations du lot 1 RFQ

Date : 12/10/2026. Version : 1.

Statut : spécification cible ; [premier incrément de propriété et d'accès](RFQ_NETWORK_LOT_1_IMPLEMENTATION_2026-10-12.md) en cours. Philippe a confirmé la visibilité limitée au desk pilote, avec partage explicite vers les autres desks, et exclu la migration des dossiers existants, qui sont des tests. Les profils et circuits ci-dessous sont des propositions de mise en oeuvre de ces décisions.

Le lot 1 donne aux nouveaux dossiers RFQ une propriété organisationnelle stable et des accès par desk. Il doit permettre à un collègue habilité de reprendre le travail tout en conservant les auteurs, les calculs et les décisions de chaque intervenant. Les règles commerciales restent celles du [lot 0](RFQ_NETWORK_LOT_0_SPECIFICATION_2026-10-12.md).

## 1 Périmètre

Le lot couvre la création et l'accès aux nouvelles RFQ, leurs réponses manuelles, leur Product, les calculs conservés, les pièces et le passage au booking local. Il prépare les habilitations des futures RFQ reçues et publications bancaires ; leurs parcours réseau seront livrés dans les lots suivants.

Aucune reprise, qualification ou migration des anciens dossiers n'est demandée. La recette utilisera de nouveaux dossiers fictifs dans un environnement dédié. La présente spécification n'effectue aucune suppression ni réinitialisation de base.

L'admission complète par invitations, le SSO, la fédération entre installations et les transferts de données entre organisations relèvent d'autres travaux. Le pilote nécessite des organisations et collaborateurs préalablement admis, avec des habilitations explicites. L'inscription publique ne constitue pas une admission à une organisation.

## 2 Propriété des nouveaux dossiers

| Information | Règle |
| --- | --- |
| Organisation propriétaire | Fixée à la création depuis le contexte autorisé de l'utilisateur. Elle ne change pas avec son employeur ou son desk. |
| Desk pilote | Un seul desk chargé du dossier à un instant donné. Visibilité limitée à ce desk par défaut. |
| Responsable opérationnel | Collaborateur affecté au suivi ; son affectation ne lui confère aucun droit supplémentaire. |
| Créateur | Conservé pour l'audit ; aucun droit permanent tiré de sa qualité de créateur. |
| Contributeurs et validateurs | Auteurs de chaque calcul, modification, sélection, confirmation ou booking. |
| Partages | Desks supplémentaires, niveau de collaboration, droits autorisés, auteur, motif et éventuelle échéance. |

Un changement de responsable ne transfère ni la propriété ni le périmètre. Un départ retire les accès du collaborateur ; ses travaux restent dans l'organisation. Un utilisateur travaillant ensuite dans une autre société ne retrouve pas ses anciens dossiers grâce à leur champ auteur.

Les nouveaux dossiers durables exigent une organisation et un desk pilote valides. Le navigateur peut proposer un contexte ; le serveur vérifie que l'utilisateur est habilité à l'utiliser. Aucune organisation n'est déduite d'un nom de banque, d'une fiche CRM ou d'une contrepartie juridique.

## 3 Cohérence RFQ, Product et booking

La RFQ et son Product local appartiennent à la même organisation. Les versions de termes, réponses manuelles, calculs et pièces suivent leur dossier, avec leurs propres auteurs conservés. Une cotation publiée par une banque conservera l'identité de cette banque et de son publieur ; sa réception ne donne aucun accès au travail privé bancaire.

Le partage d'une RFQ permet de lire les termes de Product nécessaires à cette RFQ. Il ne donne pas accès automatiquement à toutes les autres RFQ du même Product, à son contexte CRM, à ses calculs privés ou à ses exécutions. Les projections doivent montrer seulement les blocs autorisés, y compris dans les anciennes révisions et les exports.

Le booking depuis une RFQ requiert le droit de booking et l'accès à la RFQ, au Product et à l'accord concerné. Il conserve la même organisation, les références de provenance et les auteurs réels. Le droit de sélectionner un prix n'accorde pas le droit de booker. Le desk ou livre de booking peut différer du desk pilote si ce passage est explicitement autorisé.

La collaboration ne nécessite pas de remplacer le créateur par le repreneur. Un calcul conservé peut être réutilisé par un collègue habilité si les termes, la fraîcheur et la preuve restent valides. Le changement d'utilisateur ne justifie pas à lui seul un recalcul. Un reçu signé prouve le calcul ; il ne constitue pas un droit d'accès.

## 4 Habilitations par desk

Une habilitation désigne une personne, une organisation, un ou plusieurs desks, des actions autorisées, un état et, si nécessaire, une période de validité. La même personne peut cumuler plusieurs fonctions. Chaque organisation garde sa propre politique de seconde validation.

L'autorisation effective exige simultanément une identité utilisable, une habilitation active, un desk autorisé sur le dossier, le droit demandé et les préconditions métier. Les droits d'un autre desk ne sont pas empruntés implicitement. Une habilitation organisationnelle de supervision est possible, mais doit être explicitement accordée.

| Droit | Ce qu'il autorise | Limite |
| --- | --- | --- |
| Lire le dossier RFQ | Termes, échanges commerciaux, réponses et historique autorisés. | Aucun accès implicite au CRM, aux modèles, aux autres dossiers ou aux books. |
| Lire le pricing interne | Calculs, hypothèses et résultats privés du périmètre. | Distinct de la simple lecture commerciale. |
| Préparer | Créer une RFQ, préparer le produit et saisir une réponse manuelle. | Termes déjà sollicités soumis au gel et aux nouveaux tours du lot 0. |
| Solliciter | Envoyer, demander une précision ou une révision, annuler une sollicitation autorisée. | Relation et état recontrôlés ; aucun droit de traitement implicite. |
| Sélectionner | Retenir ou désélectionner une réponse. | Une sélection ne vaut ni acceptation ni réservation du prix. |
| Pricer | Calculer et conserver un résultat dans le périmètre. | Aucun pouvoir de publication implicite. |
| Valider une cotation | Contrôler le contenu commercial préparé. | Seconde personne distincte lorsque la politique l'exige. |
| Publier une cotation | Publier, réviser ou retirer une réponse propre à la banque. | Validation, fraîcheur, relation et règles de retrait du lot 0. |
| Traiter | Demander le traitement d'une réponse précise. | Accord, validité et relation de traitement contrôlés. |
| Consigner une confirmation | Enregistrer le résultat bancaire ou un accord téléphonique déclaré. | Source, interlocuteur, heure et termes obligatoires. |
| Booker | Inscrire un accord confirmé dans un livre autorisé. | Contrôles Product, pricing, contrepartie, CCR et unicité maintenus. |
| Exporter | Exporter les informations auxquelles la personne a accès. | Aucun élargissement du contenu par l'export. |
| Organiser les dossiers | Affecter un responsable, partager ou transférer le desk pilote. | Délégation explicite, périmètre et audit. |
| Administrer les habilitations | Accorder ou retirer des droits dans un périmètre délégué. | Aucun droit métier ou accès aux prix accordé par ce seul pouvoir. |

### Profils proposés

| Profil | Composition de départ |
| --- | --- |
| Consultation | Lecture RFQ ; export si accordé séparément. |
| Demandeur commercial | Lecture, préparation, saisie manuelle, sollicitation et sélection. |
| Structureur | Lecture RFQ et pricing interne, préparation et calcul. |
| Cotateur bancaire | Lecture et préparation bancaire, pricing ; validation et publication si accordées. |
| Validateur bancaire | Lecture nécessaire au contrôle et validation ; publication si accordée. |
| Trader habilité | Lecture, sélection et traitement ; consignation de confirmation si accordée. |
| Booking | Lecture des informations nécessaires, confirmation si accordée et booking dans ses livres. |
| Responsable de desk | Organisation des dossiers ; autres fonctions métier accordées séparément. |
| Administrateur d'organisation | Gestion des habilitations et desks dans sa délégation. |
| Audit ou supervision | Lecture de périmètres définis, éventuellement plusieurs desks ; aucune modification implicite. |

Ces profils servent de modèles lisibles ; ils ne remplacent pas les droits détaillés. Le rôle actuel de Checker sur les fixings n'est pas automatiquement un pouvoir de validation RFQ. Le contrôle à seconde personne doit continuer à porter sur le contenu et les personnes, même si une personne possède plusieurs profils.

## 5 Partage entre desks

Le partage est un acte explicite du responsable habilité du dossier ou d'un gestionnaire délégué. Il indique le desk destinataire et les capacités partagées : consultation, contribution de structuration, ou fonctions commerciales désignées. Ces capacités plafonnent les droits individuels du desk destinataire ; elles ne les créent pas.

Exemple : Sales partage une RFQ avec Structuration pour pricer et avec Trading pour préparer le traitement. Un structureur peut travailler sur le calcul sans accepter le prix ; un trader peut traiter sans administrer les habilitations. Back-office reçoit les informations nécessaires au booking, sans accès automatique aux paramètres de modèle ou à tout le CRM.

Un desk partagé ne peut pas repartager le dossier par défaut. Le retrait d'un partage coupe les accès futurs, y compris depuis un onglet déjà ouvert ou un lien direct. Les contributions et décisions antérieures restent conservées. Le retrait ne permet pas de reprendre les fichiers déjà exportés.

Le transfert du desk pilote est distinct d'un partage : desk source, desk cible, responsable habilité et motif sont enregistrés. L'organisation, les termes, les publications et les accords restent identiques. Les partages existants sont examinés explicitement ; le transfert ne donne pas accès à tous les desks. Le changement est visible dans l'équipe, sans nouvel envoi ni traitement automatique.

## 6 Administration et vie des droits

| Événement | Comportement cible |
| --- | --- |
| Création d'un desk | Rattaché à une seule organisation ; aucun accès aux dossiers d'un autre desk par création. |
| Attribution de droits | Acteur délégué, bénéficiaire, périmètre et date enregistrés. Pas d'auto-élévation de droits. |
| Départ ou suspension | Accès futurs retirés ; dossiers et accords conservés ; responsable réaffectable. |
| Changement de desk | Nouveaux droits accordés, anciens réexaminés ; aucun déplacement automatique des RFQ. |
| Changement d'organisation | Nouvelle admission ; aucun transfert de données. |
| Expiration d'habilitation ou de partage | Refus des nouvelles opérations concernées. |
| Révocation pendant un calcul | Résultat conservable dans le dossier d'origine ; aucune remise confidentielle à l'utilisateur désormais exclu, ni publication automatique. |
| Révocation après accord confirmé | Accord conservé ; reprise par un collègue habilité, sans nouvel ordre automatique. |
| Départ du responsable | File du desk conservée ; affectation explicite d'un remplaçant. |

L'administration technique et l'administration des utilisateurs n'accordent pas de lecture métier universelle. Un accès support doit avoir un périmètre et une durée autorisés et une trace. Un service de calcul ou d'échange dispose des seules capacités de sa mission et conserve l'organisation d'origine ; il ne choisit ni prix ni exécution.

## 7 Parcours écran à prévoir

| Écran | Contenu et actions |
| --- | --- |
| Contexte actif | Organisation et desk visibles ; changement uniquement vers un contexte habilité. |
| RFQ du desk | Dossiers du desk pilote et dossiers partagés ; filtres Mes dossiers, Desk et Partagés. Mes dossiers est un filtre de responsabilité. |
| En-tête RFQ | Organisation, desk pilote, responsable, créateur et indication de partage. |
| Affectation | Choisir un responsable habilité ; conserver l'historique. |
| Partage | Desk, capacités autorisées, échéance éventuelle, motif, récapitulatif puis application explicite. |
| Administration | Desks, membres, profils, droits détaillés, états et délégations. Aucun affichage implicite du book ou des prix. |
| Historique | Changements d'affectation, partages, habilitations et décisions métier accessibles selon le périmètre. |

Une fonction visible mais non autorisée peut expliquer le droit manquant à un utilisateur qui peut déjà consulter le dossier. Un dossier extérieur à son périmètre reste inaccessible sans révéler son contenu ou son existence. Les filtres, compteurs et recherches suivent ce même périmètre.

## 8 Réalisation et recette attendues

La lecture statique ciblée du 12/10 confirme que les RFQ sont encore filtrées par utilisateur, que l'accès Product accepte son utilisateur ou le rôle admin, et que le booking RFQ exige encore le même utilisateur. Les tables concernées portent déjà des entités mais pas de modèle complet de desks et habilitations. Cette lecture ne constitue ni un audit exhaustif ni un inventaire de la base.

| Étape | Livrable |
| --- | --- |
| 1 Identités et contextes | Organisation, desks et collaborateurs admis pour les nouveaux dossiers du pilote. |
| 2 Propriété à la création | Rattachement stable de la nouvelle chaîne RFQ–Product–réponses–calculs–booking. |
| 3 Droits effectifs | Contrôle cohérent sur lecture, actions, projections, historiques, calculs et exports. |
| 4 Collaboration | Affectation, partage, retrait et changement de desk pilote tracés. |
| 5 Qualification | Rapport de recette sur nouveaux dossiers fictifs. Aucune reprise des anciens tests. |

L'isolation doit couvrir tous les chemins donnant accès aux dossiers concernés, y compris les liens Product, les révisions, les résultats de tâches, les statistiques, les pièces et le booking. Élargir seulement le filtre de la liste RFQ serait insuffisant.

| Scénario de recette | Résultat attendu |
| --- | --- |
| Deux collègues du même desk habilités | Reprise du même dossier sans changement de créateur ni duplication. |
| Deux desks de la même organisation sans partage | Aucun accès aux RFQ de l'autre desk. |
| Partage en consultation | Lecture des blocs autorisés, aucune modification. |
| Partage pour pricing | Calcul autorisé ; publication ou traitement refusés sans droits propres. |
| Partage retiré, onglet ouvert | Nouvelle lecture ou action refusée ; historique conservé. |
| Product avec plusieurs RFQ | La RFQ partagée ne révèle pas les autres consultations ou blocs privés. |
| Même identifiant connu dans une autre organisation | Refus sur RFQ, Product, calcul, pièce, historique et export. |
| Créateur parti ou changement d'employeur | Dossier conservé dans l'organisation d'origine ; aucun accès personnel persistant. |
| Nouveau responsable | Reprise selon ses droits, auteurs et décisions inchangés. |
| Calcul d'un collègue | Réutilisation possible si autorisée et valide ; auteur original conservé. |
| Sélection par Sales, booking par un collègue habilité | Même dossier, même accord, auteurs distincts et un seul booking. |
| Validation à seconde personne | Auto-validation refusée, y compris avec cumul de profils. |
| Administrateur sans droits métier | Gestion autorisée des accès, aucune lecture ou publication implicite. |
| Révocation pendant une tâche | Aucune remise de résultat confidentiel à l'utilisateur révoqué. |
| Droits changés entre préparation et action | Recontrôle au moment de l'action ; refus explicite si nécessaire. |
| Manuel et future réponse réseau | Mêmes règles locales d'accès ; aucune divulgation des calculs bancaires privés. |

Critère de sortie : sur de nouveaux dossiers, la reprise par un collègue, le partage limité, la révocation et l'isolation sont démontrés sur toute la chaîne concernée. Le lot 1 ne livre pas encore le réseau de prix et ne requiert aucune migration historique.

## 9 Références

- [Plan RFQ](RFQ_NETWORK_ACTION_PLAN_2026-10-12.md), lots et dépendances.
- [Lot 0 RFQ](RFQ_NETWORK_LOT_0_SPECIFICATION_2026-10-12.md), règles métier inchangées.
- [Organisations et accès](ORGANIZATION_ACCESS_DESIGN_2026-09-24.md), doctrine générale et admission ultérieure.
- [Objet Product](PLAN_IMPLEMENTATION_OBJET_PRODUCT.md), dossier canonique et preuves immuables.
- Points existants lus : `backend/app/db/models.py`, `backend/app/api/auth.py`, `backend/app/api/rfq.py`, `backend/app/api/products.py`, `backend/app/api/deals.py`, `backend/app/services/product_repository.py` et `backend/app/services/product_receipts.py`.

Cette spécification décrit la cible et se distingue de l'état réalisé, détaillé dans la note d'implémentation liée ci-dessus.
