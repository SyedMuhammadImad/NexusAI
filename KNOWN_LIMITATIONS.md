# Known Limitations

- Rebuild incomplete. The active app provides authenticated archive review, not trading.
- No broker connection/reconciliation or position closure was performed during the rebuild.
- Risk reservations, universal broker authorization, timeout recovery, and confirmed accounting are not yet wired.
- Account-bound ledger order/deal/position methods and process-crash recovery are verified with fixtures,
  not MT5 evidence. This does not establish broker-call idempotency or final accounting correctness.
- Unknown and netted/multiple-origin positions are not automatically attributed or adopted.
- No historical performance, profitable strategy, or trading ML has been validated.
- The existing classifier is an acceptance/QA experiment; training and influence are disabled.
- Screenshot execution, live WhatsApp, strategy voting, synthetic backtests, and test trade injection are disabled.
- Private historical outcomes and Yahoo reference estimates are not broker fills or confirmed P&L.
- Local token authentication is mandatory. TLS, multi-user authorization, comprehensive rate limiting,
  dependency security upgrades, and clean-install qualification remain unfinished.
- Local backups are hash-verified/read-only, not off-device WORM storage. A laptop failure can still lose local copies.
- The configured news API key was found in old sibling Git histories. It needs provider-side rotation;
  no history rewriting, deletion or remote publication was performed by this rebuild.
- The old agents and adapter are preserved as inactive source. Their forensic defects are not all repaired.
