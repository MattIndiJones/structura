# RFQ réseau — lot 3 : demande figée et envoi persistant

Date : 12/10/2026. Branche : `codex/rfq-network-lot-0`. Changements locaux, sans commit ni push.

## Périmètre livré

L’action **Envoyer la RFQ** dépose réellement une demande persistante dans le desk de l’organisation destinataire, par exemple BNP. Les deux organisations doivent être enregistrées dans la même installation Structura et leur relation RFQ reconnue des deux côtés. Il ne s’agit pas d’un email ou d’un transport entre serveurs indépendants ; ce dernier appartient au lot 6.

Le récapitulatif reste une opération de lecture. L’envoi est une action distincte, habilitée `solicit`, avec contrôles répétés côté serveur. La réception bancaire minimale permet consultation et accusé de lecture. L’attribution bancaire, le pricing privé et la publication d’un prix restent les lots 4 et 5.

## Parcours demandeur

1. Ouvrir une RFQ appartenant à un desk, puis son masque **Demande partagée et contrôle du prix**.
2. Choisir BNP parmi les partenaires autorisés. Renseigner l’intitulé partagé et l’échéance explicite.
3. **Préparer le récapitulatif** : examiner les termes Product, leur version et leur empreinte, le calendrier, la demande commerciale et le message individuel. Le contact partagé est le nom et l’email du demandeur présentés dans ce message.
4. **Envoyer la RFQ** : figer le tour et enregistrer les livraisons dans une seule transaction, avec la projection RFQ du Product et l’audit. Aucune ligne de prix bancaire n’est inventée.
5. Le tableau **Suivi par destinataire** affiche desk, heure de livraison, première lecture et réponse attendue. **Actualiser le suivi** recharge les faits persistants.

Une organisation ne reçoit qu’une sollicitation par tour, même si plusieurs relations ou libellés locaux la désignent. Ajouter une autre banque conserve exactement le même contenu commun et le même délai. La relation de cette nouvelle banque est recontrôlée ; son adressage est ajouté individuellement. Une échéance dépassée empêche un nouvel envoi.

## Parcours banque

Depuis RFQ, **RFQ reçues · banque** ouvre `/rfq/recues`. La liste ne contient que les demandes adressées aux desks actifs de l’utilisateur disposant du droit `read`. Le statut administrateur n’ouvre aucun accès implicite.

**Ouvrir** affiche le message enregistré, les paramètres effectifs, le panier, les quatre dates, le script et le calendrier figés. L’ouverture réussie déclenche un accusé de lecture explicite et idempotent. Une consultation API en GET seule ne déclare pas le message lu. Le demandeur ne voit pas l’identité du lecteur bancaire.

L’accès bancaire concerne la projection reçue ; il ne donne pas accès au Product complet ni au dossier RFQ du demandeur. Ni CRM, marchés, corrélations de pricing, résultats privés, autres destinataires ou cotations concurrentes ne sont transmis.

## Propriété et persistance

Les tables additives sont `rfq_exchange_rounds`, `rfq_round_links`, `rfq_solicitations` et `rfq_send_commands`. Les anciens dossiers ne sont pas migrés. Le Product et ses versions contractuelles restent canoniques ; le tour conserve uniquement leur projection autorisée, leur identité et leur empreinte pour restituer ce qui a effectivement été partagé.

Chaque message contient référence d’échange, numéro de tour et prédécesseur éventuel, version de format, référence Product et version de termes, définition contractuelle, demandeur/desk/contact, nature, sens du demandeur, nominal et devise, prix demandé en % du nominal all-in, délai, format/documentation et adressage individuel avec relation/version. L’identifiant de message et l’horodatage UTC de publication sont ajoutés à l’envoi. L’organisation enregistrée est l’identité du demandeur ; la qualification contractuelle détaillée des personnes juridiques reste celle des relations et du futur traitement.

Le dépôt dans la boîte du desk et son accusé de livraison sont atomiques dans cette installation : aucun statut « livré » ne précède l’enregistrement de la demande. Livraison, première lecture et résultat métier restent distincts. Les horodatages de l’API sont UTC.

Une clé de commande et l’empreinte du récapitulatif protègent l’envoi : un récapitulatif modifié ou une relation révisée est refusé ; le rejeu identique retourne les mêmes identifiants sans nouvelle sollicitation. Réutiliser la clé avec un autre contenu ou solliciter à nouveau la même organisation sous une nouvelle clé est refusé. Les mutations RFQ utilisent le verrou du périmètre de desk avant contrôle des droits.

## Manuel, gel et nouveau tour

Le manuel conserve ses lignes de fournisseurs, leurs prix et son parcours de pricing/booking. Le premier ajout de fournisseur d’une nouvelle RFQ avec desk fige aussi les termes du tour. Retirer ensuite cette ligne ne défige pas le contrat. Une sollicitation réseau n’est jamais convertie automatiquement en prix manuel.

Pour une consultation mixte, envoyer d’abord le tour réseau avec son échéance, puis ajouter les fournisseurs manuels. Si le premier acte était manuel, son tour est conservé avec **délai non publié** : aucun délai n’est inventé rétroactivement. Pour commencer ensuite l’envoi réseau, **Ouvrir un nouveau tour** permet de fixer une échéance explicite dans un dossier lié.

Après gel, sens, nominal, termes Product et contexte contractuel restent protégés ; les hypothèses privées peuvent évoluer et être recalculées avec les moteurs actuels. Intitulé partagé et échéance ne changent pas sur le tour publié.

**Ouvrir un nouveau tour** réutilise le formulaire existant de création/duplication. Le nouveau dossier reçoit son propre Product et ses termes éditables ; le lien vers le tour précédent est persisté dès sa création. Les dates doivent être confirmées dans ce formulaire. Il n’hérite d’aucun prix ni destinataire effectivement envoyé. Une seule suite peut être préparée pour un tour donné.

La première sollicitation du nouveau dossier ouvre le tour suivant de la même référence d’échange et remplace le précédent. Les anciennes demandes et réponses restent sur leur ancien dossier. Un tour remplacé ne peut plus être envoyé, sélectionné, rouvert ou booké. Un ancien tour déjà booké ne peut être remplacé. Le premier tour reste ouvert pendant la simple préparation du dossier suivant. Un tour figé ne peut être supprimé ; un brouillon lié non sollicité peut être supprimé pour libérer sa préparation.

## Écrans

Réutilisation de `BaseModal`, des classes institutionnelles et du masque RFQ existant. Le masque d’envoi conserve ses sections internes à hauteur bornée et ses panneaux défilants. La liste bancaire défile dans le viewport ; ses détails utilisent le scroll interne de `BaseModal`. Les nominaux utilisent le formatage français avec séparateurs de milliers.

## Vérifications et limites

- Groupe initial de 45 tests backend ciblés : 43 réussis et 2 échecs de fixture historique, corrigés en ajoutant le contact au faux utilisateur ; ces 2 scénarios repassent.
- Ajout d’un scénario de deuxième banque, et recontrôle du récapitulatif réseau : 2 tests ciblés réussis. Au total, 46 scénarios distincts couverts par ce groupe et ses corrections.
- `npm run build` réussi : 425 tests frontend, puis compilation Vite. Aucune suite backend complète.
- Recette HTTP authentifiée sur SQLite fictive, chemin vérifié : envoi QA ClientTech vers QA BNP, termes identiques à l’aperçu, réception, lecture, suivi, rejeu sans doublon, refus d’accès étranger et de modification/suppression après gel.
- Recette visuelle non effectuée : le navigateur de l’outil a refusé l’adresse locale avec `ERR_BLOCKED_BY_CLIENT`. Bureau, mobile, clavier et comportement réel du scroll restent à vérifier à l’écran. La compilation seule ne les qualifie pas.

Incident de préparation : la variable `DATA_DIR` avait été utilisée à la place de `STRUCTURA_DATA_DIR`. Des objets fictifs ont été créés dans la base locale. L’instance a été arrêtée, une sauvegarde SQLite faite, puis seuls ces objets ont été retirés dans une transaction. Toutes les autres lignes et les protections de base ont été comparées à la sauvegarde et conservées. Les références allouées restent consommées. La recette suivante utilise `STRUCTURA_DATA_DIR` avec assertion du chemin réel de l’engine. Sauvegarde locale ignorée : `tmp/rfq-lot3-uat/pre-cleanup-backup.db`.

Aucune demande réelle n’a été adressée à une banque externe. La qualification du transport entre installations, des réponses, retries réseau, annulations et confirmations de traitement reste dans les lots suivants.
