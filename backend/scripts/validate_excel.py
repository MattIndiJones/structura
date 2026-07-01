"""Validates that the 3 generated Excel files are readable by the classic engine."""
import sys, io, pandas as pd
sys.path.insert(0, r'C:\Users\admin\GitHub\structura\backend')

for isin in ['CH1352587708', 'CH1352587716', 'CH1473736143']:
    path = rf'C:\Users\phili\Downloads\UTI\Data\{isin}\{isin}_AMC_Diagnostic_Master.xlsx'
    wb = pd.ExcelFile(path)
    print(f"\n=== {isin} ===")
    print(f"  Sheets: {wb.sheet_names}")
    # NAV_History
    nav = wb.parse('NAV_History')
    print(f"  NAV_History: {len(nav)} rows, cols={list(nav.columns)[:4]}")
    print(f"  NAV sample: {nav.head(2)[['Date','NAV']].to_string(index=False)}")
    # Composition
    comp = wb.parse('Current_Composition_API')
    print(f"  Composition: {len(comp)} positions, cols={list(comp.columns)[:4]}")
    # Trade summary
    ts = wb.parse('Trade_Summary')
    print(f"  Trade_Summary: {len(ts)} rows")
