# Clients — Lot 3 : intégration au Life Cycle

## Objectif

Rendre les événements des produits bookés exploitables commercialement depuis
le module Clients sans créer une seconde vérité contractuelle.

Le Life Cycle reste autonome et demeure la source unique pour :

- le calendrier des constatations ;
- les fixings officiels et indicatifs ;
- les statuts d'événement ;
- les rappels, maturités et résolutions ;
- les alertes et exceptions opérationnelles.

Un deal sans client continue donc de fonctionner exactement comme avant.

## Périmètre livré

1. La watchlist Life Cycle accepte des filtres optionnels `client_id` et
   `mandate_id` et expose ces identifiants dans ses lignes.
2. La fiche Client ouvre cette watchlist existante, préfiltrée sur le client ou
   sur le mandat actuellement analysé.
3. Une transaction bookée ouvre directement son calendrier dans l'onglet
   Events du Pricer.
4. Le moteur de signaux commerciaux projette la prochaine `DealEvent` non
   annulée de chaque deal actif dans l'horizon configuré.
5. Le signal indique qu'un coupon ou un rappel reste conditionnel au fixing et
   au script figé : une date de constatation n'est pas une promesse de flux.
6. Les maturités issues d'un historique importé restent visibles, mais sont
   explicitement identifiées comme informations commerciales non portées dans
   le book et n'ouvrent aucun Life Cycle.

## Invariants

- Aucun calendrier, statut ou résultat produit n'est persisté dans le module
  Clients.
- Les liens se font par identifiants, jamais par nom de client ou de
  contrepartie.
- La contrepartie de trading et le client commercial restent deux notions
  distinctes.
- Seul le prochain événement par deal est projeté afin de ne pas transformer
  les signaux en copie du calendrier complet.
- Les deals historiques sans `DealEvent` utilisent temporairement leur
  maturité contractuelle comme repli explicite `life_cycle_legacy`.
- Le filtre « Mes dossiers seulement » s'applique également aux événements des
  deals bookés.

## Hors périmètre

- nouvelle table d'événements Client ;
- second scheduler ou système d'alertes ;
- calcul de probabilité d'autocall ;
- duplication du tableau Events dans la fiche Client ;
- transformation d'une transaction importée en position de risque.

## Critères de recette

- `/api/deals/watchlist` sans filtre restitue le comportement produit autonome ;
- un filtre Client/Mandat ne retourne que les deals actifs accessibles de ce
  périmètre ;
- la même date et le même identifiant d'événement sont visibles depuis Clients
  et Life Cycle ;
- un événement annulé n'est jamais projeté comme événement à venir ;
- un signal de constatation ne présente jamais un coupon ou un rappel comme
  certain ;
- une maturité importée porte la provenance `imported_history` et aucun
  `deal_id` ;
- les contrôles de fixing et quatre yeux restent inchangés.
