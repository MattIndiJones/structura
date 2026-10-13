# RFQ réseau — exploitation et reprise du pilote

Création : 12/10/2026 ; finalisation : 13/10/2026. Périmètre : demandes, publications, retraits et clôtures entre
installations ; accord externe consigné et booking local. Ce document ne vaut
pas autorisation de négocier avec une banque réelle.

## Préparer une relation pilote

1. Désigner les deux organisations, le desk demandeur, le desk répondant et
   leurs responsables. Les identités commerciales partagées doivent correspondre
   exactement sur les deux installations ; les identifiants locaux peuvent différer.
2. Habiliter chaque personne explicitement : lecture, préparation, pricing,
   sollicitation, sélection et booking côté demandeur ; lecture, préparation,
   pricing, validation et publication côté banque. Un administrateur ne gagne
   pas automatiquement ces droits et ne peut pas se les attribuer lui-même.
3. Créer et reconnaître les périmètres de relation : formats, instruments,
   familles, devises, nominal, dates et documentation. Pour le traitement,
   renseigner les rapprochements juridiques et les accords de booking locaux.
4. Fixer la politique bancaire de seconde validation et de fraîcheur du calcul.
   Si deux personnes sont requises, disposer effectivement d'un validateur
   distinct et habilité. Tester d'abord une organisation fictive.
5. Exposer uniquement l'origine HTTPS prévue derrière l'infrastructure retenue.
   Vérifier le certificat, son nom, son expiration, la chaîne de confiance,
   l'accès à `/api/rfq-transport/receive` et la synchronisation UTC des horloges.
   Le client actuel utilise sa confiance TLS par défaut avec `trust_env=False` :
   ne pas supposer qu'une variable de proxy ou `SSL_CERT_FILE` est prise en compte.
   Une PKI privée doit être intégrée et qualifiée dans l'environnement d'exploitation.
6. Appairer les canaux et vérifier la reconnaissance mutuelle comme décrit au
   [lot 6](RFQ_NETWORK_LOT_6_IMPLEMENTATION_2026-10-12.md). Transmettre la clé par
   le canal sécurisé convenu ; ne jamais la placer dans une capture ou un ticket.
7. Tester un aller-retour avec une seule relation, puis deux et une saisie manuelle.
   Conserver le rapport de recette, les responsables et les limites de la version.

## Parcours de référence

Le demandeur crée ou duplique une RFQ sous son desk, vérifie les termes Product,
le calendrier, le nominal, la devise et les destinataires, puis confirme l'envoi
du contenu prévisualisé. Il suit chaque remise dans **Diffusion RFQ**.

La banque ouvre **RFQ reçues · banque**, prend en charge la demande et utilise
**Ouvrir dans le Pricer**. Elle conserve un calcul privé natif, prépare le prix
commercial, vérifie le récapitulatif, valide puis publie selon la politique du
desk. Le prix commercial peut différer du résultat privé ; seule la réponse
publiée revient au demandeur.

Le demandeur compare réseau et manuel, choisit une réponse puis consigne sa
demande de traitement externe. Cela n'envoie pas d'ordre bancaire natif. Il
consigne ensuite l'accord reçu, ses heures, ses preuves et sa référence
d'exécution. Les termes, prix, nominal, parties et sens doivent rester ceux de
l'accord. Le booking local utilise son propre calcul signé et les contrôles
Product, RFQ, contrepartie et CCR. Un blocage conserve l'accord et son motif.

## Lire le suivi sans inventer un résultat

| État/fait | Lecture opérationnelle | Action |
| --- | --- | --- |
| `PENDING` | Événement enregistré localement, réception non confirmée | Attendre le worker, consulter le suivi |
| `RETRY` | Indisponibilité ou accusé non exploitable | Vérifier la liaison ; reprise automatique |
| `BLOCKED` | Signature, droits, relation ou contrat à examiner | Corriger la cause, puis relancer habilité |
| `DELIVERED` | Accusé durable vérifié du destinataire | Consulter aussi son résultat métier |
| Accusé `HISTORY` | Événement conservé sans devenir une réponse active | Ne pas sélectionner comme offre active |
| `CANCELLED` | Remise annulée après contrôle | Conserver l'historique ; nouveau tour si nécessaire |
| Traitement `REQUESTED` | Demande externe déclarée, accord encore attendu | Recueillir l'accord ; aucun booking automatique |
| `CONFIRMED` | Accord externe exact consigné | Vérifier les contrôles locaux puis booker |
| `BOOKED_LOCALLY` | Deal créé dans cette installation | Ouvrir ce Deal ; ne pas recréer l'exécution |

Un canal indisponible ne signifie pas que la banque a décliné. Un accusé de
transport ne constitue ni une acceptation de traitement ni un rapprochement
bilatéral des books.

## Reprendre après interruption

1. Identifier RFQ, tour, destinataire et message dans le suivi. Relever état,
   nombre de tentatives, dernière erreur, réception confirmée et état métier.
2. Vérifier la bonne installation : origine configurée, identité persistante,
   relation reconnue, horloge, droits de l'acteur et disponibilité du service.
   Ne pas recopier la demande dans un autre dossier pour masquer une panne.
3. Redémarrer l'instance d'exploitation autorisée avec le **même répertoire de
   données**. Le worker reprend les messages persistés ; un bail actif expire
   après 45 secondes. Les reprises sont espacées jusqu'à 300 secondes ; les
   appels réseau ont un timeout de 10 secondes.
4. Si une remise a déjà été tentée, le worker consulte d'abord le reçu distant.
   Un accusé perdu ne nécessite pas de recréer la publication. Utiliser le
   bouton de relance existant après résolution de la cause, avec le droit
   approprié ; il reprogramme le même message et ses contrôles.
5. Après reprise, vérifier réception et état courant du prix : termes, tour,
   révision, retrait et validité. Une cotation périmée peut revenir en historique,
   sans devenir exécutable. Ne jamais prolonger sa validité pour terminer la recette.

Ne pas supprimer une file, réécrire une séquence, modifier une empreinte ou
fabriquer un reçu SQL pour « débloquer » un échange. Si le contenu a changé,
ouvrir le nouveau tour métier prévu.

## Traiter un booking interrompu ou bloqué

Après un timeout, ouvrir le dossier RFQ et rechercher le Deal lié et la référence
d'exécution avant de reprendre. Le même contenu est idempotent ; un contenu
différent pour la même inscription est refusé. Corriger un blocage de contrôle
local en conservant l'accord consigné. Ne pas redemander un traitement bancaire
pour la seule raison que le booking local a échoué.

Si la banque retire ou révise après une acceptation externe consignée seulement
chez le demandeur, conserver les deux preuves et ouvrir la revue de conflit.
La version actuelle bloque un nouveau booking et préserve l'accord ; elle ne
résout pas automatiquement l'ordre contesté ni n'envoie l'acceptation native.
Une exécution déjà bookée ne s'efface pas par retrait de cotation.

## Suspendre et poursuivre en manuel

L'administrateur suspend le canal concerné dans **Relations RFQ → Échanges entre
installations**, avec un motif. Les nouvelles sollicitations de ce canal sont
bloquées ; les dossiers et preuves restent consultables. La saisie manuelle
continue dans les masques RFQ habituels. Indiquer clairement son origine et ne
pas créer une copie manuelle supposée être le même événement réseau sans revue.

La reprise exige la correction de la cause, la relation courante reconnue et la
vérification des deux installations. Un changement matériel de relation appelle
un nouveau tour ; il ne modifie pas les demandes figées.

## Sauvegarde et arrêt

Sauvegarder de manière cohérente le répertoire de données de l'installation,
notamment la base, l'identité et les clés nécessaires. Protéger cet ensemble au
même niveau que les échanges et données de trading. Restaurer dans une instance
arrêtée, vérifier l'identité et les canaux, puis ouvrir une seule copie active.
Ne jamais faire tourner deux copies divergentes de la même installation.

La recette autonome démarre uniquement ses instances privées sur des ports
libres et les arrête par contrôle d'identité. Elle produit les PID, commandes,
heures et résultats de nettoyage dans `evidence.json`. Les journaux et bases
privés restent sous `tmp/` et ne doivent pas être publiés en bloc : ils contiennent
des clés fictives et les preuves détaillées.

## Ouverture progressive

| Palier | Condition pour avancer |
| --- | --- |
| Trois installations fictives | Parcours complet et refus mesurés, reprises et masques qualifiés |
| Une relation réelle désignée | Participants, accès, accords, TLS et procédures effectivement validés ; décision d'ouverture |
| Quelques relations | Suivi des remises, incidents et booking local revu sur chaque relation |
| Extension | Limites produit et compléments métier traités selon le périmètre annoncé |

Les messages natifs d'acceptation/confirmation, le rapprochement manuel/réseau,
les précisions/déclin/contre-proposition, la résolution gouvernée des conflits,
la rotation de clés et le rapprochement des books ne sont pas qualifiés par
le présent pilote. Consulter le [rapport du lot 8](RFQ_NETWORK_LOT_8_ACCEPTANCE_2026-10-13.md)
avant de décider une ouverture.
