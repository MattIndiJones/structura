# Post-mortem — réconciliation P&L FIFO vs NAV, CH1352587724 (16 juillet 2026)

Point de départ : le P&L FIFO brut ne retombait pas sur le P&L implicite du NAV publié
(écart ~48.7% en début de journée, monté jusqu'à 53% en cours de route avec le growth topup,
redescendu à 21.4% en fin de session avec le fix de pricing par date de déficit). Ce document
raconte ce qui a été tenté, ce qui a marché, ce qui a été défait, et ce qui reste ouvert —
pour ne pas repartir de zéro sur le prochain AMC.

Complète [PORTFOLIO_RECONCILIATION_LESSONS.md](PORTFOLIO_RECONCILIATION_LESSONS.md) — écrit
**dans cette même session, avant sa compaction** — plutôt que de le remplacer. Son §9 contient
une leçon qui aurait dû être relue avant de recommencer une bonne partie du travail de ce
post-mortem (voir §6 ci-dessous) : à lire en premier la prochaine fois.

## Checklist rapide pour le prochain AMC

- [ ] **Relire d'abord `PORTFOLIO_RECONCILIATION_LESSONS.md` en entier** (et ce document en
      entier) avant de recommencer une investigation sur ce fonds ou un fonds similaire — une
      bonne partie du §6 ci-dessous n'aurait pas été nécessaire sinon
- [ ] Si des positions ont un déficit ("excess sell"), regarder d'abord si leur date correspond
      à un jour où **beaucoup de titres sont tradés en même temps** (rebalancement massif) — voir §3
- [ ] Dater et pricer toute injection synthétique à la **date réelle du déficit**, jamais à la
      date T0 / première date de trading du titre — voir §2 (gain le plus solide de la session)
- [ ] Ne pas construire de mécanisme "l'encours du fonds grossit donc on rachète tout
      proportionnellement" sans vérifier son effet sur la réconciliation NAV — voir §1 (a coûté
      une demi-journée pour un résultat négatif)
- [ ] Vérifier le mapping ticker (`backend/data/underlying_prices/_ticker_map.json`) pour toute
      valeur `<TICKER>.<SUFFIXE_PAYS>` suspecte, en particulier sur les ISIN à double cotation
      (Canada, entre autres) — voir §4
- [ ] Une réconciliation qui semble excellente n'est pas forcément saine — vérifier l'absence de
      positions ouvertes négatives et d'injections synthétiques en échec avant d'y faire confiance
      (leçon §9 de `PORTFOLIO_RECONCILIATION_LESSONS.md`, reconfirmée ici — voir §6)
- [ ] Une étude sauvegardée en base (`amc_studies` dans `structura.db`) est une référence utile
      mais seulement si on peut confirmer que les **mêmes données de prix** l'ont produite — voir §6

---

## 1. Le mécanisme de "croissance d'encours" (growth topup) — construit, testé, défait

**Hypothèse de départ** : plusieurs titres du termsheet initial (Marathon Digital, Nvidia,
Coinbase...) montraient un déficit ("excess sell") alors que le panier T0 était censé les
couvrir. Le fonds a vu son encours croître fortement après la date de fixing (26 932 →
pic ~35 606 certificats), et le panier T0 statique ne suit pas cette croissance.

**Ce qui a été construit** : `build_growth_topups()` dans `backend/app/core/fifo/nav.py` —
à chaque hausse détectée de l'encours (`Outstanding quantity` dans le CSV NAV), rachat
proportionnel de **toute position ouverte à cette date**, pas seulement les 18 lignes du
termsheet. Généralisé après une remarque : "si le panier initial a une dynamique d'encours
croissant, c'est forcément le cas du panier à toutes les dates, pas que le panier de départ."

**Effet mesuré** : réduit les injections synthétiques de 42 à 11 sur ce fonds (bon signal
visuel), mais ajoute ~1100 ordres d'achat fictifs qui gonflent le P&L total de ~395k USD
(surtout latent, +360k) pour ne corriger que 13k de P&L réellement dû à un vrai déficit.
Conséquence : l'écart de réconciliation NAV **empire** (48.7% → 53%), pas l'inverse — la
valeur de marché des positions ouvertes dépasse déjà l'AUM réel de 41% sans le mécanisme,
et de 78% avec.

**Pourquoi ça ne marche pas** : le mécanisme suppose implicitement que "l'encours grossit"
= "chaque position existante grossit proportionnellement". Mais la vraie cause des déficits
(voir §3) est un problème d'export de données sur les jours de rebalancement massif, pas une
dynamique de croissance de position. Le growth topup soigne donc le mauvais diagnostic.

**Décision finale** : désactivé (`topup_orders = []` dans `pipeline.py`). Le code de
`build_growth_topups()` reste dans `nav.py`, testé et fonctionnel, au cas où il redevienne
pertinent une fois le vrai problème (§3) mieux compris — mais ne pas le réactiver sans
revérifier son effet sur la réconciliation NAV globale, pas seulement sur le nombre
d'injections visibles.

---

## 2. Dater/pricer l'injection synthétique à la date du déficit — le vrai gain

**Bug trouvé** : `engine.py::_inject_synthetic()` datait et pricait toute injection
synthétique à la date de la **première commande jamais passée sur ce titre** (`isin_orders[0].date`),
peu importe quand le déficit réel s'est produit. Pour un titre du termsheet, ça veut dire
T0 (date de fixing du fonds) — souvent 1 à 2 ans avant le vrai événement.

**Correction appliquée** : le déficit est maintenant daté et prické à la date de la vente qui
l'a révélé (`order.date`, la vente qui dépasse les lots disponibles) — un vrai prix de marché
pour ce jour précis, récupéré via une passe de détection préalable puis un fetch de prix
`build_marks()` par date exacte de déficit (`deficit_prices_prod` dans `engine.reconstruct()`).

**Effet mesuré** : écart de réconciliation NAV **53% → 21.4%**, meilleur résultat de la
session. Sur le fonds de test, ligne par ligne, l'effet n'est pas uniforme — certaines
lignes s'améliorent énormément (Swissquote : -425.4k → +57.0k, écart de +482k), d'autres se
dégradent (CrowdStrike : +150.9k → +9.3k). La raison : changer la date d'un lot synthétique
change son ordre de consommation FIFO, ce qui redistribue quels lots réels restent "ouverts"
en fin de parcours — un effet de cascade à anticiper, pas un simple ajustement local.

**Pourquoi ça marche mieux** : sur un portefeuille qui a globalement monté sur la période,
dater systématiquement les injections synthétiques à une date ancienne (T0) surestimait
mécaniquement le P&L (achat "fictif" à bas prix ancien, jamais vendu, valorisé au prix
d'aujourd'hui). Le biais allait toujours dans le même sens — optimiste.

**Implication plus large, non vérifiée** : ce bug de pricing existait dans le code AVANT
cette session (pas introduit aujourd'hui). Toute étude générée avec l'ancien comportement,
pour n'importe quel fonds, a potentiellement un P&L surestimé de façon systématique. À
vérifier si des études déjà livrées à des clients datent d'avant ce fix.

---

## 3. Les déficits corrèlent avec les jours de rebalancement massif

**Découverte** : sur CH1352587724, toutes les dates de déficit identifiées cette session
(Marathon Digital, Amazon, Cadence ×3, Snowflake, CrowdStrike, Fortinet, ASML, Alibaba,
Lasertec, Broadcom, Core Scientific, Zeta Global...) tombent sur des jours où **10 à 27
titres différents sont tradés le même jour** — des rebalancements massifs du portefeuille,
pas des jours de trading isolé (1-3 titres).

**Méthode pour la retrouver rapidement** : grouper les ordres du carnet par date, compter
le nombre d'ISIN distincts par jour, et croiser avec les dates de `synthetic_report`
(`si.t0_date` après le fix du §2, qui donne maintenant la vraie date du déficit).

**Interprétation** : ce n'est pas un problème de saisie éparpillé au hasard — c'est
spécifiquement l'export/l'extraction des opérations de rebalancement massif côté plateforme
qui perd des jambes individuelles. Sur 19 jours de rebalancement massif identifiés, 6 ont
montré un ou plusieurs déficits (parfois 4 titres touchés le même jour), 12 n'en ont montré
aucun — donc pas systématique à 100%, mais clairement concentré sur ces jours-là.

**Piste non aboutie** : 81 ordres au statut `"Discarded"` dans le JSON brut, dont 79 sont des
stubs à quantité nulle (probablement des évaluations de rebalancement n'ayant donné lieu à
aucune action) et 2 ont une quantité et un prix réels (TeraWulf -4744, Swissquote -91) mais
un `usedFxRate: null` — signe que ces deux ordres n'ont jamais fini leur pipeline de
règlement/FX. Testé en les incluant manuellement (sans toucher au code) : résout proprement
TeraWulf (4277 fantômes → -467, déficit raisonnable), mais dégrade Swissquote (cascade de 6
nouveaux déficits ailleurs dans son historique, une fois son facteur de split ~10:1 appliqué
à cet ordre). Conclusion : ce n'est pas un pattern généralisable, à traiter au cas par cas si
besoin, pas en réintégrant tous les ordres "Discarded" à quantité non nulle par défaut.

---

## 4. Bugs réels de mapping ticker/devise trouvés et corrigés

Le fichier `backend/data/underlying_prices/_ticker_map.json` mappe un ISIN vers un ticker
Yahoo Finance. Trouvé 4 mappings faux sur ce fonds, tous corrigés (via `fetch_prices()`,
qui met à jour le mapping et régénère le parquet) :

| ISIN | Faux ticker (avant) | Bon ticker (après) | Symptôme |
|---|---|---|---|
| CA15101Q2071 (Celestica) | `CLS.TO` (Toronto, CAD) | `CLS` (NYSE, USD) | Score de timing (Bloc H) à 0.000 artificiel |
| CA13321L1085 (Cameco) | `CCO.TO` (Toronto, CAD) | `CCJ` (NYSE, USD) | Trouvé par audit systématique, pas encore vu en symptôme visible |
| US02079K3059 (Alphabet Cl. A) | `GOOA.VI` (Vienne, EUR) | `GOOGL` (Nasdaq, USD) | Idem |
| US48138M1053 (Jumia) | `4JMA.SG` (Stuttgart, EUR) | `JMIA` (NYSE, USD) | Idem |

**Méthode pour les retrouver systématiquement** : pour chaque ISIN ayant un ordre dans le
carnet, comparer la devise déclarée par yfinance (`Ticker(x).fast_info["currency"]`) à la
devise déclarée par le carnet lui-même (`price_ccy` sur les ordres). Un mismatch de devise
est un signal quasi certain de mauvais ticker — pas la peine de regarder le ratio de prix
(souvent trompeur à cause de mouvements de marché légitimes sur 1-2 ans).

**Effet sur la réconciliation globale** : marginal — ces 4 corrections n'ont quasiment pas
bougé le ratio de surestimation de l'AUM (1.413 avant/après). Utile pour la justesse
individuelle des blocs (Timing Score notamment), pas un levier pour le problème principal.

**Cas à part — CyberArk (IL0011334468, ticker CYBR)** : ticker qui renvoie une erreur
yfinance ("possibly delisted"). Ce n'est pas un mauvais mapping — CyberArk a été **racheté
par Palo Alto Networks**, le ticker est réellement délisté. Pas de fix possible côté mapping ;
si besoin de continuer à suivre ce nom, il faudra une source de prix alternative ou accepter
l'absence de mark après la date d'acquisition.

---

## 5. Positions "fantômes" jamais fermées — pas résolu

Comparaison entre le FIFO reconstruit (61 positions ouvertes) et le fichier de composition
officiel de l'émetteur (`CH1352587724 Def.txt`, 20 positions listées) : 41 titres montrent
une position FIFO non nulle alors qu'ils sont absents du fichier officiel (interprété comme
"le fonds ne les détient plus"). Contrairement aux déficits du §3, ces positions ne
déclenchent jamais d'injection synthétique — leur solde reste toujours positif, donc rien ne
signale qu'elles devraient être closes.

**Attention** : la fiabilité de `Def.txt` a été mise en doute en cours de session ("on avait
constaté des erreurs dedans... sur les qty"), puis cette réserve a été explicitement levée
par la suite. Le poids total du fichier ne somme qu'à 96.2%, pas 100% — signe que ce fichier
n'est peut-être pas exhaustif sur les petites positions, à garder en tête avant de le traiter
comme vérité absolue.

**Vérifié** : ce ne sont pas des positions synthétiques (100% de lots `source=carnet`), et la
plupart ont eu de vraies ventes (pas juste "achats jamais revendus") — le carnet a juste
« oublié » la vente de clôture finale. Ni un bug de chargeur (`load_orders` filtre
correctement, testé et confirmé par l'utilisateur), ni un doublon d'ISIN (vérifié, aucun nom
de cette liste n'a de second ISIN dans le carnet).

**Piste à explorer la prochaine fois** : pour chaque position "fantôme", vérifier si sa
dernière date de trading tombe sur un jour de rebalancement massif (comme au §3) — testé sur
TeraWulf et Swissquote, qui ne corrèlent PAS avec ce pattern (3 ordres seulement le jour de
leur dernier trade), donc probablement une catégorie de problème différente des déficits.

---

## 6. La chasse au -3.2% était une fausse piste — déjà documentée avant ce post-mortem

Une étude enregistrée en base (`structura.db`, table `amc_studies`, id=3, sauvegardée le
2026-07-04) montrait un écart de réconciliation quasi parfait (**-3.2%**, P&L brut ≈ 1.6M
USD). Une bonne partie de la fin de cette session a été passée à essayer de reproduire ce
chiffre avec les données et le code actuels (testé et écarté : `n_certs: 75000` du manifest
sauvegardé — sert uniquement au Bloc E, jamais transmis au FIFO ; termsheet embarqué
identique au fichier actuel, comparé champ par champ ; retour à l'ancien comportement "date
globale unique pour l'injection synthétique" — ne reproduit pas non plus le -3.2%, donne
38.8%).

**Erreur méthodologique** : cette chasse n'aurait pas dû avoir lieu. `PORTFOLIO_RECONCILIATION_LESSONS.md`
§9 — écrit **plus tôt dans cette même session, avant sa compaction** — documente déjà que ce
-3.2% ne reposait pas sur une bonne reconstruction : la correction de split pour ServiceNow
et Carvana était incomplète à l'époque, produisant des positions ouvertes **négatives**
(-854 ServiceNow, -1530 Carvana — impossible pour un fonds long-only), masquées par des
injections synthétiques elles-mêmes dérivées de cette même source ambiguë. Une fois la
correction réellement complète, le total FIFO passe de 1.60M à 1.94M — un écart de **+23%**,
pas -3.2%. Le -3.2% n'était donc pas une cible valide à reproduire, quelle que soit la piste
suivie ensuite (prix yfinance qui bougent ou autre) — la bonne explication était déjà écrite
et n'a simplement pas été relue avant de repartir en investigation.

**Leçon (celle du §9, qu'il fallait relire avant de recommencer)** : un chiffre qui recoupe
bien une vérité indépendante (ici la NAV) n'est pas automatiquement le bon chiffre — vérifier
que la reconstruction elle-même est saine (positions ouvertes non-négatives, pas d'injection
synthétique en échec) avant de faire confiance à la proximité du résultat final.

**Leçon nouvelle, propre à aujourd'hui** : avant de lancer une investigation sur "pourquoi
ne puis-je pas reproduire ce chiffre passé", relire d'abord les MD de leçons existants sur
le même sujet — la réponse peut déjà y être. Le fix de pricing par date de déficit (§2)
reste valide et améliore la situation par rapport au +23% documenté au §9 (test du jour :
21.4%), donc le travail d'aujourd'hui n'est pas perdu — mais la comparaison correcte est
**23% → 21.4%**, pas **-3.2% → 21.4%** (ce qui aurait semblé être une régression).

---

## Résumé pour le prochain AMC

1. Commencer par vérifier les mappings ticker/devise (§4) — rapide, peu coûteux, corrige des
   bugs réels même s'ils ne sont pas le principal contributeur au problème.
2. Le fix de pricing par date de déficit (§2) est un gain solide et généralisable — déjà en
   place dans `engine.py`/`pipeline.py`, s'applique à tout fonds sans configuration
   supplémentaire.
3. Avant de construire un nouveau mécanisme correctif (comme le growth topup, §1), toujours
   mesurer son effet sur la réconciliation NAV globale, pas seulement sur des indicateurs
   cosmétiques (nombre d'injections visibles dans un panneau de debug).
4. Si des déficits subsistent, chercher d'abord une corrélation avec des jours de
   rebalancement massif (§3) avant de suspecter un bug de modélisation.
5. **Relire les MD de leçons existants avant de relancer une investigation** — le -3.2%
   poursuivi en fin de session était déjà documenté comme invalide plus tôt dans la même
   conversation (§6, §9 de `PORTFOLIO_RECONCILIATION_LESSONS.md`). La vraie référence pour
   juger le fix du §2 est +23% (post-split-fix, §9), pas -3.2%.
