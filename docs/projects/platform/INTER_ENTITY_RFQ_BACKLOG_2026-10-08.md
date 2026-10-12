# Flux RFQ entre entités Structura — chantier différé

Date : 08/10/2026. Statut : besoin exprimé, développement différé.

Cette note conserve le futur besoin d'échange entre entités. Elle ne décrit
aucune fonctionnalité livrée. Le laboratoire précédent a été retiré ; les
spécifications de la nouvelle simulation sont développées dans le
[plan d'action multi-Structura](MULTI_STRUCTURA_AGENT_ACTION_PLAN_2026-10-08.md).

## Contexte de la nouvelle simulation

Chaque agent IA utilise son propre environnement Structura : compte, identité
juridique, droits, référentiels, contrats et book. Hector représente une maison
d'émission et de distribution ; BNP, Crédit Agricole et Société Générale sont
des banques simulées indépendantes. Achille supervise la recette et aide à
identifier les défauts de Structura.

Philippe retient une utilisation des écrans et des API. Les commandes API doivent
respecter les mêmes habilitations et contrôles métier que les parcours d'écran.
L'isolation physique des instances, bases, sessions et données reste à spécifier.
L'environnement d'une banque n'accède pas au book ou aux marges internes d'Hector.

Les agents décident et agissent dans Structura. Le dispositif de simulation
organise le temps, les échanges et la collecte de preuves ; il ne remplit pas
les books à leur place pour fabriquer une réussite.

## Besoin différé : échanges RFQ natifs entre entités

Parcours cible :

1. Hector prépare une demande de prix dans son Structura : produit, version des
   termes, sens, notionnel, devise, calendrier, modalités et délai de réponse.
2. Il adresse l'AO aux banques choisies et éligibles pour cette demande.
3. Chaque banque reçoit la demande dans son propre Structura et prend en charge
   son dossier local, sans ressaisie silencieuse ou changement des termes.
4. La banque utilise son Pricer, ses hypothèses et ses conventions pour calculer
   le prix. Elle choisit sa marge et peut répondre, demander une précision ou
   décliner. Le prix calculé et le prix proposé restent distincts et traçables.
5. La réponse revient dans le Structura d'Hector : prix, convention de cotation,
   sens, devise, montant, validité, caractère indicatif ou ferme et conditions.
6. Hector peut négocier, demander une mise à jour, sélectionner une réponse ou
   arrêter l'AO. Une réponse plus chère peut être retenue avec justification.
7. L'accord commercial donne lieu aux confirmations et aux bookings de chaque
   partie, suivis d'un rapprochement entre leurs enregistrements.

Chaque banque conserve ses calculs et sa marge privée. La messagerie transporte
uniquement les informations qu'elle décide ou doit communiquer. Une banque
n'est pas obligée de coter ni de gagner un AO.

Les objets locaux des deux Structura portent une référence d'échange commune
et la version des termes communiqués. Le flux devra gérer négociations,
expiration, retrait, doublons, indisponibilité d'un destinataire, confirmation
contestée et booking présent d'un seul côté. Un message accepté ne suffit pas à
prouver que les deux books ont été enregistrés.

## Étape intermédiaire : échanges au format mail

Avant le flux natif, prévoir pour la recette une messagerie isolée au format
mail, avec une boîte par agent, fils de conversation et pièces jointes de test.
La solution de transport reste à choisir. Cette note n'autorise pas l'envoi de
messages à des banques réelles.

Les agents pourront lire les demandes, utiliser leur Structura, transmettre les
prix et traiter les réponses reçues. Un message devra référencer le dossier,
les termes proposés et la cotation. Toute ambiguïté sur le prix, le sens ou la
version du produit devra provoquer une clarification explicite.

Le contenu du message et son rapprochement avec les objets réellement créés
serviront de preuves de recette. Une déclaration « booké » dans un mail ne
remplacera pas la présence d'un deal dans le book concerné.

## Bookings et lecture du risque

Dans le cas d'une note BNP achetée puis revendue par Hector :

- BNP enregistre sa vente à Hector dans son book ; Hector enregistre son achat
  à BNP. Ce sont deux représentations locales d'une même transaction.
- Hector enregistre sa vente au client : il s'agit d'une seconde transaction.
- Le rapprochement vérifie instrument et émetteur, termes, quantités, prix,
  devises, dates et flux opposés entre les deux parties de chaque transaction.
- Après revente et règlement complets, le porteur final de la note BNP porte le
  risque de défaut de BNP. La vente seule ne crée pas une exposition de crédit
  bilatérale permanente entre BNP et Hector.
- Les risques avant règlement, les créances impayées ou un financement éventuel
  sont à traiter séparément selon les modalités effectives.

Si Hector émet sa propre note et achète une couverture OTC à BNP, la note et la
couverture sont des instruments distincts. Le client porte le risque émetteur
d'Hector ; le risque du dérivé BNP–Hector dépend des engagements, du MtM, du
netting et du collatéral applicables. Les valeurs calculées indépendamment par
les deux parties peuvent différer ; les écarts doivent être expliqués.

Une note ne devient pas un dérivé OTC parce que les deux parties ont un ISDA ou
un CSA. La documentation requise est déterminée par l'instrument et la relation.

Références : [SEC — risque émetteur des notes structurées](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-76),
[ISDA — pratiques opérationnelles de collatéral](https://www.isda.org/collateral-management-sop/),
[BIS — règlement livraison contre paiement](https://www.bis.org/publications/delivery-versus-payment-securities-settlement-systems).
Voir aussi le [cadrage notes et OTC de Structura](../pricing/SA_CCR_PORTEFEUILLE_MIXTE_ROADMAP_2026-09-29.md).

## Objectifs des agents et scénarios contractuels

Objectifs proposés par Philippe : Hector vise au moins 100 M€ de produits
structurés traités sur l'année ; BNP vise 15 % de part de marché, Crédit Agricole
30 % et Société Générale 40 %. Ces cibles guident les décisions ; elles ne
conditionnent ni la poursuite ni la réussite technique de la campagne.

Définition proposée, à préciser : volume d'Hector = notionnel des ventes
exécutées aux clients finaux, compté une seule fois ; part d'une banque =
notionnel externe exécuté avec cette banque / notionnel externe exécuté avec
toutes les banques. Les émissions propres et couvertures devront être présentées
séparément. Un dénominateur nul donne une part non calculable. Les objectifs
totalisent 85 % et ne constituent pas une allocation obligatoire du marché.

Prévoir des jeux distincts : relation BNP–Hector complète ; relation Crédit
Agricole–Hector incomplète ; puis variations sur CSA, limites, dates, périmètres,
netting et règlements. L'absence d'un CSA n'est pas automatiquement un défaut :
le scénario précise s'il est requis ou si le traitement non collatéralisé est
autorisé. Une graine de tirage permet la reproductibilité ; une matrice impose
les cas à couvrir, même si les objectifs commerciaux ne sont pas atteints.

Un refus métier attendu concerne une action ou une relation ; les autres
agents peuvent continuer. Les contrôles applicables ne sont pas désactivés
pour atteindre les objectifs. Les scénarios de refus font partie de la recette.

## Preuves attendues et prochaines spécifications

Chaque étape devra préciser acteur, action écran/API, préconditions, contrat
applicable, résultats persistés, message envoyé et contrôle indépendant. Les
bugs, mauvais usages, fonctions absentes et suggestions sont distingués.
Achille conserve le premier échec lorsqu'il propose une correction d'usage.

Restent à définir : provisionnement et onboarding des environnements, modalités
de messagerie, périmètre des premiers produits, matrice contractuelle, critères
de rapprochement, objectifs détaillés, horloge commune suspendue pendant les
traitements, coûts et délais IA, puis interface pédagogique de supervision.
La durée d'un an en une à deux heures reste une cible à mesurer sur un volume
défini. Aucun nouveau développement n'est engagé par cette note.
