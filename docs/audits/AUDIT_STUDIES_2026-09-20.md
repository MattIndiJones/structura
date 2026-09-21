# Audit Studies — préparation d'un partenariat de consulting

Date : 20 septembre 2026. Rendez-vous visé : mercredi 23 septembre 2026.
Périmètre : Studies / études AMC, moteur factoriel, blocs A à K, FIFO partagé, prix, sauvegarde, synthèse IA et exports. Audit du code présent dans le répertoire de travail, qui contient déjà des modifications d'autres travaux.
Référence Git : branche `main`, HEAD `2327776` ; cette référence ne remplace pas les modifications locales présentes au moment de la revue.

**Conclusion : Studies possède une réelle profondeur fonctionnelle et peut soutenir un partenariat de consulting. En revanche, la version examinée ne doit pas être vendue comme une notation autonome, validée et reproductible des gérants.** Plusieurs défauts reproduits peuvent inverser une conclusion ou présenter une certitude injustifiée. La voie commerciale recommandée est un pilote accompagné, avec validation des données et revue humaine, suivi d'une industrialisation conditionnée à une recette explicite.

Cet audit ne modifie aucun code applicatif ni test du dépôt. Les recommandations sont des travaux proposés, non des corrections livrées. Le pitch associé se trouve dans [le dossier Studies](C:/Users/Admin/GitHub/structura/docs/projects/studies/STUDIES_CONSULTING_PITCH_2026-09-20.md).

## 1. Méthode et limites de vérification

Travaux effectués : lecture des notes courantes pertinentes ; examen des routes, orchestrateurs, chargeurs, calculs, interface Vue, persistance et générateur PDF ; appels de fonctions réelles avec données synthétiques et substitutions en mémoire ; exécution de deux tests existants ciblés sur le contrat IA ; lecture des dates terminales des fichiers de facteurs locaux ; consultation de sources primaires sur les facteurs, l'inférence robuste et l'utilisation des données.

Les sondes quantitatives utilisent le Python du projet : Python 3.11.9, numpy 1.26.4, pandas 2.0.3, statsmodels 0.14.6, scipy 1.11.4, pyarrow 25.0.0. Elles n'altèrent pas les fonctions sur disque. Un premier essai de la sonde FX a atteint le fallback Yahoo avec le symbole fictif TEST ; son résultat a été écarté et le cas a été rejoué avec le lecteur parquet correctement substitué et le fournisseur réseau bloqué.

Limites : pas de relance complète d'un fonds réel, pas de rapprochement contre les relevés originaux de l'émetteur, pas de recette interactive du navigateur, pas de rendu visuel d'un rapport complet, pas de test de charge, pas de test d'intrusion actif. Les constats d'interface et de sécurité sont issus de la lecture du code. L'audit couvre les composants du module ; il ne constitue pas une certification de production ou une validation indépendante de tous les chiffres historiques.

La suite backend complète n'a pas été lancée. Aucun serveur n'a été démarré, aucun commit ni push effectué.

## 2. Ce qui existe et ce que cela apporte au cabinet

| Fonction | État observé | Usage de consulting et réserve principale |
|---|---|---|
| Entrée Excel | Import et analyse FF présents | Diagnostic depuis une série de NAV ; format à qualifier pour chaque source |
| Étude par dossier | Détection composition, NAV, ordres et manifeste | Prise en charge approfondie des exports de type UTI/LUKB ; pas un connecteur universel |
| A — Factoriel | OLS, FF3/FF5/momentum selon données, fenêtres glissantes, benchmark, net et regrossi | Interroger le style effectif et l'alpha résiduel ; alignement devise/période et inférence à renforcer |
| B — Attribution | FIFO réalisé/latent, prix/FX réalisé, rapprochement NAV et frais | Identifier les contributeurs et les anomalies ; une reconstruction n'est pas une comptabilité certifiée |
| C — Trading | Turnover, appariements FIFO, taux de succès, profit factor, détention | Structurer la discussion sur l'activité ; les appariements de lots ne sont pas des décisions indépendantes |
| D — Comportement | Matrice conviction/résultat, durées, annulations, changements de sens | Préparer des questions au gérant ; conviction et intention sont inférées, pas observées |
| E — Référentiel inertiel | Panier initial issu de term sheet, fallback par identité comptable | Comparer la gestion au maintien du panier initial ; défaut de date et conventions de cash/frais à traiter |
| F — Réplicabilité | Trajectoire factorielle et score | Examiner la dépendance aux facteurs ; aucune réplication investissable hors échantillon démontrée |
| G — Brinson | Calcul séparé à la demande | Diagnostic sectoriel statique ; ne restitue pas l'attribution historique complète du portefeuille géré |
| H — Timing | Exécution positionnée dans une fenêtre de ±30 jours | Analyse rétrospective des entrées/sorties ; absence de démonstration prédictive |
| I — Stock picking | Rendements futurs par achat à 21/63/126/252 séances | Étudier les choix de titres ; benchmark manquant et dépendances statistiques problématiques |
| J — Risque | Drawdown, risque baissier, ratios, concentration, facteurs | Construire une revue de risque ; plusieurs formules à corriger ou préciser |
| K — Chocs | Calendrier statique et activité autour des événements | Support d'entretien historique ; calendrier codé arrêté en 2023 |
| Manager Skill Score | Agrégateur de six dimensions, poids renormalisés | Résumé exploratoire ; pas une probabilité de talent, ni un classement calibré |
| Synthèse IA | Aperçu/édition du prompt, choix du fournisseur, insertion explicite | Aide à la rédaction d'une note ; la génération ne valide pas les calculs |
| Bibliothèque | Sauvegardes multiples par utilisateur, chargement, suppression | Réutiliser un dossier ; historique de résultats présent, paquet de preuves incomplet |
| PDF | Rapport, synthèse libre, annexes et options | Support de restitution ; identité client figée dans le frontend et provenance non scellée |

La combinaison est plus intéressante commercialement qu'une simple régression Fama-French : elle relie style, titres, décisions, risque et restitution. L'accueil réduit actuellement cette richesse au libellé « Étude Fama-French ».

## 3. Constats prioritaires

P1 : peut fausser matériellement un diagnostic ou empêcher une livraison fiable ; traiter avant l'utilisation concernée en production client. P2 : limite méthodologique ou opérationnelle importante à contractualiser et améliorer. Les P1 n'imposent pas tous d'interdire une démonstration supervisée : ils imposent de sélectionner et de contrôler les résultats présentés.

### S01 — P1 — Les blocs ne partagent pas une date de référence unique

**Reproduit et confirmé dans le code.** Le bloc E compare la dernière NAV fournie à un B&H calculé jusqu'à `datetime.now()`. Avec NAV 100 au 02/01/2024 puis 110 au 01/02/2024, et prix 100, 110, 150 au 01/03/2024, la fonction renvoie B&H +50 %, gestion +10 %, valeur ajoutée −40 points. À la date de la NAV, cette valeur ajoutée devrait être nulle.

Le FIFO prend la dernière date d'ordre exécuté ; le chargeur principal privilégie la date de composition ; H et I peuvent lire des prix postérieurs ; l'attribution par décisions prend le dernier prix du store ; G n'impose pas de borne terminale à la NAV. Même une correction de splits bornée localement ne garantit donc pas une étude cohérente.

Références : [B&H](C:/Users/Admin/GitHub/structura/backend/app/core/amc_bh.py:44), [chargement](C:/Users/Admin/GitHub/structura/backend/app/core/amc_orderbook.py:615), [pipeline FIFO](C:/Users/Admin/GitHub/structura/backend/app/core/fifo/pipeline.py:122), [attribution](C:/Users/Admin/GitHub/structura/backend/app/core/amc_attribution.py:34), [Brinson](C:/Users/Admin/GitHub/structura/backend/app/core/amc_brinson.py:158).

Préconisation : une date d'arrêté explicite, distincte de la date de calcul, transmise à tous les blocs ; dates effectives de chaque série visibles ; distinction entre analyse rétrospective à horizon réalisé et état connu à une date. Recette : ajouter des prix, ordres ou splits après l'arrêté ne doit pas changer un résultat figé.

### S02 — P1 — FX absent traité comme une conversion 1 pour 1

**Reproduit.** `build_marks` renvoie un mark de 110 USD pour un titre coté 110 JPY quand la série JPY/USD manque. La fonction corrigée `fx_rate_to` ne sécurise pas ce chemin. Le B&H conserve également le rendement local lorsque le FX échoue ; la sonde EUR/USD renvoie un résultat disponible sans avertissement prix. Le chargeur FIFO remplace aussi un `usedFxRate` absent par 1.

Références : [marks](C:/Users/Admin/GitHub/structura/backend/app/core/amc_prices.py:482), [chargeur FIFO](C:/Users/Admin/GitHub/structura/backend/app/core/fifo/loader.py:61), [B&H](C:/Users/Admin/GitHub/structura/backend/app/core/amc_bh.py:154). L'attribution et G ont aussi des chemins conservant une valeur locale quand le change est indisponible.

Préconisation : absence explicite et blocage des agrégats touchés ; couverture FX en montant ; date et source du change ; 1 autorisé uniquement pour deux devises identiques. Recette : panne FX, couverture commençant trop tard, devise inconnue et cross JPY/USD ne doivent jamais produire un montant plausible en devise produit.

### S03 — P1 — Stock picking : faux alpha et fausse significativité

**Reproduit via `compute_stockpicking_score`.** Si le benchmark est absent, `effective_alpha` devient le rendement du titre. Avec un seul achat et une série croissante, le module produit 94/100 « Excellent », un alpha moyen de 28,45 %, et une phrase affirmant une compétence statistiquement significative alors que `p=0,1056`.

Deux défauts distincts se cumulent : rendement brut étiqueté alpha ; décision de significativité fondée sur `abs(t) >= 1.96` plutôt que sur la p-value de Student effectivement calculée. Les quatre horizons d'un achat sont ensuite regroupés dans `all_alphas_flat` comme des observations pour le test, alors qu'ils se chevauchent. Plusieurs achats du même titre ajoutent une dépendance supplémentaire.

Références : [calcul et fallback](C:/Users/Admin/GitHub/structura/backend/app/core/amc_stockpicking.py:278), [interprétation](C:/Users/Admin/GitHub/structura/backend/app/core/amc_stockpicking.py:198).

Préconisation : aucun alpha ni score relatif sans benchmark valide sur le même intervalle ; test fondé sur p-value ; résultats par horizon ; inférence tenant compte des regroupements par titre et épisode ; vocabulaire « rendement excédentaire observé » plutôt qu'alpha structurel. Recette : benchmark absent → métrique relative indisponible ; un achat → aucune conclusion de talent ; aucune phrase « significatif à 5 % » si p > 0,05.

### S04 — P1 — Bloc Risque : première perte ignorée, risque baissier mal défini

**Reproduit.** Pour NAV 100 → 50 → 50, `_drawdown_series(_nav_to_returns(...))` renvoie un drawdown maximal de 0 %, au lieu de −50 %. La courbe cumulée débute après le premier rendement : la première perte devient le nouveau niveau de base.

Le risque baissier utilise l'écart-type des seuls rendements négatifs autour de leur propre moyenne. Ce n'est pas la déviation baissière par rapport à un rendement cible. Dix rendements identiques de −1 % donnent une semi-déviation affichée de 0 % et un Sortino numériquement instable. Les pertes hebdomadaires/mensuelles sont des sommes de rendements simples, pas des rendements composés. Le Sharpe utilise un taux sans risque nul implicitement ; le Calmar utilise une moyenne arithmétique annualisée.

Références : [risque](C:/Users/Admin/GitHub/structura/backend/app/core/amc_riskmanagement.py:121), notamment `_drawdown_series`, `_score_downside_risk`, `_score_risk_adjusted`.

Préconisation : inclure le capital initial dans les sommets historiques ; définir MAR, RF et conventions d'annualisation ; calculer la déviation baissière selon cette convention et composer les rendements. Recette : perte le premier jour, pertes identiques, absence de perte, historique irrégulier, comparaison avec une feuille de contrôle indépendante.

### S05 — P1 — Réconciliation NAV incorrecte lors d'un rachat intégral

**Reproduit.** Le remplissage des encours teste leur valeur logique : zéro est traité comme une absence. Pour 10 parts à 100 puis rachat des 10 parts à 110, le portefeuille terminal devrait valoir zéro et le gain être 100. Le module conserve 10 parts, affiche une valeur terminale de 1 100 et un P&L implicite de 1 200.

Référence : [rapprochement NAV](C:/Users/Admin/GitHub/structura/backend/app/core/amc_blocks.py:63).

Préconisation : distinguer zéro et donnée absente, expliciter les conventions de souscription/rachat et de distributions, refuser une origine d'encours non justifiée. Recette : rachat total, redémarrage après encours nul, encours manquant et dates de flux avec NAV distinctes.

### S06 — P1 — Une quantité exécutée nulle peut devenir un vrai trade FIFO

**Reproduit.** `_order_from_item` utilise `executedQuantity or orderedQuantity`. Un ordre `Done`, quantité exécutée 0, quantité demandée 10 et prix 100, devient un achat de 10. À cela s'ajoutent les divergences entre les deux chargeurs : états acceptés, date de trade contre date de création, devise de l'exécution contre devise du sous-jacent et gestion du FX.

Références : [FIFO loader](C:/Users/Admin/GitHub/structura/backend/app/core/fifo/loader.py:55), [orderbook](C:/Users/Admin/GitHub/structura/backend/app/core/amc_orderbook.py:123).

Préconisation : normalisation canonique partagée ; zéro exécuté signifie zéro ; données contradictoires rejetées et journalisées ; conflits entre deux versions d'un même identifiant signalés. Recette : fill partiel, fill nul, ordre amendé, dates différentes, deux fichiers contradictoires.

### S07 — P1 — Paramètres affichés et données réellement consommées peuvent diverger

**Confirmé par lecture, résolution de fichier sondée.** La term sheet éditée dans le manifeste alimente E et le panier affiché. Le FIFO relit `termsheet_positions.json` dans le dossier. La NAV du manifeste n'est pas non plus explicitement transmise à ce pipeline, qui redétecte un CSV. Une sélection d'ordres ne résolvant aucun fichier retourne `None`, ce qui réactive l'auto-détection FIFO. L'attribution à la demande et K rescannent le dossier au lieu de réutiliser exactement les ordres du manifeste.

Références : [orchestrateur](C:/Users/Admin/GitHub/structura/backend/app/core/amc_study.py:41), [pipeline](C:/Users/Admin/GitHub/structura/backend/app/core/fifo/pipeline.py:122), [éditeur de term sheet](C:/Users/Admin/GitHub/structura/frontend/src/views/AmcView.vue:4640), [API AMC](C:/Users/Admin/GitHub/structura/backend/app/api/amc.py).

Préconisation : paquet d'entrées résolu une seule fois, passé à tous les blocs ; empreintes des fichiers ; erreur sur sélection introuvable ; table « valeur saisie / valeur utilisée ». Recette : changer une ligne de term sheet dans l'interface doit modifier tous les calculs concernés et seulement ceux-ci ; un fichier exclu ne doit pas réapparaître dans K ou l'attribution.

### S08 — P1 — Prix/FX T0 et fidélité de la reconstruction FIFO restent à sécuriser

**Défaut T0 confirmé, situation du fonds historique non rejouée.** Les lots initiaux sont construits avec un prix déjà en devise produit, `fx=1`, puis rapprochés de ventes en devise locale. La ventilation prix/FX est donc incorrecte pour ces lots non domestiques, même quand le P&L total est correct.

Les cours `auto_adjust=True` servent au store tandis que les prix d'exécution sont corrigés de splits, sans normalisation équivalente des dividendes. Le traitement de quantités réelles, dividendes cash, prix ajustés et ajustements postérieurs à l'arrêté doit être audité comme un système cohérent ; les seules corrections de splits ne suffisent pas à le démontrer.

Les notes historiques documentent des déficits, des injections et des positions « fantômes ». L'écart +23 %, puis 21,4 % mentionné dans le post-mortem, est une mesure historique, pas un résultat actuel. L'hypothèse « NAV lissée » ne prouve pas la cause de l'écart ; il faut rapprocher titres, cash, flux, frais et dates. Le pourcentage d'écart actuel est rapporté au P&L NAV, pas à l'AUM : il devient instable quand le P&L approche zéro.

Références : [lots initiaux](C:/Users/Admin/GitHub/structura/backend/app/core/fifo/nav.py:86), [référence FIFO](C:/Users/Admin/GitHub/structura/docs/reference/FIFO_MODULE.md), [post-mortem](C:/Users/Admin/GitHub/structura/docs/lessons/POSTMORTEM_2026-07-16_CH1352587724_PNL_RECONCILIATION.md).

Préconisation : ledger prix nus/cash corporate actions ou convention ajustée cohérente et démontrée ; montant et origine des injections visibles ; contrôle de chaque quantité finale contre le relevé officiel ; écart en devise, en bps d'AUM et relativement au P&L. Recette sur plusieurs AMC, dont un multidevise, un split, un dividende et un titre délisté. Aucun écart inexpliqué masqué par compensation globale.

### S09 — P1 — Régression benchmark : jours manquants remplacés par zéro

**Reproduit.** `bm_excess = bm_ret.fillna(0) - RF` précède la sélection des observations de la régression benchmark. Une série comportant 30 rendements observés aboutit à une régression sur 79 observations dans le cas de contrôle. Les jours sans benchmark participent comme des jours de rendement nul.

Référence : [moteur factoriel](C:/Users/Admin/GitHub/structura/backend/app/core/amc_engine.py:519).

Préconisation : alignement explicite sur les rendements réellement observés et mêmes intervalles de détention ; nombre d'observations benchmark séparé ; pas de zéro imputé pour une absence. Recette : trou en milieu de série, fin plus ancienne, calendriers de bourse différents.

### S10 — P1 — Brinson : identité d'attribution non garantie

**Reproduit.** Avec rendement benchmark total de 10 % et proxy sectoriel de 20 %, le cas synthétique affiche un rendement actif de 11,75 points mais une somme allocation/sélection/interaction de 1,75 point. Les composantes sectorielles utilisées ne recomposent pas nécessairement le benchmark total. `check_pct` est affichable mais aucun contrôle bloquant ne garantit l'égalité. La même sonde utilise des prix au 12/02 pour une NAV arrêtée au 31/01.

Plus largement, poids d'origine, poids actuels ou achats des 60 premiers jours sont des approximations différentes. Des rendements sur portefeuille statique, des secteurs SPDR US et des poids benchmark actuels ne peuvent être assimilés sans réserve à l'attribution de la gestion active réellement effectuée.

Référence : [Brinson](C:/Users/Admin/GitHub/structura/backend/app/core/amc_brinson.py:158).

Préconisation : benchmark sectoriel cohérent en devise et période ; résidu explicite ; contrôle d'égalité ; absence de remplissage par données futures (`bfill`) ; attribution multipériode liée aux positions historiques pour une offre complète. En attendant : nommer G « analyse sectorielle statique indicative ». Recette : somme des effets = rendement actif à la tolérance d'arrondi, puis rapprochement distinct à la NAV.

### S11 — P1 — Scores globaux et « confiance » peuvent surpromettre

**Reproduit.** Un seul bloc H disponible, un seul trade annoncé et 1 % de couverture, avec timing à 1, suffisent à obtenir Manager Skill 100/100 « Gérant exceptionnel ». Les poids sont renormalisés sans seuil de couverture minimal. La fonction de confiance appelée avec B activé et zéro ordre attribue 90 % et décrit le P&L comme exact. C'est une sonde du constructeur, pas l'affirmation qu'une étude sans ordres passe l'ensemble du pipeline.

Le constructeur ne reçoit ni les écarts de rapprochement B, ni les injections, ni l'état des marks. L'agrégat ignore les dimensions indisponibles. Alpha, stock picking, VAG et ratios de risque partagent aussi des sources et des effets économiques : leurs poids ne représentent pas des preuves indépendantes.

Références : [Manager Skill](C:/Users/Admin/GitHub/structura/backend/app/core/amc_managerskill.py:218), [confiance](C:/Users/Admin/GitHub/structura/backend/app/core/amc_confidence.py:25).

Préconisation : séparer qualité des données, précision statistique et score exploratoire ; minimum de dimensions/observations ; couverture pondérée par montant ; état « conclusion insuffisamment étayée » ; analyse de sensibilité aux poids. Ne pas appeler « probabilité » les pourcentages de confiance heuristiques. Recette : aucun diagnostic global catégorique avec un seul petit échantillon ou une réconciliation non validée.

### S12 — P1 — Risque de réutiliser une synthèse ou une attribution d'une autre étude

**Confirmé par lecture du frontend.** `runStudy()` remplace le résultat et remet Brinson à zéro, mais ne vide ni `syntheseText` ni `attrResult`. L'export envoie ces variables avec le nouveau résultat. Charger une sauvegarde restaure la synthèse, mais remet Brinson et l'attribution séparée à zéro : les restitutions complémentaires ne font pas partie de la sauvegarde actuelle.

Références : [sauvegarde et chargement](C:/Users/Admin/GitHub/structura/frontend/src/views/AmcView.vue:4915), [relance et export](C:/Users/Admin/GitHub/structura/frontend/src/views/AmcView.vue:5194), [persistance](C:/Users/Admin/GitHub/structura/backend/app/api/amc_studies.py).

Préconisation : résultats et rédaction liés à un identifiant/version d'étude ; invalidation lors de tout changement ; sauvegarde atomique des blocs annexes, texte, options, provenance IA et PDF émis ; contrôle avant export. Recette interactive indispensable : rédiger A, lancer B, exporter B ; aucun texte ou tableau A ne doit subsister silencieusement.

### S13 — P1 pour usage partagé — Isolation partielle, chemins serveur et store commun

**Constat statique.** Les routes AMC examinées demandent une authentification ; les sauvegardes sont filtrées par propriétaire et les lectures/suppressions vérifient l'utilisateur. C'est un bon point à conserver.

En revanche, un utilisateur authentifié transmet un chemin serveur libre à la détection et aux calculs. Les chemins du manifeste ne sont pas confinés à un espace de travail autorisé. Les routes de prix permettent à tout utilisateur authentifié d'importer, remplacer ou supprimer les séries du store partagé. Aucun droit de propriétaire/admin distinct n'est vérifié à ces endroits. La sauvegarde par utilisateur ne suffit donc pas à isoler les données utilisées par les calculs. CORS reste ouvert globalement ; l'inscription publique peut rejoindre Demo.

Références : [API Studies](C:/Users/Admin/GitHub/structura/backend/app/api/amc_studies.py), [API prix](C:/Users/Admin/GitHub/structura/backend/app/api/amc_prices.py), [API AMC](C:/Users/Admin/GitHub/structura/backend/app/api/amc.py), [auth](C:/Users/Admin/GitHub/structura/backend/app/api/auth.py:237), [application](C:/Users/Admin/GitHub/structura/backend/app/main.py:65).

Préconisation : identifiant de dataset autorisé à la place d'un chemin libre ; espaces par client ; rôles distincts pour calculer et administrer les données ; imports bornés en taille ; journal des changements ; politique de partage explicite. Pour le pilote, conserver une instance dédiée et un périmètre mono-opérateur. Ces risques sont conditionnels à l'exposition et au partage ; aucune fuite réelle n'a été recherchée ou démontrée.

### S14 — P2 — Devise, fréquence et inférence factorielle à normaliser

Le moteur A reçoit les NAV mais pas leur devise. Il soustrait le RF de la série FF, et les régressions/benchmarks ne convertissent pas explicitement la NAV EUR/CHF en une base commune. Choisir Europe pour une classe EUR ne résout pas ce problème : les facteurs développés sont publiés en USD. La documentation primaire le confirme. [Kenneth French — facteurs développés](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_5developed.html).

OLS utilise la covariance classique ; Durbin-Watson est calculé, mais ne corrige pas les erreurs-types. Annualisation à 252, seuil de cinq observations sans contrôle explicite suffisant des degrés de liberté, NAV dupliquées/irrégulières et rendements fournis contradictoires doivent être contrôlés. Les rendements à horizon de I sont pris par nombre de lignes séparément pour le titre et le benchmark, ce qui ne garantit pas des dates terminales identiques.

Les facteurs locaux disponibles s'arrêtent au 29/05/2026, Global au 28/06/2019. Au moment de l'audit, la page officielle Developed 5F indique juillet 2026 : une partie du retard local peut être résorbée par rafraîchissement. Aucun fichier n'a été actualisé pendant l'audit.

Préconisation : devise de référence et politique de hedge documentées ; alignement des périodes ; diagnostics de résidus et erreurs-types robustes HAC lorsque justifiées ; contrôle rang/degrés de liberté ; couverture temporelle visible. Statsmodels expose déjà une covariance robuste HAC. [Documentation Statsmodels](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.OLSResults.get_robustcov_results.html).

### S15 — P2 — Limites économiques des contrefactuels et des scores comportementaux

E renormalise les poids actions : un panier initial avec du cash devient un panier pleinement investi en actions. Il compare une NAV nette de frais à un portefeuille passif sans coûts équivalents. A regrossit seulement les frais de gestion, pas tous les frais : « brut » devrait préciser cette portée.

F applique les bêtas estimés sur la période à cette même période. C'est une explication rétrospective ; ni transactions ETF, ni coûts, ni contraintes, ni validation hors échantillon ne démontrent une réplication exploitable. L'intervalle du score ne propage que l'incertitude approximative du R², pas celle de toutes ses composantes.

H utilise le futur autour du trade ; 0,5 est une baseline postulée, pas un benchmark aléatoire conditionné au marché et au processus de trading. Les prix d'exécution et cours ajustés ne sont pas nécessairement comparables. C compte des lots FIFO appariés ; D utilise notamment un poids actuel et une durée maximale pour inférer la conviction. Un mandat concentré ne doit pas être pénalisé sans considération de son objectif.

Préconisation : cash et frais comparables ; ex post clairement affiché ; validation hors échantillon de F ; bootstrap par épisodes pour H/I ; nomenclature factuelle dans D ; scores contextualisés par mandat. Un diagnostic de décision ex ante nécessiterait aussi l'information et les contraintes connues au moment de la décision.

### S16 — P2 — Validation d'entrée, modularité et performance opérationnelle

**Validation sondée.** Le modèle accepte frais de performance 100 %, frais de gestion négatifs, fenêtre −1, nombre de certificats négatif et mode de reconstruction inconnu. La formule de frais de performance divise par `1 - taux` : le cas 100 % ne doit pas atteindre le moteur.

L'étude « partielle » charge composition et carnet puis lance le FIFO avant les blocs ; désactiver B/C/D ne supprime pas ces dépendances. E est toujours exécuté ; G ne fait pas partie du contrat de toggles actuel. Les exceptions de certains blocs sont isolées, mais une défaillance de chargement/FIFO empêche toute étude. Les calculs sont synchrones avec accès réseau et sans job Studies durable, reprise, annulation ou budget global visible. Certains caches benchmark en mémoire n'ont pas d'expiration ; le peuplement automatique cible d'abord la composition actuelle, ce qui peut défavoriser les titres sortis.

Références : [manifeste](C:/Users/Admin/GitHub/structura/backend/app/core/amc_manifest.py:45), [orchestration](C:/Users/Admin/GitHub/structura/backend/app/core/amc_study.py:61), [prix](C:/Users/Admin/GitHub/structura/backend/app/core/amc_prices.py:564).

Préconisation : validation métier stricte et graphe de dépendances par bloc ; diagnostic NAV seul accessible sans carnet ; bloc `skipped/error/partial/validated` ; budget et progression de job ; cache daté et couverture de tout l'univers historique. Mesurer latence et mémoire sur petits/grands carnets avant de promettre un délai de traitement.

### S17 — P2 — Industrialisation du rapport, IA et marque partenaire

L'export Vue impose `TP Advisory Services` et `UTI`. Le sélecteur client contient des ISIN et un chemin Windows spécifiques. Une API personnalisable ne signifie donc pas une marque blanche utilisable depuis l'interface. La version dite simplifiée retire surtout les annexes ; elle ne définit pas une note exécutive courte sur mesure. Le PDF reconstruit la confiance au moment de l'export avec le code courant et ne transmet pas le résultat Brinson au constructeur de confiance.

La synthèse IA permet une adoption explicite et un aperçu du contexte : points positifs. Mais certains prompts demandent un verdict ferme et de peu insister sur les données absentes. Cette politique peut amplifier les faux signaux identifiés. Le texte généré n'est pas contrôlé automatiquement contre les chiffres sources, et la provenance complète de l'appel n'est pas sauvegardée avec l'étude par le contrat actuel. Un modèle local ne rend pas tout le module hors réseau : données de marché et modèles cloud éventuels restent des flux séparés.

Références : [export frontend](C:/Users/Admin/GitHub/structura/frontend/src/views/AmcView.vue:5317), [synthèse](C:/Users/Admin/GitHub/structura/backend/app/core/amc_synthesize.py), [PDF](C:/Users/Admin/GitHub/structura/backend/app/core/amc_pdf.py:1149), [socle IA](C:/Users/Admin/GitHub/structura/docs/projects/platform/IA_COMMUNE_2026-09-17.md).

Préconisation : identité du cabinet/client paramétrable ; rapport court et annexes distincts ; citations internes des métriques ; réserves prioritaires issues des contrôles qualité ; signature de revue humaine ; archive du PDF émis ; choix explicite du traitement local/cloud. Recette visuelle de chaque section et des tableaux longs avant démonstration commerciale.

### S18 — P2 — Écart entre profondeur métier et préparation d'un produit distribuable

Aucune suite quantitative dédiée AMC/FIFO n'a été trouvée dans les tests du dépôt par noms de fichiers et recherche d'appels aux moteurs. Des tests du socle IA et un test partagé FX existent ; ils ne valident pas la chaîne Studies. Les deux tests IA ciblés exécutés passent, sans conclure sur les calculs.

Les notes on-premise décrivent un poste Windows dédié et une industrialisation encore à réaliser : installation, sauvegarde/restauration, mises à jour, journaux, support. Leur ancien constat de secret JWT en dur est dépassé par les évolutions signalées dans l'index ; il ne faut pas le reprendre comme défaut actuel sans vérification.

Enfin, l'accès technique aux données Yahoo via yfinance n'établit pas un droit de redistribution commerciale. La documentation yfinance renvoie aux conditions Yahoo et décrit un usage personnel de l'API. Prévoir une source autorisée pour les missions et la diffusion envisagées ; ne pas promettre « données gratuites incluses sans restriction ». [Documentation yfinance](https://ranaroussi.github.io/yfinance/).

Préconisation : corpus de référence multi-AMC, tests de non-régression ciblés, paquets de données figés, contrat de support, sauvegarde testée, revue des droits des données et des dépendances. Les modalités juridiques exactes restent à valider avec les fournisseurs et les conseils du partenariat.

## 4. Lecture critique des Markdown liés à Studies

| Document | Lecture et conclusion |
|---|---|
| `CLAUDE.md` | Rôle métier et contraintes de travail appliqués ; pas de code modifié ni de suite complète |
| `docs/README.md` | Index et statut des chantiers ; ne constitue pas une preuve de livraison fonctionnelle |
| `STUDY_COMPARISON_ENGINE.md` | Lu ; moteur annoncé comme différé, absent du code repéré. Prioritaire pour la reproductibilité, mais classification des causes à revoir |
| `FIFO_MODULE.md` | Lu ; T0 prix/FX confirmé ; nombres historiques non certifiés aujourd'hui ; présentation de l'écart comme potentiellement structurel non suffisante |
| `PORTFOLIO_RECONCILIATION_LESSONS.md` | Lu ; leçons sur les sources, FX, injections et rapprochements retenues |
| `POSTMORTEM_2026-07-16_CH1352587724_PNL_RECONCILIATION.md` | Lu ; positions fantômes et déficits restent un sujet de qualification, pas une preuve de correction |
| `IA_COMMUNE_2026-09-17.md` | Lu ; contrat IA partagé présent ; le dernier appel consultable n'est pas un historique durable des preuves |
| `DEPLOIEMENT_ONPREM.md` | Lu ; cible poste Windows dédié ; plusieurs observations datées doivent être revérifiées avant utilisation commerciale |
| `FRED_INTEGRATION_ROADMAP.md` | Cadrage initial consulté : enrichissements macro et vintages envisagés ; aucune capacité FRED revendiquée dans le pitch |
| `OLD_AVANCEMENT.md` | Consulté comme historique uniquement ; chiffres et ancien VAG ne doivent pas alimenter une démonstration actuelle |
| `OLD_REPRISE_TRAVAIL.md` | Sections historiques consultées ; document archivé, non retenu comme référence normative des formules |

Trois notes signalées par l'index sont absentes de ce checkout, y compris dans la recherche des fichiers ignorés sous `docs` et `.claude` : `DECISION_ANALYSIS_ENGINE.md`, `MANAGER_DNA_ENGINE.md`, `SKILL_VS_LUCK_ENGINE.md`. Leur contenu n'a pas été lu et ne doit pas être inventé. L'index les décrit comme idées validées, non implémentées. Elles sont donc uniquement des pistes de feuille de route.

La comparaison d'études doit distinguer au moins données brutes, révisions de prix/FX/corporate actions, paramètres, version de méthode et texte. Deux études ayant le même `as_of` peuvent différer après correction d'une donnée, sans changement de code. Des dates différentes n'expliquent pas automatiquement tout delta. La future comparaison doit exposer des indices de causalité vérifiables, pas prétendre déduire une cause certaine du seul `as_of`.

## 5. Feuille de route proposée

| Lot | Contenu | Critère de sortie |
|---|---|---|
| Démonstration du 23 septembre | Dossier dédié autorisé/anonymisé ; chiffres sélectionnés et contrôlés ; scénario sans dépendance réseau ; pitch de partenariat ; réserves méthodologiques assumées | Démonstration répétée, support de secours et aucune promesse de fonctionnalité absente |
| 1 — Fiabilité des calculs | S01 à S10 : dates, FX, exécutions, inputs, drawdown, NAV, benchmark et attribution ; validation d'entrée | Cas de contrôle reproduits puis corrigés ; corpus multi-AMC rapproché ; aucun agrégat silencieux sur donnée manquante |
| 2 — Reproductibilité de la restitution | S11/S12/S17 : score/qualité, versions d'étude, annexes, synthèse, empreintes, PDF émis, comparateur | Une étude sauvegardée retrouve toutes ses preuves ; aucune contamination entre deux études ; différence expliquée par provenance |
| 3 — Pilote cabinet | Marque et clients paramétrables, rôles, espaces de données, installation, support, droits de données | Trois dossiers pilotes acceptés conjointement ; restauration et exploitation démontrées |
| 4 — Différenciation avancée | Talent/hasard, empreinte de style, décisions ex ante, Brinson multipériode, réplication hors échantillon, suivi périodique | Validation méthodologique et critères commerciaux propres à chaque extension |

Ordre recommandé : **sécuriser les moteurs existants avant d'ajouter de nouveaux scores**. Aucun budget ni délai ferme n'est déductible de cette seule revue. Chiffrer par lot après qualification des données du cabinet ; la réconciliation/corporate actions et l'industrialisation partagée sont les postes les plus incertains.

Le pilote proposé est une prestation accompagnée sur trois AMC et deux arrêtés, avec un dossier simple USD, un multidevise et un cas de corporate action/flux. Livrables : qualification des données, étude contrôlée, note de comité, liste de questions au gérant, restitution et bilan du pilote. Les seuils de rapprochement sont à fixer avec le cabinet par classe de métrique ; un écart non expliqué ne devient pas acceptable simplement parce qu'il est petit.

## 6. Journal des vérifications

| Cas | Fonction réelle sondée / contrôle | Résultat observé |
|---|---|---|
| Date B&H | `compute_bh` avec NAV arrêtée avant le dernier cours | VAG −40 points au lieu de 0 à date alignée |
| FX B&H absent | `compute_bh`, série FX vide | Disponible, rendement local conservé, zéro avertissement prix |
| FX mark absent | `build_marks`, parquet JPY et FX vide | 110 JPY devient mark numérique 110 en devise USD |
| Benchmark I absent | `compute_stockpicking_score`, un achat | Score 94 ; p=0,1056 ; texte « significatif » contradictoire |
| Score global incomplet | `compute_manager_skill_score`, H seul | 100/100 « Gérant exceptionnel » |
| Confiance sans preuve B | `build_confidence`, B activé, zéro ordre | 90 % ; ne constitue pas un test E2E d'étude vide |
| Perte initiale | `_nav_to_returns` puis `_drawdown_series` | 100→50→50 : drawdown 0 % |
| Rachat total | `_nav_reconciliation` | Valeur terminale 1 100 au lieu de 0 ; P&L 1 200 au lieu de 100 |
| Entrées invalides | `ManualParams` | Valeurs économiques invalides acceptées |
| Benchmark troué | `run_analysis`, FF 80 dates et benchmark 30 valeurs | Régression benchmark sur 79 rendements |
| Brinson | `compute_brinson`, séries/proxies synthétiques | Effets 1,75 points pour actif 11,75 points ; fin des prix après fin NAV |
| Sélection introuvable | `_resolve_order_files` | `None`, susceptible d'activer la redétection aval |
| Exécution nulle | `_order_from_item` | Quantité 0 remplacée par demande de 10 ; FX nul/absent remplacé par 1 |
| Pertes constantes | `_score_downside_risk` | Semi-déviation 0 %, Sortino numériquement extrême |
| Contrat IA | `pytest backend/tests/test_ai_workbench.py -k 'amc or modules_defer_defaults' -q -p no:cacheprovider` | **2 passed, 14 deselected** |
| Fraîcheur facteurs | Lecture parquet uniquement | Séries actives locales : 29/05/2026 ; Global : 28/06/2019 |

Les cas unitaires synthétiques prouvent les chemins et formules concernés ; ils ne mesurent pas leur impact sur le portefeuille réel de Philippe. Les étapes suivantes de validation doivent réutiliser ces contrôles puis une chaîne complète sur des données indépendamment rapprochées.

**Décision proposée pour mercredi : présenter Studies et vendre un pilote accompagné. Conditionner la licence opérationnelle et les engagements de fiabilité à la recette des lots pertinents.**


## Suite du chantier

Les corrections autorisées ensuite par Philippe, les tests et les limites restantes sont documentés dans [Studies — processus et corrections](../projects/studies/STUDIES_PROCESS_ET_CORRECTIONS_2026-09-20.md). Les constats ci-dessus décrivent l’état audité avant ce chantier.
