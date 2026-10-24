# Contre-revue de Structura — validité métier et quantitative

**Photographie du 24 octobre 2026 — Europe/Berlin.**

**Objet :** contre-revue indépendante du dossier `APPLICATION_REVIEW_2026-10-24.md` et de ses
annexes, selon le prompt `application-review-2026-10-24/REVIEW_PROMPT.md` : distinguer les défauts
établis, les défauts probables à reproduire, les limites assumées, les limites mal annoncées, les
conventions métier et les preuves insuffisantes.

**Référence Git :** branche `codex/hybrid-saas-foundation`, HEAD `7dce3021a88feb4f0021ca3de8f3596277bc72a5`,
plus 666 entrées modifiées ou non suivies dans l'arbre de travail.

**Nature de ce travail :** lecture du dossier et de ses preuves historiques, relecture du code dans
l'arbre de travail avec contrôle d'empreintes contre `SOURCE_MANIFEST.json`, cinq sondes exécutées sur
le moteur seul, et deux consultations de sources réglementaires primaires. Aucun pytest, aucun build,
aucun service démarré, aucune base ouverte, aucun téléchargement de marché.

Le cœur contractuel et quantitatif de Structura est solide et explicitement borné : funding hors du
drift, estimateur antithétique correct, domaines non supportés refusés plutôt que dégradés,
approximations auto-étiquetées. Les défauts que cette revue établit se concentrent là où une
hypothèse de marché saisie n'atteint pas le calcul publié — KID, solveur général, Mark-to-Future — et
sur un indicateur de risque PRIIPs dont la statistique n'est pas celle des bandes réglementaires
auxquelles elle est comparée.

## Périmètre et méthode

Cette revue ne s'arrête pas au dossier : le dépôt lui-même était accessible, et les quatorze fichiers
cités ici portent la même empreinte SHA-256 que `SOURCE_MANIFEST.json`. Les constats sont donc lus
dans la photographie que le rapport décrit, et non dans des extraits.

**Exécuté.** Quatre sondes, dans un script jetable hors dépôt, moteur seul : aucun service démarré,
aucune base ouverte, aucun appel réseau, N ≤ 8 000 paires.

| Sonde | Oracle | Résultat |
|---|---|---|
| `run_mc(per_path_flows=True, antithetic=False)` | un appel légal du contrat public doit répondre ou lever une erreur métier | aucune exception ; le commentaire de l'Optimizer qui annonce un `UnboundLocalError` est périmé |
| VEV du module contre l'expression de l'annexe II | arithmétique pure, `_mrm_from_vev` et `_sri` recopiées du fichier | VEV du code entre 2,1 × et 12,3 × la VEV RTS ; SRI surévalué de 1 à 3 crans |
| BRC 3 ans, barrière américaine 70 %, 16 000 jambes | hebdomadaire contre continu, funding 0 contre 150 bp | percentiles KID inchangés ; PV −23 bp (monitoring) et −404 bp (funding) |
| `solve_for_param` sur une digitale, `tol = 1e-4` | un drapeau de convergence en prix ne doit pas être vrai au-dessus de sa tolérance | `converged = True` avec un résidu de prix de 2,5 × `tol` |

**Annexes et preuves historiques.** Lues dans un second temps, et elles ont corrigé trois de mes
constats : les dix rapports de `reference-evidence/`, `DOCUMENTARY_EVIDENCE.json`,
`INSPECTION_REFERENCE.json`, et les sections du `TEST_CATALOGUE.md` portant sur le KID, l'EMT, le
solveur et le Mark-to-Future. Les catalogues `DATA_MODEL`, `MODULE_CATALOGUE`, `API_CATALOGUE` et
`CRITICAL_SOURCE_EXCERPTS` n'ont pas été lus : ayant le dépôt, j'ai vérifié dans les fichiers complets
plutôt que dans leurs extraits.

**Cinquième sonde, ajoutée après cette lecture.**
`remediation-lot-0-2026-10-20/BACKEND_FULL_VALIDATION.json` fige les empreintes des 443 sources
backend avant le passage complet du 23 octobre. Comparaison avec l'arbre de travail : les quatorze
fichiers qui portent mes constats sont **inchangés**, seul `api/deals.py` a bougé depuis.

**Non exécuté.** Aucun pytest, ciblé ou complet. Aucun build frontend, aucun parcours navigateur,
aucun téléchargement de marché, aucune campagne de simulation. La lecture de code est par chemin
critique, pas ligne par ligne sur les 155 000 lignes. Tout cas de la section E est un **test
proposé**, jamais un résultat.

**Ancrage réglementaire.** L'annexe II du règlement délégué (UE) 2017/653 a été lue dans le rendu
FCA : les bandes MRM 1–7 et la base du VaR catégorie 3 (confiance 97,5 %, actualisation au facteur
sans risque attendu, 10 000 simulations minimum) y sont textuelles. La formule de VEV y est une
image : sa parenthèse vient d'une source secondaire et est signalée comme telle. L'annexe IV est
supprimée dans ce rendu, et les sources consultées divergent sur les percentiles du scénario de
tension : la version applicable reste une question ouverte, traitée comme telle.

## A — Appréciation générale

Le moteur de diffusion et le dossier contractuel ne sont pas là où sont les défauts. Les trois
défauts établis par cette revue sont tous le même : un module dérivé — KID, Mark-to-Future, solveur —
reconstruit un contexte au lieu de recevoir celui du prix, et publie un chiffre sous une autre
hypothèse que celle affichée à côté.

**Ce qui tient, et qui est vérifiable en lecture.**

- Le funding reste hors du drift et n'agit que sur l'actualisation, avec la raison écrite au-dessus du
  code (`engine.py:1192`). Le contrôle de magnitude de `CLAUDE.md` est reproductible sur n'importe
  quel produit.
- L'estimateur antithétique est juste : prix et erreur type sur les N paires, distribution et
  quantiles sur les 2N jambes (`engine.py:2674-2691`). C'est la convention correcte, et elle est
  rarement écrite correctement.
- Le pont brownien s'auto-étiquette — `joint_extrema_exact: false`, `per_run_error_bound: null`,
  `qualification: local_synthetic_panel_only` — et refuse le domaine panier non qualifié plutôt que de
  retomber en hebdomadaire (`bridge.py:32`, `:181`).
- `position_sign` lève sur un sens inconnu au lieu de retomber sur un `else` silencieux
  (`db/models.py:1187`). La convention banque est donc traçable, pas devinable.
- VaR et ES sortent d'une seule définition, avec pondération fractionnaire du scénario de frontière :
  ES ≥ VaR par construction (`var_engine.py:383`).
- La CVA refuse une PD non risk-neutral, un recouvrement inconnu et toute extrapolation de courbe
  courte (`ccr/exposure.py:86`).

**Les trois blocages.**

1. **Le KID.** Pas parce qu'il est non conforme — c'est annoncé — mais parce que la non-conformité est
   annoncée sans son sens ni son ampleur, et ne survit pas à l'écran. Ni la réponse de l'API, ni le
   `KidRecord` conservé, ni l'EMT qui consomme le SRI ne portent le drapeau. Un SRI surévalué d'un à
   trois crans circule ensuite comme un chiffre.
2. **Le Mark-to-Future.** Le garde `_mtf_reject_unsupported` refuse courbe de taux, taux
   stochastiques, courbe de dividende, LSV et monitoring continu — pour ne pas comparer un éventail à
   un P₀ sur une autre base d'actualisation. Le spread émetteur n'est ni porté ni refusé : il n'est pas
   un paramètre de la fonction. Le défaut fermé pour la courbe de taux reste ouvert pour le funding,
   mesuré à 404 bp.
3. **Le solveur général.** `converged` est vrai dès que la demi-largeur d'intervalle passe sous `tol`,
   alors que l'infobulle de l'écran définit `tol` comme un écart de prix. Le même nombre sert dans
   deux unités.

**Et la suite complète ne les voit pas.** Les quatorze fichiers qui portent ces constats sont
identiques, octet par octet, aux empreintes figées avant le passage du 23 octobre — 3 943 tests
réussis, aucun échec. La suite passe donc sur exactement ce code. Le point aveugle est localisé, pas
général : passage des arguments du KID, critère de convergence du solveur, funding absent du
Mark-to-Future, détection de levier EMT, défauts du cœur FIFO. Deux tests visent pourtant la bonne
propriété — leur oracle est trop lâche ou leur domaine trop étroit, ce que la section C détaille.

**Ce que cette revue ne peut pas conclure.**

- Si les prix sont justes. Aucun invariant analytique n'a été exercé dans cette session. Le dossier en
  contient pourtant : C15 contrôle PAY 1 contre exp(−0,05) et un forward prépayé à moins de trois
  erreurs standards de exp(−0,01) ; C16 compare un franchissement conditionnel à 8,29388 %
  analytiques ; C17 confronte son Fourier Heston à une référence Riccati indépendante, sous 2e−8 du
  nominal. Ce qui manque est le raccordement : le Monte Carlo de production n'est pas comparé à ce
  Fourier, et C17 l'écrit.
- La conformité PRIIPs actuelle. La version applicable n'est pas établie : l'annexe IV est supprimée
  dans le rendu lu et les sources divergent sur les percentiles de tension.
- La chaîne RFQ, transport et rapprochement. Lue, non exercée. Les recettes datées sont crédibles et
  honnêtement bornées, mais ce sont des recettes locales.
- AMC et FIFO. Vérifiés par constantes et par valeurs par défaut ; aucun rapprochement NAV exécuté.

## B — Carte de validité par domaine

Le niveau de preuve suit l'échelle du rapport lui-même : code présent, test source, résultat daté,
qualification d'usage. Aucun domaine n'atteint ici le quatrième niveau, et c'est normal : il ne
s'obtient pas en lisant du code.

| Domaine | Usage justifié | Restrictions à tenir | Preuve | Décision d'usage | À valider |
|---|---|---|---|---|---|
| Payoff PayScript | Décrire et évaluer un payoff dont le texte est validé | Syntaxe valide n'est pas bon contrat ; `exec` en espace restreint, non audité en adversarial | Code + 2 545 définitions de tests, aucune exécution ici | Utilisable | Égalité au seuil, mémoire de coupons, double paiement du capital |
| Calendriers | Résoudre puis figer des dates par place et devise | Convention saisie, jamais devinée ; défaut Modified Following subsistant dans le helper bas niveau | Code + référentiel `holidays` | Utilisable | all-open contre any-open, stubs, J+0 et J+3, fermetures exceptionnelles |
| MC GBM | Prix, flux et IC95 sous hypothèses explicites | ACT 365,25 et environ 52 pas par an ; courbe de dividende en buckets annuels non croissants seulement | Code + estimateur vérifié en lecture | Utilisable | Martingale, vanille analytique, convergence en pas de temps |
| Heston, SABR, Dupire, LSV | Explorer un prix sous une dynamique nommée | Planchers et écrêtages modifient la dynamique ; surface cible synthétique ; `production_approved=false` | Code + seuils locaux C16 et C17 | Exploration seulement | Fourier indépendant, ailes SABR, couverture de l'IC LSV par réplications |
| Barrières continues | Barrière américaine mono-actif GBM, panier GBM à deux actifs | Loi jointe approximative, aucune borne d'erreur par run, tolérance de panel 10 bp | Code auto-étiqueté + panel local | Utilisable sous restriction | Franchissement analytique ; mono-actif sous Heston ou LSV, non borné |
| Greeks | Sensibilités finies à définition explicite, état réalisé conservé | `N_g = max(1000, N//4)` : plus bruités que le prix ; vega Heston partiel | Code + portées publiées | Utilisable sous restriction | Vega par bump de paramètres, theta la veille d'un événement |
| Solveur général | Trouver un paramètre encadré par les bornes | `converged` peut être vrai au-dessus de la tolérance de prix | Code + sonde, résidu 2,5 fois `tol` | Non qualifié tant que le critère n'est pas en prix | Rien à valider : corriger |
| Données de marché | Historique local réutilisé, fraîcheur 3 jours, fixings non ajustés | Yahoo seul ; réalisée n'est pas implicite ; pas d'archive point-in-time | Code + politique versionnée D03 | Utilisable pour l'indicatif | Mode sans réseau, IPO dans un panier ancien, split et dividende exceptionnel |
| Product, RFQ, booking | Geler des termes, des tours et des cotations, inscrire un deal | Le reçu atteste ce que cette instance a calculé, pas la qualité du modèle | Code + recettes datées des 23 et 24 octobre | Utilisable en local | Concurrence, révision périmée, antidatage d'une acceptation |
| Fixings et cycle de vie | Officialiser une observation avec preuve et version | Une clôture quotidienne ne prouve pas un franchissement intraday ; décision D06 ouverte | Code + registres versionnés | Utilisable sous gouvernance | Correction après consommation, fenêtre partielle, moyenne incomplète |
| MtM résiduel, archives, explain | Rejouer le passé et valoriser le reliquat | Explain est une chaîne télescopique ordonnée, pas une attribution de Shapley ; une créance n'est pas du cash | Code + tests nommés | Utilisable | Réconciliation exacte, deux PAY identiques, créance avant paiement |
| Risque et stress | Agréger des sensibilités homogènes, choquer un contexte canonique | Couverture publiée par métrique ; vegas séparés par portée | Code | Utilisable sous restriction | Vega mixte, FX absent, limite sur la position après amendement |
| VaR et ES | Mesure économique de queue sur scénarios explicites | Un seul choc de corrélation scalaire global ; en paramétrique un seul choc de vol pour tous les sous-jacents ; horizons chevauchants | Code + convention de quantile vérifiée | Pilotage interne | Queue fractionnaire sur P&L connus, scénario ou deal manquant |
| CCR économique | EE, EPE, PFE et CVA sous hypothèses déclarées | Indépendance défaut-exposition ; collatéral sur grille ; pas de SA-CCR ; actualisation CVA scalaire | Code + absences explicites | Limites internes | Netting inadmissible, créance courte, métrique bloquante sans donnée |
| Optimizer | Explorer une grille finie de huit familles | GBM seul, devise unique, protection européenne ; une grille finie n'est pas un optimum | Code + validation N et 2N à graines distinctes | Utilisable pour la recherche | Multiplicité, convergence temporelle, plateau de prix |
| Mark-to-Future | Distribution de valeurs futures en domaine restreint | Le funding n'est ni porté ni refusé ; taux plat ; biais de simulation imbriquée | Code + sonde, 404 bp sur l'instance | Non qualifié en présence de funding | Corriger ou refuser, comme pour la courbe de taux |
| KID et EMT | Analyse interne de scénarios et de profil | VEV hors RTS, percentile 1 %, montant non actualisé, colonne de tension sans volatilité stressée | Code + sonde arithmétique | Analyse interne, jamais une distribution | Reprendre la statistique ou retirer les bandes MRM |
| AMC, FIFO, scores | Reconstruire un carnet et décrire une gestion | `strict` au manifeste mais `t0_synthetic` par défaut dans le cœur ; score descriptif | Code + constantes vérifiées | Exploration documentée | Rapprochement NAV, FIFO contrôlé à la main, splits et unités |
| Exploitation hybride | Installations privées, transport signé, consultation en lecture seule | Manifestes DEVELOPMENT ; verrous mémoire mono-worker ; HMAC n'est pas une signature à non-répudiation | Code + recettes datées | Développement seulement | Multi-site, restauration, rotation de clés, charge |

## C — Registre des constats

Vingt constats, dont six établis en catégorie A. Les gravités les plus hautes sont réservées à ce qui
change un chiffre publié ou une décision : un commentaire périmé reste faible, un SRI faux ne l'est
pas.

| ID | Domaine | Cat. | Gravité | Certitude | Déclencheur | Attendu | Comportement et preuve | Impact | Reproduction | Action proposée |
|---|---|---|---|---|---|---|---|---|---|---|
| CR01 | KID | A | Haute | Établi, code et sonde | Générer un KID | L'annexe II citée en commentaire veut le VaR à 97,5 %, actualisé | `kid.py:293` prend le 1er percentile des montants NON actualisés | Deux écarts cumulés sur la statistique de risque | Comparer p1, p2,5 et le PV sur un même run | Prendre le 2,5e percentile du PV, ou cesser de citer l'annexe II |
| CR02 | KID | D | Critique pour tout usage documentaire | Établi, code et sonde | Lire le SRI | Des bandes réglementaires appliquées à une statistique réglementaire | `_VEV_THRESHOLDS` sont les bandes MRM de l'annexe II, appliquées à `sqrt(-2 ln p1 / T)` | VEV 2,1 à 12,3 fois la VEV RTS ; SRI de +1 à +3 crans | Sonde 2 | Soit la VEV RTS, soit des seuils propres et un autre nom |
| CR03 | KID | A | Haute | Établi, code | Lire la colonne de tension | Un scénario de tension suppose une volatilité stressée | Aucune étape de volatilité stressée dans le module ; la colonne est le 1er percentile de la même simulation | La colonne la plus regardée n'est pas un stress | `grep -i stress api/kid.py` : deux libellés, aucun calcul | Renommer, ou implémenter la volatilité stressée |
| CR04 | KID | D | Moyenne | Établi, code | KID avec N = 1 000 | L'annexe II impose 10 000 simulations en catégorie 3 | `PricingRequest.N` admet 1 000 et `kid_compute` l'utilise tel quel | Un KID produit sous le minimum du texte cité | Appeler `/api/kid/compute` avec `N=1000` | Plancher de N propre au KID |
| CR05 | KID et Pricer | A | Moyenne | Établi, code et sonde | Pricer avec funding, puis KID | Le dossier KID porte les hypothèses du prix affiché | Le dict `common` ne transmet ni `funding_curve`, ni `funding_spread`, ni `barrier_monitoring`, ni `value_date`, ni `payment_date` | `full_price` à 404 bp du prix du Pricer, 150 bp de spread sur 3 ans ; percentiles et TRI inchangés | Sonde 3 | Transmettre, ou refuser comme la courbe de taux |
| CR06 | Mark-to-Future | A | Haute | Établi, code et sonde | Éventail MtF, ou horizon intermédiaire de KID, sur un produit à spread émetteur | Le garde refuse tout ce qui déplacerait la base d'actualisation | `run_mark_to_future` n'a aucun paramètre de funding et `_mtf_reject_unsupported` ne le mentionne pas | L'éventail est tracé contre un P₀ qui contient le funding ; 404 bp sur l'instance | Comparer `run_mc` avec et sans funding au `main_price` transmis | Ajouter le funding au refus, puis le porter |
| CR07 | Solveur | A | Haute | Établi, code et sonde | Résoudre sur un payoff pentu ou en plateau | L'infobulle dit « Oui si l'écart au prix cible est passé sous la tolérance » | `simulation.py:124` : `abs(f_mid) < tol or (b-a)/2 < tol` ; `tol` sert en prix et en unité du paramètre | `converged=True` à 2,5 fois `tol` ; l'Optimizer s'en défie, `api/deals.py:6729` non | Sonde 4 | Séparer `tol_prix` et `tol_param` |
| CR08 | EMT | A | Moyenne | Établi, code | `PARAM GEARING = 2` | Un levier brut supérieur à 1 est un levier | `emt.py:82` exige `p.is_pct`, faux pour un défaut brut (`parser.py:742`) | `complexity_score` baisse de 1 ; le profil peut descendre d'averti à informé | Deux EMT, `GEARING = 2` contre `GEARING = 200%` | Détecter la valeur effective, pas l'unité |
| CR09 | KID et EMT | D | Haute | Établi, code | Conserver un KID, puis lire l'EMT | Un artefact conservé porte sa réserve de méthode | L'avertissement vit dans `KidPanel.vue:68` seul ; ni la réponse, ni `KidRecord`, ni le document figé ne le portent | Le SRI circule sans réserve vers l'EMT, le marché cible et le dossier | Lire un `KidRecord` conservé | Champ de méthode dans la réponse et dans la table |
| CR10 | Moteur et API | D | Moyenne | Établi, code | Demander une graine | Une étude de stabilité exige plusieurs graines | `fixed_monte_carlo_seed` renvoie 42 avant validation, dans `PricingRequest` et `AnalysisBase` | Les cas V15 et V22 du plan du rapport ne sont pas exécutables par l'API | Envoyer `seed: 7` et lire la réponse | Ouvrir la graine aux campagnes de validation |
| CR11 | Moteur | D | Moyenne | Établi, code | Appel API omettant `q` | Une hypothèse de dividende est explicite | `UnderlyingParams.q` vaut 0,02 par défaut | 2 % de dividende silencieux déplacent le forward | Pricer sans `q` | Rendre `q` obligatoire, ou nul par défaut |
| CR12 | Barrières | D | Moyenne | Établi, code | Monitoring continu, un actif, Heston ou LSV | Un domaine qualifié s'applique symétriquement | `validate_bridge_domain` sort immédiatement si `n <= 1` ; seule une note textuelle signale l'approximation | Un panier hors domaine est refusé, un mono-actif à vol stochastique est admis sans borne | Barrière américaine mono-actif sous Heston | Étendre le refus, ou publier une borne |
| CR13 | VaR | D | Moyenne | Établi, code | VaR sur un book multi-actifs | Un choc historique rejoue les mouvements observés | Un `corr_delta` scalaire porte la corrélation moyenne ; en paramétrique un seul choc de vol pour tous | Dispersion des vols et ruptures par paire écrasées | `var_engine.py:160`, `:178`, `:371` | Choc par paire, ou annoncer un facteur unique |
| CR14 | CCR | D | Faible | Établi, code | Lire `result["ee"]` | Un champ nommé EE porte EE | `summarize` affecte l'EPE au champ `ee` (`ccr/exposure.py:118`) | Confusion entre niveau courant et moyenne d'horizon | Lecture directe | Renommer |
| CR15 | CCR | C | Faible | Établi, code | CVA sur longue maturité | Cohérence avec l'actualisation du pricing | La CVA actualise à un taux scalaire | Écart avec une actualisation sur courbe, non chiffré | — | Documenter, ou porter la courbe |
| CR16 | AMC et FIFO | D | Haute | Établi, code | Appeler le cœur FIFO sans `recon_mode` | Un lot manquant est une anomalie, pas un achat | `fifo/engine.py:55` et `pipeline.py:125` ont `t0_synthetic` par défaut ; le manifeste est `strict` mais son commentaire `:106` annonce l'inverse | Des achats synthétiques changent le P&L sans demande de l'appelant | Comparer `amc_manifest.py:106` et `:109` | Défaut `strict` partout, commentaire corrigé |
| CR17 | Optimizer | D | Faible | Établi, sonde | Lire `product_optimizer/service.py:201` | Un commentaire décrit le code | Il annonce un `UnboundLocalError` sur la sortie non antithétique ; `flows_anti` et `labels_anti` sont pré-initialisés (`engine.py:2588`) | Fausse contrainte qui détourne d'un chemin valide | Sonde 1 | Supprimer le commentaire |
| CR18 | Dividendes | C | Faible | Établi, code | Courbe de dividende croissante ou non annuelle | — | `validate_dividend_curve` impose des buckets annuels consécutifs et une courbe non croissante | Cohérent avec la pratique de desk de `CLAUDE.md`, non dit par le rapport | — | Mentionner la restriction |
| CR19 | Gouvernance | E | — | Établi, code | Amendement économique | — | `STRUCTURA_AMENDMENT_FOUR_EYES` vaut 0 par défaut (`workflow.py:31`) | Un super utilisateur peut cumuler demande et approbation | Lecture directe | Arbitrage d'organisation, pas un défaut |
| CR20 | Conformité | F | — | Preuve insuffisante | Conclure sur PRIIPs aujourd'hui | — | Annexe IV supprimée dans le rendu lu, formule VEV en image, sources divergentes sur les percentiles de tension | La version applicable n'est pas datable ici | — | Lire le texte consolidé et la Q&A ESMA courante |

### Détail des constats qui portent le poids

**CR01 et CR02 — la VEV.** Le module calcule `sqrt(-2 ln(p1) / T)` où `p1` est le 1er percentile des
montants non actualisés. L'annexe II veut le VaR à 97,5 %, soit le 2,5e percentile, et la valeur
actualisée au facteur sans risque attendu. Le code cite pourtant l'annexe II dans son commentaire, et
classe son résultat dans les bandes MRM de cette même annexe. Les deux écarts vont dans le sens
conservateur, ce qui est plus difficile à repérer qu'une erreur favorable : personne ne conteste un
risque affiché trop haut.

| p1 à l'échéance, T = 5 ans | VEV du code | MRM et SRI (CRM 3) | VEV de l'expression RTS | MRM et SRI (CRM 3) |
|---|---|---|---|---|
| 0,95 | 14,3 % | MRM 4, SRI 4 | 1,2 % | MRM 2, SRI 2 |
| 0,80 | 29,9 % | MRM 5, SRI 4 | 5,0 % | MRM 2, SRI 2 |
| 0,55 | 48,9 % | MRM 6, SRI 5 | 12,7 % | MRM 4, SRI 4 |
| 0,20 | 80,2 % | MRM 7, SRI 7 | 31,2 % | MRM 6, SRI 5 |

La parenthèse de l'expression RTS retenue ici est `(sqrt(3.842 - 2 ln p1) - 1.96) / sqrt(T)`,
cohérente avec 3,842 ≈ 1,96² ; le Journal officiel la rend sous forme d'image, et cette écriture vient
d'une source secondaire. L'écart de méthode, lui, n'est pas en débat : le code le dit lui-même. Ce que
la revue ajoute, c'est son **sens** et son **ordre de grandeur**, qui ne sont écrits nulle part.

**CR05 et CR06 — le funding qui n'arrive pas.** Les deux constats sont le même mécanisme à deux
endroits, et il faut les séparer pour ne pas surévaluer le premier. Au niveau de la période de
détention recommandée, les montants d'un KID sont des sommes de flux non actualisées et les rendements
des TRI : le funding n'y entre pas, et son absence ne change ni les percentiles ni les TRI — la sonde 3
le confirme, tout est identique à 150 bp près de spread. Le seul chiffre touché est `full_price`, que
la réponse publie à 404 bp du prix du Pricer et qu'aucun consommateur ne lit aujourd'hui.

Le poids est ailleurs. Les horizons intermédiaires — les lignes « si vous sortez après un an » — valent
le cash reçu plus une marque résiduelle calculée par `run_mark_to_future`, qui n'a aucun paramètre de
funding. Cette marque ignore donc la décote de crédit de l'émetteur et sort trop haute, d'environ le
spread multiplié par la durée restante. Le même moteur sert l'éventail Mark-to-Future du Pricer, tracé
contre un P₀ fourni par l'appelant qui, lui, contient le funding.

Ce qui rend ce constat solide plutôt que théorique, c'est que l'équipe a déjà identifié et fermé
exactement ce défaut pour la courbe de taux. Le commentaire de `api/pricing.py` l'écrit : les
paramètres sont transmis « pour être REFUSÉS, pas honorés », parce que les laisser tomber « priçait
l'éventail sur une autre base d'actualisation que le P₀ contre lequel il est tracé, sans rien le dire à
l'écran ». Le spread émetteur est le dernier paramètre d'actualisation à n'avoir reçu ni le refus ni le
portage.

**CR07 — le solveur.** Deux critères de nature différente partagent un seul nombre. `abs(f_mid) < tol`
est un écart de prix, en fraction de nominal ; `(b - a) / 2 < tol` est une demi-largeur dans l'unité du
paramètre cherché — un coupon, une barrière, un levier. Sur un intervalle de recherche de 1,0, quatorze
bissections suffisent à passer sous 1e-4, quelle que soit la pente du prix. La sonde 4 obtient
`converged = True` avec un résidu de 2,5 fois la tolérance, sur une digitale dont la granularité de
prix est de 5e-4 ; sur un payoff plafonné en plateau, l'écart n'a pas de borne.

L'Optimizer ne lui fait pas confiance et le dit : il reprice après résolution, « sans se fier au
drapeau de convergence fondé sur l'intervalle ». Le solveur de funding implicite de
`api/inlife.py:651` utilise, lui, un critère en prix. Le solveur général est donc l'exception, et c'est
celui dont l'écran affiche un « ✓ Oui » vert.

### Révisions après lecture des annexes et du catalogue de tests

Trois entrées du tableau sont amendées ici plutôt que réécrites, et deux sont ajoutées. La séquence
compte : les trois premières ont été écrites avant d'avoir lu les preuves datées.

**CR07 — confirmé, et la raison de sa survie est trouvée.** Le test existe :
`test_le_solveur_atteint_vraiment_le_prix_qu_il_annonce` (`test_coherence_analytiques.py:271`) vise
exactement la bonne propriété et, **si** le solveur se déclare convergent, exige `achieved_price` égal
à la cible à `abs=2e-3`. Or la tolérance par défaut du solveur est `1e-4`. L'oracle est donc vingt fois
plus lâche que la tolérance que l'écran promet, et le résidu de 2,5e-4 de ma sonde le passe
confortablement. Le défaut ne survit pas à l'absence de test, mais à la tolérance de son test.

**CR08 — confirmé, et l'intention est écrite.** `test_le_levier_emt_lit_la_valeur_economique_saisie`
(`test_emt.py:46`) déclare la bonne règle dès son nom. Il déclare `PARAM GEARING = 50%`, donc `is_pct`
vrai, puis vérifie qu'une valeur saisie de 2,0 déclenche le levier. La déclaration brute n'est jamais
exercée. L'intention du test et l'implémentation divergent précisément là.

**CR12 — reclassé, et ma critique de l'annonce est retirée.** Le tableau de domaine de
`REMEDIATION_C16` écrit noir sur blanc, pour le cas mono : « loi jointe min/max et modèles hors GBM
déterministe toujours approximatifs et signalés ». La limite est donc annoncée, dans un document daté,
et pas seulement dans une note de code. Ce qui reste est l'asymétrie d'**application** : refus avant
simulation pour le panier, note textuelle pour le mono. La gravité tombe de Moyenne à Faible.

**CR21 — nouveau. Catégorie D, gravité haute, établi par preuve datée.** Le rapport parle de « surface
cible synthétique », ce qui sous-estime largement ce que `REMEDIATION_C17` publie lui-même. Les seuils
arbitrés sont 5 pb pour les vanilles et 10 pb pour les digitales. Mesurés : cible plate à 2 ans, 0,06
et 0,31 pb, qualifié ; smile standard à 4 ans, **47,0 et 131,4 pb** ; à 10 ans, **163,8 et 214,9 pb** ;
ATM 7 ans porté à 35 %, **307,3 et 299,3 pb**. Aucun de ces trois derniers n'est qualifié. Autrement
dit : la calibration Heston ne passe ses seuils que sur une surface **plate**, et manque d'un à deux
ordres de grandeur dès qu'il y a un smile. Le code en tire la bonne conséquence — les paramètres ne
sont pas appliqués automatiquement — mais la phrase du rapport ne permet pas de le savoir.

**CR22 — nouveau. Catégorie D, gravité haute, établi par empreintes.**
`BACKEND_FULL_VALIDATION.json` fige les 443 sources backend avant le passage de 3 943 tests du
23 octobre. Les quatorze fichiers portant CR01 à CR08 et CR16 sont inchangés depuis. La suite complète
passe donc sur exactement ce code, et aucun de ces constats n'est couvert. C'est la mesure la plus
utile du dossier : elle ne dit pas que la suite est faible, elle dit **où** elle ne regarde pas. Seul
`api/deals.py` a changé depuis le gel, donc le consommateur de solveur cité à la ligne 6729 n'est pas
couvert par ce résultat.

## D — Revue des limites assumées

La plupart des limites de Structura sont financièrement cohérentes et, fait rare, **appliquées par un
refus** plutôt que par une note. Les trois qui ne sont annoncées que textuellement sont celles qu'il
faut surveiller, parce qu'une note ne survit pas à un appel d'API.

| Limite | Cohérente | Annoncée | Appliquée | Acceptable pour | Bloquante dès que |
|---|---|---|---|---|---|
| Funding hors du drift | Oui, et c'est la bonne convention | `CLAUDE.md`, et la raison écrite dans `_funding_df_arr` | Oui, par construction : deux objets distincts | Tout usage | Jamais ; à préserver si la courbe de taux est revue |
| Grille d'environ 52 pas par an, ACT 365,25 | Oui pour des constatations périodiques | Rapport et `TIME_AXIS_POLICY` | Oui, horizon exact et occurrences ordonnées | Autocalls, phoenix, coupons périodiques | Fenêtre de moyenne courte, barrière serrée, payoff à forte convexité locale |
| Pont brownien panier, domaine local | Oui, l'approximation est nommée | `joint_extrema_exact: false`, `per_run_error_bound: null` | Oui, refus actif hors domaine, sans repli silencieux | Deux actifs GBM, barrière unilatérale | Trois actifs, double barrière, ou exigence d'une borne par run |
| Monitoring continu mono-actif sous vol stochastique | Discutable : l'exactitude marginale ne tient plus | Note textuelle seulement | **Non** : `n <= 1` sort du contrôle de domaine | Illustration et exploration | Toute barrière américaine pricée sous Heston, SABR, Dupire ou LSV pour cotation |
| Surface SSVI synthétique | Oui, la source est qualifiée | `production_approved=false`, preuve de calibration publiée | Oui | Structuration, sensibilité de smile | Dès qu'un prix de smile sort vers un client |
| Vega Heston de jambe indépendante, LSV en vol locale effective | Oui, la portée est la bonne information | `vega_scope` dans la réponse, couverture 1 − ρ² par actif | Oui, et les agrégats séparent les portées | Lecture de risque par portée | Un agrégat présenté comme un vega total homogène |
| Volatilité réalisée comme hypothèse de pricing | Oui si c'est dit | Rapport, et `calibration.py` décrit l'estimateur | Oui, la provenance est conservée | Indicatif, étude, backtest | Cotation ferme, ou comparaison à un prix de marché |
| Fraîcheur de 3 jours calendaires, borne incluse | Oui, c'est un arbitrage explicite | `POLICY_VERSION = "D03-C11-2026-10-21-3D"` | Oui, statut et âge publiés | Valorisation interne, reporting | Officialisation d'un événement contractuel sur un report de trois jours |
| Clôture quotidienne contre intraday | Oui | Rapport, et `fixing_finality` échoue fermé | Oui, place inconnue ou séance non close refusées | Barrières européennes, constats à date | Toute barrière américaine dont le franchissement doit être prouvé |
| Mark-to-Future à taux plat | Oui, et le refus est exemplaire | Messages d'erreur explicites, cinq capacités refusées | Oui pour les cinq, **non pour le funding** | Produit sans spread émetteur | Dès qu'un spread émetteur existe, c'est-à-dire presque toujours |
| VaR sur photo résiduelle, proxies réalisés | Oui comme mesure économique | Rapport, limites Q06 et D08 | Oui, exclusions visibles | Pilotage interne, limites internes | Backtesting réglementaire, capital de marché |
| CCR économique, sans SA-CCR ni WWR | Oui, l'absence est un champ | `regulatory.status = "NOT_APPLICABLE"`, `ead = null` | Oui | Décision de limite interne | Toute déclaration prudentielle ou EAD |
| KID non conforme PRIIPs | L'aveu est cohérent, le chiffre ne l'est pas | Bannière dans l'écran, commentaire dans le code | **Non** : ni la réponse, ni l'enregistrement, ni l'EMT ne la portent | Analyse interne de desk | Dès que le SRI quitte l'écran où vit l'avertissement |
| Optimizer, grille finie et GBM seul | Oui | Allowlist famille-objectif, `auto` résolu en `constant` | Oui, paramètres non résolus refusés | Recherche de contrats admissibles | Présentation comme un optimum, ou comme un moteur de robustesse |
| « Confidence » des études = couverture documentaire | Oui, et c'est dit dans le résultat | `metric = "data_coverage"` | Oui, score global retenu sous 4 dimensions | Étude interne | Communication client qui lirait le mot dans son sens statistique |
| Graine fixée à 42 | Oui comme convention de desk et pour les CRN | Docstring du validateur | Oui, trop : l'entrée est écrasée | Reproductibilité, comparaison de repricings | Toute campagne de validation par graines, celle du rapport comprise |
| Installations hybrides en DEVELOPMENT | Oui | Manifestes, `registry_state`, `billing_enabled` | Oui | Développement, recette, démonstration | Multi-site, haute disponibilité, facturation, exposition distante |

## E — Plan de validation indépendant

**Tous les cas ci-dessous sont des tests proposés. Aucun n'a été exécuté.** Ils sont moins nombreux que
les 90 du rapport et vont dans un autre ordre : d'abord ce qui a un oracle fermé et aucun aléa, ensuite
seulement le Monte Carlo.

**Conventions communes.** Prix en fraction de nominal, donc 1e-4 vaut 1 bp. Cas déterministes :
`sigma = 0` ou trajectoires imposées par substitution de `_simulate_gbm`, comme le font déjà
`test_bridge_dependence` et `test_contractual_timeline` ; tolérance 1e-10 en relatif. Cas Monte
Carlo : écart jugé à trois erreurs types, jamais à une tolérance absolue choisie à la main. Graines :
la contrainte CR10 impose d'appeler le moteur directement, l'API écrasant toute graine à 42.

**Ce qui existe déjà, et qu'il faut resserrer plutôt qu'écrire.** Le catalogue de tests et les preuves
C15 à C17 déplacent la moitié de ce plan.

- P1 et N4 sont mesurés en C15 : PAY 1 à un an contre exp(−0,05), et trajectoires de taux comme flux
  bruts identiques avec et sans funding. À rejouer seulement si l'empreinte moteur change.
- N1, N2 et C2 existent : `test_heston_spot_process_is_martingale`, `test_call_atm_1y`,
  `test_put_call_parity`, `test_local_vol_collapses_to_gbm_when_flat`. Reste à lire leurs tolérances et
  à les rejouer sur plusieurs graines, ce que l'API interdit (CR10).
- N6 est mesuré en C16 : 65 536 tirages contre 8,29388 % analytiques.
- C1 est à moitié fait : le Fourier Heston a sa référence Riccati indépendante. Le cas qui manque est
  l'autre sens — **le Monte Carlo de production contre ce Fourier** — que C17 laisse explicitement hors
  qualification.
- W2 et W3 existent, avec un oracle à `abs=2e-3` et une déclaration en pourcentage. Resserrer l'un et
  étendre l'autre suffit à faire tomber CR07 et CR08.

Restent réellement à écrire : N3, N5, W1, le refus du funding en Mark-to-Future, et tout E.1 hors P1.

### E.1 Correction du payoff, oracle fermé, sans aucun aléa

| Cas | Construction | Oracle | Critère d'acceptation |
|---|---|---|---|
| P1 | `PAY 1` certain à un an, `r = 3 %`, spread 150 bp, paiement à J+3 ouvrés, strike distinct de la value date | `exp(-(r+s) t_pay)` rebasé par `1/DF(value_date)` | Égalité à 1e-10 ; `t_pay` compté depuis le strike, jamais depuis la value date |
| P2 | Même produit, observation à un an, paiement décalé de trois jours ouvrés | Cash brut identique, PV multiplié par `exp(-(r+s) Δ)` | Le seul écart est le facteur de décalage |
| P3 | Autocall, `sigma = 0`, worst-of placé exactement au seuil de rappel, puis à un epsilon de chaque côté | L'opérateur de la term sheet | Branche conforme aux trois cas, sans tolérance |
| P4 | Barrière européenne contre américaine, trajectoire imposée qui descend sous la barrière puis remonte au-dessus | Les deux résultats diffèrent exactement du put vendu | Écart non nul et égal au montant attendu |
| P5 | Coupon mémoire non payé puis rattrapé, `sigma = 0` | Somme contractuelle des coupons dus | Montant exact, mémoire remise à jour une seule fois |
| P6 | Deux `PAY` légitimes identiques en date, montant et libellé | Deux flux | Aucune déduplication, ni dans `flux_table` ni dans le P&L |
| P7 | Rappel anticipé avec `STOP`, puis absence de rappel | Capital payé une seule fois | Somme des flux égale au capital plus les coupons dus, sur les deux chemins |

### E.2 Convergence et estimateur

| Cas | Construction | Oracle | Critère d'acceptation |
|---|---|---|---|
| N1 | GBM, `PAY S` à l'échéance, funding nul | Martingale : PV = `exp(-q T)` sur actif normalisé | Écart inférieur à trois erreurs types, sur cinq graines |
| N2 | Call et put vanilles, N = 20 000 puis 80 000 | Black-Scholes fermé | Écart sous trois erreurs types, et erreur type divisée par deux à 10 % près |
| N3 | Autocall à 52, 104, 208 puis 416 pas par an, mêmes graines | Extrapolation du prix limite | Biais temporel monotone et séparé du bruit ; publier sa valeur en bp |
| N4 | Funding modifié, aléas identiques | Trajectoires et flux bruts inchangés | Égalité bit à bit des flux bruts ; seul le PV bouge |
| N5 | LSV, vingt réplications entières à graines distinctes | Couverture empirique de l'IC95 publié | Couverture au moins 90 % ; sinon l'IC est à requalifier, pas à élargir |
| N6 | Pont mono-actif, barrière unilatérale, GBM à vol constante | Loi fermée du minimum d'un brownien géométrique | Probabilité de franchissement sous trois erreurs types |

### E.3 Modèles et calibration

| Cas | Construction | Oracle | Critère d'acceptation |
|---|---|---|---|
| C1 | Heston, cinq strikes et trois maturités, vanilles et digitales | Transformée de Fourier indépendante, écrite hors du dépôt | Erreur publiée en bp, biais de discrétisation séparé du bruit |
| C2 | Surface locale plate | Retour vers la référence GBM | Écart expliqué et borné, pas seulement « proche » |
| C3 | SABR, beta vers 0 et vol-of-vol élevée | Référence CEV avec sa politique de frontière | Effet des planchers et de l'écrêtage mesuré, non masqué par l'IC |
| C4 | SSVI à chaque pilier et en aile basse | Absence d'arbitrage papillon et calendaire | Aucune densité négative sur 60 à 150 % de moneyness |

### E.4 Données et reproductibilité

| Cas | Construction | Oracle | Critère d'acceptation |
|---|---|---|---|
| D1 | Historique local frais, réseau coupé, puis étude AMC complète | Aucun appel fournisseur | Zéro requête ; vérifier en particulier `execution_series` quand `price_close` manque |
| D2 | Donnée à J+3 puis à J+4 | Trois jours calendaires, borne incluse | Inclusion puis exclusion, avec statut et âge publiés |
| D3 | IPO récente dans un panier ancien | Aucune valeur avant la première observation réelle | Début commun explicite, corrélation refusée plutôt qu'inventée |
| D4 | Split et dividende exceptionnel sur un titre à fort rendement | Brut, ajusté et unités distingués | Drapeau `suspect` visible, fixing lu hors colonne ajustée |
| D5 | Rejeu d'archive sans réseau, puis après changement de bibliothèque | Identité de moteur | Rejeu qualifié refusé, archive toujours consultable, aucune attribution fictive |

### E.5 Workflow, documents et cash

| Cas | Construction | Oracle | Critère d'acceptation |
|---|---|---|---|
| W1 | KID à deux niveaux de funding et deux modes de monitoring | Même sémantique que le Pricer, ou refus explicite | Prédiction de CR05 : percentiles identiques, `full_price` et horizons intermédiaires divergents |
| W2 | Solveur sur un plateau de prix, puis sur une digitale à faible N | `converged` cohérent avec le résidu publié | Aucun « oui » au-dessus de la tolérance de prix |
| W3 | EMT avec `GEARING = 2` puis `GEARING = 200%` | Même contrat, même classification | `complexity_score` et profil identiques |
| W4 | FIFO : achat, vente partielle, vente en excès, split, carnet calculé à la main | Quantités et P&L exacts | Injection synthétique visible seulement en mode synthétique, et jamais en `strict` |
| W5 | Produit rappelé, paiement dans trois jours ouvrés | Créance certaine actualisée | `settlement_pending`, zéro trajectoire, aucun nouveau payoff optionnel |
| W6 | Fixing officiel corrigé après un run conservé | Ancien run conservé, fraîcheur invalidée | Aucun écrasement d'archive, nouvelle source affichée |

## F — Priorités d'action

Quatre corrections de quelques lignes ferment quatre des six constats de catégorie A, et aucune ne
touche le moteur de diffusion. Les deux autres — la statistique du KID et sa colonne de tension — sont
des décisions de produit, pas des corrections.

**Corrections nécessaires.**

- CR07 — séparer `tol_prix` et `tol_param` dans `solve_for_param`, et ne déclarer convergence que sur
  le prix. L'infobulle de l'écran redevient vraie sans être réécrite.
- CR06 — ajouter `funding_curve` et `funding_spread` à `_mtf_reject_unsupported` dès maintenant. Une
  ligne, et le Mark-to-Future cesse de publier un éventail sur une autre base que son P₀.
- CR05 — transmettre funding, monitoring, value date et payment date dans le dict `common` de
  `kid_compute`, ou les refuser avec le même message que la courbe de taux.
- CR08 — faire porter la détection de levier sur la valeur effective, non sur `is_pct`.
- CR16 — `strict` par défaut dans `fifo/engine.py` et `fifo/pipeline.py`, et corriger le commentaire du
  manifeste qui annonce l'inverse de son propre défaut.
- CR14 et CR17 — renommer le champ `ee`, supprimer le commentaire périmé de l'Optimizer.

**Restrictions d'usage à écrire avant tout usage externe.**

- Le KID est une analyse interne de desk. Ni distribution, ni SRI communiqué, ni reprise du SRI dans un
  document commercial, tant que CR01 à CR04 sont ouverts.
- Une barrière américaine mono-actif sous Heston, SABR, Dupire ou LSV reste de l'exploration : le
  domaine qualifié ne la couvre pas (CR12).
- `production_approved=false` sur le dossier de calibration vaut interdiction de cotation sur un prix de
  smile.

**Transparence.**

- CR09 — porter la réserve de méthode dans la réponse de `/api/kid/compute`, dans `KidRecord` et dans le
  document figé, et l'afficher dans l'EMT qui consomme le SRI. Aujourd'hui elle vit dans un seul
  composant Vue.
- Rendre le résidu du solveur aussi visible que le « ✓ Oui » : il est déjà dans la réponse.
- Dire que le choc de corrélation de la VaR est un facteur scalaire unique, et que le choc de vol
  paramétrique est commun à tous les sous-jacents (CR13).
- Écrire la restriction des courbes de dividende : buckets annuels consécutifs et profil non croissant
  (CR18).

**Validations complémentaires, dans cet ordre.**

1. E.1 en entier. Aucun aléa, oracle fermé, et c'est là que se cachent les erreurs de branche, de date
   et de double paiement.
2. N1, N2 et N4. Trois tests qui ferment au premier ordre la question que cette revue laisse ouverte :
   les prix sont-ils justes.
3. N5 et C1. Ils décident de ce qui peut sortir sous un modèle à volatilité stochastique.
4. D1 et D2 avant tout usage d'exploitation, et W1 pour confirmer la prédiction de CR05.

**Arbitrages métier.**

- CR02 : soit la VEV de l'annexe II, soit un indicateur maison avec ses propres seuils et un autre nom.
  Garder la formule actuelle sous les bandes réglementaires n'est pas tenable, mais le choix entre les
  deux sorties est un choix de produit.
- CR10 : ouvrir la graine aux campagnes de validation, ou assumer qu'aucune étude de stabilité ne
  passera par l'API.
- CR19 : la seconde signature des amendements.
- D06 et D07 du registre : correction après consommation d'un fixing, et politique de cash confirmé.

**Évolutions facultatives.** Porter réellement le funding dans le Mark-to-Future après l'avoir refusé ;
choc de corrélation par paire dans la VaR ; actualisation de la CVA sur courbe ; borne d'erreur par run
pour le pont brownien.

## G — Critique du rapport fourni

Le rapport est honnête et utilisable : ses empreintes tiennent, il refuse de sommer ses totaux de
tests, et il écrit ce qu'il ne conclut pas. Ses défauts sont des erreurs de **portée** — il place le
poids au mauvais endroit — plus que des erreurs de fond.

**Ce qu'il fait mieux que l'ordinaire.** Les quatre niveaux de preuve du §39.5 et la phrase « ces
totaux ne s'additionnent pas » du §39.3 ont évité deux erreurs de lecture. Les quatorze fichiers cités
ici correspondent au manifeste, donc sa photographie est vérifiable. Et la leçon de l'audit du
8 septembre — écrire les magnitudes comme des mesures d'instance — est appliquée.

**Conclusions trop fortes ou mal placées.**

1. **R02 est surévalué là où il est écrit, et sous-évalué là où il compte.** « Prix et dossier KID
   peuvent porter des hypothèses différentes », classé Haute : la rupture de passage est réelle, mais à
   la période de détention recommandée les montants d'un KID sont des sommes non actualisées et les
   rendements des TRI. La sonde ne mesure aucun écart sur les percentiles ni sur les TRI à 150 bp de
   spread. Le seul champ touché, `full_price`, n'a aucun consommateur dans le dépôt. Le poids est dans
   les horizons intermédiaires, par le Mark-to-Future — et le rapport ne fait pas ce lien.
2. **Le refus de domaine du pont est présenté comme général.** Le §10.7 écrit « une configuration hors
   domaine est refusée, sans passage automatique en monitoring hebdomadaire ». C'est vrai pour les
   paniers et faux pour le mono-actif : `validate_bridge_domain` sort immédiatement si `n <= 1`. Une
   barrière américaine mono-actif sous Heston ou LSV passe donc sans refus et sans borne. Le rapport
   note l'approximation, pas l'asymétrie de son application.
3. **Le §12.5 présente cinq refus comme la frontière du Mark-to-Future.** Le funding y manque, et pas
   comme un refus oublié : comme un paramètre qui n'existe pas dans la signature. C'est exactement le
   défaut que le rapport traque en R02, non vu là où il est matériel.
4. **R01 s'arrête à l'aveu.** « Approximation reconnue dans le code », et rien de plus. Le rapport ne
   dit pas que les seuils appliqués sont les bandes MRM réglementaires, ni dans quel sens ni de combien
   l'écart va. Une non-conformité annoncée sans son ampleur rassure, ce qui la rend plus dangereuse
   qu'une non-conformité ignorée. S'y ajoutent deux écarts non relevés — percentile 1 % au lieu de
   2,5 %, montant non actualisé — et un troisième, la colonne de tension sans volatilité stressée, que
   le §31.4 range parmi les choses « à vérifier » alors qu'elle se lit dans le fichier.
5. **Le plan de validation propose des tests que le contrat d'API interdit.** V15 demande « plusieurs
   seeds », V22 des « réplications entières indépendantes ». `fixed_monte_carlo_seed` renvoie 42 avant
   toute validation, dans `PricingRequest` et dans `AnalysisBase`. Le §9.1 décrit le tirage par
   `default_rng(seed)` sans signaler que `seed` n'est jamais celui demandé. Un reviewer qui suivrait le
   plan conclurait à une stabilité qu'il n'a pas mesurée.
6. **Une contrainte imaginaire laissée dans le code.** Le commentaire de
   `product_optimizer/service.py:201` annonce un `UnboundLocalError` sur la sortie non antithétique du
   moteur. La sonde 1 ne le reproduit pas : `flows_anti` et `labels_anti` sont pré-initialisés à
   `None`. Le rapport ne reprend pas l'affirmation, mais ne la corrige pas non plus. Une inspection
   statique ne pouvait pas trancher ce point, et c'est l'argument le plus net en faveur d'une sonde
   plutôt que d'une relecture.

**Retrait du point 2.** Après lecture de `REMEDIATION_C16`, ma critique du §10.7 ne tient pas : le
rapport réserve son « configuration hors domaine refusée » au paragraphe du panier, et C16 annonce
explicitement le cas mono. Je la retire. Subsiste l'asymétrie d'application, qui n'est pas une erreur
du rapport.

**Deux critiques à ajouter.** Le §10.8 écrit qu'une surface admissible n'est pas une surface calibrée
au marché : vrai, mais cela laisse croire à un écart de nature. C17 publie un écart de taille — 47 à
307 pb contre des seuils de 5 et 10. Et le rapport n'exploite pas son actif le plus fort : le gel
d'empreintes de `BACKEND_FULL_VALIDATION.json` permet de démontrer en une commande que les 3 943 tests
portent sur exactement le code décrit. Le §39.3 le range parmi les preuves datées, sans en tirer cette
conséquence.

**Omissions.**

- Le défaut `q = 0,02` de `UnderlyingParams`. Le §6.3 décrit l'unité de `q`, pas le fait qu'il vaille
  2 % quand l'appelant ne l'envoie pas — alors que le registre projet garde la trace d'un prix
  reproduit grâce à ce défaut.
- La restriction des courbes de dividende, présentée §6.4 comme « constantes par bucket » : elles
  doivent aussi être annuelles, consécutives et non croissantes.
- Le choc de corrélation scalaire unique de la VaR, et le choc de vol commun à tous les sous-jacents en
  paramétrique.
- Le champ `ee` du résumé CCR, qui porte l'EPE.
- Le fait que la réserve de méthode du KID ne survive pas à l'écran : ni la réponse, ni l'enregistrement
  conservé, ni l'EMT ne la portent.

**Points insuffisamment étayés.**

- Le §10.2 avertit, à juste titre, qu'une équivalence avec une ancienne boucle prouve une régression de
  code et non l'absence de biais. Mais il ne dit pas quels tests actuels se réduisent à cette
  équivalence, donc on ne sait pas quelle part du dossier Heston repose sur un oracle non indépendant.
- Le tableau du §39.3 se lit comme un bilan alors que ses lignes se recouvrent et portent des
  références successives. Le texte le dit ; la mise en forme le défait.
- Le §9.3 mélange ce que le cœur produit et ce que le schéma de réponse expose, et renvoie la
  vérification au lecteur. Pour `full_price`, la vérification donne : aucun consommateur.

**En faveur du rapport.** Son §43 demande à la contre-revue de pouvoir le contredire. Les six points
ci-dessus n'auraient pas été trouvables sans la carte qu'il fournit, et quatre d'entre eux sont des
corrections de portée, pas des erreurs de fond.

## Sources

**Fichiers du dépôt.** Quatorze fichiers relus et contrôlés par empreinte SHA-256 contre
`application-review-2026-10-24/SOURCE_MANIFEST.json` (1 147 entrées) : identiques, aucun divergent.
`api/kid.py`, `api/emt.py`, `core/payscript/engine.py`, `core/payscript/simulation.py`,
`core/payscript/parser.py`, `core/payscript/bridge.py`, `core/schemas.py`, `core/var_engine.py`,
`core/ccr/exposure.py`, `core/amc_manifest.py`, `core/workflow.py`,
`frontend/src/components/SolverPanel.vue`, `frontend/src/components/KidPanel.vue`,
`frontend/src/stores/pricing.js`. Lus sans contrôle d'empreinte : `api/pricing.py`,
`core/market_policy.py`, `core/fixing_finality.py`, `core/calibration.py`, `core/amc_timing.py`,
`core/amc_managerskill.py`, `core/fifo/engine.py`, `core/fifo/pipeline.py`,
`core/product_optimizer/service.py`, `db/models.py`, `frontend/src/components/MarketParams.vue`,
`frontend/src/data/productCatalogue.json`.

**Preuves du dossier effectivement lues.** Les dix rapports de `reference-evidence/` — dont
`REMEDIATION_C15`, `C16` et `C17`, et `BACKEND_FULL_VALIDATION_2026-10-23` —, `DOCUMENTARY_EVIDENCE.json`,
`INSPECTION_REFERENCE.json`, `remediation-lot-0-2026-10-20/BACKEND_FULL_VALIDATION.json` et les
sections KID, EMT, solveur et Mark-to-Future de `TEST_CATALOGUE.md`. Non lus : `DATA_MODEL.md`,
`MODULE_CATALOGUE.md`, `API_CATALOGUE.md`, `CRITICAL_SOURCE_EXCERPTS.md` et les JSON d'inventaire.

**Sondes.** Script unique, hors dépôt, moteur seul, exécuté avec l'interpréteur du `.venv` du projet.
Aucune base ouverte, aucun service démarré, aucun accès réseau, N ≤ 8 000 paires. Les quatre sondes et
leurs oracles sont décrits en tête de cette note ; le script est jetable et n'est pas versionné.

**Textes et sources réglementaires consultés.**

- [Annexe II du règlement délégué (UE) 2017/653, rendu FCA](https://handbook.fca.org.uk/techstandards/PRIIPs/2017/reg_del_2017_653_oj/annex02.html)
  — bandes MRM 1 à 7, VaR à 97,5 %, actualisation au facteur sans risque attendu, 10 000 simulations
  minimum en catégorie 3. La formule de VEV y est une image.
- [Annexe IV, même rendu](https://handbook.fca.org.uk/techstandards/PRIIPs/2017/reg_del_2017_653_oj/annex04.html)
  — marquée supprimée : la méthode des scénarios de performance doit être lue dans le texte consolidé
  applicable, non ici.
- [Note académique reproduisant la formule de VEV](https://www.dss.uniroma1.it/en/system/files/pubblicazioni/paper.pdf)
  — source secondaire d'où vient la parenthèse retenue, cohérente avec 3,842 ≈ 1,96².
- [Diagramme risque-rendement JC 2017 49 des ESAs](https://www.esma.europa.eu/sites/default/files/library/jc_2017_49_priips_flow_diagram_risk_reward_rev.pdf)
  — ne reflète pas les modifications de 2021/2268 ; à ne pas prendre pour la méthode courante.
- [Deloitte Luxembourg, méthodologie des scénarios de performance](https://www.deloitte.com/lu/en/Industries/investment-management/blogs/priips-rts-calculation-methodology-for-performance-scenarios.html)
  et [FE fundinfo sur la Q&A ESMA](https://www.fefundinfo.com/insights/what-the-latest-priips-faqs-mean-for-you-key-takeaways-how-we-re-responding)
  — sources secondaires qui **divergent** sur les percentiles du scénario de tension en catégorie 3.
- [Q&A EIOPA 2439](https://www.eiopa.europa.eu/qa-regulation/questions-and-answers-database/2439_fi)
  — formulation d'origine du scénario de tension, antérieure à la refonte.

**Non consulté.** Le texte consolidé du Journal officiel et la Q&A ESMA courante. Toute conclusion de
conformité actuelle exige ces deux sources, et le constat CR20 reste ouvert pour cette raison.
