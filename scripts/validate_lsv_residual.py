"""Synthetic, reproducible LSV acceptance; no live providers or production DB."""
import os,sys,json,time,math
from pathlib import Path
from datetime import date,timedelta
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
sys.path.insert(0,str(REPO))
os.environ['STRUCTURA_DATA_DIR']=str(ROOT/'data')
from sqlmodel import Session,SQLModel,create_engine,select
from sqlalchemy.pool import StaticPool
from dataclasses import replace
from backend.tests.test_simulation_grid import asset,ATHENA
from backend.app.api import deals,pricing
from backend.app.core.schemas import PricingRequest
from backend.app.core.deal_valuation import MtmRequest
from backend.app.core.valuation_context import run_valuation,run_analysis,valuation_context_from_dict
from backend.app.core.valuation_runs import stage_valuation_run,replay_valuation_run
from backend.app.db.models import User,Counterparty,Deal,DealEvent
start=ASOF-timedelta(days=372);end=start+timedelta(days=1096)
while end.weekday()>=5:end+=timedelta(days=1)
uls=[asset('STM','STMPA.PA',.54646136,.007388)]
market_sg=asset('SG','GLE.PA',.34952353,.028009)
outputs=[]
def hist(tickers,*args,**kwargs):
 return dict(dates=[str(start),str(start+timedelta(days=365)),str(ASOF)],
             prices={ticker:[100.,90.,90.] for ticker in tickers})
deals.load_hist_prices=hist
engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
SQLModel.metadata.create_all(engine)
with Session(engine) as session:
 actor=User(id=1,username='lsv-residual-recipe',email='lsv@example.invalid',password_hash='synthetic',role='user')
 session.add(actor);session.add(Counterparty(id=1,name='Recette LSV',active=True));session.commit()
 for basket in [False,True]:
  assets=[market_sg,*uls] if basket else uls
  corr=[[1.,.32012317],[.32012317,1.]] if basket else [[1.]]
  request=PricingRequest(script=ATHENA,underlyings=assets,corr_matrix=corr,r=.03,T=3.,N=1000,model='lsv',steps_per_year=52,
   strike_date=start,value_date=start,maturity_date=end,payment_date=end+timedelta(days=3),settlement_ccy='EUR',
   constats={'STARTDATE':str(start),'OBSERVATIONDATES':dict(first_observation_date=str(start+timedelta(days=365)),end_date=str(end),frequency='1Y',convention='following',settlement_lag=3,observation_calendars=['XPAR'],settlement_calendars=['TARGET'])})
  initial=pricing.price_endpoint(request)
  body=deals.DealCreate(contrepartie='Recette LSV',counterparty_id=1,transaction_format='EMTN',instrument_family='NOTE',nominal=100000,
   fair_value=initial.price*100,price_traded=initial.price*100,trade_date=str(start),strike_date=str(start),value_date=str(start),maturity_date=str(end),payment_date=str(end+timedelta(days=3)),T=3.,devise='EUR',
   underlyings=[dict(name=u['name'],ticker=u['ticker'],ccy='EUR') for u in assets],observation_times=[1.,2.,3.],script_snapshot=ATHENA,pricing_receipt=initial.pricing_receipt)
  booked=deals.book_deal(body,actor,session);deal=session.get(Deal,booked['id']);frozen=deal.market_snapshot_json
  first=next(e for e in session.exec(select(DealEvent).where(DealEvent.deal_id==deal.id)).all() if e.t_years==0.)
  first.spots_json=json.dumps({u['name']:100. for u in assets});first.source='synthetic';first.status='observé';session.add(first);session.commit()
  for frequency in (52,104,208):
   began=time.monotonic();label='SG-STM' if basket else 'STM'
   try:
    result,ctx=deals._mtm_core(deal,session,n_paths=8192,body=MtmRequest(steps_per_year=frequency),asof=ASOF)
    assert result['market_used']['lsv_calibration']['status']=='QUALIFIED'
    context=valuation_context_from_dict(ctx['valuation_context'])
    duplicate=run_valuation(ctx['residual_script'],context)
    assert duplicate['price']==result['mtm']
    lv=run_valuation(ctx['residual_script'],replace(context,model='localvol'))
    lsv_stats=run_analysis(ctx['residual_script'],context,'proba')
    lv_stats=run_analysis(ctx['residual_script'],replace(context,model='localvol'),'proba')
    row,saved=stage_valuation_run(session,deal,actor.id,'MTM',ctx,result,diagnostics={'request':MtmRequest(steps_per_year=frequency).model_dump(mode='json')})
    session.commit();replayed=replay_valuation_run(row)
    assert replayed['within_tolerance'] and replayed['qualified']
    assert session.get(Deal,deal.id).market_snapshot_json==frozen
    item=dict(basket=label,frequency=frequency,price_lsv=result['mtm'],ci_lsv=result['ic95'],price_dupire=lv['price'],ci_dupire=lv['ic95'],delta_bp=(result['mtm']-lv['price'])*10000,
      autocall_lsv=lsv_stats['autocall_pct'],autocall_dupire=lv_stats['autocall_pct'],observed=result['obs_passees'],anchor=context.local_vol_anchor,
      calibration=result['market_used']['lsv_calibration'],replay=replayed,seconds=time.monotonic()-began)
    Path(ROOT/f'context-{label}-{frequency}.json').write_text(json.dumps(ctx['valuation_context']),encoding='utf-8')
    print('PASS',label,frequency,round(result['mtm']*100,4),round(lv['price']*100,4),round(item['seconds'],1),flush=True)
   except Exception as exc:
    item=dict(basket=label,frequency=frequency,error=str(exc));print('FAIL',label,frequency,str(exc),flush=True)
   outputs.append(item);(ROOT/'chain-results.json').write_text(json.dumps(outputs,ensure_ascii=False,default=str),encoding='utf-8')
engine.dispose()

if any('error' in row for row in outputs): raise SystemExit(1)
