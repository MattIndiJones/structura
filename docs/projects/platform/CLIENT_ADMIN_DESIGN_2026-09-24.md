# Administration de l'organisation cliente — proposition fonctionnelle

Date : 24/09/2026. Statut : proposition à arbitrer avec Philippe ; aucun code de ce chantier n'est réalisé ici. Ce document complète [le cadrage des organisations et des accès](ORGANIZATION_ACCESS_DESIGN_2026-09-24.md).

## Principe

L'administrateur du client gère **son organisation**, ses collaborateurs et les référentiels qu'elle utilise. Il ne voit ni les données des autres clients ni les réglages d'exploitation de Structura. Les deals, RFQ, produits, scripts et contacts sont des données de l'organisation ; leur créateur reste un auteur dans la piste d'audit, pas leur propriétaire. Le même modèle fonctionnel s'applique à la plateforme commune et à l'installation dédiée.

La page « Administration » actuelle est un espace global réservé au rôle `admin`. Elle contient des outils d'exploitation (navigateur de données, calculs, UAT) et des référentiels métier. Elle ne peut pas devenir telle quelle la console d'un administrateur client : le rôle global, les accès aux données et les opérations d'exploitation doivent être séparés avant son ouverture à plusieurs organisations.

## Console proposée

1. **Vue d'ensemble.** Organisation et espace actifs, administrateurs, invitations et demandes en attente, utilisateurs actifs/suspendus, référentiels incomplets, alertes de configuration. Chaque indicateur mène à la liste concernée.
2. **Équipe et accès.** Inviter nominativement, traiter les demandes d'accès, affecter un ou plusieurs desks, choisir des droits par activité, limiter la durée d'un accès externe, suspendre ou révoquer. Montrer l'effet concret d'un changement de droits avant validation. Prévoir un responsable titulaire et un suppléant ; empêcher la suppression du dernier administrateur habilité.
3. **Contreparties et contacts.** Une fiche de contrepartie juridique porte l'éligibilité au booking, les identifiants utiles et les éventuelles limites approuvées. Des canaux de cotation RFQ peuvent pointer vers elle : la banque ou plateforme qui cote n'est pas toujours l'entité qui fait face au deal. Chaque canal possède ses contacts nominatifs, leur desk/fonction, e-mail, téléphone éventuel, statut actif, contact préféré et historique. Un contact désactivé disparaît des nouveaux formulaires mais reste lisible dans les RFQ passées. Détecter doublons et liens manquants ; ne pas déduire l'entité juridique d'un simple nom similaire.
4. **Référentiels métier.** Sous-jacents autorisés et devise de chacun, calendriers/conventions retenus, listes utilisées par les desks et paramètres par défaut du pricing/RFQ. Distinguer un référentiel partagé maintenu par Structura d'une préférence propre au client. Une valeur par défaut ne doit jamais modifier rétroactivement les termes enregistrés d'un produit ou d'une RFQ.
5. **Risk.** À terme, afficher les lignes par contrepartie juridique, leur devise, validité, source et approbateur, ainsi que l'utilisation et les dépassements. Le calcul du risque de crédit et le contrôle non bloquant sont encore à définir dans [la note dédiée](../pricing/RFQ_CREDIT_LINE_DESIGN_2026-09-24.md). Le plafond de concentration en nominal déjà présent n'est pas automatiquement une ligne de crédit.
6. **Historique et gouvernance.** Journal consultable des invitations, droits, rattachements, contacts, contreparties, limites et changements de configuration : qui, quand, avant/après, justification éventuelle. Export encadré, conservation/archivage et procédure de récupération du compte responsable.

## Pouvoirs à séparer

| Rôle proposé | Périmètre et action principale |
|---|---|
| Administrateur Structura | Valide une organisation et son premier responsable ; exploite la plateforme ; accès support exceptionnel, temporaire et tracé. |
| Responsable de l'organisation cliente | Nomme les administrateurs clients, définit les délégations et assure la continuité du compte. |
| Administrateur des accès client | Traite invitations, demandes, desks, habilitations et suspensions dans son organisation. |
| Administrateur des référentiels client | Tient les contreparties, canaux RFQ, contacts et préférences autorisées. |
| Responsable Risk client | Approuve les lignes et politiques de risque quand leur méthode sera arrêtée. |
| Responsable de desk | Gère ses collaborateurs et ses contacts seulement si une délégation explicite le permet. |

Une personne peut cumuler plusieurs fonctions, mais le droit d'administrer des utilisateurs ne donne pas automatiquement le droit d'approuver une ligne de crédit, de booker un deal ou de valider sa propre opération. Les actions sensibles conservent une séparation préparateur/validateur.

## Parcours à traiter explicitement

- **Création du client :** Structura vérifie l'organisation et l'autorité du responsable initial avant une invitation nominative. Le premier utilisateur inscrit ne devient pas administrateur par simple ordre d'arrivée.
- **Philippe rejoint Leonteq :** il peut demander l'accès au desk Structuration, mais ne voit aucune donnée de Leonteq avant l'accord d'un responsable habilité. Une clé commune peut aider à orienter la demande ; elle ne vaut pas autorisation. Le responsable attribue les droits réellement accordés.
- **Départ ou changement de desk :** révoquer les sessions et droits concernés ; conserver les RFQ, deals et traces dans l'organisation. Un changement d'employeur entraîne un nouveau rattachement approuvé, sans transfert automatique de données.
- **Plusieurs organisations ou installations :** afficher clairement le contexte actif. Une identité autorisée dans une organisation n'ouvre rien dans une autre. En installation isolée, prévoir l'invitation/remise contrôlée même sans messagerie et préciser qui est l'autorité locale en cas de déconnexion.
- **Conflit ou erreur :** demandes en double, approbations simultanées, invitation expirée/transférée, homonymie de banque, contact devenu inactif, fournisseur RFQ sans contrepartie juridique et dernier administrateur indisponible ont chacun un état et une action de résolution explicites.

## Ordre de développement recommandé

1. Établir la propriété organisationnelle de chaque donnée et les contrôles d'accès côté serveur, puis migrer les données existantes avec revue des cas ambigus. Sans cela, une jolie console client exposerait des données croisées.
2. Livrer admission, invitations, rôles, desks et audit, puis tester la succession de l'administrateur et le retrait d'accès.
3. Rattacher les référentiels actuels — notamment fournisseurs RFQ, contacts et contreparties de booking — à l'organisation ; ouvrir leur gestion aux administrateurs de référentiels clients.
4. Ajouter les préférences métier et, après décision Risk sur la métrique, les lignes et alertes de crédit.
5. Vérifier les mêmes parcours sur une plateforme à deux organisations et sur une installation dédiée, y compris par accès direct aux API, exports et calculs en arrière-plan.

## Arbitrages encore nécessaires

Valider qui peut nommer un administrateur client, si un responsable de desk peut gérer les contacts de sa banque, si un contact est partagé entre desks, quels changements de contrepartie nécessitent une seconde approbation, et quelles politiques de référence sont imposées par Structura plutôt que configurables par le client. Ces décisions précèdent le découpage précis des écrans et des droits.
