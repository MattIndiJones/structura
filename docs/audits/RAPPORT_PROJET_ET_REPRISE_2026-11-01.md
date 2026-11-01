# Structura — avis sur le projet et reprise sur un autre ordinateur

**Date : 1er novembre 2026.**

Ce document répond à la demande initiale de Philippe : comprendre le projet,
donner un avis clair sur sa qualité et ses priorités, puis conserver une synthèse
utile pour poursuivre le travail sur un autre poste.

Il réunit l'appréciation générale, les corrections de cette conversation, les
preuves disponibles et les consignes de reprise. La base Git initiale est
`f58fab3e4c0178e3493c3231bba89f77b1a89922`, sur `main`. La livraison qui contient
ce rapport ajoute les changements du 1er novembre à cette base.

## 1. Mon avis général

**Structura possède une base métier sérieuse et un périmètre déjà très riche.**
Son intérêt principal est de relier la définition du payoff, le pricing, les
conditions économiques, la RFQ, le booking et la vie du produit. C'est cette
continuité qui peut en faire un outil utile au desk.

Les choix structurants sont bons : origine au fixing initial, séparation entre
observation et paiement, distinction taux/funding, termes versionnés, conservation
des états réalisés et traçabilité des hypothèses. La présence de plusieurs modèles
est intéressante, mais elle vaut surtout si le modèle effectivement utilisé, sa
calibration et son domaine de validité restent visibles.

**La priorité est maintenant la cohérence des parcours et des données.** Les
problèmes rencontrés dans cette conversation le montrent : une capacité Admin
interprétée différemment entre frontend et backend, plusieurs chemins de traitement
des historiques, puis un bouton de prix reconstruisant un contexte incomplet.
Chaque morceau pouvait sembler cohérent isolément, alors que le parcours utilisateur
échouait à leur jonction.

Je privilégierais donc la consolidation des workflows existants, des jeux de
référence reproductibles et une interface plus compacte avant d'élargir encore
le catalogue fonctionnel.

## 2. Portée exacte de ce rapport

La lecture de `CLAUDE.md`, de l'index documentaire et des sources des domaines
modifiés est actuelle. Le code des routes, calendriers, historiques, backtests,
références de volatilité et composants concernés a été confronté à des tests.

Pour la vue d'ensemble, ce rapport s'appuie également sur le
[rapport d'application en 44 chapitres du 24 octobre](APPLICATION_REVIEW_2026-10-24.md),
ses annexes et les notes de corrections qui lui ont succédé. Ces éléments sont
historiques et datés ; ils ne deviennent pas une nouvelle qualification complète
au 1er novembre.

**Je ne revendique pas une lecture ligne par ligne de tous les fichiers ni une
recette exhaustive du projet.** La demande initiale de revue générale a été
réorientée vers les anomalies concrètes rencontrées dans le Pricer. Ce document
est une synthèse étayée et un bilan de ces travaux, avec les limites restantes.

Repères d'inventaire au moment de la préparation : 48 fichiers Python directement
dans `backend/app/api`, 45 vues Vue directement dans `frontend/src/views`, et
211 fichiers Markdown dans `docs` avant ajout de ce rapport. Ces comptes décrivent
le volume, pas un taux de couverture.

## 3. Ce que couvre le projet

| Domaine | Rôle dans le workflow | Appréciation et contrôle à conserver |
|---|---|---|
| PayScript et Economics | Définir le payoff, ses paramètres et ses calendriers | Bonne séparation entre logique déclarée et valeurs économiques effectivement utilisées |
| Pricer et modèles | Prix, Greeks, profils de payoff, trajectoires et probabilités | Les unités, dates et paramètres propres au modèle doivent suivre le même chemin jusqu'au moteur |
| Données de marché | Cours, volatilités réalisées, dividendes, corrélations, taux et FX | Provenance, date effective, convention d'ajustement et hypothèses manuelles sont essentielles |
| Backtest et comparateur | Rejouer un produit sur l'historique et explorer des candidats | Les périodes comparées, lacunes, substitutions et limites des clôtures doivent être visibles |
| Product, RFQ et booking | Conserver les termes, consulter les banques et enregistrer l'exécution | Le dossier canonique, les versions, reçus et contrôles d'idempotence sont des points forts |
| Fixings, lifecycle et MtM | Suivre les événements et valoriser la vie restante | Préserver les fixings contractuels, la mémoire du payoff et les flux déjà réalisés |
| Valuation Explain et risque | Expliquer les variations et mesurer les expositions | Distinguer exposition actuelle, profils futurs et conventions de calcul |
| CRM, AMC, FIFO et études | Contexte commercial, portefeuilles et analyses | La qualité des données et les conventions de reconstruction limitent la portée des conclusions |
| Documents et IA | Term sheets, KID/EMT indicatifs, assistance et simulation | Ne pas confondre un document généré ou un texte d'IA avec une validation quantitative ou réglementaire |
| Administration et installations | Droits, référentiels, comptes et environnements privés | Les droits affichés, routes autorisées et installations actives doivent rester cohérents |

Les domaines hors des corrections décrites ci-dessous ne sont pas tous rejoués
dans cette conversation. Le rapport du 24 octobre reste le point d'entrée pour
leur description détaillée et leurs restrictions historiques.

## 4. Ce qui me paraît solide

**Les conventions financières fondamentales.** Le strike est l'origine, la date
de valeur porte l'échange initial et le prix tient compte du règlement. Le funding
est séparé du drift du sous-jacent. Ces principes sont formalisés dans le projet.

**La représentation du contrat.** Les termes Product, les versions et les
snapshots fournissent une base pour éviter qu'une donnée de marché ou une édition
tardive ne transforme silencieusement un produit déjà exécuté.

**La continuité du workflow.** Le projet relie beaucoup d'étapes qui seraient
autrement dispersées dans des feuilles Excel ou des outils séparés. Le potentiel
opérationnel est réel si cette continuité reste testée de bout en bout.

**Les mécanismes de preuve.** Tests déterministes, cas synthétiques, reçus de calcul,
empreintes et journaux existent. Leur valeur vient de la précision de leur périmètre :
il faut toujours savoir ce qu'ils démontrent et ce qu'ils ne démontrent pas.

## 5. Les fragilités qui méritent la priorité

### 5.1 Plusieurs chemins peuvent exprimer différemment la même hypothèse

Le backtest principal, le comparateur, le chargement de volatilité et les fixings
officiels n'ont pas le même objectif. Des conventions différentes peuvent être
légitimes, mais elles doivent être nommées et centralisées au bon niveau.

Les correctifs du 1er novembre réduisent ces divergences dans les parcours visés.
Ils ne remplacent pas une revue globale de tous les consommateurs. En particulier,
le nouveau mode de qualification des séances est demandé par le prix indicatif
du comparateur ; les autres appels à `hist_vol` conservent leur comportement par défaut.

### 5.2 Le contexte de prix doit être transmis entièrement

Une omission de devise, de paiement, de courbe ou de calendrier peut faire échouer
une analyse ou produire une différence économique difficile à voir. Le prix
indicatif du comparateur s'appuie maintenant sur le corps commun du Pricer.
Il faut poursuivre cette discipline dans les autres écrans qui construisent
encore leurs requêtes séparément.

### 5.3 La richesse du moteur demande une qualification par domaine

Un modèle présent dans le menu n'est pas nécessairement qualifié pour chaque
barrière, panier, calibration ou condition de marché. Les limites déjà documentées
sur les grilles temporelles, dynamiques, sensibilités et dépendances statistiques
doivent rester rattachées à leurs modèles et à leurs preuves.

### 5.4 La simplicité visuelle participe à la fiabilité métier

Des formulaires trop grands, des règles dupliquées ou une erreur qui déforme un
tableau compliquent la lecture. Les derniers changements vont vers des sélecteurs
repliables, des valeurs retenues visibles et un détail accessible à la sélection.
Le thème remappe les couleurs Tailwind : un gris supposé clair pouvait devenir
noir au survol. Le comparateur utilise maintenant les bleus clairs du thème.

### 5.5 La reproductibilité doit inclure l'environnement

Le code, les fichiers verrouillés et les données de départ doivent être identifiés.
Un résultat vert obtenu sur un ancien `node_modules` ne prouve pas à lui seul
qu'un nouveau clone se reconstruit. Une installation frontend propre est vérifiée
dans un dossier isolé lors de cette livraison.

## 6. Corrections réalisées dans cette conversation

| Sujet | Cause ou demande | Résultat livré |
|---|---|---|
| Nouveau pricing renvoyé à l'accueil | Divergence d'interprétation des droits du workspace Admin | Capacités serveur cohérentes et compatibilité frontend explicite, sans élargir les droits des comptes techniques |
| Lien Trading vers CCR | Ancien chemin `/ccr` | Lien corrigé vers `/risk/ccr` |
| Début du backtest fixé à 2010 | Début indépendant des historiques disponibles | Première date valide locale proposée, commune au panier ; date automatique au chargement si nécessaire |
| Cours absents | Rejet global avant lecture des observations du payoff | Following explicite, 10 jours calendaires par défaut, ou mode strict |
| Transparence des décalages | Substitution difficile à identifier | Avertissement, dates demandées/effectives, titre concerné, motif et export complet |
| Calendriers trop volumineux | Deux listes toujours ouvertes et règles redondantes avec une seule sélection | Sélecteurs compacts ; combinaison masquée avec un seul calendrier |
| Défauts des calendriers | Confusion possible entre marché du titre et devise du deal | Place proposée selon le titre, règlement selon la devise ; Milan et Paris ajoutés comme places d'observation |
| Comparateur encore bloqué par l'ancien historique | Chemin distinct du backtest principal | Même lecteur Following et période commune à l'univers exploitable, avec exclusions explicites |
| Prix indicatif impossible | Ancienne qualification de l'historique de volatilité | Qualification des séances ouvertes, sans remplir les vrais cours manquants ; contexte complet du prix conservé |
| Détail absent après sélection | Classement limité à des statistiques résumées | Sélection d'une ligne avec statistiques, deux graphiques, fenêtres et export, comme le BT général |
| Cohérence du détail avec le classement | Risque de rejouer une autre période ou des données modifiées | Contexte conservé et empreinte des observations ; refus explicite en cas de dérive |
| Survol sombre | Couleur neutre remappée en encre par le thème | Bleu très clair au survol, plus marqué pour la sélection |

Les choix personnalisés et les contrats figés sont préservés. Le Following du
backtest ne s'applique pas aux fixings contractuels officiels. Les prix historiques
de calibration ne sont pas comblés par ce Following.

Les notes détaillées sont accessibles depuis [l'index](../README.md) :

- [Routes et accès](ROUTE_ACCESS_FIXES_2026-11-01.md) ;
- [Début commun et Following](../projects/pricing/BACKTEST_HISTORY_FOLLOWING_2026-11-01.md) ;
- [Calendriers et comparateur](../projects/pricing/CALENDARS_COMPARATOR_2026-11-01.md) ;
- [Prix et détails graphiques](../projects/pricing/COMPARATOR_DETAILS_PRICING_2026-11-01.md).

## 7. Ce qui a réellement été vérifié

| Vérification | Résultat conservé | Portée |
|---|---|---|
| Capacités backend et accès | 11 tests ciblés réussis lors de la correction des routes | Droits et contexte d'installation visés |
| Lot calendriers/comparateur | 125 tests backend ciblés réussis | Calendriers, Following, replay, cache et exclusions de l'univers |
| Lot prix/détails | 105 tests backend ciblés réussis | Détail cohérent, calibration par séance, oracles et chemins voisins |
| Dernier build frontend du poste | 959 tests réussis, compilation réussie | Ensemble des tests frontend exécutés par `npm run build` |
| Reconstruction frontend propre avant livraison | `npm ci`, 959 tests et build Vite 8.3.0 réussis avec Node 22.17.0 | Versions verrouillées, installation isolée incluant le dossier `shared` ; artefacts compilés repris dans la livraison |
| Contrôles navigateur du dernier parcours | 9 contrôles réussis, sans erreur JavaScript | Routes et formulaires visés, prix simulé, sélection, graphiques, export et largeur réduite |
| Retour de Philippe | « cela fonctionne » après les corrections prix/détail | Confirmation utilisateur du parcours rencontré, sans qualification exhaustive |

**Les nombres backend ne s'additionnent pas : leurs périmètres se recouvrent.**
La suite backend complète n'a pas été lancée. Les tests du backend utilisent des
runtimes privés et synthétiques ; les API du navigateur de recette sont simulées.
Un oracle de remboursement déterministe confronte notamment le prix à
`exp(-r × temps jusqu'au paiement)`.

Un test de booking de `test_market_data_governance.py` avait échoué lors d'un
groupe précédent parce que sa requête ne renseignait pas le format/la famille
du produit. Le même échec a été reproduit sur le code de référence sans les
modifications de cette conversation. Il ne constitue pas un défaut nouveau
établi du booking ; sa fixture mérite une actualisation séparée.

Les journaux, captures et scripts de contrôle situés dans `.runtime` restent
locaux et sont exclus de Git. Les tests source et les notes métier sont livrés.
Le journal `.runtime/delivery-frontend-build.log` identifie la reconstruction
propre effectuée pour la reprise sur un autre ordinateur.

## 8. Ce qui reste à qualifier

- Les historiques réels de chaque titre et les opérations sur titres : les tests
  synthétiques ne certifient pas les données AXA, BNP, L'Oréal ou STM.
- Les autres consommateurs de données et les parcours moins courants, notamment
  ceux qui n'utilisent pas encore les mêmes règles que le comparateur corrigé.
- Les modèles avancés et leurs paramètres propres à chaque candidat. Une
  calibration Heston, un quanto ou une corrélation aux taux ne se copient pas
  silencieusement depuis le titre initial.
- Les barrières intrajournalières : des clôtures quotidiennes disponibles ne
  démontrent pas l'absence de franchissement entre ces clôtures.
- Les corrections de fixings consommés, exceptions lifecycle et sorties
  opérationnelles complexes, selon les limites des notes de domaine.
- La confirmation bancaire d'un paiement : un flux contractuel ou un statut
  applicatif n'est pas une preuve de virement.
- L'usage réglementaire des documents et mesures de risque : les limites KID/EMT,
  VaR, CCR et CVA des rapports de domaine demeurent à respecter et à revérifier.
- L'exploitation distante, la restauration, les volumes et les défaillances
  d'infrastructure avant toute promesse de service de production.

Ces points sont des limites de preuve ou des sujets de qualification. Ils ne
doivent pas être présentés indistinctement comme des bugs actuellement reproduits.

## 9. Ordre de travail recommandé

1. **Stabiliser le parcours quotidien** : création → prix → backtest → comparaison
   → adoption → RFQ → booking, avec des profils représentatifs et des produits connus.
2. **Harmoniser les contrats de données** : source, date, unité, fraîcheur,
   calendrier, approximation et comportement en cas d'absence.
3. **Constituer des références reproductibles** : produits simples, paniers,
   calendriers, dates de paiement et cas limites, avec résultats attendus indépendants.
4. **Compléter la qualification lifecycle/risque** : fixings, rappels, mémoire,
   paiements différés, résiduel et explication des variations.
5. **Réduire progressivement la duplication** des corps de requête et des règles
   dans le store Pricing et les endpoints, en conservant les conventions métier.
6. **Qualifier l'exploitation et les documents** selon l'usage réellement visé.

## 10. Reprendre sur l'autre ordinateur

### Récupérer le code

Pour une copie existante, conserver d'abord tout travail local puis exécuter :

```powershell
git switch main
git pull --ff-only origin main
git log -1 --oneline
```

Pour un nouvel emplacement :

```powershell
git clone https://github.com/MattIndiJones/structura.git
cd structura
```

Un refus de fast-forward ou des modifications locales doivent être réconciliés,
sans reset forcé ni écrasement du travail existant.

### Recréer les dépendances

Le projet fournit `requirements.lock.txt` et `frontend/package-lock.json`.
La CI utilise Python 3.11 et Node 20 ; utiliser un Node récent compatible avec
les exigences du fichier verrouillé, pas un ancien Node 20 non mis à jour.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
npm --prefix frontend ci
npm --prefix frontend run build
```

Le frontend compilé est versionné dans cette livraison, mais la reconstruction
ci-dessus permet de vérifier le poste de reprise. Les environnements `.venv` et
`node_modules` ne sont pas transportés par Git.

### Ouvrir la bonne installation

Utiliser `lancer_structura.bat`, puis le choix **Structura complet — Admin**, ou
le workflow d'installation déjà configuré sur ce poste. Le fonctionnement du
lanceur est décrit dans
[la note d'exploitation](../projects/platform/STRUCTURA_LAUNCHER_2026-10-13.md).
Ne pas contourner les contrôles d'installation ni le marqueur de retrait legacy.

Après une mise à jour, redémarrer le backend concerné par le workflow habituel,
actualiser le navigateur avec **Ctrl + F5**, puis relancer la comparaison. Les
anciens résultats en mémoire ne disposent pas forcément du contexte de détail
ajouté dans cette livraison.

### Comprendre ce qui ne suit pas avec Git

**Le code suit ; les données privées locales ne suivent pas automatiquement.**
Les bases SQL, comptes, clés, tokens, configurations privées, documents stockés,
historiques et preuves `.runtime` ne doivent pas être poussés dans le dépôt.

Un autre poste peut donc ouvrir une installation différente ou vide. Si l'objectif
est de retrouver les mêmes dossiers métier, il faut organiser une reprise privée
cohérente de l'installation, de ses documents et de ses secrets de signature.
Copier seulement une base ou publier ces éléments dans Git serait insuffisant.

## 11. Point de départ pour la prochaine session

Lire `CLAUDE.md`, [l'index documentaire](../README.md), ce rapport puis la note
du domaine concerné. Commencer par identifier l'installation, les données et les
preuves réellement disponibles sur le nouveau poste.

Les derniers changements portent sur la fiabilité du Pricer et des backtests.
La prochaine étape utile est une recette métier ciblée sur le parcours que
Philippe veut utiliser, ou la poursuite de la revue globale à partir des sujets
de la section 8. Aucun audit exhaustif supplémentaire ne doit être déduit du
seul fait que le code a été committé et poussé.
