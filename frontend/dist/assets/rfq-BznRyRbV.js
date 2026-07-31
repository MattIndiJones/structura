import{A as Y,r as I}from"./index-DfocZu6H.js";import{a as R}from"./api-DoU1ziIU.js";const U=[{key:"autocall_athena",label:"Autocall Athena 3Y",group:"Autocall"},{key:"autocall_phoenix",label:"Phoenix 3Y (coupon conditionnel)",group:"Autocall"},{key:"autocall_worst_of",label:"Worst-of Athena 2 actifs",group:"Autocall"},{key:"autocall_gear_put",label:"Autocall Gear Put 3Y",group:"Autocall"},{key:"autocall_gear_put_worst_of",label:"Autocall Gear Put worst-of 2 actifs",group:"Autocall"},{key:"call_vanilla",label:"Call Vanille",group:"Options"},{key:"put_vanilla",label:"Put Vanille",group:"Options"},{key:"call_spread",label:"Call Spread",group:"Options"},{key:"digital",label:"Digital (binaire)",group:"Options"},{key:"capital_garanti",label:"Capital Garanti 5Y",group:"Produits à capital"},{key:"reverse_convertible",label:"Reverse Convertible",group:"Produits à capital"},{key:"twin_win",label:"Twin Win",group:"Produits à capital"},{key:"booster",label:"Booster 3Y",group:"Produits à capital"},{key:"shark_note",label:"Shark Note 3Y (capital garanti)",group:"Sharks"},{key:"shark_note_worst_of",label:"Shark Note worst-of 2 actifs",group:"Sharks"},{key:"zcb",label:"ZCB (test actualisation)",group:"Validation"}],m={autocall_athena:`# Autocall Athena 3 ans
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
PARAM FLOOR = 100%

AT MATURITY:
  SET PERF = WOF
  SET BOOSTED = MIN(CAP, FLOOR + (PERF - 1) * PART)
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
  PAY -1 * KO * (CALL - REBATE) "Abandon de performance au-delà de la barrière KO"`},h={autocall_athena:`# Autocall Athena 3 ans — mode expert
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
PARAM FLOOR = 100%

CONSTAT MATURITE

AT MATURITE:
  SET PERF = WOF
  SET BOOSTED = MIN(CAP, FLOOR + (PERF - 1) * PART)
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
  PAY -1 * KO * (CALL - REBATE) "Abandon de performance au-delà de la barrière KO"`};async function r(T,t){if(!T.ok){const n=(await T.json().catch(()=>({}))).detail;if(n&&typeof n=="object"){const O=(n.failures||[]).map(i=>`${i.code||"CONTRÔLE"} — ${i.message||JSON.stringify(i)}`);throw new Error([n.message||n.code||t,...O].join(`
`))}throw new Error(n||t)}return T.status===204?null:T.json()}const W=Y("rfq",()=>{const T=I([]),t=I(null),M=I([]),n=I([]);async function O(){const A=await R("/api/rfq/providers");M.value=await r(A,"Erreur chargement fournisseurs")}async function i(){const A=await R("/api/rfq/history");n.value=await r(A,"Erreur chargement historique")}async function S(){const A=await R("/api/rfq");T.value=await r(A,"Erreur chargement RFQ")}async function E(A){const a=await R(`/api/rfq/${A}`);return t.value=await r(a,"RFQ introuvable"),t.value}async function C(A){const a=await R("/api/rfq",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(A)}),o=await r(a,"Erreur création RFQ");return T.value.unshift(o),o}async function u(A,a){var l;const o=await R(`/api/rfq/${A}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(a)}),e=await r(o,"Erreur mise à jour RFQ");((l=t.value)==null?void 0:l.id)===A&&(t.value=e);const P=T.value.findIndex(s=>s.id===A);return P!==-1&&(T.value[P]=e),e}async function c(A){var o;const a=await R(`/api/rfq/${A}`,{method:"DELETE"});await r(a,"Erreur suppression RFQ"),T.value=T.value.filter(e=>e.id!==A),((o=t.value)==null?void 0:o.id)===A&&(t.value=null)}async function p(A,a){var P;const o=await R(`/api/rfq/${A}/quotes`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(a)}),e=await r(o,"Erreur ajout fournisseur");return((P=t.value)==null?void 0:P.id)===A&&t.value.quotes.push(e),e}async function _(A,a,o){var l;const e=await R(`/api/rfq/${A}/quotes/${a}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(o)}),P=await r(e,"Erreur mise à jour quote");if(((l=t.value)==null?void 0:l.id)===A){const s=t.value.quotes.findIndex(F=>F.id===a);s!==-1&&(t.value.quotes[s]=P)}return P}async function N(A,a){var e;const o=await R(`/api/rfq/${A}/quotes/${a}`,{method:"DELETE"});await r(o,"Erreur suppression quote"),((e=t.value)==null?void 0:e.id)===A&&await E(A)}async function L(A,a,o){var e;await _(A,a,{last_look:o}),((e=t.value)==null?void 0:e.id)===A&&await E(A)}function d(A,a){return u(A,{selected_quote_id:a})}async function K(A){const a=A.params||{},o=await fetch("/api/price",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({script:A.script_snapshot,underlyings:a.underlyings||[],corr_matrix:a.corr_matrix||[],r:a.r??.03,T:a.T??3,N:a.N??2e4,model:a.model||"constant",user_params:a.user_params||{},constats:a.constats||{},anchor:a.value_date||null})}),e=await r(o,"Erreur calcul du prix modèle");return u(A.id,{model_price:e.price*100})}return{list:T,current:t,providers:M,history:n,fetchProviders:O,fetchList:S,fetchOne:E,create:C,update:u,remove:c,addQuote:p,updateQuote:_,removeQuote:N,computeModelPrice:K,fetchHistory:i,toggleLastLook:L,selectQuote:d}});export{m as a,h as e,U as t,W as u};
