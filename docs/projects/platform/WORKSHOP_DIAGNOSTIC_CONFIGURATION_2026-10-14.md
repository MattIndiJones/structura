# Paramétrage des campagnes de diagnostic — 14 octobre 2026

## Correctif de création — 14 octobre 2026

Le premier lancement par la page était bloqué avant même la création du brouillon :
le minimum `0.000001` et le pas `0.25` de l'éditeur de courbes rendaient les
maturités préremplies 1/3/5 ans invalides pour le navigateur. Les maturités continues
acceptent désormais un pas libre, avec les mêmes bornes positives ; les courbes
annuelles conservent des années entières à partir de 1. Les contrôles métier de
cohérence, d'ordre et de funding sont conservés.

La page affiche les erreurs de validation à côté de la commande, ouvre l'onglet
concerné et place le focus sur le champ invalide, y compris dans une courbe repliée.
La recette visuelle a vérifié les 30 champs préremplis, puis le refus d'une maturité
de 31 ans avec message visible et retour automatique à « Funding et marges ».
Après restitution de 5 ans, le scénario prévu a été enregistré depuis la page :
brouillon `0280f37ec90643628b9a14780614d323`, quatre RFQ, huit cotations prévues,
Phoenix à 2 % par trimestre et destinataires conservés. Aucun agent lancé,
aucun appel IA ni écriture transactionnelle de campagne.

`npm run build` réussi : 437 tests frontend, puis compilation de production.
Aucun test backend exécuté pour ce correctif d'interface. Les preuves sont dans
`.runtime/diagnostic-acceptance/funding-fix-2026-10-14/` ; le lancement de la
campagne et ses parcours métier restent à qualifier.

## Livraison locale

La page existante **Admin → Simulation** prépare les scénarios version 2. La
configuration occupe toute la largeur de la zone principale. Cinq onglets
regroupent participants/produits, calendrier RFQ, funding/marges, risque/couverture
et exécution/coût. Le contenu défile à l’intérieur ; estimation et commande de
création restent dans la fenêtre. Les valeurs monétaires utilisent les séparateurs
français. Le suivi conserve ses commandes, journaux, books, problèmes et exports.

**Créer** enregistre un brouillon, même sans fournisseur IA disponible.
**Démarrer les IA** lance la campagne explicitement, avec les paramètres figés.
Modifier un brouillon utilise `PATCH /api/agent-workshop/{id}/configuration`.
Les données historiques restent consultables ; rejouer un scénario ancien crée
une configuration version 2 explicitement convertie, sans réécrire son historique.

Le backend doit être redémarré après cette livraison pour charger les nouvelles
routes. Un rafraîchissement du navigateur charge le frontend reconstruit.
Aucun commit, push, merge ou lancement payant n’a été effectué pour cette recette.

## Réglages préremplis

| Paramètre | Valeur |
|---|---|
| Suivi minimal | 60 mois ; prolongation jusqu’au dernier paiement contractuel |
| Demandeurs | Leonteq et Kepler Cheuvreux Solutions |
| Répondants / émetteurs | BNP Paribas, Société Générale, Citi |
| UBS | Disponible, inactive par défaut |
| Produits | Reverse Convertible 12 mois, Phoenix 36 mois, Athena classique 60 mois |
| RFQ | Une au mois 1, une au mois 2, deux au mois 3, puis zéro |
| Marché | Synthétique commun, explicitement identifié ; aucun re-fetch externe |
| Modèle de pricing | Constant ; mêmes hypothèses de marché entre émetteurs |
| Funding | Piliers 1/3/5 ans, trajectoires propres aux trois émetteurs |
| Marges cibles | BNP 35 bps, SG 45 bps, Citi 25 bps du nominal |
| Surveillance | Mensuelle, configurable tous les 15 jours |
| MtM | Trimestriel ; événements contractuels activables |
| IA | OpenAI GPT-6 Luna, clé Structura existante ; modèle modifiable avant départ |
| Plafond API | 2 USD ; 1 000 appels maximum |
| Durée réelle | 60 minutes maximum, cumul des sessions |

Les six organisations gardent des rôles indépendants d’activation, demande,
réponse et émission. Une organisation peut demander et répondre à des dossiers
différents ; elle ne répond pas à sa propre demande. Les destinataires et le payoff
peuvent être définis pour chaque RFQ, ou répartis automatiquement. Les comptes
clients fictifs et la supervision sont distincts des organisations commerciales.

Le nominal, la maturité, les coupons, barrières et sous-jacents sont propres à
chaque famille. Les coupons sont les paramètres effectivement consommés par le
script du catalogue ; la recette ne résout pas automatiquement un coupon au pair.

## Isolation et référentiel

Les campagnes utilisent leurs propres services, bases, dates économiques,
marchés synthétiques et secrets de signature. Les installations d’essai manuel
et la base principale ne servent jamais de fixtures.

Un socle privé conserve comptes, entités, desks, contreparties et accords avant
création du CRM et des transactions. Les campagnes suivantes restaurent ce socle
dans leurs bases vierges. Le premier scénario prépare les références manquantes
par les API d’administration ; les références déjà présentes sont réutilisées.
Les clés JWT, canaux RFQ et commandes de contrôle ne sont pas copiés entre
installations. Un compte désactivé n’est pas réactivé lors d’une reprise.

L’inscription par écran ne fait plus partie du parcours. La connexion technique
utilise l’identité préparée et garde une session propre à chaque navigateur.
L’accès de supervision est réservé à l’admin de simulation. Un répondant reçoit
ses seuls prix ; les hypothèses privées et marges ne sont pas exportées dans les
termes Product échangés. Les preuves détaillées de simulation sont conservées
localement jusqu’à une suppression explicite par l’admin ; les anciens essais
et les sauvegardes restent disponibles, sans purge automatique implicite.

## Orchestration, économie et calculs

Chaque demande possède un identifiant distinct. Les mois vides avancent sans
appel IA et plusieurs besoins restent indépendants. Les anniversaires mensuels
sont distingués des constatations intermédiaires : un événement avant le début
d’un mois n’ouvre pas prématurément les RFQ du mois suivant.

Les agents décident seulement sur des tâches commerciales prêtes : envoyer,
coter/refuser, comparer, proposer, accepter, confirmer et booker. La préparation,
les règlements fictifs, les constatations et le suivi quantitatif sont pilotés
de façon déterministe. Aucun commentaire IA de risque n’est demandé.

Le funding est interpolé entre dates et piliers, contrôlé par bornes et variation
maximale. Il intervient en actualisation, sans modifier le drift des sous-jacents.
La politique et la marge effectivement choisie restent privées et datées. Les
MtM utilisent la courbe de l’émetteur à la date économique du calcul, avec une
référence de provenance ; le snapshot de booking reste intact. Sans override,
le comportement historique du moteur MtM est conservé.

Le monitoring de concentration ne déclenche pas de repricing quotidien. Les
rapports indiquent si un nouveau MtM existe. Les contrôles natifs de relation et
de limite continuent de s’appliquer au booking. Les notes restent hors netting
OTC : le test CCR porte sur un call OTC hypothétique déclaré, sous un accord
ISDA/CSA configuré, sans transformer les notes en transactions OTC.

AMC, FIFO, inscription et double validation sont hors couverture. La validation
native du contenu avant publication, la confirmation avant booking et les
contrôles de validité/doublons restent actifs. La seconde validation demeure
configurable dans Structura ; ce scénario ne prétend pas la tester.

## Prévisualisation et consommation

`POST /api/agent-workshop/preview` valide et estime sans appel de modèle, pricing,
création de service ou écriture métier. Le frontend recalcule après modification
et écarte les réponses correspondant à une ancienne configuration.

L’estimation présente RFQ, cotations, pricings initiaux, borne haute de MtM,
rapports quantitatifs, recettes complémentaires, appels IA et coût bas/central/haut.
Les calculs internes d’un solveur ne constituent pas chacun un appel IA. Les
estimations reposent sur le catalogue de tarifs local daté, les mesures des
pilotes et des hypothèses explicites, avec provision pour reprises et supervision.
La durée reste indicative, dépendante de la machine, du fournisseur et des payoffs.

L’estimation de départ est conservée avec son empreinte. La consommation déclarée
en tokens, le coût calculé au tarif enregistré et l’écart au scénario sont suivis.
Les réponses sans usage retourné et les requêtes interrompues sont signalées
comme coûts inconnus. Ce compteur ne remplace pas la facture du fournisseur.
Aucune facturation des clients Structura n’est activée.

## Preuves, arrêt et reprise

Les tâches terminées/restantes et la tâche courante sont sauvegardées. Avant
reprise, les exécutions, cotations publiées et traitements sont relus dans leurs
installations natives. Les objets déjà écrits sont rapprochés ; les publications
et confirmations récupérables ne sont pas rejouées comme de nouvelles décisions.
Une ambiguïté, une preuve client absente ou des termes changés suspendent la reprise.

Chaque session conserve le HEAD Git, la branche et les empreintes du code exécuté,
y compris les modifications locales. Un changement de source pendant la session
interrompt la progression. Un blocage métier ou une corruption des termes arrête
la campagne avec acteur, module, date, attendu, observé et preuve reproductible.
Les anomalies complémentaires non bloquantes sont conservées puis la campagne
poursuit ses autres tâches. Budget, fournisseur IA et arrêt utilisateur ont des
motifs distincts d’un bug Structura.

Aucune correction automatique pendant l’exécution. Un blocage doit être qualifié
et clôturé après correction et vérification sur une copie avant reprise. L’arrêt
empêche la prochaine requête métier et ferme uniquement les processus détenus
par le contrôleur, avec ses identités privées de contrôle.

## Vérifications obtenues et limites

- **84 tests backend ciblés** : configuration, isolation du référentiel, funding,
  calendrier vide/multiple, rôles, confidentialité, estimation gratuite, gel des
  paramètres, reprise native, annulation et qualification des blocages.
- **437 tests frontend et build de production** réussis. Avertissement Vite
  préexistant sur l’import du store Pricing ; aucun échec de build.
- Recette HTTP native isolée, sans IA : RC demandé par Leonteq, Phoenix et Athena
  demandés par Kepler ; trois cotations par RFQ et quatre écritures rapprochées
  par dossier. La reprise réutilise les dossiers complets sans nouveau booking.
- Une copie a exercé les recettes complémentaires et deux arrêtés trimestriels
  (quatre MtM sur les deux écritures du demandeur). CCR calculé sur le call
  hypothétique ; KID/EMT, archive KID, note Valo Explain avec deux runs existants,
  scan de réinvestissement et recherche Optimizer à un candidat ont abouti.
- Contrôles visuels des routes existantes et de la configuration pleine largeur :
  1 392 px sur une fenêtre de 1 440 px, estimation modifiée de 3 à 8 RFQ,
  commande visible dans une fenêtre de 900 × 780 px. L’estimation et la création
  ne démarrent aucun agent.
- Tous les services de recette détenus sont fermés. Les rapports restent dans
  `.runtime/diagnostic-acceptance/`, exclu de Git.

Preuves locales : recette RFQ
`08efadbc997a421a9eb9648561f3dccf/86a93952669a46a7babee0a8007e4ea7`,
recettes complémentaires réussies sur copie
`2bdd94f97c30402f8f5e748f846c811a/86a93952669a46a7babee0a8007e4ea7`.
Les premiers rapports conservent aussi les erreurs de préparation corrigées après
arrêt : paramètre Phoenix transmis à Athena, lecture UTF-8, conventions Optimizer,
qualification action/indice et dates du call CCR.

La campagne complète de cinq ans avec décisions IA reste à lancer explicitement
depuis la page paramétrée. La recette courte ne valide pas encore tous les coupons,
rappels et paiements finaux sur cinq ans, ni tous les cas de refus juridique,
révision/retrait/expiration de cotation ou interruptions de transport. Les contrôles
natifs correspondants sont préservés ; les branches non exercées ne sont pas
déclarées validées. La matrice **Scénario exercé** décrit une preuve représentative,
pas une certification exhaustive du module ou du moteur quantitatif. La qualité
des sensibilités, la résolution au pair et l’ergonomie détaillée restent à qualifier
humainement sur les preuves et les campagnes suivantes.
