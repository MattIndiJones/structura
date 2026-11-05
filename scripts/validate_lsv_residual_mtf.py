"""Synthetic, reproducible LSV acceptance; no live providers or production DB."""
import sys,os,json,math,time
from pathlib import Path
from datetime import date,timedelta
import numpy as np
import argparse
REPO=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description='Recette LSV résiduelle isolée, sans données ni booking utilisateur.')
parser.add_argument('--output',default=str(REPO/'.runtime'/'lsv-residual-validation'))
parser.add_argument('--asof',default=date.today().isoformat())
args=parser.parse_args()
ASOF=date.fromisoformat(args.asof)
ROOT=Path(args.output).resolve()
if any(path==REPO/'backend'/'data' or REPO/'backend'/'data' in path.parents for path in (ROOT,ROOT/'data',ROOT/'data-mtf')):
 raise ValueError('Le dossier de recette doit être hors de backend/data.')
ROOT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(REPO));os.environ['STRUCTURA_DATA_DIR']=str(ROOT/'data-mtf')
from backend.app.api import inlife,pricing
from backend.app.core.schemas import MtfRequest,MtfDrilldownRequest
from backend.tests.test_simulation_grid import asset,ATHENA
start=ASOF-timedelta(days=372);end=start+timedelta(days=1096)
while end.weekday()>=5:end+=timedelta(days=1)
payment=end+timedelta(days=3)
remaining=(end-ASOF).days/365.25;final=(payment-ASOF).days/365.25
inlife.load_hist_prices=lambda tickers,*a,**kw:dict(dates=[str(start),str(start+timedelta(days=365)),str(ASOF)],prices={t:[100.,90.,90.] for t in tickers})
outputs=[]
for basket in (False,True):
 for model in ('localvol','lsv'):
  label='SG-STM' if basket else 'STM';began=time.monotonic()
  assets=[asset('STM','STMPA.PA',.54646136,.007388)]
  if basket:assets.insert(0,asset('SG','GLE.PA',.34952353,.028009))
  req=MtfRequest(script=ATHENA,underlyings=assets,corr_matrix=[[1.,.32012317],[.32012317,1.]] if basket else [[1.]],r=.03,T=3.,model=model,
   steps_per_year=52,reference_paths=8192,main_price=0.,n_outer=200,n_inner=200,
   mtm_dates=[.4,.99,remaining,final],strike_date=start,value_date=start,maturity_date=end,payment_date=payment,valuation_date=ASOF,settlement_ccy='EUR',
   constats={'STARTDATE':str(start),'OBSERVATIONDATES':dict(first_observation_date=str(start+timedelta(days=365)),end_date=str(end),frequency='1Y',convention='following',settlement_lag=3,observation_calendars=['XPAR'],settlement_calendars=['TARGET'])})
  try:
   fan=pricing.mtf_endpoint(req)
   checks=[]
   se0=(fan['reference_ci95'][1]-fan['reference_ci95'][0])/3.92
   for row in fan['results']:
    cash=np.array([sum(f['amount']*100*math.exp(-.03*f['payment_t']) for f in flows) for flows in row['settled_flows']])
    wealth=cash+np.array(row['pvs'])*math.exp(-.03*row['t'])
    se=float(wealth.std(ddof=1)/math.sqrt(len(wealth)))
    difference=float(wealth.mean()-fan['main_price'])
    z=difference/math.sqrt(se**2+se0**2) if se+se0 else 0.
    checks.append(dict(t=row['t'],initial_price=fan['main_price'],mean_discounted_wealth=float(wealth.mean()),difference_bp=100*difference,combined_half_ci95_points=1.96*math.sqrt(se**2+se0**2),z=z,n_outstanding=row['n_outstanding']))
   assert all(abs(check['z'])<=1.96 for check in checks)
   assert all(v==0. for v in fan['results'][-1]['pvs'])
   details=[]
   for row in (fan['results'][0],fan['results'][-2]):
    request=MtfDrilldownRequest(**(req.model_dump()|dict(t=row['t'],scenario_ids=[0,99,199],main_price=fan['main_price'],context_fingerprint=fan['context_fingerprint'],lsv_qualification=fan.get('lsv_qualification'))))
    detail=pricing.mtf_drilldown_endpoint(request)
    for i,scenario in zip([0,99,199],detail['scenarios']):
     diff=abs(scenario['mtf']-row['pvs'][i]);assert diff<.00011
     details.append(dict(t=row['t'],scenario=i,difference=diff))
   output=dict(basket=label,model=model,price=fan['main_price'],checks=checks,drilldown=details,seconds=time.monotonic()-began)
   print('PASS',label,model,fan['main_price'],'z',[round(x['z'],2) for x in checks],round(output['seconds'],1),flush=True)
  except Exception as exc:
   output=dict(basket=label,model=model,error=str(exc));print('FAIL',label,model,str(exc),flush=True)
  outputs.append(output);(ROOT/'mtf-results.json').write_text(json.dumps(outputs,ensure_ascii=False,default=str),encoding='utf-8')

if any('error' in row for row in outputs): raise SystemExit(1)
