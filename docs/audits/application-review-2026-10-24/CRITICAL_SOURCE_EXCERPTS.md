# Extraits critiques de source

Copies exactes de plages de source locale, avec numéros de ligne d'origine et SHA-256 du fichier complet.
Ces extraits sont incomplets par construction ; les imports, validateurs et appelants peuvent changer l'interprétation. Demander le fichier complet lorsqu'une conclusion en dépend.
Aucune donnée de base privée, clé ou fichier de credentials n'est inclus.

## Product canonique

`backend/app/core/product/models.py:185` à 195 ; SHA-256 `90f27778eb5be82c88935599fb6d6c2ad3d1da7bdf2552857a599a82639ac882`.

```text
185:     execution: FrozenObject | None = None
186:     lifecycle: FrozenObject | None = None
187:     documents: tuple[FrozenObject, ...] = ()
188:     calculations: tuple[CalculationRef, ...] = ()
189: 
190:     @property
191:     def terms_fingerprint(self) -> str:
192:         return self.terms.fingerprint
193: 
194:     def to_dict(self) -> dict:
195:         return self.model_dump(mode="json")
```

## Contrat du pricing

`backend/app/core/schemas.py:202` à 280 ; SHA-256 `6aa7ebf1afe42c558e0dbf2692bb32692494cd5ac63f50a9483cdf343ba8a404`.

```text
202: class PricingRequest(BaseModel):
203:     model_config = ConfigDict(allow_inf_nan=False)
204: 
205:     script: str = Field(max_length=MAX_SCRIPT_CHARS)
206:     underlyings: List[UnderlyingParams] = Field(min_length=1, max_length=MAX_UNDERLYINGS)
207:     corr_matrix: List[List[float]]
208:     r: float = Field(default=0.03, ge=MIN_RATE, le=MAX_RATE)
209:     T: float = Field(default=3.0, gt=0.0, le=MAX_MATURITY_YEARS)
210:     N: int = Field(default=20000, ge=1000, le=200000)
211:     seed: int = 42
212:     model: str = Field(default="constant", pattern=f"^({'|'.join(MODELS)})$")
213:     antithetic: bool = True
214:     user_params: Dict[str, Any] = {}
215:     compute_greeks: bool = False
216:     selected_greeks: List[str] = ["delta", "gamma", "vega", "theta", "rho"]
217:     yield_curve: List[List[float]] = []
218:     # Spread emetteur : il n'entre QUE dans l'actualisation, jamais dans le
219:     # drift. La courbe par piliers l'emporte sur le niveau plat quand elle est
220:     # fournie. Voir engine._funding_df_arr.
221:     funding_curve: List[List[float]] = []
222:     funding_spread: float = Field(default=0.0, ge=-0.05, le=0.50)
223:     sigma_r: float = Field(default=0.0, ge=0.0, le=0.10)
224:     a_r: float = Field(default=0.0, ge=0.0, le=2.0)
225:     # Barrier monitoring: "weekly" (extrema at the weekly grid steps, historic
226:     # behaviour) or "continuous" (Brownian-bridge within-step extrema — WOF_MIN/
227:     # S_MIN/BOF_MAX then reflect the continuous path, raising KI probability).
228:     barrier_monitoring: str = Field(default="weekly", pattern="^(weekly|continuous)$")
229:     # CONSTAT values, keyed by name — see core/payscript/parser.resolve_constats.
230:     # Empty dict is a no-op (the common/simple-mode case: no AT<ConstatName>:).
231:     constats: Dict[str, Any] = {}
232:     # Calendrier contractuel déjà résolu d'un Product conservé. Le script reste
233:     # parsé et validé ; seul le recalcul implicite des dates est évité.
234:     frozen_schedule: Optional[Dict[str, Any]] = None
235: 
236:     @field_validator("seed", mode="before")
237:     @classmethod
238:     def fixed_monte_carlo_seed(cls, _value) -> int:
239:         """Desk convention: every pricing run uses the global seed 42."""
240:         return 42
241:     # Date the calendar's year-fractions are measured from — the product's own
242:     # t=0, i.e. its value date. None keeps the historic default (today), which
243:     # is only right for a same-day settlement. Callers that know the value date
244:     # must send it: api/deals.py already anchors a booked deal's replay on
245:     # deal.value_date, so a pre-trade price left on today's anchor resolves the
246:     # same calendar into different year fractions than the very same deal once
247:     # booked — the two prices then differ for no economic reason.
248:     anchor: Optional[date] = None
249:     # Settlement currency: names the business-day calendar the CONSTAT dates are
250:     # rolled onto and the settlement lags counted in. None leaves every date raw
251:     # and every flow paid at its observation.
252:     settlement_ccy: Optional[str] = None
253:     # The product's own payment date — when the final redemption's cash moves.
254:     # From the term sheet, never derived from a fixing. None pays at maturity.
255:     payment_date: Optional[date] = None
256:     # Contractual maturity label retained by Product. The engine horizon stays
257:     # `T`; when both are supplied their consistency is an API responsibility.
258:     maturity_date: Optional[date] = None
259:     # Where the initial level is fixed, and therefore where the diffusion
260:     # starts. When given it becomes the time axis' origin, in place of `anchor`.
261:     strike_date: Optional[date] = None
262:     # When the cash is exchanged between counterparties. The quoted price is the
263:     # amount that moves on that date, so it is the date the PV is expressed at.
264:     value_date: Optional[date] = None
265: 
266:     @field_validator("yield_curve")
267:     @classmethod
268:     def validate_yield_curve(cls, curve: List[List[float]]) -> List[List[float]]:
269:         return validate_term_curve(curve, "courbe de taux")
270: 
271:     @field_validator("funding_curve")
272:     @classmethod
273:     def validate_funding_curve(cls, curve: List[List[float]]) -> List[List[float]]:
274:         return validate_term_curve(curve, "courbe de funding")
275: 
276:     @model_validator(mode="after")
277:     def validate_correlation(self):
278:         self.corr_matrix = validate_correlation_matrix(self.corr_matrix, len(self.underlyings))
279:         return self
280: 
```

## Axe de temps

`backend/app/core/payscript/engine.py:60` à 102 ; SHA-256 `37e62be348a68ad494888ae7cdeb801376d21adeccd94bb585cce10660b2edf1`.

```text
60: def _simulation_axis(horizon: float) -> tuple[int, float]:
61:     """Keep weekly diffusion density without extending the requested horizon."""
62:     if not math.isfinite(horizon) or horizon <= 0:
63:         raise ValueError("L'horizon de simulation doit être fini et strictement positif.")
64:     steps = max(1, round(horizon * SY))
65:     return steps, horizon / steps
66: 
67: 
68: def _event_schedule(events, steps, dt, *, horizon=None, maturity_payment_t=None):
69:     """Order occurrences by contract time, then source order for simultaneity.
70: 
71:     One occurrence per copy keeps ranks, windows and payments aligned even
72:     when several dates of the same block map to one diffusion step. The
73:     compiled/frozen contract is never mutated. Dated blocks precede MATURITY.
74:     """
75:     occurrences, maturity = [], []
76:     fields = ("payment_dates", "window_dates", "ranks", "releves_passes")
77:     for source_order, event in enumerate(events):
78:         if event.type == "AT_MATURITY":
79:             maturity.append(event)
80:             continue
81:         for i, when in enumerate(event.dates):
82:             step = max(1, round(when / dt))
83:             # Resolved/residual calendars store year-fractions to six decimals.
84:             # Admit that representation tolerance, never an extra market day.
85:             if step > steps or (horizon is not None and when > horizon + 1e-6):
86:                 continue
87:             if horizon is not None:
88:                 when = min(when, horizon)
89:             attributes = {field: [value[i]] if value is not None and i < len(value) else None
90:                           for field in fields if (value := getattr(event, field)) is not None}
91:             occurrence = replace(event, dates=[when], **attributes)
92:             payment = occurrence.payment_dates[0] if occurrence.payment_dates else when
93:             if maturity_payment_t is not None and abs(when - horizon) <= 1e-6:
94:                 payment = maturity_payment_t
95:             occurrences.append((when, source_order, i, step, occurrence, payment))
96:     schedule, payments = _ContractEventSchedule(), {}
97:     for when, source_order, i, step, occurrence, payment in sorted(occurrences, key=lambda row: row[:3]):
98:         schedule.setdefault(step, []).append(occurrence)
99:         payments.setdefault(step, []).append(payment)
100:     return schedule, maturity, payments
101: 
102: 
```

## GBM et quanto

`backend/app/core/payscript/engine.py:490` à 531 ; SHA-256 `37e62be348a68ad494888ae7cdeb801376d21adeccd94bb585cce10660b2edf1`.

```text
490: def _simulate_gbm(ts: int, n: int, N: int, dt: float, sq_dt: float,
491:                   underlyings, r_eff: float, L: np.ndarray,
492:                   Z: np.ndarray, spot_mult=None, vol_add=None,
493:                   r_path=None, Z_r=None, vol_out=None) -> np.ndarray:
494:     """Vectorized GBM — all paths at once via cumsum. Returns (ts+1, n, N).
495: 
496:     r_path (ts, N) and Z_r (ts, N) are the optional stochastic-rate level and raw
497:     shock from _stochastic_rate_paths — both None (default) reproduces the exact
498:     flat/curve-rate behavior. r_path overrides r_eff in the drift; Z_r re-blends
499:     each asset's own correlated Brownian via its rho_rS (_blend_rate_factor).
500: 
501:     vol_out (ts, n, N), when provided, is filled with the effective diffusion
502:     vol applied on each step — consumed by _bridge_extrema for continuous
503:     barrier monitoring. Same contract on every simulator below."""
504:     if n > 1:
505:         Z_flat = Z.reshape(ts, n, N).transpose(1, 0, 2).reshape(n, ts * N)
506:         Zc = (L @ Z_flat).reshape(n, ts, N).transpose(1, 0, 2)
507:     else:
508:         # The mono factor is sqrt(1-rho_rS^2) when coupled to a live rate.
509:         Zc = Z if L[0, 0] == 1.0 else L[0, 0] * Z
510: 
511:     S = np.ones((ts + 1, n, N), dtype=np.float64)
512:     if spot_mult is not None:
513:         S[0] = _seed_spot(spot_mult)
514: 
515:     r_term = r_eff if r_path is None else r_path
516:     dividend_steps = _build_dividend_step_matrix(underlyings, ts, dt)
517:     for i, u in enumerate(underlyings):
518:         sig = u.get("sigma", 0.20)
519:         if vol_add is not None:
520:             sig = max(0.005, sig + vol_add[i])
521:         if vol_out is not None:
522:             vol_out[:, i, :] = sig
523:         z_i = _blend_rate_factor(Zc[:, i, :], Z_r, u.get("rho_rS", 0.0)) if Z_r is not None else Zc[:, i, :]
524:         q_adj = u.get("sigma_fx", 0.0) * u.get("rho_sfx", 0.0) * sig
525:         q_term = (u.get("q", 0.02) if dividend_steps is None
526:                   else dividend_steps[:, i, None])
527:         drift = r_term + u.get("ccyh", 0.0) - q_term - q_adj - 0.5 * sig * sig
528:         log_ret = drift * dt + sig * sq_dt * z_i
529:         S[1:, i, :] = S[0, i] * np.exp(np.cumsum(log_ret, axis=0))
530: 
531:     return S
```

## Heston, variance et spot

`backend/app/core/payscript/engine.py:576` à 629 ; SHA-256 `37e62be348a68ad494888ae7cdeb801376d21adeccd94bb585cce10660b2edf1`.

```text
576:             rh  = u.get("rho_h", -0.70)
577:             kap = u.get("kappa", 2.0)
578:             th  = u.get("theta", 0.04)
579:             xi  = u.get("xi", 0.35)
580:             rhop = math.sqrt(max(0.0, 1.0 - rh*rh))
581: 
582:             cz_i = _blend_rate_factor(Zc[step, i, :], Z_r[step], u.get("rho_rS", 0.0)) if Z_r is not None else Zc[step, i, :]
583: 
584:             # Variance BM: correlated with spot via rho_h
585:             z_perp_var = Zv[step, i, :]             # independent component
586:             zv = rh * cz_i + rhop * z_perp_var      # full variance Brownian W_V
587: 
588:             V_old  = V[i]
589:             V_next = _heston_qe_vectorized(V_old, kap, th, xi, dt, zv)
590:             V_bar  = (V_old + V_next) / 2
591:             V[i]   = V_next
592: 
593:             sig_add = vol_add[i] if vol_add is not None else 0.0
594:             sv = np.sqrt(np.maximum(0.0, V_bar)) + sig_add
595:             if vol_out is not None:
596:                 vol_out[step, i, :] = sv
597: 
598:             q_adj = u.get("sigma_fx", 0.0) * u.get("rho_sfx", 0.0) * sv
599:             # `vol_add` bumps only the independent spot-volatility leg.  The
600:             # correlated Heston leg remains driven by sqrt(V_bar), so the
601:             # matching quadratic variation is rho^2*V_bar +
602:             # (1-rho^2)*sv^2.  Using -0.5*V_bar after changing `sv` breaks the
603:             # discounted-spot martingale and creates vega on PAY S[1].
604:             #
605:             # This is deliberate and it has a price: the resulting vega covers
606:             # only the independent leg, so it is scaled by (1-rho_h^2) — half
607:             # the true sensitivity at rho_h=-0.7, a fifth at -0.9. Scaling
608:             # corr_term to reach the correlated leg does NOT fix it: that term
609:             # is Andersen's exact substitution for rho/xi*integral(dV) and
610:             # carries its own compensator, so rescaling it shifts E[log S] with
611:             # nothing to offset it (measured: +40bp on a prepaid forward at
612:             # rho_h=-0.7). A genuine Heston vega means bumping the calibrated
613:             # parameters, not the diffusion legs — hence `vega_scope` below,
614:             # which reports the coverage rather than pretending it is total.
615:             bumped_variance = rh*rh * V_bar + rhop*rhop * sv*sv
616:             q_term = (u.get("q", 0.02) if dividend_steps is None
617:                       else dividend_steps[step, i])
618:             drift = (r_term + u.get("ccyh", 0.0) - q_term
619:                      - q_adj - 0.5 * bumped_variance)
620: 
621:             # Andersen (2007) spot update — see docstring for the martingale
622:             # derivation, unchanged from the original per-path formula.
623:             z_S_perp  = rhop * cz_i - rh * z_perp_var
624:             corr_term = rh / xi * (V_next - V_old - kap * (th - V_bar) * dt)
625:             S[step+1, i, :] = S[step, i, :] * np.exp(
626:                 drift*dt + corr_term + rhop * sv * sq_dt * z_S_perp
627:             )
628: 
629:     return S
```

## SABR et écrêtage

`backend/app/core/payscript/engine.py:673` à 702 ; SHA-256 `37e62be348a68ad494888ae7cdeb801376d21adeccd94bb585cce10660b2edf1`.

```text
673:             z_a = rho_s * z_S + math.sqrt(max(0.0, 1.0 - rho_s**2)) * za_raw
674: 
675:             # Lognormal SDE for stochastic vol α
676:             alpha_old = alpha[i]
677:             alpha_new = alpha_old * np.exp(nu * sq_dt * z_a - 0.5 * nu**2 * dt)
678: 
679:             # CEV effective vol: σ = α_old * S^(β−1)
680:             # Use alpha_old (not alpha_bar) to avoid correlation bias with z_S.
681:             # alpha_bar = f(z_a) = f(rho*z_S + ...) is correlated with z_S,
682:             # which would break E[exp(sig*z_S*√dt)] = exp(½sig²dt) martingale property.
683:             S_c = np.maximum(S[step, i, :], 1e-8)
684:             if abs(beta - 1.0) < 1e-4:
685:                 sig = alpha_old.copy()
686:             else:
687:                 sig = alpha_old * (S_c ** (beta - 1.0))
688: 
689:             if vol_add is not None:
690:                 sig = sig + vol_add[i]
691:             sig = np.clip(sig, 0.001, 3.0)
692:             if vol_out is not None:
693:                 vol_out[step, i, :] = sig
694: 
695:             q_adj = u.get("sigma_fx", 0.0) * u.get("rho_sfx", 0.0) * sig
696:             q_term = (u.get("q", 0.02) if dividend_steps is None
697:                       else dividend_steps[step, i])
698:             drift = r_term + u.get("ccyh", 0.0) - q_term - q_adj - 0.5 * sig**2
699:             S[step + 1, i, :] = S_c * np.exp(drift * dt + sig * sq_dt * z_S)
700:             alpha[i] = alpha_new
701: 
702:     return S
```

## LSV et particules

`backend/app/core/payscript/engine.py:879` à 914 ; SHA-256 `37e62be348a68ad494888ae7cdeb801376d21adeccd94bb585cce10660b2edf1`.

```text
879:             lv_target = g[step, k0] * (1.0-frac) + g[step, k0+1] * frac
880: 
881:             # Particle-method conditional expectation E[V|S], bucketed on a
882:             # finer grid than the local-vol lookup above. Uses
883:             # V_old (not V_next/V_bar): V_next is computed from zv_i, which is
884:             # correlated with the SAME Brownian cZ[step,i,:] that drives the
885:             # spot below — feeding a look-ahead, correlated variance into
886:             # THIS step's effective vol would break the discounted spot's
887:             # martingale property (identical pitfall to alpha_old vs
888:             # alpha_bar in _simulate_sabr above, see its comment). V_old is
889:             # known at the start of the step, uncorrelated with this step's
890:             # own shocks, so it's safe to use in both the bucketing and the
891:             # spot update below. Confirmed empirically by
892:             # test_heston_spot_process_is_martingale-style E[S_T] check.
893:             conditional_bucket = np.clip(((logS-logKmin)/conditional_step).astype(int),
894:                                           0, conditional_buckets-2)
895:             E_V_given_S = _lsv_conditional_variance(conditional_bucket, V_old,
896:                                                    conditional_buckets)
897: 
898:             leverage = np.clip(lv_target / np.sqrt(np.maximum(E_V_given_S, 1e-6)), 0.2, 5.0)
899:             eff_vol = leverage * np.sqrt(np.maximum(V_old, 0.0))
900:             if vol_add is not None:
901:                 eff_vol = eff_vol + vol_add[i]
902:             eff_vol = np.clip(eff_vol, 0.001, 3.0)
903:             if vol_out is not None:
904:                 vol_out[step, i, :] = eff_vol
905: 
906:             z_i = _blend_rate_factor(Zc[step, i, :], Z_r[step], u.get("rho_rS", 0.0)) if Z_r is not None else Zc[step, i, :]
907:             q_adj = u.get("sigma_fx", 0.0) * u.get("rho_sfx", 0.0) * eff_vol
908:             q_term = (u.get("q", 0.02) if dividend_steps is None
909:                       else dividend_steps[step, i])
910:             drift = r_term + u.get("ccyh", 0.0) - q_term - q_adj - 0.5*eff_vol**2
911:             S[step+1, i, :] = S_c * np.exp(drift*dt + eff_vol*sq_dt*z_i)
912:             V[i] = V_next
913: 
914:     return S
```

## OU et convexité

`backend/app/core/payscript/engine.py:1041` à 1088 ; SHA-256 `37e62be348a68ad494888ae7cdeb801376d21adeccd94bb585cce10660b2edf1`.

```text
1041: def _ou_transition(sigma_r: float, a_r: float, dt: float) -> tuple[float, float]:
1042:     """Exact OU transition, continuous at a_r=0 without subtractive cancellation."""
1043:     exponent = 2.0 * a_r * dt
1044:     variance_ratio = -math.expm1(-exponent) / exponent if exponent else 1.0
1045:     return math.exp(-a_r * dt), sigma_r * math.sqrt(dt * variance_ratio)
1046: 
1047: 
1048: def _hw_convexity(sigma_r: float, a_r: float, dt: float, ts: int,
1049:                   phi: float | None = None, step_sd: float | None = None) -> np.ndarray:
1050:     """Deterministic drift that makes the simulated short rate reprice its own
1051:     input curve — the property that defines Hull-White and that this model was
1052:     missing.
1053: 
1054:     Writing r = f(0,t) + x with x centred looks like it fits the curve for
1055:     free, but the discount factor is exp(-integral r), and Jensen makes
1056:     E[exp(-integral x)] = exp(+Var/2) > 1: every bond came out too EXPENSIVE,
1057:     by 164bp on a 5-year zero at 3% vol. The fix is the classic phi(t): add
1058:     back exactly the term that cancels that variance.
1059: 
1060:     The correction is computed on the DISCRETE integral the simulator actually
1061:     forms — dt * sum of x over steps — rather than on its continuous limit, so
1062:     the curve is reproduced to machine precision on the grid in use instead of
1063:     to a discretisation residual.
1064: 
1065:     For I_k = dt*sum_{j=1}^k x_j, psi_k = (Var(I_k)-Var(I_{k-1}))/(2*dt).
1066:     The OU branch propagates Var(x_k) and Cov(I_k,x_k) directly, avoiding the
1067:     cancellation of geometric sums as a_r tends to zero.
1068:     """
1069:     m = np.arange(1, ts + 1, dtype=np.float64)
1070:     if a_r == 0.0:
1071:         # x_k = sigma*sqrt(dt)*sum_{i<=k} Z_i  ->  weight of Z_i is
1072:         # dt*sigma*sqrt(dt)*(m-i), so Var(I_m) = sigma^2 dt^3 sum_{j=1..m} j^2.
1073:         var_I = sigma_r ** 2 * dt ** 3 * m * (m + 1.0) * (2.0 * m + 1.0) / 6.0
1074:     else:
1075:         if phi is None or step_sd is None:
1076:             phi, step_sd = _ou_transition(sigma_r, a_r, dt)
1077:         variance_x = covariance_I_x = 0.0
1078:         innovation_variance = step_sd * step_sd
1079:         psi = np.empty(ts, dtype=np.float64)
1080:         for k in range(ts):
1081:             variance_x = phi * phi * variance_x + innovation_variance
1082:             previous_covariance = phi * covariance_I_x
1083:             psi[k] = previous_covariance + 0.5 * dt * variance_x
1084:             covariance_I_x = previous_covariance + dt * variance_x
1085:         return psi
1086:     half = 0.5 * var_I
1087:     psi = np.empty(ts, dtype=np.float64)
1088:     psi[0] = half[0] / dt
```

## Funding

`backend/app/core/payscript/engine.py:1192` à 1216 ; SHA-256 `37e62be348a68ad494888ae7cdeb801376d21adeccd94bb585cce10660b2edf1`.

```text
1192: def _funding_df_arr(funding_curve, funding_spread: float,
1193:                     ts: int, dt: float) -> np.ndarray | None:
1194:     """Facteur d'actualisation du seul spread émetteur, ou None s'il n'y en a pas.
1195: 
1196:     DÉLIBÉRÉMENT séparé de `_RateTerm`, qui unifie drift, actualisation et
1197:     calibration du smile pour qu'ils ne puissent pas diverger. Un spread de
1198:     funding n'est pas un taux : il dit la qualité de crédit de celui qui doit
1199:     payer, pas le coût de portage du sous-jacent. Le crédit de l'émetteur ne
1200:     déplace pas le forward de l'action.
1201: 
1202:     Le router dans la courbe de taux donnerait le SIGNE INVERSE — sur une note
1203:     la hausse du forward l'emporte sur l'actualisation, et le produit vaudrait
1204:     plus cher à mesure que son émetteur se dégrade. C'est pour ça qu'il entre
1205:     ici, sur `df` seul, et jamais dans `step_fwd`.
1206: 
1207:     `funding_curve` (piliers [T, spread]) l'emporte sur `funding_spread`
1208:     (niveau plat). Interpolation et extrapolation identiques à celles de la
1209:     courbe de taux — même fonction, avec un taux de repli nul."""
1210:     if funding_curve:
1211:         return _build_df_arr(funding_curve, ts, dt, 0.0)
1212:     if funding_spread:
1213:         t = np.arange(ts + 1, dtype=np.float64) * dt
1214:         return np.exp(-funding_spread * t)
1215:     return None
1216: 
```

## Statistiques MC

`backend/app/core/payscript/engine.py:2671` à 2692 ; SHA-256 `37e62be348a68ad494888ae7cdeb801376d21adeccd94bb585cce10660b2edf1`.

```text
2671:             collect_analysis(S_anti, anti_details)
2672: 
2673:     # Price: antithetic average of paired paths (lower variance).
2674:     payoffs_avg = [(p1 + p2) / 2 for p1, p2 in zip(payoffs_base, payoffs_anti)] \
2675:                   if payoffs_anti else payoffs_base
2676: 
2677:     # Individual undiscounted payoffs (both legs) for the distribution histogram.
2678:     raw_all = sorted(raw_base + raw_anti) if raw_anti else sorted(raw_base)
2679: 
2680:     # Discounted payoffs for statistical quantities (VaR5, median, IC95).
2681:     pv_all  = sorted(payoffs_base + payoffs_anti) if payoffs_anti else sorted(payoffs_base)
2682: 
2683:     N_eff  = len(payoffs_avg)
2684:     N_hist = len(raw_all)
2685:     price  = sum(payoffs_avg) / N_eff
2686:     payoffs_arr = np.array(payoffs_avg)
2687:     se = math.sqrt(float(np.var(payoffs_arr, ddof=1)) / N_eff)
2688:     mid    = N_hist // 2
2689:     median = (pv_all[mid-1] + pv_all[mid]) / 2 if N_hist % 2 == 0 else pv_all[mid]
2690:     var5   = pv_all[int(N_hist * 0.05)]
2691:     prob_gt100 = sum(1 for p in raw_all if p > 1.0) / N_hist
2692: 
```

## Portée du vega

`backend/app/core/payscript/engine.py:2924` à 2966 ; SHA-256 `37e62be348a68ad494888ae7cdeb801376d21adeccd94bb585cce10660b2edf1`.

```text
2924:     for i in range(n):
2925:         if "delta" in sel or "gamma" in sel:
2926:             pu = price(spot_vec=_bumped(i, 1.01))
2927:             pd = price(spot_vec=_bumped(i, 0.99))
2928:             if "delta" in sel:
2929:                 greeks[f"delta_{i+1}"] = round((pu - pd) / 0.02, 4)
2930:             if "gamma" in sel:
2931:                 greeks[f"gamma_{i+1}"] = round(
2932:                     (price(spot_vec=_bumped(i, 1.03)) - 2*base_g
2933:                      + price(spot_vec=_bumped(i, 0.97))) / 0.0009, 4)
2934: 
2935:     if "vega" in sel:
2936:         for i in range(n):
2937:             va_up = [0.0]*n; va_up[i] = 0.01
2938:             va_dn = [0.0]*n; va_dn[i] = -0.01
2939:             greeks[f"vega_{i+1}"] = round((price(vol_add=va_up) - price(vol_add=va_dn)) / 0.02, 4)
2940:         # Under Heston the vol
2941:         # bump reaches only the leg independent of the variance Brownian, so
2942:         # the figure above covers a fraction (1-rho_h^2) of the true volatility
2943:         # sensitivity — half of it at the usual equity skew, a fifth at -0.9.
2944:         # It is a real sensitivity, just not the one the bare word "vega"
2945:         # implies, and a book aggregate that mixes it with GBM vegas is adding
2946:         # quantities of different scope. Say so rather than let the label pass.
2947:         if model == "heston":
2948:             greeks["vega_scope"] = {
2949:                 "type": "leg_independante",
2950:                 "coverage": {u.get("name", f"S{i+1}"):
2951:                              round(1.0 - float(u.get("rho_h", 0.0))**2, 4)
2952:                              for i, u in enumerate(underlyings)},
2953:             }
2954:         elif model == "lsv":
2955:             greeks['vega_scope'] = {'type': 'effective_local_vol', 'coverage': None,
2956:                 'definition': 'Additive bump of effective local volatility; variance process fixed, no recalibration',
2957:                 'unit': 'price per unit of volatility'}
2958:         else:
2959:             greeks["vega_scope"] = {"type": "total", "coverage": None}
2960: 
2961:     if "theta" in sel:
2962:         theta, theta_event = _theta_and_event(
2963:             script, T, st, base_g, base_res, reprice,
2964:             maturity_payment_t=maturity_payment_t)
2965:         greeks["theta"] = theta
2966:         greeks["theta_event"] = theta_event
```

## Domaine de barrière

`backend/app/core/payscript/bridge.py:16` à 54 ; SHA-256 `f6ee235f86cc594912077ce7b476381fb2c7dad95a2acff9f9f5e73421186804`.

```text
16: 
17: 
18: def basket_bridge_substeps(correlation=None):
19:     """Explicit refinement policy; unknown matrices use the conservative cap."""
20:     if correlation is None:
21:         return MAX_BASKET_BRIDGE_SUBSTEPS
22:     matrix = np.asarray(correlation, dtype=float)
23:     off_diagonal = np.abs(matrix - np.diag(np.diag(matrix)))
24:     strongest = off_diagonal.max()
25:     if strongest <= .5:
26:         return BASKET_BRIDGE_SUBSTEPS
27:     if strongest <= .9:
28:         return 256
29:     return MAX_BASKET_BRIDGE_SUBSTEPS
30: 
31: 
32: def validate_bridge_domain(underlyings, correlation, model, stochastic_rates=False):
33:     """Admit only the locally qualified basket domain; never change monitoring."""
34:     n = len(underlyings)
35:     if n <= 1:
36:         return
37:     matrix = np.asarray(correlation)
38:     bodies = [{key: value for key, value in u.items() if key not in {"name", "ticker"}}
39:               for u in underlyings]
40:     copies = np.all(matrix == 1.) and all(body == bodies[0] for body in bodies)
41:     if model == "constant" and copies:
42:         return
43:     if n == 2 and model == "constant" and not stochastic_rates and abs(matrix[0, 1]) <= .99:
44:         return
45:     raise ValueError(
46:         "Monitoring continu panier non qualifié pour cette configuration : domaine local C16 "
47:         "limité au GBM à deux actifs, taux déterministes et |corrélation| <= 99 %, ou aux "
48:         "copies GBM équivalentes corrélées à 1. Aucun passage automatique en hebdomadaire. "
49:         "Une qualification complémentaire est nécessaire.")
50: 
51: 
52: def resolve_bridge_substeps(correlation, override=None):
53:     selected = basket_bridge_substeps(correlation)
54:     if override is None:
```

## Métadonnées du pont

`backend/app/core/payscript/bridge.py:174` à 202 ; SHA-256 `f6ee235f86cc594912077ce7b476381fb2c7dad95a2acff9f9f5e73421186804`.

```text
174:             low_left, high_left = refine(left, middle, duration / 2, remaining - 1)
175:             low_right, high_right = refine(middle, right, duration / 2, remaining - 1)
176:             return np.minimum(low_left, low_right), np.maximum(high_left, high_right)
177:         low[step], high[step] = refine(logs[step], logs[step+1], dt, depth)
178:     return np.exp(low), np.exp(high)
179: 
180: 
181: def bridge_metadata(n, correlation=None, substeps=None):
182:     return {
183:         "policy": BRIDGE_POLICY,
184:         "method": "analytic_marginals" if n == 1 else "correlated_midpoints_with_marginal_leaves",
185:         "basket_substeps": resolve_bridge_substeps(correlation, substeps) if n > 1 else 1,
186:         "refinement_rule": "64 if max(abs(rho))<=0.5; 256 if <=0.9; 1024 otherwise",
187:         "joint_extrema_exact": False,
188:         "qualification": "local_synthetic_panel_only",
189:         "qualification_scope": "one_sided_two_asset_gbm_conditional_digital_or_equivalent_copies",
190:         "qualification_tolerance_nominal": QUALIFICATION_TOLERANCE_NOMINAL,
191:         "per_run_error_bound": None,
192:     }
193: 
194: 
195: def bridge_note(n, correlation=None, substeps=None):
196:     if n == 1:
197:         return ("Monitoring continu par pont brownien : chaque extremum marginal est exact "
198:                 "conditionnellement aux extrémités sous GBM à volatilité constante et taux "
199:                 "déterministes. La loi jointe minimum/maximum et les autres modèles restent approximatifs.")
200:     return (f"Monitoring continu panier approximatif : ponts browniens corrélés, "
201:             f"jusqu'à {resolve_bridge_substeps(correlation, substeps)} sous-pas par pas MC et extrema marginaux sur les sous-intervalles. "
202:             "La dépendance résiduelle des extrema reste approximative ; ce calcul n'est pas "
```

## Qualification de calibration

`backend/app/core/smile_calibration.py:97` à 142 ; SHA-256 `153f71eb8a2eb1b4c7fe49ec52c417029dc904013b7db633507b2bbe95ae6283`.

```text
97: def qualification(success, vanilla_error_bp, digital_error_bp, restrictions=()):
98:     reasons = list(restrictions)
99:     if not success:
100:         reasons.append('Optimisation non convergée.')
101:     if not math.isfinite(vanilla_error_bp) or vanilla_error_bp > THRESHOLDS_BP['vanilla']:
102:         reasons.append('Écart vanille supérieur à 5 pb.')
103:     if not math.isfinite(digital_error_bp) or digital_error_bp > THRESHOLDS_BP['digital']:
104:         reasons.append('Écart digitale supérieur à 10 pb.')
105:     return {'qualified': not reasons, 'reasons': reasons,
106:             'thresholds_bp': dict(THRESHOLDS_BP),
107:             'scope': 'Published vanilla/digital control points, flat deterministic carry only',
108:             'production_approved': False}
109: 
110: 
111: def calibrate_surface(payload, model, horizon, rate=.03, dividend=.02):
112:     if model not in ('heston', 'sabr', 'lsv') or not math.isfinite(horizon) or horizon <= 0:
113:         raise ValueError('Modèle ou horizon de calibration invalide.')
114:     surface = TermSSVISurface(payload)
115:     requested_horizon = horizon
116:     horizon = min(horizon, surface.max_expiry, 10.)
117:     # Every material target pillar is an objective point, including edited 7Y.
118:     expiries = sorted({min(t, horizon) for t in (.5, 1., 2., 4., horizon)} |
119:                       {float(t) for t, _ in surface.nodes if t <= horizon})
120:     strikes = np.array([.6, .8, 1., 1.2, 1.5])
121:     target = [surface.vanillas(strikes, t, rate, dividend) for t in expiries]
122:     calls, digitals = np.array([p[0] for p in target]), np.array([p[2] for p in target])
123:     atm = math.sqrt(surface._theta(min(1., horizon))[0]/min(1., horizon))
124:     vegas = []
125:     for t in expiries:
126:         w = surface.derivatives(np.log(strikes)-(rate-dividend)*t, t)[0]
127:         d1 = -(np.log(strikes)-(rate-dividend)*t)/np.sqrt(w)+np.sqrt(w)/2
128:         vegas.append(np.maximum(.03, math.exp(-dividend*t)*np.exp(-d1*d1/2)
129:                                 /math.sqrt(2*math.pi)*math.sqrt(t)))
130:     vegas = np.asarray(vegas)
131:     restrictions = []
132:     if requested_horizon > horizon:
133:         restrictions.append('Horizon demandé non couvert intégralement.')
134:     if model in ('heston', 'lsv'):
135:         keys = ('v0', 'theta', 'kappa', 'xi', 'rho_h')
136:         initial = [atm**2, atm**2, 1., max(.15, atm), surface.rho]
137:         bounds = ([.0001, .0001, .05, .01, -.98], [2., 2., 12., 3., .98])
138:         evaluate = lambda x: heston_prices(dict(zip(keys, x)), expiries, strikes, rate, dividend)
139:         method = 'Fourier Heston'
140:         if model == 'lsv':
141:             restrictions.append('Composante Heston seule : le modèle LSV complet n’est pas qualifié par cet ajustement.')
142:     else:
```

## Fraîcheur

`backend/app/core/market_policy.py:1` à 20 ; SHA-256 `91c32c0b9da133ad05315c0de852f352987e3658207ec99b645a9be8a1fe449e`.

```text
1: """Explicit dated-market freshness policy; contractual finality is separate."""
2: from datetime import date
3: 
4: 
5: # D03: user-approved calendar-day limits, inclusive at the boundary.
6: POLICY_VERSION = "D03-C11-2026-10-21-3D"
7: HISTORY_MAX_AGE_DAYS: int | None = 3
8: REPORTING_FX_MAX_AGE_DAYS: int | None = 3
9: 
10: 
11: def freshness(effective: str | date | None, requested: str | date, usage: str) -> dict:
12:     requested = date.fromisoformat(requested) if isinstance(requested, str) else requested
13:     effective = date.fromisoformat(effective) if isinstance(effective, str) else effective
14:     maximum = REPORTING_FX_MAX_AGE_DAYS if usage == "reporting_fx" else HISTORY_MAX_AGE_DAYS
15:     age = (requested-effective).days if effective else None
16:     status = ("MISSING" if age is None else "FUTURE" if age < 0 else "FRESH" if age == 0
17:               else "POLICY_NOT_CONFIGURED" if maximum is None else "CARRIED" if age <= maximum else "STALE")
18:     return dict(policy_version=POLICY_VERSION, usage=usage, requested_asof=requested.isoformat(),
19:                 effective_date=effective.isoformat() if effective else None, age_days=age,
20:                 max_age_days=maximum, status=status, qualified=status in {"FRESH", "CARRIED"})
```

## Finalité de close

`backend/app/core/fixing_finality.py:31` à 58 ; SHA-256 `96083ec253ab23e656cbf01c0fa23a2a4a452fa05e93d90fcae8b897ea00a182`.

```text
31: def qualify_close(market_date, source, *, now=None):
32:     result = {"policy": POLICY_VERSION, "qualified": False, "market_date": market_date}
33:     try:
34:         day = date.fromisoformat(market_date)
35:         calendar_name = VENUES.get(source.get("exchange"))
36:         if not calendar_name:
37:             return {**result, "status": "VENUE_UNKNOWN"}
38:         cal = session_calendar(calendar_name, day.year)
39:         zone = ZoneInfo(str(source.get("timezone") or ""))
40:         if str(zone) != str(cal.tz):
41:             return {**result, "status": "TIMEZONE_MISMATCH", "calendar": calendar_name}
42:         result.update(calendar=calendar_name, timezone=str(zone), exchange=source["exchange"])
43:         if not cal.is_session(day.isoformat()):
44:             return {**result, "status": "NON_SESSION"}
45:         eligible_at = cal.session_close(day.isoformat()).to_pydatetime()
46:         result["eligible_at"] = eligible_at.isoformat()
47:         clock = now or utc_now()
48:         if clock.tzinfo is None:
49:             raise ValueError("Clock must be timezone aware")
50:         if clock < eligible_at:
51:             return {**result, "status": "WAITING_SESSION_CLOSE"}
52:         fetched = datetime.fromisoformat(str(source.get("fetched_at") or "").replace("Z", "+00:00"))
53:         if fetched.tzinfo is None or fetched < eligible_at or fetched > clock:
54:             return {**result, "status": "PUBLICATION_UNVERIFIED"}
55:         return {**result, "qualified": True, "status": "ELIGIBLE_PUBLISHED_CLOSE",
56:                 "fetched_at": fetched.isoformat(), "calendar_version": __import__("exchange_calendars").__version__}
57:     except (ValueError, TypeError, KeyError, ImportError, OverflowError):
58:         return {**result, "status": "SESSION_METADATA_UNAVAILABLE"}
```

## Réutilisation locale

`backend/app/services/market_data.py:201` à 267 ; SHA-256 `7f42c98fe2b70678360ecb968cd914d8ad43c8414897a7bc08f3fa4a1c18e273`.

```text
201: def _load_hist_prices_uncached(tickers, start, end, adjusted, provider, allow_partial):
202:     """Provider observations with durable local reuse and explicit coverage."""
203:     from ..runtime import business_today
204:     from ..core import market_policy, market_storage
205:     from .market_history import local_history, store_history, align_history, _path as shared_path
206:     from .scenario_market import configured_path, history
207:     if configured_path():
208:         result = history(tickers, start, end, adjusted)
209:         if result.get("error"):
210:             return result
211:         frames = {tk:pd.Series(values, index=pd.to_datetime(result["dates"])) for tk,values in result.get("prices", {}).items()}
212:         qualified = align_history(tickers, frames, start, end or business_today().isoformat(), adjusted,
213:                                   {tk:{"provider":result.get("provider"), "storage":"SCENARIO"} for tk in frames}, {}, allow_partial)
214:         return {**result, **qualified, "provider":result.get("provider", "SYNTHETIC_SCENARIO")}
215:     try:
216:         provider = normalize_market_data_provider(provider)
217:         requested_end = date.fromisoformat(end) if end else business_today()
218:         if date.fromisoformat(start) > requested_end:
219:             raise ValueError('La date de début doit précéder la date de fin.')
220:     except ValueError as exc:
221:         return {"error": str(exc)}
222:     end = requested_end.isoformat()
223:     series, sources, failures, fetched = {}, {}, {}, {}
224:     expected = market_storage.versions([shared_path(ticker,adjusted) for ticker in tickers])
225:     for ticker in tickers:
226:         local, source = local_history(ticker, start, end, adjusted)
227:         local_window = local.loc[(local.index >= pd.Timestamp(start)) & (local.index <= pd.Timestamp(end))] if local is not None else None
228:         usable = (local_window is not None and not local_window.empty
229:                   and source.get("requested_start", start) <= start
230:                   and market_policy.freshness(local_window.index[-1].date(), requested_end, "history")["qualified"])
231:         selected = local_window if usable else None
232:         if selected is None and _HAS_YF:
233:             try:
234:                 frame = yf.Ticker(ticker).history(start=start,
235:                     end=(requested_end+timedelta(days=1)).isoformat(), auto_adjust=adjusted)
236:                 if not frame.empty and "Close" in frame:
237:                     selected = market_storage.validate_frame(frame[['Close']], ('Close',))['Close']
238:                     selected = selected.loc[(selected.index >= pd.Timestamp(start)) & (selected.index <= pd.Timestamp(end))]
239:                     if not selected.empty:
240:                         source = dict(provider=provider, storage="PROVIDER", fetched_at=datetime.utcnow().isoformat(),
241:                                       requested_start=start, requested_end=end, finality="UNVERIFIED_PROVIDER_BAR")
242:                         fetched[ticker] = selected
243:             except Exception as exc:
244:                 failures[ticker] = f"PROVIDER_UNAVAILABLE: {type(exc).__name__}"
245:         if selected is None or selected.empty:
246:             selected = local_window
247:         if selected is not None and not selected.empty:
248:             series[ticker] = selected
249:             sources[ticker] = source
250:         else:
251:             failures.setdefault(ticker, "NO_OBSERVATIONS")
252:     if fetched:
253:         try:
254:             with market_storage.transaction() as pending:
255:                 pending.require_unchanged(expected)
256:                 for ticker,values in fetched.items():
257:                     store_history(ticker,values,adjusted,start,end,transaction=pending)
258:         except (OSError,ValueError) as exc:
259:             for ticker in fetched:
260:                 sources[ticker]['storage_error'] = str(exc)
261:     payload = align_history(tickers, series, start, end, adjusted, sources, failures, allow_partial)
262:     payload["retrieved_at"] = datetime.utcnow().isoformat()
263:     payload["fetched_at"] = min((source["fetched_at"] for source in sources.values() if source.get("fetched_at")), default=None)
264:     payload["age_sessions"] = {tk:_business_sessions_between(date.fromisoformat(day), requested_end)
265:                                for tk,day in payload["effective_dates"].items()}
266:     return payload
267: 
```

## Autorité des fixings

`backend/app/core/official_history.py:12` à 53 ; SHA-256 `13317e474a2d0fd159b4ae9286f4434aa5ec9a15fbc96b344ef3c44c60c9ad42`.

```text
12:     underlyings = json.loads(deal.underlyings_json or "[]")
13:     names = {u["name"]: u["ticker"] for u in underlyings}
14:     rows, versions, strike = {}, [], {}
15:     for event in events:
16:         if event.event_date > asof.isoformat():
17:             continue
18:         version = session.get(OfficialFixingVersion, event.current_fixing_version_id) if event.current_fixing_version_id else None
19:         if not version:
20:             if event.current_fixing_version_id or event.fixing_version:
21:                 raise HTTPException(409, {"code": "OFFICIAL_FIXING_VERSION_MISSING", "event_id": event.id})
22:             if event.data_category == "FIXING_CANDIDATE":
23:                 raise HTTPException(409, {"code": "OFFICIAL_FIXING_PENDING", "event_id": event.id})
24:             continue
25:         if version.status not in {"VALIDATED", "APPLIED"}:
26:             raise HTTPException(409, {"code": "OFFICIAL_FIXING_PENDING", "event_id": event.id,
27:                 "message": "Une version de fixing attend une décision ; le MtM ne peut lui substituer le fournisseur."})
28:         values = json.loads(version.spots_json)
29:         if (version.deal_id != deal.id or version.deal_event_id != event.id
30:                 or version.record_sha256 != event.fixing_record_sha256
31:                 or values != json.loads(event.spots_json or "{}")
32:                 or set(values) != set(names)
33:                 or any(isinstance(v, bool) or not isinstance(v, (int, float))
34:                        or not isfinite(v) or v <= 0 for v in values.values())):
35:             raise HTTPException(409, {"code": "OFFICIAL_FIXING_LEDGER_MISMATCH", "event_id": event.id})
36:         points = {names[name]: float(v) for name, v in values.items()}
37:         if event.event_date in rows and rows[event.event_date] != points:
38:             raise HTTPException(409, {"code": "OFFICIAL_FIXING_DATE_CONFLICT", "event_date": event.event_date})
39:         rows[event.event_date] = points
40:         versions.append({"event_id": event.id, "event_date": event.event_date, "version_id": version.id,
41:                          "version": version.version, "record_sha256": version.record_sha256})
42:         if event.t_years == 0 and event.parent_event_id is None:
43:             strike = values
44:     # Add missing contractual dates without manufacturing observations for
45:     # another ticker. Each official row contains the complete contractual basket.
46:     combined = sorted({d for d in dates if d <= asof.isoformat()} | set(rows))
47:     original = {d: i for i, d in enumerate(dates)}
48:     overlaid = {tk: [rows[d][tk] if d in rows else prices[tk][original[d]]
49:                     for d in combined] for tk in names.values()}
50:     evidence = {"authority": "OFFICIAL_FIXINGS_WITH_PROVIDER_HISTORY" if versions else "INDICATIVE_PROVIDER_HISTORY",
51:                 "official_fixings": versions, "official_dates": sorted(rows),
52:                 "provider_history_overridden": bool(versions)}
53:     return overlaid, combined, deepcopy(strike), evidence
```

## Contrôles de publication

`backend/app/services/rfq_publication.py:167` à 209 ; SHA-256 `b961b1f3a6e8922053049d8697bcdc3e18290a27351213cdc8f0a01db87fae92`.

```text
167: def commercial_checks(session, item, case, draft, policy):
168:     bank.require_open(session, item)
169:     if not policy:
170:         raise HTTPException(409, "Configurez la politique de publication du desk bancaire")
171:     if not case or case.state != "IN_PROGRESS" or case.revision != draft.case_revision:
172:         raise HTTPException(409, "La responsabilité du dossier a changé ; préparez à nouveau la réponse")
173:     request = json.loads(item.request_json)
174:     payload = json.loads(draft.payload_json)
175:     relation = session.get(RfqRelationship, item.relationship_id)
176:     round_row = session.get(RfqExchangeRound, item.round_id)
177:     rfq = session.get(RfqRequest, round_row.rfq_id)
178:     if not relation or relation.version != request["recipient"]["relationship_version"]:
179:         raise HTTPException(409, "La relation reconnue a changé ; un nouveau tour est nécessaire")
180:     failures = relationships.eligibility(session, relation, rfq, currency=request["currency"], nominal=request["nominal"])
181:     if failures:
182:         raise HTTPException(409, {"message": "Relation RFQ inactive ou hors périmètre", "failures": failures})
183:     product = load_product(session, case.product_id)
184:     calc = session.get(ProductCalculationRun, draft.calculation_id)
185:     if not calc or calc.product_id != case.product_id or calc.terms_version != product.terms_version \
186:             or product.terms_fingerprint != request["terms_fingerprint"]:
187:         raise HTTPException(409, "Le calcul ne porte pas sur les termes reçus")
188:     if not product.calculations or product.calculations[-1].id != calc.id:
189:         raise HTTPException(409, "Un calcul plus récent existe ; préparez à nouveau la réponse")
190:     now = business_now()
191:     # Pricing receipts are issued on the operational UTC clock. Accelerated
192:     # business dates govern contractual validity, not the age of a calculation.
193:     calculation_now = datetime.utcnow()
194:     if calc.calculated_at > calculation_now or calculation_now - calc.calculated_at > timedelta(minutes=policy.max_calculation_age_minutes):
195:         raise HTTPException(409, "Le calcul privé est trop ancien pour la politique du desk")
196:     if utc(payload["valid_until"]) <= now:
197:         raise HTTPException(409, "La validité proposée est dépassée")
198:     if payload["firmness"] == "FIRM":
199:         treatment_failures = relationships.eligibility(session, relation, rfq,
200:             currency=request["currency"], nominal=request["nominal"], purpose="treat")
201:         if treatment_failures:
202:             raise HTTPException(422, {"message": "La relation et les accords de traitement doivent autoriser une offre ferme",
203:                 "failures": treatment_failures})
204:         if not payload["documentation_reference"]:
205:             raise HTTPException(422, "Une offre ferme exige une documentation explicite")
206:         if any(not request["terms"].get(field) for field in ("strike_date", "value_date", "maturity_date", "payment_date")):
207:             raise HTTPException(422, "Une offre ferme exige les quatre dates contractuelles")
208:     return product
209: 
```

## Contrôles de réception bancaire

`backend/app/services/rfq_electronic.py:146` à 179 ; SHA-256 `5f7058171522d428bbc508507e67f4273f7365ddb337dc66924bafc52ead2035`.

```text
146: def _bank_checks(session, item, payload, received_at):
147:     quote = payload['quote']
148:     published = session.exec(select(RfqQuotePublication).where(
149:         RfqQuotePublication.message_id == quote.get('message_id'), RfqQuotePublication.solicitation_id == item.id)).first()
150:     if not published or transport.canonical(json.loads(published.payload_json)) != transport.canonical(quote):
151:         raise HTTPException(409, 'La cotation exacte est inconnue ou modifiée.')
152:     if quote.get('firmness') != 'FIRM' or quote.get('conditions_type') != 'NONE':
153:         raise HTTPException(409, 'La cotation n’est pas ferme et sans condition.')
154:     # Validate against the receiving bank's clock; never backdate from the requester.
155:     if received_at >= publication.utc(quote['valid_until']) or received_at < publication.utc(quote['published_at']):
156:         raise HTTPException(409, 'La cotation n’était pas valable à sa réception bancaire.')
157:     if published.withdrawn_at or session.exec(select(RfqQuotePublication).where(
158:             RfqQuotePublication.solicitation_id == item.id, RfqQuotePublication.revision > published.revision)).first():
159:         raise HTTPException(409, 'La cotation a été retirée ou remplacée avant réception.')
160:     round_row = session.get(RfqExchangeRound, item.round_id)
161:     rfq = session.get(RfqRequest, round_row.rfq_id)
162:     if round_row.state != 'OPEN' or rfq.status in {'clos', 'sans_suite'}:
163:         raise HTTPException(409, 'Le tour a été clôturé avant réception.')
164:     case = session.get(RfqBankCase, item.id)
165:     if not case or case.state != 'IN_PROGRESS':
166:         raise HTTPException(409, 'La demande n’est pas prise en charge par la banque.')
167:     product = load_product(session, case.product_id)
168:     if product.terms_fingerprint != quote['terms_fingerprint'] or product.execution:
169:         raise HTTPException(409, 'Le Product bancaire ne porte pas les termes publiés.')
170:     relation = session.get(RfqRelationship, item.relationship_id)
171:     transport.channel_current(session, transport.channel_for_relation(session, relation.id))
172:     if relation.version != json.loads(item.request_json)['recipient']['relationship_version']:
173:         raise HTTPException(409, 'La relation du tour a changé.')
174:     failures = execution.relationships.eligibility(session, relation, rfq,
175:         currency=quote['currency'], nominal=quote['nominal'], purpose='treat')
176:     if failures:
177:         raise HTTPException(409, 'Traitement hors périmètre : ' + '; '.join(failures))
178:     return published, case
179: 
```

## Contexte bancaire de booking

`backend/app/services/rfq_electronic.py:304` à 345 ; SHA-256 `5f7058171522d428bbc508507e67f4273f7365ddb337dc66924bafc52ead2035`.

```text
304: def bank_booking_context(session, body, user):
305:     entry = _bank_entry(session, body.product_id)
306:     if not entry:
307:         return None, None
308:     bank.require_action(session, entry.solicitation_id, user, 'book', lock=True)
309:     session.refresh(entry)
310:     if entry.state != 'CONFIRMED':
311:         raise HTTPException(409, 'La décision électronique bancaire doit être confirmée avant booking.')
312:     booked = session.get(RfqElectronicBooking, entry.id)
313:     if booked:
314:         if booked.request_hash != execution.booking_request_hash(body):
315:             raise HTTPException(409, 'Cette exécution électronique est déjà bookée avec un autre contenu.')
316:         return entry, session.get(Deal, booked.deal_id)
317:     quote = json.loads(entry.request_json)['quote']
318:     item = session.get(RfqSolicitation, entry.solicitation_id)
319:     side = session.get(RfqRelationshipSide, (item.relationship_id, user.entity_id))
320:     legal = session.get(Counterparty, side.counterparty_id) if side else None
321:     product = load_product(session, body.product_id)
322:     expected = {'price_traded': quote['price'], 'nominal': quote['nominal'], 'devise': quote['currency'],
323:         'sens': 'achat' if quote['side'] == 'BUY' else 'vente', 'counterparty_id': legal.id if legal else None,
324:         'product_terms_version': product.terms_version}
325:     if not legal or not legal.active or any(getattr(body, key) != value for key, value in expected.items()) \
326:             or product.terms_fingerprint != quote['terms_fingerprint']:
327:         raise HTTPException(409, 'Le booking bancaire diffère de l’accord électronique : prix, nominal, sens, parties ou termes.')
328:     return entry, None
329: 
330: 
331: def attach_booking(session, body, deal, user, request_hash):
332:     entry = _bank_entry(session, deal.product_id)
333:     agreement = execution.active_agreement(session, body.rfq_id) if body.rfq_id else None
334:     if not entry and agreement:
335:         entry = session.exec(select(RfqElectronicExecution).where(
336:             RfqElectronicExecution.agreement_id == agreement.id)).first()
337:     if not entry:
338:         return
339:     session.add(RfqElectronicBooking(execution_id=entry.id, deal_id=deal.id, request_hash=request_hash,
340:         booked_by=user.id, booked_at=business_now()))
341:     _audit(session, entry, user.id, 'RFQ_ELECTRONIC_EXECUTION_BOOKED_LOCALLY')
342:     from .rfq_reconciliation import stage_current
343:     stage_current(session, entry, user.id)
344: 
345: 
```

## Transport authentifié

`backend/app/services/rfq_transport.py:53` à 124 ; SHA-256 `9885d1ab628967885b4df0380a4208142df1e64d1ac657a29fc2c78b9ceabc6d`.

```text
53: def endpoint(value):
54:     try:
55:         url = urlsplit(value)
56:         if url.port is not None and not 1 <= url.port <= 65535:
57:             raise ValueError("port")
58:     except ValueError:
59:         raise HTTPException(422, "Adresse d'installation ou port invalide") from None
60:     try:
61:         loopback = ipaddress.ip_address(url.hostname).is_loopback
62:     except ValueError:
63:         loopback = False
64:     if url.username or url.password or url.query or url.fragment or url.path not in {"", "/"} or not url.hostname:
65:         raise HTTPException(422, "Adresse d'installation invalide : origine HTTPS seule requise")
66:     if url.scheme != "https" and not (url.scheme == "http" and loopback
67:             and os.getenv("STRUCTURA_RFQ_ALLOW_LOOPBACK_HTTP") == "1"):
68:         raise HTTPException(422, "HTTPS requis ; HTTP local est réservé à la recette explicitement activée")
69:     return value.rstrip("/")
70: 
71: 
72: def agreement(session, relation):
73:     # Public commercial addresses and perimeter, never local IDs or booking data.
74:     return exchange.digest({"terms": json.loads(relation.terms_json),
75:         "requester": session.get(Entity, relation.requester_entity_id).name,
76:         "bank": session.get(Entity, relation.partner_entity_id).name,
77:         "desk": session.get(RfqDesk, relation.receiver_desk_id).name})
78: 
79: 
80: def channel_current(session, channel, *, confirmed=True, protective=False):
81:     relation = session.get(RfqRelationship, channel.relationship_id)
82:     if protective and channel.active and relation:
83:         return relation
84:     if not channel.active or not relation or relation.version != channel.relationship_version \
85:             or agreement(session, relation) != channel.agreement_hash:
86:         raise HTTPException(409, "Canal suspendu ou accord modifié : reconfigurez la reconnaissance du canal")
87:     own = session.get(RfqRelationshipSide, (relation.id, channel.entity_id))
88:     if not own or own.suspended or own.recognized_version != relation.version:
89:         raise HTTPException(409, "Votre organisation doit reconnaître l'accord courant")
90:     if confirmed and not channel.confirmed_at:
91:         raise HTTPException(409, "Appairage distant en attente")
92:     return relation
93: 
94: 
95: def signature(channel, value):
96:     return hmac.new(bytes.fromhex(channel.secret), canonical(value).encode(), hashlib.sha256).hexdigest()
97: 
98: 
99: def envelope(session, channel, operation, message):
100:     body = {"protocol": PROTOCOL, "channel_id": channel.id, "sender": identity(session),
101:         "receiver": channel.peer_installation_id, "issued_at": exchange.iso(datetime.utcnow()),
102:         "operation": operation, "message": message}
103:     return {"body": body, "signature": signature(channel, body)}
104: 
105: 
106: def verify(session, packet):
107:     body = packet.get("body", {})
108:     channel = session.get(RfqChannel, body.get("channel_id"))
109:     if not channel or not channel.active or not hmac.compare_digest(
110:             str(packet.get("signature", "")), signature(channel, body)):
111:         raise HTTPException(401, "Authentification du canal RFQ refusée")
112:     if set(body) != {"protocol", "channel_id", "sender", "receiver", "issued_at", "operation", "message"} \
113:             or body["protocol"] != PROTOCOL or body["sender"] != channel.peer_installation_id \
114:             or body["receiver"] != identity(session):
115:         raise HTTPException(401, "Installation ou protocole RFQ incorrect")
116:     from .rfq_publication import utc
117:     try:
118:         age = abs((datetime.utcnow() - utc(body["issued_at"])).total_seconds())
119:     except (ValueError, TypeError):
120:         raise HTTPException(401, "Horodatage du transport invalide")
121:     if age > 300:
122:         raise HTTPException(401, "Enveloppe de transport expirée")
123:     return channel, body
124: 
```

## Booking natif

`backend/app/api/deals.py:1654` à 1720 ; SHA-256 `1b72b12bf73b2e4de27e22861c9dd1291a2129be562fbf7a5f7858c8953a5763`.

```text
1654: def _execute_booking(
1655:     body: DealCreate,
1656:     current: User,
1657:     session: Session,
1658:     *,
1659:     reference_prefix: str | None = None,
1660:     uat_batch_id: int | None = None,
1661:     command: tuple[str, str] | None = None,
1662: ):
1663:     from ..core.access import require_booking_permission
1664:     require_booking_permission(current)
1665:     invalid_numbers = _non_finite_booking_paths(body.model_dump())
1666:     if invalid_numbers:
1667:         _reject_booking(session, current, body, 422, {
1668:             'code': 'BOOKING_NON_FINITE',
1669:             'message': 'Valeurs numériques finies requises avant booking.',
1670:             'fields': invalid_numbers,
1671:         })
1672:     from ..services import rfq_execution
1673:     execution_request_hash = rfq_execution.booking_request_hash(body)
1674:     try:
1675:         agreement, replayed = rfq_execution.booking_context(session, body, current)
1676:         if replayed is not None:
1677:             result = _deal_row(replayed, _get_events(replayed.id, session), session)
1678:             if command is not None:
1679:                 from ..services.booking_commands import stage_booking_command
1680:                 stage_booking_command(session, current, *command, replayed)
1681:                 session.commit()
1682:             else:
1683:                 session.rollback()
1684:             return result
1685:         from ..services.legal_identity import active_counterparty
1686:         legal_exception = None
1687:         if body.legal_identity_exception is not None:
1688:             from ..services.legal_identity import booking_exception
1689:             legal_exception = booking_exception(session, current, body)
1690:             body.contrepartie = legal_exception["counterparty_name"]
1691:             legal_exception.update({"actor_user_id": current.id, "actor_role": current.role,
1692:                 "entity_id": current.entity_id, "approved_at": business_now().isoformat(),
1693:                 "booking_request_hash": execution_request_hash,
1694:                 "nominal": body.nominal, "currency": body.devise})
1695:         else:
1696:             legal = active_counterparty(session, body.counterparty_id)
1697:             if body.contrepartie.strip() != legal.name:
1698:                 raise HTTPException(422, "Le libellé ne correspond pas à l'identifiant juridique choisi.")
1699:             body.contrepartie = legal.name
1700:         _validate_economics(body)
1701:         ai_provenance = _ai_script_provenance(body)
1702:         _apply_pricing_receipt(body, ai_provenance)
1703:         from ..core.ccr.service import enforce_booking
1704:         enforce_booking(session, current, body)
1705:         if ai_provenance and not body.pricing_receipt:
1706:             body.market_snapshot["ai_script_provenance"] = ai_provenance
1707:     except HTTPException as exc:
1708:         _reject_booking(session, current, body, exc.status_code, exc.detail)
1709: 
1710:     # Validate the RFQ link BEFORE the deal exists: rfq_id is a best-execution
1711:     # trail (which tender this trade came out of), so a stale or foreign id
1712:     # must be refused outright rather than persisted on the deal and merely
1713:     # skipped when closing the RFQ below.
1714:     client_id = body.client_id
1715:     mandate_id = body.mandate_id
1716:     opportunity_id = body.opportunity_id
1717:     primary_affiliation_id = body.primary_affiliation_id
1718:     commercial_reason = str(body.commercial_reason or "").strip() or None
1719:     legal_context = {
1720:         "transaction_format": str(body.transaction_format or "").strip() or None,
```

## Rejeu résiduel

`backend/app/core/inlife_valuation.py:334` à 378 ; SHA-256 `f6d03c24b389d7c0a151ddc94f41e81a273d5bd39ff6a49a160acbf9d8c4d23f`.

```text
334: def build_residual(p: InLifeProduct, prices: dict, dates_list: list,
335:                    T_elapsed: float, asof: date,
336:                    variant: Optional[VariantTerms] = None) -> Residual:
337:     """Rejoue le passé sur cours réels et construit le produit résiduel.
338: 
339:     L'historique arrive de l'appelant, en cours NUS : un payoff ne se lit pas
340:     sur une série ajustée des dividendes. Le cœur ne fait aucune entrée-sortie,
341:     ce qui le rend testable sans réseau et réutilisable avec un historique
342:     fourni autrement que par Yahoo.
343: 
344:     Rend un Residual ; lève ValuationError si le produit n'est pas rejouable.
345:     """
346:     today = asof
347:     value_d = p.value_date
348:     market = p.market
349:     underlyings_json = list(p.underlyings)
350:     tickers = [u["ticker"] for u in underlyings_json if u.get("ticker")]
351:     if not tickers and asof >= p.strike_date:
352:         raise ValuationError("Aucun ticker défini sur ce deal")
353: 
354:     try:
355:         compiled = parse_script(p.script_snapshot)
356:         # Même origine qu'au booking : un MtM qui recalerait le calendrier
357:         # sur une autre date ne vaudrait plus le même produit.
358:         _origin = p.strike_date
359:         if p.frozen_schedule is not None:
360:             from .product.calendar import restore_calendar
361:             compiled = restore_calendar(compiled, p.frozen_schedule)
362:         else:
363:             compiled = resolve_constats(compiled, market.get("constats") or {}, anchor=_origin,
364:                                         currency=p.currency or None)
365:     except ValueError as e:
366:         raise ValuationError(f"Script/calendriers non exploitables pour le MtM résiduel "
367:                                  f"(deal booké avant la persistance des CONSTAT ?) : {e}")
368: 
369:     # ── Avant le strike : il n'y a pas de passé, et pas encore de S₀ ───
370:     #
371:     # Le produit n'a pas commencé. Aucune constatation n'a eu lieu, aucun coupon
372:     # n'a été versé, aucune barrière n'a pu être franchie — et le niveau initial
373:     # n'existe pas : il sera constaté à la date de strike.
374:     #
375:     # L'axe des temps commence donc à la date de VALORISATION, et le fixing est
376:     # simulé comme le reste : `T_elapsed` est négatif, ce qui décale les
377:     # constatations vers l'avenir de l'écart au strike, et `strike_set_t` dit au
378:     # moteur à quel pas chaque trajectoire fixe SON strike. Le payoff, écrit en
```

## MtM d'une créance

`backend/app/core/deal_valuation.py:171` à 227 ; SHA-256 `a10e45705486fb69eeceb047ea87af44ada69603aee62748c0f867ac91e189a6`.

```text
171:             raise HTTPException(422, "Règlement atteint — l'exposition est soldée")
172:         market = json.loads(deal.market_snapshot_json or "{}")
173:         elapsed_origin = terms.strike_date
174:         elapsed = max(0.0, (today - elapsed_origin).days / 365.25)
175:         funding_curve, funding_spread = valuation_funding(body, market, elapsed)
176:         r_frac = body.r / 100.0 if body.r is not None else snapshot_rate(market)
177:         yield_curve = ([] if body.r is not None else
178:                        [[p["T"], p["rate"] / 100.0]
179:                         for p in market.get("yieldCurve") or []])
180:         amount = float(
181:             deal.settlement_amount
182:             if deal.settlement_amount is not None else
183:             (deal.realized_payout or 0.0)
184:         )
185:         remaining = (payment - today).days / 365.25
186:         mtm = deterministic_cashflow_pv(
187:             amount, remaining, r=r_frac, yield_curve=yield_curve,
188:             funding_curve=funding_curve, funding_spread=funding_spread)
189:         payload = {
190:             "deal_id": deal_id, "reference": deal.reference,
191:             "valuation_date": today.isoformat(),
192:             "status": "en_reglement", "settlement_pending": True,
193:             "mtm": mtm, "ic95": [mtm, mtm], "prob_gt100": float(mtm > 1.0),
194:             "fugit": remaining, "T_elapsed": round(elapsed, 4),
195:             "T_remaining": 0.0, "payment_date": payment.isoformat(),
196:             "settlement_amount": amount,
197:             "settled_cash_flows": [],
198:             "unsettled_cash_flows": [{
199:                 "cf": amount, "payment_date": payment.isoformat(),
200:                 "pv": mtm,
201:             }],
202:             "realized_cash_flows": [], "realized_total": 0.0,
203:             "settled_total": 0.0, "unsettled_total": amount,
204:             "unsettled_pv": mtm, "best_case": None,
205:             "n_paths": 0, "elapsed_ms": 0.0,
206:             "market_used": {
207:                 "source": "known_settlement",
208:                 "model": "deterministic_cashflow",
209:                 "r": round(r_frac * 100.0, 4),
210:                 "funding_spread": round(funding_spread * 100.0, 6),
211:                 "funding_source_reference": body.funding_source_reference,
212:                 "funding_curve": [[round(t, 6), round(s * 100.0, 6)]
213:                                   for t, s in funding_curve],
214:                 "data": {
215:                     "provider": market_provider,
216:                     "price_type": "KNOWN_CASHFLOW",
217:                     "requested_asof": today.isoformat(),
218:                 },
219:             },
220:         }
221:         return payload, {
222:             "settlement_claim": True, "fixed_price": mtm,
223:             "claim_inputs": {"amount": amount, "payment_date": payment.isoformat(),
224:                              "valuation_date": today.isoformat(), "r": r_frac,
225:                              "yield_curve": yield_curve, "funding_curve": funding_curve,
226:                              "funding_spread": funding_spread},
227:             "tickers": [], "payment_date": payment.isoformat(),
```

## Identité du moteur

`backend/app/core/valuation_runs.py:17` à 61 ; SHA-256 `909f77c87c9bcd09c00ebef711e4a0f6ecca47cc582000788a742a217dfa3a67`.

```text
17: _ENGINE_FILES = (
18:     "payscript/engine.py", "payscript/bridge.py", "payscript/parser.py", "payscript/bindings.py", "payscript/schedule_model.py", "schedule.py", "valuation_context.py",
19:     "deal_valuation.py", "inlife_valuation.py", "smile_calibration.py", "volatility_surface.py",
20:     "compute/pricers/var_scenario.py", "product/calendar.py", "calendars.py", "payscript/simulation.py",
21: )
22: 
23: 
24: def _repository_root() -> Path:
25:     return Path(__file__).resolve().parents[3]
26: 
27: 
28: def engine_identity() -> tuple[str, str]:
29:     root = _repository_root()
30:     git_dir = root / ".git"
31:     version = os.getenv("STRUCTURA_ENGINE_VERSION", "unknown")
32:     try:
33:         head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
34:         if head.startswith("ref: "):
35:             ref = head[5:]
36:             version = (git_dir / ref).read_text(encoding="utf-8").strip()
37:         elif head:
38:             version = head
39:     except OSError:
40:         pass
41:     digest = hashlib.sha256()
42:     for relative in _ENGINE_FILES:
43:         path = Path(__file__).parent / relative
44:         digest.update(relative.encode("utf-8"))
45:         digest.update(path.read_bytes())
46:     return version, digest.hexdigest()
47: 
48: 
49: def calculation_identity() -> dict:
50:     """Identity of the implementation and numerical conventions, never a backfill."""
51:     import platform
52:     import numpy
53:     import scipy
54:     version, fingerprint = engine_identity()
55:     return {"schema_version": 1, "engine_version": version,
56:             "engine_fingerprint": fingerprint, "compiler": "payscript",
57:             "conventions_version": "valuation-context-v1/calendar-v2/act365.25",
58:             "python": platform.python_version(), "numpy": numpy.__version__,
59:             "scipy": scipy.__version__}
60: 
61: 
```

## Cash contractuel

`backend/app/core/valuation_attribution.py:1` à 47 ; SHA-256 `e9f7de2ec1a38cef51121b578ea0a05a9d85b436ce8958950fc388c88964c08f`.

```text
1: """Shared factor boundaries and contractual cash conventions for valuation explain."""
2: from copy import deepcopy
3: from datetime import date
4: import math
5: 
6: ATTRIBUTION_VERSION = 'pnl-payment-v2'
7: CASH_BASIS = 'CONTRACTUAL_PAYMENT_DATE'
8: DIVIDEND_FIELDS = ('q', 'dividend_curve', 'dividend_decay')
9: 
10: 
11: def with_dividend_inputs(base: list[dict], target: list[dict]) -> list[dict]:
12:     """Change dividend inputs only, keeping diffusion, FX and identity intact."""
13:     if len(base) != len(target):
14:         raise ValueError('Univers de sous-jacents incompatible pour l’attribution des dividendes.')
15:     result = deepcopy(base)
16:     for old, new in zip(result, target):
17:         for key in DIVIDEND_FIELDS:
18:             if key in new:
19:                 old[key] = deepcopy(new[key])
20:             else:
21:                 old.pop(key, None)
22:     return result
23: 
24: 
25: def contractual_cash_in_period(payload: dict, start: date, end: date) -> list[dict]:
26:     """Contractual cash in (start, end]; never infer a payment from observation.
27: 
28:     These dated entitlements do not prove a bank transfer. Equal PAY legs remain
29:     distinct; deduplicating by amount/date/label would erase legitimate cash.
30:     """
31:     rows = payload.get('settled_cash_flows')
32:     if rows is None:
33:         raise ValueError('Flux contractuels à échéance absents : P&L cash indisponible.')
34:     result = []
35:     for row in rows:
36:         try:
37:             payment = date.fromisoformat(row['payment_date'])
38:             amount = float(row['cf'])
39:         except (KeyError, TypeError, ValueError) as exc:
40:             raise ValueError('Date de paiement ou montant absent/invalide : P&L cash indisponible.') from exc
41:         if not math.isfinite(amount):
42:             raise ValueError('Montant de cash non fini : P&L indisponible.')
43:         if start < payment <= end:
44:             cash = deepcopy(row)
45:             cash['cf'] = amount
46:             result.append(cash)
47:     return result
```

## CVA et EPE

`backend/app/core/ccr/exposure.py:86` à 137 ; SHA-256 `840ada371e0492c8d585283d4a59f95a1cd757850182b171e80b3369e3985c45`.

```text
86: def cva(times, ee, discount_rate, profile: CreditProfile | None, spread_multiplier=1.):
87:     if profile is None or profile.recovery is None:
88:         return None, "Recouvrement / LGD inconnu"
89:     if profile.pd_measure != "RISK_NEUTRAL":
90:         return None, "CVA marchande indisponible : PD non qualifiée risk-neutral"
91:     if not profile.pd_curve and not profile.spread_curve:
92:         return None, "Courbe de crédit inconnue"
93:     curve = profile.pd_curve or profile.spread_curve
94:     if times[-1] > curve[-1][0] + 1e-8:
95:         return None, "Courbe de crédit trop courte : aucune extrapolation implicite"
96:     if profile.pd_curve:
97:         pd = np.interp(times, [0] + [p[0] for p in curve], [0] + [p[1] for p in curve])
98:         pd = 1 - (1 - pd) ** spread_multiplier
99:     else:
100:         # Explicit simple flat-in-bucket hazard approximation, not CDS bootstrap.
101:         hazard = [p[1] * spread_multiplier / (1 - profile.recovery) for p in curve]
102:         cumulative = []
103:         for t in times:
104:             prev, integrated = 0., 0.
105:             for (end, _), h in zip(curve, hazard):
106:                 integrated += max(0., min(t, end) - prev) * h
107:                 prev = end
108:             cumulative.append(1 - math.exp(-integrated))
109:         pd = np.array(cumulative)
110:     # Exposure at a payment date is ex-payment. Integrating that zero over the
111:     # preceding interval deletes a real claim. Hold discounted EE from the
112:     # left endpoint until the next boundary; deterministic receivables then
113:     # integrate exactly, including a payment inside the first week.
114:     loss = (1 - profile.recovery) * np.sum(np.exp(-discount_rate * np.array(times[:-1])) * ee[:-1] * np.diff(pd))
115:     return float(loss), None
116: 
117: 
118: def summarize(exposures, uncollateralised, times, rate, profile, spread_multiplier=1.):
119:     ee = exposures.mean(axis=1)
120:     p95, p99 = np.quantile(exposures, [0.95, 0.99], axis=1, method="linear")
121:     uncoll = uncollateralised.mean(axis=1)
122:     adjustment, reason = cva(times, ee, rate, profile, spread_multiplier)
123:     # Same ex-payment convention as CVA: do not average a post-payment zero
124:     # backwards over the interval during which the claim is still outstanding.
125:     epe = float(np.sum(ee[:-1] * np.diff(times)) / times[-1])
126:     maximum = int(np.argmax(p95))
127:     return {
128:         "current_exposure": float(ee[0]), "ee": epe, "epe": epe,
129:         "pfe95": float(p95.max()), "pfe99": float(p99.max()),
130:         "maximum_pfe": float(p95[maximum]), "maximum_pfe_t": float(times[maximum]),
131:         "cva": adjustment, "cva_missing_reason": reason,
132:         "ead": None, "stressed_exposure": None,
133:         "profile": [{"t": float(t), "ee": float(e), "pfe95": float(p), "pfe99": float(q),
134:                      "uncollateralised_ee": float(u)} for t, e, p, q, u in zip(times, ee, p95, p99, uncoll)],
135:     }
136: 
137: 
```

## CCR non réglementaire

`backend/app/core/ccr/service.py:626` à 653 ; SHA-256 `e7c87c2f4417f4de4622295d5f6ebd8e6ebbe17fd2f10233256562294e7d6be1`.

```text
626:     result = {"methodology": "NESTED_MONTE_CARLO_GBM" if full else (
627:                   "NESTED_MONTE_CARLO_INCOMPLETE" if request.mode == "FULL" else "FAST_CURRENT_EXPOSURE_ONLY"),
628:             "counterparty_id": request.counterparty_id,
629:             "data_scope": request.data_scope, "uat_batch_id": request.uat_batch_id,
630:             "is_test": request.data_scope == "UAT",
631:             "requested_mode": request.mode,
632:             "status": "MISSING_DATA" if errors else "CALCULATED", "errors": sorted(set(errors)),
633:             "credit_data_status": "MISSING_DATA" if request.counterparty_id and (profile is None or profile.recovery is None or profile.has_isda is None or profile.has_csa is None) else "AVAILABLE",
634:             "warnings": warnings + (["PFE99 : échantillon faible (< 1 000 scénarios)"] if request.n_outer < 1000 and full else []),
635:             "currency": request.currency, "as_of_date": str(request.as_of_date), "before": before, "after": after,
636:             "standalone": standalone, "incremental": incremental,
637:             "netting_benefit": (standalone["pfe95"] - incremental["pfe95"] if standalone and standalone.get("pfe95") is not None
638:                                 and incremental["pfe95"] is not None else None),
639:             "deals": deals, "limits": checks, "decision": decision(checks),
640:             "regulatory": {"status": "NOT_APPLICABLE", "ead": None,
641:                            "reason": "SA-CCR non implémenté ; le PFE économique n'est jamais utilisé comme add-on réglementaire"},
642:             "credit_profile": profile.model_dump(mode="json") if profile else None,
643:             "assumptions": {"measure": "RISK_NEUTRAL", "wwr": "INDEPENDENCE",
644:               "seed": request.seed, "n_outer": request.n_outer, "n_inner": request.n_inner,
645:               "requested_dates": request.n_dates, "mtm_paths": request.mtm_paths if request.prepare_mtm else None,
646:               "common_rate": request.common_rate, "common_rate_source": request.common_rate_source,
647:               "market_overrides": {k:v.model_dump() for k,v in request.market_overrides.items()},
648:               "correlations": request.correlations, "allow_market_fetch": request.allow_market_fetch,
649:               "quantile": "linear", "pfe_limit_metric": "maximum over horizons",
650:               "time_grid": "exact payments for fixed claims; weekly for optional exposure (bounded domain)",
651:               "cva_integration": "left endpoint discounted EE, ex-payment boundaries", "spread_to_hazard": "spread / LGD, piecewise constant; no CDS bootstrap",
652:               "collateral": "lagged margin calls on valuation grid; no interpolation", "source": "frozen valuations / explicit pricer inputs"}}
653:     if not inputs.get("stress_pass") and (original_request.stress or original_request.credit_spread_multiplier != 1):
```

## VaR et ES

`backend/app/core/var_engine.py:383` à 437 ; SHA-256 `a923544ccc49025df0dc0fc0ae3340f1d7c59d56804eb9ffd0498a90d41f06f3`.

```text
383: def aggregate_var(deltas_eur: list[float], confidence: float = 0.95) -> dict:
384:     """deltas_eur: one entry per scenario — the WHOLE BOOK's ΔMtM (EUR) under
385:     that scenario (already summed across every deal). VaR/ES are read on the
386:     LOSS side (negative deltas), reported as positive numbers (a loss of
387:     480k€ is reported as var_eur=480000, not -480000) — the desk convention."""
388:     if not deltas_eur:
389:         return {"var_eur": None, "es_eur": None, "n_scenarios": 0, "distribution_summary": {}}
390:     arr = np.array(sorted(deltas_eur))   # ascending: worst losses first
391:     n = len(arr)
392:     alpha = 1.0 - confidence
393:     # The loss tail holds alpha*n scenarios — not floor(alpha*n)+1, which is
394:     # what averaging arr[:cut+1] used to do. That extra, less-bad scenario
395:     # diluted the tail: on 100 scenarios at 95% it averaged the 6 worst instead
396:     # of the 5 worst, so the reported Expected Shortfall was systematically
397:     # softer than the measure it claimed to be. The effect grows as the
398:     # scenario count falls, which is exactly when a risk figure is read most
399:     # literally.
400:     #
401:     # w is the (generally fractional) tail size, m the whole scenarios strictly
402:     # inside it. ES follows the coherent definition ES = (1/alpha)*integral of
403:     # VaR over [0, alpha], which on an empirical distribution weights the
404:     # boundary scenario by the fractional remainder. VaR is the boundary of
405:     # that same tail, so ES >= VaR holds by construction and both figures come
406:     # from one definition rather than two.
407:     w = alpha * n
408:     m = max(0, min(n, int(math.floor(w + 1e-9))))
409:     k = max(1, min(n, int(math.ceil(w - 1e-9))))
410:     var_value = -arr[k - 1]
411:     if m >= 1:
412:         tail_sum = float(arr[:m].sum())
413:         if m < n:
414:             tail_sum += (w - m) * float(arr[m])
415:         es_value = -tail_sum / w
416:     else:
417:         # Tail thinner than a single scenario: the worst one is all we know.
418:         es_value = -float(arr[0])
419: 
420:     def pctl(p: float) -> float:
421:         """Empirical quantile, inverse-CDF convention: the worst scenario that
422:         was actually observed at or below level p — arr[ceil(p*n) - 1].
423: 
424:         This used to be np.percentile, which interpolates linearly between the
425:         two neighbouring scenarios. Both estimate the same quantile of the same
426:         sample, so the payload carried two different answers to one question:
427:         on 100 scenarios of 1..100 EUR of loss, var_eur read 96.00 while p5 read
428:         -95.05. Nothing on screen said which was the 5% quantile, and a reader
429:         comparing the tile to the chart had no way to reconcile them.
430: 
431:         The VaR convention wins because it is the one a risk figure should use:
432:         no value is invented between scenarios that were run, and the number
433:         reported is a loss that actually occurred in the simulation. It also
434:         makes the relation exact and checkable — var_eur == -p5 whenever the
435:         confidence level is 95%, by construction rather than by luck."""
436:         idx = int(math.ceil(p / 100.0 * n - 1e-9)) - 1
437:         return float(arr[max(0, min(n - 1, idx))])
```

## Solveur général

`backend/app/core/payscript/simulation.py:74` à 135 ; SHA-256 `86ddc7d1898739ec7dfb3e269562cbc0ec2c58471e455f7eaa7c9b2fe353458e`.

```text
74:                      param_name: str, target_price: float, lo: float, hi: float,
75:                      N: int = DEFAULT_SOLVER_N, tol: float = 1e-4, max_iter: int = 40,
76:                      yield_curve=None, sigma_r: float = 0.0, a_r: float = 0.0,
77:                      barrier_monitoring: str = "weekly",
78:                      state: dict | None = None, funding_curve=None,
79:                      funding_spread: float = 0.0, valuation_context=None) -> dict:
80:     """Bisection root-find: find param_value in [lo, hi] such that
81:     price(param_value) == target_price.
82: 
83:     Bisection requires price(lo) and price(hi) to bracket target_price — true for
84:     the common monotonic cases (e.g. higher COUPON -> higher price). If the bracket
85:     doesn't hold, the closest endpoint is returned with converged=False rather than
86:     raising, so the caller can inspect the trace and adjust [lo, hi].
87:     """
88:     def f(x: float) -> float:
89:         return _price_with_params(script, underlyings, corr_matrix, r, T, N, model, seed,
90:                                    base_user_params, {param_name: x},
91:                                    yield_curve=yield_curve, sigma_r=sigma_r, a_r=a_r,
92:                                    barrier_monitoring=barrier_monitoring, state=state,
93:                                    funding_curve=funding_curve, funding_spread=funding_spread,
94:                                    valuation_context=valuation_context) - target_price
95: 
96:     f_lo, f_hi = f(lo), f(hi)
97:     trace = [{"iter": 0, "x": lo, "price": f_lo + target_price},
98:               {"iter": 0, "x": hi, "price": f_hi + target_price}]
99: 
100:     if abs(f_lo) < tol:
101:         return _solver_result(param_name, lo, f_lo + target_price, target_price, 0, trace, True)
102:     if abs(f_hi) < tol:
103:         return _solver_result(param_name, hi, f_hi + target_price, target_price, 0, trace, True)
104:     if (f_lo > 0) == (f_hi > 0):
105:         best_x, best_f = (lo, f_lo) if abs(f_lo) < abs(f_hi) else (hi, f_hi)
106:         return _solver_result(
107:             param_name, best_x, best_f + target_price, target_price, 0, trace, False,
108:             "Le prix cible n'est pas compris entre les prix aux bornes lo/hi — "
109:             "élargissez l'intervalle de recherche.")
110: 
111:     a, b, fa = lo, hi, f_lo
112:     x_mid, f_mid = a, fa
113:     for i in range(1, max_iter + 1):
114:         x_mid = (a + b) / 2
115:         f_mid = f(x_mid)
116:         trace.append({"iter": i, "x": x_mid, "price": f_mid + target_price})
117:         if abs(f_mid) < tol or (b - a) / 2 < tol:
118:             return _solver_result(param_name, x_mid, f_mid + target_price, target_price, i, trace, True)
119:         if (f_mid > 0) == (fa > 0):
120:             a, fa = x_mid, f_mid
121:         else:
122:             b = x_mid
123: 
124:     return _solver_result(
125:         param_name, x_mid, f_mid + target_price, target_price, max_iter, trace, False,
126:         "Nombre maximal d'itérations atteint sans convergence sous la tolérance.")
127: 
128: 
129: # ── Grid: 2D price heatmap over two PARAMs ──────────────────────────
130: 
131: def compute_price_grid(script: CompiledScript, underlyings, corr_matrix, r: float, T: float,
132:                         model: str, seed: int, base_user_params: dict,
133:                         param_x: str, x_min: float, x_max: float, x_steps: int,
134:                         param_y: str, y_min: float, y_max: float, y_steps: int,
135:                         N: int = DEFAULT_GRID_N,
```

## Allowlist Optimizer

`backend/app/core/product_optimizer/capabilities.py:1` à 38 ; SHA-256 `33b270503dd65d65e46807def28908f3074f49a2be53cff71f166e60d55fa730`.

```text
1: """An explicit allow-list, not a reflection of every model in the engine."""
2: from .contracts import MAX_CANDIDATES, MAX_SECONDS, MAX_WORK, MAX_PARALLEL_WORKERS
3: from .families import ADAPTERS, family_schema
4: 
5: 
6: def capabilities():
7:     families = []
8:     for key in ADAPTERS:
9:         try:
10:             families.append(family_schema(key))
11:         except ValueError as error:
12:             families.append(dict(product_family=key, status="UNSUPPORTED", label=key, reason=str(error)))
13:     return {
14:         "schema_version": 1,
15:         "families": families,
16:         "objectives": ["maximize_coupon", "maximize_protection", "target_coupon", "maximize_participation", "maximize_cap"],
17:         "available_analytics": ["fair_value", "price_ic95", "probability_loss", "probability_autocall", "expected_maturity"],
18:         "unavailable_analytics": ["physical_probability", "expected_return", "VaR", "ES", "continuous_barrier_breach", "greeks"],
19:         "limitations": [
20:             "Probabilités risque-neutres sous GBM, pas des prévisions ni une recommandation personnalisée.",
21:             "Marché historique chargé par panier et date ; volatilités réalisées utilisées comme hypothèses GBM, dividendes historiques à confirmer, taux et funding manuels. Références et overrides figés au lancement.",
22:             "Même devise pour les actifs et le règlement ; aucun smile, FX/quanto ou modèle de défaut émetteur. Funding appliqué à l'actualisation seule.",
23:             "Budget du payoff = prix d'émission moins frais et marge initiaux en fractions du nominal ; perte investisseur mesurée sur le prix d'émission brut.",
24:             "Barrière européenne. Grille Monte-Carlo hebdomadaire : observations approchées, paiements contractuels actualisés.",
25:             "Coupon, participation ou cap résolu selon le script ; coupon annuel nominal sauf gear put à coupon unique, hors défaut émetteur.",
26:             "Le rappel à maturité est exclu de la probabilité de remboursement anticipé.",
27:             "Exploration à graine 42, puis sélection figée de cinq candidats au maximum : paramètres résolus conservés, validation indépendante à N et 2N paires.",
28:             "Bonferroni sur la sélection : prix et compatibilité N/2N par approximation normale ; probabilités et durée par bornes empiriques de Bernstein.",
29:             "Parcours sauvegardé : demande et résultats conservés côté serveur ; la navigation ne les efface pas. Une reprise crée un nouveau calcul lié ; l'export JSON conserve une copie du dossier.",
30:             "Budget temps contrôlé pendant la recherche ; en séquentiel, un calcul engagé peut finir au-delà du budget. Tout dépassement est signalé avec une couverture partielle.",
31:             "Recommandation limitée aux candidats confirmés de la sélection ; compatibilité Monte-Carlo, sans certification du classement ni convergence temporelle automatique.",
32:         ],
33:         "limits": {"max_candidates": MAX_CANDIDATES, "max_seconds": 3600, "default_seconds":MAX_SECONDS,
34:                    "advisory_work_units": MAX_WORK, "max_simulations": 20000,
35:                    "max_parallel_workers": MAX_PARALLEL_WORKERS},
36:         "execution": "Calculs directs ; 2 candidats simultanés par défaut, nombre réduit selon CPU/mémoire ; aucun ratio entre modèles.",
37:         "model_resolution": "auto → constant (GBM), seule configuration qualifiée ; aucun repli après erreur",
38:     }
```

## KID : arguments MC

`backend/app/api/kid.py:76` à 109 ; SHA-256 `2510271c71c786ed2f60d2b8c9d665ee8469619d72d6fcc51efe45382053fb73`.

```text
76:       no reinvestment — a KID does not assume the client does anything with
77:       the money afterwards, and neither does this.
78:     - the RETURN is the internal rate of return of those flows AT THEIR
79:       DATES, which is what Excel's XIRR computes. Redeemed at year 1 paying
80:       8% gives 8%, whatever nominal horizon the row is labelled with.
81: 
82:     That denominator is the whole bug. `(amount/notional)^(1/T_h) - 1` spread
83:     an 8% one-year coupon over the five-year RHP and reported 1.55% a year.
84:     A scenario's return is annualised over the life THAT scenario had, not
85:     over the label at the top of the column."""
86:     T_eff = min(effective_T_max(compiled, T_run), T_cap)
87:     res = run_mc(
88:         script=compiled, underlyings=uls, corr_matrix=corr, r=r,
89:         T_max=T_eff, N=N, model=model, seed=seed, antithetic=antithetic,
90:         user_params=user_params, yield_curve=yield_curve or [],
91:         sigma_r=sigma_r, a_r=a_r, per_path_flows=True,
92:     )
93:     flows = res["path_flows"]
94:     px = np.array([sum(v for _t, v in fl) for fl in flows], dtype=np.float64)
95: 
96:     # Floor near-zero payoffs (surviving paths at intermediate horizon)
97:     if floor_price > 0.01:
98:         px = np.where(px < 0.01, floor_price, px)
99: 
100:     return _percentile_rows(px, flows, res["price"], T_eff)
101: 
102: 
103: def _percentile_rows(amounts, flows, pv, t_eff) -> dict:
104:     """Pick the scenario sitting at each PRIIPs percentile and report ITS
105:     amount and ITS return.
106: 
107:     Reading the percentile of the amounts and the percentile of the returns
108:     separately would pair one scenario's payout with another scenario's
109:     holding period, which is how a table ends up internally impossible. So
```

## KID : héritage et paramètres

`backend/app/api/kid.py:293` à 304 ; SHA-256 `2510271c71c786ed2f60d2b8c9d665ee8469619d72d6fcc51efe45382053fb73`.

```text
293: class KidRequest(PricingRequest):
294:     product_id: Optional[int] = None
295:     product_terms_version: Optional[int] = None
296:     crm: int = Field(default=3, ge=1, le=6)
297:     initial_price_pct: float = Field(default=100.0, gt=0.0, le=1000.0)
298:     cost_entry: float = Field(default=0.0, ge=0, le=10)    # % one-shot
299:     cost_exit: float = Field(default=0.0, ge=0, le=10)     # % one-shot
300:     cost_ongoing: float = Field(default=0.0, ge=0, le=5)   # % per year
301: 
302: 
303: # ── Endpoint ──────────────────────────────────────────────────────────
304: 
```

## KID : orchestration et VEV

`backend/app/api/kid.py:339` à 407 ; SHA-256 `2510271c71c786ed2f60d2b8c9d665ee8469619d72d6fcc51efe45382053fb73`.

```text
339:     n = len(uls)
340:     if len(corr) != n or any(len(row) != n for row in corr):
341:         raise HTTPException(422, "Matrice de corrélation invalide.")
342: 
343:     T_full = req.T
344:     T_half = T_full / 2.0
345:     T_1y   = min(1.0, T_full)
346: 
347:     common = dict(
348:         compiled=compiled, uls=uls, corr=corr, r=req.r,
349:         T_run=T_full, N=req.N, model=req.model, seed=req.seed,
350:         antithetic=req.antithetic, user_params=req.user_params,
351:         yield_curve=req.yield_curve or [], sigma_r=req.sigma_r, a_r=req.a_r,
352:     )
353: 
354:     try:
355:         # Step 1 — recommended holding period: the contract runs to term.
356:         sc_full = _mc_percentiles(**common, T_cap=T_full, floor_price=0.0)
357: 
358:         # Step 2 — intermediate horizons, valued as a LIVING product (nested
359:         # replay, see _horizon_percentiles) rather than a truncated maturity.
360:         # They are only computed when they are actually displayed below.
361:         sc_half = sc_1y = None
362:         with ThreadPoolExecutor(max_workers=2) as ex:
363:             fut_half = (ex.submit(_horizon_percentiles, **common, T_cap=T_half)
364:                         if T_full > 0.5 else None)
365:             fut_1y = (ex.submit(_horizon_percentiles, **common, T_cap=T_1y)
366:                       if T_full > 1.0 else None)
367:             if fut_half is not None:
368:                 sc_half = fut_half.result()
369:             if fut_1y is not None:
370:                 sc_1y = fut_1y.result()
371:     except ValueError as e:
372:         raise HTTPException(422, str(e))
373: 
374:     # VEV from the 1st-percentile OUTCOME at the RHP (PRIIPs Annex II).
375:     # PayScript outcomes are per unit of contractual notional.  Convert that
376:     # outcome to a factor of the actual purchase price: at par this is a no-op;
377:     # a call bought for 12 is measured against 0.12, not against 1.00.
378:     # (The VEV formula itself remains the module's own approximation rather
379:     # than the RTS expression; that non-conformity is tracked separately.)
380:     p1 = sc_full["p1"] / (req.initial_price_pct / 100.0)
381:     if p1 > 0.0 and p1 < 1.0:
382:         vev = math.sqrt(-2.0 * math.log(p1) / T_full)
383:         mrm = _mrm_from_vev(vev)
384:     elif p1 >= 1.0:
385:         # The 1st percentile still repays par: no downside worth measuring.
386:         vev, mrm = 0.0, 1
387:     else:
388:         # p1 <= 0 — at least 1% of scenarios wipe the investment out. The log
389:         # is undefined, and a single `else: vev = 0.0` used to route this into
390:         # the LOWEST risk class: a product that can lose everything came out at
391:         # MRM 1, i.e. safer than a government bond. A total loss is by
392:         # construction the top of the scale. The VEV itself has no finite value
393:         # here and is reported as absent rather than as a number.
394:         vev, mrm = None, 7
395: 
396:     sri = _sri(mrm, req.crm)
397: 
398:     # Build horizons list (ascending T)
399:     cost = (req.cost_entry, req.cost_exit, req.cost_ongoing, req.initial_price_pct)
400:     horizons = []
401:     if sc_1y is not None:
402:         horizons.append(_scenario_row(sc_1y,   T_1y,   *cost))
403:     if sc_half is not None:
404:         horizons.append(_scenario_row(sc_half, T_half, *cost))
405:     horizons.append(_scenario_row(sc_full, T_full, *cost))
406: 
407:     return {
```

## KID : avertissement UI

`frontend/src/components/KidPanel.vue:65` à 79 ; SHA-256 `ac1edb41e4b17f46da47f9c409ed6422ade21922b31deeaa2ef8504a7da31734`.

```text
65:       <!-- ── SRI ───────────────────────────────────────────── -->
66:       <div v-if="kid" class="mb-4 rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2
67:                              text-[11px] leading-relaxed text-amber-200/90">
68:         <span class="font-bold">Document indicatif — méthodologie non conforme PRIIPs.</span>
69:         Les scénarios de performance sont tirés d'une simulation risque-neutre, alors que le
70:         règlement impose pour la Catégorie 3 une distribution historique ; la formule de VEV
71:         et les horizons intermédiaires ne suivent pas non plus les prescriptions des RTS.
72:         À usage d'analyse interne uniquement — ne pas diffuser comme KID réglementaire.
73:       </div>
74:       <div v-if="kid" class="card">
75:         <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">
76:           Indicateur Synthétique de Risque (SRI)
77:           <HelpTip width="w-72" text="Échelle réglementaire PRIIPs de 1 (risque le plus faible) à 7 (le plus élevé), combinant le risque de marché (MRM, dérivé de la VEV du produit) et le risque de crédit de l'émetteur (CRM) via une table de correspondance fixée par le règlement." />
78:         </h3>
79:         <div class="flex items-center gap-6">
```

## EMT : détection

`backend/app/api/emt.py:77` à 111 ; SHA-256 `f6cf3de8d0ad0c5458fbac73c033da11f2f264b7c44da25e9d2298e5e18e03f9`.

```text
77: 
78:     def values(param):
79:         value = effective.get(param.name, param.stored_val)
80:         return value if isinstance(value, list) else [value]
81: 
82:     has_leverage = any(
83:         p.name in _LEVERAGE_NAMES and p.is_pct
84:         and any(isinstance(value, (int, float)) and value > 1.0
85:                 for value in values(p))
86:         for p in compiled.params
87:     )
88:     has_barrier = any(
89:         ('BAR' in p.name or p.name.startswith('KI') or p.name.startswith('KO'))
90:         for p in compiled.params
91:     )
92:     # A multi-asset average and a worst-of are different risks.  Read the
93:     # observable actually used by the payoff rather than guessing from the
94:     # number of underlyings.
95:     has_worst_of = bool(re.search(r"\bWOF(?:_MIN)?\b", source))
96:     is_multi_asset = n_underlyings > 1
97:     has_autocall = compiled.has_stop
98: 
99:     return {
100:         "has_leverage": has_leverage,
101:         "has_barrier": has_barrier,
102:         "has_worst_of": has_worst_of,
103:         "is_multi_asset": is_multi_asset,
104:         "has_autocall": has_autocall,
105:         "n_underlyings": n_underlyings,
106:         "complexity_score": sum([has_leverage, has_barrier, has_worst_of, has_autocall]),
107:     }
108: 
109: 
110: def _capital_tier(level_pct: float | None, condition: str) -> dict:
111:     """Classify only an explicit, unconditional contractual protection."""
```

## Upload documentaire

`backend/app/api/documents.py:133` à 159 ; SHA-256 `97fe06e7e7e6469e322cf0f7cddbf88d000be8d4a9c280b63e0d2b7e3669f9f1`.

```text
133:     except json.JSONDecodeError as exc:
134:         raise HTTPException(422, "Les métadonnées du document ne sont pas un JSON valide.") from exc
135:     if not isinstance(metadata, dict):
136:         raise HTTPException(422, "Les métadonnées du document doivent former un objet JSON.")
137: 
138:     # Sanitize filename
139:     ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
140:     original_name = Path(file.filename or "document").name
141:     safe_name = f"{ts}_{uuid4().hex}_{original_name}"
142:     dest = user_dir / safe_name
143:     dest.write_bytes(await file.read())
144: 
145:     doc = Document(
146:         user_id=current.id,
147:         deal_id=deal_id,
148:         product_id=product_id,
149:         product_terms_version=product.terms_version if product else None,
150:         doc_type=doc_type,
151:         title=title,
152:         filename=safe_name,
153:         file_path=str(dest.relative_to(_DOCS_DIR)),
154:         metadata_json=json.dumps(metadata, ensure_ascii=False, sort_keys=True),
155:     )
156:     try:
157:         session.add(doc)
158:         session.flush()
159:         if product is not None:
```

## Sessions frontend

`frontend/src/utils/session.js:1` à 52 ; SHA-256 `4c29ca4e08f6bc2363f1961ea06e7c0ea45ed2aaf2271ab8c99b6b272a4f029f`.

```text
1: // Browser sessions belong to a tab. Never import the former shared token.
2: export function sessionToken() { return sessionStorage.getItem('auth_token') }
3: export function sessionInstallation() {
4:   try { return JSON.parse(sessionStorage.getItem('auth_installation') || 'null') } catch { return null }
5: }
6: export function installationUrl(installation) {
7:   if (!installation) return ''
8:   if (!/^http:\/\/127\.0\.0\.1:\d{4,5}$/.test(installation.url || '')) throw new Error('Adresse d’installation invalide.')
9:   return installation.url
10: }
11: export function sessionUrl(path) { return installationUrl(sessionInstallation()) + path }
12: export function portalFetch(path, options = {}) {
13:   if (!String(path).startsWith('/api/platform/')) throw new Error('Chemin du portail invalide.')
14:   return fetch(path, options)
15: }
16: let epoch = 0
17: const pending = new Set()
18: export function cancelSessionRequests() {
19:   epoch++
20:   for (const controller of pending) controller.abort()
21:   pending.clear()
22: }
23: export async function sessionFetch(path, options = {}) {
24:   if (!String(path).startsWith('/api/') && path !== '/health') throw new Error('Chemin API invalide.')
25:   const version = epoch, controller = new AbortController()
26:   pending.add(controller)
27:   const abort = () => controller.abort()
28:   options.signal?.addEventListener('abort', abort, { once: true })
29:   if (options.signal?.aborted) controller.abort()
30:   try {
31:     const response = await fetch(sessionUrl(path), { ...options, signal: controller.signal })
32:     if (version !== epoch) throw new DOMException('Le contexte a changé.', 'AbortError')
33:     return response
34:   } finally {
35:     pending.delete(controller)
36:     options.signal?.removeEventListener('abort', abort)
37:   }
38: }
39: export function saveSession(token, installation) {
40:   cancelSessionRequests()
41:   sessionStorage.setItem('auth_token', token)
42:   if (installation) sessionStorage.setItem('auth_installation', JSON.stringify(installation))
43:   else sessionStorage.removeItem('auth_installation')
44:   localStorage.removeItem('auth_token')
45: }
46: export function clearSession() {
47:   cancelSessionRequests()
48:   sessionStorage.removeItem('auth_token')
49:   sessionStorage.removeItem('auth_installation')
50:   sessionStorage.removeItem('development_admin_token')
51:   localStorage.removeItem('auth_token')
52: }
```

## Cadence CRM

`backend/app/core/client_cycle.py:167` à 224 ; SHA-256 `3c52d7f630b3bb09aedf652da6c33ba847c4fb38365acd2baa210bb18e3ea0ba`.

```text
167: def compute_cycle(trade_dates: Sequence[date], *,
168:                   asof: Optional[date] = None) -> Cycle:
169:     """Cadence observée à partir de dates de transaction.
170: 
171:     `asof` sert au calcul du retard et des fenêtres ; il se passe explicitement
172:     pour que les tests ne dépendent pas du jour où ils tournent.
173:     """
174:     asof = asof or date.today()
175:     brutes = [d for d in trade_dates if d is not None and d <= asof]
176:     # Les intervalles se comptent sur des JOURNÉES, pas sur des lignes : trois
177:     # allocations le même jour ne font pas trois épisodes d'investissement.
178:     dates = sorted(set(brutes))
179: 
180:     if not dates:
181:         return Cycle(n_trades=0, n_trading_days=0,
182:                      confidence=HISTORIQUE_INSUFFISANT,
183:                      explanation=["Aucune transaction connue."])
184: 
185:     dernier = dates[-1]
186:     ecoule = (asof - dernier).days
187: 
188:     if len(dates) == 1:
189:         return Cycle(
190:             n_trades=len(brutes), n_trading_days=1,
191:             confidence=HISTORIQUE_INSUFFISANT,
192:             last_trade_date=dernier.isoformat(), days_since_last=ecoule,
193:             explanation=[
194:                 (f"{len(brutes)} transaction(s), toutes le même jour : aucun "
195:                  f"intervalle mesurable."
196:                  if len(brutes) > 1 else
197:                  "Une seule transaction connue : aucun intervalle mesurable."),
198:                 f"Dernière transaction le {dernier.isoformat()}, il y a {ecoule} jours.",
199:             ])
200: 
201:     intervalles = [float((b - a).days) for a, b in zip(dates, dates[1:])]
202:     mediane = _mediane(intervalles)
203:     moyenne = sum(intervalles) / len(intervalles)
204:     dispersion = _demi_ecart_interquartile(intervalles)
205:     # Le ratio compare l'étalement COMPLET de la moitié centrale à la médiane :
206:     # c'est lui qui décide si la cadence mérite un nom.
207:     ratio = (2 * dispersion / mediane) if mediane > 0 else 0.0
208: 
209:     # Confiance : le nombre d'observations ET leur régularité. Beaucoup de
210:     # trades très irréguliers ne valent pas mieux que peu de trades réguliers —
211:     # les deux conditions doivent tenir.
212:     if len(intervalles) >= 5 and ratio <= 0.25:
213:         confiance = CONFIANCE_HAUTE
214:     elif len(intervalles) >= 3 and ratio <= 0.50:
215:         confiance = CONFIANCE_MOYENNE
216:     else:
217:         confiance = CONFIANCE_BASSE
218: 
219:     # Largeur de la fenêtre : la dispersion observée quand elle est mesurable,
220:     # une fraction large de la médiane sinon. Jamais moins de trois jours.
221:     # Une dispersion NULLE est une mesure, pas une absence : une cadence
222:     # parfaitement régulière mérite la fenêtre la plus étroite, pas la plus
223:     # large. Seule l'impossibilité de mesurer — un intervalle unique — justifie
224:     # d'élargir par défaut.
```

## Inférence des études

`backend/app/core/amc_controls.py:75` à 85 ; SHA-256 `51f2400b82d4d30d54d74e49eb5887219873b5c8fbec73d0f39100e851c55354`.

```text
75: def clustered_mean_test(values: list[float], groups: list[str], null: float = 0.0) -> dict:
76:     """Test group means; repeated trades/horizons are not independent samples."""
77:     from scipy.stats import ttest_1samp
78:     means = pd.DataFrame({"value": values, "group": groups}).dropna().groupby("group")["value"].mean()
79:     n = len(means)
80:     if n < 10 or means.std() <= 1e-12:
81:         return {"tstat": 0.0, "pvalue": 1.0, "n_independent_groups": n, "inference_available": False}
82:     test = ttest_1samp(means, null)
83:     return {"tstat": float(test.statistic), "pvalue": float(test.pvalue),
84:             "n_independent_groups": n, "inference_available": True}
85: 
```

## Régression factorielle

`backend/app/core/amc_engine.py:567` à 586 ; SHA-256 `f13c44ad289846506962d37efc1195b0a4d8fd761399b3ea1aa5e04374e8a438`.

```text
567: 
568:     merged["excess_ret"] = merged["amc_ret"] - merged[rf_col]
569:     if "bm_ret" in merged.columns:
570:         merged["bm_excess"] = merged["bm_ret"] - merged[rf_col]
571: 
572:     # ── 5. OLS regression ─────────────────────────────────────────────
573:     Y = merged["excess_ret"]
574:     if not np.isfinite(Y).all() or Y.std() <= 1e-12:
575:         raise ValueError("Rendements constants ou non finis : inférence factorielle indisponible")
576:     X = sm.add_constant(merged[available])
577:     if len(Y) < max(20, len(available) + 5) or np.linalg.matrix_rank(X) < X.shape[1]:
578:         raise ValueError("Observations ou rang insuffisants pour cette régression")
579:     ols = sm.OLS(Y, X).fit(cov_type="HAC", cov_kwds={"maxlags": min(5, len(Y) // 4)}, use_t=True)
580: 
581:     alpha_daily = float(ols.params.get("const", 0))
582:     alpha_ann   = alpha_daily * 252
583: 
584:     # Compute p-values directly from t-stats via scipy to avoid statsmodels
585:     # version inconsistencies where pvalues Series indexing can silently
586:     # return the default (1.0) instead of the actual p-value.
```

## Conditions du score composite

`backend/app/core/amc_managerskill.py:238` à 275 ; SHA-256 `3245a370ab63827cbb899479cc56778c52678cb2a9f1e77ccd33f21065e09f57`.

```text
238:     """
239:     vag_score_val, vag_ann_raw = _vag_score(study_result, vag_result)
240:     raw_scores: dict[str, Optional[float]] = {
241:         "alpha":         _alpha_score(study_result.get("block_a")),
242:         "stock_picking": _stockpicking_score(study_result.get("block_i")),
243:         "vag":           vag_score_val,
244:         "risk_mgmt":     _riskmanagement_score(study_result.get("block_j")),
245:         "timing":        _timing_score(study_result.get("block_h")),
246:         "conviction":    _conviction_score(study_result.get("block_d")),
247:     }
248: 
249:     # Renormalize weights for available dimensions
250:     available_keys = [k for k, v in raw_scores.items() if v is not None]
251:     if not available_keys:
252:         return {
253:             "available": False,
254:             "error": "Aucun bloc disponible pour calculer le Manager Skill Score.",
255:         }
256: 
257:     total_w = sum(BASE_WEIGHTS[k] for k in available_keys)
258:     if len(available_keys) < 4 or total_w < 0.75 or study_result.get("data_quality", {}).get("status") == "review_required":
259:         return {"available": False, "score": None, "score_label": "Données insuffisantes",
260:                 "n_dimensions_available": len(available_keys), "dimension_scores": raw_scores,
261:                 "error": "Score global non publié : couverture ou qualité insuffisante (4 dimensions et 75 % des poids requis)."}
262:     norm_weights = {k: BASE_WEIGHTS[k] / total_w for k in available_keys}
263: 
264:     composite = sum(norm_weights[k] * raw_scores[k] for k in available_keys)
265:     score = max(0, min(100, round(composite)))
266:     label, color = _label_color(score)
267: 
268:     # Build dimensions list
269:     dimensions = []
270:     for k in ("alpha", "stock_picking", "vag", "risk_mgmt", "timing", "conviction"):
271:         s = raw_scores[k]
272:         eff_w = norm_weights.get(k, 0)
273:         dim: dict = {
274:             "key":                  k,
275:             "label":                _DIM_LABELS[k],
```

## Poids du score composite

`backend/app/core/amc_managerskill.py:1` à 33 ; SHA-256 `3245a370ab63827cbb899479cc56778c52678cb2a9f1e77ccd33f21065e09f57`.

```text
1: """Manager Skill Score — global aggregator of all study blocks.
2: 
3: Combines Block A (alpha FF), Block I (stock picking), Block E (Référentiel Inertiel / VAG),
4: Block J (risk management), Block H (timing), Block D (conviction)
5: into a single 0-100 composite score.
6: 
7: Base weights (renormalized if a block is unavailable):
8:   Alpha FF              30%   (Bloc A)
9:   Stock Picking         25%   (Bloc I)
10:   Référentiel / VAG     20%   (Bloc E)
11:   Risk Mgmt             15%   (Bloc J)
12:   Timing                 7%   (Bloc H)
13:   Conviction             3%   (Bloc D)
14: """
15: from __future__ import annotations
16: 
17: import math
18: from typing import Optional
19: 
20: 
21: BASE_WEIGHTS: dict[str, float] = {
22:     "alpha":         0.30,
23:     "stock_picking": 0.25,
24:     "vag":           0.20,
25:     "risk_mgmt":     0.15,
26:     "timing":        0.07,
27:     "conviction":    0.03,
28: }
29: 
30: _LABELS = [
31:     (80, "Profil descriptif très favorable", "#10b981"),
32:     (60, "Profil descriptif favorable",          "#22c55e"),
33:     (40, "Neutre",              "#f59e0b"),
```

## Prix d'exécution AMC

`backend/app/core/amc_prices.py:685` à 711 ; SHA-256 `687cee5dd5f78ab7efa3fc6001371203d331c2c4eff5782553a930cdffd12664`.

```text
685: def execution_series(isin: str, name: str, as_of: str) -> pd.Series:
686:     """Price-only history in as-of share units; never use dividend-adjusted prices for lots."""
687:     from .amc_controls import price_at
688:     try:
689:         df = load_prices(isin)
690:     except ValueError:
691:         df = pd.DataFrame()
692:     if "price_close" in df.columns:
693:         series = df["price_close"].copy()
694:         adjustment_date = pd.Timestamp(df.attrs.get("adjustment_date", as_of)).date()
695:     else:
696:         ticker = yf_symbol(isin, name)
697:         raw = yf.Ticker(ticker).history(start="2000-01-01", end=(pd.Timestamp(as_of) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), auto_adjust=False)
698:         if raw.empty:
699:             raise ValueError(f"Cours hors dividendes indisponible pour {isin}")
700:         series = raw["Close"].copy()
701:         ccy = (df.attrs.get("currency") or get_currency(isin) or "").upper()
702:         if is_gbx_ticker(ticker, ccy):
703:             series /= 100
704:         adjustment_date = pd.Timestamp.today().date()
705:     series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
706:     series = series.loc[:as_of]
707:     factor = split_factor_between(isin, name, pd.Timestamp(as_of).date(), adjustment_date)
708:     series = series * factor
709:     price_at(series, as_of)
710:     from .amc_controls import record_market
711:     return record_market(f"execution:{isin}:{as_of}", series)
```

## Financement du roll

`backend/app/core/roll_economics.py:36` à 70 ; SHA-256 `435456c019d8d7bf0d35b1a6d175b67aa4f4bed756b88c0fe27399205dfd54ee`.

```text
36: def roll_budget(model_exit: float, model_entry: float, assumptions: RollFinancing,
37:                 *, valuation_date: str | None, calculated_at: str) -> tuple[float, dict]:
38:     if not math.isfinite(model_exit) or model_exit < 0:
39:         raise ValueError('Le prix modèle de sortie doit être fini et positif ou nul.')
40:     if not math.isfinite(model_entry) or model_entry <= 0:
41:         raise ValueError('Le prix modèle de la nouvelle note doit être fini et strictement positif.')
42:     age = None
43:     if assumptions.exit_basis == 'observed_bid':
44:         gross = assumptions.bid_pct / 100
45:         if valuation_date:
46:             age = (date.fromisoformat(str(valuation_date)[:10]) - assumptions.bid_observed_at.date()).days
47:             if age < 0:
48:                 raise ValueError('Le bid est postérieur à la date de valorisation comparée.')
49:     else:
50:         gross = model_exit - assumptions.haircut_points / 100
51:     proceeds = gross - assumptions.exit_cost_points / 100
52:     entry = model_entry + assumptions.entry_cost_points / 100
53:     if proceeds < 0:
54:         raise ValueError('Le produit net de cession est négatif : le roll ne se finance pas sans apport explicite.')
55:     if not all(math.isfinite(value) for value in (gross, proceeds, entry)) or entry <= 0:
56:         raise ValueError('Les prix nets du roll doivent être finis et le prix d’entrée strictement positif.')
57:     quantity = proceeds / entry
58:     if not math.isfinite(quantity):
59:         raise ValueError('La quantité réinvestie n’est pas finie.')
60:     return quantity, {
61:         **assumptions.model_dump(mode='json'),
62:         'model_exit_price': model_exit, 'model_entry_price': model_entry,
63:         'gross_exit_price': gross, 'net_exit_proceeds': proceeds, 'entry_unit_price': entry,
64:         'bid_age_calendar_days': age, 'model_calculated_at': calculated_at,
65:         'valuation_date': valuation_date,
66:         'exit_evidence': 'OBSERVED_BID_INPUT' if assumptions.exit_basis == 'observed_bid' else 'MODEL_HYPOTHESIS',
67:         'cost_units': 'price_points', 'exit_cost_basis': 'original_nominal',
68:         'entry_cost_basis': 'new_nominal', 'recovery_basis': 'original_nominal_future_undiscounted_flows',
69:         'exit_price_convention': 'all_rights_sold_same_value_basis_as_model_before_explicit_costs',
70:     }
```

## Four eyes configurable

`backend/app/core/workflow.py:13` à 31 ; SHA-256 `467c871fbe34b23f47461081525ecac492a0094c673d1dc36bc1d2fcf5a22ffd`.

```text
13: def amendment_four_eyes_enabled() -> bool:
14:     """Whether approving and applying an amendment needs a SECOND person.
15: 
16:     Off by default. On a tactical, single-operator desk there is nobody to
17:     separate duties with, and the requirement turned the only available
18:     correction path for a booked trade (nominal, contrepartie, price_traded,
19:     payment_date) into a dead end: the maker could open a request and then
20:     nothing could ever close it.
21: 
22:     What this flag governs is deliberately narrow — the identity of the second
23:     signatory, and nothing else. The request/approve/apply state machine, the
24:     contract versioning, the stale-base-version refusals and the audit trail
25:     are unconditional, so re-arming the control is one environment variable
26:     rather than a rewrite. Read through this function (never captured into a
27:     module constant) so a deployment or a test can flip it without import-order
28:     surprises.
29:     """
30:     return os.getenv(
31:         "STRUCTURA_AMENDMENT_FOUR_EYES", "0").strip().lower() in {"1", "true", "yes", "on"}
```

## Manifeste développement

`backend/app/hybrid/config.py:12` à 49 ; SHA-256 `ef415d20e4a1866662d2bcab1452345b402f3b92e8d36e0b5da3ad4bcda0ac75`.

```text
12: class InstallationConfig(BaseModel):
13:     model_config = ConfigDict(extra="forbid", frozen=True)
14:     version: Literal[1] = 1
15:     installation_id: UUID
16:     organization_id: UUID | None = None
17:     key: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
18:     name: str
19:     kind: Literal["organization", "platform"]
20:     service: Literal["application", "simulation_controller", "portal_redirect", "admin_workbench"] = "application"
21:     environment: Literal["DEVELOPMENT"] = "DEVELOPMENT"
22:     data_dir: Path
23:     port: int = Field(ge=1024, le=65535)
24:     capabilities: tuple[Literal["request_rfq", "respond_rfq"], ...] = ()
25:     retention: Literal["UNTIL_EXPLICIT_RESET"] = "UNTIL_EXPLICIT_RESET"
26:     registry_state: Literal["NOT_CONFIGURED"] = "NOT_CONFIGURED"
27:     billing_enabled: Literal[False] = False
28: 
29:     @model_validator(mode="after")
30:     def check_scope(self):
31:         if (self.kind == "organization") != (self.organization_id is not None):
32:             raise ValueError("Le type d'installation et son organisation sont incohérents.")
33:         if self.kind == "platform" and self.capabilities:
34:             raise ValueError("Le service central ne porte aucune capacité métier privée.")
35:         if self.service != "application" and self.kind != "platform":
36:             raise ValueError("Les services de contrôle ne sont pas des installations métier.")
37:         if not self.data_dir.is_absolute():
38:             raise ValueError("Le répertoire privé doit être absolu.")
39:         return self
40: 
41:     def public_descriptor(self):
42:         return {"installation_id": str(self.installation_id),
43:                 "organization_id": str(self.organization_id) if self.organization_id else None,
44:                 "key": self.key, "name": self.name, "kind": self.kind,
45:                 "environment": self.environment, "capabilities": list(self.capabilities),
46:                 "url": f"http://127.0.0.1:{self.port}",
47:                 "registry_state": self.registry_state, "billing_enabled": False,
48:                 "retention": self.retention}
49: 
```

