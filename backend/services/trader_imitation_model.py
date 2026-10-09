"""Offline, observation-only ML model for private trader signal patterns."""

from __future__ import annotations

import json
import math
import time
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

import numpy as np

from services.trader_learning_store import TraderLearningStore


DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parents[1]
    / "models"
    / "checkpoints"
    / "private_trader_imitation_model.json"
)


class TraderImitationModelService:
    """Trains and serves a local shadow-only imitation classifier."""

    feature_names = [
        "direction_buy",
        "direction_sell",
        "parser_confidence",
        "has_entry_price",
        "risk_distance_pct",
        "reward_distance_pct",
        "risk_reward_ratio",
        "hour_sin",
        "hour_cos",
        "weekday_sin",
        "weekday_cos",
        "spread_bps_scaled",
        "rsi_scaled",
        "symbol_bucket_0",
        "symbol_bucket_1",
        "symbol_bucket_2",
        "symbol_bucket_3",
    ]

    accepted_statuses = {"ACCEPTED", "IMPORTED", "PARSED", "SUBMITTED"}

    def __init__(
        self,
        *,
        store: Optional[TraderLearningStore] = None,
        model_path: Optional[str | Path] = None,
        min_examples: int = 5,
    ):
        self.store = store or TraderLearningStore()
        self.model_path = Path(model_path or DEFAULT_MODEL_PATH)
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        self.min_examples = max(2, int(min_examples))

    def status(self) -> dict:
        artifact = self._load_artifact()
        examples = self.store.training_examples(limit=20000)
        dataset = self._dataset_summary(examples)
        if not artifact:
            return {
                "trained": False,
                "execution_enabled": False,
                "mode": "shadow_only",
                "artifact_path": str(self.model_path),
                "dataset": dataset,
                "reason": "No local imitation model artifact exists yet.",
                "timestamp": time.time(),
            }
        return {
            **artifact.get("public", {}),
            "trained": True,
            "execution_enabled": False,
            "mode": "shadow_only",
            "artifact_path": str(self.model_path),
            "dataset": dataset,
            "timestamp": time.time(),
        }

    def train(self, *, limit: int = 5000) -> dict:
        examples = sorted(self.store.training_examples(limit=limit),
                          key=lambda row: (self._float(row.get("signal_timestamp"), 0.0), row.get("signal_id", "")))
        dataset = self._build_dataset(examples)
        if dataset["X"].shape[0] < self.min_examples:
            return self._untrained_result(
                examples,
                f"Need at least {self.min_examples} stored signal examples for training.",
            )
        if len(set(dataset["y"].tolist())) < 2:
            return self._untrained_result(
                examples,
                "Need both accepted and rejected examples before a classifier can learn a boundary.",
            )

        X = dataset["X"].astype(float)
        y = dataset["y"].astype(float)
        split = self._split_index(len(y))
        if len(set(y[:split].tolist())) < 2:
            return self._untrained_result(examples, "Chronological training partition needs accepted and rejected examples.")
        mean = X[:split].mean(axis=0)
        std = X[:split].std(axis=0)
        std[std == 0] = 1.0
        Xn = (X - mean) / std
        train_X, val_X = Xn[:split], Xn[split:]
        train_y, val_y = y[:split], y[split:]

        weights, train_loss = self._fit_logistic(train_X, train_y)
        train_prob = self._predict_proba(train_X, weights)
        train_acc = float(((train_prob >= 0.5) == train_y).mean())
        metrics = {
            "train_size": int(train_y.shape[0]),
            "validation_size": int(val_y.shape[0]),
            "train_log_loss": round(float(train_loss), 6),
            "train_accuracy": round(train_acc, 4),
        }
        if val_y.shape[0]:
            val_prob = self._predict_proba(val_X, weights)
            metrics["validation_log_loss"] = round(float(self._log_loss(val_y, val_prob)), 6)
            metrics["validation_accuracy"] = round(float(((val_prob >= 0.5) == val_y).mean()), 4)
            metrics["validation_majority_baseline"] = round(float(max(val_y.mean(), 1 - val_y.mean())), 4)
            metrics["validation_has_both_classes"] = len(set(val_y.tolist())) == 2

        artifact = {
            "version": "private_signal_acceptance_logistic_v2",
            "trained_at": time.time(),
            "feature_names": self.feature_names,
            "weights": weights.tolist(),
            "mean": mean.tolist(),
            "std": std.tolist(),
            "public": {
                "model_type": "numpy_logistic_regression",
                "target": "signal_validation_acceptance",
                "evaluation": "chronological_split_train_only_scaling",
                "limitations": ["Predicts validation acceptance, not trading profitability",
                                "Small dataset; no independent strategy validation"],
                "trained_at": time.time(),
                "metrics": metrics,
                "feature_names": self.feature_names,
                "dataset": self._dataset_summary(examples),
                "execution_enabled": False,
                "mode": "shadow_only",
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", dir=self.model_path.parent, delete=False, encoding="utf-8") as handle:
            temp_path = Path(handle.name)
            json.dump(artifact, handle, indent=2, allow_nan=False)
        try:
            os.replace(temp_path, self.model_path)
        finally:
            temp_path.unlink(missing_ok=True)
        shadow_predictions = self._record_shadow_predictions(dataset["examples"], artifact, max_items=100)
        return {
            **artifact["public"],
            "trained": True,
            "artifact_path": str(self.model_path),
            "shadow_predictions_written": shadow_predictions,
            "timestamp": time.time(),
        }

    def predict_example(self, example: dict) -> dict:
        artifact = self._load_artifact()
        features = self._features(example)
        if not artifact:
            return {
                "available": False,
                "execution_enabled": False,
                "mode": "shadow_only",
                "features": features,
                "reason": "No trained model artifact exists.",
            }
        probability = self._score_features(features, artifact)
        return {
            "available": True,
            "execution_enabled": False,
            "mode": "shadow_only",
            "imitation_probability": round(probability, 4),
            "features": dict(zip(self.feature_names, features)),
        }

    def _build_dataset(self, examples: list[dict]) -> dict:
        X = []
        y = []
        used = []
        for example in examples:
            signal = example.get("parsed_signal") or {}
            status = str(example.get("validation_status") or signal.get("validation_status") or "").upper()
            has_core_fields = bool(example.get("instrument") and example.get("direction"))
            if status not in self.accepted_statuses | {"REJECTED"} or not has_core_fields:
                continue
            X.append(self._features(example))
            y.append(1.0 if status in self.accepted_statuses else 0.0)
            used.append(example)
        return {
            "X": np.asarray(X, dtype=float),
            "y": np.asarray(y, dtype=float),
            "examples": used,
        }

    def _features(self, example: dict) -> list[float]:
        signal = example.get("parsed_signal") or {}
        snapshot = example.get("market_snapshot") or {}
        direction = str(example.get("direction") or signal.get("direction") or "").upper()
        symbol = str(example.get("instrument") or signal.get("instrument") or "")
        parser_confidence = self._float(signal.get("parser_confidence"), 0.0)
        entry = self._float(example.get("entry_price") or signal.get("entry_price"), None)
        stop_loss = self._float(example.get("stop_loss") or signal.get("stop_loss"), None)
        take_profit = self._float(
            example.get("take_profit")
            or signal.get("take_profit_1")
            or signal.get("take_profit"),
            None,
        )
        price = self._float(snapshot.get("price") or entry, None)
        risk_pct = 0.0
        reward_pct = 0.0
        rr = 0.0
        if price and price > 0 and stop_loss is not None and take_profit is not None:
            risk = abs(price - stop_loss)
            reward = abs(take_profit - price)
            risk_pct = min(risk / price, 1.0)
            reward_pct = min(reward / price, 1.0)
            rr = min(reward / max(risk, 1e-12), 10.0) / 10.0

        timestamp = self._float(example.get("signal_timestamp") or signal.get("message_timestamp"), time.time())
        hour, weekday = self._time_parts(timestamp)
        bucket = sum(ord(ch) for ch in symbol.upper()) % 4 if symbol else 0
        buckets = [1.0 if bucket == index else 0.0 for index in range(4)]
        return [
            1.0 if direction == "BUY" else 0.0,
            1.0 if direction == "SELL" else 0.0,
            min(max(parser_confidence, 0.0), 1.0),
            1.0 if entry is not None else 0.0,
            risk_pct,
            reward_pct,
            rr,
            math.sin(2 * math.pi * hour / 24),
            math.cos(2 * math.pi * hour / 24),
            math.sin(2 * math.pi * weekday / 7),
            math.cos(2 * math.pi * weekday / 7),
            min(max(self._float(snapshot.get("spread_bps"), 0.0) / 100.0, 0.0), 10.0),
            min(max(self._float(snapshot.get("rsi"), 50.0) / 100.0, 0.0), 1.0),
            *buckets,
        ]

    def _fit_logistic(self, X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
        Xb = np.c_[np.ones(X.shape[0]), X]
        weights = np.zeros(Xb.shape[1], dtype=float)
        lr = 0.08
        l2 = 0.001
        for _ in range(600):
            pred = self._sigmoid(Xb @ weights)
            gradient = (Xb.T @ (pred - y)) / y.shape[0]
            gradient[1:] += l2 * weights[1:]
            weights -= lr * gradient
        return weights, self._log_loss(y, self._sigmoid(Xb @ weights))

    def _record_shadow_predictions(self, examples: list[dict], artifact: dict, *, max_items: int) -> int:
        count = 0
        for example in examples[-max_items:]:
            signal = example.get("parsed_signal") or {}
            features = self._features(example)
            probability = self._score_features(features, artifact)
            self.store.record_shadow_prediction(
                symbol=example.get("instrument") or signal.get("instrument") or "UNKNOWN",
                direction=example.get("direction") or signal.get("direction") or "UNKNOWN",
                predicted_entry=example.get("entry_price") or signal.get("entry_price"),
                stop_loss=example.get("stop_loss") or signal.get("stop_loss"),
                take_profit=example.get("take_profit") or signal.get("take_profit_1"),
                imitation_probability=round(probability, 6),
                performance_quality=None,
                features=dict(zip(self.feature_names, features)),
                matched_signal_id=example.get("signal_id"),
                match_quality={"model_version": artifact.get("version")},
                outcome={
                    "outcome_status": example.get("outcome_status"),
                    "pnl": example.get("pnl"),
                },
                prediction_id=f"shadow-{example.get('signal_id')}",
            )
            count += 1
        return count

    def _score_features(self, features: list[float], artifact: dict) -> float:
        mean = np.asarray(artifact.get("mean") or [], dtype=float)
        std = np.asarray(artifact.get("std") or [], dtype=float)
        weights = np.asarray(artifact.get("weights") or [], dtype=float)
        x = np.asarray(features, dtype=float)
        if x.shape[0] != mean.shape[0] or weights.shape[0] != x.shape[0] + 1:
            return 0.0
        xn = (x - mean) / np.where(std == 0, 1.0, std)
        return float(self._sigmoid(np.r_[1.0, xn] @ weights))

    def _dataset_summary(self, examples: list[dict]) -> dict:
        statuses: dict[str, int] = {}
        symbols: dict[str, int] = {}
        closed = 0
        for example in examples:
            status = str(example.get("validation_status") or "UNKNOWN").upper()
            symbol = str(example.get("instrument") or "UNKNOWN")
            statuses[status] = statuses.get(status, 0) + 1
            symbols[symbol] = symbols.get(symbol, 0) + 1
            if example.get("outcome_status") == "CLOSED":
                closed += 1
        return {
            "examples": len(examples),
            "closed_examples": closed,
            "statuses": statuses,
            "symbols": dict(sorted(symbols.items(), key=lambda item: item[1], reverse=True)[:20]),
            "min_examples": self.min_examples,
        }

    def _untrained_result(self, examples: list[dict], reason: str) -> dict:
        return {
            "trained": False,
            "execution_enabled": False,
            "mode": "shadow_only",
            "artifact_path": str(self.model_path),
            "dataset": self._dataset_summary(examples),
            "reason": reason,
            "timestamp": time.time(),
        }

    def _load_artifact(self) -> Optional[dict]:
        if not self.model_path.exists():
            return None
        try:
            return json.loads(self.model_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _split_index(self, count: int) -> int:
        if count < 10:
            return count
        return max(2, int(count * 0.8))

    def _time_parts(self, timestamp: float) -> tuple[int, int]:
        try:
            tm = time.gmtime(float(timestamp))
            return tm.tm_hour, tm.tm_wday
        except (TypeError, ValueError, OSError):
            tm = time.gmtime()
            return tm.tm_hour, tm.tm_wday

    def _predict_proba(self, X: np.ndarray, weights: np.ndarray) -> np.ndarray:
        return self._sigmoid(np.c_[np.ones(X.shape[0]), X] @ weights)

    def _sigmoid(self, z: Any) -> Any:
        return 1.0 / (1.0 + np.exp(-np.clip(z, -35, 35)))

    def _log_loss(self, y: np.ndarray, probability: np.ndarray) -> float:
        probability = np.clip(probability, 1e-9, 1 - 1e-9)
        return float(-(y * np.log(probability) + (1 - y) * np.log(1 - probability)).mean())

    def _float(self, value: Any, default: Optional[float]) -> Optional[float]:
        try:
            result = float(value)
            return result if math.isfinite(result) else default
        except (TypeError, ValueError):
            return default
