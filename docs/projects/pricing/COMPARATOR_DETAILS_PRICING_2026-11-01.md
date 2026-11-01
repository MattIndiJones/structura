# Comparateur : prix indicatif et détail graphique d'une ligne

État local au 01/11/2026, à la suite des
[calendriers et du Following du comparateur](CALENDARS_COMPARATOR_2026-11-01.md).

## Blocage du prix indicatif

Le bouton chargeait `/api/finance/hist_vol` avant le Monte Carlo. Ce chargement
conservait la politique historique globale à trois jours calendaires et pouvait
rejeter des fermetures prolongées de bourse, dont Pâques, avec
`UNBOUNDED_HISTORY_GAP`. Le Following du backtest n'était pas utilisé par cette
estimation de marché. La capture établit cette erreur, pas la localisation
exacte des lacunes de chaque historique réel.

Le bouton demande maintenant `session_aware=true`. Cette option charge les cours
ajustés réels, réutilise les observations stockées et qualifie les séances
attendues à partir d'un marché connu ou d'un suffixe de ticker reconnu. Les
fermetures de bourse sont exclues du calendrier attendu. Une clôture absente sur
une séance ouverte reste une erreur datée ; aucun cours Following, précédent ou
interpolé n'est injecté dans l'estimation de volatilité. Les éventuelles barres
du fournisseur hors séance sont exclues et comptées.

Le même estimateur RMS des rendements logarithmiques, annualisé à 252, et le
même échantillon commun sont conservés. Les calendriers utilisés et le nombre
de substitutions (zéro) sont exposés dans `session_qualification`. Les autres
consommateurs gardent la politique existante : cette option ne desserre pas
globalement la qualification des données. Les clôtures restent des barres
fournisseur non certifiées et le prix est indicatif.

Le corps du prix reprend maintenant le corps commun du Pricer : script,
paramètres, dates de strike/valeur/maturité/paiement, devise de règlement,
conventions, courbes de taux et funding, modèle et paramètres de taux. Les titres,
volatilités et dividendes sont ceux du candidat. La corrélation vient de la même
référence de marché datée, plutôt que de la période longue du classement.
La devise du candidat provient du catalogue ou de ses paramètres déjà renseignés,
sans EUR implicite pour un titre inconnu.

Une calibration de modèle avancé, une corrélation aux taux stochastiques ou des
paramètres de change propres au titre initial ne sont pas transférés tacitement
à un nouveau candidat. Si ces paramètres sont requis et absents, le message
demande d'adopter le panier puis de les qualifier dans le Pricer. Des dividendes
inconnus ne deviennent pas zéro. Un vrai zéro sourcé reste accepté.

Le prix réussi affiche sa date et les références de volatilité réalisée et de
dividende historique. Ce ne sont pas des volatilités implicites. Une réponse
devenue obsolète pendant le calcul n'est pas appliquée.

## Ligne sélectionnée et présentation

Les en-têtes et les valeurs du classement sont sur une seule ligne. Si nécessaire,
le tableau défile horizontalement. Les erreurs de prix sont placées sous la ligne
avec une cellule couvrant le tableau ; elles ne compriment plus les autres colonnes.

Un clic sur une ligne ou sur son nom sélectionne le candidat ; Entrée et Espace
sont également disponibles. Les boutons de prix et d'adoption gardent leurs
actions propres. Le panneau sous le tableau contient les mêmes composants que
le backtest général : statistiques, histogramme des TRI, TRI par date de départ,
détail des fenêtres, convention historique, ajustements et export complet.
`BacktestResults.vue` est partagé par les deux parcours, avec le masquage démo
et la destruction des graphiques lors d'un changement ou d'une fermeture.

## Cohérence avec le classement

La réponse de comparaison conserve son contexte de requête et une empreinte
SHA-256 des dates, prix, dates sources et type de prix. Les origines et fins
implicites sont explicitées dans ce contexte pour éviter une dérive au changement
de journée. Le contexte est celui du calcul, indépendamment du formulaire édité
après son lancement.

`POST /api/backtest/compare/detail` valide le panier sélectionné, recharge le même
univers sur cette période et vérifie l'empreinte avant de rejouer le sous-ensemble.
Les dates communes de l'univers sont conservées : le détail AXA ne repart pas sur
un historique AXA seul, plus long ou avec d'autres séances. Les mêmes paramètres,
calendriers et paiements sont utilisés. Les statistiques sont agrégées sur les TRI
non arrondis avant l'arrondi d'affichage, dans le classement comme dans le détail.

Si les observations ont changé, le serveur renvoie 409 et demande une nouvelle
comparaison. Il ne présente pas un graphique recalculé comme s'il expliquait
l'ancien classement. Les résultats de détail sont mis en cache dans le composant,
les réponses tardives sont ignorées et un nouveau classement vide cette sélection.
Le backtest général et le panier principal ne sont pas modifiés par la consultation.

## Validation et limites

- **105 tests backend ciblés réussis**, dont 11 nouveaux cas : parité du replay,
  période et origine figées, sélection invalide, changement de données d'un autre
  candidat, Pâques accepté sans remplissage, séance ouverte manquante refusée,
  week-end, exclusion d'une barre hors séance et pricing d'un remboursement
  déterministe confronté à `exp(-r × temps jusqu'au paiement)`.
- **959 tests frontend réussis et build Vite réussi**, dont neuf nouveaux cas
  sur le détail, les réponses tardives, le cache, les graphiques communs, le corps
  du prix, la provenance, les données manquantes et la calibration du candidat.
- **Neuf contrôles navigateur** sur le frontend compilé : les cinq parcours
  précédents, plus les en-têtes, le prix, la sélection AXA avec graphiques et
  export, et le changement de ligne. Aucun message d'erreur JavaScript.

Les tests backend utilisent un runtime temporaire, sans réseau externe et avec
accès SQLite à `backend/data` interdit. Les contrôles navigateur interceptent
toutes les requêtes et utilisent une identité et des données fictives. Les
graphiques sont inspectés visuellement ; ce n'est pas une qualification des
historiques réels AXA, L'Oréal ou BNP ni de toutes les familles de modèles.

Preuves locales : `.runtime/comparator-details-new.xml`,
`.runtime/comparator-details-targeted.xml`, `.runtime/comparator-details-frontend-build.log`
et `.runtime/diagnostic-acceptance/comparator-details-2026-11-01/`.

Aucun nouveau serveur applicatif lancé, aucune instance préexistante arrêtée.
La suite backend complète n'est pas exécutée. Aucun commit, push ou déploiement.
Redémarrer le backend par le workflow habituel, actualiser le navigateur et
relancer la comparaison pour recevoir le contexte nécessaire aux détails.
