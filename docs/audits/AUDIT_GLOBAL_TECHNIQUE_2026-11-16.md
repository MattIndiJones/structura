# Structura — Audit technique détaillé

**Date : 16 novembre 2026 · Commit audité : `eca6f52` (branche `main`, 05/11/2026) · Poste : Windows 10, Python 3.11.9, Node 24.12**

**État : Suivi.** Synthèse orientée décisions : [AUDIT_GLOBAL_EXECUTIF_2026-11-16.md](AUDIT_GLOBAL_EXECUTIF_2026-11-16.md).

Ce rapport applique à Structura le cahier des charges de l'audit global mené sur QISTRA le même jour : six axes (interface, fonctions métier, architecture, sécurité et base, maturité produit, industrialisation), preuves par fichier et par ligne, statuts explicites, roadmap P0 à P3. Il s'appuie sur le code, les configurations, les tests et les notes du dépôt, pas sur les fonctionnalités annoncées.

Aucun fichier de code n'a été modifié. Les seuls fichiers créés sont les deux rapports de `docs/audits/` et leur entrée dans `docs/README.md`, exigée par la règle d'indexation du projet. Les scripts de sonde et leurs sorties vivent hors du dépôt.

## Légende des statuts

| Statut | Signification |
|---|---|
| **Opérationnel** | Code présent, intégré de bout en bout, couvert par des tests qui passent |
| **Partiel** | Code réel mais périmètre incomplet, ou résultat indicatif |
| **Simulé** | Fonctionne uniquement sur un poste, contre des organisations fictives ou des données de substitution |
| **Prévu** | Décrit dans une note, absent du code |
| **Non vérifié** | Présent dans le code mais non exercé ni relu pendant cet audit |

---

## 0. Méthode, périmètre et limites

### Ce qui a été fait

- **Cartographie** : 1 632 fichiers suivis. 546 `.py` (156 000 lignes, tests inclus), 150 `.vue` (47 200 lignes), 238 `.md` (67 800 lignes), 76 `.json` (395 000 lignes, pour l'essentiel des pièces d'audit).
  - `backend/app` : 275 modules Python, 91 900 lignes.
  - `backend/tests` : 198 fichiers de tests, 60 300 lignes, **4 393 tests collectés**.
  - `frontend/src` : 238 fichiers source (59 400 lignes) et 95 fichiers de tests (9 900 lignes).
- **Lecture** intégrale ou ciblée : démarrage et cycle de vie du serveur, base de données et migrations, authentification, sessions, capacités, périmètre de lecture, transport RFQ entre installations, accès développeur, transpileur PayScript, moteur Monte Carlo (structure, `run_mc`, sorties), exécuteur de calcul, schéma de requête de pricing, KID, données de marché, identité de calcul des valorisations, audit, clés des fournisseurs d'IA, client d'API et session du front, configuration des tests, CI, dépendances.
- **Inventaires statiques** par analyse syntaxique : 458 routes et leurs dépendances d'authentification, 102 tables, motifs d'exceptions et de journalisation, sens des imports entre couches.
- **Exécutions**, toutes sur un dossier de données isolé hors de `backend/data` :
  - sondes numériques indépendantes du moteur (section 2.2) ;
  - un lot ciblé de 5 fichiers de tests backend, 160 tests ;
  - la suite complète du front, 997 tests ;
  - un build du front dans un dossier temporaire.

### Ce qui n'a pas été fait

| Zone | Raison |
|---|---|
| Suite backend complète, dans le premier passage | Règle du projet. **Lancée ensuite à la demande de Philippe, le 17/11** : résultat en section 6.1 bis |
| Parcours dans le navigateur | L'application n'a pas été lancée. L'analyse de l'interface repose sur le code Vue ; les recettes graphiques du 23/10 et du 24/10 sont citées comme des constats datés, non rejoués |
| Six installations et service central en fonctionnement | Lus, non démarrés |
| Réseau RFQ entre deux machines, TLS | Aucune seconde machine ; code lu |
| Numérique de SABR, Local Vol, LSV, Greeks, quanto | Non sondés ; seuls GBM, Heston, le pont brownien, le funding et le Mark-to-Future d'un zéro-coupon l'ont été |
| Logique de AMC, FIFO, Fama-French, CCR, VaR, Product Optimizer, CRM, EMT | Structure et tests constatés, logique non relue ligne à ligne |
| Appels aux fournisseurs d'IA, dictée Whisper, atelier d'agents | Non exécutés |
| Exécution réelle de la CI sur GitHub, protection de branche | Invérifiable depuis ce poste |

---

## 1. Architecture

### 1.1 Vue d'ensemble

```
Lanceur Tkinter (lancer_structura.bat → scripts/launch_structura.py)
        │ démarre un processus par installation, tous sur 127.0.0.1
        ▼
uvicorn mono-processus (backend/run.py)
  ├─ FastAPI « application » (app/main.py) : 435 routes, bundle Vue servi en statique
  │    ├─ api/ (46 routeurs) ──► services/ ──► core/ ──► db/ (SQLModel sur SQLite)
  │    ├─ core/payscript : transpileur + moteur Monte Carlo, sans aucun import de la base
  │    ├─ ordonnanceur quotidien 23 h et boucle de transport RFQ, dans le même processus
  │    └─ core/compute : lots de calcul en ProcessPoolExecutor, délai et annulation
  ├─ FastAPI « plateforme » (hybrid/platform.py) : annuaire central, 18 routes
  └─ contrôleur de simulation, redirection de portail (hybrid/)
```

Fichiers : [run.py](../../backend/run.py), [main.py](../../backend/app/main.py), [runtime.py](../../backend/app/runtime.py), [hybrid/config.py](../../backend/app/hybrid/config.py).

### 1.2 Points forts d'architecture (vérifiés)

- **Le moteur de pricing est isolé.** Les sondes ont importé `core/payscript/parser.py` et `engine.py` sans charger un seul module de `db/` (contrôle sur `sys.modules`). Le moteur est testable et extractible seul.
- **Les calculs lourds par lots ont un vrai exécuteur** : processus séparés, délai de 300 s par job, annulation qui termine les processus enfants, isolation des échecs par job ([executor.py:45-142](../../backend/app/core/compute/executor.py)).
- **Chaque valorisation enregistre l'identité du code qui l'a produite** : SHA du commit Git, empreinte SHA-256 des fichiers du moteur, versions de Python, numpy et scipy, version des conventions ([valuation_runs.py:28-59](../../backend/app/core/valuation_runs.py)). C'est exactement le point qui manquait à QISTRA.
- **Budget de calcul a priori** : mémoire et travail estimés avant tout tirage, refus au-delà d'une limite ([engine.py:2428-2445](../../backend/app/core/payscript/engine.py)), bornes sur la taille du script, la maturité, le nombre de sous-jacents ([compute_budget.py:16-22](../../backend/app/core/compute_budget.py)).
- **Mode consultation en lecture seule à trois verrous** : intergiciel qui refuse toute écriture, base ouverte en `mode=ro`, `PRAGMA query_only` ([main.py:94-101](../../backend/app/main.py), [database.py:22-35](../../backend/app/db/database.py)).
- **Démarrage sûr** : aucune base n'est créée ni aucun compte semé sans installation identifiée ou simulation explicitement déclarée ([database.py:921-962](../../backend/app/db/database.py)).

### 1.3 Problèmes d'architecture

| # | Constat | Preuve | Impact |
|---|---|---|---|
| A1 | **Module-monolithe côté API.** `api/deals.py` fait 7 937 lignes pour 39 routes : la logique de cycle de vie, d'amendement, de fixing et de Greeks vit dans le routeur. Les cinq plus longs gestionnaires dépassent 180 lignes | [deals.py](../../backend/app/api/deals.py) ; `main.py` importe `refresh_deal_core` et `build_watchlist_row` depuis le routeur pour les injecter dans un service ([main.py:67, 92](../../backend/app/main.py)) | Toute évolution du cycle de vie touche ce fichier ; revue et tests unitaires coûteux |
| A2 | **Le payoff s'évalue trajectoire par trajectoire en Python pur.** Mesuré : 7 s pour un call à 100 000 paires, 6,9 s pour un autocall 3 ans sur 3 sous-jacents à 40 000 paires | [executor.py:5-9](../../backend/app/core/compute/executor.py) ; sondes de la section 2.2 | Un pricing interactif coûte des secondes là où une évaluation vectorisée coûterait des dizaines de millisecondes. Greeks, grilles et solveurs multiplient ce coût |
| A3 | **Le pricing interactif tourne dans le fil de la requête**, sous le verrou global de l'interpréteur, dans un serveur mono-processus | [pricing.py:114-120](../../backend/app/api/pricing.py), [run.py](../../backend/run.py) | Pendant un calcul, toute l'API ralentit. Ni délai d'exécution ni annulation pour un prix lancé à l'écran |
| A4 | **API non typée en sortie** : 2 routes sur 458 déclarent un modèle de réponse. Le front écrit ses appels à la main | Inventaire des routes | Dérive silencieuse possible entre serveur et interface ; pas de client généré |
| A5 | **Un seul processus porte l'API, l'ordonnanceur de cycle de vie et le transport RFQ.** L'erreur d'un cycle de transport est journalisée sans trace d'appel | [main.py:139-155, 205-223](../../backend/app/main.py) | Un arrêt du serveur suspend aussi les fixings automatiques ; un rattrapage au démarrage existe (`run_missed_refresh_if_needed`) |
| A6 | **Monolithes côté interface** : `AmcView.vue` 5 913 lignes, `stores/pricing.js` 3 669, `BookingView.vue` 2 987, `RfqView.vue` 2 927 | Tailles de fichiers | Un seul magasin d'état porte tout le Pricer ; régressions croisées probables |
| A7 | **Couches lâches entre `core` et `services`** : 19 imports de `services` et 24 de `db` depuis `core` ; des modules `core` lèvent des erreurs HTTP | [core/access.py:53-55](../../backend/app/core/access.py) | Le domaine n'est pas séparable du web, à l'exception du moteur PayScript |
| A8 | **34 variables d'environnement `STRUCTURA_*`** sans schéma central ni validation d'ensemble | Inventaire statique | Configuration difficile à documenter et à auditer |
| A9 | **Versions incohérentes et aucune étiquette** : l'application se déclare `0.2.0`, `/health` répond `0.1.0`, le front `0.1.0` ; `git tag` est vide | [main.py:73, 238](../../backend/app/main.py), [package.json](../../frontend/package.json) | Aucune livraison n'est nommable |
| A10 | **Hypothèses Windows** : `taskkill`, PowerShell, lanceur `.bat` et `.vbs`, CI backend sur `windows-latest` | [hybrid/deployment.py:345](../../backend/app/hybrid/deployment.py), [ci.yml](../../.github/workflows/ci.yml) | Portage sur un serveur Linux non qualifié |
| A11 | **API de démarrage dépréciée** (`@app.on_event`) | [main.py:104, 119, 139, 205, 226](../../backend/app/main.py) ; avertissement émis à la collecte des tests | Dette mineure |

### 1.4 Résidus et hygiène du dépôt

| Élément | Preuve | Commentaire |
|---|---|---|
| **`frontend/dist` n'est jamais purgé** | 1 407 fichiers et 45,9 Mo sur disque, 21 générations du bundle principal ; 312 fichiers suivis, soit 4 générations de chaque fragment ; 1 097 des 1 098 entrées de `git status` en viennent | Un build propre fait 118 fichiers et 3,5 Mo. Chaque livraison ajoute une génération au dépôt |
| Trois journaux serveur suivis | `backend/_srv_err.log`, `_srv_out.log`, `_verify_out.log` | À sortir du suivi |
| `tmp/pdfs/` suivi alors que `/tmp/` est ignoré | 4 fichiers, 1,8 Mo | Ajoutés avant la règle |
| Fichiers de travail à la racine | `scratchpad_AMC_Etude_CH1473731680_corrige_2026-07-16.pdf` (2,2 Mo), `scratchpad_ch1473731680_result.json`, `book_campaign_v2.py` | Une étude AMC portant un ISIN réel est dans l'historique Git. Contenu non ouvert : **à qualifier** avant tout partage du dépôt |
| Pièces d'audit volumineuses | 63 fichiers JSON, 14,3 Mo dans `docs/audits/`, dont un inventaire de 6,2 Mo | Preuves utiles, mais dans le dépôt de code |
| Dépôt lourd | `.git` : 237 Mo pour 62 commits | Conséquence des trois lignes précédentes et de la vidéo de démonstration |
| Règle « rien à la racine » non tenue | `AGENTS.md`, `docs/PRODUCT_OPTIMIZER_V1.md` hors des dossiers de l'index | Écart documentaire |
| `.runtime/` | 47 dossiers de recettes isolées, ignorés par Git | Bonne pratique d'isolation ; à purger périodiquement |

Aucune fonctionnalité fictive (écran sans serveur, bouton sans effet) n'a été trouvée dans le code lu. Les parties simulées sont déclarées comme telles dans les notes.

---

## 2. Fonctionnalités métier

### 2.1 Inventaire et statut réel

| Module | Statut | Preuves | Réserves |
|---|---|---|---|
| PayScript : langage, transpileur, catalogue, modèles | **Opérationnel** | [parser.py](../../backend/app/core/payscript/parser.py) ; tests du lot ciblé ; référence de langage vérifiée par un test de vocabulaire | Sandbox lexical, voir S2 et S3 |
| Moteur Monte Carlo GBM | **Opérationnel**, recoupé | Sonde A : écart à Black-Scholes de +2,8 à +3,0 pb, dans l'IC 95 % | — |
| Heston (schéma QE) | **Opérationnel**, recoupé | Sonde C : écart au prix semi-analytique de +0,9 à +1,1 pb, dans l'IC 95 % | — |
| SABR, Local Vol (Dupire), LSV, taux stochastiques Hull-White | **Opérationnel** selon les tests du projet · **Non vérifié** ici | [engine.py:567-1030](../../backend/app/core/payscript/engine.py) ; `test_engine.py` passe sur ces modèles | LSV résiduel qualifié le 05/11 selon sa note, non rejoué |
| Barrières : grille ou pont brownien | **Opérationnel**, recoupé, **incomplet** | Sonde D | Pas de monitoring en clôture quotidienne, voir F1 |
| Greeks par bump et recalcul | **Opérationnel** · Non vérifié | [engine.py:2978](../../backend/app/core/payscript/engine.py) | — |
| Mark-to-Future | **Opérationnel**, recoupé sur un zéro-coupon | Sonde F : valeur égale à l'actualisation exacte à 0,000 pb près | Un test périmé le dit faux, voir 6.1 |
| Profil de payoff, probabilités, trajectoires, backtest historique, comparateur | **Opérationnel** · Non vérifié | [pricing.py](../../backend/app/api/pricing.py), 22 routes | Dépend des historiques Yahoo |
| Product Optimizer et recherches | **Opérationnel** · lu en surface | `core/product_optimizer/` (9 modules), archives immuables par déclencheur | — |
| Données de marché | **Partiel** | Un seul fournisseur déclaré ([market_data.py:103-104](../../backend/app/services/market_data.py)) | Voir F3 |
| Surfaces de volatilité et calibration du smile | **Partiel** | La surface se décrit elle-même comme « Synthetic assumption, not market data » ([volatility_surface.py:105](../../backend/app/core/volatility_surface.py)) | Voir F4 |
| RFQ manuelle : demandes, cotations, tours, sélection | **Opérationnel** · lu en surface | [rfq.py](../../backend/app/api/rfq.py), `test_rfq.py` (2 266 lignes) | — |
| RFQ entre installations, confirmation électronique, rapprochement | **Simulé** | Transport signé réel ([services/rfq_transport.py](../../backend/app/services/rfq_transport.py)) ; recettes entre installations locales | Jamais exercé entre deux machines ; TLS non qualifié |
| Booking, versions de contrat, amendements, commandes idempotentes | **Opérationnel** · lu en surface | `deals.py`, déclencheurs d'intégrité Product | Aucun connecteur vers un système tiers ; aucune preuve externe de règlement |
| Cycle de vie : fixings, propositions, alertes, ordonnanceur | **Opérationnel** avec réserve de source | [lifecycle_alerts.py](../../backend/app/services/lifecycle_alerts.py), [main.py:134-155](../../backend/app/main.py) | Fixings officiels issus de Yahoo, voir F3 |
| MtM résiduel, runs de valorisation, Valo Explain, notes PDF | **Opérationnel** · lu en surface | [valuation_runs.py](../../backend/app/core/valuation_runs.py), `deal_valuation_pdf.py` | — |
| Risque : chocs, VaR historique, Greeks de portefeuille | **Opérationnel** · lu en surface | `var_engine.py`, `shocks.py` | — |
| Risque de contrepartie (CCR) | **Opérationnel** · lu en surface | `core/ccr/` (7 modules), 17 routes | — |
| KID PRIIPs | **Partiel** | Le code le dit lui-même ([kid.py:391-392](../../backend/app/api/kid.py)) | Voir F5 |
| EMT | **Partiel** · Non vérifié | [emt.py](../../backend/app/api/emt.py) | Indicatif selon le rapport du 01/11 |
| Term sheets | **Non vérifié** | Aucun générateur dédié identifié dans cette lecture | — |
| CRM : clients, personnes, opportunités, interactions, import, intelligence client | **Opérationnel** · lu en surface | 7 routeurs, 71 routes | — |
| Études AMC, FIFO, Fama-French | **Opérationnel** · lu en surface | `core/amc_*.py` (24 modules), `core/fifo/` | Audit dédié du 20/09 |
| Assistant IA de script, dictée locale | **Opérationnel** si un modèle est disponible · Non vérifié | Ollama local par défaut ([providers.py:70](../../backend/app/services/llm/providers.py)) ; script généré validé par un pricing | Voir S8 |
| Atelier d'agents et campagnes de recette | **Simulé** | `services/agent_workshop/` (16 modules) | Organisations fictives |
| Plateforme centrale, six installations, portail, lanceur | **Simulé** | Toutes les adresses sont `http://127.0.0.1:<port>` ([hybrid/config.py:46](../../backend/app/hybrid/config.py)) | Voir section 3.3 |
| Registre central des RFQ et facturation | **Prévu** | Déclaré non livré dans l'index | — |
| Consultation en lecture seule d'un book sauvegardé | **Opérationnel** | Trois verrous, section 1.2 | — |

### 2.2 Fiabilité des calculs financiers

#### Sondes indépendantes menées pendant l'audit

Formules de référence codées à part, sans rien emprunter au moteur. Graine 42, variables antithétiques.

| Sonde | Résultat | Lecture |
|---|---|---|
| **A. Call européen GBM** contre Black-Scholes, r 3 %, 1 an, vol 20 %, 100 000 paires, strikes 80/100/120 % | Écarts +2,82 / +2,95 / +2,90 pb ; demi-largeurs d'IC 95 % de 3,04 / 4,64 / 3,33 pb | Juste. Les trois écarts ont le même signe parce qu'ils partagent le même tirage |
| **B. Reproductibilité** | Deux exécutions à graine 42 : prix identiques au dernier chiffre. Graine 7 : −6,45 pb | Déterministe |
| **C. Heston QE**, grille hebdomadaire, contre le prix semi-analytique, strikes 90/100/110 % | Écarts +0,94 / +0,94 / +1,08 pb ; IC de ±2,9 à ±3,1 pb | Juste |
| **D. Put down-and-in américain**, strike 100 %, barrière 70 %, vol 25 %, 1 an | Formule fermée continue 4,408 % ; correction de Broadie-Glasserman-Kou quotidienne 4,204 % ; hebdomadaire 3,962 %. Moteur « grille » 4,011 % ; moteur « continu » 4,426 % | Chaque mode est juste **pour sa convention** : +5,0 pb contre l'hebdomadaire discret, +1,8 pb contre le continu. Aucun des deux ne vaut l'observation quotidienne, voir F1 |
| **E. Funding contre taux**, autocall 3 ans worst-of, 3 sous-jacents, corrélation 0,5, vol 25 %, dividende 3 % | +100 pb de taux : **−12,7 pb**. +100 pb de spread émetteur : **−188,9 pb**, identique par `ds` et par `funding_spread`. Vie espérée 2,50 ans | La règle de `CLAUDE.md` tient sur un produit qu'elle n'avait pas servi à écrire : le spread coûte bien plus que le taux, et l'écart de 176 pb est la contribution du drift |
| **F. Mark-to-Future d'un zéro-coupon**, r 4 %, 2 ans | Valeur à chaque date égale à `exp(−r·(T−t))` à 0,000 pb près, écart-type nul | Juste sur l'axe des dates exactes |

Ce sont des **mesures d'instance** : elles valident ces produits, ces paramètres et cette graine, pas une tolérance générale.

#### Ce qui est bien fait (relu)

- **Erreur statistique correcte et publiée** : écart-type calculé sur les moyennes de paires antithétiques, IC 95 % dans chaque réponse ([engine.py:2842-2877](../../backend/app/core/payscript/engine.py)).
- **Funding en actualisation seule**, appliqué après la construction du terme de taux ([engine.py:2476-2487](../../backend/app/core/payscript/engine.py)) ; vérifié par la sonde E.
- **Actualisation à la date de paiement** et axe ancré au strike, exposés dans la signature de `run_mc` ([engine.py:2377-2385](../../backend/app/core/payscript/engine.py)).
- **Diffusion aux dates contractuelles exactes** : l'axe du temps inclut les dates du contrat au lieu de les arrondir à la semaine ([engine.py:57-101](../../backend/app/core/payscript/engine.py)).
- **Modèle inconnu ou paramètre hors domaine refusé**, là où il retombait autrefois sur GBM en silence ([engine.py:116-146](../../backend/app/core/payscript/engine.py)).
- **Matrice de corrélation réparée seulement sous un seuil**, et la réparation est rapportée à l'appelant ([engine.py:44-46, 2907-2910](../../backend/app/core/payscript/engine.py)).
- **Identifiant inconnu refusé à la compilation** plutôt que valorisé à zéro ; indice de sous-jacent hors bornes refusé ([parser.py:432-443, 888-890](../../backend/app/core/payscript/parser.py)).
- **Hypothèses de marché datées** : politique de fraîcheur explicite, report de trois jours au plus ([market_policy.py](../../backend/app/core/market_policy.py)).

#### Faiblesses et biais résiduels

| # | Constat | Preuve | Conséquence |
|---|---|---|---|
| F1 | **Aucun mode de barrière en clôture quotidienne**, qui est la convention la plus courante d'une barrière américaine. Le défaut est la grille de diffusion, hebdomadaire à 52 pas | [schemas.py:236-239](../../backend/app/core/schemas.py), [pricing.js:315](../../frontend/src/stores/pricing.js) ; sonde D | Sur l'instance sondée, le PDI vaut 4,01 % en mode par défaut contre 4,20 % en observation quotidienne : **le put vendu par l'investisseur est sous-évalué de 19 pb, donc la note surévaluée d'autant**. Le mode continu le surévalue de 22 pb. Les grilles à 104 et 208 pas réduisent l'écart sans l'annuler |
| F2 | **La graine est forcée à 42** par un validateur, quelle que soit la valeur envoyée | [schemas.py:247-251](../../backend/app/core/schemas.py) | Reproductible, mais aucun prix ne peut être recoupé par un second tirage depuis l'écran. Seul l'IC renseigne sur le bruit |
| F3 | **Yahoo Finance est l'unique source** de cours, de dividendes et de volatilité historique, et les **fixings officiels en sont issus automatiquement** (politique `AUTO_YAHOO` étendue à tous les deals) | [market_data.py:103-104](../../backend/app/services/market_data.py), [database.py:860-918](../../backend/app/db/database.py), [main.py:134-136](../../backend/app/main.py) | Une constatation contractuelle repose sur une source non officielle et non licenciée pour un usage commercial. Le contrat d'interface par fournisseur existe ; un seul adaptateur est codé |
| F4 | **Aucune volatilité implicite de marché.** Le prix repose sur une volatilité historique ou saisie ; les modèles à smile se calibrent sur des points fournis par l'utilisateur | [volatility_surface.py:105](../../backend/app/core/volatility_surface.py), `smile_calibration.py` | La qualité numérique du moteur dépasse celle de ses entrées. Un prix Structura est un prix d'hypothèses, pas un prix de marché |
| F5 | **KID non conforme au règlement délégué.** La VEV est une approximation propre, `sqrt(−2·ln(p1)/T)`, et le scénario de tension est le 1er centile de la même distribution | [kid.py:292, 387-395](../../backend/app/api/kid.py) | SRI et scénarios sont indicatifs. Le calcul est à confronter aux annexes II et IV avant toute remise à un client |
| F6 | **Défaut à 20 000 paires.** Sur l'autocall de la sonde E, l'IC mesuré est de ±13,1 pb à 40 000 paires, soit environ ±18,5 pb au défaut | [schemas.py:221](../../backend/app/core/schemas.py) | Bruit du même ordre que beaucoup d'écarts que l'on cherche à lire entre deux cotations |
| F7 | **Taux saisis.** Le taux par défaut est 3 % ; aucune source de courbe n'a été trouvée dans cette lecture | [schemas.py:219](../../backend/app/core/schemas.py) | Non vérifié en détail : `market_snapshot.py` n'a pas été relu |
| F8 | **Fraction d'année unique**, jours divisés par 365,25 | [pricing.py:138-142](../../backend/app/api/pricing.py), [valuation_runs.py:57](../../backend/app/core/valuation_runs.py) | Convention assumée et versionnée ; à écrire dans les documents remis |
| F9 | **Performance** : évaluation du payoff en Python pur (A2) | Section 1.3 | Limite le nombre de trajectoires utilisable à l'écran, donc aggrave F6 |

### 2.3 Fonctions manquantes pour une plateforme professionnelle de produits structurés

1. **Données de marché licenciées** : cours, surfaces implicites, courbes de taux, source officielle de fixing par place.
2. **Barrière en clôture quotidienne**, ou décalage de barrière explicite sur la grille.
3. **Chaîne réglementaire de production** : KID conforme, EMT validé, term sheets par émetteur.
4. **Connecteur de booking et de confirmation** vers un système tiers, avec preuve de règlement.
5. **Dossier de validation indépendante** du moteur : formules fermées (commencé ici), puis cotations de banques sur cinq structures types.
6. **Moteur vectorisé**, pour passer de quelques secondes à quelques dizaines de millisecondes.
7. **Exploitation** : installation empaquetée, TLS, sauvegardes, supervision.
8. **Portail client en lecture seule** : notes de valorisation, cycle de vie, documents.

---

## 3. Sécurité, comptes et isolation

### 3.1 Ce qui est solide (vérifié dans le code)

- **Toute route métier exige une identité.** Sur les 435 routes de l'application, 14 sont ouvertes : six routes d'authentification, la santé, deux contrôles d'instance protégés par jeton, la réception RFQ signée, le logo, la page d'accueil et deux vocabulaires statiques ([interactions.py:253-255](../../backend/app/api/interactions.py), [opportunities.py:300-304](../../backend/app/api/opportunities.py)).
- **Sessions révocables** : jeton signé portant un identifiant unique et une époque de compte ; déconnexion par empreinte, « déconnecter partout » par incrément atomique de l'époque ([auth.py:105-167, 209-231](../../backend/app/api/auth.py)).
- **Jetons liés à l'installation** : émetteur, audience et organisation vérifiés ([auth.py:113-136, 145-155](../../backend/app/api/auth.py)).
- **Mot de passe** de 12 caractères au moins, changement forcé du mot de passe provisoire ([session_security.py:7-10](../../backend/app/core/session_security.py), [auth.py:156-158](../../backend/app/api/auth.py)).
- **Clé de signature** par machine, générée si absente, valeur d'exemple publiée refusée, 32 caractères au moins ([instance_signing.py:14-63](../../backend/app/core/instance_signing.py)).
- **Frein aux essais de connexion** par couple identifiant et adresse : verrouillage de 60, 300 puis 900 s ([auth.py:41-86](../../backend/app/api/auth.py)).
- **Aucun compte par défaut** : pas de mot de passe partagé créé au démarrage ([database.py:1012-1031](../../backend/app/db/database.py)).
- **Transport RFQ authentifié** : HMAC-SHA-256 par canal, HTTPS exigé hors boucle locale explicitement activée, expéditeur et destinataire liés, âge du message contrôlé, corps limité à 2 Mo ([services/rfq_transport.py:53-119](../../backend/app/services/rfq_transport.py), [api/rfq_transport.py:164-180](../../backend/app/api/rfq_transport.py)).
- **Accès développeur borné** : mode `DEVELOPMENT` et variable d'environnement requis, poste local seulement, ticket RS256 de 60 s, usage unique, audité ([hybrid/development.py:26-84](../../backend/app/hybrid/development.py), [auth.py:313-338](../../backend/app/api/auth.py)).
- **Téléversements** : limite de taille par intergiciel, nom de fichier réduit à sa base et préfixé d'un identifiant aléatoire ([main.py:76](../../backend/app/main.py), [documents.py:139-142](../../backend/app/api/documents.py)).
- **Aucun appel dangereux hors PayScript** : pas de `eval`, `pickle`, `yaml.load` ni `shell=True` dans `backend/app` ; les sous-processus sont lancés par liste d'arguments.
- **Sandbox PayScript** : tout identifiant du script est réécrit avant exécution, les fonctions natives sont vidées ([parser.py:48-49, 381-425](../../backend/app/core/payscript/parser.py)). Quatre tentatives d'injection ont été rejetées à la compilation pendant l'audit.
- **Jeton en `sessionStorage`, par onglet**, et adresse d'API restreinte à la boucle locale côté interface ([session.js:2-11](../../frontend/src/utils/session.js)). Un seul `v-html`, sur des libellés constants.

### 3.2 Risques

| # | Gravité | Constat | Preuve | Correction proposée |
|---|---|---|---|---|
| S1 | Moyenne | **Aucun en-tête de sécurité** : ni politique de contenu, ni interdiction d'encadrement, ni HSTS. Un seul `nosniff`, sur un téléchargement | Recherche dans tout le dépôt ; [deals.py:4122](../../backend/app/api/deals.py) | Intergiciel commun ; indispensable avant toute exposition réseau |
| S2 | Moyenne | **L'évaluation d'un script n'est pas bornée.** L'opérateur puissance et la répétition de chaîne traversent le transpileur : `9**9**9**9` ressort inchangé. Le budget de calcul ne voit que trajectoires et pas de temps | [parser.py:426-428](../../backend/app/core/payscript/parser.py) ; passage vérifié, expression non évaluée | Un utilisateur habilité au pricing peut bloquer un fil du serveur ou saturer la mémoire. Borner l'exposant, refuser les littéraux de chaîne, donner un délai au pricing interactif |
| S3 | Faible | **Le libellé d'un `PAY` est inséré tel quel dans le code généré**, seule l'apostrophe étant échappée | [parser.py:533-549](../../backend/app/core/payscript/parser.py) | Les trois variantes testées (barre oblique finale, sortie de chaîne, retour chariot) échouent à la compilation : pas d'exécution. Mais la protection tient à la parité des apostrophes, pas à une règle. Passer le libellé comme donnée |
| S4 | Moyenne hors poste individuel | **Jeton valable 7 jours**, sans renouvellement | [auth.py:37](../../backend/app/api/auth.py) | 8 à 12 heures avec renouvellement dès qu'une installation est partagée |
| S5 | Moyenne (confidentialité) | **Secrets en clair sur le disque** : clés des fournisseurs d'IA, clé de signature, identifiants d'amorçage, secret de canal RFQ en base | [llm/keys.py:26-54](../../backend/app/services/llm/keys.py), [api/rfq_transport.py:108-111](../../backend/app/api/rfq_transport.py) ; noms de fichiers dans `.runtime/` | Protection par le système (DPAPI ou trousseau) ; rotation des secrets de canal |
| S6 | Faible | **Journal d'audit non infalsifiable.** Écrit dans la transaction de l'action, ce qui est bien, mais ni chaîné ni protégé par déclencheur, alors que les preuves RFQ et les archives le sont | [audit.py:1-65](../../backend/app/core/audit.py) ; aucun déclencheur sur `audit_events` | Déclencheur d'immuabilité et chaînage par empreinte |
| S7 | Faible | **Frein de connexion en mémoire**, perdu au redémarrage, propre au processus | [auth.py:41-49](../../backend/app/api/auth.py) | Limite assumée et commentée ; à persister en multi-utilisateurs |
| S8 | Moyenne (confidentialité) | **Une description de produit peut partir chez un fournisseur d'IA externe** si une clé est configurée ; identifiants de modèles écrits en dur | [providers.py:53-66](../../backend/app/services/llm/providers.py) | Le défaut local est le bon. Ajouter un marquage par client et une liste de modèles en configuration |
| S9 | Faible | **Inscription publique**, quand elle est activée par variable d'environnement, laisse rejoindre une entité existante par son nom ; la route ne vérifie pas le profil de simulation que l'écran, lui, exige | [auth.py:253-258, 379-400](../../backend/app/api/auth.py) | Désactivée par défaut. Aligner les deux conditions |
| S10 | Faible | **Temps de réponse différent** selon que l'identifiant existe ou non | [auth.py:297](../../backend/app/api/auth.py) | Hachage factice pour les comptes inconnus |
| S11 | À qualifier | **Données possiblement réelles dans Git** : étude AMC sur ISIN réel à la racine ; organisations fictives portant des noms de banques réelles | Section 1.4 ; dossiers de `.runtime/hybrid-saas/` | Retirer l'étude de l'historique ; renommer les organisations avant toute démonstration à un tiers |
| S12 | Faible | **Aucune analyse des dépendances**, verrouillage limité aux 26 dépendances directes sur 96 paquets installés | [requirements.lock.txt](../../requirements.lock.txt), [ci.yml](../../.github/workflows/ci.yml) | Verrouillage complet par empreinte, `pip-audit` et `npm audit` en CI |

### 3.3 Isolation des données

- **Modèle** : une installation par organisation, avec sa propre base SQLite, sa propre clé de signature et des jetons liés à son identifiant. À l'intérieur, cloisonnement par entité puis par droits de desk sur les RFQ ([business_access.py:15-38](../../backend/app/services/business_access.py)). C'est un modèle plus fort qu'une base partagée filtrée par le code.
- **Limite de fait** : les six organisations sont des dossiers d'un même poste, sur des ports locaux. L'isolation physique n'existe pas encore ; seule sa conception existe.
- **Contrôle réparti** : les droits sont vérifiés dans chaque gestionnaire, sans table centrale. Le périmètre de lecture des deals est filtré en Python après chargement ([business_access.py:41-42](../../backend/app/services/business_access.py)).
- **Non vérifié** : énumération croisée d'identifiants entre deux entités sur chaque route. **Aucun test générique** ne parcourt les routes pour en éprouver la frontière ; les tests de permissions sont écrits domaine par domaine.

---

## 4. Base de données

### 4.1 Modèle

- **102 tables** SQLModel, dont 79 dans `db/models.py` ; 1 112 colonnes, 266 clés étrangères déclarées, 249 index, 68 contraintes d'unicité. Une table `Deal` de 56 colonnes.
- **99 colonnes de texte JSON** : paramètres, contextes de calcul, états avant et après.
- Bases annexes en SQL brut pour la plateforme, le contrôleur de simulation et les sessions de consultation.
- **Intégrité par déclencheurs** : immuabilité des preuves d'exécution RFQ, de la boîte d'envoi, des termes Product, des archives d'études et de documents ([rfq_execution_integrity.py](../../backend/app/db/rfq_execution_integrity.py), [product_migrations.py](../../backend/app/db/product_migrations.py), [archive_integrity.py](../../backend/app/db/archive_integrity.py)).

### 4.2 Constats

| # | Gravité | Constat | Preuve | Correction proposée |
|---|---|---|---|---|
| D0 | Point fort | **Les clés étrangères sont appliquées** à chaque connexion, avec un délai d'attente de 5 s | [database.py:28-36](../../backend/app/db/database.py) | — |
| D1 | **Élevée** | **Aucune sauvegarde périodique.** Les seules copies sont ponctuelles : avant adoption d'un espace Admin, script des études, copies de campagne. Sur ce poste, la base historique a une unique copie manuelle du 06/10, dans le même dossier | Recherche de `backup` dans `backend/app`, `scripts/`, `backend/scripts/` ; contenu de `backend/data/` (noms seuls) | Sauvegarde quotidienne par installation (`sqlite3.backup` puis `integrity_check`), rotation, restauration testée. Le modèle existe dans [studies_backup.py](../../backend/scripts/studies_backup.py) |
| D2 | Élevée | **Les tests ne tournent pas sous les contraintes de la production.** 70 fichiers de tests construisent leur propre base en mémoire ; 28 seulement évoquent l'intégrité. L'activation globale a été mesurée le 31/08 : 258 échecs et 148 erreurs sur 1 292 tests | [conftest.py:8-40](../../backend/tests/conftest.py) | Un défaut d'ordre de suppression peut être vert en test et échouer sur une vraie base — c'est déjà arrivé, selon ce même fichier. Basculer le défaut domaine par domaine |
| D3 | Moyenne | **Migrations écrites à la main, sans version de schéma.** Six cents lignes d'`ALTER TABLE` conditionnels rejoués à chaque démarrage ; deux marqueurs seulement dans `app_migrations` | [database.py:58-660, 943-975](../../backend/app/db/database.py) | Fichiers de migration numérotés et table de version ; figer l'état actuel comme base |
| D4 | Moyenne | **Pas de mode WAL.** L'API, l'ordonnanceur, la boucle de transport toutes les 2 s et les retours des lots écrivent dans le même fichier en mode journal par défaut | [database.py:28-36](../../backend/app/db/database.py) ; [main.py:205-223](../../backend/app/main.py) | `journal_mode=WAL` et `synchronous=NORMAL` sur disque local |
| D5 | Moyenne | **L'isolation des tests repose sur chaque test.** À l'import, le moteur SQL vise la base du poste ; la configuration commune ne redirige pas le dossier de données | [database.py:19-25](../../backend/app/db/database.py), [conftest.py](../../backend/tests/conftest.py) | Risque structurel, non constaté. Rediriger `STRUCTURA_DATA_DIR` vers un dossier temporaire pour toute la session |
| D6 | Structurelle | **SQLite et DDL propre à SQLite** (`PRAGMA table_info`, déclencheurs) | [database.py](../../backend/app/db/database.py) | Cohérent avec « une installation, une base ». Bloquant seulement pour une offre hébergée multi-clients |
| D7 | Faible | **151 appels à `datetime.utcnow()`**, dates naïves, API dépréciée depuis Python 3.12 | Inventaire statique | À traiter lors de la montée de version de Python |
| D8 | Faible | **Charges JSON non interrogeables** et croissance sans purge des runs de valorisation et d'audit | 99 colonnes JSON | Politique de rétention |

---

## 5. Interface et expérience utilisateur

> Analyse sur le code Vue. Aucun rendu navigateur n'a été observé pendant cet audit.

### 5.1 Constats vérifiés dans le code

| Thème | Constat | Preuve |
|---|---|---|
| Structure | 45 vues, 104 composants, 8 magasins d'état, syntaxe `<script setup>` partout, 48 imports paresseux dans le routeur | [router/index.js](../../frontend/src/router/index.js) |
| Erreurs | `try/catch` dans 101 fichiers ; erreurs de validation de l'API traduites en messages français par champ | [api.js:16-53](../../frontend/src/utils/api.js) |
| Chargement | Indicateurs d'attente dans 86 fichiers | Inventaire statique |
| Aide contextuelle | 339 usages de `HelpTip` dans 45 fichiers | Inventaire statique |
| Accessibilité | 245 attributs `aria-*` dans 65 fichiers, 161 rôles | Inventaire statique |
| Adaptation à l'écran | Points de rupture Tailwind dans 61 fichiers ; vues de desk à hauteur fixe | `meta.fixedViewport` du routeur |
| Changement de contexte | Requêtes en cours annulées au changement de session ; réponses tardives ignorées | [session.js:16-38](../../frontend/src/utils/session.js) |
| Propreté | Aucun `console.log`, aucun `TODO` | Inventaire statique |
| Tests | **997 tests réussis** en 19 s ; le build exécute les tests avant de construire | `npm test`, [package.json](../../frontend/package.json) |
| Bundle | Reconstruit hors dépôt : 118 fichiers, 3,5 Mo, empreintes identiques au bundle commité | `vite build --outDir` |

### 5.2 Problèmes et améliorations prioritaires

| # | Constat | Preuve | Amélioration |
|---|---|---|---|
| U1 | **Aucun gestionnaire d'erreur global.** Une exception de rendu, ou un fragment paresseux introuvable après une reconstruction, laisse un écran blanc | 0 occurrence de `errorHandler` ou `onErrorCaptured` ; [main.js:16-19](../../frontend/src/main.js) | Gestionnaire global avec rechargement proposé |
| U2 | **Le prix se lance et s'attend à l'écran**, sans délai ni annulation côté serveur (A3) | [pricing.py:114-120](../../backend/app/api/pricing.py) | File de calcul commune avec progression, déjà en place pour les lots |
| U3 | **Vues géantes** (A6) : plusieurs milliers de lignes par écran | Tailles de fichiers | Découpage par onglet |
| U4 | **40 vues sur 45 sans fichier de test** : la couverture porte sur la logique (magasins, utilitaires), pas sur les écrans | Inventaire statique | Cinq parcours de bout en bout automatisés |
| U5 | **Recettes d'interface manuelles** : scripts Playwright et agent `client-tester`, hors CI | `scripts/check_*_ui.py`, [TESTING_JOURNAL.md](TESTING_JOURNAL.md) | Les brancher sur la CI nocturne |
| U6 | Thème partiellement en dur : 469 styles en ligne dans 60 fichiers, 255 couleurs hexadécimales dans 30 | Inventaire statique | Faible priorité |
| U7 | **Affichage du bruit Monte Carlo** : avec le défaut à 20 000 paires (F6), l'IC mérite d'être sous les yeux à chaque prix | [schemas.py:221](../../backend/app/core/schemas.py) | Non vérifié à l'écran : contrôler que l'IC est visible sans ouvrir un détail |

Non revérifiés ici : les neuf anomalies corrigées de la recette graphique du 23/10, les contrôles à 390 px du 03/11, le journal de l'agent de recette.

---

## 6. Industrialisation

### 6.1 Tests — résultats de cette exécution

| Contrôle | Commande | Résultat |
|---|---|---|
| Inventaire backend | `pytest backend/tests --collect-only` | **4 393 tests** collectés en 20 s, sans erreur de collecte |
| Lot ciblé : moteur, liaisons PayScript, inscription, identité d'installation, permissions | `pytest` sur 5 fichiers | **159 réussis, 1 échec** sur 160 |
| Suite du front | `npx vitest run` | **997 réussis** dans 95 fichiers |
| Build du front | `vite build` vers un dossier temporaire | **Réussi**, empreintes identiques au bundle commité |
| Suite backend complète, lancée à la demande de Philippe le 17/11 | `pytest backend/tests` sur données isolées | **4 323 réussis, 69 échecs, 1 ignoré** en 3 042 s (50 min 42) |

### 6.1 bis Suite complète du 17/11 : lecture des 69 échecs

| Cause | Échecs | Nature | Preuve |
|---|---:|---|---|
| **Product Optimizer cassé depuis le 05/11.** `market_engine_kwargs` injecte `steps_per_year` (grilles de diffusion, commit `eca6f52`), mais `solve_for_param` ne connaît pas ce paramètre et n'est pas enveloppé par `with_simulation_grid`. Chaque candidat lève `TypeError`, absorbée et journalisée : la recherche se termine avec **tous les candidats en échec** | 27 | **Défaut de production** | [market.py:58-61](../../backend/app/core/product_optimizer/market.py), [simulation.py:72-80](../../backend/app/core/payscript/simulation.py), [service.py:172-176, 291-295](../../backend/app/core/product_optimizer/service.py) |
| **Générateur UAT cassé depuis le 24/10.** Le contrôle de booking qui exige le format et la famille juridique (note ou OTC) a été ajouté par `9115f65` ; le générateur réserve ses deals sans les fournir et chaque chaîne est refusée en 422 | 25 | **Défaut de production** (écran Admin) | [ccr/service.py:135-151](../../backend/app/core/ccr/service.py), pile d'appel `uat_generation.py:964 → deals.py:1645 → ccr/service.py:151` |
| **Fixtures de booking périmées** par le même contrôle : bookings directs, depuis un indicatif ou une RFQ, amendements, relevés de la fenêtre de départ, structure juridique sans client | 12 | Tests périmés ; le contrôle est voulu | `test_products`, `test_workflow_phase2`, `test_legal_identity_workflows`, `test_fixings_releves`, `test_rfq`, `test_client_chain` |
| **Attentes numériques ou de dates à requalifier** : zéro-coupon MTF (périmé, sonde F), décompte de points d'une fenêtre dégénérée (9 au lieu de 2), écart réduction par actif contre agrégat (0,17 % au lieu de plus de 0,2 %), projection optionnelle courte (657 au lieu d'absente) | 4 | Test périmé pour le premier ; **non qualifiés** pour les trois autres | `test_engine`, `test_constatations_periode`, `test_risk_c21` |
| **Démarrage d'une base ancienne** refusé faute d'installation configurée | 1 | Probablement induit par la variable `STRUCTURA_DATA_DIR` posée pour isoler l'audit ; à rejouer sans elle | `test_workflow_controls.py:1219` |

**Corrections du 18/11, sans commit.**

- **Optimizer** : `solve_for_param` et `compute_price_grid` portent désormais `@with_simulation_grid` ([simulation.py](../../backend/app/core/payscript/simulation.py)). Ils acceptent la grille et la transmettent à chaque `run_mc`. Un nouveau test exige qu'elle **fasse bouger le prix** d'un PDI à 104 et 208 pas, et que le paramètre résolu se reprice à l'identique sur cette grille (`test_simulation.py`, 8 réussis).
- **Générateur UAT** : `_book` déclare `EMTN`, `NOTE` et une référence de programme fictive ([uat_generation.py](../../backend/app/services/uat_generation.py)). Toutes les familles du générateur sont des notes. `test_uat_generation.py` : **37 réussis sur 37**.
- **Optimizer, fichiers rejoués** (9 fichiers de l'Optimizer, `test_review_fixes_2026_10_24`, `test_analytics_calendrier`, `test_simulation_grid`) : **315 réussis, 5 échecs**. Ces 5 échecs **préexistent** : ils échouent à l'identique sur le code du 01/11 (`312faae`, extrait hors dépôt), avant les grilles.
  - Cause : la tolérance en prix du solveur vaut 1e-6. C'est aussi le pas d'arrondi du prix publié par `run_mc`, et le paramètre publié est lui-même arrondi à six décimales.
  - Sur l'Athena plat, la bissection atteint 1,000001 pour une cible de 1, mais le coupon publié à 0,007835 se reprice à 1,000002. Le candidat est rejeté avec le motif « paramètre arrondi » ([service.py:30-37](../../backend/app/core/product_optimizer/service.py), [simulation.py:102-127](../../backend/app/core/payscript/simulation.py)).
  - **Défaut réel** : des candidats sont écartés pour un écart de 0,0002 % du nominal.
  - **Corrigé le 18/11, à la demande de Philippe, sans commit.** Relever la tolérance seule ne suffisait pas : un autocall gear put tombait à son tour sur la nouvelle borne, la bissection s'arrêtant exactement au seuil d'acceptation. Deux changements :
    - la bissection vise désormais **la moitié de la tolérance**, et le paramètre publié est contrôlé à la tolérance entière ([simulation.py](../../backend/app/core/payscript/simulation.py)) ;
    - la tolérance de l'Optimizer passe de 1e-6 à **1e-5 du nominal** (0,1 pb, cinquante fois sous la tolérance économique minimale), avec un budget d'itérations ajusté et une version de méthode `optimizer-v3-publication-tolerance`, pour que les recherches archivées restent identifiables ([contracts.py](../../backend/app/core/product_optimizer/contracts.py), [service.py:30-37](../../backend/app/core/product_optimizer/service.py)).
  - **Résultat** : l'Optimizer complet et tous les fichiers qui appellent le solveur (Optimizer, solveur, cohérence des analytiques, permissions, gouvernance des données) donnent **369 réussis sur 369**.

**Lecture.** Le 23/10, la suite était entièrement verte. Les deux livraisons suivantes ont chacune cassé un écran métier sans que rien le signale : la CI ne sélectionne que les tests dont les fichiers ont changé, et la suite complète n'a pas été rejouée. C'est la démonstration du risque n° 1 de la synthèse.

**Durée.** 3 042 s contre 1 500 s le 23/10, pour 10 % de tests en plus. Aucun fichier n'explique seul l'écart : les douze plus lents totalisent environ 1 460 s (cohérence des analytiques 203 s, générateur UAT 196 s, MtM avant strike 165 s). La suite tourne sur un seul processus, `pytest-xdist` n'étant pas installé. Le chiffre de « six minutes » de `CLAUDE.md` est périmé.

**L'échec.** `test_engine.py::test_mtf_zcb_is_deterministic` attend une actualisation arrondie à la semaine ; le moteur actualise aux dates exactes depuis le 24/10. La sonde F montre que **le moteur est juste et que le test est périmé**. L'écart est de 2,4 pb. Le test date du premier commit ; `engine.py` a été modifié par les trois dernières livraisons sans que ce fichier de tests soit rejoué.

Ce n'est pas un défaut de prix. C'est la preuve que **`main` porte un test rouge dans le fichier de tests du moteur, et que rien ne l'a signalé**.

**Note d'environnement.** Un premier passage a donné 11 erreurs de préparation : le dossier temporaire par défaut de pytest était inaccessible dans cette session. Rejoués avec un dossier temporaire explicite, ces 11 tests passent. Sans rapport avec le code.

**Structure de la suite.** 70 fichiers sur 198 montent leur propre base en mémoire. Les tests du moteur recoupent des formules fermées, ce qui est rare et précieux. Manques : pas de mesure de couverture, pas de test de bout en bout en CI, pas de test générique de frontière d'accès, intégrité référentielle inactive dans la majorité des fichiers (D2).

### 6.2 CI et livraison

| Élément | État | Preuve |
|---|---|---|
| Déclenchement | Sur demande de fusion et à la main. **Rien sur un commit direct** | [ci.yml:3-14](../../.github/workflows/ci.yml) |
| Périmètre | Tests **sélectionnés** d'après les fichiers modifiés ; suite complète sur demande manuelle seulement | [ci.yml:40-66](../../.github/workflows/ci.yml), [select_tests.py](../../.github/scripts/select_tests.py) |
| Dernière suite backend complète | **23/10/2026**, 3 943 succès, sur un arbre non commité à cette date. Depuis : environ 450 tests de plus, trois livraisons | [BACKEND_FULL_VALIDATION_2026-10-23.md](BACKEND_FULL_VALIDATION_2026-10-23.md) ; collecte du jour |
| Analyse statique | **Absente** : ni lint, ni typage, ni formateur | Aucun fichier de configuration |
| Sécurité des dépendances | **Absente** | — |
| Déploiement | **Absent** : ni conteneur, ni paquet, ni installateur, ni artefact de livraison | Recherche de fichiers |
| Versions | Aucune étiquette ; trois numéros de version différents (A9) | `git tag` |
| Dépendances | 26 dépendances directes épinglées, 70 transitives libres ; `playwright` absent du verrou ; `pytest` et `playwright` dans les dépendances d'exécution ; pandas 2.0, numpy 1.26, scipy 1.11 | [requirements.lock.txt](../../requirements.lock.txt), [requirements.txt](../../requirements.txt) |

### 6.3 Journalisation et supervision

- **Aucune configuration de journalisation** dans tout le dépôt. 11 journaux nommés, 19 appels dans 7 fichiers ; 7 écritures seulement conservent la trace d'appel. Sans configuration, seuls les avertissements et les erreurs atteignent la sortie d'erreur.
- **163 `except Exception` dans 54 fichiers, 57 blocs qui absorbent l'erreur** sans rien écrire.
- La sortie de chaque installation est redirigée vers un fichier par le lanceur, sans rotation.
- Sonde de santé présente, sans contrôle de la base. Ni métriques, ni alerte.
- Les **événements métier**, eux, sont tracés : 132 points d'écriture d'audit dans 36 fichiers.

### 6.4 Reprise

| Scénario | Procédure | État |
|---|---|---|
| Arrêt du serveur à l'heure du fixing | Rattrapage au démarrage | Présent, **non exercé** |
| Recherche d'optimisation interrompue | Reprise au démarrage | Présent, **non exercé** |
| Message RFQ non remis | Boîte d'envoi persistante, relance | **Opérationnel** en local selon les recettes du 24/10, non rejoué |
| Adoption d'une ancienne base | Sauvegarde et contrôle d'intégrité préalables | Présent, **non exercé** |
| Perte ou corruption d'une base | — | **Absent** (D1) |
| Reprise sur un autre poste | Code par Git ; données privées par procédure manuelle | **Partiel**, décrit dans le rapport du 01/11 |

---

## 7. Documentation contre implémentation

| Document | Ce qu'il annonce | Réalité constatée |
|---|---|---|
| [CLAUDE.md](../../CLAUDE.md), conventions de pricing | Quatre dates, funding en actualisation seule, magnitudes d'instance | **Exact.** La règle du funding est recoupée sur un autre produit (sonde E) |
| `CLAUDE.md`, mémoire | Dernier point de reprise : 27/08 | **Périmé.** Une reprise du 13/10 et un rapport du 01/11 existent |
| [README.md](../README.md) | Index des notes, « rien à la racine » | Index de 1 073 lignes devenu journal ; règle de racine non tenue (1.4). États honnêtes, note par note |
| [RAPPORT_PROJET_ET_REPRISE_2026-11-01.md](RAPPORT_PROJET_ET_REPRISE_2026-11-01.md) | Base sérieuse, priorité à la cohérence ; KID et EMT « indicatifs » | **Exact et prudent** ; cet audit le confirme et le chiffre |
| [BACKEND_FULL_VALIDATION_2026-10-23.md](BACKEND_FULL_VALIDATION_2026-10-23.md) | 3 943 succès, aucun échec | Vrai à sa date, non revérifié. **Plus vrai aujourd'hui** : au moins un échec |
| [INSTITUTIONAL_ACCEPTANCE_2026-10-24.md](INSTITUTIONAL_ACCEPTANCE_2026-10-24.md) | Recette de 100 M EUR, six banques | **Simulé**, déclaré tel : banques fictives, installations locales |
| Notes du socle SaaS hybride (13/10) | Étapes 1 à 4 livrées, 5 partielle, 6 à 8 ouvertes ; registre et facturation non livrés | Conforme au code lu |
| Notes de la grille de diffusion et du LSV résiduel (05/11) | Grilles 52/104/208, levier figé | Présent dans le code ([simulation_grid.py](../../backend/app/core/simulation_grid.py)) ; recettes non rejouées |
| [AUDIT_CONVENTIONS_PRICING_2026-09-08.md](AUDIT_CONVENTIONS_PRICING_2026-09-08.md) | Les magnitudes sont des mesures d'instance | Confirmé : −12,7 pb de taux ici, contre −41 pb sur leur autocall |

**Constat de fond.** La documentation est abondante (214 notes), datée et franche sur ses limites : c'est une force réelle. Son défaut est l'empilement. Trente-sept notes d'audit portent la mention « sans commit » ; leurs corrections ont ensuite rejoint le dépôt d'un seul bloc. Le document qui fait foi sur l'état du jour n'existe pas : il faut le reconstituer de note en note.

---

## 8. Dynamique du projet

- **62 commits** du 1er juillet au 5 novembre 2026 : 16, 7, 22, 14 puis 3 par mois. Trois identités d'auteur pour une seule personne. Développement mené par agents, avec consignes versionnées (`AGENTS.md`, `.agents/skills/`, `.claude/agents/`).
- **Commits géants.** Celui du 24/10 touche 774 fichiers et ajoute 443 504 lignes ; il réunit 27 chantiers de remédiation et 21 correctifs. Les trois dernières livraisons touchent de 186 à 261 fichiers chacune. Aucune correction ne peut être isolée, relue ou annulée seule.
- **Un seul connaisseur humain** du système.
- **Le contrôle ne suit plus la cadence** : suite complète non rejouée depuis le 23/10, test rouge sur `main` non vu, CI muette sur les commits directs.

---

## 9. Roadmap priorisée

Effort : **S** ≤ 2 jours · **M** ≤ 2 semaines · **L** > 2 semaines.

### P0 — Avant toute démonstration à un tiers ou tout second utilisateur

| # | Problème et impact | Fichiers ou modules | Solution recommandée | Effort | Dépendances |
|---|---|---|---|---|---|
| P0-0 | **Deux écrans cassés en production** : Product Optimizer depuis le 05/11, générateur UAT depuis le 24/10 (6.1 bis) | `core/payscript/simulation.py:72`, `services/uat_generation.py:964` | **Corrigé le 18/11, non commité** ; les 52 tests concernés repassent | S | — |
| P0-0 bis | Candidats de l'Optimizer rejetés pour un écart d'arrondi de 1e-6 (6.1 bis), 5 tests rouges depuis au moins le 01/11 | `core/product_optimizer/contracts.py`, `service.py:30-37`, `core/payscript/simulation.py` | **Corrigé le 18/11, non commité** : recherche à la demi-tolérance, tolérance de 1e-5, version de méthode v3 | S | — |
| P0-1 | 69 échecs sur `main` (6.1 bis) | 12 fixtures de booking, 4 attentes numériques, 1 test de démarrage | Mettre les fixtures au contrôle juridique ; qualifier puis corriger les trois attentes non expliquées ; aligner le zéro-coupon sur `exp(−r·(T−t))` ; rejouer la suite complète | M | P0-0 |
| P0-2 | Rien n'impose de contrôle à la livraison (6.2, 8) | `.github/workflows/ci.yml` | Suite complète **nocturne sur GitHub**, qui ne coûte rien au poste et respecte la règle locale des tests ciblés ; déclenchement sur `main` ; branche protégée | S | Dépôt GitHub |
| P0-3 | Perte de données possible (D1, D4) | `db/database.py:28-36`, lanceur, ordonnanceur | Sauvegarde quotidienne par installation avec contrôle d'intégrité et rotation ; restauration testée ; mode WAL | S | — |
| P0-4 | Barrière américaine mal servie par les deux modes (F1) : note surévaluée de 19 pb sur l'instance | `core/payscript/bridge.py`, `engine.py`, `schemas.py:239`, `MarketParams.vue:165` | Troisième mode « clôture quotidienne » par décalage de barrière sur la grille ; mode affiché dans chaque document ; sonde D ajoutée aux tests | M | — |
| P0-5 | Documents réglementaires indicatifs sans marquage garanti (F5) | `api/kid.py`, `api/emt.py`, écrans associés | Mention « indicatif, non conforme » imposée par le serveur sur tout KID et EMT, jusqu'à P1-2 | S | — |
| P0-6 | Dépôt alourdi et pièces possiblement sensibles (1.4, S11) | `frontend/dist`, `backend/_srv_*.log`, `tmp/pdfs`, `scratchpad_*` | Ne suivre qu'une génération du bundle, ou le construire à l'installation ; retirer journaux et fichiers de travail ; décider du sort de l'étude AMC dans l'historique | S | Décision sur la réécriture d'historique |
| P0-7 | Script capable de bloquer le serveur (S2, S3) | `core/payscript/parser.py:355-429, 533-549` | Borner l'opérateur puissance, refuser les littéraux de chaîne dans les expressions, passer le libellé comme donnée ; délai sur le pricing interactif | S | — |
| P0-8 | Livraisons non nommables (A9) | `main.py:73, 238`, `frontend/package.json` | Une seule source de version ; étiquette Git à chaque livraison | S | — |

### P1 — Rendre l'outil exploitable par un tiers accompagné

| # | Problème et impact | Fichiers ou modules | Solution recommandée | Effort | Dépendances |
|---|---|---|---|---|---|
| P1-1 | Source unique et non officielle (F3, F4, F7) | `services/market_data.py:103-120`, `core/volatility_surface.py`, `core/fixing_finality.py` | Second adaptateur par fichiers d'un fournisseur licencié ; import de surfaces implicites et de courbes avec provenance ; fixing officiel par place ; toute valorisation issue de Yahoo marquée comme indicative | M à L | Choix et contrat fournisseur |
| P1-2 | KID non conforme (F5) | `api/kid.py` | Méthodologie de catégorie 3 : simulation réglementaire, VEV du règlement, scénario de tension à volatilité stressée ; recoupement sur des exemples publiés | M | P1-1 pour les historiques |
| P1-3 | Aucune preuve externe de justesse | Nouveau dossier de validation | Intégrer les sondes A à F aux tests ; ajouter SABR, Local Vol, LSV et les Greeks ; recouper cinq structures contre des cotations de banques | M | Disponibilité de cotations |
| P1-4 | Pricing lent et bloquant (A2, A3, F6, F9) | `engine.py` (`_eval_paths`), `parser.py`, `api/pricing.py` | Évaluation vectorisée du payoff pour les familles standard ; pricing interactif passé par la file de calcul, avec délai et annulation ; défaut de trajectoires relevé ensuite | L | P1-3 comme filet |
| P1-5 | Monolithe du cycle de vie (A1) | `api/deals.py` | Extraire événements, amendements, propositions, Greeks et valorisation vers des services | L | P0-1 |
| P1-6 | Tests hors contraintes de production (D2, D5) | `backend/tests/conftest.py`, 70 fichiers | Intégrité activée par défaut, domaine par domaine ; dossier de données redirigé pour toute la session | M | — |
| P1-7 | Migrations sans version (D3) | `db/database.py:58-660` | Base figée, migrations numérotées, table de version | M | P0-3 |
| P1-8 | Protections web et secrets (S1, S4, S5, S6, S12) | `main.py`, `api/auth.py`, `core/audit.py`, `services/llm/keys.py` | En-têtes ; jeton court avec renouvellement ; secrets protégés par le système ; audit chaîné ; verrouillage complet et analyse des dépendances | M | — |
| P1-9 | Diagnostic impossible (6.3) | Démarrage, ordonnanceur, transport | Journalisation configurée, fichier tournant par installation, trace d'appel sur toute erreur absorbée, santé avec contrôle de la base | S | — |
| P1-10 | Écran blanc et écrans non testés (U1, U3, U4, U5) | `main.js`, vues géantes, `scripts/check_*_ui.py` | Gestionnaire d'erreur global ; découpage des trois plus grandes vues ; cinq parcours de bout en bout en CI nocturne | M | P0-2 |
| P1-11 | API non typée (A4) | Routeurs principaux, `frontend/src/utils` | Modèles de réponse sur les vingt routes les plus utilisées ; client généré | M | — |

### P2 — Passage à plusieurs organisations réelles

| # | Problème et impact | Fichiers ou modules | Solution recommandée | Effort | Dépendances |
|---|---|---|---|---|---|
| P2-1 | Aucun déploiement hors du poste de développement | `scripts/launch_structura.py`, `hybrid/deployment.py` | Installation empaquetée et versionnée ; TLS ; portage Linux qualifié | L | P0-8, P1-9 |
| P2-2 | Réseau RFQ jamais sorti du poste | `services/rfq_transport.py`, `api/rfq_transport.py` | Deux machines réelles : TLS, horloges, rotation des secrets, reprise après coupure | M | P2-1 |
| P2-3 | Contrôle d'accès réparti et non éprouvé route par route (3.3) | 46 routeurs, `core/access.py` | Table déclarative des droits par route et test générique d'énumération croisée | M | P1-5 |
| P2-4 | Identité locale seulement | `api/auth.py`, `hybrid/platform.py` | Authentification déléguée et second facteur pour les administrateurs d'organisation | M | P2-1 |
| P2-5 | Registre central et facturation prévus, non réalisés | Notes du 13/10 | À réaliser seulement si le modèle économique le demande | L | Décision commerciale |
| P2-6 | Supervision absente | Nouveau | Métriques, alerte sur fixing manqué et sur donnée périmée | M | P1-9 |
| P2-7 | SQLite seul (D6) | `db/` | Option PostgreSQL, uniquement pour une offre hébergée | L | P1-7 |

### P3 — Différenciation commerciale

| # | Problème et impact | Fichiers ou modules | Solution recommandée | Effort | Dépendances |
|---|---|---|---|---|---|
| P3-1 | Pas de portail client | Front, droits | Lecture seule : notes de valorisation, cycle de vie, documents | M | P2-1 |
| P3-2 | Booking fermé sur lui-même | `api/deals.py`, `api/trading.py` | Premier connecteur vers un système de booking ou de confirmation, avec un client pilote | L | Client pilote |
| P3-3 | Chaîne documentaire incomplète | `api/kid.py`, `api/emt.py`, PDF | KID, EMT et term sheets de production, par émetteur | M | P1-2 |
| P3-4 | Crédit émetteur saisi à la main | `engine.py` (funding), CCR | Courbes de funding par émetteur sourcées ; ajustements de valeur au-delà du CCR actuel | L | P1-1 |
| P3-5 | Marché secondaire non outillé | `inlife_valuation.py`, `roll_economics.py` | Politique d'écart acheteur-vendeur et de rachat, à partir du MtM résiduel existant | M | P1-1 |
| P3-6 | Offre hébergée multi-clients | Toute la pile | À ne viser qu'après un premier client payant en installation privée | L | P2-1 à P2-7 |

### Ordre conseillé

1. **Tout de suite** : P0-0, puis P0-1. **Deux semaines** : P0-2, P0-3, P0-6, P0-7, P0-8 — un état vert, un garde-fou, des sauvegardes, un dépôt propre.
2. **En parallèle, côté métier** : P0-4 et P0-5 — la barrière et le marquage des documents, seuls points P0 qui touchent un chiffre remis à un client.
3. **Deux à trois mois** : P1 dans l'ordre 3, 1, 9, 8, 6, 4, 2, 10, 7, 5, 11.
4. **Ensuite** : P2 seulement si un tiers doit recevoir une installation ; sinon P3-1 et P3-5, qui valorisent le moteur sans exiger de réseau.
