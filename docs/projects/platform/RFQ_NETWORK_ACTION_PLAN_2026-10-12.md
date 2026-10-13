# Plan de réalisation du réseau RFQ Structura

Date : 12/10/2026. Version : 9.

Statut : lot 0 cadré avec prototype et préparation RFQ/Product, propriété/habilitations et collaboration de desk codées au lot 1, relations bilatérales et contrôle des destinataires livrés au [lot 2](RFQ_NETWORK_LOT_2_IMPLEMENTATION_2026-10-12.md), demande figée et envoi persistant au [lot 3](RFQ_NETWORK_LOT_3_IMPLEMENTATION_2026-10-12.md), prise en charge et pricing bancaire privé au [lot 4](RFQ_NETWORK_LOT_4_IMPLEMENTATION_2026-10-12.md), validation/publication et retour locaux au [lot 5](RFQ_NETWORK_LOT_5_IMPLEMENTATION_2026-10-12.md), puis transport signé et reprise entre installations au [lot 6](RFQ_NETWORK_LOT_6_IMPLEMENTATION_2026-10-12.md), sur `codex/rfq-network-lot-0`. Recette avec deux vrais serveurs fictifs et contrôle visuel à scroll interne réalisés au lot 6. La qualification générale des droits, les compléments précisions/déclin, la confirmation avant booking du lot 7 et le pilote réel restent à terminer.

Structura doit permettre à une organisation d'adresser une demande de prix à ses partenaires autorisés, à chaque banque de recevoir et pricer le même produit dans son environnement privé, puis de publier humainement une réponse qui revient automatiquement au demandeur. La saisie manuelle reste disponible dans le même module, y compris pour une consultation réunissant des fournisseurs connectés et non connectés.

La [spécification complète du lot 0](RFQ_NETWORK_LOT_0_SPECIFICATION_2026-10-12.md) fait foi pour les parcours, les données échangées, les droits, les transitions, la fermeté et la confirmation du traitement. Le présent plan organise les lots de réalisation et leurs critères de sortie.

## Décisions actées

| Sujet | Règle retenue |
| --- | --- |
| Propriété des dossiers et relations RFQ | Organisation utilisatrice de Structura, avec auteurs conservés pour l'audit. |
| Visibilité interne | Desk pilote par défaut, partage explicite vers les autres desks. |
| Dossiers existants | Tests hors périmètre ; aucune reprise ou migration demandée pour ce chantier. |
| Destinataires | Liste autorisée propre à chaque organisation ; relation reconnue par les deux parties. |
| Produit communiqué | Projection des termes versionnés du Product, paramètres effectifs et calendrier contractuel précis. |
| Pricing bancaire | Hypothèses, données, modèles, calculs et marge internes privés. Réutilisation des données déjà présentes avant un téléchargement externe. |
| Publication du prix | Contrôle humain par un utilisateur habilité. La réception du prix chez le demandeur est automatique. |
| Seconde validation | Configurable par organisation. Sans cette politique, un même utilisateur habilité peut calculer, contrôler et publier. |
| Parcours manuel | Conservé, avec origine des réponses et rapprochement explicite des éventuels doublons. |
| Cotation ferme | Exécutable sur les termes, le demandeur, le nominal, la devise et les dates publiés tant qu'elle reste active. |
| Retrait | Possible avant réception d'une acceptation valide, avec motif et notification. Après acceptation valide, prix réservé au traitement ; aucun retrait ordinaire par RFQ. |
| Confirmation avant booking | Accord explicite, identifié et consigné. Confirmation reçue de la banque ou accord téléphonique déclaré par un utilisateur habilité, avec suivi écrit. |
| Temps de référence | Validité de la cotation contrôlée à la réception de l'acceptation. Un accord confirmé reste bookable après expiration de la cotation d'origine. |
| Exécution | Réception, sélection, acceptation, confirmation et booking sont des faits distincts. Une référence d'exécution ne produit qu'un booking par organisation. |

## Périmètre de la première livraison

La V1 couvre les relations RFQ, les demandes et réponses natives entre organisations, le pricing bancaire privé, la publication humaine, le retour automatique, les révisions, les précisions, les déclins, les retraits autorisés, le maintien du manuel et le passage contrôlé au booking local. La confirmation de traitement peut encore être obtenue hors réseau et enregistrée avec sa provenance.

Le pilote recommandé comprend une organisation demandeuse, deux banques connectées et un fournisseur dont la réponse est saisie manuellement. Il commence par un Athena à coupon fixé, coté en pourcentage du nominal et pour la totalité du nominal demandé. Les identités des participants, le cas exact et l'hébergement du pilote restent à arrêter avant réalisation.

Les étapes suivantes couvriront les messages natifs d'acceptation et de confirmation de traitement, le rapprochement des bookings des deux parties, puis les demandes de coupon ou participation à résoudre et les exécutions partielles. La cotation bancaire sans intervention humaine reste une extension distincte. Les campagnes IA de simulation ne prouvent pas à elles seules la livraison du réseau RFQ.

## Fondations et responsabilités

| Fondation | Utilisation prévue |
| --- | --- |
| Product et versions de termes | Définition contractuelle commune et photographie locale cohérente. Chaque organisation conserve son identité de dossier locale. |
| PayScript et catalogue de modèles | Sémantique du payoff qualifiée, paramètres effectifs et versions compatibles. |
| RFQ et quotes | Comparaison, sélection, provenance et historique des réponses. |
| Relations bilatérales et référentiels | Organisation partenaire, contrepartie juridique, documentation, périmètre et droits de sollicitation ou de traitement. |
| Pricer et reçus de calcul | Calculs privés reproductibles et contrôle du prix préparé. Les reçus détaillés ne sont pas transmis avec la cotation. |
| Booking, audit et CCR | Contrôles d'exécution locaux, preuve de l'accord, inscription unique et conservation des refus ou blocages. |

Le métier arrête les conventions et réalise la recette des deux parties. Chaque administrateur d'organisation gère les habilitations et relations dans son périmètre. La banque possède la décision de prix et de publication. Le demandeur possède la sélection et la décision de demander un traitement. Les fonctions de booking conservent leurs droits propres.

Le service d'échange assure l'adressage, la remise des messages, les accusés et la reprise après interruption. Il ne choisit ni prix, ni contrepartie, ni exécution. La solution d'hébergement devra couvrir la plateforme commune et les installations séparées retenues pour le pilote sans mélanger leurs données privées.

## Lot 0 Cadrage fonctionnel

### Travail à réaliser

Consolider le parcours écran des deux parties, le contenu exact d'une demande et d'une réponse, les droits, les états indépendants et les règles de publication, retrait, acceptation et confirmation. Définir les informations partagées et privées ainsi que la coexistence avec la saisie manuelle.

Le cadrage consigné dans la spécification inclut les deux arbitrages de fermeté et de confirmation. Il prévoit la seconde validation configurable et distingue un accusé de livraison d'une réponse ou confirmation métier.

### Livrables et critère de sortie

Livrables : spécification métier, parcours tabulés, matrice des droits et scénarios d'acceptation. Le [rapport de réalisation](RFQ_NETWORK_LOT_0_IMPLEMENTATION_2026-10-12.md) couvre le prototype demandeur/banque, puis la préparation de demande depuis les RFQ/Product enregistrés, le pricing privé avec les moteurs existants et le passage au Pricer. Les masques utilisent un défilement interne. La préparation ne constitue pas un envoi réseau ; le périmètre livré, les vérifications et la suite figurent dans ce rapport.

Critère de sortie : sur une demande et deux cotations, chaque partie identifie les termes reçus, les données privées, le prix publié, les actions possibles et les faits requis avant booking. Les choix de pilote, d'hébergement et de paramètres opérationnels sont arrêtés avant le lot correspondant.

## Lot 1 Propriété et habilitations par organisation

### Travail à réaliser

La [spécification détaillée du lot 1](RFQ_NETWORK_LOT_1_SPECIFICATION_2026-10-12.md) précise propriété, habilitations, partage et recette. Établir une propriété stable de l'organisation pour les nouveaux dossiers, avec droits par desk et auteurs conservés. La visibilité est limitée au desk pilote par défaut ; le partage vers d'autres desks est explicite.

Philippe exclut la migration des dossiers existants, qui sont des tests. Le lot porte sur de nouveaux dossiers et un environnement de recette dédié. Les droits doivent couvrir RFQ, Product, réponses, calculs, pièces et passage au booking ; un changement de responsable ou d'employeur ne transfère pas leur propriété.

### Livrable et critère de sortie

Livrable : accès organisationnels effectifs sur la chaîne RFQ concernée.

Critère de sortie : un collègue habilité reprend le dossier ; une autre organisation ne peut consulter aucun contenu privé en connaissant un identifiant, par API, export, calcul ou recherche. Les droits sont recontrôlés lors des actions effectives.

## Lot 2 Relations RFQ et destinataires

État réalisé : [rapport du lot 2](RFQ_NETWORK_LOT_2_IMPLEMENTATION_2026-10-12.md). Annuaire local des organisations et desks, reconnaissance bilatérale versionnée, suspension et filtres de périmètre raccordés au récapitulatif RFQ. Aucun envoi réel à ce stade.

### Travail à réaliser

Livrer une rubrique Relations RFQ dans l'administration de chaque organisation. Chaque relation identifie organisation partenaire, entité juridique, desk destinataire, contacts, périmètre, autorisation de solliciter, autorisation de traiter, état et validité.

Prévoir la reconnaissance de la relation par les deux parties, le rapprochement explicite avec les contreparties locales et l'historique des changements. Les habitudes CRM restent informatives. Une identité réseau ne se déduit pas d'un simple nom de fournisseur.

### Livrable et critère de sortie

Livrable : annuaire de partenaires autorisés propre à chaque organisation.

Critère de sortie : deux organisations disposent de listes différentes ; un partenaire hors périmètre ne peut être sollicité en contournant l'écran. Une suspension conserve l'historique et empêche les nouvelles actions concernées.

## Lot 3 Demande versionnée et envoi explicite

Implémentation locale : [note de livraison et limites](RFQ_NETWORK_LOT_3_IMPLEMENTATION_2026-10-12.md). L’envoi, le tour figé, le suivi individuel et la réception/lecture minimale côté banque sont persistants. Les nouveaux tours utilisent des dossiers liés pour garder les anciennes réponses intactes. La recette HTTP authentifiée passe ; la recette navigateur a été bloquée par l’outil.

### Travail à réaliser

Ajouter la préparation des destinataires, le récapitulatif exact de la demande et l'action Envoyer la RFQ. Produire la projection autorisée des termes du Product avec une référence d'échange, un tour et une version identifiables.

Séparer la préparation d'un destinataire de sa sollicitation effective. Le premier acte de sollicitation manuelle ou réseau fige les termes du tour. Une modification matérielle ouvre un nouveau tour lié au précédent. Ajouter un destinataire pendant un tour ouvert conserve les mêmes termes et la même échéance.

Suivre chaque livraison indépendamment de l'état métier de l'AO. Aucune information concurrentielle ou hypothèse privée ne part avec la demande.

### Livrable et critère de sortie

Livrable : envoi traçable d'un contrat précis à chaque destinataire autorisé.

Critère de sortie : les banques retrouvent la même définition et le même calendrier, sans ressaisie ni valeurs contractuelles inventées ; les différences d'identifiants locaux sont reliées à l'identité d'échange commune.

## Lot 4 Réception bancaire et pricing privé

La [tranche prise en charge et pricing privé](RFQ_NETWORK_LOT_4_IMPLEMENTATION_2026-10-12.md) est codée : file de desk, responsable/réaffectation, Product bancaire aux termes reçus figés, ouverture native dans le Pricer, calcul et conservation privés. Recette API authentifiée réussie, recette visuelle bloquée par l’outil. Précisions, déclin et contre-propositions restent à compléter ; le lot 5 porte la publication humaine.

### Travail à réaliser

Livrer RFQ reçues, file de desk, prise en charge et échanges de précision. Permettre le déclin ou l'ouverture du produit demandé dans le Pricer bancaire.

Verrouiller les termes reçus et préserver la liberté des hypothèses de marché et du modèle bancaire. Utiliser d'abord les données présentes localement. Signaler une version non prise en charge ou un calendrier inexploitable ; une contre-proposition expose ses différences et ne réécrit pas la demande.

### Livrable et critère de sortie

Livrable : boîte de réception et ouverture native dans le Pricer.

Critère de sortie : un structureur reçoit, prend en charge et price le produit exact sans le reconstruire. Les calculs et marges d'une banque restent invisibles aux autres parties.

## Lot 5 Validation humaine et publication bancaire

La [livraison locale du lot 5](RFQ_NETWORK_LOT_5_IMPLEMENTATION_2026-10-12.md) ajoute préparation commerciale, droits explicites de validation/publication, politique de desk à seconde validation configurable et fraîcheur explicite, validation du contenu exact, publication/livraison atomiques dans la même installation, révisions et retrait tracé. Le demandeur reçoit une quote réseau non éditable dans sa table existante. Le booking réseau attend la confirmation du lot 7. La recette API authentifiée passe ; la recette visuelle reste bloquée par l’outil.

### Travail à réaliser

Distinguer résultat du pricing interne et prix commercial proposé. Relier la préparation au calcul privé et contrôler version du produit, cohérence, unité, nominal, devise, sens, validité, fermeté, documentation et conditions.

Livrer Valider et publier pour l'utilisateur habilité et le circuit à seconde validation lorsqu'il est configuré. Toute modification du contenu validé impose un nouveau contrôle. Publication, révision et retrait sont des événements conservés.

Appliquer la fermeté actée : retrait avant réception d'une acceptation valide seulement ; prix réservé ensuite ; contestation explicite en cas d'erreur après acceptation. La publication ne diffuse pas le reçu détaillé de pricing.

### Livrable et critère de sortie

Livrable : réponse publiée attribuable et versionnée, avec contenu commercial contrôlé.

Critère de sortie : le prix publié correspond au récapitulatif validé. Une préparation périmée ou portant sur d'autres termes ne peut pas être publiée comme conforme. Les conditions de retrait et l'ordre acceptation/retrait sont opposables au workflow.

## Lot 6 Retour automatique et reprise des échanges

### Réalisation du 12/10

Le [lot 6 réalisé](RFQ_NETWORK_LOT_6_IMPLEMENTATION_2026-10-12.md) apporte l’appairage par organisation, HTTPS et signatures de messages/accusés, files persistantes, baux de reprise, dédoublonnage et séquences par demande. Demandes, lectures, publications, retraits et clôtures circulent entre deux bases indépendantes, sans partager le pricing privé. Les masques montrent les tentatives, les blocages et la réception confirmée, avec relance habilitée.

La recette HTTP a arrêté puis redémarré les deux installations avant de recevoir la demande et son prix. Les contrôles visuels confirment une page de hauteur fixe et le défilement interne. Les cotations devenues caduques reviennent comme historique ou font l’objet d’une annulation de remise ; elles ne deviennent jamais exécutables par la reprise. L’acceptation et la confirmation restent au lot 7 ; aucune installation BNP réelle n’est appairée.

### Travail à réaliser

Acheminer demandes, cotations et autres messages vers les bons dossiers et versions. Conserver publication, livraison, réception et résultats métier comme faits distincts.

Gérer interruptions, retransmissions, doublons, ordre des révisions, annulations, réponses tardives et accusés perdus. Une préparation conservée seulement chez la banque reste en attente de publication ; une réponse acceptée par le canal peut rester en attente de livraison.

La reprise recontrôle droits, relation, termes, délai et validité. Elle ne fabrique ni prix ni réussite. Une banque indisponible n'est pas qualifiée comme ayant décliné.

### Livrable et critère de sortie

Livrable : transmission persistante avec suivi, accusés et reprise.

Critère de sortie : après une coupure ou un redémarrage, chaque événement retrouve le bon dossier sans doublon ni remplacement par une ancienne révision. Un retrait ou une acceptation ne se décide pas selon l'ordre d'affichage dans un navigateur.

## Lot 7 Comparaison mixte et booking local

La [tranche confirmation et booking unique du lot 7](RFQ_NETWORK_LOT_7_IMPLEMENTATION_2026-10-12.md)
ajoute une demande externe déclarée, l’accord exact consigné, la validité contrôlée
à la réception d’acceptation, le booking idempotent et la conservation des blocages.
Le manuel reste disponible. Les messages natifs de traitement, la résolution des
contestations et le rapprochement explicite des réponses manuel/réseau restent des compléments.

### Travail à réaliser

Réunir les réponses manuelles et réseau dans la comparaison existante avec origine visible. Préserver le contenu publié par la banque et séparer annotations du demandeur et modifications autorisées. Rapprocher explicitement une réponse saisie par téléphone et son équivalent reçu ensuite par réseau.

Conserver sélection motivée, révisions et last look sans déplacement automatique du choix du desk ni divulgation implicite des concurrents. Les contre-propositions sont séparées du classement conforme.

Livrer la consignation de l'accord avant booking : confirmation reçue de la banque ou accord téléphonique déclaré, avec termes, prix, nominal, parties, heure, source et référence d'exécution. Adapter le contrôle de validité à l'heure de réception de l'acceptation. Un accord confirmé peut être inscrit après expiration de la cotation d'origine sans prorogation artificielle.

Préserver les contrôles Product, reçus de pricing locaux, contrepartie, CCR et audit. Si un contrôle local bloque l'inscription d'un traitement confirmé, conserver l'accord et le blocage comme tels ; aucune nouvelle demande de traitement automatique. Une référence d'exécution ne crée qu'un booking par organisation.

### Livrable et critère de sortie

Livrable : comparaison commune, preuve d'accord et passage contrôlé au booking local.

Critère de sortie : un AO mixte fonctionne sans double comptage, écrasement de publication ou création automatique de Deal. Un traitement confirmé reste identifiable avant son booking et lorsqu'une inscription est bloquée. Booké localement ne vaut pas rapproché avec la banque.

## Lot 8 Recette et ouverture progressive

### Réalisation clôturée le 13/10

La [recette V1 du lot 8](RFQ_NETWORK_LOT_8_ACCEPTANCE_2026-10-13.md) est qualifiée
sur trois installations fictives isolées : 16 scénarios API distincts réussis,
aller-retour et booking unique, comparaison mixte, seconde validation, suspension
et maintien du manuel. Les masques ont un scroll interne mesuré en bureau et sur
écran étroit. Deux refus/affichages ont été corrigés, avec 19 tests ciblés réussis.
Le script de recette et la [procédure d'exploitation/reprise](RFQ_NETWORK_OPERATIONS_2026-10-12.md)
sont livrés. L'ouverture progressive à une véritable banque reste conditionnée
aux participants, accords, accès HTTPS, appairage et recette bilatérale ; aucun
canal réel n'est configuré. Les compléments des lots antérieurs restent identifiés.

### Travail à réaliser

Qualifier des organisations fictives dans des environnements isolés du travail réel. Exercer les parcours du demandeur et de chaque banque, les droits et les scénarios de panne, révision, retrait, acceptation et confirmation de la spécification.

Commencer par un aller-retour court avec une banque, puis deux banques et une réponse manuelle. Ouvrir ensuite à quelques relations désignées. Prévoir la suspension du canal connecté, la consultation des preuves et la poursuite du manuel.

### Livrables et critère de sortie

Livrables : rapport de recette par scénario, procédure d'exploitation et procédure de reprise.

Critère de sortie : parcours complet démontré, refus explicites, cohérence des versions, confidentialité et absence de perte ou de double traitement. Les contrôles et mesures restant ouverts sont conservés séparément des scénarios réussis.

## Ordre de livraison et dépendances

| Étape | Dépendances |
| --- | --- |
| Lot 0 | Cadrage métier consolidé et premier prototype interactif livré ; compléments d'écran et choix de pilote à finaliser. |
| Lot 1 | Propriété des nouveaux dossiers, habilitations et partage explicite par desk ; aucune migration historique. |
| Lot 2 | Identités et habilitations fiables du lot 1. |
| Lot 3 | Relations reconnues, contrat de demande et termes canoniques. |
| Lot 4 | Réception d'une demande compatible ; préparation possible en parallèle des parcours d'envoi. |
| Lot 5 | Pricing privé et contrat de réponse ; circuit humain défini. |
| Lot 6 | Transport signé et reprise réalisés sur deux installations fictives ; exploitation HTTPS du pilote à configurer et qualifier. |
| Lot 7 | Provenance des réponses, état courant et preuve d'accord fiables. |
| Lot 8 | Parcours complet sur environnements fictifs, avec mécanisme de reprise. |

Les maquettes des deux interfaces et les scénarios métier peuvent avancer pendant la conception du contrat d'échange. L'ouverture aux utilisateurs dépend des contrôles d'accès, de la remise persistante des messages et de la recette applicable.

## Matrice minimale de recette

| Scénario | Résultat attendu |
| --- | --- |
| Listes différentes selon l'organisation | Chaque demandeur sollicite ses partenaires autorisés uniquement. |
| Même Athena chez deux banques | Termes et calendrier identiques, hypothèses et calculs privés distincts. |
| Déclin bancaire | Déclin explicite sans prix inventé. |
| Prix préparé sans publication | Aucun prix communiqué au demandeur. |
| Modification après validation | Validation à refaire. |
| Seconde validation configurée | Le préparateur ne peut valider sa propre préparation. |
| Publication et panne | Reprise avec accusé, sans doublon. |
| Révisions reçues dans le désordre | Version actuelle identifiée ; anciennes publications consultables. |
| Termes modifiés après sollicitation | Nouveau tour ; anciennes réponses rattachées aux anciens termes. |
| Retrait avant acceptation valide | Retrait motivé et communiqué ; aucune nouvelle acceptation sur ce prix. |
| Acceptation valide avant retrait | Prix réservé ; retrait RFQ refusé ; confirmation attendue. |
| Ordre contesté d'événements externes | Revue manuelle, aucune priorité inventée. |
| Accord avant expiration et booking ultérieur | Inscription possible sur l'accord figé, sans prolonger la quote. |
| Traitement demandé sans confirmation | Attente explicite ; aucun ordre ou booking répété automatiquement. |
| Téléphone puis publication réseau du même prix | Rapprochement explicite et origine conservée. |
| Cotation à une consultation clôturée | Historique, sans activation dans la comparaison. |
| Relation suspendue ou droits révoqués | Nouvelles actions concernées refusées ; historique conservé. |
| Accès à une autre organisation | Refus sans exposition de données privées. |
| Reprise par un collègue | Continuité du dossier selon ses droits, auteurs conservés. |
| Réseau suspendu | Parcours manuel et consultation des preuves utilisables. |
| Même exécution enregistrée deux fois | Un seul booking par organisation, conflit explicite si le contenu diffère. |
| Une seule partie bookée | État local exact ; aucun rapprochement bilatéral annoncé. |

## Choix restant à arrêter avant réalisation

Les arbitrages de fermeté, de retrait et de confirmation sont intégrés à la spécification. La visibilité par desk et l'absence de migration historique sont actées au lot 1. Restent le déploiement du pilote, l'identité et les desks des participants, le cas Athena exact, les paramètres opérationnels de validité/fraîcheur et les modalités de mise en oeuvre des habilitations.

La relation bilatérale devra reprendre explicitement la fermeté révocable avant acceptation, le canal de réception faisant foi, les conditions publiées et la procédure de contestation. Les messages natifs de traitement et le rapprochement des books relèvent de la tranche suivante ; la preuve externe de l'accord permet la V1.

## Documents de référence

- [Spécification fonctionnelle du lot 0](RFQ_NETWORK_LOT_0_SPECIFICATION_2026-10-12.md).
- [Premier prototype du lot 0](RFQ_NETWORK_LOT_0_IMPLEMENTATION_2026-10-12.md), réalisation et limites.
- [Propriété et habilitations du lot 1](RFQ_NETWORK_LOT_1_SPECIFICATION_2026-10-12.md).
- [Organisations, admission et accès](ORGANIZATION_ACCESS_DESIGN_2026-09-24.md).
- [Objet Product](PLAN_IMPLEMENTATION_OBJET_PRODUCT.md).
- [Besoin inter-entités initial](INTER_ENTITY_RFQ_BACKLOG_2026-10-08.md), conservé pour le contexte de simulation.
- [Doctrine Clients](../clients/CLIENTS_LOT_0_DOCTRINE_METIER.md) et [habitudes de trading](../clients/CLIENTS_LOT_2_HABITUDES_TRADING.md), pour distinguer préférence et autorisation.
- [CCR](../pricing/CCR_IMPLEMENTATION_2026-09-28.md), pour les contrôles locaux à conserver.
- [Tests restants de simulation et matrice du futur réseau](AGENT_SIMULATION_TESTS_RESTANTS_2026-10-12.md), pour l'intégration ultérieure de la recette réseau dans le pilote IA.

Les vérifications de réalisation devront être ciblées sur les domaines modifiés et leurs invariants. Toute modification Vue demandera le build frontend prévu par CLAUDE.md. Une mise à jour documentaire seule ne déclenche aucun pytest ni build.
