"""Qualified adapters: script declarations own fields; policies own search roles."""
import hashlib
from copy import deepcopy

from ..payscript.catalogue import PRODUCTS
from ..payscript.parser import parse_script


RANGE_POLICIES = {
    "M_KI_BAR": dict(key="protection_barrier", label="Protection (%)", minimum=.3, maximum=1., step=.005, initial=.6),
    "M_AC_BAR": dict(key="autocall_trigger", label="Rappel initial (%)", minimum=.8, maximum=1.2, step=.005, initial=1.),
    "M_CPN_BAR": dict(key="coupon_barrier", label="Barrière coupon (%)", minimum=.3, maximum=1., step=.005, initial=.7),
    "STRIKE": dict(key="strike", label="Strike de participation (%)", minimum=.5, maximum=1.5, step=.005, initial=1.),
    "CAP": dict(key="redemption_cap", label="Cap de remboursement (%)", minimum=1., maximum=3., step=.005, initial=1.3),
    "M_PUT_STRIKE": dict(key="put_strike", label="Strike du put (%)", minimum=.3, maximum=1.2, step=.005, initial=.6),
    "GEARING": dict(key="gearing", label="Levier du put (×)", minimum=1., maximum=5., step=.1, initial=2., unit="multiple"),
}
MATURITY = dict(key="maturity_months", label="Maturité (mois)", minimum=12, maximum=60, step=1, initial=36, unit="months")
STEP_DOWN_FIELDS = [
    dict(key="decrement", label="Baisse par constatation — points %", minimum=0, maximum=.2, step=.005, initial=.025, unit="fraction", script_param="M_AC_BAR"),
    dict(key="floor", label="Plancher de rappel (%)", minimum=.3, maximum=1.2, step=.005, initial=.8, unit="fraction", script_param="M_AC_BAR"),
    dict(key="first_decrease_rank", label="Première constatation avec baisse", minimum=2, maximum=60, step=1, initial=2, unit="rank", script_param="M_AC_BAR"),
]
ADAPTERS = {
    "autocall_athena": dict(params={"COUPON":"scalar", "M_AC_BAR":"scalar", "M_KI_BAR":"scalar"}, coupon_labels=["Coupons cumulés"], coupon_rule="Coupon par période cumulé et payé au rappel ; aucun coupon sans rappel.", has_autocall=True),
    "phoenix": dict(params={"COUPON":"scalar", "M_AC_BAR":"scalar", "M_CPN_BAR":"scalar", "M_KI_BAR":"scalar"}, coupon_labels=["Coupon conditionnel"], coupon_rule="Coupon par période payé si la barrière coupon tient ; coupon manqué définitivement perdu.", has_autocall=True),
    "phoenix_memoire": dict(params={"COUPON":"scalar", "M_AC_BAR":"scalar", "M_CPN_BAR":"scalar", "M_KI_BAR":"scalar"}, coupon_labels=["Coupon et rattrapage"], coupon_rule="Coupons manqués rattrapés au prochain paiement ; mémoire non payée si la barrière coupon ne tient jamais à nouveau.", has_autocall=True),
    "autocall_barriere_degressive": dict(params={"COUPON":"scalar", "M_AC_BAR":"array", "M_KI_BAR":"scalar"}, coupon_labels=["Coupons cumulés"], coupon_rule="Coupon par période cumulé au rappel ; seuil de rappel dégressif explicite par constatation.", has_autocall=True),
    "reverse_convertible": dict(params={"COUPON":"scalar", "M_KI_BAR":"scalar"}, coupon_labels=["Coupon"], coupon_rule="Coupon unique à maturité, égal au coupon annuel nominal × maturité en mois / 12 ; aucun rappel.", has_autocall=False),
    "capital_garanti": dict(params={"PART":"scalar", "STRIKE":"scalar"}, coupon_labels=["Participation à la hausse"], coupon_rule="Nominal protégé à maturité, hors défaut émetteur ; participation à la hausse au-dessus du strike, sans coupon ni rappel.", has_autocall=False, objectives=["maximize_participation"], solved="PART"),
    "booster": dict(params={"PART":"scalar", "CAP":"scalar"}, coupon_labels=["Participation plafonnée"], coupon_rule="Hausse démultipliée, remboursement plafonné ; baisse subie une pour une. Cap 130 % = gain maximal 30 %, hors défaut émetteur.", has_autocall=False, objectives=["maximize_participation","maximize_cap"], solved="PART", risk_severity=True),
    "autocall_gear_put": dict(params={"COUPON":"scalar", "M_AC_BAR":"scalar", "M_PUT_STRIKE":"scalar", "GEARING":"scalar"}, coupon_labels=["Coupon"], coupon_rule="Coupon unique au rappel, sans INDEX ni cumul ; perte sous le strike du put démultipliée par le gearing et plafonnée au nominal.", has_autocall=True, objectives=["maximize_coupon","target_coupon"], risk_severity=True, coupon_unit="total"),
}
OBJECTIVE_LABELS = {"maximize_coupon":"Maximiser le coupon", "maximize_protection":"Maximiser la protection", "target_coupon":"Coupon cible et meilleure protection", "maximize_participation":"Maximiser la participation", "maximize_cap":"Maximiser le cap à participation imposée"}
CAPITAL_LOSS_LABELS = {"booster":["Put vendu — perte en capital"],
                       "autocall_gear_put":["Put vendu avec levier, perte plafonnée au capital"]}


def _mode_schema(key, policy, parsed, objective):
    solved = "CAP" if objective == "maximize_cap" else policy.get("solved","COUPON")
    quantity = {"COUPON":"coupon","PART":"participation","CAP":"redemption_cap"}[solved]
    unit = policy.get("coupon_unit","annual") if solved == "COUPON" else "fraction"
    label = "Coupon unique (%)" if unit == "total" else "Coupon annuel nominal (%)" if solved == "COUPON" else "Participation (%)" if solved == "PART" else "Cap de remboursement (%)"
    bounds = (0.,.5,0.,.3) if solved == "COUPON" else (0.,5.,0.,3.) if solved == "PART" else (1.,3.,1.01,2.)
    bound_prefix = "cap" if solved == "CAP" else quantity
    solution = dict(key=quantity,script_param=solved,label=label,unit="fraction",value_convention=unit,
                    minimum=bounds[0],maximum=bounds[1],initial_minimum=bounds[2],initial_maximum=bounds[3],
                    minimum_key=bound_prefix+"_minimum",maximum_key=bound_prefix+"_maximum")
    fields, fixed, parameters = [deepcopy(MATURITY)], [], []
    for p in parsed.params:
        if p.name == solved:
            binding,role = quantity,"solved"
        elif p.name == "PART":
            binding,role = "participation","fixed"
            fixed.append(dict(key=binding,label="Participation imposée (%)",minimum=.005,maximum=5.,step=.005,initial=1.5,unit="fraction",script_param=p.name))
        else:
            field=deepcopy(RANGE_POLICIES[p.name]);field.setdefault("unit","fraction");field["script_param"]=p.name
            fields.append(field);binding,role=field["key"],"range"
        parameters.append(dict(name=p.name,kind=p.kind,required=p.required,unit="fraction",default=p.stored_val,role=role,binding=binding))
    if policy["params"].get("M_AC_BAR") == "array": fixed.extend(deepcopy(STEP_DOWN_FIELDS))
    x = dict(key="protection_barrier",label="Barrière de protection (%)",unit="fraction",preference="min")
    if key == "capital_garanti": x.update(key="strike",label="Strike de participation (%)")
    if key == "booster": x.update(key="expected_capital_loss" if objective=="maximize_cap" else "redemption_cap",label="Perte en capital moyenne Q (%)" if objective=="maximize_cap" else "Cap de remboursement (%)",preference="min" if objective=="maximize_cap" else "max")
    if key == "autocall_gear_put": x.update(key="put_strike",label="Strike du put (%)")
    return dict(script_parameters=parameters,range_fields=fields,fixed_fields=fixed,solved_field=solution,
                solved_parameters=[quantity],frontier=dict(x=x,y=dict(key=quantity,label=label,unit="fraction",preference="max")),
                optimization_parameters=[f["key"] for f in fields]+(["observation_months"] if policy["has_autocall"] else []))


def family_schema(key, objective=None):
    policy = ADAPTERS[key]
    product = PRODUCTS[key]
    parsed = parse_script(product["script"])
    declarations = {p.name:p.kind for p in parsed.params}
    if declarations != policy["params"] or any(not p.is_pct for p in parsed.params):
        raise ValueError(f"Script {key} incompatible avec son adaptateur Optimizer ; qualification requise.")
    if any(not any(line.strip().startswith("PAY ") and f'"{label}"' in line for line in product["script"].splitlines())
           for label in policy["coupon_labels"]+CAPITAL_LOSS_LABELS.get(key,[])):
        raise ValueError(f"Libellés des flux de {key} incompatibles avec les analytics ; qualification requise.")
    calendar = "OBSERVATIONDATES" if policy["has_autocall"] else "MATURITYDATE"
    expected_constats = {"STARTDATE":"single", calendar:"schedule" if policy["has_autocall"] else "single"}
    if {c.name:c.kind for c in parsed.constats} != expected_constats or parsed.has_stop != policy["has_autocall"]:
        raise ValueError(f"Calendrier ou rappel de {key} incompatible avec son adaptateur.")
    objectives=policy.get("objectives",["maximize_coupon","maximize_protection","target_coupon"])
    objective=objective or objectives[0]
    if objective not in objectives: raise ValueError("Objectif non applicable au script sélectionné.")
    modes={name:_mode_schema(key,policy,parsed,name) for name in objectives}
    return dict(product_family=key, status="SUPPORTED", label=product["label"], description=product["description"],
                script=product["script"], script_hash=hashlib.sha256(product["script"].encode()).hexdigest(),
                **modes[objective], modes=modes,objective=objective,
                objectives=[dict(value=name,label="Coupon cible et perte en capital minimale" if key == "autocall_gear_put" and name == "target_coupon" else OBJECTIVE_LABELS[name]) for name in objectives],
                has_autocall=policy["has_autocall"], coupon_rule=policy["coupon_rule"],
                coupon_analytics=key in ("phoenix", "phoenix_memoire"),
                risk_severity=policy.get("risk_severity",False),
                models=["constant"], underlying_types=["equity","index"], basket_types=["single_asset","worst_of"],
                max_underlyings=3, observation_months=[1,3,6,12] if policy["has_autocall"] else [],
                )


def solution_scale(candidate):
    if candidate.product_family == "autocall_gear_put" or ADAPTERS[candidate.product_family].get("solved") == "PART":
        return 1.
    return candidate.observation_months/12


def solution_definition(req):
    return family_schema(req.product_family,req.objective)["solved_field"]


def solved_value(req,candidate):
    return getattr(candidate,solution_definition(req)["key"])


def coupon_labels(key):
    return ADAPTERS[key]["coupon_labels"]


def autocall_levels(candidate, settings):
    if candidate.product_family != "autocall_barriere_degressive":
        return candidate.autocall_trigger
    count = candidate.maturity_months // candidate.observation_months
    return [max(settings["floor"], candidate.autocall_trigger-settings["decrement"]*max(0,rank-settings["first_decrease_rank"]+1))
            for rank in range(1,count+1)]
