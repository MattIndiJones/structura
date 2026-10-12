"""Short genuine AI run checking published phases and native contract requests.

Fresh private accounts/data only. Stop after the first native relationship has
been created; this checks live visibility, not a new annual qualification.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import socket
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
directory=ROOT/'output/agent-workshop-ui'/('live-activity-'+uuid4().hex)
directory.mkdir(parents=True)
os.environ['STRUCTURA_DATA_DIR']=str(directory/'controller')
os.environ['STRUCTURA_WORKSHOP_ROOT']=str(directory/'campaigns')
from backend.app.services.agent_workshop.store import store, CampaignConfig
from backend.app.services.agent_workshop.engine import manager

state=store.create(CampaignConfig(name='Recette de visibilité en direct',months=1,include_sg=False,max_turns=60,coaching=False),1)
key=state['id'];observed={};deadline=time.monotonic()+180
try:
    manager.start(key)
    while time.monotonic()<deadline:
        snap=manager.snapshot(key)
        activity=snap.get('activity') or {}
        phase=activity.get('phase')
        if phase and phase not in observed:
            observed[phase]={k:activity.get(k) for k in ('actor','phase','tool','started_at','request')}
        request=activity.get('request') or {}
        if request.get('status')=='PENDING' and 'NATIVE_PENDING' not in observed:
            observed['NATIVE_PENDING']={'actor':activity['actor'],'request':request}
        native=next((a for a in snap['actions'] if a['tool']=='relationship' and a['status']=='SUCCESS'),None)
        if native:
            observed['CONTRACT_RESULT']={k:native.get(k) for k in ('actor','tool','status','http_calls','started_at','completed_at')}
            break
        if snap['status'] in {'ATTENTION','STOPPED','COMPLETED'}:
            raise AssertionError('Run ended before a native contract result: '+str(snap['status']))
        time.sleep(.1)
    else:raise AssertionError('No native contract within the qualification deadline')
    assert {'THINKING','EXECUTING','CONTRACT_RESULT'}<=set(observed),observed
    assert any(c['method']=='POST' and c['path']=='/api/trading/relationships' and c['status']==201 for c in observed['CONTRACT_RESULT']['http_calls'])
finally:
    if manager.thread and manager.thread.is_alive():
        manager.control(key,'stop')
        manager.thread.join(timeout=60)
    assert not manager.thread or not manager.thread.is_alive(),'Controller still closing; inspect private process manifest'
    final=manager.snapshot(key)
    assert final['activity'] is None and final['active_actor'] is None and not final['processes']
    ports=[int(p['url'].rsplit(':',1)[-1]) for p in final.get('process_history',[])]
    for port in ports:
        with socket.socket() as connection:
            connection.settimeout(.5)
            assert connection.connect_ex(('127.0.0.1',port))!=0,port
    (directory/'visibility-proof.json').write_text(json.dumps({'checked_at':datetime.now(timezone.utc).isoformat(),'campaign_id':key,'observed':observed,'final_status':final['status'],'private_ports_closed':ports},ensure_ascii=False,indent=2),encoding='utf-8')
print('GENUINE_LIVE_ACTIVITY_OK',directory,'phases',list(observed),'closed_ports',ports,flush=True)
