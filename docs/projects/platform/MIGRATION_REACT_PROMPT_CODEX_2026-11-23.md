# Mission Codex : migrer l'interface de Structura vers React sans régression

Ce document est ton cahier des charges complet. Lis-le entièrement avant toute action.

**Priorité absolue : aucune régression.** Elle passe avant la vitesse, l'élégance du code et le
design. Sur un outil de pricing, un champ mal transmis ou un chiffre mal affiché peut produire un
faux prix sans aucune erreur visible. En cas de doute, tu t'arrêtes et tu poses la question à
Philippe.

Tu t'adresses à Philippe en français, comme à un pair structureur. L'interface, les messages et
les documents sont en français. Le code, les commentaires et les noms de fichiers sont en anglais.

---

## 1. Décisions déjà prises

Ne les rediscute pas. Si l'une d'elles devient impossible à tenir, arrête-toi et explique pourquoi.

1. **Nouveau projet front uniquement** : `C:\Users\admin\GitHub\structura-react`.
2. **Le backend FastAPI de Structura reste l'unique backend.** Il n'est ni copié, ni déplacé, ni
   modifié.
3. **React, TypeScript strict et SVG.** Aucune bibliothèque de graphiques, Chart.js compris.
4. **Le design cible est la version C** : poste de travail à panneaux, adouci, bleu nuit et accent
   ambre. Le prototype est dans `docs/projects/platform/prototype-react-2026-11-23/` (section 8).
5. **Quatre couches indépendantes** : design, graphiques, métier d'affichage, contrat API
   (section 4).
6. **L'interface Vue reste en service** jusqu'à une bascule explicitement validée par Philippe.
7. **Migration fonctionnelle à iso-périmètre** : ni fonction ajoutée, ni fonction retirée, ni bug
   corrigé en passant.

---

## 2. Interdits absolus

- **Ne rien modifier dans `C:\Users\admin\GitHub\structura`.** Ce dépôt est en lecture seule pour
  toi : aucun fichier, aucune branche, aucun `npm install`, aucun build dans `frontend/dist`.
- **Ne jamais lire, copier ou ouvrir le dossier `backend/data/` du poste de Philippe** ni aucune
  base réelle. Les deals, clients, RFQ et études qui s'y trouvent sont des données réelles. Le clone
  jetable de la section 9.1 ne contient que les fichiers versionnés.
- **Ne jamais arrêter une instance Structura que tu n'as pas lancée.** Ne jamais tuer tous les
  processus Python ou Node.
- **Ne jamais committer ni pousser** sans instruction explicite de Philippe dans son message
  courant. Cela vaut aussi pour `structura-react`.
- **Ne jamais calculer un prix, un Greek, une probabilité ou une valorisation dans le navigateur.**
  Tout vient de l'API.
- **Ne jamais reprendre `engine.js` du prototype.** C'est un moteur de démonstration.
- **Ne jamais inventer une donnée, un défaut ou un repli** pour faire fonctionner un écran.
- **Ne jamais supprimer, désactiver, affaiblir ou marquer `skip` un test** pour obtenir un résultat
  vert.
- **Ne jamais corriger silencieusement un comportement de l'application Vue**, même s'il te paraît
  faux. Tu le reproduis et tu l'inscris au registre (section 9.5).
- **Ne jamais lancer la suite backend complète** sans demande explicite de Philippe. Ce chantier
  ne modifie pas le backend.
- **Ne pas saturer la machine** : pas de calcul Monte Carlo lourd, et pas plus d'une instance de
  test à la fois sauf nécessité documentée.

---

## 3. Point de départ mesuré

Référence : `main` au commit `fa7ff711e9e4dfc4c2d923ea3d3e9138237f7961`. Au Lot 0, vérifie le
`HEAD` réel. S'il a changé, signale-le et prends le nouveau commit comme référence après accord de
Philippe.

| Élément | Mesure au 23/11/2026 |
|---|---|
| Entrées de routes (`frontend/src/router/index.js`) | 51 |
| Composants `.vue` | 171 fichiers, 47 985 lignes |
| JavaScript hors tests | 111 fichiers, 14 538 lignes |
| Tests Vitest | 102 fichiers, 10 500 lignes |
| `v-model` | 785, dont 209 `.number`, 9 `.trim`, aucun `.lazy` |
| `v-if` / `v-for` / `v-show` | 1 892 / 737 / 16 |
| `computed` / `watch` / `nextTick` | 603 / 171 / 39 |
| Hooks de cycle de vie | 106 |
| `Teleport` / `Transition` / `provide-inject` | 2 / 3 / 3 fichiers |
| Appels `apiFetch` / `fetch` directs | 310 / 14 |
| Fichiers important Chart.js | 17 |
| Fichiers liés au mode démo | 49 |
| Fichiers utilisant `confirmer` | 25 |
| Consommateurs de `durableCommand` | 4 |
| `utils/` indépendants de Vue | 57 sur 57 |
| `stores/` liés à Vue ou Pinia | 19 sur 22 |
| `composables/` liés à Vue ou Pinia | 13 sur 19 |

Ces chiffres servent de contrôle. Recalcule-les au Lot 0 et explique tout écart.

**À lire avant de commencer**, dans le dépôt Structura :

- `CLAUDE.md`, `AGENTS.md`, `docs/README.md`
- `.agents/skills/structura-pricing-ui/` et les autres skills du dossier `.agents/skills/`
- `docs/reference/PAYSCRIPT_REFERENCE.md`, `docs/reference/GOUVERNANCE_AMENDEMENTS.md`
- `docs/projects/pricing/EDITEUR_ECONOMICS_DESIGN.md`, `docs/projects/pricing/MODELES_PRODUITS_DESIGN.md`
- `docs/projects/platform/API_TYPEE_P1_11_2026-11-19.md`
- `docs/projects/platform/ECRANS_P1_10_2026-11-19.md`
- `docs/projects/platform/SECURITE_P1_8_2026-11-19.md`
- `docs/projects/platform/PRICING_INTERACTIF_P1_4_2026-11-19.md`
- `docs/audits/AUDIT_GLOBAL_EXECUTIF_2026-11-16.md`

Les notes datées peuvent être dépassées. En cas d'écart, **le code au commit de référence fait foi**.

---

## 4. Architecture cible

```text
structura-react/
├── docs/migration/          preuves et registres de la migration
├── src/
│   ├── legacy-core/         logique reprise de Structura, sans réécriture
│   │   ├── utils/
│   │   ├── stores/
│   │   ├── composables/     uniquement ceux sans rendu
│   │   ├── data/
│   │   └── api/             generated.js, copie exacte
│   ├── bridge/              liaison entre stores réactifs et React
│   ├── design/              jetons, styles de base, composants d'interface
│   ├── charts/              échelles et tracés purs, puis rendu SVG
│   ├── display/             formats, unités, dates, statuts en français
│   ├── app/                 coque, routeur, gardes, erreurs, confirmation
│   └── features/            un dossier par domaine métier
└── tests/
    ├── unit/
    ├── parity/              comparaison Vue contre React
    └── e2e/
```

**Règles de dépendance, contrôlées par ESLint :**

- `design`, `charts` et `display` n'importent ni les stores, ni l'API, ni `features`.
- Seuls `legacy-core` et `bridge` peuvent importer `vue` ou `pinia`.
- Aucun composant React n'appelle `fetch` : il passe par `legacy-core`.
- Aucun calcul financier dans `charts`, `display` ou les composants. Un graphique met à l'échelle
  des valeurs déjà reçues.
- Pas de `any` dans les nouvelles couches, sauf à une frontière documentée avec `legacy-core`.

**Dépendances de production autorisées :** `react`, `react-dom`, un routeur compatible avec les
blocages de navigation et le mode hash (`react-router-dom`), et temporairement `vue@3.5.45` et
`pinia@2.3.1` sans aucun rendu Vue. Toute autre dépendance demande l'accord de Philippe. Versions
exactes, `package-lock.json` obligatoire, Node 20 comme la CI.

### 4.1 Reprise de la logique : copier d'abord, ne pas réécrire

C'est la principale protection contre les régressions.

1. **`utils/`, `data/`, `api/generated.js`** : copie à l'identique. Un manifeste SHA-256 prouve
   l'identité avec la référence.
2. **Stores Pinia** : ils restent tels quels et tournent sans composant Vue. C'est déjà le cas dans
   leurs tests, qui s'exécutent en environnement `node`. La logique du Pricer, ses 14 modules et
   l'ordre de ses `watch` ne sont donc pas réécrits.
3. **Composables** : ceux qui n'ont pas de rendu sont repris. `useAiWorkbench` et
   `useBacktestHistory`, liés au routeur ou au cycle de vie, sont adaptés par une interface
   explicite, avec des tests avant et après.
4. **Tests existants des stores et utilitaires** : copiés sans modification, ils doivent passer.
5. **Le remplacement éventuel de Pinia est hors périmètre.** Il sera décidé après la bascule.

### 4.2 Le pont `bridge/`

Écris et teste le pont **avant le premier écran** :

- abonnement par `useSyncExternalStore` ;
- détection des **mutations en place** d'objets et de tableaux, très fréquentes dans les stores ;
- pas de rendu déchiré, pas de boucle, pas de fuite d'abonnement au démontage ;
- compatibilité avec `React.StrictMode`, qui rejoue les effets en développement ;
- écriture dans le store par la même affectation que le `v-model` d'origine.

---

## 5. Invariants métier à préserver

Chaque invariant doit avoir au moins un test de parité. Les chemins sont relatifs à `frontend/src/`.

### Pricing

1. **Quatre dates distinctes** : Strike/StartDate, Valeur, Maturité, Paiement. Ne les fusionne
   jamais à l'écran ni dans un corps de requête. `_baseBody` envoie
   `anchor: frozen?.strike_date ?? frozen?.value_date` (`stores/pricing/requestState.js`).
2. **Le funding reste séparé des taux.** Il n'entre qu'en actualisation, par `_fundingPayload`.
   Aucun écran ne doit fusionner taux et spread.
3. **Economics fait foi.** Le script déclare le payoff, l'unité et la valeur initiale. La valeur
   envoyée est celle d'Economics, dans `user_params`. Ne touche pas à `_syncParamOverrides`.
4. **Un champ vide n'est pas zéro.** Vide, `0`, `null` et absent sont quatre états à conserver.
5. **`PARAM()` par observation** : la dernière ligne s'étend aux observations suivantes, et une
   ligne équivaut à un scalaire.
6. **Préfixe `M_`** : la direction et l'observable viennent de l'analyse du serveur. L'interface
   ne les déduit jamais du nom.
7. **Maturité** : toujours éditable, égale à la dernière constatation, saisie retenue au blur ou à
   Entrée. Relis `MODELES_PRODUITS_DESIGN.md`, section 9.2.
8. **Termes figés au booking** : `frozen?.user_params` et le contexte figé priment sur l'écran.
9. **Provenance de la volatilité** : une vol rouverte reste `saved`. L'arrivée tardive du catalogue
   de sous-jacents ne doit pas la remplacer par un défaut (`stores/pricing/loaders.js`). Ce défaut
   a déjà fait rouvrir un script à 30 % au lieu de 23 %.
10. **Valeur de référence et valeur utilisée** restent distinctes, avec leur source et leur état de
    surcharge. Un champ qui ne pilote pas le modèle actif doit rester libellé comme référence.
11. **File de calcul** (`utils/pricingJobs.js`) : soumission, interrogation avec backoff, annulation,
    remplacement par famille via `jobChannel`, statuts terminaux, messages 429, 499 et 504. Un prix
    périmé ne s'affiche jamais comme à jour.

### RFQ, booking et cycle de vie

12. **Le sens RFQ est inversé par rapport au Deal, volontairement.** `RfqRequest.sens = achat`
    signifie que nous achetons. `Deal.sens = vente` signifie que la banque vend. Voir
    `stores/pricing/loaders.js`, ligne 567. **Ne jamais harmoniser.**
13. **Sérialisation des termes RFQ** : le contrôle de booking compare ce que chaque écran écrit.
    Teste avec la sortie réelle de chaque écran, jamais avec une fixture au format du serveur.
14. **Commandes durables** (`utils/commands.js`) : `command_key`, registre en `sessionStorage`,
    reprise après réponse perdue, un seul envoi au double clic.
15. **Une RFQ bookée reste protégée** : refus 409 affiché, lien « Voir le booking », aucun second
    booking proposé.
16. **Les réponses tardives sont ignorées** : une réponse arrivée après un changement de deal,
    d'onglet, de compte ou d'installation ne s'affiche jamais.

### Sessions, droits et sécurité

17. **Session par onglet** : `auth_token` en `sessionStorage`, jamais en `localStorage`. Reprends
    `utils/session.js` et `stores/auth.js` sans modification.
18. **Renouvellement** : 5 minutes avant l'échéance, au réveil d'une veille, retour à la connexion
    avec motif en fin de session.
19. **La déconnexion recharge la page** (`AppHeader.vue`). C'est ce qui empêche les données d'un
    compte d'apparaître dans le suivant.
20. **Gardes de navigation** : reproduis exactement l'ordre de `router.beforeEach`, pour tous les
    rôles de `backend/app/core/access.py`, le portail plateforme et le mode consultation.
21. **Modifications non enregistrées** : garde `variantDirty`, `beforeunload`, `hasContextChanges`,
    attribut `data-context-selector`, et règle de sortie de Valo Explain (lecture libre, écriture
    confirmée).
22. **Mode démo** : il ne lit ni ne modifie aucun prix, et masque toutes les valeurs sensibles,
    **graphiques compris**.
23. **Écran d'erreur global** : `#app-error`, un seul rechargement sur fragment manquant
    (`structura_fragment_reload_at`, 20 secondes), avis discret pour une action en échec.
24. **CSP réelle** (`backend/app/core/security_headers.py`) : `script-src 'self'`, donc ni script
    en ligne ni `eval`. Polices Google, iframes `blob:` et micro restent autorisés.
25. **Pas de HTML injecté.** Le seul `v-html` (`components/MarketParams.vue:192`) devient un rendu
    structuré. `dangerouslySetInnerHTML` est interdit.

### Navigation et listes

26. **Mêmes URL hash**, paramètres compris (`?deal=`, `?modele=`, `?category=`). Le routeur Vue
    utilise des contraintes de paramètres (`:id(\d+)`, `:section(apercu|liste|…)`) et des
    redirections qui doivent garder le même résultat.
27. **Bouton retour visible** sur toute vue imbriquée, avec le comportement de `ui/BackLink.vue`.
28. **Filtres partagés** : « tout sélectionner » ne prend que les lignes filtrées
    (`useDataFilter`, `DataFilterBar`).

---

## 6. Pièges de la conversion Vue vers React

| Vue | Risque | Exigence |
|---|---|---|
| `v-model` sur `type="number"` | Vue convertit **même sans `.number`** | Helper unique, testé contre `looseToNumber` de Vue |
| `.number` | `parseFloat`, sinon garde la chaîne : `12abc` donne `12`, vide donne `''` | Reproduire exactement, sans `Number()` |
| Blur sur un champ converti | Vue réécrit la valeur affichée | Reproduire |
| Composition IME | Vue n'écrit pas pendant la composition | Reproduire |
| `v-show` (16) | L'état du composant survit | Le garder monté et masqué |
| `v-if` (1 892) | L'état est détruit à la sortie | Démonter réellement |
| Clés `v-for` | Réutilisation d'état | Mêmes clés, jamais l'index à la place d'un identifiant |
| `watch` (171) | Ordre et moment d'exécution | Rester dans `legacy-core` quand c'est possible, sinon test d'ordre |
| `computed` (603) | Dépendances implicites | Pas de tableau de dépendances approximatif |
| `nextTick` (39) | Focus et mesure après rendu | `useLayoutEffect` justifié au cas par cas |
| `StrictMode` | Effets joués deux fois : double POST | Aucun effet ne déclenche une écriture sans protection |
| Fermetures asynchrones | Lecture d'un état périmé | Relire le store au retour de l'appel |
| `Teleport` | Portée du focus et des événements | Portail avec gestion du focus |
| CSS `scoped` | Fuite de styles | CSS Modules et jetons |
| Attributs de test | Parcours e2e cassés | Conserver rôles, libellés et identifiants utilisés |

---

## 7. Écrans à couvrir

**Les 51 entrées de routes sont dans le périmètre**, pas seulement les huit écrans du prototype :
connexion, compte, consultation, portail plateforme, atelier de simulation, accueil, scripts,
produits, modèles, documentation, Pricer et ses variantes, booking RFQ, booking, Valo Explain,
historique des MtM, risque, CCR, réinvestissement, AMC, FIFO, clients et leurs fiches, RFQ, RFQ
reçues, analyse, prototype réseau, trading, Structuring, Optimizer, recherches, et toute
l'administration.

Le Pricer doit garder ses cinq onglets de définition (Script, Economics, Marché & Paramètres, Deal,
Events) et ses 14 vues de résultats : Résultats, Résumé, Flux, Greeks, Profil Payoff, Chemins MC,
Probabilités, Backtest, Mark to Future, Simulation, Scénarios, Déclinaisons, KID PRIIPs et EMT.
Leur regroupement visuel peut changer. **Aucune ne disparaît.**

---

## 8. Design cible et limites du prototype

Ouvre `docs/projects/platform/prototype-react-2026-11-23/index.html` et lis `styles.css`.

**À reprendre :**

- Coque : barre de navigation, dossiers récents, bandeau produit (« ticket »), panneaux flottants,
  barre d'état.
- Couleurs : bleu nuit `#15395f`, `#1c4671`, `#285886` ; bandeau `#1a4269` ; accent ambre `#f2bf4a` ;
  fond ivoire `#e7e6e0`, panneaux `#fbfaf7`, cartes `#ffffff`.
- Formes : panneaux à 10 px, contrôles à 7 px, 8 px entre panneaux, ombre discrète, densité élevée.
- Typographie : Geist à chiffres tabulaires, Geist Mono réservée au code et aux références.
- Graphiques SVG dimensionnés aux pixels réels, avec survol, axes discrets et étiquettes directes.

**Choix de Philippe à respecter :**

- **Pas de noir, pas d'anthracite, pas de vert** comme couleur d'interface. Le vert reste limité
  aux gains et aux statuts conformes.
- **Ne pas reproduire l'interface de QISTRA.**
- Texte encre sur fond clair, jamais de texte coloré sur un fond de même teinte, deux panneaux
  voisins de couleurs différentes.
- **Une courbe de payoff n'est jamais lissée** : le saut à la barrière reste visible.
- Thème clair uniquement en V1, avec des jetons prêts pour un thème sombre ultérieur.

**Ce que le prototype montre mais que tu ne dois PAS reproduire tel quel :**

| Dans le prototype | En production |
|---|---|
| Prix recalculé pendant le glissement d'une barrière | Le glissement modifie la valeur Economics. Le prix passe à « périmé » jusqu'au prochain calcul lancé par l'utilisateur. Aucun calcul automatique |
| Grille, sensibilités et sorties calculées localement | Résultats de l'API uniquement (`/api/grid`, Greeks, probabilités) |
| Flux FastAPI et courbe de convergence | L'API expose `job_id`, `status`, `queue_position`, `elapsed_ms`. Garde l'interrogation actuelle, sans SSE ni convergence |
| Dossiers ouverts en onglets avec états parallèles | Le store du Pricer est un singleton. En V1, ces onglets sont des liens récents qui passent par les gardes |
| Radar, pipeline, limites, contrôles de prix, données fictives | Affichés seulement si une donnée réelle existe. Sinon, ils sortent de la V1 et entrent dans `DESIGN_GAPS.md` |
| Sélecteur de palette et thème sombre | Absents de la V1 |
| Huit écrans seulement | Les 51 entrées de routes restent couvertes |

Si le design entre en conflit avec un comportement existant, **le comportement gagne** et tu
signales le conflit.

---

## 9. Méthode de preuve

### 9.1 Environnement de test isolé

- Crée un clone jetable de la référence hors des deux dépôts, par exemple
  `%TEMP%\structura-ref-<sha>`.
- Utilise `e2e/structura_instance.py` : profil simulation, dossier de données temporaire, compte
  technique généré. N'utilise jamais `backend/data`.
- Pour tester React avec le vrai serveur, sa vraie CSP et ses vrais parcours, construis React et
  remplace `frontend/dist` **dans ce clone uniquement**. Le serveur attend `index.html`, `assets/`
  et `tp_logo.png`.
- Toute instrumentation de la version Vue, par exemple pour exposer les données Chart.js, se fait
  **uniquement dans ce clone**.
- Note le PID, l'heure et la commande de chaque processus lancé. À la fin ou en cas d'erreur,
  arrête-les et vérifie que leurs ports sont libres.

### 9.2 Harnais de parité

Écris **avant le premier écran React** une suite Playwright en TypeScript dans `tests/parity/`.
Le même scénario s'exécute sur Vue et sur React, puis les captures sont comparées.

**Capture de chaque requête `/api/*` et `/health` :** méthode, chemin, paramètres, en-têtes
métier, corps JSON canonique.

**Règles de comparaison :**

- Écritures (`POST`, `PUT`, `PATCH`, `DELETE`) : **même nombre, même ordre, même corps**.
- Lectures (`GET`) : même ensemble d'URL. Toute lecture en plus ou en moins est justifiée au
  registre.
- JSON : l'ordre des clés d'objet est ignoré, jamais l'ordre des tableaux.
- `null`, absent, `""` et `0` sont différents.
- Les nombres sont comparés **exactement**, sans tolérance ni arrondi.
- Seuls peuvent être normalisés : jeton, `command_key` aléatoire, identifiants créés, identifiants
  de job, horodatages générés. La liste est dans `tests/parity/normalizers.ts`. **Tout ajout demande
  l'accord de Philippe.**

**Données déterministes :** données créées par l'API dans l'instance jetable, données de marché
figées par fixtures, seed 42, date de valorisation fixe.

**Couverture minimale :**

- chaque route, avec chaque rôle pertinent, y compris les refus ;
- chaque formulaire : valeur nominale, champ vidé, valeur invalide, valeur limite ;
- les **19 modèles de produits** du catalogue, chacun pricé ;
- le Phoenix mémoire sous GBM, Heston, SABR, Local Vol et LSV, plus les modèles de taux ;
- au moins un produit par devise, un mono-sous-jacent et un panier ;
- pricing initial, deal en cours de vie, deal rouvert, variante, RFQ vers Pricer, RFQ vers booking ;
- réponses simulées 401, 403, 404, 409, 422, 429, 499, 500, 503, 504, réseau coupé, réponse tardive,
  double clic, rechargement en cours d'édition, retour navigateur, lien profond ;
- mode démo actif et inactif, mode consultation.

### 9.3 Portes de validation

Un lot n'est terminé que si **toutes** ses portes sont vertes.

| Porte | Contrôle | Seuil |
|---|---|---|
| G1 | `tsc --noEmit`, ESLint, frontières d'import | 0 erreur |
| G2 | Manifeste SHA-256 de `legacy-core` | Identique à la référence, écarts déclarés seulement |
| G3 | Tests unitaires repris et nouveaux | 100 % verts, aucun test perdu |
| G4 | Parité des requêtes | 0 différence |
| G5 | Parité des valeurs affichées : libellés, unités, signes, décimales | 0 différence non approuvée |
| G6 | Parité des comportements : gardes, erreurs, annulation, brouillons, double clic | 0 différence |
| G7 | Parité des données de chaque graphique contre Chart.js | Séries identiques |
| G8 | Parcours `e2e/` de Structura, **non modifiés**, sur le build React | 100 % verts |
| G9 | Sécurité : 0 violation CSP, aucun jeton en `localStorage`, aucune donnée après changement de compte | 0 défaut |
| G10 | Rendu à 1440×900, 1280×720, 1024×768, 390×844 : aucun débordement ni texte coupé, focus clavier, contraste ≥ 4,5:1 | 0 défaut |
| G11 | Console du navigateur | 0 erreur, 0 avertissement React |
| G12 | Dérive de la référence (section 11) | Aucune non traitée |

### 9.4 Correspondance des tests

Tiens `docs/migration/TEST_MAPPING.md` avec **une ligne par fichier de test Vue** : copié tel quel,
adapté, ou remplacé, avec le nom du successeur et ce qu'il prouve. Les tests qui montent un
composant ou lisent une source `.vue` doivent garder une preuve équivalente. Un test sans successeur
bloque le lot.

### 9.5 Registre des écarts

`docs/migration/REGRESSION_LEDGER.md` consigne tout écart constaté :

- **A, défaut React** : à corriger avant de continuer.
- **B, défaut déjà présent dans Vue** : comportement conservé, signalé à Philippe, jamais corrigé
  sans son accord.
- **C, changement de présentation voulu** : valeur, unité et comportement inchangés, décrit
  précisément.

---

## 10. Plan par lots

**Tu t'arrêtes à la fin de chaque lot.** Tu présentes le rapport (section 12) et tu attends le
feu vert de Philippe. Ne commence jamais le lot suivant de ta propre initiative.

| Lot | Contenu | Sortie attendue |
|---|---|---|
| **0. Référence** | Vérifier le commit, relire les notes, recalculer la section 3, créer le clone jetable, jouer sur Vue `npm ci`, les tests, le build et `e2e/` | Rapport de base avec chiffres exacts. **Aucun code React** |
| **1. Inventaire** | Matrices des routes, droits, appels API, stores, `v-model`, `watch`, confirmations, stockage, graphiques et tests | `docs/migration/*_MATRIX.md`, chaque élément avec fichier et ligne |
| **2. Harnais** | Parité Vue contre Vue, sans React | Deux passages successifs identiques : aucun bruit |
| **3. Fondations** | Projet, `legacy-core`, manifeste, pont, session, routeur, gardes, erreurs, confirmation, mode démo, coque | G1, G2, G3, G9. Écrans encore vides, aucune donnée inventée |
| **4. Bibliothèques** | Jetons, composants d'interface, champs numériques, tableaux, bibliothèque SVG | Tests de chaque composant, page de référence interne |
| **5. Accès** | Connexion, compte, consultation, accueil | Toutes les portes |
| **6. Bibliothèque produit** | Scripts, produits, modèles, documentation | Toutes les portes |
| **7. Pricer** | Lots internes : Script, Economics, Marché, Deal, Events, puis les 14 vues | Toutes les portes. **Revue de Philippe obligatoire** |
| **8. Cycle de vie** | Booking, historique MtM, Valo Explain, réinvestissement | Toutes les portes |
| **9. Risque** | Risk Management, ses 8 onglets, CCR | Toutes les portes |
| **10. RFQ** | Demandes, reçues, analyse, réseau, booking RFQ | Toutes les portes |
| **11. Clients** | Sections, fiches, contacts, opportunités, import | Toutes les portes |
| **12. Structuring** | Optimizer, recherches, résultats | Toutes les portes |
| **13. Exploitation** | Trading, administration, portail plateforme, atelier | Toutes les portes |
| **14. Études** | FIFO. **Arrêt avant AMC** | Voir ci-dessous |
| **15. Répétition générale** | Toutes les portes sur tout le périmètre, deux passages consécutifs, retour arrière répété dans le clone | Rapport de parité complet |
| **16. Proposition de bascule** | Procédure, retour arrière, adaptation de la CI, liste des décisions restantes | Document uniquement. **Rien n'est appliqué** |

**AMC :** `AmcView.vue` compte 5 912 lignes et le projet prévoit de faire passer l'étude AMC sous
QISTRA (décision du 18/11, `ECRANS_P1_10_2026-11-19.md`). Avant de la migrer, demande à Philippe si
elle doit être portée dans React ou rester hors de cette migration.

**Conditions d'arrêt immédiat :**

- un changement backend semble nécessaire ;
- une porte reste rouge après deux tentatives de correction ;
- un comportement Vue est ambigu ;
- une règle de ce document contredit le code de référence ;
- une donnée réelle apparaît dans un test ou un journal ;
- la référence a changé sur un écran déjà migré.

---

## 11. Gestion de la dérive

Structura continue d'évoluer pendant la migration.

- Génère `docs/migration/SOURCE_MANIFEST.json` : pour chaque écran migré, le SHA-256 de ses fichiers
  source Vue, stores, utilitaires et tests.
- Au début de chaque lot, compare au `main` local de Structura, en lecture seule.
- Toute différence sur un fichier migré est listée, puis reportée après accord de Philippe, avec
  mise à jour des tests de parité.
- `api/generated.js` doit rester identique à celui de la référence. Une différence signale un
  changement de contrat et bloque le lot.

---

## 12. Rapport de fin de lot

Termine chaque lot par ce rapport, en français :

```text
LOT n : terminé | bloqué
Commit de référence :
Fichiers créés ou modifiés :
Portes : G1 … G12, résultat et commande exacte de chacune
Tests : avant / après / ajoutés / adaptés (aucun perdu : oui ou non)
Scénarios de parité : joués / identiques / écarts
Registre : nouveaux écarts A, B, C
Non vérifié :
Risques restants :
Processus lancés et arrêtés (PID, ports libérés) :
Décision attendue de Philippe :
```

Ne déclare jamais un point vérifié si tu ne l'as pas exécuté. Un test non lancé s'écrit « non
vérifié ».

---

## 13. Définition de terminé

La migration n'est terminée que si :

- les 51 entrées de routes sont couvertes, sous réserve de la décision AMC ;
- toutes les portes sont vertes sur deux passages consécutifs ;
- chaque test Vue a un successeur documenté ;
- les parcours `e2e/` passent sans modification sur le build React ;
- aucun écart de type A ne reste ouvert ;
- chaque écart B et C a été présenté à Philippe ;
- la procédure de bascule et de retour arrière a été répétée dans le clone jetable ;
- Philippe a validé par écrit le passage en production.

---

## 14. Ta première action

Exécute **uniquement le Lot 0**. N'écris aucun composant React, n'installe rien dans Structura et
ne crée aucun commit. Termine par le rapport de la section 12, puis attends le feu vert de Philippe.
