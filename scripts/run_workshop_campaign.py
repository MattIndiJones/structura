"""Launch and supervise an explicitly requested complete native RFQ campaign."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.hybrid.launcher import Launcher
from app.hybrid.deployment import probe


def utc():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def emit(value):
    print(json.dumps(value, ensure_ascii=True), flush=True)


def run():
    launcher = Launcher()
    owned = []
    client = None
    endpoint = None
    directory = None
    manifest = {'started_at':utc(), 'driver_pid':os.getpid(), 'command':[sys.executable,str(Path(__file__).resolve())],
                'scope':'PRIVATE_SIMULATION', 'billing_enabled':False, 'max_wall_seconds':21600,
                'scenario':'12 mois commerciaux, cinq répondants et suivi jusqu’au dernier paiement',
                'role_choice':'Kepler REQUESTER; BNP/SG/Citi/UBS/Leonteq BANK; client fictif'}
    try:
        launched = launcher.launch('simulation', open_browser=False)
        owned = [c for c in (launcher.controls['admin-workbench'], launcher.platform) if launcher.owns(c)]
        manifest['services'] = launched['services']
        base = launcher.controls['admin-workbench'].public_descriptor()['url']
        client = httpx.Client(timeout=20, trust_env=False)
        reply = client.post(base+'/api/auth/development-admin-session', headers={'X-Structura-Development':'1'})
        reply.raise_for_status()
        client.headers['Authorization'] = 'Bearer '+reply.json()['access_token']
        existing = client.get(base+'/api/agent-workshop')
        existing.raise_for_status()
        if any(c.get('controller_active') for c in existing.json()):
            raise RuntimeError('Une campagne préexistante est active ; aucun autre travail interrompu.')
        config = {'name':'Campagne complète RFQ native — Kepler, cinq répondants', 'model':'qwen2.5-coder:7b',
                  'start_date':'2025-10-13', 'months':12, 'target_volume':100_000_000, 'ticket':10_000_000,
                  'max_turns':1200, 'timeout_seconds':90, 'seed':42, 'coaching':True, 'include_sg':True,
                  'contract_scenario':'all_complete', 'environment':'hybrid', 'leonteq_role':'bank', 'native_rfq':True}
        reply = client.post(base+'/api/agent-workshop',json=config)
        reply.raise_for_status()
        state = reply.json()
        endpoint = base+'/api/agent-workshop/'+state['id']
        directory = launcher.controls['admin-workbench'].data_dir/'campaigns'/state['id']
        instructions = ROOT/'docs/projects/platform/AGENT_WORKSHOP_NATIVE_RFQ_2026-10-13.md'
        manifest.update(campaign_id=state['id'], config=config, url=base+'/#/agent-workshop',
                        instructions_sha256=hashlib.sha256(instructions.read_bytes()).hexdigest())
        write(directory/'full-launch-manifest.json',manifest)
        reply = client.post(endpoint+'/start')
        reply.raise_for_status()
        emit({'campaign':state['id'],'phase':'STARTED','url':manifest['url'],'path':str(directory)})
        deadline = time.monotonic()+manifest['max_wall_seconds']
        previous = None
        stopping = False
        while True:
            reply = client.get(endpoint)
            reply.raise_for_status()
            state = reply.json()
            activity = state.get('activity') or {}
            summary = {'campaign':state['id'],'status':state['status'],'month':state['month'],
                       'commercial_months':config['months'], 'turns':state['turns'],'phase':activity.get('phase'),
                       'actor':activity.get('actor'),'registered':sum(a.get('registered',False) for a in state['actors'].values()),
                       'cases':len(state['cases']),'quotes':len(state['quotes']),
                       'booked_legs':sum(len(a.get('deals',[])) for a in state['actors'].values()),
                       'incidents':len(state['incidents']),'controller_active':state.get('controller_active'),
                       'business_date':state['business_date'],'observed_at':utc()}
            if {k:v for k,v in summary.items() if k!='observed_at'} != previous:
                emit(summary)
                previous = {k:v for k,v in summary.items() if k!='observed_at'}
            write(directory/'full-progress.json',summary)
            if state['status'] in {'COMPLETED','STOPPED','ATTENTION'} and not state.get('controller_active'):
                break
            if not stopping and (state['status']=='PAUSED' or time.monotonic()>=deadline):
                reason = 'PAUSED_'+state.get('pause_reason','UNKNOWN') if state['status']=='PAUSED' else 'WALL_BUDGET_6_HOURS'
                write(directory/'full-stop-reason.json',{'reason':reason,'requested_at':utc(),'state':summary})
                client.post(endpoint+'/stop').raise_for_status()
                stopping = True
            time.sleep(3)
        exported = client.get(endpoint+'/export')
        exported.raise_for_status()
        write(directory/'full-export.json',exported.json())
        manifest['final'] = summary
    except Exception as exc:
        manifest['error'] = str(exc)
        emit({'phase':'ERROR','error':str(exc)})
    finally:
        if endpoint and client:
            try:
                state = client.get(endpoint).json()
                if state.get('controller_active'):
                    client.post(endpoint+'/stop').raise_for_status()
                    deadline = time.monotonic()+120
                    while time.monotonic()<deadline:
                        if not client.get(endpoint).json().get('controller_active'):
                            break
                        time.sleep(.5)
            except Exception as exc:
                manifest['campaign_cleanup_error'] = str(exc)
        if owned:
            try:
                manifest['service_cleanup'] = launcher.stop(only=owned)
                manifest['owned_service_health_after_stop'] = {c.key:probe(c) for c in owned}
            except Exception as exc:
                manifest['service_cleanup_error'] = str(exc)
        if client:
            client.close()
        manifest['finished_at'] = utc()
        if directory:
            write(directory/'full-result.json',manifest)
        emit({'phase':'FINISHED','campaign':manifest.get('campaign_id'),'final':manifest.get('final'),
              'error':manifest.get('error'),'cleanup_error':manifest.get('service_cleanup_error')})


if __name__ == '__main__':
    run()
