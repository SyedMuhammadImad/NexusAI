# P3 Native Operator Providers

ADR-012 governance update (2026-09-13): P3 ENGINEERING VERIFIED_COMPLETE only
within non-operational/fixture/native-normalization scope; P3 OPERATOR DEMO
VERIFICATION DEFERRED / PENDING. These providers are not machine/account qualified.
Broker execution remains HARD DISABLED for normal application/P4-P9 paths; P4
engineering is READY, not started here. The isolated operator procedure below is
deferred, requires separate authorization and all original gates, and must not be
invoked by later engineering/research components. Its actual verification remains
mandatory before ordinary demo execution, P10 or any live-readiness work.
Prior PARTIAL/P4-blocked checkpoint evidence below is preserved, not downgraded.

Date: 2026-09-13. Baseline: `1b51674288442a050fdbb55bddde43aa9622ed73`.
Authority: the current bounded operator-provider task, ADR-008, ADR-010 and ADR-011.
Status: IMPLEMENTED, fixture-tested; actual machine qualification NOT_PROVEN.
P3 remains PARTIAL. No default-app/native dispatch, P4, strategy or policy change.

## Implementation

- `backend/core/rebuild/native_operator.py`: fixed private configuration loader,
  Windows isolation provider, explicit one-shot native connector, native P2 context,
  minimum-volume adapter, pre-flight and operator composition.
- `scripts/p3_windows_host.ps1`: read-only process identity/session and ACL collector.
  It receives paths and a service SID, never a login or password.
- `scripts/p3_native_preflight.py`: default metadata-only report. Explicit `--attest`
  enters the operator-only read/connection path only after required-file checks.
  Neither mode resets HALT, generates a signal, creates an approval or submits.
- `NativeOperatorVerification.submit_once`: mandatory PASS pre-flight, then existing
  one-shot wrapper, final P2/HALT revalidation and durable execution engine.
  Pre-flight is not a reusable approval or substitute for final revalidation.

Importing these modules does not load settings, import MT5, connect or open a DB.
No arbitrary import/callback/path is accepted from CLI or private JSON. Dependency
injection in Python tests remains trusted implementation code, not a public API.

## Operator Files

Only these explicitly named files may be loaded by the native provider:

| Fixed path | Required evidence |
|---|---|
| `backend/private/mt5/p3-operator.json` | Exact DemoAccount binding; secret password; absolute private portable terminal executable; SHA-256; dedicated service SID; exact broker/terminal companies; authorized manual source; permitted symbols; P2 policy version |
| `backend/private/mt5/p3-risk-basis.json` | Evidence ID and account/currency binding; observation time; UTC daily/Monday weekly boundaries and recorded equity baselines; high-water equity; cumulative cash flows and evidence ID |
| `backend/private/mt5/p3-costs.json` | Evidence ID and account/currency binding; observed/expiry times; explicit nonnegative commission-per-lot values for every enabled symbol |

Schemas are `OperatorSettings`, `RiskBasis` and `CostBasis`. Extra keys, duplicate
JSON keys, non-finite numbers, oversized files and linked paths reject. Private
files must remain ignored; do not paste their contents into chats, logs or reports.
There is no .env, previously supplied account, saved-login or zero-cost fallback.
This task did not create these files or transfer old credentials into them.

Risk-basis evidence must be fresh within five seconds and refer to the actual
current periods. A qualified operator evidence producer must preserve the original
recorded baselines and track intervening cash flows, not simply refresh a timestamp
on guessed values. Current MT5 equity/balance or deal history alone does not recover
unobserved historical floating equity/high-water state. Missing recorded history
is a blocker, not permission to start the baseline again. Cost evidence must be
explicit, account-bound and unexpired; a declared zero requires qualified evidence.

## Windows and Account Gate

The native connector is deferred until the host provider accepts all of:

1. Exact dedicated non-administrator service identity, non-interactive session 0.
2. Exactly one designated terminal and only the expected verifier/collector
   processes under that identity; missing ownership metadata rejects.
3. Protected ACL ownership/access on the named credential files, terminal directory
   and new verification directory. No additional principals may have allow ACEs.
4. Non-linked approved paths and exact configured terminal executable SHA-256.
5. A fresh host check, repeated around attestation/reads and before submission.

The connector explicitly supplies executable, login, server, password and portable
mode. It never selects an ambient/default account. Native evidence must then prove
exact account/server/currency, DEMO mode, hedging, connectivity, trade permissions,
company, portable terminal/data directory and valid build. One initialization
attempt per connector; failure is sanitized and not automatically retried.

These source checks and synthetic collector tests are NOT proof that this machine
has the required service, ACLs, terminal or no-live isolation. The collector syntax
was parsed, not exercised against real process/credential directories. Missing WMI
ownership permissions fail closed; do not elevate the trading identity or omit
unknown processes merely to pass. Provision the isolated host and its read-only
metadata visibility separately. ACL/process snapshots are not an OS sandbox or an
atomic account-bound send, and do not protect against administrators/kernel compromise,
uncontrolled account switching, or unauthorized terminal automation. A portable
flag, company string or fixture receipt cannot qualify those operational controls.

Native terminal/account field references:
[account_info](https://www.mql5.com/en/docs/python_metatrader5/mt5accountinfo_py),
[terminal_info](https://www.mql5.com/en/docs/python_metatrader5/mt5terminalinfo_py).
The collector uses read-only
[Get-Acl](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.security/get-acl?view=powershell-7.5)
and [GetOwnerSid](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/getownersid-method-in-class-win32-process).
No published example was run.

## Native P2 Context

`NativeP2Context` consumes normalized account, inventory, symbol and quote evidence
from `NativeEvidenceReader`, plus the mandatory recorded risk/cost basis. It checks
freshness independently for account/inventory (5 s), quote (3 s), metadata (1 h),
and calculation completion. It rejects wrong account/currency, unknown orders,
unattributable positions, invalid values, missing costs and unsupported conversion.
Broker profit currency must equal account currency in this bounded implementation;
there is no invented cross-currency conversion rate.

Each pending order must match a durable started P3 attempt. Current positions use
exact opening-order attribution, active stops and remaining volume. Pending risk
remains in existing P2 reservations, not a duplicate fabricated position. Native
projection still independently checks exact broker inventory/metadata equality;
unknown entities quarantine rather than become owned trades.

Margin is calculated natively for minimum volume on both BUY/ASK and SELL/BID;
the larger estimate is used. Numeric conversion must round-trip exactly through
the Python/native boundary. The operator adapter repeats the calculation at the
authorized minimum volume and requires
`(used_margin + estimated_margin) / equity <= 0.25`
before the underlying final account/quote/expiry/send checks.
This is a minimum-lot smoke provider, NOT a proven linear margin model for arbitrary
larger volumes or broker tiers. MetaQuotes documents that
[order_calc_margin](https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcmargin_py)
returns account-currency margin, may fail with None, and does not account for existing
positions/pending orders. The one-shot path requires an empty reconciled account;
P2 still owns aggregate reservations and every other locked risk limit.

## Pre-Flight and Remaining Procedure

Metadata-only command, no secrets or connection:

```powershell
.\backend\.venv\Scripts\python.exe -B scripts/p3_native_preflight.py
```

On this machine all three required files were absent; status FAIL with
MISSING_OPERATOR_EVIDENCE. No native import/connection, real evidence read, DB
creation or broker action was attempted. FAIL means not established, not that a
real account was inspected and found unsafe. See the corresponding audit.

After the owner provisions and independently qualifies the dedicated environment
and required evidence, the explicit operator-only `--attest` option performs read
qualification. A new ledger is HALTED, so it will not report admission readiness
until the deliberate existing P2 reset procedure has been satisfied. No CLI unlock
or automatic strategy/request generation was added.

For a retained operator session, `open_native_operator()` composes a fresh isolated
ledger, SafetyEngine, native providers and one-shot wrapper. The authorized operator
must prove HALT denial, qualify the current evidence, use the existing P2 reset
procedure, prepare one MANUAL/MARKET canonical request with explicit SL/TP and risk
that P2 actually allocates at the exact minimum volume, and obtain PASS from
`connected_preflight(run)`. `run.submit_once(request_id)` repeats pre-flight and
existing final safety checks; legacy intent.volume cannot override P2 sizing.
No configuration/session object or raw exception should be printed.

Preserve `.p3-verification/` and its one-use claim. Any mismatch: stop, retain
evidence and use `run.stop()`; after STARTED never resubmit on timeout or absence of
a response. `run.reconcile()` is read-only, HALTED recovery. Prove exact lineage,
IDs, reservation conversion, repeated reconciliation and broker-confirmed terminal
state. A protective exit is broker evidence; a local stop is not a broker close.
There is no manual flatten/close helper and no permission to reconnect legacy agents.
External safe-stop ability, uninterrupted isolation and actual broker timing still
require operator qualification. No P4 work is authorized by this document.

## Verification

`test_p3_native_operator.py` covers pure provider mapping into the real native
journal/projection, independent freshness, invalid/missing risk/cost evidence,
failed margin calls, host negatives, binary changes, exact demo attestation,
one-shot explicit connector, redaction, pre-flight/HALT and mandatory submission
pre-flight. All accounts, files, native clients and host receipts are synthetic.
Prior P3 tests cover crash/restart/revision/duplicate/partial-fill lineage and
reservation behavior; these are still fixture proofs, not new broker evidence.
Final counts and reproduction: `../TESTING.md`.
