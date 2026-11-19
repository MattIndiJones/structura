# Rechargement du marché : séances de bourse

État local au 03/11/2026. Complément au
[correctif du comparateur du 01/11](COMPARATOR_DETAILS_PRICING_2026-11-01.md).

## Cause constatée

Le rechargement global et individuel du marché dans le Pricer ne demandaient pas
`session_aware=true`. La politique générique de continuité rejetait les fermetures
prolongées comme des lacunes non bornées (`UNBOUNDED_HISTORY_GAP`).

Lecture du cache BNP.PA de ce poste : historique ajusté de 355 observations,
avec deux intervalles de cinq jours, jusqu'au 29/12/2025 et au 07/04/2026.
Ces intervalles correspondent aux fermetures de Noël et de Pâques du calendrier
XPAR. Le diagnostic reproduit le message sans réseau ni modification du cache.

## Correction

Les deux chargements du Pricer demandent maintenant la qualification des séances
déjà utilisée par le comparateur. L'estimateur RMS, l'annualisation 252, les
252 derniers rendements et le calcul de corrélation sur échantillon commun sont
conservés. Les vraies clôtures absentes sur séance ouverte restent bloquantes ;
aucun remplissage, cours précédent ou Following n'est injecté.

La séance courante n'entre dans l'échantillon attendu qu'après la clôture de sa
place, selon l'horloge métier et son fuseau. Une barre intrajournalière déjà
stockée est exclue avant cette clôture, sans être qualifiée de barre hors séance.
Les dates concernées figurent dans `session_qualification.pending_sessions`.
Cette sélection temporelle ne certifie pas la finalité des barres fournisseur.

Si les métadonnées stockées et le suffixe ne donnent pas de calendrier connu,
le service demande la place de cotation à Yahoo. La provenance est exposée dans
`sources`. Un titre sans suffixe comme AAPL peut ainsi être rattaché au Nasdaq ;
aucune place n'est inférée de la devise. Une place non identifiée reste un refus.
Les fixings officiels, les contrats bookés et la politique globale de fraîcheur
ne sont pas modifiés.

## Vérification et activation

- Sur le cache réel BNP.PA, sans réseau : 252 rendements, volatilité réalisée
  de 27,61045 %, date effective 02/11/2026, zéro substitution ; la séance du
  03/11 en cours est exclue. Ce chiffre décrit ce cache à cet instant.
- 59 tests backend ciblés distincts réussis : qualification, route HTTP,
  calendrier Nasdaq sourcé, trous réels, séance en cours et cache/provenance.
  Une fixture existante de booking a été complétée avec les deux champs
  `transaction_format=NOTE` et `instrument_family=NOTE` : son refus 422 pour
  classification absente était déjà documenté dans le rapport du 01/11.
- 961 tests frontend réussis et build Vite réussi, dont les deux nouveaux cas
  de rechargement individuel/global. Frontend compilé régénéré.

Les tests utilisent des données synthétiques, des fournisseurs simulés et des
bases isolées. Le diagnostic réel relit seulement les fichiers de marché locaux.
Aucun serveur existant arrêté, aucun compte, deal ou cache réel modifié par le
diagnostic. Aucune suite backend complète lancée, aucun commit ni push.

Redémarrer le backend par le lanceur, puis actualiser le navigateur avec Ctrl+F5
avant de recharger le marché pour appliquer aussi la sélection des séances
terminées et la résolution des places de cotation.

## Complément du 18/11/2026 : MtM du deal en « Marché actuel »

Constaté sur un autocall GLE.PA (STRU-20261105-001) : « Historique incomplet ou hors
politique : GLE.PA (UNBOUNDED_HISTORY_GAP) » au calcul du MtM en marché actuel. Même
cause qu'ici : la recalibration réalisée de `core/deal_valuation.mtm_core` lisait sa
fenêtre d'un an sur le chemin générique, qui compte Pâques (quatre jours sans séance sur
Euronext) et Noël un jeudi comme des lacunes. Ce correctif du 03/11 n'avait couvert que
le Pricer et le comparateur.

Le chargement qualifié est désormais une seule fonction,
`services/market_data.load_session_calibration_history`, utilisée par
`load_hist_vol(session_aware=True)` et par le MtM : les deux chemins ne peuvent plus
diverger. Une place inconnue ou une clôture manquante sur une séance ouverte donnent un
422 avec la raison ; aucun cours n'est remplacé. Sur la série réelle de GLE.PA au
18/11/2026 : 355 séances, volatilité réalisée de 34,73 % sur 252 rendements. Tests :
`test_mtm_realized_sessions.py`.

**Premier passage incomplet, corrigé le même jour.** Le cœur choisissait le chargeur
qualifié quand aucun chargeur de prix n'était injecté. Or la route
(`api/deals/valuation._mtm_core`) injecte explicitement `load_hist_prices` : l'écran
gardait le refus, alors que les tests, qui appelaient le cœur sans injection, passaient.
Le chargeur de calibration est désormais une dépendance explicite (`calibration_loader`),
transmise par la route. Le test passe par la route, et échoue si on retire cette ligne.
Vérifié de bout en bout par la route sur STRU-20261105-001 (base en lecture seule) :
MtM 87,83 %, σ réalisée 34,73 %.

Deux corrections du harnais de test vont avec :

- `deals_patch.patch_deals(..., "load_hist_prices", ...)` fait aussi suivre la
  recalibration, comme le faisait l'ancienne injection ;
- `amc_prices` fige son répertoire au premier import. Un autre module de test collecté
  avant peut donc faire lire au test le vrai magasin AMC, où la séance retirée existe.
  Le test coupe ce magasin.

## Complément du 18/11/2026 (2) : la règle de continuité elle-même

En préparant l'extension aux autres appels, la mesure sur les vraies séries a montré que
le défaut ne venait pas des appels mais de la règle de continuité. `align_history` comptait
les jours calendaires entre deux cotations, **cours nus et ajustés confondus** :

| Chemin générique, arrêté au 18/11/2026 | Avant | Après |
|---|---|---|
| GLE.PA depuis le 05/01/2026 (Pâques) | refusé | 225 dates |
| GLE.PA depuis le 17/11/2025 (Noël un jeudi, Pâques) | refusé | 257 dates |
| GLE.PA + AAPL depuis le 05/01/2026 | refusé | 227 dates |
| UCG.MI + STMPA.PA + SAP.DE depuis le 01/06/2024 | refusé | 631 dates |
| AAPL depuis le 05/01/2026 | 221 dates | 221 dates |

Le rejeu du cycle de vie d'un deal européen frappé avant Pâques 2026 était donc refusé
lui aussi, et avec lui le MtM même en mode booking, les constatations, le P&L explain,
les notes, la VaR et le CCR : seize appels passent par ce chemin.

**La correction** (`core/venue_closures.py`) retire du décompte, et de l'âge d'un cours
reporté dans un panier sur plusieurs places, les **jours de semaine où la place du titre
est fermée**. Les week-ends comptent comme avant et une séance ouverte sans cotation reste
une lacune. La règle ne cesse donc que de pénaliser les fermetures : elle n'accepte rien
qu'elle refusait pour une autre raison. La place est celle que déclare le fournisseur,
sinon celle du suffixe du ticker. Une place inconnue garde la règle calendaire et le refus.
La table des suffixes est désormais unique et partagée avec la qualification de
calibration. Le contrôle de `storage_status` suit la même règle. Le panier
GLE.PA + AAPL garde une seule séance reportée, le lundi de Pâques, où New York cote et
Paris est fermé.

**Ce qui ne change pas** : la limite de trois jours de D03 elle-même, et le contrôle de
fraîcheur à la date demandée (`market_policy.freshness`). Une valorisation **le** lundi de
Pâques d'un titre parisien, dont la dernière clôture date du jeudi, reste refusée comme
périmée. C'est le texte de D03, non modifié sans décision explicite.

La **reconduction** calibre désormais comme le Pricer (`load_hist_vol(session_aware=True)`)
et renvoie `vol_refresh_error` quand elle retombe sur la vol du booking. L'infobulle de
l'écran Booking affiche cette raison au lieu d'un « Yahoo indisponible » systématique.
La **VaR** et le **marché commun du CCR** n'ont pas eu besoin d'être modifiés : ils
passaient par la règle corrigée.

Tests : `test_venue_closures.py`. Les quatre tests de comportement échouent sans la
correction ; les quatre tests de garde (lacune réelle, place inconnue, résolution de la
place) passent dans les deux cas. `test_comparator_details_pricing.py` exigeait encore le
refus du chemin générique ; c'est corrigé. Ses quatre tests de séance manquante
échouaient aussi selon l'ordre de collecte, **avant cette correction déjà** : ils lisaient
le vrai CS.PA du magasin AMC, figé au premier import. Sa fixture coupe désormais ce
magasin.

## Complément du 19/11/2026 : D03 à la date demandée

**Décision de Philippe** : le jour où la place est fermée, on prend le dernier prix connu.

La réserve du complément précédent est levée. `market_policy.freshness` reçoit désormais la
place du titre et retire de l'ancienneté de la dernière clôture les jours de semaine où
cette place est fermée, entre cette clôture et la date demandée. C'est la même règle que
celle de la continuité. Une valorisation de GLE.PA le lundi de Pâques prend la clôture du
jeudi : quatre jours calendaires, dont deux de fermeture, soit deux jours retenus.

| Clôture du jeudi 02/04/2026, place XPAR | Calendaires | Fermés | Retenus | Statut |
|---|---|---|---|---|
| Vendredi saint 03/04 | 1 | 1 | 0 | reporté |
| Lundi de Pâques 06/04 | 4 | 2 | 2 | reporté (refusé avant) |
| Mardi 07/04 | 5 | 2 | 3 | reporté (refusé avant) |
| Mercredi 08/04 | 6 | 2 | 4 | **périmé** |

**Ce qui ne change pas** : la limite de trois jours ; les week-ends, qui comptent toujours ;
une place inconnue, qui garde la règle calendaire et donc le refus ; le change de reporting,
qui n'a pas de place. La version de la politique devient `D03-C11-2026-11-19-3D-VENUE`, et
chaque statut de fraîcheur expose `venue_calendar`, `venue_closed_days` et
`policy_age_days` à côté de l'ancienneté calendaire `age_days`.

Appels raccordés : l'alignement des historiques, le choix du stock local avant un
téléchargement, `storage_status`, la référence de marché, le profil de dividendes, et
l'observation de la watchlist, qui suivait la même règle entre deux dates d'observation.
Les fixings contractuels (`fixing_finality`) ne sont pas concernés : un fixing reste une
constatation de séance, pas un cours reporté.

Tests : dix cas ajoutés à `test_venue_closures.py`. Les neuf cas de comportement échouent
sans la correction ; le dixième, la place inconnue toujours refusée, est une garde ;
266 tests des consommateurs de la règle et 40 des chargements de prix réussis. Pas de
mesure sur une série réelle à cette date.
