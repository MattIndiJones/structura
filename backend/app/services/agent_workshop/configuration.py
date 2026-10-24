"""Versioned diagnostic scenarios and inexpensive, side-effect-free forecasts."""
from __future__ import annotations

from datetime import date
from dateutil.relativedelta import relativedelta
import hashlib
import json
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PARTIES = {'hector': 'Kepler Cheuvreux Solutions', 'leonteq': 'Leonteq',
           'bnp': 'BNP Paribas', 'sg': 'Société Générale', 'ca': 'Citi', 'ubs': 'UBS'}
PAYOFFS = {'reverse_convertible': 'Reverse convertible', 'phoenix': 'Phoenix',
           'autocall_athena': 'Athena classique'}
COVERAGE = ('clients', 'products', 'pricing', 'rfq', 'booking', 'lifecycle',
            'risk', 'ccr', 'documents', 'valuations', 'reinvestment', 'optimizer', 'administration', 'screens')


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class FundingPoint(StrictModel):
    month: int = Field(ge=0, le=240)
    pillars: list[list[float]] = Field(min_length=1, max_length=30)


class Economy(StrictModel):
    minimum_bps: float = Field(default=0, ge=-500, le=5000)
    maximum_bps: float = Field(default=300, ge=-500, le=5000)
    max_change_bps_per_quarter: float = Field(default=75, gt=0, le=1000)
    funding: list[FundingPoint] = Field(default_factory=lambda: [FundingPoint(month=0, pillars=[[1, 60], [3, 90], [5, 110]])], min_length=1, max_length=81)
    margin_min_bps: float = Field(default=15, ge=0, le=1000)
    margin_target_bps: float = Field(default=30, ge=0, le=1000)
    margin_max_bps: float = Field(default=80, ge=0, le=1000)

    @model_validator(mode='after')
    def coherent(self):
        if not self.minimum_bps <= self.maximum_bps or not self.margin_min_bps <= self.margin_target_bps <= self.margin_max_bps:
            raise ValueError('Bornes de funding ou de marge incohérentes.')
        if self.funding[0].month != 0 or any(a.month >= b.month for a, b in zip(self.funding, self.funding[1:])):
            raise ValueError('Le funding commence au mois 0, puis ses dates sont strictement croissantes.')
        tenors = None
        previous = None
        for point in self.funding:
            if any(len(p) != 2 for p in point.pillars):
                raise ValueError('Chaque pilier contient une maturité en années et un spread en bps.')
            current = [p[0] for p in point.pillars]
            if any(t <= 0 for t in current) or current != sorted(set(current)) or tenors is not None and current != tenors:
                raise ValueError('Les piliers sont positifs, ordonnés et identiques entre les dates.')
            if any(not self.minimum_bps <= p[1] <= self.maximum_bps for p in point.pillars):
                raise ValueError('Un spread de funding sort de ses bornes.')
            if previous and any(abs(p[1]-q[1]) > self.max_change_bps_per_quarter * (point.month-previous.month)/3 + 1e-9 for p, q in zip(point.pillars, previous.pillars)):
                raise ValueError('La variation du funding dépasse le maximum trimestriel choisi.')
            previous, tenors = point, current
        return self


class Participant(StrictModel):
    key: Literal['hector', 'leonteq', 'bnp', 'sg', 'ca', 'ubs']
    active: bool = True
    request_rfq: bool = False
    respond_rfq: bool = False
    issue_notes: bool = False
    note_ready: bool = True
    otc_ready: bool = False
    concentration_limit_eur: float | None = Field(default=None, gt=0)
    bilateral_limit_eur: float = Field(default=1_000_000_000, gt=0)
    economy: Economy | None = None


class ProductSettings(StrictModel):
    template: Literal['reverse_convertible', 'phoenix', 'autocall_athena']
    nominal: float = Field(default=10_000_000, gt=0, le=1e9)
    maturity_months: int = Field(default=36, ge=6, le=60)
    coupon_percent: float = Field(default=8, ge=0, le=30)
    barrier_percent: float = Field(default=60, ge=1, le=100)
    tickers: list[str] = Field(default_factory=lambda: ['AIR.PA'], min_length=1, max_length=5)
    spot_overrides: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode='after')
    def unique_tickers(self):
        if len(set(self.tickers)) != len(self.tickers) or any(not t.strip() or len(t) > 40 for t in self.tickers):
            raise ValueError('Les sous-jacents doivent être uniques et renseignés.')
        if any(t not in self.tickers or v <= 0 for t, v in self.spot_overrides.items()):
            raise ValueError('Les cours explicites doivent être positifs et associés aux sous-jacents du produit.')
        return self


class RfqSlot(StrictModel):
    requester: str | None = None
    template: str | None = None
    recipients: list[str] = Field(default_factory=list)


class CalendarMonth(StrictModel):
    month: int = Field(ge=1, le=120)
    count: int = Field(default=0, ge=0, le=1000)
    slots: list[RfqSlot] = Field(default_factory=list, max_length=1000)


class Cadences(StrictModel):
    risk_days: Literal[15, 30] = 30
    mtm_months: Literal[1, 3, 6, 12] = 3
    mtm_on_events: bool = False
    pricing_paths: int = Field(default=2000, ge=1000, le=20000)


def default_participants():
    rows = []
    for key in PARTIES:
        rows.append(Participant(key=key, active=key != 'ubs', request_rfq=key in {'hector', 'leonteq'},
                                respond_rfq=key in {'bnp', 'sg', 'ca'}, issue_notes=key in {'bnp', 'sg', 'ca'},
                                otc_ready=key in {'bnp', 'sg'}))
    return rows


def default_products():
    return [ProductSettings(template='reverse_convertible', maturity_months=12),
            ProductSettings(template='phoenix', maturity_months=36, coupon_percent=2),
            ProductSettings(template='autocall_athena', maturity_months=60)]


def default_calendar():
    return [CalendarMonth(month=1, count=1, slots=[RfqSlot(requester='leonteq', template='reverse_convertible')]),
            CalendarMonth(month=2, count=1, slots=[RfqSlot(requester='hector', template='phoenix', recipients=['sg'])]),
            CalendarMonth(month=3, count=2, slots=[RfqSlot(requester='leonteq', template='autocall_athena', recipients=['bnp']), RfqSlot(requester='hector', template='reverse_convertible')])]


def is_diagnostic(config):
    return config.get('schema_version', 1) == 2


def participants(config):
    return {p['key']: p for p in config['participants'] if p['active']}


def schedule(config):
    parties = participants(config)
    requesters = [k for k, p in parties.items() if p['request_rfq']]
    products = {p['template']: p for p in config['products']}
    tasks = []
    for row in sorted(config['calendar'], key=lambda r: r['month']):
        if row['count'] and not requesters:
            raise ValueError('Aucun demandeur actif pour les RFQ prévues.')
        for index in range(row['count']):
            slot = row['slots'][index] if index < len(row['slots']) else {}
            sender = slot.get('requester') or requesters[len(tasks) % len(requesters)]
            template = slot.get('template') or list(products)[len(tasks) % len(products)]
            recipients = slot.get('recipients') or [k for k, p in parties.items() if k != sender and p['respond_rfq'] and p['issue_notes']]
            if sender not in requesters or template not in products or not recipients:
                raise ValueError('Demandeur, payoff ou destinataires non disponibles dans le calendrier.')
            if len(set(recipients)) != len(recipients) or any(k == sender or k not in parties or not parties[k]['respond_rfq'] or not parties[k]['issue_notes'] for k in recipients):
                raise ValueError('Destinataire non habilité ou réponse à sa propre RFQ.')
            tasks.append({'id': f'CASE-{len(tasks)+1:04d}', 'month': row['month']-1, 'requester': sender,
                          'template': template, 'recipients': recipients, 'product': products[template]})
    return tasks


def validate_scenario(config):
    if config.get('market_mode') == 'historical':
        start = date.fromisoformat(config['start_date'])
        if not config.get('end_date'):
            raise ValueError('La date finale du rejeu historique doit être renseignée.')
        end = date.fromisoformat(config['end_date'])
        if not start < end <= date.today():
            raise ValueError('La fenêtre historique commence avant sa date finale, au plus tard aujourd’hui.')
        if any(r['count'] and start+relativedelta(months=r['month']-1) > end for r in config['calendar']):
            raise ValueError('Une nouvelle RFQ dépasse la date finale de la campagne.')
    if config['environment'] != 'hybrid' or not config['native_rfq']:
        raise ValueError('Les nouveaux diagnostics utilisent les installations hybrides et le RFQ natif.')
    if len({p['key'] for p in config['participants']}) != len(config['participants']):
        raise ValueError('Une organisation figure plusieurs fois.')
    if len({p['template'] for p in config['products']}) != len(config['products']) or not config['products']:
        raise ValueError('Sélectionnez des payoffs distincts.')
    if len({r['month'] for r in config['calendar']}) != len(config['calendar']):
        raise ValueError('Un mois figure plusieurs fois.')
    if any(r['month'] > config['horizon_months'] and r['count'] or len(r['slots']) > r['count'] for r in config['calendar']):
        raise ValueError('Le calendrier dépasse la durée ou contient plus de détails que de RFQ.')
    if any(p['respond_rfq'] and not p['issue_notes'] for p in config['participants'] if p['active']):
        raise ValueError('Un répondant aux notes doit avoir une politique d’émetteur explicite.')
    if sum(r['count'] for r in config['calendar']) > 5000:
        raise ValueError('Maximum 5 000 RFQ par campagne de diagnostic.')
    tasks = schedule(config)
    return tasks


def funding_at(config, key, month):
    policy = participants(config)[key].get('economy') or config['economy_common']
    points = policy['funding']
    left = next((p for p in reversed(points) if p['month'] <= month), points[0])
    right = next((p for p in points if p['month'] > month), left)
    weight = (month-left['month'])/(right['month']-left['month']) if left != right else 0
    return [[a[0], (a[1]+weight*(b[1]-a[1]))/10000] for a, b in zip(left['pillars'], right['pillars'])], policy


def preview(config):
    """Forecast only: never query providers, launch workers or price products."""
    from .openai_model import MODELS
    tasks = validate_scenario(config)
    quotes = sum(len(t['recipients']) for t in tasks)
    historical = config.get('market_mode') == 'historical'
    end = config['horizon_months']
    if historical:
        start, cutoff = date.fromisoformat(config['start_date']), date.fromisoformat(config['end_date'])
        end = (cutoff.year-start.year)*12+cutoff.month-start.month+int(cutoff.day>start.day)
    else:
        end = max([end]+[t['month']+t['product']['maturity_months']+1 for t in tasks])
    lives = [min(t['product']['maturity_months'], max(0,end-t['month'])) if historical else t['product']['maturity_months'] for t in tasks]
    mtms = sum(4*(2+math.ceil(life/config['cadences']['mtm_months'])) for life in lives)
    if config['cadences']['mtm_on_events']:
        mtms += sum(4*(1+math.ceil(t['product']['maturity_months']/(3 if t['template']=='phoenix' else 12))) for t in tasks)
    pricings = quotes+3*len(tasks)
    calls = quotes + 2*len(tasks)
    rates = MODELS.get(config['model'], {}) if config['provider'] == 'openai' else {}
    # Measured pilots: 19 calls / 0.0063816 USD for one RFQ with five banks.
    central = calls*(2600*rates.get('input', 0)+180*rates.get('output', 0))/1_000_000
    coverage_jobs = len(config['coverage_modules'])
    path_scale = config['cadences']['pricing_paths']/2000
    maturity_scale = max(1, sum(t['product']['maturity_months'] for t in tasks)/max(1,len(tasks))/24)
    risk_reports = math.ceil((end+1)*30/config['cadences']['risk_days'])*(len(participants(config))+1)
    seconds = calls*5 + (quotes+mtms)*3*path_scale*maturity_scale + risk_reports*1.5 + coverage_jobs*15 + 60
    warnings = []
    if central*2.5 > config['max_ai_cost_usd'] and config['provider'] == 'openai':
        warnings.append('La borne haute estimée dépasse le plafond API.')
    if calls > config['max_model_calls']:
        warnings.append('Le plafond d’appels peut interrompre ce scénario.')
    if seconds*2 > config['max_wall_minutes']*60:
        warnings.append('La durée haute estimée dépasse la limite de temps réel.')
    if not tasks:
        warnings.append('Aucune RFQ prévue : les parcours dépendant d’un produit seront non testés.')
    market_sources=[]
    if historical:
        from .historical_market import sources
        market_sources, market_warnings = sources(config)
        warnings.extend(market_warnings)
    fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return {'config_hash': fingerprint, 'rfqs': len(tasks), 'quotes': quotes, 'pricings_high':pricings, 'mtms_high': mtms,
            'risk_reports_high': risk_reports,
            'coverage_jobs': coverage_jobs, 'model_calls': {'low': round(calls*.8), 'central': calls, 'high': calls},
            'cost_usd': {'low': round(central*.6, 4), 'central': round(central, 4), 'high': round(central*2.5, 4)},
            'duration_minutes': {'low': round(seconds/120, 1), 'central': round(seconds/60, 1), 'high': round(seconds/30, 1)},
            'end_month': end, 'end_date':config.get('end_date'), 'market_mode':config.get('market_mode','synthetic'),
            'market_sources':market_sources, 'warnings': warnings, 'pricing_source': 'Catalogue local daté du 14/10/2026',
            'assumptions': ['Toutes les RFQ sont cotées ; toutes les notes sont bookées et survivent à leur maturité pour la charge haute.',
                            '2 600 tokens d’entrée et 180 de sortie par décision ; provision de longueur des réponses, aucun retry automatique.',
                            'Durée indicative basée sur les pilotes ; calculs locaux non facturés par OpenAI.',
                            'Une décision par cotation, offre et acceptation client. RFQ, confirmations et bookings natifs déterministes.',
                            'Arrêt à la date finale historique ; contrats encore vivants conservés avec un MtM résiduel.' if historical else 'Scénario synthétique ancien : suivi jusqu’au dernier paiement.',
                            'Aucun commentaire IA de risque ; aucune inscription ; aucune seconde validation testée.'],
            'forecast_version': 2}
