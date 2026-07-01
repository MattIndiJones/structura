"""Run FF analysis on CH1352587708 and print a diagnostic."""
import sys, io, json
sys.path.insert(0, r'C:\Users\admin\GitHub\structura\backend')

from app.core.amc_engine import parse_amc_excel, run_analysis, ff_data_status

ISIN  = "CH1352587708"
EXCEL = rf"C:\Users\phili\Downloads\UTI\Data\{ISIN}\{ISIN}_AMC_Diagnostic_Master.xlsx"

# --1. Parse Excel ------------------------------------------------------
with open(EXCEL, 'rb') as f:
    buf = io.BytesIO(f.read())
data = parse_amc_excel(buf)
nav   = data['nav']
tx    = data['transactions']
comp  = data['composition']
expos = data['exposures']

print(f"NAV: {len(nav)} obs  [{nav[0]['date']} -> {nav[-1]['date']}]")
print(f"Transactions: {len(tx)}")
print(f"Composition: {len(comp)} lignes")

# --2. FF store status --------------------------------------------------
print("\nFF store:")
for s in ff_data_status():
    avail = "OK" if s['available'] else "MISSING"
    print(f"  {s['key']:20s} {avail}  {s.get('date_min','')}->{s.get('date_max','')}")

# --3. Run analysis - several configs ----------------------------------
CONFIGS = [
    ("Developed_5F / FF5+MOM",  "Developed_5F",  ["Mkt-RF","SMB","HML","RMW","CMA","MOM"], "IXG"),
    ("Developed_5F / FF5",      "Developed_5F",  ["Mkt-RF","SMB","HML","RMW","CMA"],       "IXG"),
    ("Developed_3F / FF3",      "Developed_3F",  ["Mkt-RF","SMB","HML"],                   "IXG"),
    ("Global_3F / FF3",         "Global_3F",     ["Mkt-RF","SMB","HML"],                   "IXG"),
    ("EU_5F / FF5",             "EU_5F",         ["Mkt-RF","SMB","HML","RMW","CMA"],       "EUFN"),
]

print("\n" + "="*90)
print(f"{'Config':<30} {'N':>5} {'Period':>24} {'R2':>6} {'AdjR2':>6} {'Alpha%':>8} {'t_a':>7} {'p_a':>7}")
print("="*90)

results = {}
for label, series, factors, bm in CONFIGS:
    try:
        r = run_analysis(nav, tx, comp, expos, series, factors, bm, 60)
        reg = r['regression']
        p   = r['period']
        overlap = f"{p['overlap_start']} -> {p['overlap_end']}"
        print(f"{label:<30} {reg['n_obs']:>5} {overlap:>24} "
              f"{reg['r2']:>6.3f} {reg['adj_r2']:>6.3f} "
              f"{reg['alpha_ann_pct']:>8.2f} {reg['alpha_tstat']:>7.3f} {reg['alpha_pvalue']:>7.4f}")
        results[label] = r
    except Exception as e:
        msg = str(e).encode('ascii', errors='replace').decode('ascii')
        print(f"{label:<30} ERROR: {msg}")

# --4. Detailed view of best config (Developed_5F / FF5+MOM) ----------
key = "Developed_5F / FF5+MOM"
if key in results:
    r = results[key]
    reg = r['regression']
    perf = r['performance']
    print("\n" + "="*90)
    print(f"DETAIL: {key}")
    print("="*90)
    print(f"  Period: {r['period']['overlap_start']} -> {r['period']['overlap_end']}  ({reg['n_obs']} obs)")
    print(f"  R2={reg['r2']:.4f}  AdjR2={reg['adj_r2']:.4f}  DW={reg['dw']:.3f}")
    print(f"  Alpha ann = {reg['alpha_ann_pct']:+.2f}%  t={reg['alpha_tstat']:.3f}  p={reg['alpha_pvalue']:.4f}")
    print(f"  IC95(alpha): [{reg.get('alpha_ci_low','?')}% , {reg.get('alpha_ci_high','?')}%]")
    print()
    print(f"  {'Factor':<12} {'Beta':>8} {'CI_low':>8} {'CI_high':>8} {'t':>8} {'p':>8}")
    for f in reg['factors']:
        sig = "***" if f['pvalue']<0.001 else "**" if f['pvalue']<0.01 else "*" if f['pvalue']<0.05 else "." if f['pvalue']<0.1 else ""
        print(f"  {f['name']:<12} {f['beta']:>8.4f} {f['ci_low']:>8.4f} {f['ci_high']:>8.4f} {f['tstat']:>8.3f} {f['pvalue']:>8.4f} {sig}")
    print()
    print("  Performance (overlap period):")
    print(f"    Ret ann   = {perf['ann_ret_pct']:+.2f}%")
    print(f"    Vol ann   = {perf['ann_vol_pct']:.2f}%")
    print(f"    Sharpe    = {perf['sharpe']:.3f}")
    print(f"    Max DD    = {perf['max_dd_pct']:.2f}%")
    if perf.get('tracking_err_pct'):
        print(f"    Tracking e= {perf['tracking_err_pct']:.2f}%  IR={perf.get('info_ratio','?')}")
    print()
    print("  Warnings:")
    for w in r['warnings']: print(f"    [!] {w}")

# --5. NAV base-currency note ------------------------------------------
print("\n" + "="*90)
print("NOTE DEVISE")
print("="*90)
print("  L'AMC CH1352587708 est cote en CHF (NAV base 100 en CHF).")
print("  Les facteurs Fama-French (Developed_5F) sont en USD.")
print("  Il n'y a PAS de conversion CHF->USD appliquee sur le NAV avant la regression.")
print("  => L'alpha absorbe partiellement l'evolution du cross CHF/USD.")
print("  => Les betas refletent l'exposition aux facteurs MAIS contamines par le FX.")
