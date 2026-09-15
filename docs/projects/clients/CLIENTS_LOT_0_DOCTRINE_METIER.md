# Clients — Lot 0 : doctrine métier et référentiel

Statut : **validé fonctionnellement et socle implémenté**  
Date : 1er septembre 2026  
Nature : spécification métier et contrat d'implémentation

## 1. Objectif

Le Lot 0 définit le vocabulaire, les responsabilités et les règles d'autorité de la
partie Clients de Structura. Il sert de contrat aux lots suivants.

Structura doit devenir une mémoire commerciale augmentée : il conserve les faits,
fait émerger des habitudes explicables et aide le commercial sans transformer le
comportement passé du client en interdiction permanente.

## 2. Principes validés

1. Une habitude de trading n'est pas une contrainte bloquante.
2. Les faits issus des RFQ et Deals sont historiques et immuables.
3. Les déclarations du client sont datées et n'effacent pas l'historique.
4. Les inférences Structura sont révisables, explicables et non contractuelles.
5. Une déclaration récente peut contredire une habitude ancienne.
6. Toute conclusion affichée doit exposer ses preuves et son périmètre.
7. Une impossibilité opérationnelle documentée reste distincte d'une préférence.
8. Les données fictives, importées et natives doivent être identifiables séparément.

## 3. Périmètres métier

### Client

Le Client représente l'organisation ou l'entité juridique suivie commercialement.

### Contact et affiliation

La personne physique reste indépendante de son employeur. Son affiliation au client
est datée afin de préserver l'historique lors d'un changement d'organisation.

### Mandat, fonds, compte ou desk

Un Client peut comporter plusieurs périmètres de trading. Les habitudes et
préférences peuvent varier entre ces périmètres et ne doivent pas être agrégées sans
que cette différence soit visible.

### Portée d'une information

Une préférence, une observation ou une tendance peut être attachée :

- au Client ;
- au mandat, fonds, compte ou desk ;
- au Contact ;
- à une combinaison explicite de ces périmètres.

Une préférence portée par un Contact ne devient pas automatiquement une préférence
de toute l'organisation.

## 4. Nature des informations

| Nature | Définition | Exemple |
|---|---|---|
| Déclarée | Information exprimée par le client | « Nous préférons les notes EMTN » |
| Observée | Fait issu d'un RFQ ou d'un Deal | 12 notes EMTN sur 15 Deals |
| Déduite | Lecture produite par Structura | Habitude EMTN bien documentée |
| Commerciale | Commentaire du sales | Le client semble plus ouvert aux swaps |
| Opérationnelle | Capacité documentaire référencée | ISDA actif, CSA non référencé |

Ces natures ne doivent jamais être fusionnées silencieusement.

## 5. Structures de transaction

Les termes demandés commercialement sont : **EMTN, BMTN, OTC et Swap**.

Ils sont présentés de manière familière au sales, tout en restant distincts dans la
doctrine métier :

- EMTN, BMTN et OTC décrivent le format ou l'enveloppe de la transaction ;
- Swap décrit une famille d'instrument, généralement exécutée en OTC.

Exemple :

```text
Format        : OTC
Instrument    : Swap
Payoff        : Autocall
Documentation : ISDA
```

Autre exemple :

```text
Format        : EMTN
Instrument    : Note
Payoff        : Phoenix Memory
```

## 6. Documentation juridique

Structura référence seulement la documentation. Il n'a pas vocation, dans ce
périmètre, à devenir un système documentaire ou juridique complet.

La référence peut comprendre :

- type de documentation ;
- statut ;
- client et contrepartie concernés ;
- date de dernière vérification ;
- référence ou lien externe ;
- commentaire.

Exemples de documentation : programme EMTN, ISDA, CSA, FBF ou convention bilatérale
locale.

## 7. Catalogue initial des payoffs

Le catalogue standard initial comprend :

- Autocall ;
- Phoenix ;
- Phoenix Memory ;
- Reverse Convertible ;
- Barrier Reverse Convertible ;
- Capital garanti ;
- Participation ;
- Twin Win ;
- Shark Note ;
- Credit-Linked Note ;
- Callable Note ;
- Produits structurés de taux ;
- Swap actions ;
- Swap de taux ;
- Autre.

Un Client peut avoir un produit ou une appellation spécifique. Dans ce cas,
l'information conserve lorsque possible :

- une famille standard ;
- un nom spécifique au client ;
- une description explicite des particularités ;
- le client ou mandat concerné.

Une appellation spécifique ne rejoint pas automatiquement le catalogue global.

## 8. Habitudes et tendances

Une habitude peut porter sur une dimension ou une combinaison explicite :

- émetteur ou contrepartie ;
- format EMTN, BMTN ou OTC ;
- instrument, dont Swap ;
- payoff ;
- sous-jacent ;
- devise ;
- maturité ;
- taille de ticket ;
- protection ;
- fréquence d'observation ;
- règlement ou collatéralisation lorsque ces éléments sont pertinents.

Chaque tendance indique :

- son périmètre ;
- sa nature ;
- son contexte ;
- la période étudiée ;
- le nombre de cas comparables ;
- la dernière observation ;
- la dernière confirmation éventuelle du client ;
- son statut courant ;
- les faits qui la justifient.

## 9. Volume minimal d'observations

| Cas comparables | Présentation autorisée |
|---:|---|
| 1 | Observation isolée |
| 2 | Répétition observée, aucune tendance affirmée |
| 3 à 4 | Tendance émergente |
| 5 à 9 | Habitude observée |
| 10 et plus | Habitude bien documentée |

Les faits restent visibles sous le seuil. Le système ne masque pas le faible
échantillon et n'utilise pas de score opaque.

## 10. Récence

| Dernière observation | Présentation |
|---|---|
| Moins de 12 mois | Actuelle |
| Entre 12 et 24 mois | À confirmer |
| Plus de 24 mois | Historique |
| Déclaration récente contradictoire | En évolution |

Aucune habitude n'est automatiquement supprimée. Pour un client peu actif, une
observation ancienne peut rester utile à condition d'être clairement datée.

## 11. Confirmation par le client

Le client est l'autorité sur ses préférences déclarées. Tant qu'il n'existe pas de
portail client, le commercial enregistre la confirmation après l'interaction.

La confirmation conserve :

- le Contact source ;
- la date ;
- le commercial ayant saisi l'information ;
- le canal ;
- le périmètre ;
- la déclaration ;
- l'interaction source lorsqu'elle existe.

Le commercial ne confirme pas une inférence en son propre nom : il enregistre la
confirmation ou la contradiction exprimée par le client.

## 12. RFQ et alimentation du profil

### RFQ sans aucun Deal

Il peut être rattaché au Client, au mandat et à l'Opportunity. Il reste dans
l'historique commercial mais n'influence pas les habitudes de trading.

### RFQ ayant produit un Deal

Les quotes comparables non sélectionnés peuvent contribuer à l'analyse de sélection,
car une décision de transaction a réellement été prise.

Pour analyser un meilleur quote non sélectionné, il faut au minimum :

- le même RFQ et les mêmes termes ;
- le même format juridique lorsque matériel ;
- une direction achat/vente cohérente ;
- un quote valide et exécutable ;
- une convention économique de comparaison explicite.

Le fait « Marex était meilleur sur six RFQ traités et n'a pas été sélectionné » est
affichable. La conclusion « le client refuse Marex » ne l'est pas sans déclaration du
client.

## 13. Provenance des données

Les données historiques importées peuvent avoir le même poids que les données natives
si elles sont suffisamment fiables et normalisées.

Les données présentes au moment de cette spécification sont fictives. Elles servent
aux démonstrations et tests, mais devront rester exclues de tout profil réel futur.

Les provenances minimales sont :

- fictif ou démonstration ;
- historique importé ;
- Structura natif.

## 14. Règles d'autorité

```text
Faits issus des Deals réels
        ↓
Habitudes observées
        ↓
Tendances explicables
        ↓
Déclaration ou correction du client
        ↓
Vue commerciale actuelle
```

- Les faits RFQ et Deal ne sont pas réécrits.
- Les déclarations sont historisées.
- Les inférences peuvent être recalculées, contestées ou devenir anciennes.
- Une habitude conseille mais ne bloque pas.
- Une incapacité documentaire référencée peut signaler une impossibilité
  opérationnelle réelle.

## 15. Hors périmètre

Le Lot 0 ne comprend aucun scoring automatique, contrôle réglementaire, import
externe ou modification du Pricer et du booking.

## 16. Critères de validation

La doctrine doit représenter sans ambiguïté :

1. un client traitant habituellement en EMTN ;
2. un client traitant un Swap OTC sous ISDA ;
3. des habitudes différentes entre deux mandats ;
4. une préférence propre à un Contact ;
5. Marex meilleur quote mais non sélectionné ;
6. Marex historiquement évité puis récemment accepté ;
7. un RFQ sans Deal rattaché mais exclu des habitudes ;
8. un produit spécifique au client ;
9. une structure atypique mais non interdite ;
10. un Deal historique inchangé après évolution du profil client.

## 17. Raccordement à l'existant

Le socle du Lot 0 réutilise volontairement l'onglet et le moteur de contraintes
dynamiques existants. Il ne crée ni seconde fiche Client, ni nouvel onglet, ni
parcours parallèle.

- La route technique `/constraints` et les clés historiques sont conservées pour
  compatibilité.
- L'onglet existant est présenté au commercial comme **Préférences**.
- Les valeurs saisies sont explicitement non bloquantes ; les restrictions
  opérationnelles réelles restent distinguées.
- EMTN, BMTN et OTC sont ajoutés comme formats ; Swap comme instrument.
- Les payoffs standards servent de suggestions et restent ouverts à une
  appellation propre au client.
- Les cadres juridiques sont seulement référencés dans le profil existant.
- La provenance fictive, importée ou native est portée par la fiche Client et
  visible dans son en-tête.

Les mandats, fonds, comptes et desks restent prévus au Lot 1, lorsqu'ils auront
une utilité transactionnelle dans la chaîne Opportunity → RFQ → Deal. Les créer
dans une API ou une interface isolée au Lot 0 produirait un second référentiel
sans consommateur métier.
