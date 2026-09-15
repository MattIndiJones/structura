# Clients — Lot 1 : contexte Client optionnel dans la chaîne Produit → RFQ → Deal

Statut : **implémenté — recette technique et fonctionnelle acceptée après corrections**  
Date : 2 septembre 2026  
Prérequis : `CLIENTS_LOT_0_DOCTRINE_METIER.md`

Vérification technique du 1er septembre 2026 : 180 tests backend ciblés, 62 tests
frontend et build de production réussis. Le serveur n'a pas été démarré par la session ;
la migration s'appliquera au prochain redémarrage normal de l'instance.

Recette sur l'instance du 2 septembre 2026 : deux parcours complets ont été
matérialisés dans la base fictive, un parcours Client et un parcours Produit
autonome. Les anomalies découvertes pendant cette recette ont été corrigées et
les tests de non-régression ont été rejoués. Le détail figure au §18.

Décisions métier validées avec le sponsor le 1er septembre 2026. Ce document décrit
le résultat attendu ; il n'autorise pas la création d'un second parcours UI.

## 1. Finalité

Le Lot 1 doit rendre infaillible et auditable la chaîne qui relie, lorsqu'il existe,
un besoin commercial au Deal booké.

Le moteur Produit reste entièrement autonome. Structura doit continuer à permettre de
pricer, lancer un RFQ, sélectionner un quote et booker un Deal **sans Client, sans
mandat, sans Contact et sans Opportunity**. La partie Clients est une couche de contexte
optionnelle ; elle ne devient contraignante que lorsqu'un utilisateur décide de
rattacher le workflow à un Client.

Le problème actuel n'est donc pas l'existence d'un Deal autonome sans attribution. Le
problème est qu'une Opportunity volontairement transmise au RFQ peut être perdue lors
du passage RFQ → Pricer → Booking. Un Deal initié dans un contexte commercial peut
alors perdre une attribution qui existait en amont.

Le Lot 1 ne construit pas encore le moteur d'habitudes. Il fiabilise les faits dont ce
moteur dépendra.

## 2. Résultat attendu

```text
PARCOURS PRODUIT AUTONOME
Pricer → Indicatif / RFQ → Quote choisi → Deal

PARCOURS ENRICHI D'UN CONTEXTE CLIENT
Client + Mandat + Contact → Opportunity ─┐
                                         ├→ RFQ → Quote choisi → Deal
Client + Mandat sans Opportunity ────────┘
                                                    ↓
                                  Historique commercial réconcilié
```

Les deux parcours utilisent les mêmes RFQ, le même Pricer, le même Booking et le même
Deal. Il n'existe pas une version « commerciale » séparée du moteur Produit.

Lorsqu'un contexte Client est présent, Structura doit savoir :

- pour quel Client le travail est réalisé ;
- pour quel mandat, fonds, compte ou desk ;
- avec quel Contact ;
- à quelle Opportunity il répond ;
- quelle structure de transaction est recherchée ;
- quelle structure a été demandée, quotée puis bookée ;
- quelle donnée est une référence courante et quelle donnée est figée.

### 2.1. Point de départ réel

Le Lot 1 n'est pas une construction à partir de zéro. Structura possède déjà :

- les liens `Opportunity → RFQ` et `Opportunity → Deal` ;
- le lien unique `RFQ → Deal`, qui protège déjà contre un double booking ;
- les contrôles backend de cohérence entre Client, Contact, Opportunity et entité ;
- un snapshot commercial du Client, du Contact et de l'Opportunity au booking ;
- le chargement d'un RFQ dans le Pricer ;
- les vues existantes Opportunity, RFQ, Pricer, Booking et Deal.

Le défaut principal est un défaut de continuité : lors du passage
`RFQ → Pricer → Booking`, le contexte Client/Contact/Opportunity n'est pas transporté
de bout en bout par l'interface, et le backend ne le redéduit pas encore du RFQ comme
source autoritative. Le Deal peut donc perdre son attribution alors que l'information
existait en amont.

Le seul nouvel objet métier structurant de ce lot est le **mandat ou périmètre de
trading**. Le reste consiste à compléter, raccorder et durcir l'existant.

L'absence de contexte Client dans un workflow autonome est un état valide. Elle ne
doit produire ni erreur, ni avertissement bloquant, ni obligation de justification.

### 2.2. Raccordement obligatoire aux écrans existants

Le Lot 1 étend uniquement :

- le formulaire et la fiche Opportunity existants ;
- la vue RFQ existante ;
- le chargement RFQ du store de pricing et le bandeau de contexte du Pricer ;
- le composant de booking existant ;
- la fiche Deal et son mécanisme d'amendement/audit existants ;
- la fiche Client existante pour administrer ses mandats.

Il ne crée ni nouveau module Client, ni second formulaire Opportunity, ni second
Pricer, ni écran de booking concurrent. Les nouveaux champs s'insèrent dans les
composants et routes actuels.

## 3. Principes non négociables

1. Le backend est l'autorité de l'attribution commerciale.
2. Le frontend transporte et affiche le contexte mais ne l'invente pas.
3. Le workflow Produit, RFQ, quote et Booking fonctionne sans objet commercial.
4. Un booking depuis un RFQ enrichi hérite du contexte validé du RFQ.
5. Le Deal conserve toujours son snapshot produit et juridique ; son snapshot
   commercial n'existe que si un contexte Client est présent.
6. Un RFQ ne peut pas produire deux Deals par double clic ou requête répétée.
7. Une incohérence cross-client, cross-mandat ou cross-entité est refusée dès qu'un
   contexte Client est engagé.
8. Les rattachements et corrections matérielles sont audités.
9. Les données fictives sont identifiées et exclues des futures analyses réelles.
10. Une Opportunity peut produire plusieurs Deals, mais un même RFQ ne produit qu'un
   seul Deal.
11. L'état courant corrigé ne doit jamais effacer l'attribution constatée au booking.
12. Aucun champ Client nullable ne doit devenir une dépendance du pricing, du RFQ, du
    booking, de la valorisation ou du cycle de vie produit.

### Activation des règles commerciales

Le contexte commercial est considéré comme engagé dès qu'un Client, un mandat, un
Contact ou une Opportunity est volontairement rattaché. À partir de ce moment, le
backend exige un ensemble cohérent et refuse les demi-rattachements au moment de
l'envoi du RFQ ou du booking.

À l'inverse, l'absence totale de ces références définit un **parcours Produit
autonome**. Ce parcours n'est pas implicitement classé comme test, démonstration ou
opération interne et ne requiert aucun motif.

## 4. Mandat minimal nécessaire au Lot 1

Le Lot 1 introduit ou formalise le périmètre Mandat/Fonds/Compte/Desk afin que les
attributions suivantes puissent être précises.

Le périmètre minimal contient :

- Client parent ;
- type : mandat, fonds, compte, desk ou autre ;
- nom ;
- statut actif ou archivé ;
- devise de référence facultative ;
- commentaire ;
- provenance fictive, importée ou native.

Les préférences détaillées du mandat seront traitées dans un lot ultérieur.

Le mandat est :

- facultatif pendant la création d'une Opportunity en brouillon ;
- sans objet dans un parcours Produit autonome ;
- obligatoire avant l'envoi d'un RFQ rattaché à un Client ;
- obligatoire pour un Deal rattaché à un Client, direct ou issu d'un RFQ ;
- toujours rattaché à un seul Client ;
- archivé et non supprimé lorsqu'il a déjà été utilisé.

La gestion se fait dans un bloc compact de la fiche Client existante. La sélection du
mandat est ajoutée au formulaire Opportunity et aux contextes RFQ/Booking existants ;
aucun écran autonome n'est créé pour ce lot.

## 5. Contexte porté par l'Opportunity

Une Opportunity qualifiée doit pouvoir porter :

- Client ;
- mandat ou périmètre de trading ;
- Contact principal et affiliation ;
- owner commercial ;
- besoin ou objectif ;
- notionnel et devise ;
- fenêtre de transaction ;
- format envisagé : EMTN, BMTN ou OTC ;
- instrument envisagé, dont Swap ;
- famille de payoff standard ou spécifique ;
- prochaine action et date ;
- provenance des données.

Au stade initial, certaines informations peuvent être inconnues. La qualification doit
rendre visibles les champs manquants sans inventer de valeur par défaut.

La qualification n'est pas un nouveau statut. C'est une règle de complétude contrôlée
avant de lancer un RFQ rattaché à un Client : Client, mandat, owner et besoin doivent
être renseignés ; le Contact reste référencé lorsqu'il est connu, et toute affiliation
renseignée doit être cohérente avec le Client.

## 6. Création et rattachement d'un RFQ

### RFQ lancé depuis une Opportunity

Le RFQ hérite automatiquement :

- du Client ;
- du mandat ;
- du Contact ;
- de l'Opportunity ;
- du format et de l'instrument envisagés lorsqu'ils sont déjà connus.

Le commercial ne doit pas ressaisir ces informations.

Lors de sa création, le RFQ conserve à la fois les références utiles et un snapshot
compact du contexte commercial reçu. Une modification ultérieure de l'Opportunity ne
réécrit pas silencieusement le contexte sur lequel le RFQ a été envoyé.

### RFQ créé directement

Un RFQ direct reste possible pour préserver la rapidité du desk. Il peut être :

- créé et exécuté jusqu'au Deal sans aucune notion Client ;
- immédiatement rattaché à un Client et un mandat, avec ou sans Opportunity ;
- rattaché ultérieurement tant qu'aucun Deal incohérent n'a été booké ;
- explicitement classé comme test, démonstration ou travail interne.

Un rattachement ou changement ultérieur est audité.

En production, un RFQ direct peut donc suivre l'une des voies suivantes :

- **Produit autonome** : aucune donnée Client et aucune justification requises ;
- **rattaché à un Client** : Client et mandat obligatoires, Opportunity facultative ;
- **test/démonstration** : provenance fictive explicite, données exclues des
  statistiques réelles ;
- **interne** : classification explicite uniquement lorsque cette qualification est
  utile au desk, données exclues des statistiques commerciales Clients.

### RFQ sans Deal

Lorsqu'il est rattaché à un Client, il reste visible dans son historique commercial
mais, conformément au Lot 0, n'alimente pas les habitudes de trading. Un RFQ Produit
autonome reste dans les vues RFQ/Produit et n'entre dans aucun historique Client.

## 7. Passage du RFQ au Pricer

Le Pricer chargé depuis un RFQ affiche un bandeau compact et non ambigu **si le RFQ
porte un contexte Client** :

- Client ;
- mandat ;
- Contact ;
- Opportunity ;
- référence RFQ ;
- provenance « Hérité du RFQ ».

Ce contexte n'est pas un ensemble de champs silencieusement modifiables dans le
Pricer. Toute correction matérielle doit revenir au workflow approprié et être validée
côté serveur.

Le store de pricing existant transporte ce contexte avec les termes du RFQ lorsqu'il
existe. Le Pricer ne crée pas une copie locale indépendante du Client ou du mandat.
Sans contexte Client, son comportement actuel reste inchangé et aucun bandeau vide ou
avertissement commercial n'est imposé.

Lorsque la distinction est utile, l'utilisateur peut identifier s'il travaille :

- depuis une Opportunity et un RFQ ;
- depuis un RFQ direct ;
- depuis le Pricer sans contexte commercial ;
- dans un contexte fictif ou interne.

## 8. Booking

### Booking depuis RFQ

Si le RFQ porte un contexte Client, le backend le déduit de la source ; il ne fait pas
confiance aux identifiants commerciaux éventuellement renvoyés par le navigateur.
S'ils sont présents, ils servent uniquement à détecter une divergence et à refuser le
booking. Si le RFQ n'en porte aucun, le booking aboutit normalement sans créer un
contexte commercial artificiel.

Les contrôles Client suivants ne sont exécutés que si ce contexte existe :

- que l'Opportunity appartient au Client ;
- que le mandat appartient au Client ;
- que l'affiliation du Contact est cohérente à la date concernée ;

Dans tous les cas, le backend vérifie :

- que le quote sélectionné appartient au RFQ ;
- que le RFQ n'a pas déjà produit le Deal concerné ;
- que la structure bookée correspond au quote sélectionné ou qu'une différence est
  explicitement documentée.

Le corps envoyé par le frontend ne peut pas remplacer ces faits par d'autres valeurs.

Le booking continue de réutiliser la contrainte existante **un RFQ = un Deal**. Une
Opportunity multi-tranches utilise plusieurs RFQ, chacun pouvant produire son Deal,
ou un Deal direct explicitement rattaché lorsqu'il s'agit réellement du bon workflow.

### Booking direct depuis le Pricer

Le booking direct accepte les cas suivants :

- **Deal Produit autonome** : aucun Client, mandat, Contact, Opportunity ou motif
  commercial n'est requis ;
- **Deal rattaché à un Client et une Opportunity** : Client et mandat requis ;
- **Deal rattaché à un Client sans Opportunity** : autorisé avec un motif expliquant
  le contournement du pipeline Opportunity ;
- transaction explicitement interne ou technique : motif requis seulement si cette
  classification est choisie ;
- démonstration ou test : provenance fictive obligatoire.

Un Deal autonome sans attribution est un Deal Produit valide. Il n'apparaît simplement
pas dans les statistiques Clients et ne doit jamais être silencieusement interprété
comme une transaction commerciale attribuée.

## 9. Snapshot du Deal

Le Deal fige dans tous les cas :

- son contrat Produit et son payoff ;
- le RFQ et le quote sélectionné lorsqu'ils existent ;
- le format juridique EMTN, BMTN ou OTC ;
- la famille d'instrument, dont Swap ;
- l'émetteur ;
- le provider de quote ;
- la contrepartie de booking ;
- la documentation référencée lorsqu'elle est connue ;
- le règlement et la collatéralisation lorsqu'ils sont matériels ;
- la provenance fictive, importée ou native.

Il fige en complément, lorsqu'un contexte Client existe :

- identifiants et libellés du Client ;
- mandat ou périmètre de trading ;
- Contact et affiliation au moment du Deal ;
- Opportunity ;
- owner commercial pertinent ;

Tous les champs commerciaux de ce complément restent nullables. Une modification
ultérieure du Client, du Contact, du mandat, du RFQ ou des préférences ne modifie pas
ce snapshot.

Lorsqu'un contexte commercial existe, le Deal expose séparément :

- l'**attribution initiale**, exactement telle qu'elle a été figée au booking ;
- l'**attribution courante corrigée**, uniquement si une rectification a été approuvée ;
- l'événement de rectification permettant d'expliquer qui a proposé, validé et
  appliqué la correction.

## 10. Statut de l'Opportunity

Le statut commercial ne doit pas contredire les faits.

Cette section ne s'applique qu'aux Deals rattachés à une Opportunity. Un RFQ ou un Deal
Produit autonome ne crée pas automatiquement d'Opportunity et ne modifie aucun statut
commercial.

Le Lot 1 conserve les statuts existants et leur vocabulaire. Il ne crée pas un second
workflow conceptuel. Le seul état manquant à ajouter est `partially_won` afin de gérer
les opportunités multi-tranches.

Lecture fonctionnelle du cycle existant :

```text
Lead / besoin / idée / intérêt client / structuring
                         ↓
                RFQ / négociation
                         ↓
              Partiellement gagnée
                    ↓           ↓
                 Gagnée       Perdue
                         ↘ Annulée / Archivée
```

Règles validées :

- l'existence d'un RFQ actif est affichée comme un fait ; elle n'écrase pas sans
  contrôle le statut commercial choisi ;
- le premier Deal booké fait passer l'Opportunity à `partially_won` ;
- `partially_won` permet à l'Opportunity de rester ouverte pour d'autres
  tranches ou Deals ;
- `won` est une décision explicite du commercial lorsqu'aucun complément n'est
  attendu ;
- `lost` requiert un motif commercial ;
- `cancelled` désigne un abandon interne ou une demande retirée sans décision de
  concurrence ;
- une Opportunity ne peut pas être perdue si un Deal booké existe sans traitement
  explicite de la contradiction ;
- un gain externe à Structura requiert une référence et une justification.

## 11. UX attendue

### Fiche Opportunity

Elle présente dans un seul chemin :

1. contexte Client, mandat et Contact ;
2. besoin et économie ;
3. format juridique et instrument envisagés ;
4. RFQ associés ;
5. Deals obtenus ;
6. prochaine action ;
7. historique et audit.

Action principale : **Lancer un RFQ**.

Cette action ouvre la vue RFQ actuelle préremplie ; elle ne duplique pas le formulaire
RFQ dans la fiche Opportunity.

### Fiche RFQ

Lorsqu'il existe, elle affiche en permanence le contexte commercial et fournit des
liens directs vers le Client et l'Opportunity. Sans contexte, la fiche RFQ actuelle
reste centrée sur le Produit et les quotes, sans espace commercial vide imposé.

Action principale lorsqu'un quote est sélectionnable : **Sélectionner et booker**.

### Écran de booking

Avant confirmation, un résumé montre les valeurs qui seront figées. Une attribution
héritée du RFQ est identifiée comme telle et n'est pas présentée comme une saisie libre.
En parcours autonome, le résumé reste entièrement opérationnel sans bloc Client.

### Fiche Client

La fiche actuelle reçoit un bloc compact **Mandats / périmètres** permettant de créer,
modifier et archiver les seules informations définies au §4. Les habitudes de trading
restent dans le dispositif de préférences existant et ne sont pas déplacées dans le
mandat au Lot 1.

## 12. Audit

Lorsqu'un contexte commercial existe, les événements suivants sont journalisés avec
avant/après lorsque pertinent :

- création et modification du rattachement Client ;
- changement de mandat ;
- changement de Contact ou d'affiliation ;
- rattachement ou détachement d'un RFQ ;
- changement d'owner ;
- passage de statut Opportunity ;
- booking ;
- tentative de booking en double ;
- correction exceptionnelle d'une attribution ;
- classement interne, fictif ou commercial.

Une correction post-booking suit le mécanisme existant de proposition et validation
à quatre yeux :

1. un utilisateur habilité propose la nouvelle attribution et justifie la correction ;
2. un second utilisateur habilité l'approuve ou la rejette ;
3. l'application conserve le snapshot initial et ajoute un événement de rectification ;
4. les vues courantes utilisent l'attribution corrigée tout en laissant l'originale
   consultable.

Il n'existe pas d'édition directe du snapshot initial.

## 13. Hors périmètre

Le Lot 1 ne comprend pas :

- calcul des habitudes ou préférences ;
- analyse de sélection des providers ;
- scoring prédictif ;
- dashboard commercial complet ;
- import historique avancé ;
- stockage des contrats ISDA, CSA ou EMTN ;
- moteur réglementaire ou de suitability ;
- refonte générale du Pricer.

## 14. Scénarios d'acceptation

1. Opportunity → RFQ → Pricer → Deal conserve Client, mandat et Contact.
2. Un second clic de booking ne crée pas un deuxième Deal.
3. Un mandat appartenant à un autre Client est refusé.
4. Un Contact non affilié au Client est refusé ou explicitement non retenu.
5. Une modification de la fiche Client ne change pas le Deal booké.
6. Un Contact change d'employeur sans modifier son ancien snapshot.
7. Plusieurs RFQ peuvent être liés à la même Opportunity.
8. Plusieurs Deals peuvent être liés à une Opportunity, mais jamais deux Deals au
   même RFQ.
9. Un RFQ direct peut être rattaché ultérieurement avec audit.
10. Un RFQ sans Deal apparaît dans l'historique mais n'alimente pas les habitudes.
11. Un Deal Produit autonome reste bookable et est absent des statistiques Clients ;
    un Deal fictif est en plus exclu des statistiques Produit réelles.
12. Un booking cross-entity est refusé.
13. Une Opportunity perdue ne peut pas masquer silencieusement un Deal booké.
14. Le snapshot reste relisible si le RFQ ou le quote est modifié ultérieurement.
15. Le premier Deal place l'Opportunity en `partially_won`, puis le commercial peut la
    clôturer en `won`.
16. Un RFQ rattaché à un Client sans mandat est refusé ; le même RFQ sans aucun
    contexte Client reste entièrement opérationnel et ne requiert aucun motif.
17. Une rectification d'attribution requiert deux intervenants et laisse le snapshot
    initial consultable.
18. Pricer → RFQ → Quote → Deal fonctionne de bout en bout sans Client, mandat,
    Contact ni Opportunity.
19. Pricer → Booking direct fonctionne sans donnée commerciale et sans créer
    d'Opportunity implicite.

## 15. Critères de sortie

- 100 % des bookings depuis RFQ conservent leur attribution commerciale.
- Aucun Deal commercial n'est silencieusement sans Client ou mandat.
- 100 % des parcours Produit autonomes continuent de fonctionner sans objet Client.
- Le backend reconstitue le contexte depuis la source autoritative.
- Le booking est idempotent.
- Les snapshots sont immuables et relisibles.
- Les statuts Opportunity sont cohérents avec les RFQ et Deals.
- Les données fictives sont visiblement séparées.
- Les parcours directs restent possibles ; seuls les modes test/démonstration ou
  interne volontairement déclarés exigent leur classification propre.
- Les scénarios end-to-end ciblés passent sur une base isolée.
- Aucun nouvel écran parallèle n'a été introduit.
- L'absence de contexte commercial ne génère ni blocage ni avertissement trompeur.

## 16. Décisions validées

1. Une Opportunity peut produire plusieurs Deals ou tranches.
2. Le premier Deal place l'Opportunity en `partially_won` ; la clôture en `won` reste
   manuelle.
3. Le mandat est sans objet dans le parcours Produit autonome, facultatif dans une
   Opportunity en brouillon et obligatoire dès qu'un RFQ ou Deal est rattaché à un
   Client.
4. Un RFQ direct sans Opportunity reste autorisé, avec ou sans contexte Client. Sans
   Client, aucune classification interne/test et aucun motif ne sont imposés.
5. Un Deal direct sans Opportunity reste autorisé. Sans contexte Client, il s'agit
   d'un Deal Produit autonome normal. Avec un Client, le mandat et un motif sont
   obligatoires.
6. Une correction post-booking nécessite un droit renforcé et une validation à quatre
   yeux.
7. Une correction conserve le snapshot initial et crée un événement de rectification.

## 17. Séquence de réalisation du Lot 1

### Étape 1 — Mandat et règles de complétude

- ajouter le mandat minimal au modèle existant ;
- l'administrer depuis la fiche Client actuelle ;
- l'ajouter au formulaire Opportunity actuel ;
- empêcher les incohérences Client/mandat et l'effacement d'un mandat déjà utilisé ;
- appliquer les règles Client optionnel versus Produit autonome, sans rendre le
  mandat dépendant du moteur Produit.

### Étape 2 — Continuité Opportunity → RFQ

- enrichir le RFQ existant avec les références et le snapshot commercial ;
- préremplir depuis l'Opportunity sans ressaisie ;
- préserver sans friction le RFQ direct sans contexte Client ;
- auditer les rattachements et changements.

### Étape 3 — Continuité RFQ → Pricer → Booking

- transporter le contexte dans le store de pricing existant lorsqu'il existe ;
- l'afficher conditionnellement dans le Pricer et le résumé de booking existants ;
- déduire côté serveur l'attribution depuis le RFQ ;
- refuser les divergences et préserver l'idempotence existante.

### Étape 4 — Deal, statuts et rectifications

- compléter le snapshot Produit/juridique de tous les Deals et le snapshot commercial
  nullable avec le mandat ;
- ajouter `partially_won` au workflow Opportunity existant ;
- automatiser le passage au premier Deal sans clôturer l'Opportunity ;
- raccorder les corrections d'attribution au mécanisme d'amendement et de validation
  à quatre yeux existant.

### Étape 5 — Recette de chaîne complète

- couvrir les scénarios du §14 au niveau API et interface ;
- vérifier les données fictives séparément des données commerciales ;
- tester les parcours Produit autonome, commercial, historique, direct,
  multi-tranches et rectifié ;
- vérifier qu'aucune régression n'est introduite dans RFQ, Pricer, Booking et Deal.

Le développement pourra commencer par l'Étape 1 uniquement après validation de ce
document. Chaque étape réutilise les composants existants et doit être démontrable de
bout en bout avant de passer à la suivante.

## 18. Compte rendu de recette sur l'instance

### 18.1. Verdict

**Accepté après corrections.** Les deux invariants centraux sont démontrés sur
l'instance réelle de développement :

- un workflow volontairement rattaché conserve son Client et son mandat jusqu'au
  Deal et fait évoluer l'Opportunity ;
- un workflow sans aucune donnée commerciale reste bookable et ne crée aucune
  attribution implicite.

### 18.2. Parcours Client matérialisé

- Client : `Bank Helvetia` (`client_id=8`, provenance fictive) ;
- mandat : `Fonds Recette Lot 1` (`mandate_id=1`) ;
- Opportunity : `OPP-20260902-001` (`opportunity_id=10`) ;
- RFQ : `RFQ-20260902-001` (`rfq_id=2`) ;
- Deal : `DEMO-20260902-001` (`deal_id=11`) ;
- cadre juridique : `OTC` ; instrument : `Swap` ; payoff : `Autocall` ;
- résultat : attribution initiale figée et attribution courante identiques ;
  RFQ `EXECUTED` ; Opportunity `partially_won` ; paiement conservé au
  `2029-09-19`.

Le Client choisi n'avait pas de Contact actif. La continuité Contact et les refus
d'affiliation incohérente restent donc vérifiés par les tests API ciblés, sans créer
une personne fictive supplémentaire pour la recette.

### 18.3. Parcours Produit autonome matérialisé

- RFQ : `RFQ-20260902-002` (`rfq_id=3`) ;
- Deal : `DEMO-20260902-002` (`deal_id=12`) ;
- cadre juridique : `EMTN` ; instrument : `Note` ; payoff : `Call` ;
- résultat : booking accepté sans Client, mandat, Contact, Opportunity ni motif ;
- les champs `client_id`, `mandate_id`, `primary_affiliation_id`,
  `opportunity_id`, `client_provenance` et `client_attribution_current` sont
  tous `NULL` ;
- l'historique de Bank Helvetia compte uniquement le Deal Client, pas ce Deal
  autonome.

### 18.4. Anomalies révélées et corrigées

1. **Migration des mandats** — une base Lot 0 portait le texte libre dans
   `notes`, alors que le Lot 1 lisait `comment`, ce qui provoquait une erreur 500
   à l'ouverture d'une fiche Client. La migration ajoute `comment` et y recopie
   les anciennes données une seule fois.
2. **Date de paiement RFQ → Pricer** — une course entre le chargement asynchrone
   de la RFQ et la proposition automatique à J+3 pouvait remplacer la date du
   term sheet. Les trois dates RFQ sont désormais remises explicitement au
   formulaire de booking lors du handoff final.
3. **RFQ faussement « prête à booker »** — l'écran pouvait annoncer cet état sans
   prix modèle RFQ horodaté, alors que le backend refusait justement le booking.
   L'action exige désormais visiblement le calcul du prix modèle avant d'ouvrir
   le Pricer.

### 18.5. Preuves de contrôle

- migration ancienne base et API Clients : **37 tests réussis** après correction ;
- frontend : **62 tests réussis** ;
- build de production Vite : **réussi** ;
- piste d'audit observée : `RFQ_CREATED`, `QUOTE_SELECTED`,
  `MODEL_PRICE_RECORDED`, refus de booking explicite puis `BOOKING_ACCEPTED` ;
- après booking, la RFQ expose le Deal exécuté et ne propose plus une seconde
  action de booking ; la contrainte structurelle un RFQ / un Deal reste couverte
  par les tests backend.

Les objets ci-dessus sont conservés dans la base parce qu'ils constituent les
preuves de recette et sont explicitement marqués comme données fictives.
