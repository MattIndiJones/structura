# Note de valorisation client (PDF) — design (2026-07-19)

**Statut : IMPLÉMENTÉ le 2026-07-19 (v1), 154/154 tests, build vite OK.** Notes
d'implémentation en bas de page. Arbitrages tranchés :
annexe technique complète (transparence, la dernière page peut ne pas être envoyée),
v1 = explication simple sans waterfall, palette blanche imprimable, français seulement.

## Objectif

Après un MtM résiduel dans la page Booking, générer une note PDF d'1–2 pages A4 à envoyer
au client qui demande « pourquoi mon produit vaut X ? » : le chiffre daté, la situation du
produit dans sa vie, et une explication en français lisible en 2 minutes. Profondeur
technique reléguée en annexe.

## Mécanique

- Bouton **« 📄 Note de valo »** dans BookingView, à côté du résultat MtM (visible seulement
  quand `mtmResults[d.id]` est un succès).
- Endpoint `POST /api/deals/{deal_id}/mtm/report` : rejoue `deal_mtm` avec le **même body**
  (mode booking / marché actuel du select repris tel quel) et le **même seed 42** → le PDF
  affiche exactement le chiffre vu à l'écran. Renvoie `application/pdf`.
- Infrastructure : réutiliser ReportLab + matplotlib (déjà en place dans `amc_pdf.py`, avec
  `_LOGO_PATH`). Nouveau module `backend/app/core/deal_valuation_pdf.py`. **Palette claire
  print-friendly** (ne PAS reprendre la charte sombre AMC).

## Contenu (ordre des sections)

1. **En-tête** — logo, « Note de valorisation indicative », date de valo. Identification :
   référence, type de produit, sous-jacent(s), nominal + devise, sens, contrepartie,
   dates strike/valeur/maturité. Tout vient de `Deal` + `market_snapshot`.
2. **Le chiffre** — MtM en % ET en cash (nominal × MtM), vs prix traité avec P&L latent
   en points et en cash. Réponse `/mtm` telle quelle.
3. **Vie du produit** — barre de vie print (reprendre le concept de la fiche Booking) :
   constats passés avec issue, « aujourd'hui », constats restants ; tableau des flux déjà
   payés (`realized_cash_flows`, dates + montants).
4. **Explication de valo (le cœur)** — phrases générées à base de règles depuis la réponse
   `/mtm` (aucun LLM) :
   - spots vs strike et vs barrières (contrat M_ / `monitors` pour les niveaux, y compris
     PARAM() dégressif à la bonne ligne — réutiliser la logique de `build_watchlist_row`) ;
   - état du KI : barrière touchée ou non, plus bas atteint (`wof_min_realized`, expliquer
     que c'est le plus bas des closes quotidiens depuis le strike) ;
   - drivers : `prob_gt100` (probabilité de rembourser > pair), `fugit` (vie attendue),
     prochaine observation (date + niveau à atteindre) ;
   - phrase de conclusion type « Le produit se valorise au-dessus/en-dessous du pair car… ».
5. **Graphique** — trajectoires des sous-jacents depuis le strike (closes déjà fetchés pour
   le replay, normalisées % du strike), barrières KI/AC en pointillés (niveaux du contrat
   M_), pastilles aux dates de constat, trait vertical « aujourd'hui ». Matplotlib Agg.
6. **Annexe technique** (page séparée, peut ne pas être envoyée) — méthode (Monte Carlo,
   `n_paths`, antithétique, monitoring de barrière), `market_used` complet (source, modèle,
   σ/q par sous-jacent, corr, r, fenêtre), IC95, état hérité (obs passées, WOF min réalisé,
   S_MIN per-asset). Disclaimer : valorisation indicative, ne constitue pas un prix ferme ni
   une offre, données de marché Yahoo Finance, date/heure de génération.

## v1.2 — retours de Philippe (2026-07-19, 2e itération) — CODÉE (167/167)

- **Mise en page** : la tuile MtM débordait (24pt dans une table imbriquée) →
  `_stat_tiles` (table plate 2 lignes × n colonnes, 17pt), logo à ratio intrinsèque
  (`ImageReader`), pied de page « Structura — document indicatif » + n° de page sur
  toutes les pages (`_footer` via onFirstPage/onLaterPages), zébrage des tableaux.
- **Sensibilités** en annexe des DEUX notes : `_residual_greeks` (deals.py) —
  bump-and-reprice CRN sur le setup résiduel complet (état hérité), unités desk :
  Δ = pts de MtM pour +1% de spot, Γ = convexité (2e différence), véga = pts pour
  +1 pt de vol (None si modèle non-GBM — bump σ serait un no-op trompeur).
- **Note PDF d'explication de valo** : `generate_explain_pdf` + endpoint
  `POST /mtm/explain/report` (même body/seed que l'écran) + bouton « 📄 Note
  d'explication » dans le bloc explain. Contenu : tuiles MtM d1/d2/variation/P&L,
  **graphique waterfall** (barres flottantes vert/rouge, connecteurs pointillés),
  tableau des effets, phrases, annexe (méthodo CRN, marché d1 vs d2, sensibilités).
  Validé en réel sur 026 : Δ +0.11, Γ −0.012, véga −0.13 (autocall proche du rappel).

## v1.1 — retours de Philippe (2026-07-19 soir) — CODÉE (162/162)

Implémentation : `pv_max`/`pv_p95` exposés par run_mc, bloc `best_case` dans le payload
/mtm (deals.py, seuil `_EXIT_CAPTURE = 0.97`), tuile renommée « MtM — valeur
indicative », phrases + encadré ambre « Opportunité de sortie anticipée » dans le PDF,
badge « ⚡ sortie envisageable » + meilleur scénario dans la card Booking.
Nuance découverte en réel (026) : un autocall à coupons croissants n'a PAS le haut de
distribution plat (rappels 8/16/24% étalés) → capped=False → pas de claim de cap ni de
signal, juste « scénario favorable (q95) + meilleur scénario simulé ». Le signal ne se
déclenche que quand le rappel prochain est quasi certain — comportement voulu.

## v1.1 — cadrage d'origine

1. **Renommer la tuile** « Valeur indicative » → « MtM — valeur indicative » (le mot MtM
   doit apparaître, un client le cherche) + « mark-to-market » dans la phrase de conclusion.
2. **Potentiel résiduel & signal de sortie** :
   - meilleur scénario actualisé = max de la distribution des payoffs actualisés du MC
     (payoff-agnostique ; pour un autocall = rappel à la prochaine obs + coupon) ;
   - `upside résiduel = meilleur scénario − MtM`, en points ET annualisé ;
   - si MtM ≥ ~97-98% du meilleur scénario (seuil à régler) → encadré « Opportunité de
     sortie anticipée » (formulation prudente, le disclaimer couvre) ;
   - produits NON plafonnés (max = queue de distribution sans sens commercial) : afficher
     le quantile 95% « scénario favorable », PAS de signal de sortie. Détection sur la
     forme de la distribution (plafonnée vs non).
   - run_mc expose déjà payoffs/pv ; il faudra faire remonter max_pv (et p95) dans le
     payload /mtm.

## v2 (plus tard, non codé)

- **Waterfall d'attribution** : prix booké → effet temps → effet spot → effet vol → effet
  taux → MtM du jour (~4 runs MC supplémentaires avec CRN : swap d'un paramètre à la fois
  entre snapshot booking et marché actuel). Très vendeur, à brancher sur le même endpoint
  avec un flag.
- Version EN, envoi email direct.

## Tests

- Génération sur un deal actif de la base `test` (les 11) : PDF non vide, MtM du PDF ==
  MtM de l'endpoint au tick près (même seed), sections présentes.
- Deal mono vs multi sous-jacents (graphique et corr), deal avec PARAM() dégressif
  (bonne barrière affichée), deal legacy sans monitors M_ (phrases dégradées proprement,
  fallback heuristique).
- Deal résolu / échu → 422 (pas de note de valo sur un produit mort, le relevé de
  résolution est un autre document).

## Notes d'implémentation (2026-07-19)

- `deal_mtm` refactoré : cœur extrait dans `_mtm_core(deal, session, n_paths, body)`
  → `(payload, ctx)` ; le ctx (historique, état, compiled, norm_spots) alimente le PDF
  sans second fetch Yahoo. `deal_mtm` et `deal_mtm_report` sont des endpoints minces.
- `_monitor_levels(compiled, user_params, next_row)` (deals.py) : niveaux des barrières
  M_ à la ligne de la prochaine obs (PARAM() dégressif), **fallback heuristique
  `_classify_param_barrier`** pour les scripts legacy sans M_ (validé en réel sur
  DEMO-20260718-026 : phrases rappel 100% + protection 60% correctes).
- `core/deal_valuation_pdf.py` : `generate_valuation_pdf(data)` pure (testable offline,
  `tests/test_valuation_pdf.py`), `build_explanation(data)` = phrases à base de règles.
  Pièges ReportLab rencontrés : échapper `&` dans les Paragraph (`P&amp;L`), ne pas
  faire de `.replace(",", " ")` sur une phrase entière pour formater un nombre.
- PDF ≈ 1.4 Mo (graphique 180 dpi) — OK pour email.
- Frontend : bouton « 📄 Note de valo » dans le bloc résultat MtM (BookingView),
  reprend le mode booking/marché actuel du select, download blob.
