# P8 Research Model Registry

Owned root: `research/p8-intelligence/`, ignored by Git and separate from P5 and
all lifecycle/operator databases. Marker `.p8-research` binds registry version.
Ordinary tests use fresh temporary owned roots. Linked roots/files and private/
operator/data roots reject before use. These checks are not an OS sandbox.

SQLite models table: deterministic `model_id`, immutable JSON record, actual
`created_at`. UPDATE/DELETE triggers reject. IDs exclude creation wall clock.
Each current model record carries task/track/type, dataset IDs/row hash, schema,
label version, train/test ranges, empty validation range(NO_TUNING), parameters,
seed, metrics, qualification and explicit execution_eligible=false. Runtime
versions, fitted medians/scales/category vocabulary, coefficients or complete
tree state reside in the hash-bound portable JSON model artifact.

Artifact filenames are SHA256 JSON basenames only; no pickle, absolute path,
arbitrary executable deserialization or serving. The registry verifies content
hash and row identity on read. Publication writes/fsyncs a temporary complete
artifact, then atomically publishes. Registration uses BEGIN IMMEDIATE; a
failed/dead transaction cannot leave a registered half-record. An unregistered
content-addressed orphan after process death is harmless and reused on safe retry.
Identical concurrent publication validates the existing bytes, including Windows
replace races. No credential, human raw text or checkpoint token is recorded.

Current result references15 fold-baseline artifacts and two independent audit
entries. Prior interrupted/changed research attempts remain append-only; total
registry rows can exceed17. Do not delete them to make evidence look clean.
Three prior baseline artifacts are EXPERIMENTAL; twelve learned fold artifacts
are REJECTED for overall filter qualification. Human: INSUFFICIENT_DATA.
Kronos: KRONOS_RUNTIME_BLOCKED. The full evidence result is separately registered.

Portable JSON prediction replay matches sklearn probabilities at absolute1e-12.
This is an offline research replay function, not an HTTP prediction or trade API.
Same exact fit inputs produce identical artifact/prediction hashes. Changing
schema/data/model configuration produces a different identity, never an overwrite.
Anonymous external runtime feasibility metadata may change over time; its audit
gets a new identity without invalidating deterministic Track A fit reproducibility.

Tests prove duplicate/concurrent registration, SQL immutability, tamper detection,
transaction rollback, real child-process death before commit, restart retry,
research-only flags and storage separation. Parent audit hooks do not protect
child processes; that fixture child's minimal imports/temporary paths were reviewed.
