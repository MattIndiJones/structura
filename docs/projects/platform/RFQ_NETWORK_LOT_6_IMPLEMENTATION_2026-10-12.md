# RFQ réseau — lot 6 : échanges entre installations

Date : 12/10/2026. Branche : `codex/rfq-network-lot-0`. Changements locaux, sans commit ni push.

## Périmètre réalisé

Deux installations Structura, avec bases et clés de pricing distinctes, peuvent échanger une demande RFQ figée, un avis de lecture, une cotation publiée, son retrait et la clôture du tour. Les réponses reviennent automatiquement au demandeur. La publication reste humaine, avec la politique de seconde validation du lot 5. Les Product, calendriers, moteurs et masques existants sont réutilisés.

Les partenaires sur la même installation conservent la remise locale atomique. Un canal distant configuré impose le transport distant : il ne retombe jamais silencieusement sur une livraison dans la base locale. Le manuel coexiste avec les réponses réseau. Aucune migration des anciens dossiers n’est ajoutée.

## Mise en place par les deux administrateurs

1. Dans chaque installation, déclarer les deux organisations et le desk bancaire dans le référentiel local. Les noms partagés des organisations et du desk doivent correspondre exactement. Les identifiants numériques peuvent être complètement différents.
2. Dans **Administration → Relations RFQ**, créer la relation directionnelle **ClientTech → BNP** sur chaque installation. Côté BNP, choisir ClientTech comme organisation demandeuse et BNP comme répondante. Renseigner le même périmètre commercial, les dates, devises, bornes, règles de traitement et documentation. Chaque organisation conserve ses propres rapprochements et accords de booking.
3. Configurer le rapprochement juridique local puis reconnaître **sa propre partie** de la version courante. L’autre partie sera reconnue par l’appairage signé, sans créer un utilisateur bancaire dans l’installation du demandeur.
4. Dans **Échanges entre installations Structura**, communiquer l’identifiant public de son installation à l’administrateur partenaire.
5. Le demandeur choisit **Appairer un partenaire**, la relation, l’identifiant distant, l’origine HTTPS distante et le rapprochement juridique local de sa propre entité vue par le partenaire. Il saisit un motif. Structura génère un identifiant de canal et une clé aléatoire de 256 bits.
6. Transmettre les informations d’appairage à l’administrateur BNP par le canal sécurisé convenu. La clé est affichée au créateur/importateur du canal, puis retirée du masque à sa fermeture ; elle n’est pas renvoyée par les listes ni inscrite dans l’audit.
7. BNP importe ces informations dans son propre masque, renseigne l’adresse HTTPS du demandeur, sa relation locale et son rapprochement juridique. Le rôle réception/publication est déduit de la relation choisie.
8. **Vérifier les deux installations** réalise une reconnaissance mutuelle signée du même accord. Les versions locales de relation peuvent différer ; l’empreinte de leur périmètre et de leurs adresses commerciales doit être identique. Une divergence empêche l’ouverture du canal.

La relation modifiée doit être reconnue localement, puis son canal reconfirmé sur les deux installations. Le bouton de suspension/reprise actualise la version et l’empreinte lorsque la relation a changé. Les demandes déjà figées restent attachées à leur ancien accord : une modification matérielle demande un nouveau tour.

Le réseau du pilote doit exposer `/api/rfq-transport/receive` derrière les origines HTTPS configurées, avec certificat valide. Le service habituel reste lié à son adresse locale ; ce lot n’ouvre aucun port publiquement. Le répertoire de données, ses sauvegardes et les clés de canal doivent être protégés par les droits du compte d’exploitation. Une restauration reprend l’identité persistée ; ne pas exploiter simultanément deux copies divergentes du même répertoire.

## Authentification et confidentialité

Chaque enveloppe contient le protocole `STRUCTURA_RFQ_1`, le canal, les identités persistantes des installations émettrice/destinataire, l’opération, un horodatage UTC et le message. Le JSON canonique est signé en HMAC-SHA256 avec la clé propre à cette relation. Le destinataire vérifie signature, direction, installation et fraîcheur de l’enveloppe. L’accusé est signé en retour et lié à l’identifiant, à l’empreinte et à la séquence du message.

HTTPS assure la confidentialité et le contrôle du certificat reste actif. Les redirections et les proxys hérités de l’environnement ne sont pas suivis. Les adresses se configurent uniquement par un administrateur de l’organisation ; une adresse reçue dans un message ne sert jamais de destination. La clé de canal n’est ni la clé JWT ni celle des reçus de pricing.

Le corps entrant est limité à 2 Mo. Une enveloppe expire après cinq minutes ; une reprise crée une nouvelle enveloppe autour du même message métier. Les horloges des installations doivent être synchronisées.

La demande transportée contient les termes canoniques, le calendrier, l’empreinte, la version contractuelle, le tour, le nominal, la devise, le sens, les conventions de prix, le délai et les contacts partagés. Les clés locales d’organisation, desk, relation et tour précédent sont retirées. Le routage repose sur le canal appairé et l’identifiant universel de demande. Les marchés, modèles, calculs privés, reçus de pricing, marges, données CRM et autres destinataires restent locaux.

## Persistance et reprise

L’action métier et son message sortant sont enregistrés dans la même transaction. Un arrêt entre cet enregistrement et le réseau laisse un message récupérable. La réception, son effet métier et son reçu durable sont également atomiques. Le succès HTTP est renvoyé après le commit récepteur.

Un worker démarre avec l’application. Il traite des messages dus par lots bornés, sans conserver de verrou de base pendant les appels HTTP. Chaque message possède un bail de 45 secondes et un jeton de possession. Un autre worker ne peut pas envoyer sous ce bail ; un bail expiré permet la reprise après arrêt brutal.

Les appels ont un timeout de dix secondes. Les échecs reprennent après 5, 10, 20, 40, 80, 160 puis 300 secondes au maximum. L’arrêt de l’application attend la fin de l’appel courant et interrompt le lot suivant. Les workers sont désactivés en consultation et lors des tests pytest.

Lorsqu’un envoi a déjà été tenté, le worker demande d’abord le reçu durable au partenaire. Un message reçu dont l’accusé a été perdu devient ainsi confirmé sans rejouer l’action métier. La révocation ultérieure d’un droit n’efface pas ce fait passé. Sans reçu, les droits, le canal, l’accord, les termes, l’état du tour et les contraintes de publication sont revérifiés avant une nouvelle remise.

Les contenus sortants, messages entrants et reçus sont protégés par des contraintes et des gardes SQLite. Les tentatives et les accusés signés sont conservés. Une reprise ne remplace jamais le contenu d’un message ni sa validité contractuelle.

## Doublons, ordre et messages devenus caducs

| Situation | Résultat |
| --- | --- |
| Même identifiant, même contenu | Reçu déjà enregistré renvoyé ; aucun second dossier ou prix. |
| Même identifiant, contenu différent | Conflit explicite, aucune application. |
| Plusieurs livraisons simultanées | Réception sérialisée ; un seul effet métier et un seul reçu. |
| Révision reçue avant son prédécesseur | Refus de séquence ; le prédécesseur doit être confirmé. |
| Banque indisponible | Reprise technique ; aucun déclin inventé. |
| Demande clôturée/expirée avant réception | Annulation signée, sans transmettre ses termes ; preuve de séquence conservée. |
| Cotation retirée, remplacée ou tour fermé avant réception | Annulation de la remise devenue caduque ; les messages suivants peuvent poursuivre le flux. |
| Cotation encore pertinente mais calcul, validation ou validité devenus insuffisants | Réception comme historique uniquement, sans sélection ni booking. |
| Droit de publication révoqué avant première réception | Reprise bloquée ; aucune nouvelle communication du prix sous ce droit. |
| Retrait/clôture après suspension de relation | Fait protecteur transmis par le canal encore actif ; la suspension ne laisse pas une ancienne offre active. |
| Canal technique désactivé | Échanges interrompus jusqu’à sa reprise explicite ; manuel disponible. |

La séquence est indépendante pour chaque demande et chaque direction. Une séquence manquante empêche une révision plus récente de doubler son prédécesseur. Les annulations consomment leur place sans publier les termes/prix supprimés de la remise. Un message déjà reçu reste un fait reçu ; son retrait ou sa clôture passent par un nouvel événement.

Un prix reçu tardivement ne reçoit aucune prolongation artificielle. L’historique conserve son identité, ses termes et sa validité d’origine. Une cotation retirée, remplacée, historique, expirée ou rattachée à un tour fermé reste non sélectionnable.

## Réception bancaire et isolation

La demande reçue crée une projection technique des termes dans un Product interne, avec un compte désactivé sans organisation et sans connexion possible. Cette projection n’est pas un dossier RFQ du demandeur local et n’est accessible ni par les liens RFQ normaux ni par les API Product des utilisateurs, y compris administrateurs.

**Prendre en charge** crée le Product bancaire privé natif du lot 4. Seuls les membres habilités du desk peuvent le lire et le pricer. Les hypothèses bancaires ne changent jamais la demande figée. Le message partagé original reste conservé avec son empreinte ; les clés locales de réception sont rapprochées explicitement au canal et à la relation.

Les contrôles de booking de l’organisation restent locaux. La partie distante de l’accord est reconnue par l’empreinte négociée, sans exiger d’importer ses identifiants privés de booking.

## Masques et suivi

Le masque partagé affiche **En attente**, **Reprise automatique**, **Reprise bloquée**, **Réception confirmée** ou **Envoi annulé avant réception**, avec nombre de tentatives, prochaine reprise, motif et dernières tentatives. Une relance habilitée avance la prochaine tentative ; elle ne modifie ni le message ni les contrôles.

Le masque bancaire distingue **Publié · réception en attente** de la réception confirmée. Chaque publication et son retrait ont leur suivi. Le demandeur reçoit ses réponses dans la RFQ existante ; les champs réseau restent non éditables. Aucun prix n’est automatiquement sélectionné et aucun booking n’est créé.

Le récapitulatif contractuel figé reste visible après envoi et après clôture. La préparation, les panneaux de suivi, l’historique et les formulaires d’appairage utilisent les zones de défilement et `BaseModal` existantes, sans agrandir le document.

## Validation du 12/10/2026

- 98 tests backend distincts validés sur les fichiers transport (18), livraison (9), relations (17), publication (13), banque (7), desks (9) et Product (25). Transport entre deux bases, HTTP signé, perte d’accusé, identités locales différentes, absence de clés locales sur le fil, droits révoqués, annulation avant réception, ordre, publication/retour/retrait/clôture, reçu concurrent, baux et intégrité. Les corrections ont été vérifiées par leurs seuls tests concernés ; aucune suite backend complète lancée.
- Build Vue : 427 tests frontend, puis compilation Vite réussis.
- Recette avec deux vrais serveurs, deux répertoires `STRUCTURA_DATA_DIR` privés et deux clés de pricing : arrêt BNP avant envoi, tentative en échec, arrêt du demandeur, redémarrage des deux serveurs, réception automatique, prise en charge, calcul Product natif, validation/publication à 98,5 %, prix reçu, ajout d’un fournisseur manuel, retrait puis clôture transmis. Aucun dossier réel utilisé.
- Contrôle visuel obtenu dans le navigateur : suivi demandeur, détail bancaire et formulaire d’appairage. À 1 280 × 720, document et body restent à 720 pixels. Le panneau partagé présente 602 pixels de contenu dans une zone de 223 pixels à scroll interne ; le détail bancaire 1 289 pixels dans une modale de 594 pixels.
- Preuves locales privées : `tmp/rfq-lot6-uat/evidence.json`, `ui-scroll.json`, captures et journaux des instances. Tous les processus de recette et leurs ports ont été arrêtés et libérés.

## Suite

Le lot 7 reste la confirmation explicite du traitement avant booking, avec unicité d’exécution locale. Les messages d’acceptation/confirmation, le rapprochement entre prix manuel et réseau, les compléments précisions/déclin et le pilote réel restent au plan. Aucun appairage avec une véritable installation BNP ni déploiement externe n’a été effectué. La rotation de clés et le changement d’adresse d’un canal existant nécessitent encore un parcours administratif dédié ; les sauvegardes conservent les identités et clés courantes.
