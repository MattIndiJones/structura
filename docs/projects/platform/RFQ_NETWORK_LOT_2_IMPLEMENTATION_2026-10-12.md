# Lot 2 RFQ — relations reconnues et destinataires autorisés

Date : 12/10/2026. Branche : `codex/rfq-network-lot-0`.

Le lot ajoute **Administration → Relations RFQ** et raccorde cet annuaire à la préparation des nouvelles RFQ de desk. Une relation identifie une organisation demandeuse, une organisation répondante et son desk de réception. Elle est directionnelle : le droit inverse de demander des prix nécessite sa propre relation. Les identités proviennent des organisations et desks de cette installation ; aucun nom de fournisseur ou de fiche CRM ne crée une identité réseau.

## Reconnaissance et périmètre

La préparation d'une relation ne l'active pas. Un administrateur rattaché à chacune des deux organisations reconnaît explicitement la même version. L'administrateur technique sans organisation ne peut pas reconnaître à la place des parties. Une modification de périmètre, de desk ou de rapprochement crée une nouvelle version et invalide les deux reconnaissances. Les versions attendues sont contrôlées lors des mutations.

Le périmètre contient des listes explicites de formats, instruments, familles du catalogue et devises, des bornes facultatives de nominal, les dates d'effet et d'expiration et des autorisations distinctes pour solliciter, demander un indicatif, demander un prix to trade et traiter. Les bornes absentes sont affichées comme telles. Les nombres sont groupés par milliers dans les masques.

Chaque partie rapproche explicitement sa contrepartie juridique avec le référentiel existant. Elle peut rattacher son accord de booking `TradingRelationship`, sans recopier ses termes ou contrôles. L'autorisation de traiter exige un accord local actif et documenté de chaque côté lors de la reconnaissance. Elle prépare les contrôles des futurs traitements réseau ; elle ne modifie pas le booking manuel existant. La politique RFQ V1 de fermeté, canal horodaté de réception, confirmation avant booking et revue des contestations est identifiée et visible.

Les contacts saisis sont explicitement partagés. Les identifiants des accords de booking locaux et leurs détails privés restent propres à chaque organisation. Le même administrateur ne peut modifier la configuration locale de l'autre partie en fournissant son identifiant d'organisation.

## Suspension et contrôles des destinataires

Une suspension par l'une des parties bloque la relation. Sa reprise retire la suspension locale mais exige une nouvelle reconnaissance de cette partie ; elle ne réactive pas implicitement une reconnaissance ou une suspension de l'autre organisation. L'expiration et une date d'effet future sont distinguées de la reconnaissance en attente. Les créations, changements, reconnaissances, suspensions et reprises sont conservés dans l'audit. L'historique affiché est paginé et limité à la relation des deux parties.

`GET /api/rfq/{id}/recipients` contrôle le droit de solliciter et calcule les partenaires éligibles à partir des termes Product de la RFQ, de son nominal et de ses informations juridiques. Le masque présente les partenaires autorisés et les motifs d'exclusion. `exchange-preview` recontrôle les relations choisies : une sélection conservée dans un onglet ne contourne ni suspension, ni expiration, ni changement de périmètre. Les identifiants de relation et de fournisseur manuel restent distincts.

Le récapitulatif partage la version des termes Product avec l'organisation, le desk et la version de relation concernés. Les hypothèses, modèles, résultats, autres destinataires et accords de booking privés ne sont pas inclus. Il conserve `delivery_available=false` : **ce lot ne transmet aucune RFQ**. Le lot 3 ajoutera l'envoi versionné, le tour et le suivi individuel de livraison. Les dossiers historiques sans desk conservent leur parcours manuel ; aucune migration ne les transforme en dossiers réseau.

## Complément de collaboration du lot 1

Le masque **Affecter / transférer** permet de changer le responsable habilité et le desk pilote. Il exige le droit d'organiser, un desk cible de la même organisation, un responsable habilité, un motif et une revue explicite des partages à conserver. Le desk source ne reçoit aucun partage automatique. Les changements de périmètre périmés sont refusés et l'accès du créateur est recalculé après transfert. Partage et affectation sont sérialisés pour éviter un accès conservé implicitement lors d'une modification concurrente.

L'organisation, le créateur, le Product et sa version de termes restent identiques. Le lot 1 conserve ses travaux de qualification restants sur l'ensemble des exports, pièces et tâches longues ; cette livraison ne constitue pas une validation exhaustive de toute la chaîne de droits.

## Vérifications du 12/10

- 37 tests backend ciblés réussis : relations bilatérales, périmètres, refus inter-organisation, suspension, nouvelle reconnaissance, versions périmées, mappings locaux, projection sans envoi et affectations. Les nouveaux cas réseau utilisent une base isolée avec clés étrangères actives.
- Contrôle final des 9 cas de desk réussi après sérialisation du partage et du transfert.
- `npm run build` réussi : 425 tests frontend, puis compilation Vite. Aucune suite backend complète lancée.
- Recette à l'écran sur une base fictive dédiée : création par QA ClientTech, rapprochement et reconnaissance par QA BNP, reconnaissance par le demandeur, relation active et partenaire disponible dans la RFQ. Références de recette uniquement ; aucun accord réel ni envoi externe.
- Transfert de la RFQ fictive vers Structuration : dossier retiré de la liste et du détail du créateur exclu, message explicite de nouvelle affectation.
- Bureau 1280 × 720 : hauteur du document 720 px, modale 688 px. Mobile 390 × 844 : hauteur du document 844 px, largeur 390 px, modale 812 px, corps visible 641 px pour un contenu de 1 424 px. Le pied d'actions reste visible et le défilement demeure interne.
- Instance de recette arrêtée après utilisation ; port 8036 libéré. La base utilisateur n'a pas été utilisée.

## Suite

Le lot 3 doit utiliser ces contrôles au moment de l'envoi réel et conserver la version de relation appliquée à chaque sollicitation. L'annuaire inter-installations, l'admission par invitation et le transport authentifié restent à réaliser avant un pilote réparti sur plusieurs installations. Aucune configuration BNP réelle n'est ajoutée automatiquement par cette livraison.
