# Pricing avant strike et reprise de session — 07/10/2026

## Causes et corrections

La route `/api/price/in-life` appelait l'historique et exigeait un ticker même
avant StartDate. L'absence de données bloquait donc un produit sans fixing
passé. Avant strike, elle utilise désormais les hypothèses reçues sans aucun
appel à l'historique ; le moteur existant simule le fixing sur chaque
trajectoire. Après strike, les contrôles historiques restent actifs.
Les payoffs, modèles de diffusion et calibrations ne changent pas.

Les résultats affichent « Fixing initial à venir » : aucune clôture future
n'est recherchée et un S₀ normalisé n'est plus présenté comme constaté.

Le seed contenait AXA sous `AXA.PA`. Le symbole Yahoo est
[`CS.PA`](https://fr.finance.yahoo.com/quote/CS.PA/), déjà présent ailleurs
dans l'administration. Au démarrage, la ligne initiale du référentiel est
corrigée en conservant son identifiant. Si `CS.PA` existe déjà dans le même
groupe, l'ancienne ligne est désactivée, sans suppression. Les groupes
personnalisés et snapshots contractuels restent intacts. Un panier déjà saisi
avec `AXA.PA` doit être corrigé explicitement pour charger le marché ou
ses fixings passés.

`PricerView` réinitialisait chaque retour sur `/pricer`. Le chargement des
liens script/produit/deal/RFQ/modèle est maintenant centralisé dans cette vue.
Le retour sur la même entrée ou sur `/pricer` reprend la session en mémoire.
Une autre entrée explicite est chargée normalement ; « Ouvrir le modèle »
remplace volontairement la session même pour le même modèle.
L'accueil affiche « Reprendre le pricing » et le Pricer propose une action
explicite « Nouveau pricing ». La reprise couvre la navigation, pas le
rechargement de la page ni la fermeture du navigateur. La conservation en
dossier reste une action volontaire.

## Validation

- **168 tests backend ciblés**, sur `test_inlife_pricing.py`,
  `test_payscript_presets.py`, `test_underlyings_catalog.py`. Les 15 exemples
  sont pricés avant strike en mono et multi avec ticker absent/invalide et
  un historique qui fait échouer le test si appelé.
- **287 tests frontend et build réussis**. Reprise des différentes entrées,
  conservation des termes/marché/prix et rendu S₀ futur sans fetch de clôture.
- Recette sur une copie isolée : Autocall 3Y, StartDate 14/10/2026,
  valorisation 07/10/2026, coupon 10 %, AC 100 %, KI européenne 60 %, r 3 %,
  q 2 %, σ 30 %, 20 000 paires antithétiques, seed 42. Sans ticker,
  GBM **92,91 %** ; avec le profil actions indicatif actif, Dupire **92,20 %**.
  Passage par Clients puis Pricing : mêmes saisies, même prix et onglet
  Marché repris. Le sélecteur AXA propose effectivement `CS.PA`.
  Capture : `output/forward-session-20261007/session-retained.png`.

## Contrôle complémentaire du smile

Autocall 5Y, mêmes hypothèses, surface actions SSVI rho -75 %, eta 0,85,
ATM plate 30 %, corrélation multi 40 %, via l'API forward start :

| Cas | GBM | Dupire | Dupire − GBM |
|---|---:|---:|---:|
| Mono | 91,4651 % | 91,7659 % | +30,08 bp |
| Worst-of à deux actifs | 78,7561 % | 79,1613 % | +40,52 bp |

Même seed, mais aucun intervalle couplé de l'erreur sur la différence n'est
calculé ici. Le signe et la magnitude ne sont pas universels. L'écart de
3 bp signalé par Philippe reste à vérifier sur ses termes et sa surface exacts.
Résultats : `output/forward-session-20261007/comparison.json`.

La recette ne modifie pas la base réelle. L'instance préexistante n'est pas
arrêtée : son propriétaire doit redémarrer le backend pour charger les
corrections et rectifier le référentiel existant.
