# Accueil — 4 catégories + drill-down (design 2026-07-19)

**Statut : IMPLÉMENTÉ le 2026-07-19, testé de bout en bout via Playwright (navigateur
headless piloté sur l'instance déjà en ligne de Philippe, port 8000), 0 erreur console,
captures d'écran vérifiées visuellement.**

## Notes d'implémentation

- 2 fichiers modifiés seulement : `frontend/src/views/HomeView.vue` (réécrit),
  `frontend/src/style.css` (classes `.category-switch-*` ajoutées). Rien d'autre touché
  (routes, `stores/auth.js` inchangés).
- **Bug trouvé et corrigé pendant le test** : `el.focus()` appelé de façon synchrone
  dans le hook `@after-enter` de `<Transition>` ne "prenait" pas (l'élément recevait
  bien le focus un instant mais `document.activeElement` retombait sur `<body>`) — Échap
  ne fonctionnait pas après un drill-down. Corrigé en différant l'appel d'une frame
  (`requestAnimationFrame(() => el.focus())`) dans le hook. Piège classique des hooks
  liés à `transitionend`.
- **Point de test important** : avec `mode="out-in"`, la sortie et l'entrée s'enchaînent
  **séquentiellement** (sortie ~220ms PUIS entrée ~220ms, soit ~440ms au total) — un
  premier test avec un délai d'attente de 400ms montrait un faux négatif sur Échap
  (capturé en plein milieu de la transition). Gardez ce timing en tête pour tout test
  manuel ou automatisé futur sur ce composant.
- Validé : 4 cartes niveau 1 correctes, drill-down Studies (3 sous-cards dont le widget
  async "Charger une étude"), Life Cycle (1 sous-card Booking), bouton retour, Échap,
  icône admin absente pour un compte non-admin (`ADMIN_ICON_COUNT_NONADMIN=0`), 0 erreur
  console sur l'ensemble du parcours.
- Pas testé : le rendu avec un compte admin (icône ⚙️ visible) — la condition
  `v-if="auth.isAdmin"` et le `RouterLink` sont repris à l'identique de l'ancien code
  (juste déplacés du corps de la grille vers le header), donc risque très faible, mais
  Philippe peut vouloir un coup d'œil avec son propre compte admin.

## Retouche visuelle (2026-07-19, essai sur 2 vues avant généralisation)

À la demande de Philippe ("l'application est assez terne"), premier essai d'un langage
visuel plus profond, appliqué **seulement sur HomeView et la card de deal de
BookingView** (pas touché à la classe `.card` globale — les autres vues restent
inchangées tant que la direction n'est pas validée) :
- Profondeur : `shadow-lg`/`hover:shadow-xl` + léger dégradé `bg-gradient-to-b
  from-slate-900 to-slate-950/40` sur les cards (remplace le fond plat).
- Micro-interaction : `hover:-translate-y-0.5` (léger soulèvement au survol),
  `transition-all duration-200` (remplace `transition-colors` pour animer aussi
  l'ombre et le transform ensemble).
- Identité de catégorie : les 4 grandes cards de l'accueil ont désormais un accent de
  couleur en haut (`border-t-2 border-t-{couleur}-600`), pas les sous-cards (réservé au
  niveau 1, qui porte l'identité).
- Titres avec dégradé de texte subtil (`bg-gradient-to-r from-slate-100 to-slate-400
  bg-clip-text text-transparent`) sur "Bonjour" et le titre de catégorie.
- Le chiffre MtM dans Booking (jusque-là texte blanc plat malgré son importance) a le
  même traitement en dégradé bleu.
- **Validé par Philippe** ("oui c'est très bien") → généralisé : la profondeur de base
  (dégradé + ombre) fait maintenant partie de la classe `.card` globale dans
  `style.css` — toute l'app en profite automatiquement (le lift/hover reste opt-in par
  usage, cohérent avec la convention du projet). Les classes redondantes dans
  HomeView/BookingView ont été nettoyées après coup.

## Idées piquées de weeknd_claude (2026-07-19, appliquées sur Home + Booking)

Philippe a demandé d'explorer `C:\Users\admin\GitHub\weeknd_claude` (autre projet, thème
clair, CSS custom) pour des idées transposables. 3 adoptées, formalisées dans
`style.css` :
- **`.text-brand-gradient`** (`from-indigo-400 to-purple-500 bg-clip-text
  text-transparent`) — réservé aux chiffres qu'on veut mettre en évidence (distinct des
  couleurs fonctionnelles de navigation). Appliqué au chiffre MtM dans BookingView.
- **`.kpi-tile`** (halo diagonal `::before` en dégradé indigo à 10% d'opacité) — à
  combiner avec `.card`. Appliqué à la card de stats agrégées de BookingView.
- **`.pulse-ring`** (anneau `box-shadow` qui respire, `@keyframes`, `prefers-reduced-
  motion` géré) — signale un élément "vivant"/en attente d'attention. Appliqué au badge
  alertes non lues (HomeView, cartes Life Cycle + Booking) et à un point avant le titre
  de la card "Alertes non lues" dans BookingView.

**Écartés délibérément** : le drawer latéral (trop gros changement d'archi pour le
gain) et le "fan carousel" (très réussi visuellement mais pas le ton d'un outil de desk
pro utilisé intensivement) — le fan carousel est noté comme idée future si un vrai
besoin de "choisir entre 3-4 options équivalentes" se présente un jour dans le Pricer.

Validé en réel (Playwright, captures d'écran) : dégradés/profondeur/accents visibles,
0 erreur console. Le pulse-ring n'a pas pu être confirmé visuellement (aucune alerte en
attente sur le compte de test au moment du test) mais suit le même chemin de code que
le badge rouge déjà validé.

## Généralisation du hover-lift aux cards cliquables restantes (2026-07-19, suite)

Cartographié les 32 fichiers utilisant `.card` : l'immense majorité (AmcView à elle
seule ~40 usages, tous les panneaux Admin/RFQ/Pricer) sont des **panneaux statiques**
(formulaires, tableaux, tuiles de stats) — leur laisser le hover-lift serait trompeur
(fausse promesse de clic). Seules les cards **réellement cliquables** identifiées
(`cursor-pointer`/`RouterLink`/`@click` sur la card elle-même) ont reçu le traitement
`hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all
duration-200` (déjà en place sur Home/Booking) :
- `ScriptsView.vue` : cards de script dans la grille.
- `AdminView.vue` : les 5 RouterLink de sous-sections.
- `DocumentationView.vue` : 4 des 5 cards (Bibliothèque doc, Term Sheet Indicatif, KID
  PRIIPs, Term Sheet Final) — **pas** la 5e ("Confirmation de trade", `opacity-50
  cursor-not-allowed`, désactivée intentionnellement, exclue à raison).
- `RfqView.vue` : liste de RFQ dans la sidebar — traitement allégé (ombre seule, sans
  translate-y) car liste compacte à items serrés, un lift vertical aurait chevauché la
  card voisine ; état sélectionné distingué par une ombre bleutée persistante.

Validé en réel (Playwright) sur Scripts/Documentation/RFQ : 0 erreur console, rendu
correct. Pas pu valider visuellement les cards Admin (compte de test non-admin) ni les
cards Scripts/Documentation à l'état peuplé (comptes de test vides sur ces modules) —
risque jugé très faible (classes Tailwind additives, motif déjà éprouvé ailleurs).

## Contexte

L'accueil actuel (`HomeView.vue`) est une grille plate de 9-10 tuiles (Mes Scripts,
Nouveau Script, Documentation, Étude Fama-French, Charger une étude, Carnet d'ordres,
RFQ Fournisseurs, Analyse Contreparties, Booking, + Administration pour les admins).
Ça a bien tenu jusqu'ici mais commence à ressembler à un menu plat sans hiérarchie —
chaque nouvelle fonctionnalité (le chantier Booking de ce jour en est un exemple) ajoute
une tuile de plus. Objectif : un accueil plus moderne, différenciant, organisé par grande
famille de workflow plutôt qu'à plat.

## Les 4 catégories (mapping validé sur les tuiles existantes)

Correction du 2026-07-19 (2e passe) : le Carnet d'ordres (FIFO) est une reconstruction/
analyse a posteriori (P&L réalisé, réconciliation) — il va avec Studies, pas avec Life
Cycle qui suit un produit vivant au jour le jour.

| Catégorie | Tuiles regroupées | Routes |
|---|---|---|
| **Pricing** | Mes Scripts, Nouveau Script, Documentation | `/scripts`, `/pricer`, `/documentation` |
| **Life Cycle** | Booking (seul) | `/booking` |
| **Studies** | Étude Fama-French, Charger une étude (widget études récentes), Carnet d'ordres (FIFO) | `/amc`, `/fifo` |
| **Competitive Bidding** | RFQ Fournisseurs, Analyse Contreparties | `/rfq`, `/rfq/analyse` |

**Retour sur Life Cycle (2026-07-19, 3e passe)** : d'abord tranché en navigation directe
(une seule tuile ne justifiait pas un drill-down), puis reconsidéré — un futur module de
**génération d'idées de produits / proposition d'alternatives au client** (voir
[[deal-lifecycle-valorisation]], section "module de proposition de produits", idée
gardée en tête depuis la session MtM) viendra s'ajouter comme 2e sous-card de Life
Cycle. Décision finale : **les 4 catégories gardent le même mécanisme de drill-down
animé**, y compris Life Cycle avec une seule sous-card (Booking) pour l'instant — pas
de cas particulier à retirer puis remettre au moment d'ajouter la 2e carte. Le
placeholder de la future carte "Génération d'idées de produits" n'est PAS ajouté
maintenant (pas encore cadré/codé), seul le mécanisme reste prêt à l'accueillir.

**Administration** ne rentre dans aucune catégorie → sort de la grille, devient une
icône ⚙️ dans le header (à côté du nom d'utilisateur / déconnexion), visible admins
seulement (`v-if="auth.isAdmin"`, comportement inchangé, juste déplacé).

## Interaction : expand-in-place, pas de nouvelle route

Un seul état local (`selectedCategory = ref(null)`), pas de changement de route :

- **Niveau 1 (défaut)** : 4 grandes cartes de catégorie (grille 2×2, empilée en 1
  colonne sur mobile comme aujourd'hui), chacune avec icône, titre, une ligne de
  description. En-tête reste « Bonjour, {user} / Que voulez-vous faire ? ».
- **Clic sur une carte** → `<Transition>` Vue (crossfade + léger scale, ~200-250ms,
  respecter `prefers-reduced-motion`) vers les sous-cards de la catégorie. L'en-tête
  bascule sur un **vrai bouton retour** (`.btn-secondary`, pas juste le logo ni un lien
  texte discret — voir [[feedback-ui-navigation]], la même règle s'applique ici) +
  le titre de la catégorie.
- Les sous-cards affichées sont **exactement celles d'aujourd'hui**, inchangées
  (markup, couleurs, textes, y compris le widget « Charger une étude » avec son fetch
  des études récentes) — seulement re-parentées sous la vue de leur catégorie.
- Retour : clic sur le bouton retour, ou touche Échap.

**Pourquoi pas une vraie route par catégorie (`/home/pricing`)** : plus léger, plus
rapide à livrer, garde l'accueil comme un seul écran sans rechargement de page. Le
compromis assumé : pas d'URL partageable/bookmarkable par catégorie. Si le besoin se
présente plus tard, une route par catégorie serait facile à ajouter sans changer la
logique visuelle (le `<Transition>` resterait le même, juste piloté par la route au lieu
d'un ref local).

## Identité visuelle des 4 catégories

Une couleur d'accent distincte par catégorie, cohérente avec les couleurs déjà en place
sur les sous-cards qu'elle regroupe (pas de rupture visuelle en drill-down) :
- **Pricing** : bleu (Mes Scripts est déjà bleu, Nouveau Script vert, Documentation
  violet — bleu comme couleur dominante de la famille)
- **Life Cycle** : ambre/jaune (Booking est déjà jaune, cohérent avec l'urgence des
  alertes)
- **Studies** : ambre (Fama-French est déjà ambre ; Charger une étude et FIFO
  s'alignent dessus comme accent dominant de la famille)
- **Competitive Bidding** : rose (RFQ et Analyse Contreparties sont déjà dans la
  famille rose/rose foncé)

## Indicateurs visibles au niveau 1 (sans cliquer)

**Seule la carte Life Cycle** porte un badge — le compteur d'alertes non lues
(`unreadAlerts`, même fetch qu'aujourd'hui sur la tuile Booking, 🔔 N). Studies et les
2 autres catégories n'ont pas d'indicateur en v1 (peut être ajouté plus tard sans
changer la structure — ex. nombre d'études récentes sur Studies).

## Explicitement hors périmètre de cette itération

- Pas de refonte visuelle des sous-cards existantes (elles marchent bien, effort porté
  entièrement sur le nouveau niveau 1 et la transition).
- Pas de badge sur Studies/Pricing/Competitive Bidding.
- Administration reste une icône header, pas une 5e carte.

## Vérification (une fois codé)

- Chaque sous-card, après drill-down, doit pointer vers la même route qu'aujourd'hui
  (aucune régression de navigation) — comparer 1:1 avec `HomeView.vue` actuel.
- Badge alertes Life Cycle == badge Booking actuel (même valeur, même source).
- Icône admin visible seulement pour un compte admin, route `/admin` inchangée.
- `npm run build` après implémentation (convention du projet, voir
  [[feedback-vite-build]]) + test manuel dans le navigateur : drill-down/retour sur les
  4 catégories, clavier Échap, responsive mobile (empilement 1 colonne).
