"""Independent antithetic pairs, rather than 2N independent observations."""
import math
from statistics import NormalDist

import numpy as np
from .families import family_schema, coupon_labels, CAPITAL_LOSS_LABELS


def normal_interval(mean, standard_error, alpha=.05):
    z = NormalDist().inv_cdf(1-alpha/2)
    return [float(mean-z*standard_error), float(mean+z*standard_error)]


def bounded_interval(values, low, high, alpha):
    """Two-sided empirical Bernstein bound (Maurer/Pontil, union of two tails)."""
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n < 2 or not np.isfinite(values).all() or np.any(values < low-1e-10) or np.any(values > high+1e-10):
        raise ValueError("Échantillon hors du domaine statistique.")
    log_term = math.log(4/alpha)
    radius = math.sqrt(2*float(np.var(values, ddof=1))*log_term/n)
    radius += 7*(high-low)*log_term/(3*(n-1))
    mean = float(np.mean(values))
    return [max(low, mean-radius), min(high, mean+radius)]


def summarize_paths(result, pairs, terminal, issue_price, alpha=.05, simultaneous=False, candidate=None, observation_times=None):
    paths = result.get("path_flows")
    if not paths or len(paths) != 2*pairs:
        raise ValueError("Flux par trajectoire indisponibles ou nombre incohérent.")
    losses, recalls, lives = [], [], []
    stops = result.get("path_stop_times")
    if stops is not None and (len(stops) != len(paths) or any(not math.isfinite(t) or t < 0 or t > terminal+1e-8 for t in stops)):
        raise ValueError("Dates de terminaison incohérentes.")
    for index, path in enumerate(paths):
        if not path or any(not math.isfinite(float(x)) for flow in path for x in flow):
            raise ValueError("Flux de trajectoire absents ou non finis.")
        life = stops[index] if stops is not None else max(float(t) for t, _ in path)
        losses.append(float(sum(float(amount) for _, amount in path) < issue_price-1e-10))
        recalls.append(float(life < terminal-1e-8))
        lives.append(life)
    samples = {}
    for name, data in (("probability_loss", losses), ("probability_autocall", recalls), ("expected_maturity", lives)):
        values = np.asarray(data, dtype=float)
        samples[name] = (values[:pairs]+values[pairs:])/2
    coupon_bound = None
    if candidate is not None and family_schema(candidate.product_family)["risk_severity"]:
        labels = result.get("path_flow_labels")
        if labels is None or len(labels) != len(paths): raise ValueError("Libellés de pertes indisponibles.")
        capital_losses = []
        for path,names in zip(paths,labels):
            if len(path) != len(names): raise ValueError("Libellés de flux incohérents.")
            loss = -sum(amount for (_,amount),label in zip(path,names) if label in CAPITAL_LOSS_LABELS[candidate.product_family])
            if not -1e-10 <= loss <= 1.+1e-10: raise ValueError("Perte hors du nominal.")
            capital_losses.append(min(1.,max(0.,loss)))
        values = np.asarray(capital_losses)
        samples["expected_capital_loss"] = (values[:pairs]+values[pairs:])/2
        indicators = (values > 1e-10).astype(float)
        samples["probability_capital_loss"] = (indicators[:pairs]+indicators[pairs:])/2
    if candidate is not None and family_schema(candidate.product_family)["coupon_analytics"]:
        labels = result.get("path_flow_labels")
        if labels is None or len(labels) != len(paths) or observation_times is None:
            raise ValueError("Flux de coupons ou dates de constatation indisponibles.")
        coupon_period = candidate.coupon*candidate.observation_months/12
        dt = terminal/max(1, round(terminal*52))
        dates = [round(t/dt)*dt for t in observation_times]
        paid, unpaid = [], []
        for path, names, life in zip(paths, labels, lives):
            if len(path) != len(names): raise ValueError("Libellés de flux incohérents.")
            coupon = sum(amount for (_,amount),label in zip(path,names) if label in coupon_labels(candidate.product_family))
            entitlement = coupon_period*sum(t <= life+1e-8 for t in dates)
            if coupon < -1e-8 or coupon > entitlement+1e-8: raise ValueError("Coupons hors domaine contractuel.")
            paid.append(max(0.,coupon)); unpaid.append(max(0.,entitlement-coupon))
        for name,data in (("expected_coupon_paid",paid),("expected_coupon_unpaid",unpaid)):
            values = np.asarray(data, dtype=float)
            samples[name] = (values[:pairs]+values[pairs:])/2
        coupon_bound = candidate.coupon*candidate.maturity_months/12
    means = {name: float(np.mean(values)) for name, values in samples.items()}
    errors = {name: float(np.std(values, ddof=1)/math.sqrt(pairs)) for name, values in samples.items()}
    # The engine's price/IC already use paired discounted payoffs. Its six-digit
    # output loses at most 0.5e-6 on each endpoint; round the recovered SE upwards.
    means["fair_value"] = float(result["price"])
    errors["fair_value"] = max(0., (float(result["ic95"][1])-float(result["ic95"][0])+1e-6)/3.92)
    bounds = {"fair_value": normal_interval(means["fair_value"], errors["fair_value"], alpha)}
    for name, values in samples.items():
        high = terminal if name == "expected_maturity" else coupon_bound if name.startswith("expected_coupon") else 1.
        bounds[name] = bounded_interval(values, 0., high, alpha) if simultaneous else [
            max(0., normal_interval(means[name], errors[name], alpha)[0]),
            min(high, normal_interval(means[name], errors[name], alpha)[1])]
    if not all(math.isfinite(v) for v in [*means.values(), *errors.values(), *(v for b in bounds.values() for v in b)]):
        raise ValueError("Résultat numérique non fini.")
    if result.get("corr_repair"):
        raise ValueError("Corrélation réparée par le moteur : résultat non admissible.")
    return {"pairs": pairs, "means": means, "standard_errors": errors, "bounds": bounds}


def apply_summary(candidate, summary):
    m, b = summary["means"], summary["bounds"]
    candidate.fair_value = m["fair_value"]
    candidate.price_ic95 = b["fair_value"]
    candidate.probability_loss = m["probability_loss"]
    candidate.probability_loss_ic95 = b["probability_loss"]
    candidate.probability_autocall = m["probability_autocall"]
    candidate.probability_autocall_ic95 = b["probability_autocall"]
    candidate.expected_maturity = m["expected_maturity"]
    candidate.expected_maturity_upper95 = b["expected_maturity"][1]
    if not family_schema(candidate.product_family)["has_autocall"]:
        candidate.probability_autocall = candidate.probability_autocall_ic95 = None
    for name in ("expected_coupon_paid", "expected_coupon_unpaid"):
        if name in m:
            setattr(candidate,name,m[name]); setattr(candidate,name+"_ic95",b[name])
    if "expected_capital_loss" in m:
        for name in ("expected_capital_loss", "probability_capital_loss"):
            setattr(candidate,name,m[name]); setattr(candidate,name+"_ic95",b[name])
        probability = m["probability_capital_loss"]
        candidate.conditional_capital_loss = m["expected_capital_loss"]/probability if probability > 0 else None
        loss_bound, probability_bound = b["expected_capital_loss"], b["probability_capital_loss"]
        candidate.conditional_capital_loss_ic95 = ([max(0.,loss_bound[0]/probability_bound[1]),
             min(1.,loss_bound[1]/probability_bound[0]) if probability_bound[0] > 0 else 1.] if probability_bound[1] > 0 else [0.,1.])
