# Product Optimizer — marché automatique et recherche complète, 08/10/2026

État : **implémenté localement ; tests ciblés, build et recette API réussis**.
Aucun commit ni push. Suite du lot participation / cap / gear put. Priorité
confirmée : Optimizer ; smile urgent mais différé, Copilot et conservation des
recherches dans un second temps.

## Problème traité

### Ajustement d’affichage demandé par Philippe — 08/10/2026

Le sélecteur de famille et celui du modèle occupent chacun une ligne entière.
Les libellés des axes de recherche sont au-dessus des cases : mode, minimum,
maximum et pas restent alignés. Les panneaux passent à deux colonnes entre
768 et 1 199 px, puis à une colonne en dessous ; la hauteur suit leur contenu.

Les hypothèses de volatilité et dividendes chargées ou rétablies depuis le marché
sont arrondies à deux décimales **en pourcentage** avant envoi au moteur.
Les corrélations sont arrondies à deux décimales dans leur unité native.
Les champs décimaux du marché, des coûts, de résolution et des contraintes
affichent deux décimales avec un pas de 0,01 et arrondissent une saisie plus
précise. Les champs entiers restent entiers. Les références sources conservent
leur précision dans le snapshot et l’export ; le libellé indique leur utilisation
arrondie. Les surcharges volontaires et données absentes restent distinctes.

L’exemple BNP de la capture utilise donc 28,54 % de volatilité et 6,46 % de
dividendes. Le chargement et le retour à la référence n’introduisent plus la
discordance entre la précision de la valeur et le pas HTML qui bloquait l’envoi.

Validation : `npm run build`, **325 tests frontend réussis**, build réussi.
Les contrôles couvrent l’envoi des hypothèses arrondies, le rétablissement de
référence, la conservation de sa précision source, les attributs numériques et
la saisie (valeur intermédiaire, arrondi, zéro et champ vide). La recette visuelle
n’a pas pu être effectuée : le navigateur intégré refuse l’URL locale avec
`ERR_BLOCKED_BY_CLIENT`. L’instance backend préexistante n’a pas été modifiée.

### Résultats calculés visibles même hors conditions — 08/10/2026

Retour de Philippe : trois structures pricées mais rejetées pour incertitude
Monte-Carlo donnaient seulement « Aucune structure confirmée », sans prix visible
ni indication opérationnelle de ce qu’il faut revoir.

Le résultat affiche désormais les structures `PRICED` avec juste valeur finie,
classées selon l’objectif métier, indépendamment de leur admission. Dix sont
affichées par défaut, avec choix de 25 ou de toutes, tri par proximité du prix
cible ou probabilité de perte Q. Les coupons, participations, caps et objectifs
de protection suivent le mode du payoff ; aucun score ne mélange des années,
des probabilités et des paramètres contractuels.

- Fond vert : contraintes respectées et validation indépendante `PASSED`.
- Fond rouge : hors conditions, incertitude non concluante ou erreur de validation.
- Fond ambre : exploration admissible mais validation manquante.

Chaque prix affiche paramètres, métriques Q, intervalle IC95, écart au budget
payoff net et diagnostics. Ceux-ci utilisent les chiffres et limites du résultat
figé : intervalle trop large avec prix central conforme, prix central hors cible,
limites de risque, coupon cible, incompatibilité N/2N ou erreur technique. Ils
indiquent le réglage à examiner et, lorsqu’il est calculable, la tolérance qui
couvrirait l’intervalle actuel ou la limite qui respecterait la borne mesurée.
Ces seuils sont indicatifs et ne modifient aucune contrainte ; davantage de
simulations n’est pas présenté comme une garantie de validation.

La comparaison accepte les structures rouges avec leur statut et leur couleur.
Lorsqu’aucun résultat n’est confirmé, les deux meilleurs prix sont présélectionnés
pour comparaison. Recommandation et frontière restent limitées aux résultats
confirmés. Les erreurs et structures non pricées sont visibles séparément : les
prix aux bornes de résolution, s’ils existent, ne deviennent pas un prix résolu.
Le message de validation « terminée » sur zéro candidat sélectionné est retiré.

Validation : **337 tests frontend réussis**, `npm run build` réussi. Cas de trois
prix rejetés / zéro confirmé, rendu des couleurs, classement des objectifs,
diagnostics chiffrés, comparaison et exclusion stricte des recommandations
couverts. Aucun moteur, prix, critère d’admission ni calcul backend modifié.
Pas de nouvelle recette visuelle : l’accès local du navigateur intégré reste
bloqué, comme indiqué au correctif précédent.

### Livraison initiale

La reprise du Pricer dépendait de sa session et échouait sur ses tickers vides ou
dupliqués, même avec un titre correctement choisi dans l’Optimizer. STMicro
pouvait être affiché comme indice, avec les valeurs génériques 20 % / 2 %.
La grille Phoenix de la capture produisait 135 structures, bloquées par un plafond
de 32 et par un plafond de travail indépendant de la mémoire nécessaire.

## Marché et dates

Le bouton de copie du Pricer disparaît du parcours principal. La sélection du
panier, de la devise ou de la **date de pricing** charge automatiquement les
références via `POST /api/product-optimizer/market-reference`, sans lire la session
Pricer. Le catalogue existant fournit identité, devise et classification.

La colonne additive `underlyings.asset_class` distingue action, indice et inconnu.
La migration est idempotente. Les identités connues du seed sont qualifiées par
leurs groupes explicites, sans règle basée sur le préfixe du ticker : CSI 300
reste un indice bien que son symbole ne commence pas par `^`. Les classifications
manuelles existantes sont conservées. L’administration permet de qualifier les
titres ; un type connu est verrouillé dans l’Optimizer et contrôlé côté API.
Un titre inconnu demande une qualification explicite, sans repli implicite sur indice.

La base ne contient pas de cotations implicites par titre. Le service réutilise
les services historiques existants et leurs caches ; les références du panier
daté sont gardées cinq minutes en mémoire, avec au plus 128 clés. Les appels
volatilité / dividendes sont parallélisés dans trois threads au maximum.

| Champ | Référence automatique | Valeur de pricing |
|---|---|---|
| Volatilité | Réalisée annualisée, clôtures ajustées, au plus 252 rendements communs | Hypothèse de sigma GBM, modifiable ; aucune qualification implicite |
| Dividende | `dividend_profile(ticker, asof)`, dividendes détachés sur un an / clôture nue finale | Hypothèse de rendement forward, modifiable ; divergence ajusté/nu signalée |
| Corrélation | Rendements ajustés communs du panier daté | Matrice utilisée, modifiable ; aucune réparation implicite |
| Taux, courbes, funding | Saisie explicite | Hypothèses manuelles ; funding en actualisation seule |

La date effective de la dernière observation, le fournisseur, la fenêtre,
le nombre d’observations et la date de récupération sont conservés quand
disponibles. Les observations futures sont exclues. Une donnée absente reste
vide et bloque le lancement jusqu’à saisie manuelle ; elle ne devient ni zéro
ni un défaut de 20 % / 2 %. Une erreur du flux dividendes devient une absence
de donnée, distincte d’une série réellement vide sans dividende.

Les surcharges volontaires restent prioritaires lors d’un changement de date.
Changer de titre efface les valeurs du titre précédent. Les réponses arrivées
après un autre choix sont ignorées. Les corrélations et leurs surcharges restent
attachées aux paires de tickers, pas à une position dans le panier. Chaque champ
permet de revenir à sa référence ; rétablir q efface la courbe de dividendes
manuelle pour éviter un premier bucket incompatible.

Le marché envoyé est `AUTO_MARKET`, avec provenance `HISTORICAL_ESTIMATE` ou
`USER_ASSUMPTION`. Référence et valeur utilisée sont conservées dans le snapshot
figé, son empreinte et l’export. Le contrat exige des références complètes, des
tickers, la devise et un timestamp avec fuseau. Cette traçabilité ne certifie
pas une cotation de booking.

**Périmètre des dates : recherche à l’émission.** `pricing_date` est explicite
dans la requête et doit égaler `market.as_of` et `strike_date` ; la valeur reste
à cette même date. L’interface affiche cette convention. Les constatations et
les paiements sont calculés séparément depuis le strike, avec leurs calendriers
et le décalage de règlement. Choisir une date historique charge le marché arrêté
à cette date. Le démarrage différé et la valorisation en cours de vie ne sont
pas ajoutés ici : ils nécessitent de reprendre le traitement forward-start / MtM
du Pricer, et ne sont pas simulés par un simple changement d’étiquette.

## Grille, ressources et arrêt

Chaque axe applicable au script propose **Fixe** ou **À explorer**. Une valeur
fixe devient une plage singleton. Les valeurs effectivement générées et leur
nombre sont affichés ; les champs non applicables au script restent absents.
L’estimation distingue grille brute, exclusions contractuelles et calculs requis.

Le plafond maximal passe à **256 candidats**, également choisi par défaut dans
l’interface. Le budget temps est modifiable entre 30 et 3 600 secondes ;
l’interface propose 1 800 s. Le défaut API reste 120 s pour les anciens appels.
Le volume total estimé devient un avertissement, car les unités de travail ne
prédisent pas le temps mural. Les limites contraignantes sont la taille de grille,
la mémoire d’un calcul individuel et le délai maximal. Aucun échantillonnage de
grille ni réduction de N n’est automatique.

Le calcul direct et les graines restent inchangés. L’exécuteur soumet une fenêtre
bornée au nombre de processus retenus, avec au plus quatre demandés. La mémoire
de travail est provisionnée sur le plus grand calcul à 2N ; elle ne représente
pas la mémoire totale des interpréteurs et de l’application. Pour la capture,
135 Phoenix / un titre / 4 000 paires : **201,6 Mo estimés, deux processus sur
quatre demandés**, fenêtre de deux. Le délai restant d’exploration est estimé
après les premiers calculs ; exclusions préalables et validation sont séparées.
Il reste indicatif, notamment lorsque les maturités changent.

L’arrêt volontaire utilise `POST /api/product-optimizer/cancel/{run_id}`. Le jeton
éphémère appartient à l’utilisateur ; le serveur ne garde que le propriétaire
et un signal d’arrêt, aucune recherche ni résultat persistant. La connexion reste
ouverte jusqu’au résultat partiel. Les workers sont nettoyés avant libération du
créneau ; en séquentiel, le calcul courant doit se terminer.

Un résultat partiel précise `USER_STOP` ou `TIME_BUDGET`, les évaluations terminées,
la couverture manquante et les validations en attente. Les confirmations déjà
terminées restent recommandables et exportables. Un arrêt pendant l’exploration
peut ne conserver aucune recommandation : la validation des cinq premiers se
fait après classement de l’exploration, sans sélection adaptative ni remplissage
après échec. Quitter la page interrompt la connexion, sans sauvegarde de run.

## Motifs d’absence de solution

Les rejets distinguent prix cible hors bornes, résolution numérique non concluante,
contraintes de risque effectivement dépassées, incertitude Monte-Carlo et
incompatibilités contractuelles. Pour un plafond de risque, une estimation centrale
qui respecte la limite mais dont la borne de contrôle la dépasse est identifiée
comme incertitude Monte-Carlo. Les incompatibilités N/2N sont également explicites.

Les candidats proches d’une contrainte sont consultables **non admissibles**, avec
estimation, borne de contrôle, limite et dépassement. Le rapprochement se fait
par métrique ; il ne crée pas de score global mélangeant probabilités et années.
Aucune contrainte ni tolérance n’est assouplie automatiquement.

## Vérifications et limites

Tests backend ciblés du domaine Optimizer, catalogue et dividendes ; montage des
setups Vue avec leurs vrais hooks et watchers, tests de payload / provenance,
champs fixes / explorés, réponses obsolètes et arrêt avec résultat partiel.
**193 tests backend ciblés distincts réussissent**, en plusieurs exécutions et
reprises des cas corrigés ; aucune suite backend complète. Les vérifications
couvrent les huit familles, les processus réels, les dates, les sources manquantes,
la migration additive et la propriété du jeton d’arrêt.
`npm run build` réussit avec **321 tests frontend**.

La recette API de 135 candidats utilise une base en mémoire et des références
**QA synthétiques**, avec le véritable moteur GBM, les processus et les holdouts.
Résultat : **135 / 135 candidats évalués et pricés, aucun échec, aucun non évalué**,
en **1 025,844 s**, soit environ 17 min 06 s sur ce poste. Tous les candidats
étaient admissibles à l’exploration. Les cinq validations indépendantes N/2N ont
été terminées : **un candidat confirmé, quatre rejetés pour incertitude Monte-Carlo**,
à tolérance de prix conservée de ±0,5 point. Aucune borne ni simulation réduite.
Cette durée décrit cette instance de recette, avec une partie des tests ciblés
exécutée simultanément ; elle n’est pas une prévision générale de performance.
Le dossier de preuve est `output/optimizer-market-135-result.json`, références
synthétiques explicitement identifiées par `QA_SYNTHETIC`.

L’accès du navigateur à `http://127.0.0.1:8001` est bloqué (`ERR_BLOCKED_BY_CLIENT`).
La recette visuelle desktop / mobile n’a donc pas été effectuée pour ce lot.
L’onglet temporaire est fermé. Le serveur de recette isolé est arrêté et le port
8001 libéré ; ses workers sont terminés. La base réelle conserve sa taille et sa
date de modification d’avant recette. Aucun arrêt n’a été envoyé au PID préexistant
25480, identifié comme `backend/run.py` ; il n’est plus présent au contrôle final,
et le port 8000 n’écoute plus. La cause de cette disparition n’a pas été déterminée.
Le backend doit être relancé pour charger les nouvelles routes et la migration.

Smile, calibration implicite, convergence temporelle plus fine, scénarios enrichis,
recherche de nouveaux paniers, conservation des runs et Copilot restent différés.
