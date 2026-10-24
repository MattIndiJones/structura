# RFQ — navigation séparée entre demandeur et répondant

Date : 13/10/2026. Branche : `codex/hybrid-saas-foundation`.
Modifications locales, sans commit ni push.

Le menu **RFQ** présente directement deux parcours au même niveau :

- **RFQ Fournisseurs** (`/rfq`) : créer et envoyer une demande de prix,
  puis comparer les cotations reçues.
- **RFQ reçues** (`/rfq/recues`) : consulter les demandes adressées aux desks
  habilités, les prendre en charge et préparer une réponse bancaire.

Analyse Contreparties et Relations et exécutions restent accessibles dans ce menu.
Le retour de secours de la réception mène au menu RFQ. Le raccourci existant depuis
les demandes fournisseurs reste disponible, sans être le point d'entrée obligatoire.

L'écran de réception, Product, moteurs, masques, droits et contrôles RFQ existants
sont réutilisés. Aucun changement de traitement métier ni de transport réseau.
L'ajout de la carte n'accorde aucun accès supplémentaire aux dossiers reçus.
Le viewport borné, le scroll interne et les séparateurs de milliers de la réception
sont conservés.

Tests suspendus à la demande de Philippe ; compilation frontend seule
(`npm run build:skip-tests`) réussie.
La recette visuelle est différée. Aucun serveur lancé pour ce correctif.
