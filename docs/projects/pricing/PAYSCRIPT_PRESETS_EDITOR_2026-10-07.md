# Éditeur unique et exemples PayScript préremplis — 07/10/2026

**État : implémenté localement sur `codex/payscript-basket-startdate`.**

Complément de recette : [pricing avant strike et reprise de session](../../audits/RECETTE_FORWARD_SESSION_2026-10-07.md).
Demande de Philippe : supprimer la séparation Normal/Expert devenue inutile et
ajouter des exemples comme « Autocall 3Y », sans encombrer la bibliothèque générique.

## Parcours livré

Le Pricer utilise un seul éditeur. Les 19 modèles génériques gardent des
`PARAM` requis et des calendriers vides ; leur logique, le panier `UNDERLYING
Basket`, son attribut `yield` et le fixing explicite `StartDate` sont conservés.
Le sélecteur Normal/Expert et son état Pinia sont retirés.

Les réglages de roll/stub se déplient sous « Réglages avancés du calendrier »
dans Economics et dans les éditeurs RFQ. Les conventions de jour ouvré et les
décalages de règlement restent visibles. Les cours initiaux en devise sont
proposés lorsqu’un script utilise des cours absolus, ou lorsqu’une valeur a
déjà été saisie. L’initialisation `Basket.spot0 = Basket.spot@StartDate` et le
ratio `Basket.spot / Basket.spot0` ne déclenchent pas cette saisie.

« Exemples préremplis… », à côté des modèles génériques et dans la création
RFQ, ouvre un aperçu facultatif. L’utilisateur choisit l’exemple et sa date
de départ. L’aperçu montre les paramètres, le strike effectif, la date de valeur,
la première observation, la maturité et le paiement final ; les dates
d’observation et le script complet se déplient à la demande.

Le chargement remplace la logique et ses Economics. Il conserve le panier,
les volatilités/surfaces, dividendes, corrélations, modèle de pricing, taux,
funding, nominal et devise. Dans le Pricer, les résultats et les liens du
précédent brouillon sont effacés, puis Economics s’ouvre. Les termes d’un
contrat figé ne peuvent pas être remplacés par un exemple.

Les configurations personnelles restent disponibles sous « Mes configurations
enregistrées… ». Les exemples livrés sont des données statiques du dépôt,
pas des lignes ajoutées à la base des scripts.

## Les 15 exemples

Tous utilisent le worst-of du panier existant, y compris en mono-actif.
Les coupons s’expriment **par observation**, sans annualisation implicite.

| Exemple | Observations | Paramètres affichés dans Economics |
|---|---|---|
| Autocall 3Y / 4Y / 5Y | Annuelles | Coupon cumulé 10 %, rappel 100 %, protection européenne 60 % |
| Autocall à barrière américaine 3Y | Annuelles | Coupon cumulé 10 %, rappel 100 %, protection américaine 60 % |
| Autocall dégressif 5Y | Annuelles | Coupon cumulé 10 %, rappel 100/95/90/85/80 %, protection européenne 60 % |
| Phoenix trimestriel 3Y / 5Y | Trimestrielles | Coupon 2 % / 2,5 % par trimestre, rappel 100 %, coupon et protection européenne 60 % |
| Phoenix mémoire 3Y / 5Y | Trimestrielles | Même coupon, avec rattrapage des coupons manqués |
| Reverse Convertible 1Y | À maturité | Coupon 8 %, protection européenne 60 % |
| Capital garanti 5Y | À maturité | Participation 100 %, strike 100 % |
| Twin Win 3Y | À maturité et monitoring américain | Plafond de remboursement 120 %, barrière américaine 60 % |
| Call 1Y / Put 1Y | À maturité | Strike 100 %, sans jambe de remboursement nominal |
| Call Spread 1Y | À maturité | Strikes 100 % et 120 %, sans jambe de remboursement nominal |

Le Twin Win conserve le payoff du modèle : performance absolue plafonnée sans
franchissement ; après franchissement, exposition linéaire à la performance
finale. Les autres scripts ne sont pas dupliqués ni réécrits : chaque exemple
référence sa fiche du catalogue et fournit ses paramètres/calendriers séparément.

## Dates et protection des saisies

Les exemples choisissent explicitement **jour ouvré suivant / J+3 ouvrés**,
affichés dans l’aperçu. Il ne s’agit pas de nouveaux défauts globaux.
Le serveur résout les jours ouvrés selon la devise. La date de valeur proposée
égale le strike effectif ; les observations commencent un an ou un trimestre
plus tard selon l’exemple. Pour une option, l’unique observation est à maturité.
Toutes ces propositions restent modifiables.

Les dates et le script sont validés **avant** toute modification de la session.
Une erreur de préparation ou une annulation ne remplace aucune saisie. Les
réponses d’un ancien aperçu et les anciens parses RFQ ne peuvent pas écraser
l’exemple chargé. Une ancienne proposition de paiement RFQ ne remplace plus une
date explicitement chargée entre-temps.

La revalidation d’un `CONSTAT` simple conserve ses conventions et son règlement.
La recette du dégressif a aussi révélé une variable manquante dans Economics :
les dates des lignes `PARAM()` ne pouvaient pas être affichées. Le composant
utilise désormais `datesObservations` du même aperçu que sa table des événements.

## Vérifications réalisées

- `backend/tests/test_payscript_presets.py` : **95 cas réussis**, dont les
  15 exemples × 3 dates de départ × EUR/CHF. Compilation, paramètres requis,
  coupon en %, première observation distincte du fixing, paiements J+3,
  absence de doublon après sauvegarde de la maturité ajustée et nombre de
  barrières dégressives. Cinq scénarios de flux indépendants : rappel,
  survie/protection, perte, mémoire trimestrielle et rappel dégressif.
- `backend/tests/test_payscript_reference.py` : **14 tests réussis** après
  mise à jour du lexique. Aucune suite backend complète lancée.
- `npm run build` : **284 tests frontend réussis**, puis build Vite réussi.
  Les nouveaux contrôles portent sur les unités, les dates, la conservation
  du marché/panier, les refus sans mutation, les cours absolus et le rendu
  effectif des tableaux dans Economics/RFQ. Le plugin Vue existant est activé
  dans Vitest pour les deux tests de rendu sans navigateur.
- Recette navigateur sur une copie isolée de la base : Autocall 3Y chargé et
  pricé ; Phoenix mémoire 3Y chargé avec deux actifs et 12 observations puis
  pricé ; dégressif 5Y affichant ses cinq barrières après correction ; roll/stub
  accessibles dans le Pricer et la RFQ ; Autocall 4Y chargé en RFQ CHF avec
  panier et volatilité saisie de 33 % conservés ; annulation d’un Call Spread
  laissant cette RFQ intacte. Aucune nouvelle erreur console après la correction.

L’Autocall mono a donné 99,58 % et le Phoenix mémoire en panier 101,68 % sous
GBM, avec les hypothèses de recette de 20 % de vol, 2 % de dividende, 3 % de taux,
20 000 paires antithétiques, seed 42 et corrélation nulle. Ce sont des mesures
de fonctionnement sur hypothèses, pas des prix de marché ni un nouveau
comparatif de modèles de volatilité.

Les captures et traces de cette recette sont dans
`output/payscript-presets-20261007/` (hors Git). La base réelle n’est pas modifiée.
La recette ne crée ni deal ni RFQ persistante ; les nouveaux exemples utilisent
les mêmes interfaces de termes que les modèles génériques. Le booking, le
replay et le cycle de vie n’ont pas fait l’objet d’une nouvelle recette ici.

La référence maintenue est
[PayScript Reference](../../reference/PAYSCRIPT_REFERENCE.md). La note
[Basket / StartDate du 06/10](PAYSCRIPT_STARTDATE_IMPLEMENTATION_2026-10-06.md)
reste l’historique de la livraison précédente, avec son ancien sélecteur.
