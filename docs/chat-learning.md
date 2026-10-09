# Historical Chat Learning

Page: http://127.0.0.1:5173/#/chat-learning

Upload a WhatsApp ZIP containing one UTF-8 chat text file and optional JPG, PNG,
or WebP attachments, or upload the text alone. Choose the export's date order,
group name, and UTC offset. Defaults are day/month/year and UTC+05:00.
Messages retain their original local timestamps and are also stored as UTC epoch
timestamps. The service accepts iOS bracketed and Android dash-separated headers.

The local archive is `backend/data/chat_imports/archive.sqlite3`. It stores the
original ZIP, message text, parsed candidates, image references, and review history.
ZIP contents are read in memory, never extracted to user-supplied paths. Limits:
100 MB upload, 300 MB expanded archive, 5 MB text, 20,000 messages, 10,000 ZIP
entries and 15 MB per viewable image. Reimporting the same archive is idempotent.
Reviewed learner signals deduplicate across overlapping exports using group,
timestamp, sender and text.

Signals, updates, reported results, cancellations, media, and discussion are
heuristic categories and require human review. Candidate links use the same sender,
an optional matching symbol and the preceding 24 hours, capped at 20 suggestions.
They are not confirmed
trade relationships. Reported profits never become verified outcomes or P&L.

Only complete signals with consistent entry/stop/target geometry can be approved.
Source-based price corrections require a note and retain the previous values and
original message. Approval writes an IMPORTED example to TraderLearningStore with
execution_status NOT_APPLICABLE, outcome_status UNVERIFIED, and no current market
snapshot. Approval does not train a model or publish an execution event.

No archive content is sent to DeepSeek or WhatsApp. Images are available for manual
inspection; automatic chart extraction is not part of this import. There is no
automatic historical price verification, outcome reconstruction, or profitability
model training. The existing model learns acceptance labels, not a validated
trading strategy. Ambiguous prices must not be guessed from today's market.

Routes under `/api/private/chat-imports` use the existing control-access policy.
Like the rest of the development dashboard, authentication is not required in
development mode. Keep it on localhost; do not expose private archives publicly.
