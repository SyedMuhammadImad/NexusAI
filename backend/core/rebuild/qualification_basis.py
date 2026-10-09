"""ADR-019 evidence producer. No credentials, native connection or order actions."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

from pydantic import AwareDatetime, Field, StrictBool

from .execution_contracts import Attestation
from .ledger import canonical, hashed
from .native_operator import OperatorBlocked, RiskBasis, StrictRecord
from .operator_verification import VerificationLedger
from .safety import fresh
from .safety_contracts import Positive

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
VERSION = 'qualification-start-v1'


class BoundaryEquity(StrictRecord):
    observed_at: AwareDatetime
    equity: Positive
    cash_flow_total: Decimal = Field(allow_inf_nan=False)
    evidence_id: str = Field(min_length=1)


class QualificationEvidence(StrictRecord):
    attestation: Attestation
    observed_at: AwareDatetime
    equity: Positive
    history_from: AwareDatetime
    history_complete: StrictBool
    history_evidence_id: str = Field(min_length=1)
    ever_traded: StrictBool
    inventory_complete: StrictBool
    inventory_evidence_id: str = Field(min_length=1)
    open_position_ids: tuple[str, ...] = ()
    pending_order_ids: tuple[str, ...] = ()
    cash_flow_total: Decimal = Field(allow_inf_nan=False)
    cash_flow_evidence_id: str = Field(min_length=1)
    # Exact UTC boundary observations, never inferred from a later current balance.
    rollovers: tuple[BoundaryEquity, ...] = ()


def qualification_basis(ledger, evidence, *, current):
    if not isinstance(ledger, VerificationLedger):
        raise OperatorBlocked('ISOLATED_VERIFICATION_LEDGER_REQUIRED')
    e = QualificationEvidence.model_validate(evidence.model_dump())
    if current.tzinfo is None:
        raise OperatorBlocked('QUALIFICATION_AWARE_TIME_REQUIRED')
    current = current.astimezone(timezone.utc)
    fresh(e.observed_at, current, 5)
    fresh(e.attestation.observed_at, current, 5)
    a = e.attestation
    expected = ledger.account
    if (expected is None or a.account_key != expected.key
            or (a.account_id, a.server, a.currency, a.scope) !=
            (expected.account_id, expected.server, expected.currency, expected.evidence_source)
            or not a.connected or not a.trade_allowed or not a.expert_allowed or not a.hedging):
        raise OperatorBlocked('QUALIFICATION_ACCOUNT_NOT_ATTESTED')
    if (not e.history_complete or e.history_from != EPOCH or not e.inventory_complete):
        raise OperatorBlocked('QUALIFICATION_HISTORY_OR_INVENTORY_INCOMPLETE')
    day = current.replace(hour=0, minute=0, second=0, microsecond=0)
    week = day - timedelta(days=day.weekday())
    rollovers = {r.observed_at: r for r in e.rollovers}
    if len(rollovers) != len(e.rollovers) or any(t > e.observed_at for t in rollovers):
        raise OperatorBlocked('QUALIFICATION_ROLLOVER_CONFLICT')
    with ledger.transaction() as conn:
        ledger._check_account(conn, a)
        prior = conn.execute("SELECT payload FROM audit_events WHERE event_type='P3_QUALIFICATION_BASELINE' ORDER BY sequence DESC LIMIT 1").fetchone()
        if prior is None:
            if (e.ever_traded or e.open_position_ids or e.pending_order_ids
                    or conn.execute('SELECT 1 FROM p2_baselines').fetchone()
                    or conn.execute('SELECT 1 FROM p3_attempts').fetchone()):
                raise OperatorBlocked('QUALIFICATION_ACCOUNT_NOT_UNUSED')
            started = e.observed_at.isoformat()
            day_equity = week_equity = high = e.equity
        else:
            old = json.loads(prior[0])
            if old['account_key'] != expected.key or old['version'] != VERSION:
                raise OperatorBlocked('QUALIFICATION_BASELINE_BINDING_MISMATCH')
            previous = QualificationEvidence.model_validate(old['evidence'])
            if e.observed_at < previous.observed_at:
                raise OperatorBlocked('QUALIFICATION_SNAPSHOT_REGRESSION')
            if e.observed_at == previous.observed_at:
                if e.model_dump(mode='json') != old['evidence']:
                    raise OperatorBlocked('QUALIFICATION_SNAPSHOT_CONFLICT')
                return RiskBasis.model_validate(old['basis'])
            started = old['qualification_started_at']
            basis = RiskBasis.model_validate(old['basis'])
            flow = e.cash_flow_total - basis.cash_flow_total
            day_equity, week_equity = basis.day_equity + flow, basis.week_equity + flow
            high = max(basis.high_water_equity + flow, e.equity)
            for label, boundary in (('day', day), ('week', week)):
                old_start = getattr(basis, label + '_start')
                if boundary < old_start:
                    raise OperatorBlocked('QUALIFICATION_PERIOD_REGRESSION')
                if boundary != old_start:
                    if (boundary not in rollovers or previous.observed_at > boundary
                            or e.observed_at < boundary):
                        raise OperatorBlocked('QUALIFICATION_ROLLOVER_EVIDENCE_MISSING')
                    r = rollovers[boundary]
                    adjusted = r.equity + e.cash_flow_total - r.cash_flow_total
                    if label == 'day': day_equity = adjusted
                    else: week_equity = adjusted
        document = e.model_dump(mode='json')
        basis = RiskBasis(evidence_id=hashed([VERSION, started, document]),
            account_key=expected.key, currency=expected.currency, observed_at=e.observed_at,
            day_start=day, week_start=week, day_equity=day_equity, week_equity=week_equity,
            high_water_equity=high, cash_flow_total=e.cash_flow_total,
            cash_flow_evidence_id=e.cash_flow_evidence_id)
        ledger.audit(conn, 'P3_QUALIFICATION_BASELINE', None,
            dict(version=VERSION, account_key=expected.key, qualification_started_at=started,
                 period_basis='QUALIFICATION_START_THEN_EVIDENCED_UTC_ROLLOVERS',
                 evidence=document, basis=basis.model_dump(mode='json')))
        return basis
