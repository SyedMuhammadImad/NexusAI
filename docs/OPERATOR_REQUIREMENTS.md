# Operator Requirements

## First Three Phases (0, 1, 2)

No new API key, broker login, paid service or model access is needed to implement
or run the local preservation, parser and ledger tests. Trading stays disabled.

| Item | Current status | What is needed from you |
|---|---|---|
| News API credential | Known exposure in historical report blobs in two sibling Git repositories | Revoke/rotate the old key through its provider. Configure any replacement locally, never in chat or Git. News remains disabled and no replacement is required for these phases. |
| Remote Git history | Local scan completed; remote publication has not been verified | Confirm the authoritative GitHub repository and authorize inspection. If affected history was published, approve a separately scoped cleanup after rotation. |
| Independent backup | Verified local snapshots and restore drill available | Choose an external drive or private backup destination and encryption method. Keep the encryption recovery key separately. Another folder on this laptop is not an independent backup. |
| Local dashboard access | Existing private control-token mechanism | Use the locally configured token. No new token needs to be sent in chat. |

Do not reuse credentials previously pasted into chat. Treat those credentials as
exposed and rotate them before any future integration is enabled. This is separate
from the confirmed news-key finding in local Git objects.

## Later Phases Only

These are not prerequisites for marking the local Phase 0-2 gates passed, and none
is permission to enable execution now.

- Demo broker: confirm the intended demo account and server, install/sign in to
  MT5 locally, and later approve read-only account attestation. Do not send the password here.
- Risk policy: choose symbol allowlist, per-trade risk budget, aggregate exposure,
  daily-loss and drawdown limits before Phase 3 policy acceptance.
- Continuous operation: select an always-on Windows machine or suitable hosting,
  plus a budget and backup destination. Laptop sleep stops local services.
- Future image extraction: choose a verified image-capable provider and spending
  limit only when the screenshot phase is reached. No vision key is needed now.
- Historical data: choose the instruments, intervals and required provenance when
  the market-data/research phases are reached. Reference data is not a broker fill.

WhatsApp credentials and ML-training keys are not required for the current rebuild.
No profitability, autonomous trading or production-readiness claim follows from
passing the software tests.
