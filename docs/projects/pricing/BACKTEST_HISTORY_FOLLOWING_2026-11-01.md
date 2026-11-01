# Backtest historique : début commun et Following explicite

État local au 01/11/2026. Le backtest principal du Pricer propose désormais le
premier début commun connu et une convention explicite pour les cours absents.
Le choix confirmé par Philippe est **10 jours calendaires maximum par défaut**.

## Périmètre et diagnostic

Le message `UNBOUNDED_HISTORY_GAP` est produit par la qualification globale de
l'historique, qui rejetait une série présentant une longue interruption avant
même de lire les observations nécessaires au payoff. Modifier seulement le début
du formulaire ne suffisait donc pas à traiter les lacunes internes.

Le backtest principal utilise maintenant les clôtures non ajustées réellement
observées et leur intersection entre titres, sans remplir une matrice de prix.
Les autres consommateurs conservent leur politique de données et leur convention
de lecture. Le comparateur de sous-jacents utilise également ce mode depuis
[l'extension du 01/11](CALENDARS_COMPARATOR_2026-11-01.md), avec une période commune
à son univers exploitable et des exclusions exploratoires explicites.
Le rejeu officiel d'un deal, ses fixings et sa valorisation ne reçoivent pas cette
option ; le moteur refuse de la combiner avec une origine de contrat explicite.

Le cas réel STM de la capture n'a pas été rejoué : ni son historique réel ni son
script complet n'ont été qualifiés pendant cette recette. L'implémentation traite
la classe de problème observée, sans affirmer que toutes les lacunes de ce titre
sont acceptables sous la limite retenue.

## Début de période

- À l'ouverture, `GET /api/backtest/history-bounds` lit uniquement les historiques
  locaux non ajustés. Aucun téléchargement fournisseur n'est déclenché.
- Pour un titre : première clôture valide connue. Pour un panier : première date
  disposant simultanément de clôtures valides pour tous les titres, et non le
  simple maximum des dates individuelles de début.
- Sans historique commun local connu, le champ reste vide. Le lancement explicite
  détermine le début depuis les données chargées ; une date vide signifie
  « automatique » dans `BacktestRequest`.
- Une saisie manuelle est conservée. Le bouton « Utiliser le début commun »
  réactive le défaut. Un changement de panier invalide la prévisualisation
  précédente ; les réponses tardives sont ignorées.
- Le chargement réutilise les données locales si leur couverture est suffisante.
  Le mode automatique ne retélécharge pas simplement parce que le titre n'a pas
  de cours en 1900. Un téléchargement reste possible au lancement si les données
  locales sont absentes ou nécessitent une actualisation.

## Lecture des observations

| Choix | Comportement |
|---|---|
| Following, défaut | Première date commune réellement cotée à la date demandée ou après |
| Strict | Refus dès qu'une observation nécessaire manque à la date demandée |
| Limite | 10 jours calendaires par défaut, réglable de 0 à 31 ; 10 accepté, 11 refusé avec le défaut |
| Au-delà de la limite ou après la fin disponible | Échec explicite du calcul, aucune fenêtre concernée retirée silencieusement des statistiques |

Tous les titres du panier sont lus à la même date effective. Pour chacun, le
rapport distingue un cours absent à la date demandée d'un déplacement imposé par
l'alignement sur les autres titres. Le système ne prétend pas distinguer un jour
de fermeture d'une lacune du fournisseur.

La convention ne modifie pas l'échéancier contractuel d'origine. Elle s'applique
aux constatations requises par la fenêtre de backtest, y compris aux relevés
d'une moyenne. Des relevés distincts peuvent aboutir à la même clôture : leurs
poids dans la réduction restent conservés et leurs décalages sont explicités.
Les événements gardent leur ordre dans le script. Après un `STOP`, les événements
futurs ne provoquent pas de substitutions inutiles.

Les constatations sont datées à leur date effective. Les paiements correspondants
sont décalés du même nombre de jours calendaires, en conservant le décalage de
paiement demandé par le calendrier. Il s'agit d'une convention de simulation
affichée dans le formulaire et le résultat, pas d'une nouvelle convention de
règlement contractuel. Aucun calendrier de règlement supplémentaire n'est
implicitement appliqué au déplacement. Le TRI utilise les dates de paiement
effectives. Le temps de `REALVOL` utilise le temps calendaire écoulé dans ce mode,
afin qu'une interruption ne soit pas comptée comme une seule séance.

Le suivi des barrières et des extrema porte sur les clôtures communes disponibles.
Les franchissements intrajournaliers et les cours absents entre clôtures ne sont
pas reconstitués, y compris en mode strict. Strict contrôle les observations
requises ; ce n'est pas une certification d'exhaustivité de toutes les séances.

## Résultat et traçabilité

`history_policy` conserve la version de méthode, le mode, la limite, les bornes
demandées et utilisées, la convention de paiement et les ajustements. Chaque
ligne contient la fenêtre de départ, le ticker, la date demandée, la date retenue,
le nombre de jours et le motif. La provenance et les bornes par titre restent dans
`market_data`. Un scénario synthétique garde son libellé et ses avertissements.

Le disclaimer reste visible au-dessus du menu « Dates ajustées ». Le tableau est
paginé par 50 lignes ; l'export JSON contient **tout** le résultat et tous ses
ajustements. Un résultat ancien ne s'applique pas à un panier modifié pendant le
calcul. Les cours fournisseur restent non certifiés ; cet export ne constitue pas
à lui seul un gel exhaustif des données permettant un rejeu futur à l'identique.

## Validation et mise en service

- 26 nouveaux tests backend réussis : cours suivant réel et datation du flux,
  dates exactes, strict, limites inclusives, fin d'historique, panier et motif,
  moyenne, ordre et STOP, paiement différé, TRI indépendant, temps de REALVOL,
  début commun, réutilisation locale sans fournisseur, téléchargement explicite
  de l'historique maximal ou d'une période choisie, conservation du scénario
  synthétique et refus d'une politique non bornée.
- Groupe ciblé final : 101 réussites et un échec de booking dans
  `test_market_data_governance.py`. Le même échec est reproduit sur un export du
  code `HEAD` sans les modifications locales : format/famille du produit absent
  de la requête du test. Il préexiste à ce changement. Les 26 nouveaux tests
  sont inclus dans les 101 réussites ; ces nombres ne doivent pas être additionnés.
- `npm run build` : 935 tests frontend réussis, dont 11 nouveaux tests, puis
  compilation Vite réussie.
- Quatre contrôles navigateur sur le frontend compilé : début du titre et défaut
  de 10 jours ; début commun du panier et saisie manuelle ; strict, disclaimer et
  tableau déplié ; export JSON complet. Toutes les API sont simulées, identité et
  données fictives ; aucune validation de prix réels STM n'est revendiquée.
- Preuves locales : `.runtime/backtest-following-new.xml`,
  `.runtime/backtest-following-targeted.xml`, `.runtime/backtest-baseline.xml`,
  `.runtime/backtest-following-frontend-build.log` et
  `.runtime/diagnostic-acceptance/backtest-following-2026-11-01/`.

Aucune base métier ouverte par les tests : runtime temporaire, réseau externe
bloqué côté backend ; toutes les API du navigateur interceptées. Les instances
préexistantes sur 8000 et 8100 sont conservées ; aucun nouveau serveur applicatif
n'est lancé. Le backend existant fonctionne sans reloader : il faudra le
redémarrer par le workflow habituel pour charger ces nouvelles routes et règles,
puis actualiser le navigateur. Aucun commit, push ou déploiement effectué.
