"""C12: rejected imports, one commit, crash recovery and independent caches."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from io import BytesIO
import json
import shutil
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backend.app.core import amc_prices as prices, market_storage as storage
from backend.app.services import market_history as history, market_data as market

CONVENTIONS = dict(currency='EUR',price_type='ADJUSTED_CLOSE',unit='CURRENCY')


@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    monkeypatch.setenv('STRUCTURA_DATA_DIR',str(tmp_path))
    monkeypatch.setattr(prices,'_PRICE_STORE',tmp_path/'underlying_prices')
    monkeypatch.setattr(prices,'_TICKER_MAP_FILE',tmp_path/'underlying_prices'/'_ticker_map.json')
    monkeypatch.setattr(prices,'_FX_STORE',tmp_path/'fx_rates')
    prices._PRICE_STORE.mkdir();prices._FX_STORE.mkdir()
    monkeypatch.setattr(market,'_HAS_YF',False)
    market.vider_cache_prix()
    yield tmp_path
    market.vider_cache_prix()


def upload(key='A',rows=None,**kwargs):
    data = [{'date':'2026-08-26','close':100},{'date':'2026-08-27','close':101}] if rows is None else rows
    return prices.upload_prices(key,json.dumps(data).encode(),'prices.json',**{**CONVENTIONS,**kwargs})


def observations(value=100):
    return pd.Series([value,value+1],index=pd.to_datetime(['2026-08-26','2026-08-27']))


def provider(monkeypatch,value=100,*,currency='EUR',broken=None):
    class Instrument:
        fast_info = {'currency':currency}
        def __init__(self,ticker):self.ticker=ticker
        def history(self,auto_adjust,**kwargs):
            if broken == 'network':raise RuntimeError('offline')
            if broken == 'raw_empty' and not auto_adjust:return pd.DataFrame()
            series = observations(value if auto_adjust else value+10)
            if broken == 'duplicate':series.index = pd.to_datetime(['2026-08-27']*2)
            if broken == 'infinite':series.iloc[1]=np.inf
            return series.to_frame('Close')
    monkeypatch.setattr(prices,'yf',SimpleNamespace(Ticker=Instrument))
    return Instrument


@pytest.mark.parametrize('rows',[
    [{'date':'2026-08-27','close':1},{'date':'2026-08-27','close':2}],
    [{'date':'bad-date','close':1}], [{'date':None,'close':1}],
    [{'date':'2026-08-27','close':float('inf')}],
    [{'date':'2026-08-27','close':float('nan')}],
    [{'date':'2026-08-27','close':0}], [{'date':'2026-08-27','close':-1}],
    [{'date':'2026-08-27','close':True}], [{'date':'2026-08-27','close':'not-a-price'}],
    [{'date':'2026-08-27','close':None}],
    [{'date':123456,'close':100}],
    [{'date':'27/08/2026','close':100}],
    [{'date':'2026-08-26','close':1},{'date':'2026-08-27'}], [],
])
def test_invalid_import_keeps_the_entire_series_mapping_and_manifest(isolated,rows):
    upload(ticker='ORIGINAL')
    manifest = (storage._root()/'manifest.json').read_bytes()
    frame = prices.load_prices('A');mapping = prices._load_ticker_map()
    with pytest.raises(ValueError):upload(rows=rows,ticker='REPLACEMENT')
    assert (storage._root()/'manifest.json').read_bytes() == manifest
    pd.testing.assert_frame_equal(prices.load_prices('A'),frame)
    assert prices._load_ticker_map() == mapping


@pytest.mark.parametrize('missing',['currency','price_type','unit'])
def test_missing_convention_is_rejected_before_replacement(missing):
    upload();before=storage.revision()
    with pytest.raises(ValueError,match='Conventions'):upload(**{missing:None})
    assert storage.revision()==before


def test_optional_raw_prices_require_explicit_share_unit_date():
    rows=[{'date':'2026-08-27','close':100,'price_close':110}]
    with pytest.raises(ValueError,match='unités de titres requise'):upload(rows=rows)
    upload(rows=rows,adjustment_date='2026-08-27')
    frame=prices.load_prices('A')
    assert frame['price_close'].tolist()==[110] and frame.attrs['adjustment_date']=='2026-08-27'


def test_raw_only_import_is_not_mislabelled_as_a_total_return_series():
    with pytest.raises(ValueError,match='cours brut seul'):upload(price_type='UNADJUSTED_CLOSE')
    assert storage.revision()[1]=='legacy'


def test_duplicate_json_object_keys_cannot_hide_duplicate_dates():
    content=b'{"2026-08-27":100,"2026-08-27":200}'
    with pytest.raises(ValueError,match='dupliqu'):
        prices.upload_prices('A',content,'x.json',**CONVENTIONS)


@pytest.mark.parametrize('bad',[float('inf'),0,'bad'])
def test_excel_import_rejects_bad_rows_without_trimming_them(bad):
    out=BytesIO();pd.DataFrame({'Date':['2026-08-26','2026-08-27'],'Price':[100,bad]}).to_excel(out,index=False)
    with pytest.raises(ValueError):prices.upload_prices('A',out.getvalue(),'x.xlsx',**CONVENTIONS)


@pytest.mark.parametrize('keys',[('A/B','A B'),('A'*81+'B','A'*81+'C'),('Asset','ASSET'),('../A','..\\A')])
def test_lossy_long_or_case_variant_keys_do_not_collide(keys):
    first,second=keys
    a=upload(first);b=upload(second,rows=[{'date':'2026-08-27','close':200}])
    assert a['key'] != b['key'] and a['key'].casefold()!=b['key'].casefold()
    assert prices.load_prices(first)['close'].iloc[0]==100
    assert prices.load_prices(second)['close'].iloc[0]==200
    assert prices.load_prices(a['key'])['close'].iloc[0]==100


def test_legacy_ambiguous_slug_is_not_adopted_for_another_name():
    legacy=prices._PRICE_STORE/'A_B.parquet'
    observations(50).to_frame('close').to_parquet(legacy)
    with pytest.raises(ValueError):prices.load_prices('A/B')
    upload('A/B');upload('A B',rows=[{'date':'2026-08-27','close':200}])
    assert pd.read_parquet(legacy)['close'].iloc[0]==50
    assert prices.load_prices('A_B')['close'].iloc[0]==50


def test_unambiguous_legacy_name_is_readable_without_rewriting_it():
    legacy=prices._PRICE_STORE/'Apple.parquet';observations().to_frame('close').to_parquet(legacy)
    original=legacy.read_bytes()
    assert prices.load_prices(prices._slug('Apple'))['close'].iloc[0]==100
    assert legacy.read_bytes()==original
    upload('Apple');prices.delete_prices(prices._slug('Apple'))
    with pytest.raises(ValueError):prices.load_prices('Apple')
    assert legacy.read_bytes()==original and prices.price_status()==[]


@pytest.mark.parametrize('broken',['network','raw_empty','duplicate','infinite'])
def test_failed_download_changes_neither_series_nor_instrument_association(monkeypatch,broken):
    upload(ticker='OLD');before=storage.revision();frame=prices.load_prices('A')
    provider(monkeypatch,broken=broken)
    with pytest.raises((ValueError,RuntimeError,KeyError)):
        prices.fetch_prices('A','NEW','2026-08-26','2026-08-28')
    assert storage.revision()==before and prices._load_ticker_map()=={'A':'OLD'}
    pd.testing.assert_frame_equal(prices.load_prices('A'),frame)


def test_unknown_provider_currency_cannot_publish_a_partial_download(monkeypatch):
    upload();before=storage.revision();provider(monkeypatch,currency='')
    with pytest.raises(ValueError,match='Devise'):prices.fetch_prices('A','NEW','2026-08-26','2026-08-28')
    assert storage.revision()==before


@pytest.mark.parametrize('stage',['serialize','publish'])
def test_write_failure_keeps_old_amc_shared_bases_and_mapping(monkeypatch,stage):
    provider(monkeypatch,100);prices.fetch_prices('A','OLD','2026-08-26','2026-08-28')
    before=storage.revision();mapping=prices._load_ticker_map();old=prices.load_prices('A')
    provider(monkeypatch,200)
    if stage=='serialize':
        original=pd.DataFrame.to_parquet;calls=[]
        def fail(frame,path,*args,**kwargs):
            calls.append(path)
            if len(calls)==3:raise OSError('simulated disk failure')
            return original(frame,path,*args,**kwargs)
        monkeypatch.setattr(pd.DataFrame,'to_parquet',fail)
    else:
        monkeypatch.setattr(storage.os,'replace',lambda *args:(_ for _ in ()).throw(OSError('publish failed')))
    with pytest.raises(OSError):prices.fetch_prices('A','NEW','2026-08-26','2026-08-28')
    assert storage.revision()==before and prices._load_ticker_map()==mapping
    pd.testing.assert_frame_equal(prices.load_prices('A'),old)
    assert history.local_history('NEW','2026-08-26','2026-08-27',False)[0] is None
    assert not list(storage._root().glob('*.tmp'))


def test_one_commit_exposes_both_bases_and_mapping_together(monkeypatch):
    provider(monkeypatch,100);prices.fetch_prices('A','A','2026-08-26','2026-08-28')
    with storage.read_view():
        old=prices.load_prices('A');old_revision=storage.view_revision()
        provider(monkeypatch,200);prices.fetch_prices('A','B','2026-08-26','2026-08-28')
        assert storage.revision()!=old_revision
        pd.testing.assert_frame_equal(prices.load_prices('A'),old)
        assert prices._load_ticker_map()=={'A':'A'}
        assert history.local_history('B','2026-08-26','2026-08-27',False)[0] is None
    assert prices._load_ticker_map()=={'A':'B'}
    assert prices.load_prices('A')['close'].iloc[0]==200
    assert history.local_history('B','2026-08-26','2026-08-27',False)[0].iloc[0]==210


def test_process_crash_before_publish_leaves_previous_generation_readable(isolated):
    upload(ticker='OLD');before=storage.revision();old=prices.load_prices('A')
    code="""import os,pandas as pd
from backend.app.core import market_storage as s,amc_prices as p
with s.transaction() as tx:
 tx.parquet(p._logical_price_path('A'),pd.DataFrame({'close':[999.]},index=pd.to_datetime(['2026-08-27'])))
 tx.json(p._TICKER_MAP_FILE,{'A':'WRONG'})
 os._exit(29)
"""
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=30)
    assert result.returncode==29,result.stderr
    assert storage.revision()==before and prices._load_ticker_map()=={'A':'OLD'}
    pd.testing.assert_frame_equal(prices.load_prices('A'),old)
    upload(ticker='NEXT');assert prices._load_ticker_map()=={'A':'NEXT'}


def test_concurrent_raw_history_merges_do_not_lose_observations():
    barrier=threading.Barrier(6)
    def write(index):
        barrier.wait()
        day=f'2026-08-{index+20:02d}'
        history.store_history('A',pd.Series([100+index],index=pd.to_datetime([day])),False,day,day)
    with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(write,range(6)))
    series=history.local_history('A','2026-08-20','2026-08-25',False)[0]
    assert len(series)==6 and series.tolist()==list(range(100,106))


def test_concurrent_instrument_commits_do_not_lose_map_entries():
    with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(lambda n:upload(f'A{n}',ticker=f'T{n}'),range(6)))
    assert prices._load_ticker_map()=={f'A{n}':f'T{n}' for n in range(6)}
    assert len(prices.price_status())==6


def test_shared_history_rejects_duplicate_and_nonfinite_input_before_replacing():
    history.store_history('A',observations(),True,'2026-08-26','2026-08-27');before=storage.revision()
    for series in [pd.Series([1,2],index=pd.to_datetime(['2026-08-27']*2)),observations(float('inf'))]:
        with pytest.raises(ValueError):history.store_history('A',series,True,'2026-08-26','2026-08-27')
        assert storage.revision()==before


def test_nested_response_mutation_and_simultaneous_cache_hits_are_independent():
    history.store_history('A',observations(),False,'2026-08-26','2026-08-27')
    baseline=market.load_hist_prices(['A'],'2026-08-26','2026-08-27')
    barrier=threading.Barrier(8)
    def read(index):
        barrier.wait();result=market.load_hist_prices(['A'],'2026-08-26','2026-08-27')
        result['prices']['A'][0]=index;result['sources']['A']['provider']='MUTATED'
        result['coverage']['included'].clear();return result
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(read,range(8)))
    assert len({id(x['prices']['A']) for x in results})==8
    assert market.load_hist_prices(['A'],'2026-08-26','2026-08-27')==baseline


def test_identical_concurrent_misses_share_one_provider_call(monkeypatch):
    arrived=threading.Event();release=threading.Event();calls=[]
    class Instrument:
        def __init__(self,ticker):pass
        def history(self,**kwargs):
            calls.append(kwargs);arrived.set();assert release.wait(5)
            return observations().to_frame('Close')
    monkeypatch.setattr(market,'yf',SimpleNamespace(Ticker=Instrument));monkeypatch.setattr(market,'_HAS_YF',True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        first=pool.submit(market.load_hist_prices,['A'],'2026-08-26','2026-08-27');assert arrived.wait(5)
        others=[pool.submit(market.load_hist_prices,['A'],'2026-08-26','2026-08-27') for _ in range(7)]
        release.set();results=[first.result()]+[x.result() for x in others]
    assert len(calls)==1 and all(x['prices']=={'A':[100.,101.]} for x in results)
    results[0]['prices']['A'][0]=999;assert results[1]['prices']['A'][0]==100


def test_storage_update_invalidates_memory_before_ttl_and_old_view_cannot_poison_new():
    history.store_history('A',observations(),True,'2026-08-26','2026-08-27')
    assert market.load_hist_prices(['A'],'2026-08-26','2026-08-27',adjusted=True)['prices']['A'][0]==100
    with storage.read_view():
        history.store_history('A',observations(200),True,'2026-08-26','2026-08-27')
        assert market.load_hist_prices(['A'],'2026-08-26','2026-08-27',adjusted=True)['prices']['A'][0]==100
    assert market.load_hist_prices(['A'],'2026-08-26','2026-08-27',adjusted=True)['prices']['A'][0]==200


def test_fx_cache_write_failure_returns_old_cache_and_does_not_truncate_it(monkeypatch):
    path=prices._FX_STORE/'USDEUR.parquet'
    pd.DataFrame({'rate':[.8]},index=pd.to_datetime(['2024-01-01'])).to_parquet(path);before=path.read_bytes()
    class Instrument:
        def __init__(self,ticker):pass
        def history(self,**kwargs):return observations(.9).to_frame('Close')
    monkeypatch.setattr(prices,'yf',SimpleNamespace(Ticker=Instrument))
    monkeypatch.setattr(storage.os,'replace',lambda *args:(_ for _ in ()).throw(OSError('disk')))
    result=prices.get_fx_series('USD','EUR',end='2026-08-28')
    assert result.iloc[0]==.8 and path.read_bytes()==before


def test_http_import_requires_admin_and_preserves_old_series_on_rejection(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.api.auth import get_current_admin,get_current_user
    upload();before=storage.revision()
    try:
        client=TestClient(app)
        file={'file':('x.json',b'[{"date":"2026-08-27","close":200}]','application/json')}
        assert client.post('/api/amc/prices/upload',data={'key':'A'},files=file).status_code==401
        app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(id=2,role='user')
        assert client.post('/api/amc/prices/upload',data={'key':'A',**CONVENTIONS},files=file).status_code==403
        app.dependency_overrides[get_current_admin]=lambda:SimpleNamespace(id=1,role='admin')
        missing=client.post('/api/amc/prices/upload',data={'key':'A'},files=file)
        assert missing.status_code==422 and storage.revision()==before
        saved=client.post('/api/amc/prices/upload',data={'key':'A',**CONVENTIONS},files=file)
        assert saved.status_code==200,saved.text
        assert prices.load_prices('A')['close'].tolist()==[200]
    finally:app.dependency_overrides.clear()


def test_late_download_cannot_overwrite_a_more_recent_instrument_replacement(monkeypatch):
    upload(ticker='OLD')
    class Instrument:
        fast_info={'currency':'EUR'}
        def __init__(self,ticker):pass
        def history(self,auto_adjust,**kwargs):
            if auto_adjust:upload(rows=[{'date':'2026-08-27','close':999}],ticker='LATEST')
            return observations().to_frame('Close')
    monkeypatch.setattr(prices,'yf',SimpleNamespace(Ticker=Instrument))
    with pytest.raises(ValueError,match='réponse ancienne'):
        prices.fetch_prices('A','EARLIER','2026-08-26','2026-08-28')
    assert prices.load_prices('A')['close'].tolist()==[999]
    assert prices._load_ticker_map()=={'A':'LATEST'}


def test_late_read_and_cache_clear_cannot_republish_old_observations(monkeypatch):
    started=threading.Event();release=threading.Event()
    class Instrument:
        def __init__(self,ticker):pass
        def history(self,**kwargs):
            started.set();assert release.wait(5)
            return observations().to_frame('Close')
    monkeypatch.setattr(market,'yf',SimpleNamespace(Ticker=Instrument));monkeypatch.setattr(market,'_HAS_YF',True)
    with ThreadPoolExecutor(max_workers=1) as pool:
        old=pool.submit(market.load_hist_prices,['A'],'2026-08-26','2026-08-27');assert started.wait(5)
        market.vider_cache_prix()
        history.store_history('A',observations(200),False,'2026-08-26','2026-08-27')
        current=market.load_hist_prices(['A'],'2026-08-26','2026-08-27')
        release.set();older=old.result()
    assert 'réponse ancienne' in older['sources']['A']['storage_error']
    assert older['prices']['A'][0]==100 and current['prices']['A'][0]==200
    assert market.load_hist_prices(['A'],'2026-08-26','2026-08-27')['prices']['A'][0]==200


def test_cross_process_writers_share_the_same_commit_lock(isolated):
    code="""import sys,time,pandas as pd
from pathlib import Path
from backend.app.services.market_history import store_history
root=Path(sys.argv[1]);number=int(sys.argv[2]);(root/f'ready-{number}').write_text('ready')
deadline=time.monotonic()+10
while not (root/'start').exists():
 assert time.monotonic()<deadline
 time.sleep(.01)
day=f'2026-08-{number+26:02d}'
store_history('A',pd.Series([100+number],index=pd.to_datetime([day])),False,day,day)
"""
    children=[subprocess.Popen([sys.executable,'-c',code,str(isolated),str(n)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for n in range(2)]
    try:
        deadline=time.monotonic()+15
        while not all((isolated/f'ready-{n}').exists() for n in range(2)):
            assert time.monotonic()<deadline
            time.sleep(.01)
        (isolated/'start').write_text('go')
        for child in children:
            out,error=child.communicate(timeout=20);assert child.returncode==0,error
        assert history.local_history('A','2026-08-26','2026-08-27',False)[0].tolist()==[100,101]
    finally:
        for child in children:
            if child.poll() is None:child.kill();child.wait(timeout=5)


def test_failed_publish_preserves_legacy_files_without_a_migration(monkeypatch):
    path=prices._PRICE_STORE/'A.parquet';observations(50).to_frame('close').to_parquet(path)
    prices._TICKER_MAP_FILE.write_text('{"A":"OLD"}')
    before=path.read_bytes();mapping=prices._TICKER_MAP_FILE.read_bytes()
    monkeypatch.setattr(storage.os,'replace',lambda *args:(_ for _ in ()).throw(OSError('disk')))
    with pytest.raises(OSError):upload(ticker='NEW')
    assert storage.revision()[1]=='legacy' and path.read_bytes()==before
    assert prices._TICKER_MAP_FILE.read_bytes()==mapping


def test_corrupted_mapping_is_not_silently_replaced_by_an_empty_map():
    prices._TICKER_MAP_FILE.write_text('{broken')
    with pytest.raises(ValueError,match='Association'):upload(ticker='NEW')
    assert prices._TICKER_MAP_FILE.read_text()=='{broken'


def test_cached_response_is_isolated_between_runtime_data_roots(monkeypatch,isolated):
    history.store_history('A',observations(),False,'2026-08-26','2026-08-27')
    assert market.load_hist_prices(['A'],'2026-08-26','2026-08-27')['prices']['A'][0]==100
    with monkeypatch.context() as other:
        other.setenv('STRUCTURA_DATA_DIR',str(isolated/'second-installation'))
        history.store_history('A',observations(200),False,'2026-08-26','2026-08-27')
        assert market.load_hist_prices(['A'],'2026-08-26','2026-08-27')['prices']['A'][0]==200
    assert market.load_hist_prices(['A'],'2026-08-26','2026-08-27')['prices']['A'][0]==100


def test_T04_calendar_freshness_failed_import_and_offline_recovery(monkeypatch):
    from backend.app.core.schedule import generate_main_schedule,parse_tenor,StubConvention
    from backend.app.api.schedule import resolve_business_day
    from backend.app.core.schemas import BusinessDayRequest
    dates=generate_main_schedule(date(2026,1,31),date(2026,5,31),date(2026,1,31),parse_tenor('1M'),StubConvention.SHORT_LAST)
    assert dates==[date(2026,1,31),date(2026,2,28),date(2026,3,31),date(2026,4,30),date(2026,5,31)]
    assert resolve_business_day(BusinessDayRequest(date='2026-04-02',currency='EUR',business_days=3))['date']=='2026-04-09'
    provider(monkeypatch);prices.fetch_prices('A','A','2026-08-26','2026-08-28')
    before=storage.revision()
    with pytest.raises(ValueError):upload(rows=[{'date':'2026-08-27','close':float('inf')}],ticker='WRONG')
    assert storage.revision()==before and prices._load_ticker_map()=={'A':'A'}
    monkeypatch.setattr(market,'_HAS_YF',False)
    history.store_history('B',pd.Series([50.],index=pd.to_datetime(['2026-04-01'])),False,'2026-01-31','2026-04-01')
    basket=market.load_hist_prices(['A','B'],'2026-01-31','2026-08-27')
    assert basket['error'] and basket['missing']==['B'] and basket['prices']=={}
    assert basket['freshness']['B']['status']=='STALE'
    offline=market.load_hist_prices(['A'],'2026-08-26','2026-08-27')
    assert offline['prices']['A']==[110.,111.] and offline['coverage']['complete']
    monkeypatch.setattr(prices,'get_fx_series',lambda *a,**kw:pd.Series([.9],index=pd.to_datetime(['2024-01-01'])))
    quote=prices.fx_quote_to('USD','EUR','2026-08-27')
    assert quote['rate'] is None and quote['status']=='STALE' and quote['max_age_days']==3


def test_historical_campaign_reader_resolves_committed_series_and_ticker_map(monkeypatch):
    from backend.app.services.agent_workshop.historical_market import cached_series
    provider(monkeypatch);prices.fetch_prices('A/B','A','2026-08-26','2026-08-28')
    series,source=cached_series('A',roots=[prices._PRICE_STORE])
    assert series.tolist()==[110,111] and source['price_basis']=='RAW_CLOSE'
    assert Path(source['cache_file']).parent==storage._root()/'objects'
    assert source['source_sha256']


def reference_package(root,values):
    folder=root/'manual_prices_E';folder.mkdir(parents=True,exist_ok=True)
    for number,value in enumerate(values,1):
        (folder/f'SYNTH_E_USD_{number}.json').write_text(json.dumps([{'date':'2026-08-27','close':value}]))


def test_reference_installer_uses_only_the_explicit_target_store(isolated):
    from scripts.studies_reference.install_e_prices import install
    package=isolated/'package';reference_package(package,[100,200])
    target=isolated/'other-installation'/'underlying_prices';before=storage.revision()
    install(package,target)
    assert storage.revision()==before
    with storage.store_context(target.parent):
        version=storage.revision();paths=storage.logical_paths(target)
        assert len(paths)==2
        assert sorted(pd.read_parquet(storage.current_path(p))['close'].iloc[0] for p in paths)==[100,200]
    install(package,target)
    with storage.store_context(target.parent):assert storage.revision()==version


def test_reference_installer_aborts_whole_batch_on_collision(isolated):
    from scripts.studies_reference.install_e_prices import install
    package=isolated/'package';reference_package(package,[100,200])
    target=isolated/'other-installation'/'underlying_prices';install(package,target)
    with storage.store_context(target.parent):version=storage.revision()
    reference_package(package,[999,200,300])
    with pytest.raises(ValueError,match='Collision'):install(package,target)
    with storage.store_context(target.parent):
        assert storage.revision()==version and len(storage.logical_paths(target))==2


def test_copy_to_another_data_directory_preserves_committed_references(monkeypatch,isolated):
    upload(ticker='A')
    history.store_history('A',observations(200),False,'2026-08-26','2026-08-27')
    relocated=isolated.parent/(isolated.name+'-relocated')
    shutil.copytree(isolated,relocated)
    with monkeypatch.context() as other:
        other.setenv('STRUCTURA_DATA_DIR',str(relocated))
        other.setattr(prices,'_PRICE_STORE',relocated/'underlying_prices')
        other.setattr(prices,'_TICKER_MAP_FILE',relocated/'underlying_prices'/'_ticker_map.json')
        assert prices._load_ticker_map()=={'A':'A'}
        assert prices.load_prices('A')['close'].tolist()==[100,101]
        assert market.load_hist_prices(['A'],'2026-08-26','2026-08-27')['prices']['A']==[200,201]
