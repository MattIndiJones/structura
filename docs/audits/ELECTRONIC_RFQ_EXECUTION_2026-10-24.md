# Confirmation électronique RFQ — recette locale du 24 octobre 2026

La demande de traitement et la décision bancaire sont désormais échangées nativement entre deux installations. La réception technique reste distincte de la décision métier. La recette fictive Leonteq/BNP a confirmé la même exécution après arrêt successif de chaque destinataire, puis obtenu un seul Deal dans chaque base.

Livraison locale sans commit ni push, sur la branche `codex/hybrid-saas-foundation`, HEAD `7dce3021a88feb4f0021ca3de8f3596277bc72a5`. Les preuves de la [recette bilatérale précédente](BILATERAL_RFQ_ACCEPTANCE_2026-10-24.md) restent historiques et inchangées : son accord était déclaré par téléphone. Cette nouvelle recette emploie un autre runtime, de nouvelles identités et un accord électronique.

[Preuves structurées](remediation-lot-0-2026-10-20/ELECTRONIC_RFQ_VALIDATION.json) · [Registre](remediation-lot-0-2026-10-20/REGISTER.json) · [Dépendances](remediation-lot-0-2026-10-20/DEPENDENCIES_AND_VALIDATION.md).

## Règles et transitions

Le périmètre qualifié localement est une RFQ **to trade**, une réponse réseau **ferme, sans condition supplémentaire**, une révision précise, un nominal intégral et un sens explicite. Les prix indicatifs, traitements partiels et changements contractuels requièrent un autre parcours.

| Action et auteur | Préconditions | Fait conservé et résultat | Reprise / refus |
| --- | --- | --- | --- |
| Le demandeur envoie la demande | Droit métier et droit `book` du desk, quote sélectionnée, version et empreinte Product contrôlées, revue explicite | Intention `PENDING`, accord local `REQUESTED`, message `EXECUTION_REQUEST`, UUID/référence et quote exacte | Même clé et même contenu : même intention ; autre clé/contenu sur ce dossier : conflit |
| La banque reçoit le message authentifié | Canal appairé, identité, signature et séquence valides | `RECEIVED`, heure de réception bancaire figée ; accusé de transport distinct | Une première arrivée hors validité, une révision retirée/remplacée ou un contexte inéligible produit un **refus métier** durable |
| La banque confirme ou refuse | Utilisateur autorisé à booker ce desk, empreinte de l’intention attendue, revue et motif ; confirmation : contexte courant encore éligible | Décision immuable `CONFIRMED` ou `REJECTED`, auteur/heure/motif, message `EXECUTION_CONFIRMATION` | Même décision/motif : même message ; décision contradictoire : conflit |
| Le demandeur reçoit la décision | Message authentifié correspondant exactement à l’UUID, au dossier et à l’empreinte de la demande | Accord local confirmé avec source `ELECTRONIC_CONFIRMATION`, référence commune et preuve ; ou accord annulé par refus | Aucune déclaration manuelle ne peut se substituer à une décision attendue ; aucun booking avant confirmation |
| Chaque desk booke localement | Confirmation métier et contrôles locaux Product, calcul signé, contrepartie, économie et limites | Deal local et lien unique `rfq_electronic_bookings` vers l’exécution commune | Même booking natif : Deal existant ; contenu divergent : refus ; aucune création automatique à la livraison |

La validité est évaluée à **l’arrivée effective dans la banque**, avec son horloge, et non à l’heure déclarée par le demandeur. Une demande arrivée avant expiration peut être confirmée après expiration, en conservant l’heure initiale et après recontrôle du contexte. Une première livraison tardive est refusée sans antidatage. Les horloges UTC doivent être synchronisées.

Une intention reçue protège la cotation contre remplacement/retrait. Le transport ne permet pas d’annuler l’intention ou la décision par un simple `CANCEL`. Un refus est conservé ; la renégociation exige un nouveau tour. Une panne ne constitue jamais une annulation ni un accord. Une décision bancaire déjà enregistrée reste livrable après expiration de la quote ou changement ultérieur des habilitations métier, sous authentification du canal ; l’envoi initial et le booking restent contrôlés.

Le rapprochement compare l’empreinte contractuelle partagée. Les numéros Product, contrepartie et version locale ne sont pas des identifiants globaux : les tests exercent aussi une version locale bancaire différente de la version partagée. La convention existante de sens des Deals est conservée (`vente` = position longue/BUY pour notre livre).

## Persistance et prévention des doublons

Trois tables additives sont enregistrées dans le schéma natif : exécution électronique, lien au booking local, enveloppe reçue authentifiée. Le démarrage natif crée les tables et installe les gardes SQLite ; aucun ancien accord n’est transformé en confirmation électronique. Les snapshots et décisions déjà confirmés ne sont pas réécrits.

L’intention et son outbox sont validés dans la même transaction. À réception, fait métier, inbox, enveloppe vérifiée et éventuelle décision de refus/outbox sont atomiques. La décision bancaire et son outbox sont également atomiques. Un rollback conserve donc la possibilité de reprendre le même message, sans accusé de succès inventé.

La file existante conserve identités de messages, ordre, tentatives, backoff et accusés signés. Après perte d’accusé, `STATUS` retrouve la réception durable avant une nouvelle remise. Une identité de message réutilisée avec un autre contenu est refusée ; une autre identité ne peut créer une seconde intention sur la même sollicitation. Les verrous et contraintes uniques protègent les accès concurrents. Les triggers interdisent les mutations/suppressions des demandes figées, décisions, dates de réception déjà établies, preuves et liens de booking.

Les enveloppes d’origine sont archivées chez le destinataire après vérification HMAC ; les accusés restent conservés chez l’émetteur. Le canal repose sur une **clé partagée** : cette authentification n’est pas une signature bancaire qualifiée ni une preuve de non-répudiation.

Le protocole conserve son identifiant `STRUCTURA_RFQ_1` et ajoute deux types. **Les deux installations doivent être mises à jour avant activation** : aucune négociation de capacités avec un ancien pair n’est fournie. Garder l’ancienne version face à un nouveau type produit un blocage, pas une confirmation rétrocompatible.

## Dépendances conservées

| Correctifs | Rôle et critère exercé |
| --- | --- |
| C01/C02 | Permissions métier et desk, identité locale et appairage ; pas d’élargissement des droits |
| C03/C04 | Mappings juridiques et relations reconnues, économie exacte et limites conservées au booking |
| C05/C06 | Contrat, calendrier, Product/version épinglés ; comparaison des empreintes entre installations |
| C07/C08 | Clé de commande durable côté interface, outbox/inbox, unicité et reprise sans nouvelle intention |
| C10 | Retours tardifs isolés par dossier et ouverture ; erreur serveur visible, pas de faux succès |
| C18 | Calcul local signé conservé pour chaque livre ; hypothèses et résultats privés non transportés |
| C23 | Quote/révision/validité exacte, sélection, décision et clôture propagée |

D05 reste suivi selon son statut antérieur ; aucune nouvelle règle de rôle ou seconde signature générale n’est approuvée implicitement. Aucun arbitrage quantitatif, calendrier, funding, fixing ou cash n’est modifié.

## Résultats obtenus

Le runtime ignoré `.runtime/diagnostic-acceptance/electronic-rfq-2026-10-24` utilise trois services natifs : plateforme 18300, BNP 18301, Leonteq 18305. Les deux organisations ont des bases, identités, Product, référentiels et calculs distincts. Les références fictives sont initialisées séparément ; la préparation RFQ/pricing/publication/sélection utilise les API authentifiées natives. Aucun Product, RFQ, accord ou Deal n’est fabriqué par insertion SQL.

La demande et la décision ont été **exercées dans les interfaces**, avec revue et motif, au moyen de connexions directes aux deux origines isolées. Les bookings et répétitions sont ensuite exercés par **API HTTP native authentifiée**, puis revus à l’écran. Cette distinction est conservée dans les preuves.

| Contrôle | Résultat |
| --- | --- |
| Banque arrêtée avant demande | Intention persistée, état en attente, aucun booking ; reprise de la même intention après redémarrage |
| Accusé de réception sans décision | Écran demandeur toujours en attente de confirmation métier |
| Demandeur arrêté avant décision | Décision bancaire persistée ; file en reprise ; même décision livrée après redémarrage |
| Référence commune | `EXE-D67D989D-C7A7-4784-BC6D-C43F54BCE6ED` |
| Économie | 1 000 000 EUR, 98,50 %, Leonteq BUY / BNP SELL, mêmes termes et quatre événements |
| Deals locaux | `LEON-20261024-001` et `BNPX-20261024-001`, un seul dans chaque base |
| Répétitions | Demande et décision rejouées sans nouvel événement ; booking bancaire exact rejoué ; booking RFQ sur revue courante retrouve le Deal |
| Revue devenue obsolète | L’ancien jeton de revue après premier booking est refusé 409 selon C01 ; aucune création supplémentaire. Recharger le dossier et consulter le Deal lié |
| Confidentialité | Volatilités privées 20 % / 30 % ; aucun champ de pricing privé dans les payloads contrôlés |
| Réconciliation | 28 contrôles réussis en lecture seule ; UUID, empreintes et décision identiques, clés étrangères valides |
| Preuves | Enveloppes originales et accusés HMAC vérifiés hors ligne ; mêmes identités de message, toutes les files finales livrées |
| Clavier | Ouverture par Entrée, fermeture Échap et retour du focus à « Ouvrir » ; garde de revue avant envoi/décision |

**E01 — défaut d’ordre d’insertion corrigé pendant la recette :** l’ajout de l’enveloppe authentifiée pouvait précéder le flush de son inbox parent, provoquant un refus de clé étrangère/HTTP 500. L’inbox est maintenant flushée avant son enfant, dans la même transaction. La même demande a repris sans modification SQL, nouvelle intention, changement de validité ou faux accord. Les 38 tests électroniques passent après correction sous clés étrangères actives ; le passage intermédiaire en échec est conservé, sans être assimilé aux 180 cas historiques F01–F21.

## Validation et critères

**252 tests backend ciblés distincts réussissent** dans le passage final (aucun échec/erreur/ignoré), décrit dans le JSON de preuve : compilation PayScript et pricing réels des fixtures, accords externes antérieurs, transport, publication, C08, intégrité Product, bootstrap et permissions voisins. **38 nouveaux cas électroniques** couvrent prix/révision/nominal/devise/sens/parties altérés, droits, contexte modifié, premier message expiré, décision après arrivée valide, chronologie future, perte d’accusé après commit sur les deux jambes, reçus concurrents, mutations SQL et bookings/replays.

Frontend : **756 tests réussis dans 84 fichiers**, dont huit nouveaux tests (sept du panneau et un du store) ; `npm run build` exécuté avec succès. Les réponses tardives, fermeture/réouverture, erreur serveur, clé de commande réutilisée et accusé technique sans accord sont couverts. Les résultats ciblés antérieurs ne sont pas additionnés à ces totaux. **15 jalons DOM/capture** sont conservés ; viewport observé 1280 × 720, affichage étroit non qualifié.

La preuve finale inventorie les cas distincts, empreintes d’artefacts, source modifiée, préservation des preuves antérieures, PID/ports et nettoyage. La suite backend complète du 23/10 reste datée **avant** cette livraison ; elle n’a pas été relancée.

## Limites et suite

- Recette sur HTTP loopback explicitement autorisé dans les installations fictives. TLS, PKI, proxy, réseau distant et déploiement ne sont pas qualifiés.
- Les pannes réelles sont des arrêts/redémarrages de destinataires. La perte d’accusé **après commit distant** et les accès concurrents sont provoqués dans les tests ciblés, pas dans une infrastructure distante.
- La preuve porte sur une Athena mono EUR. Matrice multi-devises, rôles multiples réels, volumétrie, arrêt brutal pendant commit, bascule machine et restauration d’une sauvegarde restent à qualifier.
- La décision bancaire utilise les droits métier/desk existants et une revue explicite ; aucune politique autonome de double signature d’exécution n’est ajoutée.
- Annulation contestée, amendement après confirmation, traitement partiel et rapprochement opérationnel manuel/réseau restent des travaux distincts. Ne pas effacer une exécution acceptée pour renégocier.
- Aucun règlement, virement, cash réel ou nouveau journal Note n’est exercé dans cette recette. Le journal Note déjà vérifié dans la recette précédente reste une preuve séparée.
- T02 et T12 restent **partiels** pour la matrice complète et la qualification déployée. Les 132 constats, 27 chantiers, 16 cas transverses, 13 décisions et les 180 cas F01–F21 ne sont pas renumérotés.

Avant ouverture réelle : mettre à jour et qualifier les deux pairs sur la copie d’environnement autorisée, vérifier UTC/TLS/identité et restauration, désigner les opérateurs et le circuit de résolution des conflits. Conserver cette recette locale comme preuve bornée, sans la présenter comme autorisation de production.
