# P5 Kronos Compatibility - Source Inspection Only

## Safe Local Runtime Check (2026-09-14)

Under the documented credential-free guard, numpy 2.5.2 imported successfully.
Module discovery found pandas, torch, einops, huggingface_hub and safetensors all
absent from the backend environment. A direct pandas import failed with
ModuleNotFoundError; this is an actual runtime blocker, not an inferred version
incompatibility. The subsequent presence check exited 0 with six guard self-tests,
zero sensitive/operator attempts and no forbidden runtime modules.

No dependencies/checkpoints were installed and no model imported, trained or run.
Minimal model shape execution is NOT_PROVEN. Canonical OHLC and UTC timestamps
match the inspected source field contract, but missing volume/amount and float32
loss require an explicit isolated adapter/experiment sidecar as described below.
No lossless end-to-end compatibility claim is made. Status remains PARTIAL;
Kronos runtime is not a P5 exit prerequisite under ADR-013.

Inspected 2026-09-14 without extraction, installation, imports or execution:
`D:/quant project/kronos/Kronos-master.zip`.
SHA256: `92fc55519ddc46f22e0c8ac10a37cde73d6346818f4b8aa10f0e54c9f8a620ff`.
The inspected directory contains a source archive, not proof of an installed or
working runtime. No `.safetensors`, `.pt`, `.pth` or `.bin` checkpoint entries
were found inside that archive. Other model caches/private locations were not searched.

## Code-Evidenced Contract

References below are ZIP members, not imported modules:
`Kronos-master/model/kronos.py`, `README.md`, `requirements.txt`.

| Concern | Inspected behavior |
|---|---|
| Required schema/order | `KronosPredictor` line 489: open, high, low, close; final input at line 540 appends volume, amount |
| Missing volume | Lines 528-532: absent volume/amount filled with zero; absent amount with volume present estimated from mean OHLC times volume |
| Time input | Separate pandas Series x_timestamp/y_timestamp; minute, hour, weekday, day, month features (line 472) |
| Timeframe | No explicit 1H/4H whitelist in predictor. Caller supplies timestamps. This does not prove equal predictive validity across timeframes or sessions |
| Context | Predictor default max_context=512; README lists small/base 512, mini 2048; matching tokenizer/model required |
| Horizon | Caller specifies positive pred_len and matching future timestamp length; fixed rolling context. P5 does not approve a forecasting horizon |
| Preprocessing | Lines 540-547: float32 conversion, per-input-window mean/std, epsilon 1e-5 and clipping (default 5) |
| Output | Line 558: predicted OHLC, volume, amount DataFrame indexed by supplied future timestamps; sampled autoregressive outputs, not actual candles |
| Hardware | Line 496: CUDA preferred, then MPS, otherwise CPU; actual GPU availability/performance not inspected or proven |
| Checkpoints | README examples load NeoQuasar/Kronos-Tokenizer-base + Kronos-small; mini requires its 2k tokenizer. No checkpoint downloaded or loaded |
| Runtime | README says Python 3.10+. Requirements include torch>=2.0.0, numpy, pandas and pinned pandas==2.2.2, einops==0.8.1, huggingface_hub==0.33.1, matplotlib==3.9.3, tqdm==4.67.1, safetensors==0.6.2 |

The inspected dependency pins are not verified compatible with NexusAI's Python
3.14 environment. Do not install them into the working backend merely to satisfy
an import. Future experimentation requires an isolated environment and tested
checkpoint/runtime pairing. No CPU/GPU memory or throughput claim is made.

## NexusAI Mapping and Losses

P5 Candle.open/high/low/close map directly to corresponding columns; opened is the
UTC input timestamp and closed is the earliest time the complete bar is available.
HistData volume is unavailable, not measured zero. P5 keeps volume/spread null and
volume_kind=NONE. Kronos's zero-filling must be an explicit experiment assumption,
never written back into the canonical store as measured volume. Actual traded
amount cannot be reconstructed from these data.

This is NOT a lossless end-to-end conversion: Decimal to float32 loses precision;
Kronos does not carry dataset/provider/quality identity; missing volume/amount are
imputed and outputs are stochastic model results. A future separate adapter must
export a selected immutable dataset/window plus a provenance/quality sidecar,
record rounding and missing-volume treatment, and leave the canonical data intact.
No adapter invocation, forecast, training or model qualification is part of P5.
Compatibility status: PARTIAL (schema/code inspected, runtime unverified).

## Leakage and Evidence Boundaries

- Query only completed candles at each simulated decision time; never expose the
  containing candle's later high/low/close. Retain dataset version and ingestion
  vintage; later provider corrections were not known in the original historical run.
- Split chronologically and fit any preprocessing on the permitted past window
  only. The predictor computes statistics over all supplied rows, so supplying
  future observations leaks information even if timestamps look correct.
- Future timestamps may describe a known calendar, never future prices or an
  assumed gap-free session. Do not compress gaps without an explicit experiment rule.
- Save model/tokenizer/version, context/horizon, seed, sampling settings and
  dependency versions. A model output must not enter the REAL candle store.
- Bar-level TP/SL order can remain AMBIGUOUS (ADR-004); forecasts cannot resolve
  historical ordering or become verified economic labels.
- No predictive value, profitability or execution qualification is claimed.
