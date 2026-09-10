import{N as Y,r as M,m as i}from"./index-CVbKf7Is.js";const F=[{key:"autocall_athena",label:"Autocall Athena 3Y",group:"Autocall"},{key:"autocall_phoenix",label:"Phoenix 3Y (coupon conditionnel)",group:"Autocall"},{key:"autocall_worst_of",label:"Worst-of Athena 2 actifs",group:"Autocall"},{key:"autocall_gear_put",label:"Autocall Gear Put 3Y",group:"Autocall"},{key:"autocall_gear_put_worst_of",label:"Autocall Gear Put worst-of 2 actifs",group:"Autocall"},{key:"call_vanilla",label:"Call Vanille",group:"Options"},{key:"autocall_moyenne_periode",label:"Autocall coupon moyenné sur la période",group:"Autocall",expertOnly:!0},{key:"call_moyenne",label:"Call panier, strike et final moyennés",group:"Options",expertOnly:!0},{key:"call_lookback",label:"Call à strike lookback (min période)",group:"Options",expertOnly:!0},{key:"put_vanilla",label:"Put Vanille",group:"Options"},{key:"call_spread",label:"Call Spread",group:"Options"},{key:"digital",label:"Digital (binaire)",group:"Options"},{key:"capital_garanti",label:"Capital Garanti 5Y",group:"Produits à capital"},{key:"reverse_convertible",label:"Reverse Convertible",group:"Produits à capital"},{key:"twin_win",label:"Twin Win",group:"Produits à capital"},{key:"booster",label:"Booster 3Y",group:"Produits à capital"},{key:"shark_note",label:"Shark Note 3Y (capital garanti)",group:"Sharks"},{key:"shark_note_worst_of",label:"Shark Note worst-of 2 actifs",group:"Sharks"},{key:"zcb",label:"ZCB (test actualisation)",group:"Validation"}],U={autocall_athena:`# Autocall Athena 3 ans
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
  PAY KI * WOF`,autocall_moyenne_periode:`# Autocall 3 ans — coupon constaté sur la MOYENNE de la période — mode expert
# Chaque constatation annuelle est la moyenne des relevés trimestriels de
# l'année, par sous-jacent, avant que WOF n'agrège. La protection finale, elle,
# regarde le COURS de clôture : .last.last descend de la constatation à son
# dernier relevé.
PARAM COUPON    = 8%
PARAM M_AC_BAR   = 100%
PARAM M_PDI_BAR  = 60%

CONSTAT() OBSERVATIONS AVG PERIOD

AT OBSERVATIONS:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * (1 + COUPON * INDEX) "Rappel + coupon sur moyenne de période"
  IF CALL = 1:
    STOP

AT OBSERVATIONS.last.last:
  SET KI = INDIC(WOF < M_PDI_BAR)
  PAY 1 - KI * (1 - WOF) "Remboursement, PDI sur le cours final"`,autocall_gear_put:`# Autocall 3 ans — gear put avec levier sur strike — mode expert
PARAM COUPON     = 10%
PARAM M_AC_BAR     = 100%
PARAM M_PUT_STRIKE = 80%
PARAM GEARING    = 150%

CONSTAT STRIKE_FIX AVG
CONSTAT() OBSERVATIONS

AT OBSERVATIONS:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBSERVATIONS.last:
  SET LOSS = MIN(1, GEARING * MAX(0, 1 - WOF/M_PUT_STRIKE))
  PAY 1 "Remboursement nominal"
  PAY -1 * LOSS "Put vendu à effet de levier (plafonné à 100% du capital)"`,autocall_gear_put_worst_of:`# Worst-of autocall 2 sous-jacents — gear put avec levier sur strike — mode expert
PARAM COUPON     = 12%
PARAM M_AC_BAR     = 100%
PARAM M_PUT_STRIKE = 80%
PARAM GEARING    = 150%

CONSTAT STRIKE_FIX AVG
CONSTAT() OBSERVATIONS

AT OBSERVATIONS:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBSERVATIONS.last:
  SET LOSS = MIN(1, GEARING * MAX(0, 1 - WOF/M_PUT_STRIKE))
  PAY 1 "Remboursement nominal"
  PAY -1 * LOSS "Put vendu à effet de levier (plafonné à 100% du capital)"`,call_moyenne:`# Call panier — strike et niveau final moyennés — mode expert
# S0 et SF sont constatés PAR SOUS-JACENT sur leur fenêtre (longueur et
# fréquence saisies dans le panneau CONSTAT), et BASKET agrège ensuite.
PARAM STRIKE = 100%

CONSTAT STRIKE_FIX  AVG
CONSTAT MATURITE    AVG

AT MATURITE:
  PAY MAX(0, BASKET - STRIKE) "Call panier, strike et final moyennés"`,call_lookback:`# Call à strike lookback — mode expert
# Le strike est le PLUS BAS de chaque sous-jacent sur la période de départ :
# le niveau de référence le plus favorable à l'acheteur du call.
PARAM STRIKE = 100%

CONSTAT STRIKE_FIX  MIN
CONSTAT MATURITE

AT MATURITE:
  PAY MAX(0, WOF - STRIKE) "Call sur perf vs plus bas de la période de départ"`,call_vanilla:`# Call Vanille — mode expert
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
  PAY -1 * KO * (CALL - REBATE) "Abandon de performance au-delà de la barrière KO"`};function y(t={},l){var R;if(!l)return t;const I=Object.keys(t.scales||{}),r=I.length?I:["x","y"],o={};for(const _ of r){const c=(t.scales||{})[_]||{};o[_]={...c,ticks:{...c.ticks||{},display:!1}}}return{...t,scales:o,plugins:{...t.plugins,tooltip:{...(R=t.plugins)==null?void 0:R.tooltip,enabled:!1}}}}async function s(t,l){if(!t.ok){const r=(await t.json().catch(()=>({}))).detail;if(r&&typeof r=="object"){const o=(r.failures||[]).map(R=>`${R.code||"CONTRÔLE"} — ${R.message||JSON.stringify(R)}`);throw new Error([r.message||r.code||l,...o].join(`
`))}throw new Error(r||l)}return t.status===204?null:t.json()}const g=Y("rfq",()=>{const t=M([]),l=M(null),I=M([]),r=M([]),o=M(null);async function R(){const A=await i("/api/rfq/providers");I.value=await s(A,"Erreur chargement fournisseurs")}async function _(){const A=await i("/api/rfq/history");r.value=await s(A,"Erreur chargement historique")}async function c(){const A=await i("/api/rfq");t.value=await s(A,"Erreur chargement RFQ")}async function S(A){const e=await i(`/api/rfq/${A}`);return o.value&&o.value.rfqId!==A&&(o.value=null),l.value=await s(e,"RFQ introuvable"),l.value}async function p(A){const e=await i("/api/rfq",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(A)}),n=await s(e,"Erreur création RFQ");return t.value.unshift(n),n}async function E(A,e){var P,u;const n=await i(`/api/rfq/${A}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(e)}),a=await s(n,"Erreur mise à jour RFQ");((P=l.value)==null?void 0:P.id)===A&&(l.value=a),a.model_price==null&&((u=o.value)==null?void 0:u.rfqId)===A&&(o.value=null);const T=t.value.findIndex(O=>O.id===A);return T!==-1&&(t.value[T]=a),a}async function N(A){var n;const e=await i(`/api/rfq/${A}`,{method:"DELETE"});await s(e,"Erreur suppression RFQ"),t.value=t.value.filter(a=>a.id!==A),((n=l.value)==null?void 0:n.id)===A&&(l.value=null)}async function d(A,e){var T;const n=await i(`/api/rfq/${A}/quotes`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(e)}),a=await s(n,"Erreur ajout fournisseur");return((T=l.value)==null?void 0:T.id)===A&&l.value.quotes.push(a),a}async function C(A,e,n){var P;const a=await i(`/api/rfq/${A}/quotes/${e}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(n)}),T=await s(a,"Erreur mise à jour quote");if(((P=l.value)==null?void 0:P.id)===A){const u=l.value.quotes.findIndex(O=>O.id===e);u!==-1&&(l.value.quotes[u]=T)}return T}async function L(A,e){var a;const n=await i(`/api/rfq/${A}/quotes/${e}`,{method:"DELETE"});await s(n,"Erreur suppression quote"),((a=l.value)==null?void 0:a.id)===A&&await S(A)}async function K(A,e,n){var a;await C(A,e,{last_look:n}),((a=l.value)==null?void 0:a.id)===A&&await S(A)}function f(A,e){return E(A,{selected_quote_id:e})}async function B(A){var T,P,u,O;const e=A.params||{},n=await i("/api/price",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({script:A.script_snapshot,underlyings:e.underlyings||[],corr_matrix:e.corr_matrix||[],r:e.r??.03,T:e.T??3,N:e.N??2e4,model:e.model||"constant",yield_curve:e.yield_curve||[],funding_curve:e.funding_curve||[],funding_spread:e.funding_spread??0,user_params:e.user_params||{},constats:e.constats||{},strike_date:e.strike_date||null,value_date:e.value_date||null,payment_date:e.payment_date||null,settlement_ccy:e.currency||null,anchor:e.strike_date||e.value_date||null})}),a=await s(n,"Erreur calcul du prix modèle");return o.value={rfqId:A.id,result:a,strikeDate:e.strike_date||null,valueDate:e.value_date||null,hypotheses:{model:e.model||"constant",r:e.r??null,N:e.N??null,sigma:((P=(T=e.underlyings)==null?void 0:T[0])==null?void 0:P.sigma)??null,q:((O=(u=e.underlyings)==null?void 0:u[0])==null?void 0:O.q)??null},at:new Date().toISOString()},E(A.id,{model_price:a.price*100})}return{list:t,current:l,providers:I,history:r,lastPricing:o,fetchProviders:R,fetchList:c,fetchOne:S,create:p,update:E,remove:N,addQuote:d,updateQuote:C,removeQuote:L,computeModelPrice:B,fetchHistory:_,toggleLastLook:K,selectQuote:f}});export{U as a,y as d,v as e,F as t,g as u};
