"""Reconcile recorded native executions without inferring missing evidence."""

LEG_SIDES = {'BANK_SELL': 'SELL', 'HECTOR_BUY': 'BUY', 'HECTOR_SELL': 'SELL', 'CLIENT_BUY': 'BUY'}
PAIR_FIELDS = ('trade_reference', 'instrument_reference', 'issuer', 'nominal', 'currency', 'price_traded', 'value_date', 'contract_hash')
INSTRUMENT_FIELDS = ('instrument_reference', 'issuer', 'nominal', 'currency', 'contract_hash')


def check_books(state):
    checks = []
    actors = state.get('actors', {})
    for case in state.get('cases', {}).values():
        records = [dict(d, actor=key) for key, actor in actors.items()
                   for d in actor.get('deals', []) if d.get('case_id') == case['id']]
        issues, missing = [], []
        grouped = {leg: [d for d in records if d.get('leg') == leg] for leg in LEG_SIDES}

        def issue(code, leg, field, expected, actual):
            issues.append(dict(code=code, leg=leg, field=field, expected=expected, actual=actual))

        def compare(left, right, fields):
            for field in fields:
                if left.get(field) is None or right.get(field) is None:
                    missing.append(field)
                elif left[field] != right[field]:
                    issue('FIELD_MISMATCH', right['leg'], field, left[field], right[field])

        for leg, rows in grouped.items():
            if len(rows) > 1:
                issue('DUPLICATE_LEG', leg, 'count', 1, len(rows))
        for row in records:
            if row.get('leg') not in LEG_SIDES:
                issue('UNEXPECTED_LEG', row.get('leg'), 'leg', list(LEG_SIDES), row.get('leg'))
        selected = next((q for q in state.get('quotes', [])
                         if q.get('id') == state.get('accepted', {}).get(case['id'])), None)
        bank_rows = grouped['BANK_SELL']
        bank = selected.get('bank') if selected else bank_rows[0]['actor'] if len(bank_rows) == 1 else None
        sender = case.get('requester', 'hector')
        owners = {'BANK_SELL': bank, 'HECTOR_BUY': sender, 'HECTOR_SELL': sender, 'CLIENT_BUY': 'client'}
        parties = {'BANK_SELL': sender, 'HECTOR_BUY': bank, 'HECTOR_SELL': 'client', 'CLIENT_BUY': sender}
        for row in records:
            leg = row.get('leg')
            if leg not in LEG_SIDES:
                continue
            if owners[leg] and row['actor'] != owners[leg]:
                issue('ACTOR_MISMATCH', leg, 'actor', owners[leg], row['actor'])
            if leg == 'BANK_SELL' and actors.get(row['actor'], {}).get('role') != 'bank' and not actors.get(row['actor'], {}).get('capabilities', {}).get('respond_rfq'):
                issue('ACTOR_MISMATCH', leg, 'role', 'bank', actors.get(row['actor'], {}).get('role'))
            if row.get('our_side') != LEG_SIDES[leg]:
                issue('SIDE_MISMATCH', leg, 'our_side', LEG_SIDES[leg], row.get('our_side'))
            if selected:
                issuer = actors.get(bank, {}).get('entity')
                if issuer and row.get('issuer') != issuer:
                    issue('ISSUER_MISMATCH', leg, 'issuer', issuer, row.get('issuer'))
                price = selected.get('price') if leg in {'BANK_SELL', 'HECTOR_BUY'} else state.get('client_offers', {}).get(case['id'], {}).get('client_price')
                if price is not None and row.get('price_traded') != price:
                    issue('ACCEPTED_PRICE_MISMATCH', leg, 'price_traded', price, row.get('price_traded'))
            entity = actors.get(parties[leg], {}).get('entity')
            if not entity or not row.get('counterparty'):
                missing.append('counterparty')
            elif row['counterparty'] != entity:
                issue('COUNTERPARTY_MISMATCH', leg, 'counterparty', entity, row['counterparty'])
            for field in ('nominal', 'instrument_reference'):
                if field in case and row.get(field) != case[field]:
                    issue('CASE_MISMATCH', leg, field, case[field], row.get(field))
            if actors.get(row['actor'], {}).get('native_sync_error'):
                missing.append('native_refresh')
        for left_leg, right_leg, fields in (
            ('BANK_SELL', 'HECTOR_BUY', PAIR_FIELDS),
            ('HECTOR_BUY', 'HECTOR_SELL', INSTRUMENT_FIELDS),
            ('HECTOR_SELL', 'CLIENT_BUY', PAIR_FIELDS),
        ):
            if len(grouped[left_leg]) == len(grouped[right_leg]) == 1:
                compare(grouped[left_leg][0], grouped[right_leg][0], fields)
        closed = case.get('outcome') in {'CLIENT_DECLINED', 'NO_QUOTE'}
        if closed and records:
            issue('BOOKING_AFTER_REFUSAL', '', 'outcome', 'Aucune écriture', case['outcome'])
        status = 'PENDING'
        if issues:
            status = 'MISMATCH'
        elif not records and closed:
            status = 'NO_TRADE'
        elif records and missing:
            status = 'UNVERIFIED'
        elif all(len(rows) == 1 for rows in grouped.values()):
            status = 'COMPLETE'
        elif len(grouped['BANK_SELL']) == len(grouped['HECTOR_BUY']) == 1:
            status = 'MATCHED'
        client = grouped['HECTOR_SELL']
        checks.append(dict(case_id=case['id'], status=status, legs=len(records),
                           client_volume=client[0]['nominal'] if status == 'COMPLETE' else 0,
                           missing_legs=[leg for leg, rows in grouped.items() if not rows],
                           missing_evidence=sorted(set(missing)), issues=issues))
    return checks
