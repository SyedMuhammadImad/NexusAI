# P3 Operator Setup

2026-09-13. Schema source: `backend/core/rebuild/native_operator.py`
(`OperatorSettings`, `RiskBasis`, `CostBasis`), `ledger.py:DemoAccount`,
`safety_contracts.py:SafetyConfiguration`, and the existing native context checks.
Baseline: `f6d7dd05ffc0a6f71139986abf3fd3abc58f1897`.
P3 stays PARTIAL; this guide is not broker attestation or permission to trade.

## Three Different Files

- `backend/private/mt5/p3-operator.json`: allowed demo account and environment
  identity. It contains the password and must never be committed or shared.
- `backend/private/mt5/p3-risk-basis.json`: recorded P2 period/high-water/cash-flow
  evidence. It does NOT replace current broker equity, margin, quotes or inventory.
- `backend/private/mt5/p3-costs.json`: validated account-currency commission evidence
  for the enabled instruments. It does NOT set spread, slippage or risk limits.

Public templates are under `backend/examples/` with `.example.json` suffixes.
Every angle-bracket value is an intentionally INVALID placeholder, not a suggested
account, password, amount, timestamp, hash or SID. DEMO, MT5_DEMO and P2-DEMO-1.0
are required non-secret policy constants, not examples of live evidence. Replace
placeholders only in the ignored operator copies, never in the tracked examples.
No files were created in private storage and no credentials were accessed in this task.

All fields below are required unless explicitly marked defaulted. Extra fields
reject. Decimal amounts may be JSON decimal strings or numbers; decimal strings
are preferred to preserve exact precision. All money is in the bound account
currency, not automatically USD. Timestamp strings must include a timezone;
use UTC ISO-8601 with Z. The current Pydantic models also accept timezone-aware
offsets/epoch timestamps; the guide recommends explicit UTC strings for review.

Sensitivity: SECRET = authentication material; PRIVATE = account/machine identity
or financial information; PUBLIC = not intrinsically secret. All actual files
stay private regardless of individual fields. No real values belong in logs/reports.

## Account and Environment

`p3-operator.json`:

| Field | Type / units | Source of truth | Sensitive | Manual supply? | Validation / placeholder |
|---|---|---|---|---|---|
| account | object / none | Explicit allowed demo binding | PRIVATE | Yes, reviewed operator setup | Exact nested DemoAccount fields below |
| account.account_id | string / broker login ID | Owner-approved exact demo login | PRIVATE | Yes, locally | 1-128 chars, trimmed, decimal digits, integer >0; `<ALLOWED_DEMO_LOGIN_AS_STRING>` |
| account.server | string / server ID | Exact server for approved demo account | PRIVATE | Yes | 1-128 chars, not blank/padded; `<EXACT_DEMO_SERVER>` |
| account.currency | string / account currency | Verified account denomination | PRIVATE when linked | Yes, from evidence | Exactly three uppercase letters; `<THREE_LETTER_ACCOUNT_CURRENCY>` |
| account.mode | string / enum | ADR-008 | PUBLIC | No; keep constant | `DEMO`; model defaults to DEMO if omitted; not proof of connected mode |
| account.evidence_source | string / enum | Native provider binding | PUBLIC | No; keep constant | `MT5_DEMO`; underlying DemoAccount also accepts FIXTURE, but operator binding rejects it |
| password | string / none | Owner's approved broker credential | SECRET | Owner only, locally | Nonempty SecretStr; `<SUPPLY_LOCALLY_DO_NOT_SHARE>`; never request it in chat |
| terminal_exe | string / absolute path | Designated isolated portable installation | PRIVATE | Operator provisions/selects | Under repository backend/private/mt5, basename terminal64.exe or terminal.exe; `<ABSOLUTE_PRIVATE_TERMINAL_EXE_PATH>` |
| terminal_sha256 | string / SHA-256 | Actual approved executable bytes | PRIVATE deployment fingerprint | Compute locally, do not guess | Exactly 64 lowercase hexadecimal characters; `<64_LOWERCASE_HEX_SHA256>` |
| service_sid | string / Windows SID | Dedicated non-admin service identity | PRIVATE | Obtain from operator provisioning | Pattern `^S-1-5-21-(\d+-){2}\d+-\d+$`; `<DEDICATED_WINDOWS_SERVICE_SID>` |
| broker_company | string / name | Qualified native account company evidence | PRIVATE when linked | Supply from evidence | Nonempty, exact native comparison later; `<EXACT_BROKER_COMPANY>` |
| terminal_company | string / name | Qualified native terminal company evidence | PRIVATE deployment info | Supply from evidence | Nonempty, exact native comparison later; `<EXACT_TERMINAL_COMPANY>` |
| source_id | string / source identifier | Explicit authorized MANUAL test source | PRIVATE provenance | Operator chooses/reviews | Nonempty, must match later canonical authorized source; `<AUTHORIZED_MANUAL_SOURCE_ID>` |
| symbols | array of strings / broker symbols | ADR-010 and verified broker metadata | PUBLIC | Select approved subset | Nonempty subset of XAUUSDm, XAGUSDm, USOILm; no aliases/new instruments; `<APPROVED_INSTRUMENT_SYMBOL>` |
| policy_version | string / version | ADR-010 | PUBLIC | No; keep constant | Exactly `P2-DEMO-1.0` |

Schema-only checks cannot prove that a login is demo, a server/company is genuine,
the binary hash is correct, or the OS isolation exists. Native runtime attestation
and the host gates remain mandatory in a separately authorized operator task.

## Recorded Risk Basis

`p3-risk-basis.json`:

| Field | Type / units | Source of truth | Sensitive | Manual supply? | Validation / placeholder |
|---|---|---|---|---|---|
| evidence_id | string / snapshot ID | Qualified risk-evidence producer | PRIVATE provenance | Producer; operator supplies reference | Nonempty; `<RISK_SNAPSHOT_EVIDENCE_ID>` |
| account_key | string / SHA-256 identity | DemoAccount.key derived from complete account object | PRIVATE derived identity | Compute, never invent | Exact equality to operator account key; `<DERIVED_DEMO_ACCOUNT_KEY>` |
| currency | string / currency | Bound account denomination | PRIVATE when linked | Producer copies approved binding | Must equal account.currency; `<THREE_LETTER_ACCOUNT_CURRENCY>` |
| observed_at | aware timestamp / UTC time | Actual snapshot capture time | PRIVATE operational info | Producer refreshes genuine evidence | Runtime age <=5 s, future skew <=2 s; `<UTC_ISO8601_OBSERVATION_TIME>` |
| day_start | aware timestamp / UTC boundary | Current calendar day at 00:00 UTC | PUBLIC | Producer computes | Exact current UTC midnight; `<CURRENT_UTC_DAY_MIDNIGHT>` |
| week_start | aware timestamp / UTC boundary | Current Monday at 00:00 UTC | PUBLIC | Producer computes | Exact current UTC Monday midnight; `<CURRENT_UTC_MONDAY_MIDNIGHT>` |
| day_equity | decimal / account money | Recorded daily baseline with qualified cash-flow accounting | PRIVATE financial | Recorded producer, not a guessed manual value | Finite >0; `<RECORDED_DAY_BASELINE_DECIMAL>` |
| week_equity | decimal / account money | Recorded weekly baseline with qualified cash-flow accounting | PRIVATE financial | Recorded producer | Finite >0; `<RECORDED_WEEK_BASELINE_DECIMAL>` |
| high_water_equity | decimal / account money | Recorded high-water equity history | PRIVATE financial | Recorded producer | Finite >0; `<RECORDED_HIGH_WATER_DECIMAL>` |
| cash_flow_total | decimal / signed account money | Consistent cumulative external cash-flow ledger | PRIVATE financial | Recorded producer | Finite, may be positive/zero/negative; deposits positive, withdrawals negative; `<SIGNED_CUMULATIVE_CASH_FLOW_DECIMAL>` |
| cash_flow_evidence_id | string / evidence reference | Supporting cash-flow ledger/snapshot | PRIVATE provenance | Producer supplies | Nonempty; `<CASH_FLOW_LEDGER_EVIDENCE_ID>` |

Account key algorithm: `DemoAccount.key` is SHA-256 of UTF-8 JSON for the complete
validated account object, including mode and evidence_source, using sorted keys,
separators `(',', ':')` and allow_nan=False. Use the existing `DemoAccount.key`
property in a trusted local evidence producer, not a hash of the login alone.
The offline validator compares the key without printing it or writing a file.

The runtime safety engine compares changes in cumulative cash_flow_total across
snapshots to preserve cash-flow-adjusted baselines. Preserve the same accounting
origin and actual evidence; do not restart the counter or double-count flows.
The schema has no explicit accounting-origin field and does not certify producer
correctness. An unqualified history remains a blocker. There is no schema rule
that makes a guessed high-water amount valid simply because it is positive.

Current equity/balance/used margin and broker quotes/orders/positions are fetched
separately by the native provider. Do NOT add them to this JSON: extra keys reject.
Current equity cannot reconstruct missed historical floating equity or the true
high-water mark. Do not replace missing period values with current equity, zero,
a demo opening balance assumption, or figures from a screenshot. Static manually
filled files become stale within seconds; a qualified producer is still required.

## Cost Evidence

`p3-costs.json`:

| Field | Type / units | Source of truth | Sensitive | Manual supply? | Validation / placeholder |
|---|---|---|---|---|---|
| evidence_id | string / evidence ID | Reviewed broker fee schedule/evidence for this account | PRIVATE provenance | Operator/producer supplies | Nonempty; `<VALIDATED_COST_EVIDENCE_ID>` |
| account_key | string / SHA-256 identity | Same DemoAccount.key | PRIVATE derived identity | Compute from binding | Exact equality across files; `<DERIVED_DEMO_ACCOUNT_KEY>` |
| currency | string / currency | Fee amounts expressed in account currency | PRIVATE when linked | Producer verifies/converts only with qualified evidence | Exact account currency; `<THREE_LETTER_ACCOUNT_CURRENCY>` |
| observed_at | aware timestamp / UTC time | Actual cost-evidence observation | PRIVATE operational info | Producer/operator records | Must not be in future; `<UTC_ISO8601_COST_OBSERVATION_TIME>` |
| valid_until | aware timestamp / UTC time | Defensible validity of that evidence | PRIVATE operational info | Qualified producer/operator, not arbitrary extension | Later than observed_at and current time; `<UTC_ISO8601_COST_EXPIRY_TIME>` |
| commission_per_lot | object, symbol -> decimal / account money per lot | Qualified commission allowance for enabled broker instruments | PRIVATE account fee info | Operator/producer supplies every enabled symbol | Finite >=0 per value; all configured symbols covered; no missing-to-zero fallback; `<APPROVED_INSTRUMENT_SYMBOL>` -> `<VALIDATED_NONNEGATIVE_ROUND_TRIP_COST_PER_LOT>` |

P2 uses this scalar as per-lot friction, adding it to loss and subtracting it from
reward. Supply a conservative allowance covering applicable entry/exit commission;
do not blindly insert a one-side quote. It is not a percentage or a total cash
charge for the chosen trade volume. A validated zero is allowed, but absence is
not zero. The schema has no separate tax/swap/fee-side fields or automatic fee
schedule discovery: unresolved cost coverage requires review, not invented fields
or altered trading logic. Cost expiry has no new fixed maximum duration in this tool.

## Offline Validation

From the repository root, the owner may run AFTER filling the ignored files:

```powershell
.\backend\.venv\Scripts\python.exe -B scripts/validate_p3_operator_files.py --operator-files
```

This is an explicit operator-only read of exactly the three named files. It does
not import MetaTrader5, connect, read the terminal binary, inspect native state,
create a database, reset HALT or place orders. Reports contain fixed file labels
and statuses only; no values, account key, field-validation input or traceback.
There is no arbitrary private-path argument. Exit 0 means offline checks passed;
exit 2 means incomplete/invalid. PASS is never trading authorization.

Checks: presence, <=64 KiB, non-linked/single-link files, valid JSON/no duplicate
keys/nonstandard NaN, placeholder rejection, existing model fields/types/ranges,
native DEMO binding and version, allowlist, lexical terminal path, cross-file
account/currency, current risk periods/freshness, cost expiry and symbol coverage.
Unknown keys reject. Model coercions match existing schemas; this is not a new
strict-type trading policy. The command does not verify truth of financial evidence,
password correctness, ACL isolation, executable hash, source expiry or actual broker state.

Without `--operator-files`, it checks ONLY public example files. Expected result:
FAIL / PLACEHOLDERS for all three. That is intentional protection against using
an example as qualified evidence. This task tests only public/synthetic inputs;
it does not run the private-file mode or access existing credentials.

## Protection and Next Action

Git metadata checks confirm `backend/private/` ignore coverage for all three named
files and a representative descendant; no such paths are tracked. AGENTS.md's
Sensitive-Path Boundary prohibits ordinary agent access and requires explicit
scoped operator authorization. Git ignore and instructions are not Windows ACLs;
actual host/file permissions remain unqualified. No private files were enumerated.

After offline PASS, preserve the evidence and request a separately authorized
operator-only host/account/readiness review. That review must qualify fresh native
data, dedicated non-admin terminal isolation, DEMO identity and safe stop controls
before considering the existing gated smoke test. Do not run `--attest`, connect
MT5, unlock HALT or submit merely because these templates are filled. This task
does not authorize those actions or mark P3 complete.
