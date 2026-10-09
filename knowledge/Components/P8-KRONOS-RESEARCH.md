# P8 Kronos Research Feasibility

**KRONOS_RUNTIME_BLOCKED. Inference, forecast accuracy and added value NOT_PROVEN.**
Do not interpret runtime failure as a negative prediction result or require a GPU
that has not been shown necessary. No installation, checkpoint download or backend
dependency change was performed.

Existing local source: `D:/quant project/kronos/Kronos-master.zip`.
Archive SHA256:92fc55519ddc46f22e0c8ac10a37cde73d6346818f4b8aa10f0e54c9f8a620ff.
Actual Git commit UNKNOWN(source ZIP, no repository metadata). Source requirements,
README and model/kronos.py hashes are recorded; no checkpoint file exists inside
the inspected archive. Unrelated/home caches were not searched.

Primary contract: [official source](https://github.com/shiyu-coder/Kronos).
OHLC plus optional volume/amount, separate input and future calendar timestamps;
float32 per-context mean/std normalization,epsilon1e-5,clipping5; sampled OHLCVA
forecast, not observed candles. Mini context2048 with its 2k tokenizer; small/base
512 with corresponding tokenizer. Research horizon fixed to1, not tuned on test.
CPU fallback exists in source; actual throughput/memory/GPU state unmeasured.

The existing backend3.14 lacks torch,pandas,einops,huggingface_hub,safetensors.
Direct torch import:ModuleNotFoundError. Anonymous
[PyPI pandas2.2.2 metadata](https://pypi.org/pypi/pandas/2.2.2/json)
confirms no Windows CPython3.14 wheel for
the source's pin. This is a backend pin incompatibility, not proof that no other
isolated Python runtime can work.

The bundled Python3.12.14 was checked: pandas present, torch/einops/HF/safetensors
absent. A compatible isolated3.12 alternative was evaluated using public wheel
metadata, not installed into this shared runtime. Torch+pandas+numpy core wheels
alone total151,130,488 bytes, exceeding this task's bounded optional dependency
download budget128MiB(134,217,728), before other modules/tokenizer/checkpoint.
This is a documented engineering resource bound, NOT an unavoidable access,
licensing, GPU or credentials blocker. A separately bounded isolated-runtime task
could revisit it; no user secret is currently required for public model metadata.

Public [Kronos-mini](https://huggingface.co/NeoQuasar/Kronos-mini) is accessible.
Queried revision:f4e68697d9d5aed55cef5c96aabc3376bcad9f81.
Model.safetensors metadata size16,440,776 bytes. This is checkpoint AVAILABILITY,
not proof of local loading, model/source compatibility or inference. Matching
tokenizer is also required. Anonymous metadata fetches use no netrc/token/HF cache.
Exact wheel names/hashes, checkpoint revision/file sizes and source hashes are in
../Audits/P8-RESEARCH-RESULTS.json, kronos; upstream metadata may change on rerun.

The P8 K-line/context adapter carries dataset/qualification/instrument/timeframe,
as-of time, complete-bar availability, context hash, explicit horizon and BID basis.
It rejects future/incomplete, unordered, mixed or oversized windows. Unknown
volume/amount stays null; any future zero-imputation must be an experiment-only
assumption and never alter P5 source candles. No forecast is admitted as real data.

Context/lineage/blocked-runtime behavior is fixture-tested. Existing P5 source
compatibility evidence remains preserved. No persistence/zero-return/trend baseline
comparison, sampled forecast or Kronos-enhanced Track A model was run. Those claims
are NOT_APPLICABLE until a qualified isolated runtime is available. The owner's
P8 exit gate explicitly allows this exact, transparent blocked-runtime disposition.
