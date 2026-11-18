# Découpage du store du Pricer — 18/11/2026

Reprise du constat A6 de l'[audit technique du 16/11](../../audits/AUDIT_GLOBAL_TECHNIQUE_2026-11-16.md) :
`frontend/src/stores/pricing.js` faisait 3 668 lignes, un seul magasin d'état pour tout le
Pricer. Branche `refactor/split-pricing-store`.

**Aucune logique n'a changé, et l'interface du store non plus** : l'objet renvoyé par
`usePricingStore()` est le même, recopié tel quel. Les 999 tests frontend passent, de même
que le build.

## Le principe

Le store est en mode « setup » : une seule fermeture où l'état, les fonctions et les
observateurs se voient par leur nom. Chaque section du fichier devient un module
`src/stores/pricing/<domaine>.js` qui exporte `install<Domaine>(s)`. Le store installe les
modules dans l'ordre, sur un contexte partagé `s`, puis renvoie son objet.

Dans chaque module :

- les noms définis par un module **précédent** sont déstructurés en tête
  (`const { globalParams, result, … } = s`) et le code se lit comme avant ;
- les noms définis par un module **suivant**, une quinzaine en tout, sont lus en `s.nom` au
  moment de l'appel ;
- les compteurs `let` partagés entre modules (`_pricingRevision`, `_parseRevision`,
  `_marketDataRevision`, `automaticMarketRequest`, `lastAutomaticMarketKey`) vivent sur `s`,
  pour garder une seule valeur ; ceux qu'un seul module utilise y ont été déplacés ;
- à la fin, `Object.assign(s, { … })` publie ce que le module définit.

Les quatorze fonctions pures (sans aucun état) sont dans `helpers.js`, importées normalement,
avec `DEFAULT_SCRIPT`.

Le découpage a été fait par un script qui analyse la fermeture avec `@babel/parser`, résout
les portées (paramètres, blocs, `catch`, boucles) pour ne réécrire que les vraies références,
et refuse toute fonction « pure » qui toucherait l'état.

## Le piège rencontré

Une référence vers l'avant **passée comme valeur au moment de l'installation** ne peut pas
être lue en `s.nom` : l'observateur `watch(…, _applyCalendarDefaults, { flush: 'sync' })`
recevait `undefined`, puisque le module qui définit la fonction n'était pas encore installé,
et les calendriers de règlement ne suivaient plus la devise. Le test
`calendarDefaults.test.js` l'a vu. Une telle référence passe désormais par un relais
`(...args) => s.nom(...args)`. C'est le seul cas dans le store.

## Les modules

| Module | Lignes | Contenu |
|---|---:|---|
| `pricing.js` | 126 | Installation des modules et objet renvoyé |
| `helpers.js` | 144 | Fonctions pures, script par défaut |
| `scriptState.js` | 225 | Onglets, script, paramètres déclarés, calendriers CONSTAT |
| `marketInputs.js` | 174 | Sous-jacents, paramètres globaux, courbes, sélection des Greeks |
| `productContext.js` | 149 | Script en base, variante, produit, RFQ, deal |
| `requestState.js` | 430 | États des résultats, construction des corps de requête |
| `parsePrepare.js` | 264 | Analyse du script, préparation des calculs |
| `dates.js` | 221 | Régime de valorisation, maturité |
| `runs.js` | 549 | Pricing, Greeks, profil, trajectoires, probabilités, backtest, comparateur, assistant, dictée |
| `mtf.js` | 193 | Mark-to-Future et détail par date |
| `simulationTools.js` | 113 | Solveur, grille, scénarios |
| `marketData.js` | 268 | Données de marché |
| `session.js` | 156 | Remise à zéro, suivi de session |
| `loaders.js` | 719 | Chargement depuis un modèle, un preset, un produit, un deal, une RFQ, la base |
| `persistence.js` | 217 | Variantes, sauvegarde, gestion des sous-jacents |

## Pour la suite

- Un nouvel état ou une nouvelle action se range dans le module de son domaine et entre dans
  son `Object.assign` ; s'il doit être visible des composants, il entre aussi dans l'objet
  renvoyé par `pricing.js`.
- Un module ne déstructure que ce que les modules précédents ont publié. Pour utiliser un nom
  d'un module suivant, écrire `s.nom` dans le corps d'une fonction, et un relais s'il est passé
  comme valeur à l'installation.
- `loaders.js` (719 lignes) reste le plus gros : `loadFromDeal` et `loadFromRfq` y font chacun
  plus de 150 lignes. Les redécouper serait un travail de conception.
- Vérifié par les tests et le build, **pas dans l'application ouverte** : un tour du Pricer
  (pricing, Mark-to-Future, chargement d'un deal) reste à faire.
