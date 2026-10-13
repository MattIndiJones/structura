# RFQ réseau — lot 7 : confirmation et booking local unique

Date : 12/10/2026. Branche : `codex/rfq-network-lot-0`. Changements locaux, sans commit ni push.

## Parcours livré

La RFQ conserve une **sélection locale**, puis une **demande de traitement externe déclarée**, une **confirmation consignée** et un **booking local**. Aucun de ces faits n’est déduit d’un accusé de livraison du prix. Les termes viennent du Product canonique et de sa version contractuelle.

Dans le dossier demandeur, **Accord de traitement → Consigner le traitement** ouvre `BaseModal`. L’utilisateur habilité déclare une demande effectivement faite par téléphone, courriel ou document, avec référence et interlocuteur. La réponse doit encore être active à cette déclaration. Structura ne transmet aucun ordre de traitement avec ce bouton.

**Consigner la confirmation** exige référence d’exécution, heures de réception de l’acceptation et de confirmation, preuves de réception et d’accord exact, interlocuteur et source. Deux modes existent : confirmation reçue de la banque et accord téléphonique déclaré. Le téléphone garde un indicateur d’écrit à suivre. Ce fait local n’est pas présenté comme une acceptation électronique de la banque.

L’accord porte la totalité du nominal et le prix de la réponse exacte. Produit, version/empreinte, calendrier, parties, sens, nominal, devise, convention all-in et publication d’origine sont figés. Une modification de prix ou des termes demande une nouvelle réponse et un nouvel accord ; la publication bancaire reste intacte. Les réponses conditionnelles ou non conformes ne sont pas acceptées par ce parcours.

Une demande non confirmée peut être annulée avec motif, puis remplacée par une nouvelle demande. Les anciennes déclarations sont conservées. Un accord confirmé n’est pas annulé ni réécrit par ce masque. Le changement de sélection et les modifications de la réponse manuelle concernée sont bloqués pendant le traitement ; le repricing privé reste possible.

## Droits et contrôles

Le droit existant **book** du desk autorise la déclaration, la confirmation et le booking ; aucun droit n’est attribué implicitement. La sélection conserve son propre droit. Organisation et habilitations sont recontrôlées à chaque action. La relation réseau, sa version reconnue, son périmètre de traitement et les accords de booking locaux sont contrôlés à la déclaration et à la confirmation.

La confirmation extérieure est une attestation de l’utilisateur habilité avec preuves référencées, sans extraction automatique d’un document ni vérification de son contenu. La réception ne peut précéder l’émission de la réponse, dépasser son expiration ou se situer dans le futur. La déclaration doit avoir été enregistrée pendant la validité du prix : une offre déjà expirée ne devient pas exécutable par saisie rétroactive d’une heure. Un retrait, remplacement ou clôture intervenu avant consignation empêche de déduire une priorité des seules heures saisies.

## Passage au booking

Le lien RFQ reste obligatoire quand le Product porte une réponse réseau ou un accord actif : l’omission de `rfq_id` ne transforme pas ce dossier en booking direct. Le contrôle crédit RFQ utilise la contrepartie de la publication réseau, avec contrôle des droits de lecture et de pricing du desk.

Une quote réseau nécessite un accord confirmé. Le parcours RFQ → Pricer → Booking reste celui existant. Le prix traité est affiché en lecture seule dans le Pricer lorsqu’un accord confirmé est chargé. Le serveur vérifie prix, nominal, parties, sens, Product, version, calendrier et réponse retenue contre l’accord.

La validité de la cotation se contrôle à la réception consignée de l’acceptation ; un accord valide reste inscriptible après l’expiration de l’offre. Les autres contrôles continuent à porter sur le booking actuel : pricing local signé, fraîcheur du prix modèle, inputs, contrepartie, contexte commercial, CCR et Product.

Un refus de booking conserve l’accord confirmé, son motif et l’heure de blocage. La projection Product est actualisée. Une correction locale permet de réessayer l’inscription ; elle ne réémet pas le traitement à la banque. La réussite conserve l’accord dans la provenance figée du Deal et dans le dossier Product.

## Unicité et reprise

Les tables additives sont `rfq_execution_agreements` et `rfq_execution_bookings`. Aucun ancien dossier n’est migré. Une seule demande non annulée peut exister par RFQ ; une référence d’exécution normalisée est unique par organisation. Les snapshots et confirmations sont protégés par des gardes SQLite, et les preuves de booking sont immuables.

Le booking est sérialisé par RFQ. Une répétition du même contenu pour la même exécution retrouve le même Deal, y compris après perte de réponse ou double clic. Un autre contenu produit un conflit explicite. L’empreinte de reprise conserve également les inputs et la preuve de pricing du booking : une nouvelle demande financièrement différente ne se confond pas avec une reprise.

Une référence et un accord ne peuvent produire qu’un booking dans cette organisation. **Booké localement** ne signifie pas booké par la banque ni rapproché avec son book.

## Réseau et manuel

Les quotes manuelles restent utilisables avec leur parcours historique. La consignation d’accord est proposée en complément ; dès qu’elle est engagée, sa confirmation précède le booking. Les quotes réseau restent non éditables ; leur fermeté publiée n’est pas réécrite par le booking.

Sur une même installation, une confirmation consignée protège la publication contre le retrait ou le remplacement ordinaire. Entre installations, la preuve externe ne constitue pas un message natif d’acceptation. Un retrait ou une révision bancaire reçu après confirmation conserve l’accord, trace le conflit et bloque une nouvelle inscription locale pour revue. L’événement reçu est conservé et n’annule pas silencieusement le traitement ; un Deal déjà booké n’est pas effacé.

## Masques et limites

Le panneau s’insère dans la zone de défilement RFQ existante et le formulaire utilise le scroll interne de `BaseModal`. Les montants utilisent les séparateurs français existants. Les contrôles d’attente, l’historique, la source et le blocage sont visibles.

Restent hors de cette tranche : messages natifs de demande/acceptation/confirmation, résolution gouvernée des contestations, rapprochement explicite d’un prix manuel et réseau, rapprochement des books, contre-propositions et exécutions partielles. L’indicateur de confirmation écrite à suivre ne constitue pas un circuit documentaire de résolution. Le pilote connecté à une installation bancaire réelle reste au lot 8.

## Vérification

- 19 scénarios backend distincts réussis : 14 nouveaux scénarios d’accord/exécution et cinq contrôles voisins Product, RFQ, publication et transport. Incluent deux bookings concurrents, conflit de référence entre RFQ, contenu différent, conservation du refus, reprise après expiration, droits, immutabilité, maintien du manuel et refus d’omettre le lien RFQ pour un Product réseau. Les deux scénarios réseau initialement bloqués par une configuration de recette incomplète ont été corrigés et rejoués seuls ; les ajouts/corrections ultérieurs ont été vérifiés par leurs seuls scénarios concernés.
- `npm run build` exécuté une fois : 427 tests frontend réussis, compilation Vite réussie. Aucun changement Vue après ce build.
- Vérification obtenue à l’écran sur une installation fictive : RFQ, état confirmation attendue, réponse réseau protégée, formulaire, preuves obligatoires et bouton désactivé lorsque la confirmation est incomplète. À 1 280 × 720, `body` et document restent à 720 pixels ; le corps de modale défile avec 632 pixels de contenu dans une zone de 542 pixels. Capture privée dans `tmp/rfq-lot7-uat/confirmation-desktop.png`.
- Serveur fictif et navigateur de recette arrêtés ; identité des processus et libération du port 8097 conservées dans les preuves locales. Aucune suite backend complète et aucune base réelle utilisée pour la recette.

Les validations métier ont été réalisées par les commandes natives ; la confirmation financière n’a pas été soumise dans le navigateur. Le contrôle mobile et le pilote sur des installations bancaires réelles restent à qualifier. Le backend opérationnel doit être relancé pour charger le nouveau code et créer les tables additives, puis l’application rechargée.
