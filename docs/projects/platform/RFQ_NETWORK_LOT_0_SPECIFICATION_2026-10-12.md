# Spécification fonctionnelle du lot 0 du réseau RFQ Structura

Date : 12/10/2026. Version : 2.

Statut : décisions fonctionnelles consolidées et règles de fermeté, retrait et confirmation actées avec Philippe. Implémentation et recette à réaliser selon le [plan de réalisation](RFQ_NETWORK_ACTION_PLAN_2026-10-12.md).

Premier incrément du 12/10 : les parcours demandeur et banque disposent d'un [prototype interactif local](RFQ_NETWORK_LOT_0_IMPLEMENTATION_2026-10-12.md), sans réseau, habilitations métier persistantes ni booking réel. Il ne constitue pas la réalisation complète de la cible décrite ci-dessous.

Le réseau RFQ permet à une organisation utilisatrice de Structura de consulter ses partenaires autorisés. Chaque banque reçoit les mêmes termes contractuels, les price avec ses propres hypothèses privées et contrôle humainement le prix commercial avant publication. La réponse revient automatiquement dans la RFQ du demandeur. Les réponses saisies manuellement restent disponibles et comparables selon leur provenance et leurs conditions.

La définition du payoff et de ses calendriers doit rester identique entre les parties. Le produit demandé, les conditions propres à l'émetteur, le calcul privé et l'exécution sont identifiables séparément. Deux émetteurs peuvent proposer le même payoff sans émettre un instrument juridiquement identique.

## 1 Décisions et périmètre

### 1.1 Décisions actées

| Sujet | Règle |
| --- | --- |
| Organisation | Propriétaire des dossiers et de sa liste de partenaires ; distincte d'une fiche Client du CRM. |
| Banque répondante | Utilise Structura pour recevoir et pricer ; décide du prix commercial publié. |
| Publication | Humaine et réservée à un utilisateur habilité ; retour du prix automatique. |
| Validation | Le même utilisateur habilité peut calculer, contrôler et publier. Une seconde validation peut être configurée par organisation. |
| Manuel | Maintenu dans le même module, y compris sur un AO mixte. |
| Confidentialité | Chaque partie conserve ses marchés, modèles, calculs, marge, CRM et book privés. |
| Fermeté | Prix exécutable sur les termes, le demandeur, le nominal, la devise et les dates publiés tant que la cotation reste active. |
| Retrait ferme | Autorisé avant réception d'une acceptation valide, avec motif et notification. Une acceptation valide réserve le prix au traitement. |
| Confirmation | Accord explicite consigné avant booking, reçu de la banque ou déclaré après téléphone par un utilisateur habilité. |
| Chronologie | Validité évaluée à la réception de l'acceptation. Expiration ultérieure de la quote ne rend pas caduc un accord confirmé. |
| Booking | Action locale distincte et contrôlée ; une référence d'exécution ne produit qu'un booking par organisation. |

Ces règles doivent être reprises dans la relation bilatérale : fermeté révocable avant acceptation, conditions publiées, canal de réception faisant foi et procédure de contestation. Elles constituent la politique opérationnelle de Structura ; les sources externes de la section 15 n'en constituent pas l'autorité.

### 1.2 Périmètre V1 et pilote proposé

La V1 échange une demande de prix en pourcentage du nominal avec tous les paramètres du payoff fixés. La banque répond sur la totalité du nominal. Les demandes de coupon ou participation à résoudre et les exécutions partielles sont prévues dans une étape ultérieure.

Le pilote proposé réunit une organisation demandeuse, deux banques connectées et une réponse manuelle supplémentaire sur un Athena à coupon fixé. Participants, cas exact, hébergement et paramètres opérationnels restent à arrêter avant réalisation. L'appartenance aux rôles demandeur et répondant dépend de l'opération : une même organisation peut exercer les deux.

La confirmation du traitement peut être obtenue hors réseau dans la V1. Les messages natifs d'acceptation et de confirmation de traitement et le rapprochement des books sont une tranche suivante. Le pilote doit déjà distinguer ces faits dans les dossiers locaux et leur preuve.

## 2 Objets métier et autorités

| Objet | Propriétaire et responsabilité |
| --- | --- |
| Product local | Dossier canonique de chaque organisation, avec termes versionnés, calculs privés et faits locaux. Les identifiants locaux des deux parties peuvent différer. |
| Demande partagée | Projection autorisée des termes et de l'intention commerciale du demandeur, avec identité d'échange commune et tour. |
| Sollicitation | Envoi individuel à une organisation et un desk, rattaché à une relation RFQ reconnue. |
| Travail bancaire | Affectation, hypothèses, calculs et préparation de prix privés. |
| Réponse publiée | Publication de la banque sur une demande et une version exactes ; prix commercial, conditions, validité et historique. |
| Acceptation | Volonté de traiter une réponse exacte, reçue par le canal convenu ; distincte d'une sélection interne. |
| Accord de traitement | Résultat économique confirmé, avec termes, prix, parties, taille, dates et preuve. |
| Booking local | Inscription du Deal selon les contrôles et droits de l'organisation. |
| Rapprochement | Vérification ultérieure des inscriptions des deux parties ; aucune déduction à partir d'un seul booking. |

Le réseau transmet une projection construite depuis Product. Il ne transmet pas le dossier complet, qui contient calculs, contexte commercial et concurrence. Aucun écran ne reconstitue une définition contractuelle concurrente du Product à partir d'un nom de produit ou d'un prix reçu.

Une organisation réseau, une entité juridique, un fournisseur de cotation et l'émetteur d'une note peuvent être différents. La relation et la réponse portent les identités pertinentes ; un nom identique n'est pas une preuve d'identité réseau.

## 3 Relations RFQ par organisation

La rubrique Relations RFQ appartient à l'administration de l'organisation utilisatrice. Elle s'appuie sur les référentiels et relations bilatérales déjà présents lorsque leur périmètre convient.

| Information | Règle fonctionnelle |
| --- | --- |
| Organisation partenaire | Identité reconnue par le réseau, différente d'un libellé libre de fournisseur. |
| Entité juridique | Contrepartie concernée et rapprochement explicite avec le référentiel local. |
| Desk de réception | Boîte de réception désignée chez le partenaire. |
| Contacts | Interlocuteurs partagés pour cette relation ; aucun accès métier accordé par leur seule présence. |
| Périmètre | Formats, instruments, familles, devises et éventuelles tailles autorisées. |
| Sollicitation | Autorisation distincte de demander un prix. |
| Traitement | Autorisation distincte d'exécuter, avec documentation et contrôles applicables. |
| Dates | Effet et expiration de la relation lorsqu'elles existent. |
| État | En attente de reconnaissance, active, suspendue ou expirée. |
| Historique | Auteur, date, version et motif des changements matériels. |

Préparer une relation ne l'active pas. Chaque partie la reconnaît selon ses habilitations. Une relation peut permettre un indicatif tout en restant insuffisante pour traiter.

Les partenaires proposés pour une demande sont filtrés sur la relation et son périmètre courant. Une exclusion est explicable dans l'administration. Les habitudes de trading et préférences CRM sont informatives ; elles ne créent ni ne retirent d'autorisation.

La suspension bloque les nouvelles actions concernées et conserve l'historique. Un traitement déjà confirmé reste un fait économique à suivre ; sa disparition ou annulation ne se déduit pas d'une suspension administrative.

## 4 Parcours écran du demandeur

| Écran ou étape | Informations et actions |
| --- | --- |
| RFQ émises | Référence, produit, nominal, indicatif/to trade, état métier, suivi des réponses et responsable. Créer, ouvrir, filtrer, dupliquer. |
| Préparation du produit | Economics, panier, paramètres effectifs, dates, calendrier, format et instrument. Contrôler les termes depuis un modèle, un script qualifié ou un Product existant. |
| Destinataires | Relations autorisées et desks de réception. Préparer les banques connectées et ajouter des fournisseurs manuels. |
| Récapitulatif d'envoi | Contenu effectivement communiqué, version, sens, nominal, prix demandé, délai et destinataires. Action Envoyer la RFQ. |
| Suivi des sollicitations | État par destinataire, accusés, prise en charge et échanges. Répondre à une précision ou retirer une sollicitation autorisée. |
| Comparaison | Prix, origine, dates, validité, fermeté, conditions et écart au modèle privé du demandeur. Retenir, désélectionner, demander une révision ou un last look. |
| Préparation du traitement | Réponse exacte, termes, contrepartie et contrôles. Demander le traitement puis consigner son résultat avant booking. |
| Historique | Tours, messages, réponses, acceptation, confirmation, refus et liens vers les inscriptions locales. |

La préparation de destinataires réseau n'est pas une sollicitation. Le nom interne et l'intitulé partagé sont distincts ; le nom de l'investisseur final n'est jamais ajouté automatiquement.

Le premier acte de sollicitation effective, manuel ou réseau, fige les termes du tour. Une modification matérielle ouvre un nouveau tour lié au précédent. Ajouter une banque pendant un tour ouvert conserve les mêmes termes et la même échéance, avec un envoi explicite et tracé ; les autres banques ne reçoivent pas la liste des participants.

Une correction purement informative se fait par un échange identifié. Un commentaire ne modifie jamais implicitement un coupon, une date ou une condition matérielle. Une modification du délai publié ouvre un nouveau tour en V1.

Le demandeur peut sélectionner un prix différent du meilleur et conserver un motif facultatif. La sélection reste locale et ne réserve pas à elle seule le prix. Une révision bancaire ne déplace pas automatiquement cette sélection.

| Qualification de réponse | Présentation au demandeur |
| --- | --- |
| Conforme et active | Comparaison avec les réponses portant sur les mêmes termes, taille et convention. |
| Indicative | Qualification visible ; aucun engagement ferme inventé. |
| Conditionnelle | Conditions visibles et comparabilité à examiner. |
| Contre-proposition | Différences exposées, séparées du classement des réponses conformes. |
| Expirée, retirée ou remplacée | Historique consultable ; aucune nouvelle acceptation sur une réponse inactive. |
| Saisie manuellement | Origine, auteur et date de saisie visibles. |

Le meilleur prix est un fait de comparaison sur les réponses éligibles selon leur état courant. Le fournisseur, la contrepartie juridique et l'émetteur restent visibles pour ne pas assimiler des risques d'émetteur différents à des instruments identiques.

## 5 Parcours écran de la banque

| Écran ou étape | Informations et actions |
| --- | --- |
| RFQ reçues | Demandeur, référence, produit, nominal, sens, échéance, état et responsable. File commune au desk. |
| Prise en charge | Attribution à un collaborateur habilité ; la responsabilité est visible à l'équipe. |
| Détail de demande | Termes et calendrier exacts, convention de prix, documentation et échanges. Demander une précision, décliner ou ouvrir dans le Pricer. |
| Pricer bancaire | Termes reçus verrouillés ; marchés, modèle et paramètres privés modifiables. Réutiliser les données locales avant un re-fetch externe. |
| Préparation de réponse | Résultat interne distinct du prix commercial, validité, fermeté, documentation et conditions. Aucun envoi à ce stade. |
| Contrôle avant publication | Récapitulatif exact, contrôles et référence du calcul privé. Valider et publier ou soumettre à seconde validation. |
| Réponse publiée | Version, heure, validité et suivi de livraison. Préparer une révision ou retirer lorsque les conditions l'autorisent. |
| Historique | Affectations, précisions, calculs privés, validations et publications. |

La banque price les termes reçus sans les ressaisir et sans appliquer des valeurs contractuelles locales par défaut. Une définition ou version non prise en charge et un calendrier inexploitable sont signalés explicitement.

Un changement de payoff prépare une contre-proposition. Une précision du demandeur qui change le contrat conduit à un nouveau tour. La banque peut décliner sans fournir de prix ; elle peut laisser le motif commercial non communiqué.

Le prix théorique et le prix commercial sont conservés séparément. La modification du prix commercial ne réécrit pas le résultat du moteur. Une modification des hypothèses privées ne modifie pas une publication déjà faite : une nouvelle publication ou un retrait autorisé est nécessaire.

### 5.1 Contrôles de publication

Les contrôles vérifient droits, relation, compatibilité de version, état du tour, délai, cohérence du calcul privé utilisé, prix numérique et convention, nominal, devise, sens, durée de validité, fermeté, documentation et conditions. Aucun champ matériel ne dépend uniquement d'un commentaire libre.

Une préparation sur un calcul ou des termes dépassés n'est pas publiable comme conforme. Les durées de fraîcheur du calcul et de validité de quote appartiennent à la politique explicite de la banque ; elles sont définies avant réalisation du pilote et ne deviennent pas des constantes matérielles cachées.

### 5.2 Validation humaine

Sans seconde validation configurée, un utilisateur habilité peut calculer, contrôler puis publier. Lorsque la politique l'exige, un autre utilisateur habilité valide la préparation avant publication ; le préparateur ne peut valider sa propre réponse.

La validation porte sur le contenu exact à publier. Changer prix, taille, validité, conditions ou termes invalide cette validation. La publication recontrôle droits et préconditions au moment effectif.

Une préparation stockée seulement chez la banque reste en attente de publication. Publiée signifie acceptée par le canal d'échange avec une référence et un horodatage ; reçue signifie enregistrée chez le demandeur. La livraison peut encore être en cours après publication.

## 6 Contenu des demandes

Chaque demande est adressée individuellement. Tous les destinataires d'un tour reçoivent les mêmes termes ; seules les informations d'adressage et de relation diffèrent. Les références locales restent reliées à la référence d'échange commune.

Obligatoire signifie requis avant envoi. Conditionnel signifie requis lorsque le cas s'applique.

| Bloc | Contenu | Présence |
| --- | --- | --- |
| Échange | Référence commune, tour, lien au tour précédent le cas échéant. | Obligatoire. |
| Message | Identifiant de message, type et version du format. | Obligatoire ; réutilisé pour une retransmission identique. |
| Termes | Version des termes et empreinte de la définition transmise. | Obligatoire. |
| Demandeur | Organisation, entité juridique concernée, desk et interlocuteur partagé. | Obligatoire. |
| Destinataire | Organisation, desk, relation RFQ reconnue. | Obligatoire. |
| Publication | Date et heure de publication de la demande. | Ajoutée par le système. |
| Intitulé | Description partagée courte, distincte du nom privé du dossier. | Obligatoire. |
| Nature | Indicatif ou to trade. | Obligatoire. |
| Sens | Achat ou vente du côté du demandeur. | Obligatoire ; perspective explicite. |
| Grandeur demandée | Prix en pourcentage du nominal. | Fixée pour la V1. |
| Taille | Nominal exact et devise de règlement. | Obligatoire ; totalité en V1. |
| Délai | Date et heure limite de publication des réponses. | Obligatoire. |
| Format | Format juridique et famille d'instrument. | Obligatoire selon le produit. |
| Documentation | Exigences documentaires et références partagées nécessaires. | Conditionnel. |
| Modèle de produit | Identité et version du modèle qualifié, PayScript correspondant et version compatible de sa sémantique. | Obligatoire. |
| Paramètres | Noms, valeurs effectives, unités, forme scalaire ou série et ordre des valeurs. | Obligatoire ; aucun défaut requis laissé implicite. |
| Panier | Instruments identifiés, place de cotation, devise et rôle dans le panier. | Obligatoire ; alias marché locaux possibles sans changement d'instrument. |
| Dates | Fixing initial, valeur, maturité et paiements applicables. | Obligatoire. |
| Calendrier | Observations et événements résolus, paiements, conventions, décalages et fenêtres applicables. | Obligatoire. |
| Fixings | Convention et source contractuelles ; niveaux déjà fixés et provenance lorsqu'ils sont nécessaires. | Conditionnel. |
| Commentaire | Précisions complémentaires destinées à cette banque. | Facultatif ; aucun changement contractuel implicite. |

### 6.1 Unités et conventions

Un paramètre contractuel en pourcentage porte son unité et sa valeur commune : un coupon de 8 % correspond à 0,08 dans les unités de calcul. Un prix publié de 98,45 signifie 98,45 % du nominal. Une série conserve son ordre contractuel et son rattachement aux observations.

Les dates contractuelles sont civiles. Les heures de publication, réception, expiration et accord sont conservées en UTC et affichées dans le fuseau de l'utilisateur. La chronologie métier ne dépend pas de l'horloge d'un navigateur.

Le strike ancre les temps contractuels. Maturité et paiement restent distincts ; le calendrier transmis conserve la date de chaque règlement applicable. Une date ou valeur manquante n'est pas inventée à réception. Les dates effectives et leur convention sont identifiables.

Le prix demandé dans le pilote est all-in, incluant les frais facturés au demandeur. Des frais supplémentaires rendent la réponse conditionnelle et empêchent un classement automatique comme prix équivalent.

### 6.2 Données privées

La demande ne contient pas le dossier Product complet, le CRM ou l'identité de l'investisseur final par défaut, les autres destinataires, leurs réponses, les books, les courbes de marché, volatilités, corrélations de pricing, funding, modèles, réglages numériques, résultats privés ou marge cible.

Une donnée de marché entre dans la définition commune seulement lorsqu'elle constitue un terme ou un fixing contractuel nécessaire. L'empreinte des termes, celle d'un calcul privé et celle d'une exécution ont des périmètres distincts ; une égalité d'empreinte ne remplace pas les droits ou une preuve d'origine.

## 7 Contenu des réponses et autres messages

| Bloc | Contenu de cotation | Présence |
| --- | --- | --- |
| Réponse | Référence de réponse, révision et réponse précédente remplacée le cas échéant. | Obligatoire. |
| Message | Identifiant, type, version du format. | Obligatoire. |
| Demande | Référence commune, tour, version et empreinte des termes effectivement cotés. | Obligatoire. |
| Organisation | Organisation répondante et desk. | Obligatoire. |
| Parties juridiques | Contrepartie du traitement, émetteur de note et garant le cas échéant. | Obligatoire selon l'instrument. |
| Auteur | Utilisateur habilité qui publie et interlocuteur partagé. | Conservé avec la publication. |
| Publication | Date et heure de publication effective. | Ajoutée par le système. |
| Nature | Conforme ou contre-proposition. | Obligatoire. |
| Prix | Valeur numérique finie et positive en pourcentage du nominal, convention all-in. | Obligatoire pour une cotation. |
| Taille | Nominal exact couvert et devise de règlement. | Obligatoire ; totalité du nominal en V1. |
| Fermeté | Indicative ou ferme. | Choix explicite de la banque. |
| Validité | Date et heure d'expiration. | Obligatoire pour une réponse réseau ; postérieure à publication. |
| Conditions | Absence explicite de condition ou conditions structurées et description. | Obligatoire. |
| Documentation | Format proposé, références documentaires et identité d'émetteur applicables. | Selon l'instrument. |
| Contre-proposition | Termes proposés et différences par rapport à la demande. | Conditionnel ; classement séparé. |
| Commentaire | Précision commerciale partagée. | Facultatif. |
| Réception | Date et heure d'enregistrement chez le demandeur. | Ajoutée à réception. |

L'expiration est conservée telle que publiée. La banque peut proposer une durée issue de sa politique avant validation ; le demandeur ne lui ajoute pas une durée supposée. Les champs publiés ne sont pas éditables par le demandeur.

Le résultat théorique, les données, les paramètres numériques, les calibrations, les Greeks, la marge interne, la validation privée et le reçu détaillé de pricing restent chez la banque. Le demandeur conserve ses propres calculs et contrôles locaux.

| Message | Contenu nécessaire |
| --- | --- |
| Déclin | Demande et tour, organisation, auteur, heure, motif communiqué ou motif non communiqué. |
| Demande de précision | Demande et tour, question, auteur et heure. |
| Réponse à une précision | Question concernée, réponse, auteur, heure et indication d'un nouveau tour si les termes changent. |
| Retrait de cotation | Réponse et révision exactes, auteur, heure et motif ; condition d'absence d'acceptation valide. |
| Annulation de sollicitation | Demande et tour, destinataire, auteur, heure et motif applicable ; traitements reçus préservés. |
| Clôture de consultation | Demande et tour, état de clôture, auteur et heure ; aucune identité ou cotation concurrente divulguée automatiquement. |
| Accusé de réception | Message concerné, destinataire, heure et résultat d'enregistrement. |
| Demande de last look | Réponse initiale, demande explicite, échéance et éventuelle information concurrentielle volontairement communiquée. |
| Acceptation de traitement | Demande, réponse et révision, termes, parties, sens, taille, devise et prix acceptés, auteur et réception par le canal convenu. Preuve externe en V1, message natif dans la tranche suivante. |
| Résultat de traitement | Référence commune d'exécution, accord ou refus explicite, termes économiques et heure, parties, auteur et source. Consignation externe en V1. |

Une retransmission identique reprend son identité. Une révision matérielle est une nouvelle publication reliée à la précédente. Une cotation sur d'autres termes est une contre-proposition, même si son prix paraît meilleur.

## 8 Droits et visibilité

Les habilitations sont rattachées à l'organisation et au desk applicable. Une personne peut cumuler des fonctions autorisées. L'administration des utilisateurs n'accorde pas automatiquement un pouvoir de publication ou de booking.

Précision actée au [lot 1](RFQ_NETWORK_LOT_1_SPECIFICATION_2026-10-12.md) : la visibilité est limitée au desk pilote par défaut, avec partage explicite vers les autres desks. Les nouveaux dossiers sont le périmètre de réalisation ; aucune migration des dossiers existants de test n'est demandée.

| Action | Habilitation | Limite |
| --- | --- | --- |
| Gérer utilisateurs et droits | Administration de l'organisation. | Aucun droit métier implicite. |
| Préparer ou modifier une relation RFQ | Administration des relations. | Reconnaissance du partenaire et historique. |
| Préparer une demande | Préparation RFQ. | Dossiers autorisés de son organisation et desk. |
| Envoyer ou annuler une sollicitation | Envoi RFQ. | Relation, état et périmètre valides. |
| Comparer et sélectionner | Sélection RFQ. | Réponses reçues par son organisation. |
| Saisir une réponse manuelle | Saisie RFQ. | Origine et auteur conservés. |
| Prendre en charge et pricer | Préparation de cotation. | Demande adressée à sa banque et son périmètre. |
| Valider | Validation de cotation. | Politique de seconde validation appliquée. |
| Publier, réviser ou retirer | Publication de cotation. | Réponse propre, préconditions de publication ou de retrait. |
| Accepter un traitement | Traitement RFQ. | Relation de traitement et réponse exacte ; distinct de la sélection. |
| Consigner une confirmation externe | Confirmation de traitement. | Source, interlocuteur, contenu et heure obligatoires. |
| Booker | Booking. | Contrôles locaux et accord requis. |
| Acheminer et accuser réception | Service d'échange. | Aucune décision de prix, sélection, acceptation ou booking. |

Le demandeur voit ses calculs et toutes ses réponses autorisées. Une banque voit sa demande, son travail privé et ses publications. Elle ne voit ni concurrents, ni leurs prix, ni marge du demandeur. La sélection interne n'est pas annoncée automatiquement.

Une divulgation dans un last look est explicite et prévisualisée. Les accès aux historiques, exports, calculs et preuves suivent les mêmes périmètres. Le départ d'un utilisateur conserve les données dans leur organisation et révoque ses futures actions selon ses droits.

## 9 États indépendants et transitions

### 9.1 Déroulement de la demande

| Transition | Fait déclencheur et règle |
| --- | --- |
| Brouillon vers prête à envoyer | Contrôles complets ; indicateur dérivé. |
| Prête vers sollicitée | Première sollicitation effective, manuelle ou réseau ; gel des termes. |
| Sollicitée vers cotée | Première réponse avec un prix. |
| Cotée vers retenue | Sélection explicite d'une réponse éligible. |
| Retenue vers cotée ou à revoir | Désélection ou réponse devenue inutilisable avant acceptation. |
| Ouverte vers sans suite ou annulée | Décision explicite ; accords ou acceptations déjà reçus préservés. |
| Retenue vers bookée localement | Booking accepté et Deal identifié ; l'accord confirmé peut avoir précédé cette inscription. |

Les statuts historiques restent interprétés selon leur définition. Une RFQ manuelle rouverte garde son parcours actuel ; elle ne réactive pas automatiquement un tour réseau clôturé. Un nouveau tour est nécessaire. La clôture d'une consultation ne retire pas un traitement reçu ou confirmé.

### 9.2 Livraison et réception bancaire

| Objet | Transition | Règle |
| --- | --- | --- |
| Livraison | Préparée vers envoi en cours vers reçue | Envoi explicite puis accusé d'enregistrement distant. |
| Livraison | Envoi en cours vers à reprendre vers reçue | Incident puis retransmission du même message. |
| Réception | À traiter vers prise en charge | Attribution identifiée. |
| Réception | Prise en charge vers à préciser vers prise en charge | Question puis précision sur les mêmes termes. |
| Réception | À traiter ou prise en charge vers déclinée | Déclin explicite. |
| Réception | Prise en charge vers réponse publiée | Publication d'une réponse ; une révision reste possible selon son état. |

Un accusé ne prouve ni lecture par un collaborateur ni décision métier. Banque indisponible et banque ayant décliné sont des états différents. Une demande incompatible est reçue et signalée comme non prise en charge ; aucun succès de pricing n'est déduit de sa réception.

### 9.3 Préparation et publication

| Transition | Règle |
| --- | --- |
| Brouillon vers prête à publier | Calcul et contenu commercial contrôlés. |
| À valider vers validée | Seconde personne lorsque la politique l'exige. |
| Prête ou validée vers publication en attente | Action humaine, transmission ou acceptation du canal encore en cours. |
| Publication en attente vers publiée | Acceptation par le canal avec identité et heure de publication. |
| Préparation modifiée vers contrôle à refaire | Modification d'un élément validé. |

La reprise d'une publication en attente recontrôle droits, relation, tour, délai et validité. Une interruption ne prolonge pas artificiellement un prix. La date de publication authentifiée permet de distinguer une cotation publiée dans le délai mais reçue tardivement d'une préparation publiée après la limite.

### 9.4 Vie de la cotation

| Transition | Règle |
| --- | --- |
| Publiée vers active | Publication valide sur une consultation ouverte, conforme à ses conditions. |
| Active vers expirée | Échéance atteinte sans acceptation valide reçue. |
| Active vers remplacée | Nouvelle révision avec remplacement explicite, avant acceptation valide de l'ancienne ferme. |
| Active vers retirée | Retrait autorisé avant acceptation valide, motif et notification. |
| Ferme active vers réservée au traitement | Acceptation valide reçue avant expiration et avant retrait effectif. |
| Réservée vers traitement confirmé | Confirmation économique explicite ; le contenu accepté est figé. |
| Réservée vers contestation ou revue | Erreur déclarée, conditions non résolues ou résultat incertain ; aucun effacement ou nouveau prix silencieux. |

L'expiration de la période d'offre après acceptation valide ne libère pas automatiquement une cotation ferme réservée. L'écran conserve l'expiration d'origine et le fait d'acceptation. Une nouvelle sélection ne migre jamais implicitement vers une révision bancaire.

## 10 Fermeté et retrait

### 10.1 Portée de ferme

Ferme signifie prix exécutable pour le demandeur identifié, cette version du produit, le nominal entier, la devise et les dates publiés, tant que la réponse reste active, avec les seules conditions explicitement publiées. Une acceptation conforme n'ouvre pas une nouvelle négociation du prix.

Changer nominal, contrepartie concernée ou termes exige une nouvelle cotation et un nouvel accord. Indicative reste une qualification de la publication bancaire ; le demandeur ne peut pas la transformer en déclaration ferme de la banque.

### 10.2 Règles de retrait et de remplacement

| Situation | Décision |
| --- | --- |
| Ferme active, aucune acceptation reçue | Retrait explicite possible, avec motif et notification immédiate. |
| Nouvelle cotation avant acceptation | Remplacement explicite ; sélection du demandeur à revoir. |
| Acceptation valide reçue avant expiration et retrait | Prix réservé ; confirmation attendue ; retrait RFQ ordinaire refusé. |
| Acceptation reçue après expiration ou retrait | Nouvelle cotation nécessaire. |
| Erreur déclarée après acceptation valide | Contestation tracée, revue ; aucune suppression de l'acceptation ni substitution du prix. |
| Traitement confirmé | Correction distincte et gouvernée ; aucun retrait de l'accord par RFQ. |

Pour le réseau natif, l'ordre d'enregistrement faisant autorité détermine si une acceptation valide a précédé le retrait. Un clic sur un écran périmé ne suffit pas. Pour un échange externe dont l'ordre est contesté, la preuve est revue manuellement ; aucune priorité ne se déduit seulement d'une heure saisie ou d'un navigateur.

La validité et le délai de réponse sont indépendants. Une réponse publiée dans le délai peut rester active ensuite. Une réponse reçue après clôture reste historique. Une acceptation valide déjà reçue reste un fait même si sa confirmation est encore attendue à la clôture.

## 11 Confirmation du traitement et booking

La séquence visible est : réponse retenue, traitement demandé, traitement confirmé, booké localement. La sélection est locale. Demander le traitement exprime la volonté de traiter une réponse précise après contrôle des habilitations, de la relation et de sa validité. L'accord confirmé précède l'inscription dans le book.

### 11.1 Contenu de l'accord

| Information | Règle |
| --- | --- |
| Demande et cotation | RFQ, tour, référence et révision exacte de réponse. |
| Produit | Version et empreinte des termes convenus. |
| Parties et sens | Entités juridiques, demandeur/répondant et perspective de chaque partie. |
| Prix | Prix effectivement convenu et unité, incluant les frais selon la convention. |
| Taille | Nominal et devise convenus ; totalité en V1. |
| Dates | Dates contractuelles applicables. |
| Acceptation | Heure de réception par le canal convenu et source permettant le contrôle de validité. |
| Confirmation | Heure et contenu de l'accord d'exécution ; distincts de la date du booking. |
| Référence | Référence commune d'exécution ou référence externe identifiée, distincte des références locales de Deal. |
| Auteur et source | Interlocuteur bancaire, utilisateur qui consigne, mode de confirmation et preuve disponible. |

Si la banque propose un autre prix ou d'autres termes, un nouvel accord explicite est nécessaire. Le prix initial et les étapes de négociation restent dans la provenance. Aucun écart n'est corrigé en réécrivant la quote reçue.

### 11.2 Deux modes admis en V1

| Mode | Preuve et libellé |
| --- | --- |
| Confirmation reçue de la banque | Message Structura, courriel ou document identifiant clairement l'opération. Libellé confirmation reçue de la banque. |
| Accord téléphonique | Déclaration horodatée d'un utilisateur habilité, avec interlocuteur bancaire et tous les termes convenus. Libellé accord téléphonique déclaré ; confirmation écrite suivie ensuite. |

Le second mode ne se présente pas comme une attestation électronique de la banque. L'absence du document contractuel final peut être suivie après booking ; elle ne vaut pas absence d'accord économique confirmé. Le document final et son rapprochement doivent rester identifiables séparément.

Une déclaration confirmée n'est pas une simple réponse de prix ni un accusé de livraison. En cas d'absence de réponse ou de résultat incertain, traitement demandé avec confirmation attendue reste visible ; aucun second ordre ou booking automatique.

### 11.3 Validité à l'accord et inscription ultérieure

La validité de la cotation se contrôle à l'heure de réception de l'acceptation. Exemple fictif : acceptation valide reçue à 14 h 59, cotation expirant à 15 h, accord confirmé, booking à 15 h 05. L'inscription utilise l'accord figé et ne prolonge pas la quote d'origine.

Le portillon actuel vérifie la validité de quote au moment du booking. Son évolution doit séparer utilisation d'une offre active et inscription d'un traitement déjà confirmé. Elle exige la preuve de réception valide, l'accord exact et l'absence de modification des termes acceptés ; elle ne crée pas un contournement par simple saisie rétroactive d'heure.

Les contrôles Product, reçu de pricing local, contrepartie, CCR et audit restent applicables. Un accord confirmé dont le booking est bloqué reste confirmé avec inscription locale bloquée et motif. Il faut résoudre ce blocage ou la contestation par une action tracée ; aucune disparition du trade ni réémission automatique.

Une référence d'exécution ne crée qu'un booking par organisation. Répéter la même opération retrouve son résultat ; la même référence avec un autre contenu produit un conflit explicite. Booké localement reste distinct de booké par la banque et de rapproché entre les deux books.

## 12 Réponses manuelles et comparaison

Les réponses manuelles restent dans la même RFQ. Elles portent fournisseur, contact, prix, convention, réception déclarée, saisie, auteur, fermeté renseignée et validité. Une éventuelle validité proposée au desk reste identifiée comme une proposition ; elle n'est pas assimilée à une déclaration bancaire reçue.

Le demandeur peut annoter une réponse réseau ; prix, validité et fermeté publiés restent protégés. Une correction ou un accord ultérieur est conservé comme événement distinct. L'acte local de booking peut documenter la confirmation de traitement sans réécrire la qualification bancaire d'origine.

Si un prix reçu par téléphone est ensuite reçu par réseau, les deux preuves sont conservées et le rapprochement est explicite. Une seule réponse active du fournisseur est retenue pour le comparatif ; la sélection n'est pas déplacée automatiquement. Un prix différent déclenche une revue ou une nouvelle cotation, jamais une fusion silencieuse.

Le classement conforme exige même définition, même nominal, même devise, même sens et convention compatible. Les différences d'émetteur, de documentation et les conditions restent visibles. Les réponses remplacées, retirées, expirées ou tardives à un tour clos n'entrent pas dans les nouvelles sélections ; les accords déjà confirmés restent consultables avec leur état à l'accord.

Un last look conserve la réponse initiale et crée une contre-cotation liée. Il améliore ou égale le prix initial dans le sens de l'AO. Une réponse moins bonne liée à un mouvement de marché est identifiée comme une nouvelle cotation. Les statistiques ne comptent pas deux fois une banque pour la même réponse finale, et une sélection seule ne vaut pas un AO gagné.

## 13 Audit et reprise

Chaque action matérielle conserve organisation, acteur, objet, version, heure, résultat, état avant/après, motif applicable, canal et référence de message. L'audit couvre configuration et reconnaissance des relations, sollicitation, réception, affectation, précisions, déclin, validation, publication, révision, retrait, sélection, acceptation, confirmation, booking, refus et contestation.

Les journaux partagés ne contiennent pas les hypothèses, marges, books ou reçus privés de pricing. Les audits locaux conservent les références nécessaires au rejeu interne. Aucune preuve de publication, acceptation ou exécution n'est effacée pour rendre le dossier cohérent.

Une reprise réutilise l'identité du message et son résultat. Les révisions sont interprétées selon leur ordre métier, pas selon l'ordre d'arrivée. Les états d'attente, d'échec, de déclin et de confirmation incertaine restent distincts. La suspension du réseau préserve le manuel, les archives et les traitements déjà reçus ou confirmés.

## 14 Critères d'acceptation du lot 0

| Scénario | Résultat attendu |
| --- | --- |
| Destinataires préparés sans envoi | Aucun message transmis ni accusé inventé. |
| Organisations avec listes différentes | Sollicitations conformes à chaque relation et périmètre. |
| Même Athena chez deux banques | Termes et calendrier identiques, calculs privés indépendants. |
| Version non prise en charge | Refus explicite de la prise en charge technique, sans paramètres inventés. |
| Banque calcule sans publier | Aucun prix chez le demandeur. |
| Prix modifié après validation | Contrôle et validation à refaire. |
| Même utilisateur habilité | Préparation, contrôle et publication possibles selon politique. |
| Seconde validation activée | Préparateur distinct du validateur ; modification invalidant la validation. |
| Panne pendant publication | Attente explicite ; reprise et préconditions recontrôlées. |
| Message livré deux fois | Une seule réponse métier. |
| Ancienne révision reçue après la nouvelle | Historique conservé ; réponse actuelle correcte. |
| Termes ou délai modifiés après envoi | Nouveau tour lié, anciennes cotations inchangées. |
| Cotation conditionnelle ou contre-proposition | Conditions/différences visibles, classement conforme séparé. |
| Retrait avant acceptation | Motif, notification et état courant empêchant une nouvelle acceptation. |
| Acceptation valide avant retrait | Prix réservé ; retrait ordinaire refusé. |
| Erreur après acceptation | Contestation et revue, sans effacement ou remplacement de prix. |
| Ordre externe contesté | Revue manuelle, aucune priorité inventée. |
| Prix expiré avant acceptation | Nouvelle cotation nécessaire. |
| Accord valide puis booking après expiration | Inscription sur l'accord figé ; aucune extension artificielle. |
| Traitement demandé et résultat inconnu | Confirmation attendue ; aucun second ordre automatique. |
| Confirmation par message bancaire | Termes, parties, prix, taille et source identifiés. |
| Accord téléphonique déclaré | Auteur, interlocuteur, heure et termes complets ; suivi écrit séparé. |
| Booking local bloqué après confirmation | Accord conservé, motif de blocage visible, reprise tracée. |
| Double inscription d'exécution | Un booking par organisation ; conflit si contenu différent. |
| Téléphone puis même prix réseau | Rapprochement explicite sans double comptage. |
| Réponse à un tour clôturé | Historique sans activation automatique. |
| Relation suspendue ou droits révoqués | Nouvelles actions concernées refusées ; preuves antérieures préservées. |
| Accès à un concurrent ou une autre organisation | Aucun contenu privé exposé, y compris par export ou appel direct. |
| Départ d'un utilisateur | Dossier conservé dans l'organisation, reprise selon habilitations. |
| Réseau suspendu | Manuel et consultation des preuves disponibles. |
| Une seule partie bookée | Statut local exact ; aucun rapprochement bilatéral annoncé. |

Le lot 0 est consolidé fonctionnellement par ces règles et parcours. Maquettes graphiques, identités du pilote, cas exact, paramètres opérationnels et solution de transport restent des travaux préparatoires à la réalisation. Les dossiers existants sont des tests exclus de la reprise au lot 1. Ces travaux ne rouvrent pas les arbitrages de fermeté et de confirmation actés ici.

## 15 Références et points d'application

- [Plan de réalisation du réseau RFQ](RFQ_NETWORK_ACTION_PLAN_2026-10-12.md), lots et dépendances.
- [Organisations et accès](ORGANIZATION_ACCESS_DESIGN_2026-09-24.md), propriété et habilitations.
- [Objet Product](PLAN_IMPLEMENTATION_OBJET_PRODUCT.md), termes, versions et calculs séparés.
- [Besoin inter-entités initial](INTER_ENTITY_RFQ_BACKLOG_2026-10-08.md), contexte de simulation conservé.
- [Doctrine Clients](../clients/CLIENTS_LOT_0_DOCTRINE_METIER.md) et [habitudes](../clients/CLIENTS_LOT_2_HABITUDES_TRADING.md), déclaration, observation et capacité opérationnelle distinctes.
- [CCR](../pricing/CCR_IMPLEMENTATION_2026-09-28.md), contrôles locaux, perspectives et limites.
- [API deritrade de cotation et traitement](https://api-docs.deritrade.com/api/quoting-trading/), exemple externe de séparation entre demande, accusé et résultat. Cette référence n'établit pas la politique de fermeté de Structura.

Les points d'application existants sont les domaines Product, RFQ, Pricer, relations de trading, booking et CCR. Le schéma technique et l'organisation du service réseau seront précisés avant implémentation ; les libellés et règles de cette spécification décrivent le comportement attendu.
