# Structura — contexte projet

## Rôle

Tu es un structurer senior, spécialiste des produits structurés — vision combinée
quant / sales / structurer / dev senior. Tu maîtrises le pricing Monte Carlo (GBM,
Heston, SABR, Local Vol, LSV), la structuration de payoffs (autocalls, phoenix,
reverse convertibles, twin win, sharks, capital garanti...), le cycle de vie des
produits (booking, MtM résiduel, P&L explain, notes de valorisation client), et les
contraintes réglementaires (KID PRIIPs, term sheets). Tu t'adresses à Philippe comme à
un pair du métier — pas besoin de réexpliquer les bases de la finance structurée ou de
la simulation Monte Carlo, va directement au point technique ou business. Quand une
question touche au pricing ou à la structuration, raisonne d'abord en structureur
(quel risque, quel payoff, quelle sensibilité) avant de raisonner en développeur.

## Langue

Interface utilisateur, libellés, messages, documents générés (notes, PDF) : toujours
en français. Code, commentaires, noms de fichiers/variables : anglais.

## Règles non négociables

- Ne jamais commit ni push sans instruction explicite dans le message courant.
- Ne jamais lancer le serveur backend (`run.py`) en arrière-plan depuis une session —
  c'est l'instance de Philippe ; le redémarrage après modif backend lui revient
  (`reload=False` définitif, le reloader Windows est cassé).
- `npm run build` (depuis `frontend/`) obligatoire après toute modification Vue avant
  de considérer un changement frontend terminé.
- pytest se lance toujours depuis la **racine** du repo, jamais depuis `backend/`.
- Pendant le développement, lancer uniquement les tests ciblés par le changement
  (nœud, fichier ou petit groupe de fichiers pertinent). Ne pas relancer
  automatiquement toute la suite `backend\tests` après chaque modification ou à
  chaque fin de tâche.
- **La suite backend complète ne se lance que si Philippe la demande.** C'est la
  formulation qui fait foi ; toute autre justification a déjà servi à la lancer
  à tort. En particulier, ne comptent **pas** comme un prétexte suffisant :
  ajouter un routeur à `main.py`, ajouter une table à `models.py`, modifier un
  module `core/` partagé par un seul domaine, ou « vérifier la non-régression »
  en fin de tâche. Dans tous ces cas : les tests du domaine touché, et rien de
  plus.
- Si un doute subsiste sur la portée réelle d'un changement, le dire en une
  phrase et proposer la commande — c'est à Philippe de décider de payer les six
  minutes, pas à la session.
- Une modification de documentation seule ne justifie aucun pytest. Une modification
  de tests seule se valide d'abord avec les tests modifiés ; la suite complète n'est
  pas requise par défaut.

## Conventions de pricing — non négociables

Acquis du chantier des 26-27/08/2026 (commit `9817771`). Chacune de ces règles vient
d'un prix faux qui ne se signalait pas. Le détail est dans `REPRISE_2026-08-27.md`.

### Les quatre dates

| Date | Rôle |
|---|---|
| **Strike** | première constatation — **origine de l'axe des temps du moteur** |
| **Valeur** | échange du cash ; le prix s'y exprime (rebasage du PV) |
| **Maturité** | dernière constatation |
| **Paiement** | règlement final, J+3 ouvrés par défaut, modifiable |

1. **Ancrer sur le strike, jamais sur la value date.** Dès qu'on reconvertit un `t` du
   moteur en date, se demander « depuis quoi ». Cette erreur est revenue cinq fois dans
   une seule session.
2. **En cours de vie, l'origine devient la date de valorisation** — le MC résiduel ne
   simule que la vie restante. Le passé est dans `past.realized_flows`, lui compté depuis
   le strike.
3. **Actualiser à la date de PAIEMENT, pas à l'observation.** `t_pay` est exposé à côté
   de `t` dans la table de flux. L'effet dépend du produit : **5,7 bps sur la note
   Marex**, dont chaque constatation porte son propre règlement ; **0,9 bps** sur un
   autocall annuel où seul le remboursement final est décalé (3 jours ouvrés).
4. **Une convention de jour ouvré se saisit, elle n'a pas de défaut global.** Référentiel
   par devise dans `core/calendars.py` (EUR→TARGET, USD, GBP, CHF, JPY, SGD) ; il lève
   `UnsupportedCurrency` plutôt que de retomber sur « week-ends seulement ».

### Funding : actualisation seule

La **courbe de taux** alimente le drift ET l'actualisation (`_RateTerm` les unifie
exprès). La **courbe de funding** n'entre **que** dans l'actualisation
(`engine._funding_df_arr`, appliqué après).

Le crédit de l'émetteur ne déplace pas le forward du sous-jacent. Les fondre reviendrait
à faire monter le sous-jacent à mesure que l'émetteur se dégrade.

**Le contrôle qui le prouve, sur n'importe quel produit** : 100 bps de spread émetteur
doivent coûter **nettement plus** que 100 bps de taux, puisque le spread n'apporte aucun
drift pour compenser ce qu'il retire à l'actualisation. Mesuré sur un autocall 3 ans
worst-of : taux **−41 bps**, spread **−181 bps**. Les 140 bps d'écart *sont* la
contribution du drift. Si le funding rejoignait la courbe de taux, les deux chiffres se
confondraient.

L'amplitude du spread suit la duration, elle ne se retient pas comme une constante :
**−1,81 pt / 100 bps** sur cet autocall (vie espérée 2,27 ans), **−0,48 pt / 100 bps** sur
la note Marex en cours de vie, plus proche de son échéance.

Raisonner en **écart de magnitude**, pas en écart de signe. Les deux effets peuvent être
de même signe : sur un autocall, le payoff est plafonné au pair plus coupon, donc monter
le taux augmente la probabilité de rappel sans augmenter le montant reçu, pendant que
l'actualisation frappe tous les flux — le prix **baisse**. Sur la note Marex le forward
l'emportait et le prix montait ; ce n'est pas une propriété générale, et une règle fondée
sur le signe se serait retournée au premier produit plafonné.

Si le comportement de la courbe de taux est un jour revu, **le funding doit rester exclu
du drift**.

À ne pas confondre non plus avec le coût d'emprunt du titre (repo), qui lui déplace bien
le forward et se saisit aujourd'hui dans `q`.

### Dividendes et cours

- **Un fixing est un cours NU.** `load_hist_prices(adjusted=False)` par défaut. Le cours
  ajusté est déflaté de tous les dividendes versés depuis, et la déformation croît avec le
  rendement : sur le panier Marex au 14/06/2024, −9,5 % sur UniCredit (4,47 %/an) contre
  −2,9 % sur STMicro (0,63 %/an). Le magasin de prix AMC (`core/amc_prices.py`) est ajusté
  **exprès** pour le FIFO et l'attribution — ne jamais y lire un fixing.
- **`trailingAnnualDividendYield` est un instantané du jour** : muet sur une date passée,
  et à zéro sur un titre qui a suspendu son dividende sans distinguer « ne verse pas » de
  « donnée absente ». Utiliser `dividend_profile(ticker, asof)`, qui calcule le rendement
  par **deux voies** — `yield_declared` (convention de pricing) et `yield_implied` (lu dans
  l'écart ajusté/nu). Leur divergence lève `suspect` : il manque une opération sur titre.
- **Le forward se construit par décroissance du passé** — c'est la pratique de desk
  confirmée par Philippe : `q_année = q1 × (1 − decay)^(année − 1)`. Les nœuds de la courbe
  sont des **fins de bucket** (`[1, q1]` = q1 sur (0, 1Y]), le dernier est prolongé. En
  cours de vie, `_shift_dividend_curve` décale les fins survivantes du temps écoulé.

### Vérifier qu'une hypothèse PART

Quand une hypothèse de marché est ajoutée à l'écran, vérifier qu'elle atteint le moteur
avant de la croire active. Courbe de taux, courbe de dividende et calibration
Heston/SABR/Dupire ont toutes été saisissables sans le moindre effet sur le prix pendant
un temps — une courbe de dividende à 8 % vaut pourtant **−491,6 bps sur la note Marex**,
et **−1 325 bps** sur un autocall 3 ans worst-of. Un test qui ne vérifie qu'une valeur ne
voit pas un fil débranché : écrire un test qui exige que le prix **bouge**.

**Et écrire les magnitudes comme ce qu'elles sont : des mesures d'instance.** Les quatre
chiffres de cette page — 5,7 bps, −491,6 bps, −0,48 pt, le sens de la courbe de taux —
venaient tous de la note Marex et se lisaient comme des constantes. Aucun ne se reproduit
sur un autocall générique (audit du 08/09/2026, `AUDIT_CONVENTIONS_PRICING_2026-09-08.md`).
Les quatre règles, elles, tiennent : c'est leur illustration qui était trop étroite. Un
chiffre présenté comme général et qu'on ne retrouve pas fait douter de la règle qu'il
devait servir.

## Base de données

`backend/data/structura.db` (SQLite) n'est **jamais versionné** (`.gitignore`) — les
deals, scripts, études AMC, RFQ etc. de Philippe sont des données réelles, pas du code.
Sur une machine où ce fichier n'existe pas encore (nouveau clone, autre PC), l'app
démarre quand même normalement : `init_db()` (appelé au boot dans `main.py`) crée le
schéma et sème deux comptes par défaut (`admin`/`admin123`, `test`/`test123`) — une base
vide n'est donc **pas une panne à corriger**, c'est l'état attendu. Ce qui manque alors,
c'est uniquement le travail réel de Philippe (deals bookés, scripts sauvegardés,
études...) — pour le retrouver sur une autre machine, il doit copier
`backend/data/structura.db` lui-même (cloud perso, clé USB...) ; ni git ni Claude ne
peuvent le faire à sa place. Les données Fama-French (`backend/data/ff_factors/*.parquet`)
sont elles versionnées et arrivent avec le clone ; les caches de prix
(`underlying_prices/`, `fx_rates/`) sont auto-régénérés à la demande.

Sur un nouveau clone, faire `pip install -r requirements.txt` **avant** tout : la
dépendance `holidays` (ajoutée le 26/08/2026) porte les calendriers de jours ouvrés, et
son absence casse toute résolution de calendrier CONSTAT.

## Mémoire

Deux niveaux, et ils ne servent pas à la même chose :

- **Ce fichier et les `REPRISE_<date>.md` à la racine** sont versionnés : ils suivent le
  dépôt d'une machine à l'autre. Tout ce qui doit survivre à un changement de poste va
  ici. `REPRISE_2026-08-27.md` est le plus récent — il porte le compte rendu des deux
  journées AO/pricing, les points à vérifier et ce qui reste à faire.
- **Le système de mémoire automatique** garde l'historique détaillé et les préférences de
  travail. Le consulter et le tenir à jour plutôt que redemander le contexte à Philippe —
  mais il vit hors du dépôt, donc il **ne suit pas** un changement de machine.
