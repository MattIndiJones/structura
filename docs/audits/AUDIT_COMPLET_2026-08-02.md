# Rapport d'audit complet — STRUCTURA

**Date de l'audit :** 2 août 2026
**Révision examinée :** `4167eeb` (« feat: securiser les fixings et le lifecycle »),
branche `feat/client-test-agent`, **worktree non propre** — 27 fichiers modifiés,
3 fichiers backend non suivis, 2 331 insertions non commitées côté backend.
**Périmètre :** moteur de pricing et modèles, PayScript, payoffs, Greeks, lifecycle,
Mark-to-Future, dates et fixings, données de marché, VaR et risque, KID/PRIIPs, RFQ et
workflow, **cloisonnement des données, piste d'audit et surface d'authentification**.
**Hors périmètre :** AMC et INDEX_STUDIO (exclusion demandée), performance et
scalabilité, style de code.
**Mode opératoire :** audit en lecture seule. Aucun fichier du dépôt n'a été modifié,
aucun serveur lancé, `backend/data/structura.db` jamais ouvert en écriture. Les
conclusions reposent sur **10 sondes exécutables** écrites hors dépôt, comprenant des
références analytiques fermées, des appels directs aux handlers d'API sur base SQLite
en mémoire, et une analyse statique de la couche d'autorisation.

**Relation aux rapports précédents.** Ce document succède à
`AUDIT_QUANTITATIF_2026-08-01.md`. Il ne le réécrit pas. Il fait trois choses :
il **rejoue numériquement ses vingt findings** sur le code d'aujourd'hui — car
`engine.py`, `parser.py`, `var_engine.py` et `deals.py` ont été modifiés **après** sa
rédaction (22 h 19 contre 19 h 36) ; il **ouvre le volet intégrité applicative** que les
audits quantitatifs n'avaient pas couvert ; et il chiffre ce qui restait qualitatif.

---

## 1. Résumé exécutif

### Verdict

**La vague de correction de la nuit du 1er au 2 août est réelle et vérifiée.**
Sur les vingt findings du 1er août, **onze sont fermés**, deux sont ramenés au rang de
défaut divulgué, sept restent ouverts. Deux des cinq bloquants critiques ont disparu, et
l'un des deux — la convexité Hull-White — passe de **+164,1 bp à +0,47 bp**, soit un
facteur 350. La robustesse d'entrée du moteur, qui était le point faible structurel
(modèle inconnu accepté, corrélation réparée en silence, `BASKET` divisant par deux),
est aujourd'hui la partie la mieux tenue.

**Mais l'audit ouvre un front qui n'avait jamais été sondé, et il est plus grave que ce
qui reste côté quant.** Le secret de signature JWT est écrit en dur dans
`backend/app/api/auth.py`, versionné dans git, sans surcharge par variable
d'environnement. Quiconque dispose du dépôt peut forger un jeton valide pour n'importe
quel utilisateur, administrateur compris, sans mot de passe. C'est démontré en trois
lignes en §6.1. Tant que l'application tourne sur le poste de Philippe derrière
`127.0.0.1`, l'exposition est nulle ; le jour où elle est servie à un tiers, elle est
totale.

Le contraste mérite d'être dit clairement : **le cloisonnement métier est bien conçu**
— 58 routes vérifiées, aucune fuite inter-utilisateur ni inter-entité, piste d'audit
strictement append-only, maker-checker couvert par 48 tests dédiés — **mais il repose
sur une identité que rien ne protège**.

### Ce qui reste bloquant, par ordre de gravité

1. **secret JWT en dur et versionné** — usurpation d'identité administrateur (nouveau) ;
2. les horizons intermédiaires du KID **déclenchent la maturité** du produit (QNT-105) ;
3. un **FX manquant vaut 1,0** en silence — +8,7 % sur un nominal USD, ×164 sur du JPY ;
4. le **backward fill** injecte de l'information future dans tout replay historique ;
5. le monitoring « continu » price une barrière proche **14,3 % trop bas** (QNT-101) ;
6. la corrélation taux/actions **contamine** la corrélation actions : **+7,6 points** de
   prix sur un worst-of à `rho_rS` = 0,9 (QNT-113) ;
7. l'IRR renvoie `None` sur une perte totale, et la fenêtre **disparaît** des
   statistiques de backtest (QNT-120).

### Zone utilisable aujourd'hui

Le moteur peut servir de **calcul indicatif contrôlé**, sur un poste local
mono-utilisateur, lorsque toutes ces conditions sont réunies : monitoring de barrière
**discret** ; pas de KID réglementaire ; portefeuille **mono-devise EUR**, ou FX vérifié
à la main ; pas de backtest historique comme argument de vente ; pas de VaR comme limite
officielle ; taux stochastiques désormais **admis** (la convexité est corrigée) ;
Mark-to-Future désormais **admis** sur produit rappelable (la reprise d'état est
corrigée et vérifiée) ; contrôle indépendant du résultat.

### Notation

| Domaine | Note /10 | 01/08 | Appréciation |
|---|---:|---:|---|
| Exactitude des payoffs | 7,0 | 6,0 | Pièges DSL fermés (`BASKET`, `S[0]`, `PAY PARAM()`) ; ambiguïtés de templates intactes |
| Qualité du Monte Carlo | 7,5 | 6,5 | Hull-White exact à 0,5 bp ; pont brownien et grille hebdo ouverts |
| Exactitude des Greeks | 6,5 | 6,5 | Stateful et validés ; vega Heston étiqueté mais non corrigé |
| Gestion des dates | 4,0 | 4,0 | Inchangé : grilles 52/252, calendriers absents, quantification hebdomadaire |
| Qualité des données | 3,5 | 3,5 | Flux non ajusté ajouté pour les fixings ; `bfill` et FX = 1 intacts |
| Robustesse numérique | 7,5 | 3,5 | Validation de modèle, de paramètres et de corrélation : le progrès le plus net |
| Qualité des backtests | 3,0 | 3,0 | Biais de sélection IRR et look-ahead non traités |
| Conformité réglementaire | 2,5 | 2,5 | Horizons KID toujours faux |
| Couverture des tests | 6,0 | 6,5 | 516 tests (+21), mais **zéro test d'intégration de la couche API/auth** |
| Maintenabilité quantitative | 4,5 | 4,5 | `deals.py` à 6 339 lignes, en croissance de 1 277 lignes |
| **Note quantitative globale** | **5,4** | **4,8** | **Noyau pré-trade consolidé ; modules aval encore hors production** |
| Cloisonnement et piste d'audit | 7,5 | — | Nouveau volet : bien conçu, testé, sans fuite détectée |
| Sécurité d'authentification | **1,5** | — | Nouveau volet : secret en dur, CORS ouvert, aucun durcissement |
| **Aptitude à un usage multi-utilisateur** | **2,0** | — | **NO-GO tant que le secret n'est pas externalisé** |

### Verdict par usage

| Usage | Verdict | Motif déterminant |
|---|---|---|
| Prix indicatif pré-trade, GBM, monitoring discret | **GO sous contrôle** | Validé analytiquement ; entrées désormais validées |
| Taux stochastiques | **GO** *(nouveau)* | Convexité corrigée, 0,47 bp sur un ZC 5 ans |
| Mark-to-Future sur produit rappelable | **GO sous contrôle** *(nouveau)* | Reprise d'état corrigée et vérifiée ; monitoring continu refusé explicitement |
| Prix officiel / valorisation client | **NO-GO** | Dates contractuelles, pont brownien, quantification hebdomadaire |
| Mesure de risque portefeuille, VaR | **NO-GO** | FX manquant silencieusement à parité |
| KID PRIIPs | **NO-GO** | Horizons intermédiaires valorisés comme une maturité |
| Backtest historique | **NO-GO** | Backward fill et exclusion des fenêtres en perte totale |
| Déploiement hors poste local | **NO-GO** | Secret JWT en dur et versionné |

---

## 2. Méthode et preuves

### 2.1 Sondes exécutées

| # | Sonde | Objet |
|---|---|---|
| 1 | `p1_critiques.py` | Pont brownien vs Merton ; ZC Hull-White ; vega Heston vs GBM |
| 2 | `p2_mtf_kid.py` / `p2b_mtf.py` | MTF d'un autocall rappelé ; horizons KID ; MTF d'un ZC (contrôle) |
| 3 | `p3_eleves.py` | Corrélations, DSL, validation de modèle, corrélation taux/actions, VaR/ES |
| 4 | `p4_invariants.py` | Martingalité 5 modèles, parité call-put, convergence, vol locale, grilles |
| 5 | `p5_irr_grille.py` | IRR sur cas dégénérés ; divergence des grilles temporelles |
| 6 | `p6_cloisonnement.py` | Analyse statique : 58 routes récupérant un objet possédé par identifiant |
| 7 | `p7_cloisonnement_dyn.py` | Appel direct des handlers avec 6 acteurs (propriétaire, pair, entité tierce, ops, checker, admin) |
| 8 | `p8_securite.py` | Secret JWT et forge de jeton, politique de session, CORS, immutabilité de la piste d'audit |
| 9 | `p9_donnees.py` | Look-ahead par `bfill` ; FX manquant à parité |
| 10 | `p10_liste.py` | Portée réelle de `GET /deals` pour 6 acteurs sur 3 propriétaires |

Toutes les sondes ont tourné sur l'interpréteur du projet (`.venv`), contre le code du
worktree, sans modification du dépôt.

### 2.2 Suite de tests

```
516 passed in 147.38s
```

contre 495 collectés le 1er août : **21 tests ajoutés** par la vague de correction. La
suite est verte en intégralité. Ce fait n'est pas une preuve de justesse — la totalité
des défauts listés ci-dessous coexiste avec une suite verte — mais l'absence de
régression sur le harnais golden de bit-identité indique que les corrections n'ont pas
déplacé les prix de référence.

### 2.3 Limites

Les sondes portent sur les fonctions de domaine et les handlers appelés directement.
Elles ne couvrent pas la couche HTTP réelle (middlewares, sérialisation, dépendances
FastAPI) ni le frontend, faute de pouvoir démarrer l'instance de Philippe. La
configuration CORS a donc été testée sur une application jetable portant la **même
déclaration de middleware**, pas sur `main.py` lui-même.

---

## 3. État des findings du 1er août

Rejoués un par un. « Fermé » signifie que la sonde qui le démontrait ne le reproduit
plus, pas que le diff le prétend.

### 3.1 Les cinq bloquants critiques

| ID | Titre | Statut | Preuve mesurée aujourd'hui |
|---|---|---|---|
| QNT-101 | Pont brownien −14 % sur barrière proche | **ouvert, divulgué** | 0,044237 contre 0,051611 (Merton exact) à N = 400 000 : **−73,74 bp, soit −14,29 %**. Inchangé au centième près. Le résultat expose désormais `barrier_monitoring_note` décrivant le biais. |
| QNT-102 | MTF marquant un produit mort | **fermé** | Après rappel : `mark = 0,000`, `terminated_pct = 100,00`, cash versé reporté séparément. Contrôle sur ZC 2 ans : marks à **±3 bp** de l'actualisation exacte. |
| QNT-103 | Vega Heston × (1 − ρ²) | **ouvert, étiqueté** | Ratio au vega GBM : 0,965 / 0,877 / **0,488** / 0,181 / 0,019 pour ρ_h = 0 / −0,3 / −0,7 / −0,9 / −0,99. La loi (1 − ρ²) est intacte. `compute_greeks` expose `vega_scope = {"type": "leg_independante", "coverage": {"S1": 0.51}}`. |
| QNT-104 | Hull-White sans convexité | **fermé** | ZC 5 ans, courbe plate 3 %, exact 0,860708 : **+0,05 / +0,21 / +0,47 bp** à σ_r = 1 / 2 / 3 % (contre +18,1 / +72,6 / **+164,1 bp**). Vérifié aussi à `a_r` = 0,05 : ≤ +0,37 bp. |
| QNT-105 | Horizons KID déclenchant la maturité | **ouvert** | Autocall 5 ans à l'horizon 1 an : **prix 1,0000, payoff médian 1,0000, 100 % de payoffs non nuls**, dont 50,2 % issus du bloc `AT MATURITY`. Le prix n'est toujours pas monotone en horizon (1,0000 / 0,9654 / 0,9502). |

### 3.2 Les findings de sévérité élevée

| ID | Statut | Preuve mesurée aujourd'hui |
|---|---|---|
| QNT-106 réparation silencieuse des corrélations | **fermé** | Matrice 3×3 à ρ = −0,9 : `ValueError` métier explicite (« la projection la plus proche déplace un coefficient de … »). Plus de prix silencieux. |
| QNT-107 matrice PSD singulière | **fermé** | `[[1,1],[1,1]]` renvoie une Cholesky (2, 2) valide. Le test est passé de `< 0` à `< 1e-10`. |
| QNT-108 `BASKET` diluant | **fermé** | `BASKET(0.5,0.5)` sur un actif : erreur métier « 2 poids pour 1 sous-jacent ». `BASKET()` sur 3 actifs : 1,000019. |
| QNT-109 `S[0]` pointant le dernier actif | **fermé** | `S[0]` et `S[4]` sur un panier de 3 : « indice hors bornes ». `S[3]` : 1,000052. |
| QNT-110 `PAY` d'un `PARAM()` tableau | **fermé** | Prix 1,060000 — exact (2 coupons de 3 % + capital, r = 0). Plus de `TypeError`. |
| QNT-111 modèle inconnu → GBM | **fermé** | « Modèle inconnu : 'modele_inexistant' — valeurs admises : constant, heston, sabr, localvol, lsv. » |
| QNT-112 paramètres Heston non validés | **fermé** | `xi=0`, `rho_h=-1,5`, `kappa=-2`, `v0=-0,04`, `beta=1,5` : tous refusés par message métier nommant le paramètre et le domaine attendu. |
| QNT-113 corrélation taux/actions contaminante | **ouvert** | Worst-of 3 actifs, ρ_actions = 0,30 fixe : **0,862947 → 0,880808 → 0,939192** pour ρ_rS = 0 / 0,5 / 0,9. **+7,6 points de prix** sur un paramètre présenté comme sans rapport avec la dépendance actions. |
| QNT-114 horizon étendu silencieusement | **ouvert** | `effective_T_max(script à observation en t=3, T demandé = 1,0)` = **3,0**. |
| QNT-115 quantification hebdomadaire | **ouvert** | ZC à 0 jour = **0,999423** (−5,77 bp) ; 1 j, 5 j et 10 j donnent **la même valeur**. À 91 j et 365 j : exact au centième de bp. |
| QNT-116 VaR/ES incluant une observation de trop | **fermé** | n = 100, pertes 1..100 : VaR 95 % = **96,0** (5ᵉ pire, exact), ES = **98,0** (moyenne des 5 pires, exact). |
| QNT-117 deux définitions du quantile | **ouvert, documenté** | `var_eur` = 96,0 et `distribution_summary.p5` = −95,05 cohabitent toujours dans le même payload. Le champ `n_tail` (= 5,0) rend désormais explicite l'épaisseur de la queue. |
| QNT-118 surface de vol locale saturée | **ouvert** | Grille 52 × 50, plafond 1,5 : **9,1 % des cellules au plafond**, 12,3 % au-dessus de 1,0. Sur mon jeu de paramètres (skew −0,08, courbure 0,03) le smile à 1 an reste monotone — le retournement signalé le 1er août dépend des paramètres de smile, il n'est pas systématique. |
| QNT-119 grilles temporelles divergentes | **ouvert** | Résolution MC 7,02 j/pas contre replay 1,45 j/ligne. Pour une même date contractuelle : **jusqu'à 2,23 jours d'écart** (t = 1,7 an → 1,6923 en MC, 1,6984 en replay). |
| QNT-120 IRR à point de départ unique | **ouvert** | Perte quasi totale (−100, +0,01) et **perte totale (−100, 0)** renvoient toutes deux `None` : ces fenêtres sont **exclues** des statistiques. Les cas sains sont exacts à 1e-13. |

**Bilan : 11 fermés, 2 ouverts mais divulgués dans le résultat, 7 ouverts.**

---

## 4. Invariants fondamentaux — état des lieux

Aucun de ces contrôles n'est en échec. Ils sont reportés parce qu'un audit qui ne dit
que ce qui ne va pas ne permet pas de décider.

### 4.1 Martingalité — `E[S_T·e^{−rT}] = S₀·e^{−qT}`

r = 3 %, q = 2 %, T = 1 an, N = 200 000, référence 0,980199 :

| Modèle | Prix | Biais |
|---|---:|---:|
| constant | 0,980213 | +0,14 bp |
| heston | 0,980105 | −0,94 bp |
| sabr | 0,980105 | −0,94 bp |
| localvol | 0,980191 | −0,08 bp |
| lsv | 0,980024 | **−1,75 bp** |

Les cinq modèles tiennent sous 2 bp. LSV est le moins bon, ce qui est attendu d'une
méthode particulaire.

### 4.2 Parité call-put — `C − P = S₀·e^{−qT} − K·e^{−rT}`

Écarts de +0,15 / −0,93 / −0,93 / −0,08 / −1,74 bp sur les cinq modèles. Ils
**reproduisent exactement les biais de martingalité**, ce qui est le comportement
correct : l'erreur est dans la diffusion, pas dans l'évaluation du payoff.

### 4.3 Convergence

Call ATM contre Black-Scholes :

| N | Erreur |
|---:|---:|
| 12 500 | 10,32 bp |
| 50 000 | 1,87 bp |
| 200 000 | 0,50 bp |
| 800 000 | **0,16 bp** |

Décroissance conforme, meilleure que 1/√N sur cette réalisation de graine.

---

## 5. Findings nouveaux — quantitatif

### QNT-201 — Le FX manquant vaut 1,0, en silence

**Catégorie :** risque / données
**Statut :** confirmé
**Sévérité :** critique
**Fichier :** `backend/app/api/portfolios.py`, lignes **164**, **309**, **455**

**Code en cause.** `fx_rate = float(fx.iloc[-1]) if not fx.empty else 1.0`

**Comportement observé.** Une série de change indisponible — ticker FX absent du cache,
Yahoo en échec, devise exotique — fait retenir la parité. Le taux multiplie ensuite le
nominal en EUR, les poids du portefeuille, les Greeks agrégés et la VaR.

| Paire | Cours réaliste | Retenu si absent | Erreur sur 1 M de nominal |
|---|---:|---:|---:|
| USD/EUR | 0,9200 | 1,0000 | +80 000 EUR (**+8,7 %**) |
| CHF/EUR | 1,0700 | 1,0000 | −70 000 EUR (−6,5 %) |
| GBP/EUR | 1,1900 | 1,0000 | −190 000 EUR (**−16,0 %**) |
| JPY/EUR | 0,0061 | 1,0000 | +993 900 EUR (**×164**) |

**Comportement attendu.** Une position dont la devise n'est pas convertible doit être
signalée et exclue de l'agrégation, pas convertie à un taux inventé.

**Impact.** Un portefeuille multi-devises s'affiche normalement, sans aucun signal, avec
une exposition fausse. Sur du JPY l'erreur est de deux ordres de grandeur.
**Correction recommandée.** Lever, ou porter la position dans une ligne « non
convertible » explicite avec un total partiel. Jamais de valeur par défaut.
**Test à ajouter.** Portefeuille à deux lignes dont une en devise sans série FX :
vérifier que le total refuse de se calculer silencieusement.

### QNT-202 — Le backward fill injecte de l'information future

**Catégorie :** données / backtest
**Statut :** confirmé
**Sévérité :** élevée
**Fichier :** `backend/app/services/market_data.py`, ligne **130**

**Code en cause.** `prices = pd.DataFrame(price_series).dropna(how="all").ffill().bfill()`

**Comportement observé.** Reproduction sur deux séries dont l'une démarre au 6ᵉ jour
(introduction, changement de ticker, suspension de cotation). Les cinq premiers jours du
titre récent reçoivent **50,00** — son premier cours connu, recopié en arrière sur des
dates où il n'existait pas.

Conséquence mesurée sur la volatilité : 4 rendements réellement observables (σ = 0,0614)
deviennent 9 rendements (σ = 0,0480), dont **5 rendements nuls fabriqués** — soit une
volatilité **sous-estimée de 21,8 %**.

**Impact sur les barrières.** Un titre dont le premier cours connu est au-dessus de la
barrière ne la franchira jamais sur la période antérieure, quel qu'ait été son parcours
réel. Le backtest d'un produit à barrière est donc biaisé **en faveur du produit**.

**Nuance importante.** Le flux `load_yahoo_reference_closes` ajouté par la vague de
correction (ligne 147) est **exempt** du défaut : `auto_adjust=False`, aucun remplissage
inter-tickers, splits conservés. La séparation fixings contractuels / séries indicatives
est donc acquise. Le défaut ne subsiste que sur `load_hist_prices` (ligne 107), qui
alimente le replay et les backtests, et sur `load_hist_vol` (ligne 20).
**Correction recommandée.** Supprimer `.bfill()` ; démarrer chaque série à sa première
cotation réelle et journaliser les exclusions.

### QNT-203 — Aucun test d'intégration sur la couche API

**Catégorie :** couverture
**Statut :** confirmé
**Sévérité :** moyenne

Sur 516 tests, **aucun n'instancie de client HTTP** : `TestClient` n'apparaît nulle part
dans `backend/tests/`. La suite teste les fonctions de domaine directement, ce qui est
un choix défendable et explicitement assumé dans l'en-tête de
`test_workflow_controls.py`. La conséquence est que rien ne couvre l'authentification,
l'expiration de jeton, la résolution de rôle, l'ordre de déclaration des routes
(`/watchlist` contre `/{deal_id}` — piège signalé deux fois en commentaire), la
sérialisation ni les dépendances FastAPI. Ce sont précisément les couches où se logent
les défauts trouvés en §6.

---

## 6. Findings nouveaux — intégrité applicative

### SEC-101 — Le secret de signature JWT est en dur et versionné

**Catégorie :** authentification
**Statut :** confirmé
**Sévérité :** critique
**Fichier :** `backend/app/api/auth.py`, ligne **14**

**Code en cause.**

```python
_SECRET = "structura-jwt-secret-change-in-prod"
_ALGO = "HS256"
_EXPIRE_DAYS = 7
```

**Comportement observé.** Le fichier est suivi par git (`4167eeb`). Aucune surcharge par
variable d'environnement n'existe : ni `STRUCTURA_SECRET`, ni `JWT_SECRET`, ni
`SECRET_KEY` ne sont lus. Le commentaire « change-in-prod » n'est appliqué nulle part.

Sonde : un jeton forgé avec ce secret pour `sub = "1"`, `role = "admin"`, expirant dans
365 jours, est décodé sans erreur par la même clé que le serveur. `get_current_user`
(ligne 39) ne fait ensuite que vérifier la signature puis `session.get(User, sub)` —
il n'existe aucun second facteur, aucune liste de jetons émis, aucune vérification
d'émission.

**Conséquence.** Toute personne disposant d'une copie du dépôt — clone, sauvegarde,
poste secondaire, futur collaborateur — peut se présenter comme n'importe quel
utilisateur, y compris l'utilisateur 1, qui est l'administrateur créé par `_seed()`.
Aucune trace ne distingue ce jeton d'un jeton légitime : la piste d'audit enregistrera
l'action sous l'identité usurpée.

**Ce qui limite la portée aujourd'hui.** L'application est servie sur `127.0.0.1:8000`
sur le poste de Philippe. Tant que c'est le cas, l'attaquant devrait déjà être sur la
machine. Le risque n'est pas actuel, il est **structurel et bloquant pour toute mise à
disposition**.

**Correction recommandée.** Lire le secret depuis l'environnement, refuser de démarrer
s'il est absent ou égal à la valeur d'exemple, et régénérer — ce qui invalide les jetons
en circulation, effet souhaitable ici.
**Test à ajouter.** Démarrage sans variable d'environnement : doit échouer.

### SEC-102 — Politique de session sans garde-fous

**Catégorie :** authentification
**Statut :** confirmé
**Sévérité :** élevée
**Fichier :** `backend/app/api/auth.py`

| Contrôle | État |
|---|---|
| Longueur minimale du mot de passe | 6 caractères |
| Complexité exigée | **aucune** |
| Limitation de débit sur `/login` | **absente** |
| Verrouillage après N échecs | **absent** |
| Révocation / liste noire de jetons | **absente** |
| Durée de vie du jeton | **7 jours**, non renouvelable, non révocable |
| Inscription | **ouverte**, sans dépendance d'authentification |

`POST /api/auth/register` crée un compte `role="user"` et **rejoint une entité existante
si le nom fourni correspond** (`entity_name`, ligne 108). Le rôle attribué reste
`user` — un compte ainsi créé ne voit que ses propres deals, le cloisonnement de §6.3
tient. Le défaut n'est donc pas une élévation de privilège, mais l'absence de contrôle
d'accès à l'instance elle-même, doublée de l'absence de toute défense contre l'essai
exhaustif de mots de passe.

### SEC-103 — CORS ouvert et aucun en-tête de durcissement

**Catégorie :** exposition
**Statut :** confirmé
**Sévérité :** moyenne (élevée hors poste local)
**Fichier :** `backend/app/main.py`, ligne **47**

Configuration : `allow_origins=["*"]`, `allow_credentials=True`, `allow_methods=["*"]`,
`allow_headers=["*"]`.

Comportement mesuré sur une application portant la même déclaration :

| Requête | `Allow-Origin` émis | `Allow-Credentials` |
|---|---|---|
| GET simple depuis `https://site-tiers.example` | `*` | `true` |
| Préflight OPTIONS (POST + `authorization`) | **`https://site-tiers.example`** | `true` |

Le préflight **renvoie l'origine demandeuse** plutôt que `*`, ce qui autorise
explicitement une page tierce à émettre des requêtes créditées portant un en-tête
`Authorization`. Le jeton étant porté en `Bearer` et non en cookie, le navigateur ne
l'attache pas automatiquement : l'exploitation directe reste limitée. La configuration
n'en est pas moins la plus permissive possible.

En-têtes de durcissement dans `main.py` : `Content-Security-Policy`,
`X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security` et
`Referrer-Policy` sont **tous absents**.

---

## 7. Ce qui est bien tenu

Vérifié, pas supposé.

### 7.1 Cloisonnement des données — solide

**Analyse statique.** 58 routes réparties sur 14 modules récupèrent un objet possédé par
identifiant. Toutes contiennent une garde de propriété dans le corps de la fonction.
L'heuristique employée est volontairement grossière — elle cherche un marqueur
(`user_id`, `entity_id`, `_can_access`, `_ops_deal`, dépendance admin) n'importe où dans
la fonction, donc elle ne prouve pas que la garde porte sur le bon objet quand une route
en manipule plusieurs. Elle sert de filtre, la preuve vient de la vérification dynamique
ci-dessous.

**Vérification dynamique — accès par identifiant.** Un deal appartenant à `alice`
(entité 1), sollicité par six acteurs :

| Route | alice (propr.) | bob (même entité) | carol (autre entité) | ops2 (ops, autre entité) | chk1 (checker, même entité) | admin |
|---|---|---|---|---|---|---|
| `GET /deals/{id}` | OK | **404** | **404** | **404** | OK | OK |
| `GET /deals/{id}/audit` | OK | **404** | **404** | **404** | OK | OK |
| `GET /deals/{id}/reprice` | OK | **404** | **404** | **404** | 404 | 404 |
| `POST /deals/{id}/mtm` | OK | **404** | **404** | **404** | 404 | 404 |
| `POST /deals/{id}/greeks` | OK | **404** | **404** | **404** | 404 | 404 |

Aucune fuite. Le point notable est qu'un **ops_maker d'une autre entité est bloqué** :
`_can_access_deal` exige l'égalité des entités, pas seulement le rôle. C'est le bon
comportement et il est rarement implémenté correctement.

**Vérification dynamique — portée des listes.** Trois deals, un par propriétaire :
`D-1` (alice, entité 1), `D-2` (bob, entité 1), `D-3` (carol, entité 2). Retour réel de
`GET /deals` :

| Acteur | Rôle | Deals retournés |
|---|---|---|
| alice (E1) | user | 1 → `D-1` |
| bob (E1) | user | 1 → `D-2` |
| carol (E2) | user | 1 → `D-3` |
| ops1 (E1) | ops_maker | 2 → `D-1`, `D-2` |
| ops2 (E2) | ops_maker | 1 → `D-3` |
| adm (E1) | admin | 3 → `D-1`, `D-2`, `D-3` |

La graduation est exacte : un utilisateur ne voit que ses deals, un ops ne voit que son
entité, l'administrateur voit tout. C'est le comportement attendu, sans exception ni
débordement.

Un effet de bord mineur : `reprice`, `mtm` et `greeks` renvoient 404 **même à
l'administrateur et au checker de l'entité**, qui peuvent pourtant lire le deal. Ce
n'est pas un défaut de sécurité — c'est une asymétrie fonctionnelle à trancher :
un checker qui doit contrôler une valorisation ne peut pas la recalculer.

### 7.2 Piste d'audit — append-only vérifié

`AuditEvent` est documenté « append-only business audit trail ». Recherche exhaustive
sur `backend/app/` : **0 suppression** et **0 mutation** d'un `AuditEvent` existant.
(Sept lignes remontées par la recherche initiale sont des comparaisons `==` dans des
filtres de requête, pas des affectations.) Le modèle porte `before_json`, `after_json`,
`actor_user_id`, `actor_type`, `result` — la structure nécessaire à une reconstitution.

### 7.3 Workflow maker-checker — 48 tests dédiés

`test_workflow_controls.py` couvre nommément : le maker ne peut pas valider sa propre
soumission ; le checker est cantonné à l'entité du deal ; le propriétaire du deal ne
peut pas capturer un fixing même s'il est `ops_maker` ; une correction crée une version
immuable ; un rejet restaure la version officielle précédente ; l'échec de l'audit
empêche la persistance du fixing ; l'application de résolution est exactement-une-fois
et rollbackée si l'audit échoue. C'est le module le mieux protégé du dépôt.

### 7.4 Corrections de la vague du 1er août au soir

Outre les onze findings fermés, la vague apporte trois choses vérifiables :

- **`_hw_convexity`** calcule l'ajustement sur l'intégrale **discrète** réellement
  formée par le simulateur, pas sur sa limite continue — d'où les 0,47 bp résiduels au
  lieu d'un résidu de discrétisation ;
- l'appariement antithétique **négocie en place** (`np.negative(Z, out=Z)`) et libère la
  jambe de base avant d'allouer l'antithétique : les prix sont inchangés au bit près,
  la mémoire de pointe tombe d'environ 500 Mo sur un run 3 ans / 100 k trajectoires ;
- `_theta_and_event` divise désormais par `365,25 × dt_step` et non par 7 en dur, ce qui
  supprime une dépendance silencieuse de theta à la constante `SY`.

---

## 8. Soupçons non confirmés

Signalés sans note ni verdict, faute d'avoir pu les reproduire dans le temps de l'audit.

- **Réconciliation deal ↔ RFQ (RFQ-001 du 31/07).** `booking_gate_failures` et
  `pricing_input_hash` existent et sont testés, un index unique
  `ux_deals_rfq_id` impose un deal par RFQ. Je n'ai pas construit le scénario complet
  RFQ → cotation → booking permettant de statuer sur l'équivalence économique des
  termes.
- **Ambiguïtés de templates (QNT-121 à QNT-124).** Non rejouées : elles portent sur
  `frontend/src/data/payscriptTemplates.js` et demandent une term sheet de référence
  pour être tranchées, pas une sonde.
- **Conformité KID au-delà des horizons.** Seul le défaut d'horizon a été mesuré. La
  conformité de la méthodologie MRM/VEV à une version donnée des RTS n'est pas
  vérifiable par sonde.
- **Durabilité du scheduler (LCY-005 du 31/07).** Non instrumenté.
- **Effet réel du CORS sur l'instance servie.** Testé sur une application jetable à
  configuration identique, pas sur `main.py` en fonctionnement.

---

## 9. Plan de remédiation

Ordonné par ratio risque/effort. La ligne de démarcation marque ce qui doit être fait
avant toute utilisation dépassant le poste local.

### Lot 1 — avant toute mise à disposition (effort : faible)

1. **Externaliser `_SECRET`** en variable d'environnement, refuser le démarrage sur la
   valeur d'exemple. *(SEC-101 — quelques lignes, aucun risque de régression)*
2. **Refuser un FX manquant** au lieu de retenir 1,0, aux trois emplacements de
   `portfolios.py`. *(QNT-201 — trois lignes, effet immédiat sur la justesse du risque)*
3. **Supprimer `.bfill()`** de `load_hist_prices`. *(QNT-202 — une ligne)*
4. Limitation de débit et verrouillage sur `/login`. *(SEC-102)*

### Lot 2 — justesse des chiffres publiés (effort : moyen)

5. **Horizons intermédiaires du KID** : revaloriser en produit vivant, avec la mécanique
   de reprise d'état désormais disponible dans le MTF corrigé. *(QNT-105 — c'est le seul
   bloquant critique quantitatif restant, et la brique existe déjà)*
6. **Orthogonaliser le facteur de taux** pour que `rho_rS` cesse de déplacer la
   corrélation actions. *(QNT-113)*
7. **IRR** : encadrement par bissection avant Newton, et journal explicite des fenêtres
   exclues plutôt que leur disparition. *(QNT-120)*
8. Unifier `var_eur` et `distribution_summary.p5`, ou renommer l'un des deux.
   *(QNT-117)*

### Lot 3 — fondations (effort : élevé)

9. Refaire le tirage joint des extrema du pont brownien, ou retirer le mode « continu »
   de l'interface. *(QNT-101)*
10. Calendrier contractuel avec jours ouvrés et fériés ; unification des grilles 52/252 ;
    fin de la quantification hebdomadaire sur les maturités courtes.
    *(QNT-114, QNT-115, QNT-119)*
11. Vega Heston par bump des paramètres calibrés, ou renommage définitif du champ.
    *(QNT-103)*
12. Tests d'intégration HTTP sur la couche auth et les routes sensibles. *(QNT-203)*

### Lot 4 — industrialisation

13. En-têtes de durcissement et restriction CORS à l'origine servie. *(SEC-103)*
14. Golden scenarios par template, avec spécification économique écrite.
15. Intégration continue backend et frontend.

---

## 10. Conclusion

Le moteur a progressé de façon mesurable en vingt-quatre heures, et pour la bonne
raison : les corrections ont visé les causes racines, pas les symptômes. La convexité
Hull-White est calculée sur la discrétisation réellement utilisée ; la reprise d'état du
Mark-to-Future rejoue le contrat depuis l'origine plutôt que d'estimer ; la validation
des entrées refuse au lieu de réparer. Trois choix qui indiquent une compréhension du
problème plutôt qu'un contournement.

Ce qui reste ouvert côté quantitatif est désormais **borné et nommé** : sept défauts,
tous mesurés, tous accompagnés d'un ordre de grandeur. Aucun n'est un mystère.

Le vrai changement de nature est ailleurs. Un audit purement quantitatif ne pouvait pas
voir que la couche qui protège l'identité des utilisateurs repose sur une chaîne de
caractères publiée dans le dépôt. Le cloisonnement métier, lui, est **mieux construit
que la moyenne de ce qu'on rencontre** — un ops_maker d'une autre entité est refusé,
la piste d'audit ne se réécrit pas, le maker ne valide pas sa propre soumission. Cette
qualité mérite qu'on ne la laisse pas reposer sur un secret d'exemple.

**Le premier lot de remédiation tient en une poignée de lignes et ferme les quatre
risques les plus graves.** C'est le meilleur rapport effort/risque que ce dépôt ait
offert depuis le début des audits.

---

## 11. Remédiation appliquée — lots 1 et 2

*Section ajoutée après coup : les deux premiers lots du plan §9 ont été codés le
2 août, à la demande. L'audit lui-même reste le constat en lecture seule décrit
ci-dessus ; ce qui suit décrit ce qui a changé depuis.*

### 11.1 État

| # | Correctif | Fichier | Mesure avant → après |
|---|---|---|---|
| 1.1 | Secret JWT externalisé | `api/auth.py` | Valeur publiée en dur → variable d'environnement, sinon clé générée par machine dans `backend/data/.jwt_secret` (ignoré par git). Une clé absente ou trop courte, ou la valeur d'exemple, refusent le démarrage. |
| 1.2 | FX manquant refusé | `core/amc_prices.py`, `api/portfolios.py`, `api/shocks.py`, `api/var.py` | Parité silencieuse → `None` explicite et position nommée. |
| 1.3 | Backward fill supprimé | `services/market_data.py` | Vol sous-estimée de 21,8 % → **valeur réellement observable** (0,0614). |
| 1.4 | Débit limité sur `/login` | `api/auth.py` | Aucune limite → verrouillage par (identifiant, IP) après 5 échecs, paliers 60 s / 5 min / 15 min. |
| 2.5 | Horizons KID en produit vivant | `api/kid.py`, `engine.py` | À 1 an : prix 1,0000 et médiane 1,0000 → **0,9470**, médiane 0,9759, éventail p10–p90 de 0,2781. |
| 2.6 | Facteur de taux orthogonalisé | `engine.py` | Worst-of dérivant de **+7 600 bp** avec `rho_rS` → **−1,5 bp**. |
| 2.7 | IRR par encadrement | `engine.py`, `api/pricing.py` | Perte totale `None` (fenêtre exclue) → **−100 %**, et journal des exclusions restantes. |
| 2.8 | Quantiles de VaR unifiés | `core/var_engine.py` | `var_eur` 96,00 contre `p5` −95,05 → **`var_eur == −p5` par construction**. |
| 2.9 | Annualisation du KID (§11.2bis) | `api/kid.py`, `engine.py` | Autocall à coupon 8 % rappelé à 1 an, affiché **1,55 %/an** → **8,00 %/an** (TRI des flux datés). |

### 11.2 Trois points qui méritent d'être signalés

**Le défaut FX était plus large que ce que l'audit avait mesuré.** Il existait aussi
dans `shocks.py` (lignes 135 et 159) et `var.py` (ligne 57), c'est-à-dire dans la
mesure de risque elle-même et non seulement dans son affichage. Les six sites sont
corrigés par un helper commun, `core/amc_prices.fx_rate_to`. La raison pour laquelle
le défaut ne se voyait jamais est maintenant explicite dans son docstring :
`get_fx_series` répond « série vide » aussi bien quand la conversion est inutile
(même devise — le cas de l'immense majorité des deals) que quand elle a échoué.

**La correction du KID a fait apparaître une incohérence de convention.** Les horizons
intermédiaires sortent naturellement en valeur *à la date* d'horizon, alors que la
ligne RHP est une valeur actuelle. Les deux ont été ramenées sur la même base, ce qui
fournit un contrôle exploitable : sous absence d'opportunité d'arbitrage, la valeur
actuelle de la position ne dépend pas de la date à laquelle on la regarde. Les trois
horizons donnent désormais **0,9470 / 0,9481 / 0,9502** — 32 bp d'écart, soit le bruit
Monte Carlo entre un MC imbriqué et un MC direct.

### 11.2bis — Deux erreurs de ma part, et le défaut qu'elles masquaient

*Cette sous-section a été réécrite deux fois. Elle est conservée sous cette forme
parce que le cheminement est instructif : les deux versions précédentes étaient
fausses, et c'est Philippe qui a redressé le raisonnement.*

**Version finale — la règle est celle du TRI.** Le montant affiché est la somme des
flux effectivement reçus. Le rendement est le **TRI de ces flux à leurs dates** — la
fonction `XIRR` d'Excel — annualisé sur la durée de vie **réelle du scénario**, pas
sur l'horizon nominal de la ligne. Aucune hypothèse de réinvestissement n'intervient,
nulle part : un KID n'en fait pas, et le moteur non plus désormais.

| Autocall à coupon 8 %, rappelé à 1 an, ligne « 5 ans » | Rendement publié |
|---|---:|
| Avant l'audit — `(montant/nominal)^(1/5)` | **1,55 %** |
| Ma première correction — capitalisation à 3 % puis puissance 1/5 | **4,02 %** |
| **Correct — TRI des flux datés** | **8,00 %** |

Propriété qui rend la mesure fiable, vérifiée pour un rappel en année 1, 2, 3 et 5 :
un coupon annuel de 8 % donne **8,00 % quelle que soit l'année de rappel**.

**Les deux erreurs, nommées.** J'avais d'abord supposé que `run_mc` renvoyait des
payoffs actualisés — faux, une sonde donne un `payoffs` médian de 1,000000 sur un ZC
5 ans à 3 %. J'avais ensuite comblé l'écart d'horizon par une capitalisation au taux
sans risque — une hypothèse que le produit ne porte pas, et qui mélangeait la
performance du produit avec celle d'un placement de trésorerie.

**Le défaut réel, qu'aucune des deux versions n'atteignait.** L'exposant
`1/T_horizon` ignore que le scénario a pu vivre moins longtemps que la ligne où il
s'affiche. Le dénominateur doit suivre le scénario, pas l'étiquette de colonne.

**Conséquence de présentation, assumée.** Deux cellules d'une même colonne peuvent
désormais porter des durées différentes. C'est correct et c'est signalé : chaque
cellule expose sa `life`, affichée sous le rendement quand elle diffère de
l'en-tête (« rappel à 1,00 an »).

**Mise en œuvre.** `_eval_paths` enregistre en option les flux datés par trajectoire
(`per_path_flows`) — `flux_table` agrège entre trajectoires et ne pouvait donc pas
répondre. Le percentile est pris **une seule fois, sur le résultat**, et le montant
comme le rendement sont lus sur *le même* scénario : les lire séparément
apparierait le versement d'un scénario avec la durée d'un autre. Le TRI réutilise
`compute_irr`, fiabilisé au lot 2.7. Le VEV et donc le MRM sont **inchangés** — `p1`
garde sa définition d'origine.

---

### 11.2ter — Ancienne rédaction (conservée pour mémoire)

Une première version de cette section affirmait que `_scenario_row` annualisait des
valeurs actuelles comme si elles étaient des valeurs futures. **C'était faux, et la
correction qui en découlait l'était aussi.** Vérification par sonde :
`run_mc` renvoie deux séries, `raw_all` (non actualisée, exposée sous `payoffs`) et
`pv_all` (actualisée, restée interne). Un ZC 5 ans à 3 % donne un `payoffs` médian de
**1,000000** et non 0,860708 : la table PRIIPs travaillait donc déjà sur des montants
non actualisés, ce qui est la bonne base d'affichage. L'actualisation `exp(-r·T_cap)`
introduite dans `_horizon_percentiles` était par conséquent une **régression de ma
part**, désormais retirée.

Le vrai défaut est ailleurs, et il est plus significatif. `payoffs` **somme les flux
d'une trajectoire sans tenir compte de leur date**. Un autocall rappelé à un an pour
1,08 était donc affiché comme 1,08 détenu à cinq ans, puis annualisé sur cinq ans :

| | Montant RHP | Rendement annualisé |
|---|---:|---:|
| Avant | 1,0800 | **1,55 %** |
| Après | **1,2177** | **4,02 %** |

*(cas de contrôle à rappel quasi certain : 1,08 reçu à t = 1 an, replacé quatre ans à
3 % — l'attendu analytique est 1,217697 et 4,02 %, obtenus à 1e-6 près.)*

Un produit qui a rendu +8 % en douze mois était présenté au client comme rapportant
1,55 % par an.

**Correctif.** Les montants sont reconstruits depuis la valeur actuelle
(`pv × exp(r·T)`), ce qui restitue la date des flux. Toutes les lignes de la table
répondent désormais à une seule question — *« que détenez-vous à cette date, produits
réinvestis au taux sans risque »* — la convention que les horizons intermédiaires
appliquaient déjà par construction. Elle est déclarée dans le payload
(`reinvestment: "taux_sans_risque"`) parce que c'est une convention, pas un fait, et
que les rendements annualisés ne se lisent pas sans elle. `run_mc` expose les payoffs
actualisés en option (`pv_payoffs=True`) pour ne pas alourdir la réponse de pricing.

**Deux effets à connaître.** Les montants et rendements annualisés affichés changent
pour tout produit à flux intermédiaires ou à rappel anticipé — c'est le correctif.
Et le `p1` qui alimente le VEV est maintenant le montant détenu à la RHP par unité
investie, plus proche de la définition de l'Annexe II que la somme brute de flux
qu'il utilisait : **le MRM peut se déplacer sur certains produits**. La formule VEV
elle-même reste l'approximation du module, non l'expression des RTS — non-conformité
déjà suivie par ailleurs.

**Deux refus explicites ont été ajoutés**, dans la logique déjà retenue pour les
matrices de corrélation non définies positives :
- une spécification `rho_rS` incompatible avec la matrice actions est refusée avec un
  message qui dit quoi ajuster, au lieu de pricer le panier qu'elle implique ;
- les horizons intermédiaires du KID refusent une courbe de taux ou des taux
  stochastiques, que la revalorisation résiduelle ne porte pas encore. Les absorber en
  silence aurait mis deux conventions de taux dans un même document réglementaire.

### 11.3 Vérification

**558 tests passent** (516 avant, **42 ajoutés**). Le nouveau fichier
`backend/tests/test_remediation_2026_08_02.py` contient un test par défaut corrigé,
assertant la valeur que l'audit avait mesurée — chacun de ces défauts produisait un
résultat plausible, fini et non signalé, c'est-à-dire précisément ce qu'une suite verte
ne détecte pas d'elle-même.

Une sonde de vérification consolidée hors dépôt exécute 31 contrôles sur les huit
correctifs : **31/31 au vert**.

### 11.4 Ce que la remédiation ne change pas

Les findings des lots 3 et 4 restent entiers : pont brownien du monitoring continu
(−14,3 %), vega Heston (×(1−ρ²)), calendrier contractuel, grilles 52/252,
quantification hebdomadaire, `effective_T_max`, saturation de la surface de vol locale,
en-têtes de durcissement HTTP et CORS. Le verdict par usage du §1 reste valable pour
tout ce qui en dépend.

Ce qui change : **« déploiement hors poste local »** passe de NO-GO bloquant à
NO-GO résiduel — le secret n'est plus publié, mais CORS, les en-têtes de durcissement
et l'absence de test d'intégration de la couche auth restent à traiter. Et la **mesure
de risque portefeuille** passe de NO-GO à **GO sous contrôle** : un FX manquant est
désormais refusé et nommé au lieu d'être inventé.

---

*Audit conduit en lecture seule. Dix sondes exécutables, 516 tests de la suite
existante exécutés, aucun fichier du dépôt modifié pendant l'audit, aucun serveur
démarré, base de production jamais ouverte en écriture. La §11 rend compte de la
remédiation codée ensuite, à la demande.*
