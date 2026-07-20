# Reprise du travail — 2026-07-19 (chantier Booking & cycle de vie)

État au soir du 2026-07-18. Session très dense — tout ce qui suit est **fait, testé et buildé**,
sauf la section "À corriger en priorité" et le backlog.

---

## 🔴 À corriger en priorité demain

### Bug 1 — 422 au pricing d'un deal rouvert depuis Booking (vu en fin de session, capture fournie)

**Symptôme** : ouvrir un deal depuis Booking ("→ Ouvrir", ex. DEMO-20260718-019), puis cliquer
"▶ Pricer" → bandeau d'erreur rouge :
`{"type": "float_type", "loc": ["body", "underlyings", 0, "sigma_fx"], "msg": "Input should be a valid number", "input": null}` (idem `rho_sfx`, et sans doute tous les champs modèle).

**Cause identifiée (non corrigée)** : les 22 deals de la campagne API ont un
`market_snapshot.underlyings` partiel — seulement `{name, ticker, ccy, sigma, q}`.
`loadFromDeal()` (pricing.js) remplace `store.underlyings` par ces objets partiels tels quels ;
`_buildUls()` calcule ensuite `u.sigma_fx / 100` → `undefined/100 = NaN` → sérialisé `null` en
JSON → 422 Pydantic.

**Fix proposé** : dans `loadFromDeal`, fusionner chaque underlying du snapshot par-dessus un
objet complet par défaut (même shape que `_defaultUnderlying()` / `addUnderlying()`) :
`{ ...defaults, ...u }`. Ainsi un snapshot partiel (ancien deal, deal bookés par API) redevient
priçable avec des défauts neutres pour les champs absents. Les deals bookés depuis l'UI ne sont
pas concernés (snapshot complet depuis le fix du même jour).

### Bug 2 — reloader uvicorn gelé sous Windows (récurrent, confirmé 2×)

`run.py` lance uvicorn avec `reload=True`. Sous Windows, WatchFiles détecte le changement
(log : "Reloading...") mais le worker ne redémarre jamais → le serveur sert indéfiniment du
code périmé, sans erreur visible. Ça a fait perdre du temps deux fois aujourd'hui (le fix
strike-weekend semblait "ne pas marcher", pareil pour `terms`).

- **Palliatif actuel** : redémarrer le serveur après chaque modif backend.
- ⚠️ **Le serveur tourne actuellement dans un process lancé depuis la session Claude d'hier —
  il sera mort demain matin.** Relancer : `cd backend && ..\.venv\Scripts\python.exe run.py`.
- Il y avait aussi une **instance dupliquée zombie** (python spyder-6) qui détenait le port —
  tuée. Vérifier qu'une seule instance tourne : `netstat -ano | findstr :8000`.
- **Fix candidat** : `reload=False` dans run.py (redémarrage manuel assumé), ou tester
  `reload_dirs=["app"]` / forcer le reloader statreload.

---

## ✅ Fait aujourd'hui (2026-07-18)

### Réorganisation UI Pricer
- Ordre des onglets : Script → Deal → Marché & Paramètres → Events.
- Deal = point d'entrée produit : identité (devise éditable ici, miroir lecture seule dans
  Marché & Params), économique, dates (+ **payment_date**, nouveau champ DB), sous-jacents
  (picker ticker/CCY, la calibration σ/q/smile reste dans Marché & Params, index actif partagé
  via `store.activeUnderlyingIdx`), calendrier CONSTAT (déplacé depuis Script), aperçu
  constatations, booking.
- Maturité dérivée : mode expert = date de fin la plus tardive des calendriers CONSTAT ; sinon
  value_date + T. Jamais éditable.
- Contrepartie du booking = **select** depuis le catalogue admin (voir plus bas).

### Cycle de vie automatique (le gros morceau)
- `events/refresh` rejoue le script figé sur l'historique Yahoo (`eval_script_on_history`) :
  détecte **callé** (event déclencheur marqué, suivants "annulé", `deal.status`,
  `realized_payout`, `resolution_outcome` persistés) et **échu** (event final "final" ou "ki"
  via heuristique payout < 99.5%).
- Reprice d'un deal résolu → court-circuit : prix résiduel 0% + remboursement réalisé (plus de
  MC "comme si le produit démarrait aujourd'hui").
- **Fix strike week-end/férié** : fenêtre historique élargie à J-7 avant strike (sinon S₀
  jamais rempli — trouvé par la campagne, strikes samedi 20/09/2025 et Labor Day 02/09/2024).

### PayScript : PARAM() + convention M_ (docs/PAYSCRIPT_PARAM_PAR_OBSERVATION.md mis à jour)
- `PARAM() NOM [= seed%]` : valeurs par observation saisies dans l'UI (tableau une ligne par
  obs, dernière ligne s'étend, 1 ligne ≡ scalaire — vérifié au tick près). Résolution unique
  `_pobs` (parser.py) par INDEX.
- Préfixe `M_` = surveillé par la watchlist ; direction (up/down) et observable (WOF, BOF,
  S[i], WOF_MIN, BOF_MAX…) déduits de l'usage réel (`_analyze_monitors`). Ambigu → neutre.
- Tous les templates migrés (M_AC_BAR, M_KI_BAR, M_KO_BAR, M_CPN_BAR, M_PUT_STRIKE).
- `user_params` **figés au booking** dans `market_snapshot.user_params` (unités stockées) —
  relus par le replay cycle de vie, la watchlist, et `loadFromDeal` (restaurés en unités
  d'affichage dans les overrides — fix du jour).
- Tests : 130/130, dont 9 nouveaux (§ PARAM() & convention M_ dans test_parser.py).

### Page Booking (/booking, tuile Accueil activée)
- Filtres (contrepartie, sous-jacent, type de produit, statut) + stats sur la sélection :
  hit ratio callé/final/ki des deals résolus, nominal total, remboursement moyen.
- **Watchlist** triée par urgence : prochaine obs (J−x), WOF actuel + min historique, écarts
  aux barrières M_ (bon observable, bon sens, niveau de la **prochaine obs** pour un PARAM()
  dégressif), fallback heuristique pour scripts sans M_.
- **Fiche détail dépliable par deal** (accordéon multi-ouvert) : barre de vie avec pastilles
  de constatations colorées + trait "aujourd'hui", dates complètes, **termes économiques**
  (PARAM figés, endpoint `GET /api/deals/{id}` → clé `terms`, tableaux affichés
  "105% / 100% / 95%"), sous-jacents S₀/spot/perf, barrières, tableau constatations lecture
  seule. "→ Ouvrir" réservé au vrai repricing.

### Contreparties éligibles (admin)
- Modèle `Counterparty` + seed 16 grandes banques. CRUD complet :
  Administration → Contreparties deals. Endpoint non-admin `GET /api/deals/counterparties`
  (actives seulement) pour le select du booking.

### Base de test (user `test` / `test123`)
- **26 deals** : 8 callés, 7 échus (4 final dont shark 125.9% et capital garanti 139.1%,
  3 KI réels : BABA 62.3%, PFE 50.4%, worst-of NKE+SPX 48.2%), 11 actifs (dégressifs,
  worst-of 3 actifs, twin win sur WOF_MIN, shark sur BOF_MAX, legacy sans M_, sens achat…).
- 20 contreparties distinctes, types Autocall/Options/Produits à capital/Sharks.
- Script de génération : scratchpad `book_campaign.py` (non idempotent, ne pas relancer tel quel).

---

## 📋 Backlog (ordre suggéré)

1. **Bug 1 ci-dessus** (fusion défauts dans loadFromDeal) — petit, bloquant pour "→ Ouvrir".
2. **Refresh périodique** : `events/refresh` est purement passif (aucun scheduler dans main.py).
   Priorité 2 actée de longue date. Y rattacher les **alertes** (franchissement barrière,
   rappel détecté rétroactivement).
3. **MtM résiduel** d'un deal actif : le reprice actuel relance `AT 1,2,3` "depuis
   aujourd'hui" — il faudrait renormaliser le script sur les échéances restantes réelles.
   Chantier de fond identifié, jamais commencé.
4. Petits fils qui traînent : option "annulé" absente du dropdown statut d'event
   (EventsTab.vue) ; mode expert gear-put compare via `SET PERF` → monitors M_ non détectés
   (puce neutre) ; heuristique ki mal étiquette un produit 100% optionnel échu (payout < 99.5%
   structurel) ; cache watchlist si le book grossit (1 fetch Yahoo/deal actif/consultation) ;
   afficher le script figé dans la fiche détail (bloc repliable).
