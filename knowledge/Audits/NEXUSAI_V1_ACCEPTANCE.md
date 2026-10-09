# NEXUSAI_V1_ACCEPTANCE

Updated: 2026-09-28. Baseline: 9954eb8091fde073f301e5eca89b53394915fc51,
branch core-rebuild. Status: **V1_PARTIAL; actual operation blocked**.
Implementation checkpoint: `b7036dc0d2cba6c6139215ec5baad6e63dbd0d77`.
Local commit only; no push. Unrelated untracked README_SETUP.md left untouched.
This is a readiness/acceptance report, NOT an operational session export.
Authority: owner V1 completion task and ADR-018. Non-executing V1 application
integration was implemented and tested; operator gates are unchanged.

## New Engineering Evidence (2026-09-28)

- Guarded V1+P4 focused: 79 passed /401 warnings,16.24s. Final allowlisted broad
  suite: 1026 passed /2333 warnings,171.81s,exit0. Six guard self-tests, zero
  sensitive/operator access attempts, no forbidden runtime modules. First broad
  run had three schema-count assertions expecting8; changed only those expected
  counts to9 and reran. Preserved payload/HALT/firewall assertions passed unchanged.
- Four connector queue tests passed: authorization/provenance, duplicate/reconnect
  restart, uncertain HTTP delivery, conflicting revisions, loopback/no redirects.
- Production frontend build passed. Fresh headless Chrome desktop1440x1000 and
  mobile390x844 passed all seven pages, no viewport overflow, manual HALT rejection,
  zero execution attempts, disabled strategy registration, export, Arena navigation
  and workspace lock. Zero page errors. Screenshots: ignored tmp/v1-ui/ (14 images).
  Headless Edge initially exited before a page; Chrome was used successfully.
- UI preview uses only a fresh temporary fixture DB/account and synthetic token.
  It did not read or migrate operator history. No real quote/account values shown.
- Dedicated connector credential cannot read/control the workspace; ordinary
  control credential cannot impersonate the connector endpoint. P4 validates
  exact group/sender again. Historical/screenshot/strategy execution remains denied.
- npm audit of the new connector found five high-severity package findings in the
  extract-zip/Puppeteer chain. No live startup/browser download occurred. Registry
  offered no patched24.x release; suggested downgrade was not accepted blindly.
  Dependency remediation/compatibility is an additional pre-link engineering gate,
  not a claim that the connector is security-qualified. See RISKS.md.

## Preserved Operator Evidence (2026-09-24, Not Re-Attested)

## Current Evidence

- `scripts/p3_native_preflight.py` (without --attest) returned FAIL with
  MISSING_OPERATOR_EVIDENCE and broker_actions=0. Configuration, risk_basis and
  cost_basis were all absent at their three fixed private paths. This operation
  inspected metadata only; it did not read credentials, initialize MT5 or open DBs.
- `Get-Process -Name terminal64,terminal` returned no matching process. This is
  a point-in-time local process observation, not proof about every installed copy.
- The public installation is `C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe`,
  version 5.0.0.6140, 121845984 bytes, SHA-256
  `33617c8e3cf71906c5125a229b04cbfc50413f222bda4ea2d41afef4adc45cf4`.
  Public executable metadata/hashing is not account, integrity-signature or demo
  attestation. This location is outside the existing approved private portable
  terminal boundary. No copy, terminal launch or account selection was performed.
- Current process: Windows session 1; elevated administrator false. Existing
  `WindowsTerminalIsolation.require_safe` requires a dedicated non-admin service
  identity in session 0, exact owned process/ACL evidence and designated binary.
  The current desktop process cannot satisfy that contract. Creating/qualifying
  the dedicated service environment needs an administrator-provisioned boundary;
  running the trading process as administrator is NOT the solution.
- `git check-ignore -v` confirms backend/private/ exclusion for all three P3 files
  and a representative WhatsApp descendant. `git ls-files -- backend/private
  backend/.env .p3-verification` returned no tracked paths. No private directory
  enumeration, credential read, operator DB read or unrelated store search.
- `application.py:create_app` rejects non-FIXTURE account binding and native
  execution adapters; P4 configuration cannot compose with execution. Its initial
  ledger state is HALTED. `source_registry` and migration 008 preserve a further
  persistent broker block. No attempt was made to remove these protections.
- The earlier rebuild-only frontend has now gained seven V1 views, but remains
  non-operational. Tournament Arena source/evidence is unchanged.
- A separate text-only connector transport/outbox is now fixture-tested. It has
  NOT been started, linked or live-authorized. No session store was inspected.

The owner selected an EXISTING demo account with recorded risk-history evidence.
The evidence location and protected current account binding have been requested;
the owner then requested engineering first and will provide credentials later.
No values have been supplied or inferred during this verification. Old chat
credentials are not copied or reused. Availability elsewhere is UNKNOWN.

## Acceptance Matrix

| Gate | Mandatory evidence | Current result |
|---|---|---|
| A Manual success | P1 -> P2 approved -> reservation -> attempt -> real order/deal/position -> reconciliation -> UI/P9 | FIXTURE_PROVEN through exact non-submitted request; real demo NOT_RUN |
| B Manual rejection | Unsafe intent -> persisted P2 rejection -> no broker send | FIXTURE_PROVEN in new API/UI composition, no broker attempt |
| C WhatsApp success | Actual authorized arrival -> trusted identity/parser -> P2 -> demo -> UI/P9 | FIXTURE_PROVEN envelope -> P2/request and durable transport delivery; actual live arrival/demo NOT_RUN |
| D WhatsApp quarantine | Ambiguous/incomplete/unauthorized/stale input -> reason -> zero order | FIXTURE_PROVEN including V1 stored classification; finer missing-fields taxonomy still incomplete |
| E Automated strategy | Closed current broker candle -> selected strategy -> P2 -> demo if approved | NOT_RUN; disabled registry only, no scheduler/operational integration |
| F HALT | All execution-capable sources denied at economic boundary | FIXTURE_PROVEN in existing P2/P3/P4 scope; real V1 composition NOT_RUN |
| G Restart/recovery | Persisted request/broker position -> reconcile -> no duplicate economic action | FIXTURE_PROVEN; actual demo restart NOT_RUN |
| H P9 | Complete truthful observer-only metrics/alerts/UI with provenance/windows | PARTIAL; integrated observer API/UI proven, full native/forward metrics missing |

The 30 new V1 backend cases, four transport tests and new desktop/mobile checks
are bounded fixture evidence. They do not substitute for operational A-H acceptance.

## Full P9 / Frontend Obligations Still Open

Do not reduce these to a status endpoint or static cards:

1. Health of API, DB, event processing, MT5/binding, quotes/candles, P2, execution,
   reconciliation, WhatsApp, strategy scheduler and monitoring itself, with ages.
2. Separate MANUAL/WHATSAPP_HUMAN/NEXUSAI_STRATEGY/HISTORICAL_WHATSAPP/SCREENSHOT
   received, validated, quarantine, P2 approve/reject, execute and duplicate counts.
3. Policy hash, risk/capacity/margin, daily/weekly/high-water drawdown, correlation
   buckets, reservations, HALT/reasons and rejection categories from P2 evidence.
4. Exact request/attempt/order/deal/position/exit lineage, partials, latency,
   admission spread, slippage, broker errors and retained/converted reservations.
5. Matched and unknown entities, ambiguity, revisions, contradictions and stale
   state; observation count must not double-count economic deals.
6. Broker-authoritative account/portfolio P&L, exposure and source/strategy/
   instrument breakdown; forward results never mix with research P6/P7 results.
7. Persistent INFO/WARNING/CRITICAL alerts with timestamps, identity and ack state;
   acknowledging an alert never clears HALT or resolves broker ambiguity.
8. Data freshness/mapping/session quality and P8_DEFERRED placeholders; daily/weekly
   performance, uptime/incidents and safety history for FUTURE P10, not qualification.
9. Existing-frontend Dashboard, New Trade, Positions/Execution, Safety, WhatsApp,
   Strategies, Monitoring/Alerts and preserved Tournament Arena navigation.
10. Persisted/audited manual, WhatsApp and automation switches under HALT/live lock;
    deterministic redacted read-only operational evidence export and tested windows/
    denominators. The new Markdown report is not a substitute for that export.

## Exact Blockers and Minimum Actions

| Blocker | Why not derivable now | Authoritative source / minimum action |
|---|---|---|
| Current designated demo binding/credential absent | No safe configured native session; old exposed chat values are not current proof | Owner supplies current credential locally in the existing approved private configuration, not chat; if multiple accounts, select exact allowed demo |
| Recorded risk-history location absent | Current balance/deals cannot establish unobserved floating-equity maxima | Owner identifies the existing recorded equity/baseline/cash-flow evidence file/export; do not manually fabricate values or reset history |
| Account-specific prospective costs absent | No attested account type or fee evidence; missing commission is not zero | Identify the broker fee evidence/account type locally; derive and validate the cost basis when available, request only genuinely unavailable evidence |
| Dedicated operator host not qualified | Current non-admin interactive session cannot create or prove session-0 service/ACL isolation | One-time administrator provisioning of the existing approved dedicated non-admin service/portable terminal boundary, or provide an already qualified operator host |

Account metadata, server/currency, symbol mappings, minimum lot/step, digits/tick,
contract size, margin/filling/session rules and fresh risk snapshots are subsequent
native derivation/verification work, NOT a list of manually guessed user inputs.
Canonical XAUUSD/XAGUSD/USOIL research names are not broker mappings. ADR-010's
existing symbol allowlist cannot be silently amended if actual symbols differ.

Live WhatsApp linking and exact group/sender identities are later operator inputs
only where trusted connector discovery cannot derive them. Do not treat old group
names or a saved display name as provider-attested current authorization.

## Stop State and Next Work

Zero connections/orders/deals/positions created by this task. No local or broker
close, account login, live strategy evaluation, WhatsApp session, training or P8 work.
Broker execution HARD_DISABLED; LIVE_LOCKED remains required and unchanged.

Once the required operator inputs/environment are available, qualify them through
the existing guarded P3 operator path, refresh real P2 evidence, prove HALT and one
minimum-volume approved demo request plus a rejected request, preserve exact IDs,
then reconcile/restart without resubmitting ambiguity. Only after actual P3 PASS
may the bounded operational integration and V1 A-H acceptance proceed.

Remaining engineering: qualified native application/source composition and control
activation; current closed-candle strategy scheduling/P2 route; full P9 native
instrumentation/latency/slippage/attributed performance/uptime; connector dependency
remediation and actual source authorization/linking. Providing credentials alone
will NOT complete these items. Detailed inventory: ../Components/V1-OPERATIONS.md.
