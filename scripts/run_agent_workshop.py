"""Run actual local AI users; evidence is available in Structura's admin page.

No real application database is opened by this controller. Every worker has
its own fresh data directory. Commercial decisions come from Ollama.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['STRUCTURA_DATA_DIR']=tempfile.mkdtemp(prefix='structura-ai-controller-')
os.environ['STRUCTURA_DISABLE_SCHEDULER']='1'
from backend.app.services.agent_workshop.store import store, CampaignConfig
from backend.app.services.agent_workshop.engine import manager


def main():
    parser=argparse.ArgumentParser(description='Recette réelle de Structura par utilisateurs IA locaux')
    parser.add_argument('--months',type=int,default=12)
    parser.add_argument('--max-turns',type=int,default=800)
    parser.add_argument('--deadline-minutes',type=int,default=120)
    parser.add_argument('--model')
    parser.add_argument('--without-sg',action='store_true')
    parser.add_argument('--contract-scenario',choices=['baseline','all_complete','random'],default='baseline')
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--resume')
    args=parser.parse_args()
    # Persistent campaign evidence, separate from structura.db.
    store.root=ROOT/'backend'/'data'/'agent_workshop'
    state=store.load(args.resume) if args.resume else store.create(CampaignConfig(
        name=f'Recette IA réelle — {args.months} mois',months=args.months,max_turns=args.max_turns,
        model=args.model or 'qwen2.5-coder:7b',include_sg=not args.without_sg,contract_scenario=args.contract_scenario,seed=args.seed),1)
    print('CAMPAIGN',state['id'],'EVIDENCE',store.path(state['id']),flush=True)
    manager.start(state['id'],model=args.model);last=len(state['actions']);deadline=time.monotonic()+args.deadline_minutes*60
    try:
        while manager.thread.is_alive() and time.monotonic()<deadline:
            snapshot=manager.snapshot(state['id'])
            for action in snapshot['actions'][last:]:
                print(action['date'],action['actor'],action['tool'],action['status'],
                    json.dumps(action['result'],ensure_ascii=True)[:400],flush=True)
            last=len(snapshot['actions'])
            if snapshot['status']=='PAUSED' and snapshot.get('pause_reason')!='USER':
                print('PAUSED_FOR_DIAGNOSIS',flush=True);break
            time.sleep(1)
    finally:
        manager.shutdown()
    snapshot=manager.snapshot(state['id'])
    print('FINAL',snapshot['status'],'MONTH',snapshot['month']+1,'VOLUME',snapshot['commercial_volume'],
        'BOOKS',snapshot['book_checks'],'INCIDENTS',len(snapshot['incidents']),flush=True)
    if snapshot['status']!='COMPLETED':sys.exit(2)


if __name__=='__main__':main()
