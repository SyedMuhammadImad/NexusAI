# WhatsApp Announcement Source Identity

Recorded: 2026-10-02, Asia/Karachi. Scope: owner-authorized read-only identity
verification under ADR-001/018, NOT connector activation or broker qualification.

## Authority and actual result

The owner confirms REDACTED_OPERATOR_IDENTIFIER is the previously supplied sender ending3934,
and explicitly selects the BUY/SELL announcement community/group. No phone
number, linked-account ID or actual group ID belongs in this public document.

The actual restored WhatsApp client returned SOURCE_IDENTITY_VERIFIED, exit0.
The exact registered number mapped to an opaque LID; WhatsApp's authoritative
PN/LID result agreed with the approved phone. Both linked-account identity and
CONNECTED state were checked before/after discovery. Two distinct group IDs have
the title REDACTED_OPERATOR_IDENTIFIER: one ordinary group and one announcement group. The
approved sender is an admin/member of both. Only the announcement group is
selected, consistent with the owner's explicit scope, not a title-only allowlist.

Exact linked-account, group and sender IDs are retained in a new immutable
source-identity-UUID.json under backend/private/whatsapp/v1/. Earlier discovery
receipts are preserved, including the initially ambiguous candidate result.
No connector.json, source registry, backend token, execution switch, broker
credential or operator database was created/changed by this task.

## Implemented boundary

connectors/whatsapp/identity.mjs is OPERATOR-ONLY. It reads a small JSON request
from stdin, with only phone (international digits, no plus) and group_names
(nonempty explicit labels). No real identity is hardcoded in source or supplied
as a command-line argument. Example input must use placeholders, not live values.

It uses the same fixed dedicated LocalAuth boundary as pair.mjs; no personal
browser profile or unrelated credential directory is used. A shared pairing lock
prevents these two launchers overlapping. Dynamic dependency imports remain
outside ordinary fixture tests. No application message listeners, delivery,
outbox, chat history fetch, broker module, control token or execution path exists.

Number lookup may return PN or LID. An opaque LID is accepted ONLY when the
provider explicitly maps it back to the exact approved PN and the same LID;
suffix matching, contact names and guessed identifiers are never authority.

Metadata selection uses common groups and explicitly named cached group titles
inside the browser, because native common-group discovery did not expose the
announcement subgroup. It does not call getChats/getChatById, the message
serializer or message-history APIs. It refreshes only matching group metadata,
returns only matching titles and approved-member membership/admin evidence, and
discards other groups' names and other members' IDs before crossing that boundary.
Uncached shared metadata stays incomplete. Group-name changes during refresh,
session/account changes, missing mappings or contradictory evidence reject.

The source-inspected adapter uses wwebjs1.34.7 WAWebCollections.Chat,
WAWebWidFactory and GroupMetadata update/participant serialization semantics.
These upstream internal APIs are compatibility-sensitive. A failed read is not
permission to infer identities or weaken verification. Two matching ANNOUNCEMENT
groups remain ambiguous; a same-name ordinary group cannot authorize execution.

The private receipt is identity evidence only, not a signed/evergreen runtime
authorization. Future connector composition must bind exact IDs to the trusted
source registry and linked account, then check actual live message group/author,
original timestamp and replay identity. Old messages are not replay-authorized.
No P2 or HALT rule changes; broker execution remains HARD_DISABLED.

## Evidence and limitations

- npm test:32 passed,0 failed in0.74s; fixtures only, no real session/native reads.
- Coverage: PN/LID mapping consistency, wrong number, missing/unmatched/admin
  membership, ambiguity, duplicate group IDs, exact announcement selection,
  cached announcement outside common-group list, missing metadata, no unrelated
  message/description leakage, session changes, renamed group, request schema,
  read-only callback completion/failure and existing pairing/bridge tests.
- npm audit --json --ignore-scripts:0 known vulnerabilities,159 dependencies.
- Actual native reads prove restore without a new QR and the exact source identity.
  No message was forwarded or sent. No MT5 connection or economic action occurred.
- Preserve earlier failures: initial strict PN expectation rejected native LID;
  wrapper group serialization failed; common-group-only scan found no target;
  initial same-title matching was ambiguous. These prompted tested normalization
  and metadata-only selection changes, not fabricated success evidence.
- Several earlier Windows closes printed an already-absent-child taskkill warning.
  The final account-bound run exited0 without that warning; this is not proof
  of reliability under all native shutdown/reconnect conditions.
- Live signal arrival, source admission, HTTP delivery, supervision and economic
  integration remain unverified/unenabled. No V1/P3/P9 phase closeout follows.

Primary API references: [Client](https://docs.wwebjs.dev/Client.html),
[GroupChat](https://docs.wwebjs.dev/GroupChat.html) and source-inspected installed
Client.js / util/Injected/Utils.js. WhatsApp Web automation remains unofficial.
