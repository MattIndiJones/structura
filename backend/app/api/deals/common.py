"""Shared booking/workflow helpers: economics, calendars, RFQ identity, workflow refusals."""
from __future__ import annotations
import json
from datetime import datetime, date, timedelta
from typing import List
from fastapi import HTTPException
from sqlmodel import Session, select
from ...core.access import has_business_role
from ...db.models import Alert, Deal, User, RfqQuote, RfqRequest
from ...core.payscript.parser import parse_script, resolve_constats, effective_T_max
from ...core.audit import commit_rejection
from ...core.agregats_officiels import calculer as calculer_agregat
from ...core.rfq_controls import booking_terms_differences, product_terms, product_terms_hash
from ...core.booking_contract import DealCreate
from ...services.business_access import deal_entity_id as _deal_entity_id

# ── Helpers ───────────────────────────────────────────────────────────

def _date_plus_years(d: str, years: float) -> str:
    return (date.fromisoformat(d) + timedelta(days=round(years * 365.25))).isoformat()


def _years_between(start: str, end: str) -> float:
    """Inverse of _date_plus_years, same 365.25-day year."""
    return (date.fromisoformat(end) - date.fromisoformat(start)).days / 365.25


def _validate_economics(body) -> None:
    """Refuse what is not a trade. The booking form checks part of this, but
    the form is not the boundary — the API is, and it accepted a deal with a
    negative nominal (which then SUBTRACTS from counterparty exposure in
    api/portfolios.py), a fair value of zero (every later MtM is measured
    against it), a settlement before its own strike, or a maturity in 2020.

    Deliberately NOT checked: a counterparty outside the catalog (the field is
    a free string on purpose — see models.py:Counterparty, booked history must
    stay readable after a rename), and a strike far in the past (booking an
    old trade after the fact is legitimate)."""
    errors = []
    if not body.contrepartie or not body.contrepartie.strip():
        errors.append("la contrepartie est obligatoire")
    if body.nominal is None or body.nominal <= 0:
        errors.append(f"le nominal doit être strictement positif (reçu : {body.nominal})")
    if not body.fair_value:
        errors.append("la fair value est nulle — le P&L du deal se mesurerait contre zéro "
                      "(lancez ▶ Pricer, ou saisissez-la)")
    elif body.fair_value < 0:
        errors.append(f"la fair value ne peut pas être négative (reçu : {body.fair_value})")
    if not body.price_traded or body.price_traded <= 0:
        errors.append(f"le prix traité doit être strictement positif (reçu : {body.price_traded})")

    if body.T is None or body.T <= 0:
        errors.append(f"la maturité en années T doit être strictement positive (reçu : {body.T})")
    if not body.script_snapshot or not body.script_snapshot.strip():
        errors.append("le script contractuel est obligatoire")
    if not body.underlyings:
        errors.append("au moins un sous-jacent est obligatoire")
    if len(body.devise or "") != 3 or not body.devise.isalpha():
        errors.append(f"la devise doit être un code ISO à trois lettres (reçu : {body.devise!r})")
    body_ul_ids = [
        (str(u.get("name") or "").strip(), str(u.get("ticker") or "").strip(),
         str(u.get("ccy") or body.devise).strip().upper())
        for u in body.underlyings
    ]
    if len(set(body_ul_ids)) != len(body_ul_ids):
        errors.append("la liste des sous-jacents contient des doublons")
    market_uls = (body.market_snapshot or {}).get("underlyings") or []
    if market_uls:
        market_ul_ids = [
            (str(u.get("name") or "").strip(), str(u.get("ticker") or "").strip(),
             str(u.get("ccy") or body.devise).strip().upper())
            for u in market_uls
        ]
        if market_ul_ids != body_ul_ids:
            errors.append("les sous-jacents du deal et du snapshot de marché divergent")

    parsed_dates = {}
    for label, raw in (("trade", body.trade_date), ("strike", body.strike_date),
                       ("valeur", body.value_date), ("maturité", body.maturity_date),
                       ("règlement", body.payment_date)):
        if not raw and label == "règlement":
            continue
        try:
            parsed_dates[label] = date.fromisoformat(raw)
        except (TypeError, ValueError):
            errors.append(f"la date de {label} est invalide ({raw!r})")

    if body.maturity_date and body.value_date and body.maturity_date <= body.value_date:
        errors.append(f"la maturité ({body.maturity_date}) n'est pas postérieure à la date "
                      f"de valeur ({body.value_date})")
    if body.payment_date and body.maturity_date and body.payment_date < body.maturity_date:
        errors.append(f"le règlement ({body.payment_date}) précède la maturité "
                      f"({body.maturity_date})")
    if errors:
        raise HTTPException(422, "Booking impossible : " + " ; ".join(errors) + ".")


def _deal_product_terms(body: DealCreate) -> dict:
    """Canonical contractual identity presented by a deal booking request."""
    market = body.market_snapshot or {}
    params = {
        "underlyings": market.get("underlyings") or body.underlyings,
        "user_params": market.get("user_params") or {},
        "constats": market.get("constats") or {},
        "notional": body.nominal,
        "currency": body.devise,
        "strike_date": body.strike_date,
        "value_date": body.value_date,
        # La date de reglement final fait partie de l identite du produit : deux
        # deals identiques regles a deux dates differentes ne valent pas le meme
        # prix, l ecart se compte en points de base.
        "payment_date": body.payment_date,
        "T": body.T,
    }
    return product_terms(body.script_snapshot, params)


def _validate_rfq_booking_identity(rfq: RfqRequest, body: DealCreate,
                                   session: Session) -> None:
    """Refuse a deal that merely points at an RFQ but is not its product."""
    from ..rfq import _counterparty_by_provider, superseded_quote_ids

    quotes = session.exec(select(RfqQuote).where(RfqQuote.rfq_id == rfq.id)).all()
    selected = next((q for q in quotes if q.id == rfq.selected_quote_id), None)
    if not selected or selected.price is None:
        raise HTTPException(422, "La réponse retenue doit porter un prix final avant booking.")
    from ...services.rfq_quote_integrity import same_currency, selection_matches
    if not same_currency(session, rfq, selected) or not selection_matches(rfq, selected):
        raise HTTPException(409, "Requalifiez la sélection de cette révision et sa devise avant booking.")
    if selected.status in {"decline", "expire"}:
        raise HTTPException(422, "La réponse retenue n'est plus exécutable.")
    if selected.id in superseded_quote_ids(quotes):
        raise HTTPException(422, "La réponse retenue a été remplacée par un last look final.")
    if rfq.status == "sans_suite":
        raise HTTPException(409, "Une RFQ classée sans suite doit être rouverte avant booking.")

    expected_sens = "vente" if rfq.sens == "achat" else "achat"
    if body.sens != expected_sens:
        raise HTTPException(
            422, f"Le sens du deal ({body.sens}) ne correspond pas au sens de la RFQ "
                 f"({rfq.sens}, donc deal attendu : {expected_sens}).")

    expected_counterparty = _counterparty_by_provider(session).get(selected.provider)
    if expected_counterparty and body.contrepartie != expected_counterparty:
        raise HTTPException(
            422, f"La contrepartie du deal ({body.contrepartie}) ne correspond pas au "
                 f"fournisseur retenu ({selected.provider} → {expected_counterparty}).")

    expected = product_terms(rfq.script_snapshot, json.loads(rfq.params_json or "{}"))
    changed = booking_terms_differences(expected, _deal_product_terms(body))
    if changed:
        raise HTTPException(
            422, "Le deal ne correspond pas aux termes contractuels figés de la RFQ : "
                 + ", ".join(changed) + ". Rechargez le booking depuis la RFQ ; "
                 "pour un autre produit, créez une nouvelle RFQ.")


def _resoudre_pour_booking(body) -> tuple:
    """Le script du deal, calendrier résolu, et l'origine de son axe des temps.

    Ancré sur la constatation initiale, pas sur le règlement : le produit
    commence quand son niveau de référence est fixé. Repli sur la value date
    pour les bookings qui n'ont pas encore de date de strike.

    Extrait pour que l'échéancier figé et les temps d'observation viennent de
    la MÊME résolution. Deux résolutions séparées, c'est deux calendriers qui
    peuvent diverger — exactement ce que le figement doit empêcher."""
    origin = body.strike_date or body.value_date
    compiled = resolve_constats(
        parse_script(body.script_snapshot),
        (body.market_snapshot or {}).get("constats") or {},
        anchor=date.fromisoformat(origin) if origin else None,
        currency=(body.devise or "").strip().upper() or None,
    )
    return compiled, origin


def _fenetres_par_date(schedule_json: str) -> dict:
    """{t arrondi: {reduction, releves}} pour les constatations MOYENNÉES.

    Lu depuis l'échéancier figé, pas recalculé : c'est lui qui fait foi une fois
    le deal booké."""
    try:
        ech = json.loads(schedule_json or "{}")
    except (TypeError, ValueError):
        return {}
    return {round(c["t"], 4): {"reduction": c["reduction"], "releves": c["releves"]}
            for c in ech.get("constatations") or []
            if c.get("reduction") and c.get("releves")}


def _fenetre_de_depart(schedule_json: str) -> dict | None:
    """{reduction, releves} de la fenêtre qui fixe S₀, lue dans l'échéancier
    FIGÉ — None pour un S₀ ponctuel, ce que sont l'immense majorité des
    produits."""
    try:
        depart = (json.loads(schedule_json or "{}") or {}).get("depart")
    except (TypeError, ValueError, AttributeError):
        return None
    if not depart or not depart.get("reduction") or not depart.get("releves"):
        return None
    return {"reduction": depart["reduction"], "releves": depart["releves"]}


def _niveau_initial_constate(events: list, schedule_json: str) -> dict:
    """S₀ par sous-jacent tel que le contrat le définit — {} tant qu'il ne l'est
    pas.

    Sans fenêtre de départ, c'est le fixing du jour de strike. Avec une fenêtre
    (`CONSTAT STRIKE_FIX AVG`), c'est la réduction des cours de SES relevés, dont
    ce fixing n'est que le premier : mesurer le spot contre lui seul déplaçait
    chaque barrière de l'écart entre ce cours et S₀. Une fenêtre incomplète ne
    rend rien — la règle de l'agrégat officiel : une moyenne partielle présentée
    comme S₀ est le chiffre faux qui ne se signale pas."""
    strike = next((e for e in events
                   if e.t_years == 0.0 and e.parent_event_id is None), None)
    if strike is None:
        return {}
    depart = _fenetre_de_depart(schedule_json)
    if not depart:
        return json.loads(strike.spots_json or "{}")
    attendus = [r["date"] for r in depart["releves"] if r.get("date")]
    fournis = {}
    for e in [strike] + [e for e in events if e.parent_event_id == strike.id]:
        spots = {nom: v for nom, v in json.loads(e.spots_json or "{}").items()
                 if float(v or 0) > 0}
        if spots and e.event_date in attendus:
            fournis[e.event_date] = {"spots": spots, "version": e.fixing_version or 0}
    agregat = calculer_agregat(depart["reduction"], attendus, fournis)
    return dict(agregat.niveaux) if agregat.calculable else {}


_REDUCTION_LIBELLE = {"AVG": "moyenne", "MIN": "plus bas", "MAX": "plus haut"}


def _evenements_pour_la_note(events: list, schedule_json: str) -> tuple[list[dict], str | None]:
    """Les lignes « Constatation » de la note de valorisation client, et la
    prochaine date d'observation qu'elle annonce.

    Les relevés n'y figurent pas : un document client n'appelle pas
    « constatation » une ligne de fixing qui ne décide rien, et ne présente pas
    son premier relevé comme la prochaine observation. La fenêtre n'est pas tue
    pour autant — elle qualifie la constatation qu'elle alimente, avec le nombre
    de relevés que l'échéancier FIGÉ lui attribue."""
    fenetres = _fenetres_par_date(schedule_json)
    constatations = [e for e in events if e.parent_event_id is None]
    lignes = []
    for e in constatations:
        label = e.label
        fenetre = fenetres.get(round(e.t_years, 4))
        if fenetre:
            libelle = _REDUCTION_LIBELLE.get(fenetre["reduction"], fenetre["reduction"])
            label = f"{label} — {libelle} de {len(fenetre['releves'])} relevés"
        lignes.append({"date": e.event_date, "label": label, "status": e.status,
                       "t_years": e.t_years})
    prochaine = next((e.event_date
                      for e in sorted(constatations, key=lambda x: x.t_years or 0.0)
                      if e.status == "futur"), None)
    return lignes, prochaine


def _figer_echeancier(body) -> str:
    """L'échéancier contractuel du deal, en JSON, tel qu'il sera figé.

    Figé et non recalculé : les dates d'un deal booké se reconstruisaient
    jusqu'ici à chaque valorisation depuis ses CONSTAT. Une convention de jour
    ouvré modifiée, un référentiel de fériés mis à jour, ou un changement dans
    la génération de calendrier déplaçaient donc rétroactivement les
    constatations d'un contrat signé. Ce que le term sheet dit ne doit dépendre
    d'aucun code exécuté plus tard.

    Un script qu'on ne sait pas résoudre ne bloque pas le booking : le champ
    reste vide, ce qui se lit comme « pas d'échéancier figé » — la vérité — au
    lieu d'un échéancier reconstruit après coup."""
    try:
        compiled, _ = _resoudre_pour_booking(body)
        ech = getattr(compiled, "echeancier", None)
        return json.dumps(ech.to_dict()) if ech is not None else "{}"
    except Exception:
        return "{}"


def _derive_observation_times(body) -> List[float]:
    """The deal's observation schedule, read off the product itself rather than
    off a pricing run.

    The client derives it from the last Monte Carlo's flux table, which fails
    in two ways. It is EMPTY when nothing was priced in the session — booking
    straight from an RFQ prefill (which clears results on purpose) produced a
    deal whose only event was the strike, so no barrier watchlist, no residual
    MtM and no automatic resolution, silently. And when it is filled, its times
    are the simulation's WEEKLY GRID steps (0.9808 = 51/52), not the calendar's
    (0.9884): a 3-day drift on every observation date the lifecycle then works
    from.

    Resolving the script's own calendar gives both — the true contractual
    dates, and no dependency on having clicked ▶ Pricer."""
    compiled, origin = _resoudre_pour_booking(body)
    # AT_MATURITY carries no date of its own: it fires at the end of the
    # horizon. Which end? The deal's OWN maturity date, not the tenor typed in
    # the pricing form — the two diverge as soon as a CONSTAT calendar is in
    # play, since the form keeps a round 3.0 while the calendar ends at 2.9897.
    # Reading the horizon off body.T put the redemption 4 days AFTER the
    # maturity the deal itself declares, and added a fifth observation line to
    # a product that has four. A coupon calendar shorter than the note (2Y of
    # coupons on a 3Y maturity) stays correct: its maturity date is the 3Y one.
    horizon = body.T
    # Mesure depuis la MEME origine que les constatations resolues ci-dessus :
    # la date de strike. Compter l horizon depuis la value date alors que les
    # observations partent du strike decalerait le remboursement de l ecart
    # entre les deux dates.
    if body.maturity_date and origin:
        from_maturity = _years_between(origin, body.maturity_date)
        if from_maturity > 0:
            horizon = from_maturity
    T_eff = effective_T_max(compiled, horizon)
    times = set()
    for ev in compiled.events:
        if ev.type == "AT_MATURITY":
            times.add(round(T_eff, 4))
        for d in (ev.dates or []):
            times.add(round(d, 4))
    # t=0 is the strike/fixing line, added separately by book_deal.
    return sorted(t for t in times if t > 0)


def _rfq_provenance(rfq, price_traded: float, session: Session,
                    *, fermete_avant: str | None = None,
                    firmness_affirmee_au_booking: bool = False) -> str:
    """Freeze the tender's competitive picture onto the deal: the retained
    response, every rival price it beat, and our own model price at the time.
    Stored as JSON on the deal (Deal.rfq_provenance_json) rather than looked
    up through rfq_id on demand, because the RFQ keeps living afterwards —
    a price corrected or a quote deleted would silently rewrite the
    justification of a trade already done.

    price_traded is carried alongside the retained quote's price rather than
    validated against it: the two legitimately differ (last-minute
    negotiation, fees, rounding). Recording the gap documents it; refusing it
    would block real bookings."""
    from ..rfq import superseded_quote_ids

    quotes = session.exec(select(RfqQuote).where(RfqQuote.rfq_id == rfq.id)).all()
    superseded = superseded_quote_ids(quotes)
    won = next((q for q in quotes if q.id == rfq.selected_quote_id), None)
    booked_at = datetime.utcnow()
    frozen_terms = product_terms(rfq.script_snapshot, json.loads(rfq.params_json or "{}"))
    return json.dumps({
        "rfq_id": rfq.id,
        "reference": rfq.reference,
        "sens": rfq.sens,
        "kind": rfq.kind,
        "model_price": rfq.model_price,
        "model_price_at": rfq.model_price_at.isoformat() if rfq.model_price_at else None,
        "booked_at": booked_at.isoformat(),
        "price_traded": price_traded,
        "selection_reason_code": rfq.selection_reason_code,
        "selection_reason_note": rfq.selection_reason_note,
        "product_terms": frozen_terms,
        "product_terms_sha256": product_terms_hash(frozen_terms),
        "retained": {
            "provider": won.provider, "price": won.price,
            "is_last_look": won.parent_quote_id is not None,
            "quoted_at": won.quoted_at.isoformat() if won.quoted_at else None,
            # D'où vient la fermeté : affirmée par la contrepartie avant le
            # trade, ou par l'acte de booking lui-même. Six mois plus tard, les
            # deux se lisent « FIRM » sur la quote — seules ces lignes les
            # distinguent, et c'est la distinction qui a une valeur probante.
            #
            # `firmness_before_booking` porte le cas qui compte : une cotation
            # marquée INDICATIVE et bookée quand même. Le booking ne s'y oppose
            # plus, mais la piste d'audit doit continuer de le dire.
            "firmness": won.firmness,
            "firmness_before_booking": fermete_avant,
            "firmness_asserted_at_booking": firmness_affirmee_au_booking,
        } if won else None,
        # Only final answers: a superseded quote is the same bank's earlier
        # price, not a competitor (see rfq.py:superseded_quote_ids).
        "competition": sorted(
            [{"provider": q.provider, "price": q.price}
             for q in quotes
             if q.id not in superseded and q.id != rfq.selected_quote_id and q.price is not None],
            key=lambda x: x["price"],
        ),
        # Complete final-response evidence for Client Intelligence.  The old
        # `retained`/`competition` keys stay for backward compatibility, while
        # this list also preserves solicitations without a price, declines,
        # firmness and validity.  Later RFQ edits therefore cannot rewrite the
        # observed provider behaviour of an executed deal.
        "responses": [
            {
                "quote_id": q.id,
                "provider": q.provider,
                "price": q.price,
                "currency": q.currency,
                "status": q.status,
                "firmness": q.firmness,
                "quoted_at": q.quoted_at.isoformat() if q.quoted_at else None,
                "valid_until": q.valid_until.isoformat() if q.valid_until else None,
                "is_last_look": q.parent_quote_id is not None,
                "is_final": q.id not in superseded,
                "selected": q.id == rfq.selected_quote_id,
                "comparable": (
                    q.id not in superseded
                    and q.price is not None
                    and q.status not in {"decline", "expire"}
                    and (q.valid_until is None or q.valid_until > booked_at)
                ),
            }
            for q in quotes
        ],
    }, ensure_ascii=False)


def _workflow_failure(
    code: str,
    field: str,
    message: str,
    *,
    expected: str | None = None,
    action: str | None = None,
    received=None,
) -> dict:
    row = {"code": code, "field": field, "message": message, "blocking": True}
    if expected is not None:
        row["expected"] = expected
    if action is not None:
        row["action"] = action
    if received is not None:
        row["received"] = received
    return row


def _reject_workflow_action(
    session: Session,
    *,
    action: str,
    object_type: str,
    object_id: int | None,
    current: User,
    message: str,
    failures: list[dict],
    status_code: int = 422,
    before: dict | None = None,
) -> None:
    detail = {
        "code": action,
        "message": message,
        "failures": failures,
    }
    commit_rejection(
        session,
        action=action,
        object_type=object_type,
        object_id=object_id,
        actor_user_id=current.id,
        before=before,
        reason=message,
        metadata={"failures": failures},
    )
    raise HTTPException(status_code, detail)


def _ops_deal(
    deal_id: int,
    current: User,
    session: Session,
    *,
    allowed_roles: set[str],
    action: str,
) -> Deal:
    deal = session.get(Deal, deal_id)
    if not deal:
        raise HTTPException(404, "Deal introuvable")
    entity_id = _deal_entity_id(deal, session)
    if current.entity_id is None or current.entity_id != entity_id:
        raise HTTPException(404, "Deal introuvable")
    if not has_business_role(current, allowed_roles):
        role_label = "Ops Maker" if allowed_roles == {"ops_maker"} else "Ops Checker"
        _reject_workflow_action(
            session,
            action=action,
            object_type="DEAL",
            object_id=deal.id,
            current=current,
            message="Votre rôle ne permet pas cette action lifecycle.",
            failures=[_workflow_failure(
                "WORKFLOW_ROLE_REQUIRED",
                "user.role",
                f"Cette action est réservée au rôle {role_label} de l’entité du deal.",
                expected=role_label,
                received=getattr(current, "role", None),
                action=f"Demandez à un {role_label} habilité de traiter cette étape.",
            )],
            status_code=403,
        )
    return deal


def _ensure_alert(
    session: Session,
    deal: Deal,
    kind: str,
    message: str,
    dedup_key: str,
) -> Alert:
    existing = session.exec(
        select(Alert).where(Alert.dedup_key == dedup_key)
    ).first()
    if existing:
        return existing
    alert = Alert(
        user_id=deal.user_id,
        deal_id=deal.id,
        deal_reference=deal.reference,
        kind=kind,
        message=message,
        dedup_key=dedup_key,
    )
    session.add(alert)
    return alert
