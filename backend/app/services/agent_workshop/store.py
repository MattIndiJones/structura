from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, date, timezone
from dateutil.relativedelta import relativedelta
import json
import hashlib
import os
import random
from typing import Literal
from pathlib import Path
from threading import RLock
from uuid import uuid4
from pydantic import BaseModel, Field, model_validator
from ...runtime import data_path
from .persistence import atomic_write
from .configuration import (Participant, ProductSettings, CalendarMonth, Economy, Cadences,
    default_participants, default_products, default_calendar, validate_scenario, preview, COVERAGE)


class CampaignConfig(BaseModel):
    schema_version: Literal[1, 2] = 1
    horizon_months: int = Field(default=60, ge=1, le=120)
    market_mode: Literal['synthetic', 'historical'] = 'synthetic'
    end_date: str | None = None
    participants: list[Participant] = Field(default_factory=default_participants, min_length=1, max_length=6)
    products: list[ProductSettings] = Field(default_factory=default_products, max_length=3)
    calendar: list[CalendarMonth] = Field(default_factory=default_calendar, max_length=120)
    economy_common: Economy = Field(default_factory=Economy)
    cadences: Cadences = Field(default_factory=Cadences)
    max_wall_minutes: int = Field(default=60, ge=1, le=1440)
    coverage_modules: list[str] = Field(default_factory=lambda: list(COVERAGE))
    name: str = Field(default="Une année avec Hector", min_length=1, max_length=100)
    provider: Literal['ollama', 'openai'] = 'ollama'
    model: str = Field(default="qwen2.5-coder:7b", min_length=1, max_length=100)
    start_date: str = Field(default_factory=lambda:(date.today()-relativedelta(years=1)).isoformat())
    months: int = Field(default=12, ge=1, le=60)
    maturity_months: int = Field(default=6, ge=6, le=60)
    payoff_templates: list[Literal['reverse_convertible', 'phoenix', 'autocall_athena']] = Field(default_factory=list, max_length=3)
    target_volume: float = Field(default=100_000_000, gt=0, le=1e10)
    ticket: float = Field(default=10_000_000, gt=0, le=1e9)
    max_turns: int = Field(default=800, ge=10, le=5000)
    timeout_seconds: int = Field(default=90, ge=10, le=180)
    max_ai_cost_usd: float = Field(default=5, ge=0.01, le=500)
    max_model_calls: int = Field(default=1500, ge=1, le=20000)
    seed: int = Field(default=42, ge=0, le=2147483647)
    coaching: bool = True
    exploratory_actions: bool = False
    include_sg: bool = True
    contract_scenario: Literal['baseline','all_complete','random'] = 'baseline'
    environment: Literal['legacy', 'hybrid'] = 'hybrid'
    leonteq_role: Literal['bank'] = 'bank'
    native_rfq: bool = True
    @model_validator(mode='after')
    def validate_model_selection(self):
        if self.provider == 'openai':
            from .openai_model import MODELS
            if self.model not in MODELS:
                raise ValueError('Modèle OpenAI non proposé pour la simulation.')
            if self.environment != 'hybrid':
                raise ValueError('OpenAI est réservé aux installations fictives hybrides de simulation.')
        if len(set(self.payoff_templates)) != len(self.payoff_templates):
            raise ValueError('Chaque payoff ne doit figurer qu’une fois dans le plan de campagne.')
        self.start_date = self.validate_start(self.start_date)
        if self.schema_version == 2:
            if len(set(self.coverage_modules)) != len(self.coverage_modules) or set(self.coverage_modules)-set(COVERAGE):
                raise ValueError('Module de couverture inconnu ou dupliqué.')
            validate_scenario(self.model_dump())
        return self
    @classmethod
    def validate_start(cls, value):
        from datetime import date
        return date.fromisoformat(value).isoformat()


ACTORS = {
    "hector": {"name": "Hector", "entity": "Maison Hector", "role": "issuer", "goal": "100 M€ de ventes clients, satisfaction et marge maîtrisée", "colour": "#15375a"},
    "bnp": {"name": "BNP", "entity": "BNP Paribas", "role": "bank", "goal": "15 % du volume bancaire, marge positive", "colour": "#176447"},
    "ca": {"name": "Crédit Agricole", "entity": "Crédit Agricole CIB", "role": "bank", "goal": "30 % du volume bancaire, marge et documentation maîtrisées", "colour": "#008177"},
    "sg": {"name": "Société Générale", "entity": "Société Générale", "role": "bank", "goal": "40 % du volume bancaire, service et marge", "colour": "#b12d39"},
    "client": {"name": "Élodie", "entity": "Gestion Élodie", "role": "client", "goal": "Investir avec des termes compris et un interlocuteur réactif", "colour": "#7950a0"},
    "achille": {"name": "Achille", "entity": "Supervision", "role": "supervisor", "goal": "Identifier les bugs et améliorer les usages", "colour": "#9a6b27"},
}


class Store:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(os.environ.get("STRUCTURA_WORKSHOP_ROOT", data_path("agent_workshop")))
        self.lock = RLock()

    def path(self, key):
        if not isinstance(key, str) or len(key) != 32 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("Référence de campagne invalide.")
        return self.root / key

    def load(self, key):
        with self.lock:
            return json.loads((self.path(key) / "campaign.json").read_text(encoding="utf-8"))

    def save(self, state):
        with self.lock:
            state['updated_at']=datetime.utcnow().isoformat()
            directory = self.path(state["id"])
            directory.mkdir(parents=True, exist_ok=True)
            atomic_write(directory/'campaign.json',json.dumps(state, ensure_ascii=False, allow_nan=False, indent=2))

    def create(self, config, owner):
        state = self.initial_state(config, owner)
        self.save(state)
        return state

    def initial_state(self, config, owner):
        config.start_date = CampaignConfig.validate_start(config.start_date)
        actors = deepcopy(ACTORS)
        if not config.include_sg:
            actors.pop("sg")
        if config.environment == 'hybrid':
            actors['hector'].update(name='Kepler', entity='Kepler Cheuvreux Solutions', organization_key='kepler-cheuvreux-solutions')
            actors['ca'].update(name='Citi', entity='Citigroup', organization_key='citi')
            actors['ubs'] = {**deepcopy(ACTORS['bnp']), 'name':'UBS', 'entity':'UBS', 'organization_key':'ubs', 'colour':'#a52f3d'}
            actors['leonteq'] = {**deepcopy(ACTORS['bnp']),
                                 'name':'Leonteq', 'entity':'Leonteq', 'organization_key':'leonteq', 'colour':'#6b4ba2'}
            for key, actor in actors.items():
                if actor['role'] == 'bank':
                    actor['goal'] = 'Coter les demandes reçues avec un prix privé, une marge motivée et des termes valides.'
        if config.schema_version == 2:
            enabled = {p.key: p for p in config.participants if p.active}
            actors = {k: a for k, a in actors.items() if k in enabled or k in {'client', 'achille'}}
            for key, policy in enabled.items():
                actors[key]['role'] = 'issuer' if policy.request_rfq else 'bank'
                actors[key]['capabilities'] = policy.model_dump(exclude={'economy'})
                actors[key]['goal'] = 'Exécuter les tâches prévues, décider sur les faits natifs et signaler les anomalies, sans objectif de volume imposé.'
        requester_keys = [key for key, actor in actors.items() if actor['role'] == 'issuer']
        for key in requester_keys:
            if config.schema_version == 1:
                actors[key]['goal']=f"Participer à l'objectif commun de {config.target_volume/1_000_000:g} M€ ; satisfaction et marge maîtrisée, sans forcer une vente."
        for key, actor in actors.items():
            actor.update(id=key, status="À préparer", registered=False, memory=[], history=[], relations={}, prices={}, deals=[], crm={})
        from ...core.calendars import adjust, BusinessDayConvention
        from datetime import date
        initial = adjust(date.fromisoformat(config.start_date), "EUR", BusinessDayConvention.FOLLOWING).isoformat()
        state = {"id": uuid4().hex, "owner": owner, "config": config.model_dump(),
            "status": "DRAFT", "created_at": datetime.utcnow().isoformat(),
            "business_date": initial, "month": 0, "turns": 0, "actors": actors,
            "messages": [], "actions": [], "incidents": [], "cases": {}, "quotes": [],
            "accepted": {}, "client_offers": {}, "client_acceptances": [], "coverage": {
                "registration_ui":"NOT_EXERCISED", "bilateral_isda_csa":"NOT_EXERCISED", "crm":"NOT_EXERCISED",
                "native_pricing":"NOT_EXERCISED", "notes_booking":"NOT_EXERCISED", "native_mtm":"NOT_EXERCISED",
                "sourced_manual_fixings":"NOT_EXERCISED", "otc_credit_risk":"NOT_EXERCISED", "margin_calls":"NOT_EXERCISED",
                "counterparty_default":"NOT_EXERCISED", "hector_own_issuance":"NOT_EXERCISED", "reinvestment":"NOT_EXERCISED",
                "historical_market":"NOT_EXERCISED", "inter_entity_rfq_network":"NOT_EXERCISED" if config.native_rfq else "DEFERRED"},
            "milestones": [], "usage": {"duration_seconds": 0, "model_calls": 0,
                "model_input_tokens": 0, "model_output_tokens": 0, "model_cost_usd": 0.0}, "processes": []}
        if config.schema_version == 2:
            state['forecast'] = preview(config.model_dump())
            state['coverage_matrix'] = {m: {'status': 'NOT_TESTED', 'evidence': []} for m in config.coverage_modules}
            state['checkpoint'] = {'completed_tasks': [], 'current_task': None, 'pending_tasks': []}
            state['coverage']['registration_ui'] = 'OUT_OF_SCOPE'
            state['coverage']['bank_second_validation'] = 'OUT_OF_SCOPE'
        return state

    def configure(self, key, owner, config):
        with self.lock, self.lifecycle_guard(key):
            old = self.load(key)
            if old['owner'] != owner:
                raise FileNotFoundError('Campagne introuvable.')
            if old.get('run_manifests') or old.get('config_frozen_at') or old['status'] != 'DRAFT':
                raise ValueError('La configuration est figée après le premier démarrage.')
            updated = self.initial_state(config, owner)
            updated.update(id=key, created_at=old['created_at'])
            self.save(updated)
            return updated

    @contextmanager
    def lifecycle_guard(self, key):
        """Serialize starts and resets across controllers, outside movable data."""
        from .lease import CampaignLease
        self.path(key)
        with self.lock:
            directory = self.root / '_locks' / key
            if directory.resolve() != self.root.resolve() / '_locks' / key:
                raise ValueError('Dossier de verrouillage invalide.')
            directory.mkdir(parents=True, exist_ok=True)
            lease = CampaignLease(directory)
            try:
                yield
            finally:
                lease.close()

    def archive(self, key):
        """Remove from the list while retaining all private files for recovery."""
        source = self.path(key)
        root = self.root.resolve()
        destination = self.root / '_archive' / f'{key}-{uuid4().hex}'
        if source.resolve() != root / key or destination.resolve().parent != root / '_archive':
            raise ValueError('Dossier de campagne invalide ; opération annulée.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        return destination

    def restart(self, key, owner):
        """Replace a stopped campaign with fresh installations and identical settings."""
        previous = self.load(key)
        fresh = self.initial_state(CampaignConfig(**previous['config']), owner)
        backup = self.archive(key)
        try:
            self.save(fresh)
        except Exception:
            # A partially written replacement must never hide the previous run.
            if self.path(fresh['id']).exists():
                self.archive(fresh['id'])
            backup.rename(self.path(key))
            raise
        return fresh

    def replay(self, key, owner):
        previous = self.load(key)
        configuration = previous['config']
        if configuration.get('schema_version', 1) == 1:
            from .diagnostic import convert_legacy
            configuration = convert_legacy(previous)
        fresh = self.initial_state(CampaignConfig(**configuration), owner)
        fresh['replay_of'] = key
        try:
            self.save(fresh)
        except Exception:
            if self.path(fresh['id']).exists():
                self.archive(fresh['id'])
            raise
        return fresh

    def issue_reviews(self, key):
        try:
            return json.loads((self.path(key) / 'issue_reviews.json').read_text(encoding='utf-8'))
        except FileNotFoundError:
            return {}

    def review_issue(self, key, owner, issue_id, review):
        # Separate annotations cannot be overwritten by a running CLI controller.
        with self.lifecycle_guard(key):
            state = self.load(key)
            if state['owner'] != owner:
                raise FileNotFoundError('Campagne introuvable.')
            known = any(i.get('id') == issue_id for i in state.get('incidents', []))
            if not known and issue_id.startswith('action-') and issue_id[7:].isdigit():
                index = int(issue_id[7:])
                known = index < len(state.get('actions', [])) and state['actions'][index].get('status') == 'FAILED'
            if not known:
                raise FileNotFoundError('Signalement introuvable.')
            reviews = self.issue_reviews(key)
            entry = dict(review, reviewed_by=owner, reviewed_at=datetime.now(timezone.utc).isoformat())
            entry['history'] = reviews.get(issue_id, {}).get('history', []) + [entry.copy()]
            reviews[issue_id] = entry
            atomic_write(self.path(key) / 'issue_reviews.json', json.dumps(reviews, ensure_ascii=False, allow_nan=False, indent=2))
            return entry

    def command(self, key, action):
        with self.lock:
            path=self.path(key)
            command={"id":uuid4().hex,"action":action}
            atomic_write(path/'control.json',json.dumps(command))
            return command

    def read_command(self, key):
        try:return json.loads((self.path(key)/'control.json').read_text(encoding='utf-8'))
        except FileNotFoundError:return None

    def list(self, owner):
        if not self.root.exists():
            return []
        rows = []
        for path in self.root.glob("*/campaign.json"):
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
                if state["owner"] == owner:
                    rows.append({**{k: state[k] for k in ("id", "status", "created_at", "business_date", "config", "turns")},'month':state.get('month', 0),'replay_of':state.get('replay_of'),'updated_at':state.get('updated_at',state['created_at'])})
            except (ValueError, OSError, KeyError):
                continue
        return sorted(rows, key=lambda x: x["updated_at"], reverse=True)


store = Store()


def contract_mandate(state):
    """Reproducible contractual prerequisites; never commercial outcomes."""
    if state['config'].get('schema_version') == 2:
        return {**{p['key']: {'note_ready': p['note_ready'], 'otc_ready': p['otc_ready']}
                   for p in state['config']['participants'] if p['active']}, 'client': {'note_ready': True, 'otc_ready': False}}
    scenario=state['config'].get('contract_scenario','baseline')
    rng=random.Random(state['config']['seed'])
    banks=[k for k,a in state['actors'].items() if a['role']=='bank']
    result={k:{'note_ready':scenario=='all_complete' or (rng.choice([True,False]) if scenario=='random' else k!='ca'),
               'otc_ready':scenario=='all_complete' or (rng.choice([True,False]) if scenario=='random' else k!='ca')} for k in banks}
    result['client']={'note_ready':True,'otc_ready':False}
    return result


def source_manifest(include_git=False):
    root=Path(__file__).resolve().parents[4]
    sources=list((root/'backend/app').rglob('*.py'))
    sources += list((root/'frontend/dist').rglob('*.js')) + list((root/'frontend/dist').rglob('*.css'))
    sources += [root/'frontend/dist/index.html']
    result={'captured_at':datetime.utcnow().isoformat(),'source_sha256':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources if p.exists()}}
    if include_git:
        import subprocess
        for key,args in (('git_head',['rev-parse','HEAD']),('git_branch',['branch','--show-current'])):
            command=subprocess.run(['git',*args],cwd=root,capture_output=True,text=True,timeout=5,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            result[key]=command.stdout.strip() if command.returncode==0 else None
        result['working_files']='Empreintes du code réellement exécuté, y compris les modifications locales.'
    return result
