# Clients — Lot 2 : habitudes de trading explicables et multi-périmètres

Statut : **description fonctionnelle et technique à valider avant codage**  
Date : 2 septembre 2026  
Prérequis : `CLIENTS_LOT_0_DOCTRINE_METIER.md` et
`CLIENTS_LOT_1_CHAINE_COMMERCIALE.md`

## 1. Finalité

Le Lot 2 transforme les faits fiabilisés par le Lot 1 en une mémoire commerciale
utilisable. Il doit aider le commercial à comprendre ce qu'un Client, un mandat ou un
Contact fait habituellement, ce qu'il a déclaré, ce qui semble évoluer et quelles
questions doivent être reposées.

Il ne doit jamais transformer le passé en interdiction.

Exemple attendu :

```text
Marex a fourni le meilleur prix sur 6 des 8 RFQ comparables ayant abouti.
Marex n'a été retenue sur aucune de ces 6 RFQ.
Dernier cas : 14 août 2026.
Motif client documenté : aucun.
Lecture autorisée : comportement récurrent à revalider avec le client.
Lecture interdite : le client refuse Marex.
```

Si Marex est ensuite retenue, l'ancien comportement reste visible et la vue courante
indique que l'habitude est possiblement en évolution.

## 2. Valeur commerciale recherchée

Sur une fiche Client, le sales doit pouvoir répondre rapidement à cinq questions :

1. Que traite habituellement ce Client ou ce mandat ?
2. Qu'a-t-il explicitement déclaré, à qui et quand ?
3. Les transactions récentes confirment-elles ou contredisent-elles cette déclaration ?
4. Comment arbitre-t-il entre les fournisseurs lors des RFQ réellement traitées ?
5. Sur quels faits, quelle période et quel volume repose chaque lecture ?

Le produit devient commercialement utile lorsque la réponse est actionnable et
défendable devant un autre commercial, un manager ou un auditeur, sans dépendre de la
mémoire de la personne qui suit le compte.

## 3. Diagnostic de départ

Le Lot 2 ne repart pas de zéro. Structura possède déjà :

- un moteur d'intelligence Client fondé sur les Deals et historiques importés ;
- des seuils de preuve et une lecture de la récence ;
- une comparaison entre préférences saisies et transactions observées ;
- un référentiel dynamique de préférences standards ou spécifiques à un Client ;
- la cadence, les tickets, les maturités, les devises, les émetteurs et les produits ;
- les RFQ, les quotes, le quote retenu et leur snapshot au booking ;
- les nouveaux rattachements Client, mandat, Contact et Opportunity ;
- les dimensions format, instrument, payoff et documentation juridique du Lot 1.

Ces éléments sont pertinents et doivent être conservés. En revanche, ils ne sont pas
encore suffisamment fiables pour constituer un profil commercial de production.

| Élément actuel | Décision Lot 2 | Motif |
|---|---|---|
| Seuils de preuve 1 / 2 / 3-4 / 5-9 / 10+ | Conserver | Lecture simple, transparente et déjà conforme au Lot 0 |
| Récence actuelle / à confirmer / historique | Conserver | Empêche de présenter une ancienne habitude comme vérité actuelle |
| Onglet existant « Préférences » | Enrichir | Pas de nouvel écran ni de second référentiel |
| Profil dynamique standard et spécifique Client | Conserver | Répond au besoin de personnalisation sans casser le vocabulaire commun |
| Agrégation générale au niveau Client | Corriger | Elle masque aujourd'hui les différences entre mandats |
| Lecture par Contact | Conserver mais isoler | Une préférence personnelle ne doit pas devenir celle de toute la maison |
| Champ générique `product_type` | Décomposer | Il ne distingue pas format EMTN/OTC, instrument Swap/Note et payoff |
| Données fictives dans les calculs | Exclure du profil réel | Une démonstration ne doit jamais produire une conclusion commerciale |
| Vocabulaire « autorisé / exclu / politique » | Remplacer dans l'usage commercial | Il transforme trop facilement une habitude en contrainte |
| Historique courant des préférences sous forme de blob | Compléter | La version courante ne suffit pas pour dater une déclaration ou une contradiction |
| Score synthétique ou prédiction opaque | Ne pas introduire | Non explicable et prématuré au regard des volumes disponibles |

### Rating avant Lot 2

| Axe | Note | Lecture |
|---|---:|---|
| Continuité Opportunity → RFQ → Deal | 8,5/10 | Le Lot 1 a sécurisé la matière première |
| Pertinence métier des habitudes actuelles | 5,5/10 | Bonnes idées, mais agrégation encore trop grossière |
| Auditabilité des conclusions | 6/10 | Les transactions sont traçables, les déclarations le sont insuffisamment |
| Compatibilité avec le parcours Produit autonome | 9/10 | Invariant acquis et à préserver |
| Viabilité commerciale globale de la partie Clients | 6/10 | Démontrable, mais pas encore assez fiable pour guider un sales |

La cible raisonnable après Lot 2 est une viabilité commerciale de **8 à 8,5/10**. Le
reste dépendra ensuite des outils de pilotage et d'action commerciale, pas d'un moteur
d'habitudes plus sophistiqué.

## 4. Principe non négociable : le Produit reste autonome

Le Lot 2 n'ajoute aucune dépendance commerciale au Pricer, au RFQ, au Booking, au Deal,
à la valorisation ou au lifecycle.

```text
Pricer → RFQ → Deal sans Client
                 ↓
          fonctionnement inchangé

Client ou mandat rattaché → mêmes objets Produit
                 ↓
          habitudes calculables après les faits
```

- Sans Client, aucun profil n'est calculé et aucun avertissement commercial n'apparaît.
- Une préférence ne filtre jamais les fournisseurs et ne bloque jamais une structure.
- Une habitude ne préremplit pas silencieusement le produit ou le quote retenu.
- Les champs EMTN, BMTN, OTC, Swap, Note et payoff restent des attributs Produit et
  juridiques, utilisables avec ou sans contexte commercial.

## 5. Les cinq natures d'information

Le Lot 2 rend visuellement et techniquement distinctes cinq natures :

| Nature | Autorité | Exemple |
|---|---|---|
| Fait exécuté | Deal ou historique importé qualifié | Swap OTC traité avec UBS le 3 juin |
| Habitude observée | Calcul déterministe Structura | 7 Deals OTC sur 9 cas comparables |
| Préférence déclarée | Client, enregistrée par le sales | « Préférence actuelle pour les EMTN » |
| Lecture déduite | Structura, révisable | Usage OTC en hausse sur les 12 derniers mois |
| Capacité opérationnelle | Référence documentaire | ISDA référencé comme actif avec une contrepartie |

Une note commerciale reste une note. Elle peut déclencher une question ou une saisie
de préférence déclarée, mais elle ne devient pas automatiquement un fait Client.

## 6. Périmètres et héritage

Le calcul doit exister séparément pour :

- le Client ;
- chaque mandat, fonds, compte ou desk ;
- chaque Contact via son affiliation datée ;
- le groupe « périmètre non identifié » pour les anciennes transactions sans mandat.

La vue Client peut résumer ses mandats, mais elle doit rendre leur hétérogénéité
visible. Elle ne peut pas annoncer « le Client traite en EMTN » si un mandat traite en
EMTN et un autre exclusivement en Swap OTC.

Une préférence Client constitue un contexte général. Une préférence de mandat plus
précise est présentée en priorité sur ce mandat, sans effacer ni modifier la préférence
Client. Une préférence de Contact reste attachée à l'affiliation concernée.

## 7. Matière première autorisée

### 7.1. Alimente les habitudes de trading

- un Deal exécuté et rattaché à un Client ;
- une transaction historique importée, normalisée et non annulée ;
- le snapshot du RFQ d'un Deal exécuté, uniquement pour étudier la décision de
  fournisseur.

### 7.2. N'alimente pas les habitudes de trading

- un RFQ sans Deal ;
- un indicatif ;
- une Opportunity ouverte, perdue ou annulée ;
- une quote seule ;
- un Deal Produit autonome sans Client ;
- une donnée UAT, fictive ou de démonstration dans le profil réel.

Les Opportunities perdues et RFQ sans suite restent utiles pour l'activité commerciale
et les motifs de non-aboutissement. Ils ne prouvent pas une habitude de trading.

### 7.3. Gestion des données fictives

La base actuelle étant fictive, le mode de développement peut afficher les calculs avec
un bandeau **Données de démonstration — exclues du profil réel**. En mode réel, ces
données sont exclues par défaut et ne se mélangent jamais aux données natives ou
importées.

### 7.4. Données anciennes incomplètes

Un champ absent n'est jamais deviné. Un ancien Deal dont le format juridique n'est pas
renseigné contribue aux dimensions connues, mais pas au calcul EMTN/BMTN/OTC. La
couverture de chaque dimension est affichée : par exemple « format connu sur 8 Deals
sur 12 ».

## 8. Dimensions analysées

Le premier périmètre couvre :

- format de transaction : EMTN, BMTN, OTC ou valeur spécifique ;
- famille d'instrument : Note, Swap ou valeur spécifique ;
- famille de payoff et appellation spécifique Client ;
- émetteur ou contrepartie ;
- fournisseur sollicité, meilleur fournisseur et fournisseur retenu ;
- devise ;
- sous-jacent ou univers ;
- maturité ;
- taille de ticket ;
- coupon, protection et barrières lorsque la donnée est disponible ;
- documentation juridique référencée : programme EMTN, ISDA, CSA, FBF ou autre.

Le système n'appelle jamais « Swap » un format juridique. Il peut afficher la
combinaison **OTC / Swap / Autocall / ISDA** sans écraser les quatre dimensions.

## 9. Règles de preuve et de récence

Les seuils du Lot 0 restent les seuls libellés autorisés :

| Nombre de cas comparables | Libellé |
|---:|---|
| 1 | Observation isolée |
| 2 | Répétition observée |
| 3 à 4 | Tendance émergente |
| 5 à 9 | Habitude observée |
| 10 et plus | Habitude bien documentée |

Le volume seul ne suffit pas. Chaque carte d'habitude indique également :

- le numérateur et le dénominateur ;
- le périmètre exact ;
- la période étudiée ;
- la dernière observation ;
- la récence : actuelle, à confirmer ou historique ;
- la part native et importée ;
- le taux de couverture de la dimension ;
- les transactions permettant de vérifier la conclusion.

Une habitude est calculée par dimension et sur des cas réellement comparables. Il
n'existe pas de « score Client » global.

## 10. Préférences déclarées et historisation

L'onglet existant **Préférences** conserve son référentiel dynamique, mais une valeur
active devra désormais porter :

- son périmètre : Client, mandat ou Contact ;
- sa date de déclaration ou de confirmation ;
- le Contact source lorsqu'il est connu ;
- le canal : réunion, téléphone, email, autre ;
- le commercial ayant enregistré l'information ;
- une interaction source facultative ;
- un commentaire ou une reformulation fidèle ;
- son statut : active, remplacée, contestée ou historique.

Une nouvelle déclaration ne réécrit pas l'ancienne. Elle crée une nouvelle version et
clôt la précédente pour la vue courante. Le blob actuel peut rester une projection de
compatibilité, mais il ne constitue plus l'historique d'autorité.

Le commercial peut enregistrer :

- une préférence explicitement déclarée par le client ;
- une confirmation par le client d'une habitude observée ;
- une contradiction exprimée par le client ;
- une simple note commerciale, clairement identifiée comme telle.

Il ne peut pas convertir une déduction Structura en déclaration Client sans renseigner
la source de cette confirmation.

## 11. Analyse des fournisseurs et cas Marex

Cette analyse porte uniquement sur les RFQ comparables ayant produit un Deal.

Pour chaque fournisseur, Structura distingue :

1. sollicité ;
2. a répondu ;
3. a fourni une quote ferme et comparable ;
4. a fourni le meilleur prix selon le sens de la RFQ ;
5. a été retenu ;
6. a finalement été booké.

Le meilleur prix n'est calculé que si la comparaison respecte au minimum :

- le même RFQ et les mêmes termes figés ;
- le même format lorsque celui-ci est matériel ;
- un sens achat ou vente cohérent ;
- une quote valide, exécutable et non remplacée par un last look ;
- une convention directionnelle correcte : moins cher à l'achat, plus riche à la vente.

Le profil montre les faits et non une causalité. Si le fournisseur le mieux placé n'est
pas retenu, un motif peut être documenté : demande Client, documentation, crédit,
concentration, relation commerciale, qualité d'exécution, autre. Ce motif est utile
mais son absence ne doit pas être remplacée par une supposition.

La sélection d'un quote moins bon ne sera pas interdite par le Lot 2. Le système
affichera simplement « motif non documenté » lorsqu'il n'existe pas.

## 12. Restitution dans les écrans existants

### Fiche Client — Aperçu

L'aperçu existant est enrichi avec :

- un sélecteur de périmètre Client / mandat / Contact ;
- les habitudes principales par dimension ;
- leur niveau de preuve, leur récence et leur couverture ;
- un accès aux Deals constituant la preuve ;
- les divergences entre déclaré et observé ;
- les comportements de sélection des fournisseurs ;
- les questions de revalidation suggérées.

Exemple de question suggérée : « Marex a été meilleur sur les 3 derniers RFQ traités
mais n'a pas été retenu. Souhaitez-vous revalider ce point avec le Client ? »

### Fiche Client — Préférences

L'onglet existant est divisé visuellement en :

- état courant déclaré ;
- préférences par mandat ou Contact ;
- historique des confirmations et contradictions ;
- références opérationnelles et juridiques, clairement séparées.

### Bloc Mandats existant

Chaque mandat affiche un résumé compact de ses habitudes et permet de sélectionner ce
périmètre dans l'aperçu Client. Aucun écran Mandat autonome n'est créé.

### RFQ existant

Lorsqu'un Client et un mandat sont rattachés, un panneau contextuel compact peut
afficher les habitudes pertinentes et leurs preuves. Ce panneau :

- reste informatif ;
- ne masque aucun fournisseur ;
- ne change pas automatiquement le quote retenu ;
- ne bloque aucune action ;
- n'existe pas dans le parcours Produit autonome.

### Deal existant

Le Deal reste l'objet de preuve. Le Lot 2 ne crée pas de saisie parallèle au booking.
La fiche Deal permet seulement de revenir au contexte et au snapshot ayant alimenté
l'analyse.

## 13. Exigences techniques

Le futur codage devra respecter les points suivants :

1. Normaliser une observation transactionnelle commune aux Deals et historiques
   importés, avec Client, mandat, affiliation, format, instrument, payoff, fournisseur,
   dates, devise, notionnel et provenance.
2. Étendre l'import historique avec des colonnes facultatives de mandat, format,
   instrument, payoff et documentation, sans inventer les valeurs absentes.
3. Déterminer explicitement l'éligibilité analytique et exclure les lots UAT et données
   de démonstration du profil réel.
4. Calculer les habitudes à une date d'observation donnée afin qu'une recette soit
   reproductible.
5. Figer au booking une photographie RFQ suffisante pour expliquer la sélection des
   fournisseurs, y compris les réponses finales pertinentes.
6. Conserver l'historique des déclarations dans des enregistrements append-only et
   utiliser le profil actuel comme projection de lecture.
7. Ne persister aucun score opaque. Toute agrégation doit pouvoir être recalculée à
   partir des faits.
8. Empêcher tout accès cross-entité aux habitudes, preuves et déclarations.
9. Charger les profils Client et mandat avec un nombre de requêtes borné, sans requête
   supplémentaire par mandat, Contact ou transaction.
10. Maintenir la compatibilité des routes et données actuelles pendant la migration.
11. Conserver les snapshots initiaux après une correction d'attribution ; la vue
    courante peut utiliser l'attribution approuvée sans réécrire l'histoire du booking.

## 14. Ce qui est explicitement hors Lot 2

- recommandation automatique de produit ;
- « next best product » ou probabilité de succès ;
- classement automatique des fournisseurs ;
- blocage d'un fournisseur ou d'une structure au titre d'une habitude ;
- suitability, appropriateness ou contrôle réglementaire complet ;
- stockage des contrats et documents juridiques ;
- récupération de données externes ;
- campagne commerciale, emailing ou automatisation CRM ;
- machine learning ;
- dashboard de management global multi-Clients.

Ces sujets éventuels doivent partir d'une mémoire fiable. Les traiter dans le Lot 2
masquerait les problèmes de qualité des faits sous une couche de sophistication.

## 15. Séquence proposée de réalisation

### Étape 2.1 — Fiabiliser la matière analytique

- normaliser les Deals et historiques importés ;
- intégrer mandat, format, instrument, payoff et provenance ;
- exclure explicitement les données fictives du profil réel ;
- mesurer la couverture des données anciennes.

### Étape 2.2 — Calculer par périmètre

- Client, mandat, Contact et non attribué ;
- mêmes seuils de preuve et de récence ;
- absence d'agrégation silencieuse entre mandats divergents ;
- drill-down jusqu'aux transactions sources.

### Étape 2.3 — Historiser le déclaré

- source, date, canal, Contact et auteur ;
- confirmation, contradiction, remplacement et statut ;
- migration de l'état courant sans fabriquer de date historique.

### Étape 2.4 — Expliquer la sélection des fournisseurs

- cas RFQ traités seulement ;
- comparabilité, meilleur prix, retenu et booké ;
- dernier comportement et évolution ;
- motif documenté ou explicitement inconnu.

### Étape 2.5 — Enrichir les composants existants

- aperçu Client ;
- onglet Préférences ;
- bloc Mandats ;
- panneau contextuel RFQ ;
- aucun nouveau parcours concurrent.

### Étape 2.6 — Recette et non-régression

- tests métier déterministes ;
- tests d'isolation par entité ;
- tests de performance et de requêtes ;
- parcours réel enrichi et parcours Produit autonome ;
- démonstration séparée avec données fictives identifiées.

## 16. Critères de recette métier

Le Lot 2 sera accepté si Structura représente correctement les scénarios suivants :

1. un Client avec deux mandats ayant des habitudes opposées ;
2. une préférence générale Client et une préférence spécifique de mandat ;
3. une préférence propre à un Contact qui ne contamine pas la maison ;
4. une déclaration récente contredisant un historique ancien ;
5. une habitude EMTN distincte d'un instrument Note ;
6. un Swap correctement présenté comme instrument dans une enveloppe OTC ;
7. un payoff spécifique Client conservant sa famille standard ;
8. Marex meilleur sur plusieurs RFQ exécutés mais jamais retenu ;
9. Marex finalement retenu sans disparition de l'ancien comportement ;
10. un motif Client documenté et un autre cas dont le motif reste inconnu ;
11. un RFQ sans Deal visible dans l'historique mais absent des habitudes ;
12. un Deal autonome sans Client qui continue à fonctionner et n'alimente aucun profil ;
13. des données fictives visibles en démonstration mais exclues du profil réel ;
14. un historique importé incomplet dont les champs manquants ne sont pas devinés ;
15. une correction approuvée d'attribution sans réécriture du snapshot initial ;
16. une conclusion dont tous les Deals sources sont consultables ;
17. un utilisateur incapable de lire les habitudes d'une autre entité ;
18. aucun N+1 lors du chargement d'un Client comprenant plusieurs mandats et Contacts.

## 17. Décisions proposées pour validation

1. Le Lot 2 porte bien sur les habitudes de trading et la sélection des fournisseurs.
2. Toutes les habitudes sont informatives et non bloquantes.
3. Les seuils et règles de récence du Lot 0 sont conservés sans score supplémentaire.
4. Les préférences déclarées deviennent datées, sourcées et historisées.
5. Le niveau mandat est prioritaire pour la lecture opérationnelle, sans effacer le
   niveau Client.
6. L'absence de motif lorsqu'un meilleur quote n'est pas retenu reste affichée comme
   inconnue ; elle n'est jamais complétée automatiquement.
7. Les données fictives restent utilisables en démonstration mais sont exclues de tout
   profil réel.
8. Aucun nouvel écran principal n'est créé : les composants Client, Mandat, RFQ et Deal
   existants sont enrichis.
9. Le parcours Produit sans notion commerciale reste strictement inchangé.

Après validation de ces neuf décisions, le codage peut commencer par l'étape 2.1.

## 18. État d'implémentation au 3 septembre 2026

Le Lot 2 est implémenté dans les composants et parcours existants :

- les faits Deal et historique importé portent désormais le mandat, le format de
  transaction, l'instrument, le payoff et la référence documentaire ;
- le profil réel exclut les Deals UAT et données de démonstration, tandis qu'un
  Client explicitement fictif reste utilisable pour la démonstration ;
- les habitudes sont rendues par dimension avec dénominateur, part, niveau de
  preuve, récence, origine et transactions sources ;
- la vue Client peut être restreinte à un mandat ou à une affiliation, et signale
  les divergences dominantes entre mandats au lieu de les moyenner ;
- les préférences Client, mandat et Contact sont enregistrées dans un journal
  append-only avec nature, date, source, canal, note et auteur ;
- le profil courant reste une projection compatible avec l'ancien formulaire et
  les valeurs antérieures à ce lot sont conservées comme états non datés ;
- les écritures Client et les écritures mandat/Contact disposent d'un verrou de
  concurrence afin qu'une seconde session ne puisse pas écraser la première ;
- le booking fige toutes les réponses finales du RFQ, leur comparabilité et le
  motif facultatif de sélection ;
- une cotation expirée, déclinée ou remplacée ne peut plus être retenue ni devenir
  artificiellement la meilleure réponse affichée ;
- l'analyse « meilleur prix non retenu » ne porte que sur les RFQ exécutées et
  produit une question de revalidation après répétition, jamais une exclusion ;
- l'import JSON/Excel accepte les mandats et dimensions juridiques sans inventer
  les données manquantes ;
- un Deal ou un RFQ Produit autonome conserve exactement son fonctionnement :
  tous les rattachements commerciaux restent facultatifs.

### Recette automatisée

- 210 tests backend ciblés Clients, migrations et RFQ : réussis ;
- 64 tests frontend : réussis ;
- compilation Python : réussie ;
- build de production Vue/Vite : réussi.

### Recette fonctionnelle sur l'instance locale

La recette de bout en bout a été exécutée sur les données explicitement fictives :

- une référence juridique datée et sourcée a été ajoutée au profil Client, puis
  retrouvée dans le journal append-only et exclue d'une projection antérieure à sa
  date de déclaration ;
- le profil propre au Contact Pierre Girard a reçu le format OTC et l'instrument
  Swap sans contamination du profil Client ;
- la provenance de saisie est réinitialisée après enregistrement et changement de
  portée afin d'éviter de réutiliser accidentellement une ancienne source ;
- le RFQ `RFQ-20260903-001` a comparé Marex à 97 et BNP Paribas à 98 dans le sens
  achat : Marex est correctement identifié comme meilleur prix ;
- BNP Paribas a été retenue avec le motif documenté « Demande du Client », sans
  transformer Marex en exclusion ;
- le Deal `DEMO-20260903-001` a figé les deux réponses, leur comparabilité, le choix,
  le motif, le mandat et les dimensions OTC / Swap / Autocall ;
- au retour du Pricer, le RFQ relit son état booké, masque toute seconde action de
  booking et rend le motif figé visible en lecture seule ;
- la fiche Bank Helvetia restitue le comportement sur le mandat concerné et présente
  Marex comme une observation isolée de « meilleur non retenu », sans causalité
  inventée ;
- un RFQ Produit autonome déjà booké reste lisible sans Client, mandat ni Contact.

Deux défauts de restitution découverts pendant cette recette ont été corrigés dans
les composants existants : conservation involontaire de la provenance entre deux
portées, et détail RFQ périmé au retour du Pricer. Aucune nouvelle route d'écran n'a
été introduite.
