# RFQ réseau — exploitation et reprise du pilote

Création : 12/10/2026 ; finalisation : 13/10/2026. Périmètre : demandes, publications, retraits et clôtures entre
installations ; accord externe consigné et booking local. Ce document ne vaut
pas autorisation de négocier avec une banque réelle.

## Actualisation du 24 octobre 2026 — confirmation électronique locale

Le [parcours électronique](../../audits/ELECTRONIC_RFQ_EXECUTION_2026-10-24.md)
ajoute `EXECUTION_REQUEST` et `EXECUTION_CONFIRMATION` au transport existant.
Mettre à jour **les deux pairs** avant activation : l’identifiant de protocole
reste `STRUCTURA_RFQ_1`, sans négociation automatique de capacités.

Sur une RFQ to trade, retenir la réponse réseau ferme sans condition puis choisir
**Demander la confirmation électronique**, contrôler prix/nominal/révision et envoyer.
Dans **RFQ reçues**, un opérateur doté du droit métier et du droit `book` du desk
examine la demande, vérifie les termes, motive puis confirme ou refuse. Un accusé
de réception de transport ne remplace jamais cette décision. Le booking reste une
action locale avec ses contrôles habituels.

La validité de la quote est contrôlée à l’arrivée dans la banque ; une première
arrivée tardive est refusée. Une intention reçue protège la révision jusqu’à la
décision. Après panne ou accusé perdu, consulter l’état puis relancer **le même
message** ; ne recréer ni demande, ni décision, ni accord manuel de substitution.
Le refus est conservé ; la renégociation exige un nouveau tour. Un `CANCEL` de
transport n’annule pas une exécution. Après booking interrompu, rechercher le
Deal lié ; si le jeton de revue est devenu obsolète, recharger le dossier.

Les enveloppes HMAC reçues et accusés sont conservés localement. La clé partagée
n’offre pas une signature bancaire qualifiée. Cette capacité a une recette locale
sur deux installations fictives ; TLS, résolution des conflits et ouverture réelle
restent à qualifier. Les descriptions ci-dessous du traitement externe consigné
restent applicables à ce parcours distinct et décrivent le pilote antérieur.

## Actualisation du 24 octobre 2026 — rapprochement des livres

Le [rapprochement opérationnel](../../audits/RFQ_RECONCILIATION_2026-10-24.md)
ajoute `EXECUTION_STATUS`. Mettre à jour les deux pairs ensemble. La file bancaire
affiche les dossiers incomplets ; l’inventaire habilité est disponible via
`GET /api/rfq-reconciliation`. Chaque dossier conserve les derniers états datés.

1. Examiner **Rapprochement des deux livres** : confirmation, booking local,
   booking distant, champs divergents et date/version du dernier état distant.
2. Après panne, utiliser **Rapprocher et reprendre les échanges** : la même
   intention/décision reste en place, la séquence et ses clôtures sont reprises.
   Aucun Deal ni accord n’est créé par cette action.
3. Si notre booking manque, reprendre le dossier confirmé avec ses contrôles
   locaux. Côté banque, **Reprendre le booking confirmé** reste disponible après
   clôture pour une jambe confirmée non bookée. Réaffecter explicitement si le
   responsable change ; ne pas rouvrir la négociation pour inscrire l’accord.
4. Si le prix, le nominal, les termes, la documentation ou les dates divergent,
   conserver les preuves et faire revoir l’accord/livre concerné. Ne pas
   écraser un booking ou choisir une date de trade par conversion d’horodatage.
5. Après correction gouvernée du livre ou d’une déclaration, republier un état
   courant. L’ancien état est conservé ; attendre aussi l’acquittement de remise.

`MATCHED` signifie concordance des derniers états déclarés, pas surveillance en
temps réel de la base distante. Les calculs privés et identifiants locaux ne sont
pas transmis. La reprise après ajout de la table n’octroie aucune concordance
rétroactive. Le traitement des exécutions manuelles, règlements et conflits
contractuels reste distinct ; TLS et qualification déployée restent ouverts.

## Préparer une relation pilote

1. Désigner les deux organisations, le desk demandeur, le desk répondant et
   leurs responsables. Les identités commerciales partagées doivent correspondre
   exactement sur les deux installations ; les identifiants locaux peuvent différer.
2. Habiliter chaque personne explicitement : lecture, préparation, pricing,
   sollicitation, sélection et booking côté demandeur ; lecture, préparation,
   pricing, validation et publication côté banque ; ajouter le droit métier et
   le droit `book` du desk pour la décision d’exécution électronique. Un administrateur ne gagne
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

### Révisions et clôture — correctif local C23 du 22/10/2026

Une sélection vise une révision précise de la cotation. Modifier le prix,
la devise, le statut, la fermeté ou les heures révoque cette sélection et son
motif ; le desk doit décider à nouveau. Les anciennes valeurs restent dans
les événements d'audit avant/après, avec la révision. Une note seule ne change
pas la révision commerciale. Les écrans transmettent la révision affichée et
refusent une saisie devenue obsolète.

La devise absente est reprise explicitement des termes Product figés. Une
réponse USD à une RFQ EUR reste consultable, mais ne peut être retenue ni
bookée comme réponse conforme. Une contre-proposition qui modifie le contrat
exige un nouveau tour et les termes correspondants ; aucune conversion FX
implicite n'est effectuée. L'heure de cotation est distincte de la date de
saisie ; toute mise à jour valide ensemble cotation et fin de validité en UTC.

Si une révision de l'originale rend son last look moins favorable ou change sa
devise, ce last look est conservé et marqué expiré. Sa sélection est révoquée.
Le réactiver exige une contre-cotation au moins aussi favorable que la nouvelle
originale, dans la même devise. Une nouvelle sélection reste explicite.

Le classement « sans suite » clôture durablement le tour figé, y compris les
cotations manuelles. La clôture est propagée par la file existante. **Rouvrir
ce même tour est refusé** : utiliser **Nouveau tour** dans **Diffusion RFQ**,
puis confirmer son envoi. L'ancien tour et ses réponses restent consultables.
Les états `RESERVED` et `ROUND_CLOSED` restent éligibles à l'historique lorsque
la réponse est conforme ; ils ne deviennent pas des offres actives. Le
graphique affiche une moyenne quotidienne explicite, calculée sur toutes les
observations admissibles du fournisseur.

La migration est additive. Elle ne certifie pas rétroactivement les anciennes
sélections : avant un nouveau traitement ou booking, cliquer sur **Retenir à
nouveau** pour lier explicitement la révision. Les deals déjà bookés restent
consultables. Cette livraison locale ne qualifie ni le déploiement ni la reprise
sur une copie des données d'exploitation ; voir le
[rapport C23](../../audits/REMEDIATION_C23_2026-10-22.md).

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
Le parcours externe consigné bloque un nouveau booking et préserve l'accord ; il ne
résout pas automatiquement l'ordre contesté et n’envoie pas l’acceptation native.
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

Les messages natifs d'acceptation/confirmation sont maintenant exercés localement
par la recette du 24/10 ci-dessus, sans qualification déployée. Le rapprochement manuel/réseau,
les précisions/déclin/contre-proposition, la résolution gouvernée des conflits,
la rotation de clés et le rapprochement des books ne sont pas qualifiés par
le présent pilote. Consulter le [rapport du lot 8](RFQ_NETWORK_LOT_8_ACCEPTANCE_2026-10-13.md)
avant de décider une ouverture.
