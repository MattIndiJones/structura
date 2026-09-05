import{M as f,r as _,m as i}from"./index-DmBzRy7K.js";const m=[{key:"autocall_athena",label:"Autocall Athena 3Y",group:"Autocall"},{key:"autocall_phoenix",label:"Phoenix 3Y (coupon conditionnel)",group:"Autocall"},{key:"autocall_worst_of",label:"Worst-of Athena 2 actifs",group:"Autocall"},{key:"autocall_gear_put",label:"Autocall Gear Put 3Y",group:"Autocall"},{key:"autocall_gear_put_worst_of",label:"Autocall Gear Put worst-of 2 actifs",group:"Autocall"},{key:"call_vanilla",label:"Call Vanille",group:"Options"},{key:"put_vanilla",label:"Put Vanille",group:"Options"},{key:"call_spread",label:"Call Spread",group:"Options"},{key:"digital",label:"Digital (binaire)",group:"Options"},{key:"capital_garanti",label:"Capital Garanti 5Y",group:"Produits à capital"},{key:"reverse_convertible",label:"Reverse Convertible",group:"Produits à capital"},{key:"twin_win",label:"Twin Win",group:"Produits à capital"},{key:"booster",label:"Booster 3Y",group:"Produits à capital"},{key:"shark_note",label:"Shark Note 3Y (capital garanti)",group:"Sharks"},{key:"shark_note_worst_of",label:"Shark Note worst-of 2 actifs",group:"Sharks"},{key:"zcb",label:"ZCB (test actualisation)",group:"Validation"}],U={autocall_athena:`# Autocall Athena 3 ans
PARAM COUPON = 8%
PARAM M_AC_BAR = 100%
PARAM M_KI_BAR = 60%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,autocall_phoenix:`# Phoenix 3 ans — coupon conditionnel
PARAM COUPON = 10%
PARAM M_AC_BAR = 100%
PARAM M_CPN_BAR = 80%
PARAM M_KI_BAR = 60%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  SET CPN  = INDIC(WOF >= M_CPN_BAR)
  PAY CPN * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,autocall_worst_of:`# Worst-of Athena 2 sous-jacents
PARAM COUPON = 12%
PARAM M_AC_BAR = 100%
PARAM M_KI_BAR = 55%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET KI = INDIC(WOF_MIN < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,autocall_gear_put:`# Autocall 3 ans — gear put avec levier sur strike
PARAM COUPON     = 10%
PARAM M_AC_BAR     = 100%
PARAM M_PUT_STRIKE = 80%
PARAM GEARING    = 150%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET LOSS = MIN(1, GEARING * MAX(0, 1 - WOF/M_PUT_STRIKE))
  PAY 1 "Remboursement nominal"
  PAY -1 * LOSS "Put vendu à effet de levier (plafonné à 100% du capital)"`,autocall_gear_put_worst_of:`# Worst-of autocall 2 sous-jacents — gear put avec levier sur strike
PARAM COUPON     = 12%
PARAM M_AC_BAR     = 100%
PARAM M_PUT_STRIKE = 80%
PARAM GEARING    = 150%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET LOSS = MIN(1, GEARING * MAX(0, 1 - WOF/M_PUT_STRIKE))
  PAY 1 "Remboursement nominal"
  PAY -1 * LOSS "Put vendu à effet de levier (plafonné à 100% du capital)"`,call_vanilla:`# Call Vanille
PARAM STRIKE = 100%

AT MATURITY:
  PAY MAX(0, WOF - STRIKE)`,put_vanilla:`# Put Vanille
PARAM STRIKE = 100%

AT MATURITY:
  PAY MAX(0, STRIKE - WOF)`,call_spread:`# Call Spread 100%-120%
PARAM K1 = 100%
PARAM K2 = 120%

AT MATURITY:
  PAY MAX(0, MIN(WOF - K1, K2 - K1))`,digital:`# Digital (option binaire)
PARAM STRIKE = 100%
PARAM REBATE = 10%

AT MATURITY:
  SET ITM = INDIC(WOF >= STRIKE)
  PAY ITM * REBATE`,capital_garanti:`# Capital Garanti 5 ans
PARAM PART = 80%
PARAM STRIKE = 100%

AT MATURITY:
  PAY 1
  PAY MAX(0, WOF - STRIKE) * PART`,reverse_convertible:`# Reverse Convertible 1 an
PARAM COUPON = 10%
PARAM M_KI_BAR = 80%

AT MATURITY:
  PAY COUPON
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,twin_win:`# Twin Win 3 ans
PARAM CAP = 150%
PARAM M_KI_BAR = 70%

AT MATURITY:
  SET BREACHED = INDIC(WOF_MIN < M_KI_BAR)
  SET UPS = MIN(CAP, MAX(1, WOF))
  SET DNS = MIN(CAP, MAX(1, 2 - WOF))
  PAY (1 - BREACHED) * MAX(UPS, DNS)
  PAY BREACHED * WOF`,booster:`# Booster 3 ans (levier haussier)
PARAM PART = 200%
PARAM CAP = 140%
PARAM PLANCHER = 100%

AT MATURITY:
  SET PERF = WOF
  SET BOOSTED = MIN(CAP, PLANCHER + (PERF - 1) * PART)
  SET DOWN = MIN(1, PERF)
  SET IS_UP = INDIC(PERF >= 1)
  PAY IS_UP * BOOSTED
  PAY (1 - IS_UP) * DOWN`,zcb:`# ZCB — validation actualisation
# Prix théorique = exp(-r * T)
AT MATURITY:
  PAY 1`,shark_note:`# Shark Note 3 ans — capital garanti
PARAM PART   = 100%
PARAM STRIKE = 100%
PARAM M_KO_BAR = 130%
PARAM REBATE = 3%

AT MATURITY:
  SET KO = INDIC(BOF_MAX >= M_KO_BAR)
  SET CALL = PART * MAX(0, WOF - STRIKE)
  PAY 1 "Remboursement nominal"
  PAY CALL "Call acheté (participation à la hausse)"
  PAY -1 * KO * (CALL - REBATE) "Abandon de performance au-delà de la barrière KO"`,shark_note_worst_of:`# Shark Note worst-of 2 sous-jacents — capital garanti
PARAM PART   = 80%
PARAM STRIKE = 100%
PARAM M_KO_BAR = 130%
PARAM REBATE = 3%

AT MATURITY:
  SET KO = INDIC(BOF_MAX >= M_KO_BAR)
  SET CALL = PART * MAX(0, WOF - STRIKE)
  PAY 1 "Remboursement nominal"
  PAY CALL "Call acheté (participation à la hausse)"
  PAY -1 * KO * (CALL - REBATE) "Abandon de performance au-delà de la barrière KO"`},v={autocall_athena:`# Autocall Athena 3 ans — mode expert
PARAM COUPON = 8%
PARAM M_AC_BAR = 100%
PARAM M_KI_BAR = 60%

CONSTAT() OBSERVATIONS

AT OBSERVATIONS:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBSERVATIONS.last:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,autocall_phoenix:`# Phoenix 3 ans — mode expert
PARAM COUPON = 10%
PARAM M_AC_BAR = 100%
PARAM M_CPN_BAR = 80%
PARAM M_KI_BAR = 60%

CONSTAT() OBSERVATIONS

AT OBSERVATIONS:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  SET CPN  = INDIC(WOF >= M_CPN_BAR)
  PAY CPN * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBSERVATIONS.last:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,autocall_worst_of:`# Worst-of Athena 2 sous-jacents — mode expert
PARAM COUPON = 12%
PARAM M_AC_BAR = 100%
PARAM M_KI_BAR = 55%

CONSTAT() OBSERVATIONS

AT OBSERVATIONS:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBSERVATIONS.last:
  SET KI = INDIC(WOF_MIN < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,autocall_gear_put:`# Autocall 3 ans — gear put avec levier sur strike — mode expert
PARAM COUPON     = 10%
PARAM M_AC_BAR     = 100%
PARAM M_PUT_STRIKE = 80%
PARAM GEARING    = 150%

CONSTAT() STRIKE_FIX
CONSTAT() OBSERVATIONS

SET REF = FIX_AVG

AT OBSERVATIONS:
  SET PERF = WOF / REF
  SET CALL = INDIC(PERF >= M_AC_BAR)
  PAY CALL * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBSERVATIONS.last:
  SET PERF = WOF / REF
  SET LOSS = MIN(1, GEARING * MAX(0, 1 - PERF/M_PUT_STRIKE))
  PAY 1 "Remboursement nominal"
  PAY -1 * LOSS "Put vendu à effet de levier (plafonné à 100% du capital)"`,autocall_gear_put_worst_of:`# Worst-of autocall 2 sous-jacents — gear put avec levier sur strike — mode expert
PARAM COUPON     = 12%
PARAM M_AC_BAR     = 100%
PARAM M_PUT_STRIKE = 80%
PARAM GEARING    = 150%

CONSTAT() STRIKE_FIX
CONSTAT() OBSERVATIONS

SET REF = FIX_AVG

AT OBSERVATIONS:
  SET PERF = WOF / REF
  SET CALL = INDIC(PERF >= M_AC_BAR)
  PAY CALL * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBSERVATIONS.last:
  SET PERF = WOF / REF
  SET LOSS = MIN(1, GEARING * MAX(0, 1 - PERF/M_PUT_STRIKE))
  PAY 1 "Remboursement nominal"
  PAY -1 * LOSS "Put vendu à effet de levier (plafonné à 100% du capital)"`,call_vanilla:`# Call Vanille — mode expert
PARAM STRIKE = 100%

CONSTAT MATURITE

AT MATURITE:
  PAY MAX(0, WOF - STRIKE)`,put_vanilla:`# Put Vanille — mode expert
PARAM STRIKE = 100%

CONSTAT MATURITE

AT MATURITE:
  PAY MAX(0, STRIKE - WOF)`,call_spread:`# Call Spread 100%-120% — mode expert
PARAM K1 = 100%
PARAM K2 = 120%

CONSTAT MATURITE

AT MATURITE:
  PAY MAX(0, MIN(WOF - K1, K2 - K1))`,digital:`# Digital (option binaire) — mode expert
PARAM STRIKE = 100%
PARAM REBATE = 10%

CONSTAT MATURITE

AT MATURITE:
  SET ITM = INDIC(WOF >= STRIKE)
  PAY ITM * REBATE`,capital_garanti:`# Capital Garanti 5 ans — mode expert
PARAM PART = 80%
PARAM STRIKE = 100%

CONSTAT MATURITE

AT MATURITE:
  PAY 1
  PAY MAX(0, WOF - STRIKE) * PART`,reverse_convertible:`# Reverse Convertible 1 an — mode expert
PARAM COUPON = 10%
PARAM M_KI_BAR = 80%

CONSTAT MATURITE

AT MATURITE:
  PAY COUPON
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,twin_win:`# Twin Win 3 ans — mode expert
PARAM CAP = 150%
PARAM M_KI_BAR = 70%

CONSTAT MATURITE

AT MATURITE:
  SET BREACHED = INDIC(WOF_MIN < M_KI_BAR)
  SET UPS = MIN(CAP, MAX(1, WOF))
  SET DNS = MIN(CAP, MAX(1, 2 - WOF))
  PAY (1 - BREACHED) * MAX(UPS, DNS)
  PAY BREACHED * WOF`,booster:`# Booster 3 ans — mode expert
PARAM PART = 200%
PARAM CAP = 140%
PARAM PLANCHER = 100%

CONSTAT MATURITE

AT MATURITE:
  SET PERF = WOF
  SET BOOSTED = MIN(CAP, PLANCHER + (PERF - 1) * PART)
  SET DOWN = MIN(1, PERF)
  SET IS_UP = INDIC(PERF >= 1)
  PAY IS_UP * BOOSTED
  PAY (1 - IS_UP) * DOWN`,zcb:`# ZCB — validation actualisation — mode expert
CONSTAT MATURITE

AT MATURITE:
  PAY 1`,shark_note:`# Shark Note 3 ans — capital garanti — mode expert
PARAM PART   = 100%
PARAM STRIKE = 100%
PARAM M_KO_BAR = 130%
PARAM REBATE = 3%

CONSTAT MATURITE

AT MATURITE:
  SET KO = INDIC(BOF_MAX >= M_KO_BAR)
  SET CALL = PART * MAX(0, WOF - STRIKE)
  PAY 1 "Remboursement nominal"
  PAY CALL "Call acheté (participation à la hausse)"
  PAY -1 * KO * (CALL - REBATE) "Abandon de performance au-delà de la barrière KO"`,shark_note_worst_of:`# Shark Note worst-of 2 sous-jacents — capital garanti — mode expert
PARAM PART   = 80%
PARAM STRIKE = 100%
PARAM M_KO_BAR = 130%
PARAM REBATE = 3%

CONSTAT MATURITE

AT MATURITE:
  SET KO = INDIC(BOF_MAX >= M_KO_BAR)
  SET CALL = PART * MAX(0, WOF - STRIKE)
  PAY 1 "Remboursement nominal"
  PAY CALL "Call acheté (participation à la hausse)"
  PAY -1 * KO * (CALL - REBATE) "Abandon de performance au-delà de la barrière KO"`};function h(t={},o){var s;if(!o)return t;const I=Object.keys(t.scales||{}),l=I.length?I:["x","y"],r={};for(const O of l){const E=(t.scales||{})[O]||{};r[O]={...E,ticks:{...E.ticks||{},display:!1}}}return{...t,scales:r,plugins:{...t.plugins,tooltip:{...(s=t.plugins)==null?void 0:s.tooltip,enabled:!1}}}}async function R(t,o){if(!t.ok){const l=(await t.json().catch(()=>({}))).detail;if(l&&typeof l=="object"){const r=(l.failures||[]).map(s=>`${s.code||"CONTRÔLE"} — ${s.message||JSON.stringify(s)}`);throw new Error([l.message||l.code||o,...r].join(`
`))}throw new Error(l||o)}return t.status===204?null:t.json()}const g=f("rfq",()=>{const t=_([]),o=_(null),I=_([]),l=_([]),r=_(null);async function s(){const e=await i("/api/rfq/providers");I.value=await R(e,"Erreur chargement fournisseurs")}async function O(){const e=await i("/api/rfq/history");l.value=await R(e,"Erreur chargement historique")}async function E(){const e=await i("/api/rfq");t.value=await R(e,"Erreur chargement RFQ")}async function c(e){const A=await i(`/api/rfq/${e}`);return r.value&&r.value.rfqId!==e&&(r.value=null),o.value=await R(A,"RFQ introuvable"),o.value}async function p(e){const A=await i("/api/rfq",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(e)}),n=await R(A,"Erreur création RFQ");return t.value.unshift(n),n}async function S(e,A){var P,u;const n=await i(`/api/rfq/${e}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(A)}),a=await R(n,"Erreur mise à jour RFQ");((P=o.value)==null?void 0:P.id)===e&&(o.value=a),a.model_price==null&&((u=r.value)==null?void 0:u.rfqId)===e&&(r.value=null);const T=t.value.findIndex(M=>M.id===e);return T!==-1&&(t.value[T]=a),a}async function N(e){var n;const A=await i(`/api/rfq/${e}`,{method:"DELETE"});await R(A,"Erreur suppression RFQ"),t.value=t.value.filter(a=>a.id!==e),((n=o.value)==null?void 0:n.id)===e&&(o.value=null)}async function d(e,A){var T;const n=await i(`/api/rfq/${e}/quotes`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(A)}),a=await R(n,"Erreur ajout fournisseur");return((T=o.value)==null?void 0:T.id)===e&&o.value.quotes.push(a),a}async function C(e,A,n){var P;const a=await i(`/api/rfq/${e}/quotes/${A}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(n)}),T=await R(a,"Erreur mise à jour quote");if(((P=o.value)==null?void 0:P.id)===e){const u=o.value.quotes.findIndex(M=>M.id===A);u!==-1&&(o.value.quotes[u]=T)}return T}async function L(e,A){var a;const n=await i(`/api/rfq/${e}/quotes/${A}`,{method:"DELETE"});await R(n,"Erreur suppression quote"),((a=o.value)==null?void 0:a.id)===e&&await c(e)}async function K(e,A,n){var a;await C(e,A,{last_look:n}),((a=o.value)==null?void 0:a.id)===e&&await c(e)}function F(e,A){return S(e,{selected_quote_id:A})}async function Y(e){var T,P,u,M;const A=e.params||{},n=await i("/api/price",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({script:e.script_snapshot,underlyings:A.underlyings||[],corr_matrix:A.corr_matrix||[],r:A.r??.03,T:A.T??3,N:A.N??2e4,model:A.model||"constant",yield_curve:A.yield_curve||[],funding_curve:A.funding_curve||[],funding_spread:A.funding_spread??0,user_params:A.user_params||{},constats:A.constats||{},strike_date:A.strike_date||null,value_date:A.value_date||null,payment_date:A.payment_date||null,settlement_ccy:A.currency||null,anchor:A.strike_date||A.value_date||null})}),a=await R(n,"Erreur calcul du prix modèle");return r.value={rfqId:e.id,result:a,strikeDate:A.strike_date||null,valueDate:A.value_date||null,hypotheses:{model:A.model||"constant",r:A.r??null,N:A.N??null,sigma:((P=(T=A.underlyings)==null?void 0:T[0])==null?void 0:P.sigma)??null,q:((M=(u=A.underlyings)==null?void 0:u[0])==null?void 0:M.q)??null},at:new Date().toISOString()},S(e.id,{model_price:a.price*100})}return{list:t,current:o,providers:I,history:l,lastPricing:r,fetchProviders:s,fetchList:E,fetchOne:c,create:p,update:S,remove:N,addQuote:d,updateQuote:C,removeQuote:L,computeModelPrice:Y,fetchHistory:O,toggleLastLook:K,selectQuote:F}});export{U as a,h as d,v as e,m as t,g as u};
