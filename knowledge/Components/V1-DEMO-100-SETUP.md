# V1 $100 Demo Setup and WhatsApp Pairing

Source-identity follow-up: the owner confirmed the sender ending3934. The actual
client verified its PN/LID and membership/admin role in the uniquely selected
REDACTED_OPERATOR_IDENTIFIER announcement group, distinguished from a same-name ordinary group.
32 connector tests pass; private immutable identity receipt retained. See
V1-WHATSAPP-SOURCE-IDENTITY.md. Forwarding and economic activation remain off;
the historical initial pairing/13-test evidence below is preserved.

Recorded: 2026-10-02 (Asia/Karachi). V1 remains PARTIAL; broker execution is
HARD_DISABLED. Authority: ADR-010, ADR-018 and ADR-019, plus the owner's current
request to pair WhatsApp before supplying group/sender details.

## Account and risk

The owner reports a $100 demo account and that isolation setup is done. These
are human statements, not fresh broker equity or a successful host-attestation
receipt. No account file is read or changed by this setup task. Never inject 100
into the runtime account evidence as a fallback. Sizing remains based on
MIN(fresh valid equity, balance); margin utilization uses fresh valid equity.

Existing P2-DEMO-1.0 limits already scale to account size. If capital, account
currency and all relevant baselines are genuinely USD100, the illustrations are:

| Rule | Approved limit | Illustration at USD100 |
|---|---|---|
| Default requested stop-risk including modeled costs | 0.25% | USD0.25 |
| Maximum per-trade risk | 0.50% | USD0.50 |
| Portfolio stop-risk | 1.50% | USD1.50 |
| Per-instrument stop-risk | 0.75% | USD0.75 |
| Precious-metals bucket stop-risk | 1.00% | USD1.00 |
| Energy bucket stop-risk | 0.75% | USD0.75 |
| Portfolio gross notional | 300% | USD300 |
| Per-instrument gross notional | 150% | USD150 |
| Projected margin utilization | 25% of equity | USD25 |
| Daily loss blocks new admission | >=2% of adjusted daily baseline | USD2 |
| Weekly loss blocks new admission | >=4% of adjusted weekly baseline | USD4 |
| Latched high-water drawdown HALT | >=8% of adjusted high-water equity | USD8 |

These are not fixed dollar limits; deposits, withdrawals and changing evidenced
capital/baselines matter. Maximum three open/pending/reserved positions;
same-instrument stacking and opposite-direction exposure remain prohibited.
Volume rounds DOWN. Below broker minimum volume rejects; never round up to force
activity. A USD100 account may be unable to trade the permitted instruments under
these risk/notional caps. That is unproven until fresh broker metadata and quotes
establish a feasible minimum lot. Do not widen risk or change stops to bypass it.

## Reward to risk

The owner requests 1:2 to 1:3. The five frozen P6 rules currently propose a
2-ATR stop and 4-ATR target (nominal 2R) in strategy_observer.py. Costs and a
different executable entry can lower that ratio. The authoritative P2 minimum
remains cost-adjusted1.50; it has NOT been silently changed to2.00.

The owner explicitly clarified: keep strategy targets at1:2-1:3 and retain the
existing cost-adjusted1.50 safety floor for all sources. No global policy version
change is required. Current frozen strategy proposals use the2R end of the range;
no3R tuning or engine threshold change was performed. Never alter a human
sender's SL/TP to manufacture compliance.

## Five strategies and later replacements

Selected demo candidates remain EMA9/21, EMA20/50, MACD, Supertrend and Donchian
(p6-01,p6-02,p6-04,p6-05,p6-07). ADR-018's conditional demo exception remains,
with DEMO_ONLY / UNQUALIFIED_AUTOMATION / RESEARCH_EVIDENCE_INSUFFICIENT labels.
No P7 research-qualified strategy was produced; do not rewrite that finding.
The current observer does not submit or route strategy candidates through P2.

Twenty future strategies are a backlog until definitions and deterministic
tests exist. Arena comparison remains cost-aware and chronological under ADR-006,
with separate instrument/timeframe samples. One week is a proposed review time,
NOT automatic promotion evidence. Ranking by raw profit alone mixes opportunity,
size, exposure and luck. Insufficient sample remains insufficient; preserve
drawdown, expectancy, costs and exact strategy attribution. No automatic rotation,
deletion or performance-based order sizing was added. Replacement/promotion
criteria remain to be explicitly agreed before implementing rotation.

## Login first, source authorization later

New operator-only launcher: connectors/whatsapp/pair.mjs.

```powershell
Set-Location 'D:/project'
node .\connectors\whatsapp\pair.mjs
```

It uses only the dedicated ignored backend/private/whatsapp/v1/auth session,
clientId nexusai-v1, matching the later connector. It can use an explicit absolute
browser-executable argument, otherwise checks known public Chrome/Edge binaries.
The browser is visible so the user scans its WhatsApp QR directly. QR payloads
and provider errors are never logged. No connector configuration/token is needed
for this linking stage. No message/chat handlers, outbox or delivery path are
registered. The client requests browser shutdown after ready without logging out
or deleting LocalAuth. Timeout/auth failure/disconnection also stop it. A shutdown
hang has a30-second bound and may stop only the browser child handle owned by
this client; it returns4/STOP_UNVERIFIED, never a clean-link success. Reconnect and
persistence must still be observed independently.

Only authentication storage under the approved fixed private boundary is used.
No existing personal browser profile, MT5 credential, operator database or broker
is accessed. Link/hardlink refusal and a pairing lock are defensive checks, not
hostile-user OS isolation. The provider necessarily syncs its authenticated web
session; absence of application chat handlers is not a claim that WhatsApp itself
never downloads account data. A stale lock after a crash needs operator review,
not automatic deletion. Do not run pair.mjs and operator.mjs concurrently.

After linking, the exact authorized group and sender identities, fresh source
configuration, scoped connector token and qualified backend binding are still
required before intake. Linking does NOT authorize existing/backfilled messages
or enable execution. Existing operator.mjs still enforces those requirements.

Implementation/API sources: [Client lifecycle](https://docs.wwebjs.dev/Client.html)
and [LocalAuth](https://docs.wwebjs.dev/LocalAuth.html). This is the unofficial
whatsapp-web.js adapter, not an official business API; account restrictions and
upstream compatibility remain risks.

## Verification scope

2026-10-02: initial npm test,11 passed (four bridge, one API compatibility, six
pairing cases); no real session used by tests. npm audit --json --ignore-scripts reported
zero known vulnerabilities. Git ignore metadata confirmed auth, pairing lock and
the named MT5 operator configuration excluded. An owner-authorized login-only
process emitted SCAN_QR_IN_DEDICATED_BROWSER, then
WHATSAPP_LINKED_EXECUTION_DISABLED. The actual web client reached ready and the
link-only process requested shutdown. Browser close initially stalled; the
operator sent CloseMainWindow only to the directly owned Edge PID after verifying
parent identity. Browser and launcher then stopped; exit code was not retained.
This proves session readiness for this run, NOT
group/sender authorization, reconnection, intake/delivery or broker execution.
No MT5 connection/order or backend execution unlock occurred.

Subsequent bounded-shutdown cases: final npm test13 passed,0 failed in0.65s.
The real run's close stall is preserved above; mock cleanup success does not prove
session persistence or real reconnect.
