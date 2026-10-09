"""
Exness MT5 demo integration.

This adapter supports account snapshots, symbol quotes, broker position
reconciliation, and guarded order placement for local MT5 demo accounts.
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


SUCCESSFUL_CHECK_RETCODES = {0, 10008, 10009, 10010}
SUCCESSFUL_SEND_RETCODES = {10008, 10009, 10010}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _parse_symbol_map(raw: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for part in raw.split(","):
        if ":" not in part:
            continue
        source, broker = part.split(":", 1)
        source = source.strip()
        broker = broker.strip()
        if source and broker:
            mapping[source.casefold()] = broker
    return mapping


def _mask_login(login: Optional[int]) -> Optional[str]:
    if login is None:
        return None
    value = str(login)
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}***{value[-2:]}"


def _to_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "_asdict"):
        return dict(value._asdict())
    if isinstance(value, dict):
        return value
    return {
        key: getattr(value, key)
        for key in dir(value)
        if not key.startswith("_") and not callable(getattr(value, key))
    }


def _json_number(value: Any) -> float:
    if hasattr(value, "item"):
        value = value.item()
    return float(value)


@dataclass(frozen=True)
class ExnessMT5Config:
    login: Optional[int]
    password: str
    server: str
    terminal_path: str
    symbols: tuple[str, ...]
    trade_symbols: tuple[str, ...] = ()
    symbol_map: Dict[str, str] = field(default_factory=dict)
    enable_demo_trading: bool = False
    allow_min_volume_round_up: bool = False
    max_order_volume: float = 0.01
    max_order_risk_usd: float = 2.0
    deviation_points: int = 20
    magic: int = 260831

    @classmethod
    def from_env(cls) -> "ExnessMT5Config":
        raw_login = os.getenv("EXNESS_DEMO_LOGIN", "").strip()
        login = int(raw_login) if raw_login.isdigit() else None
        raw_symbols = os.getenv("EXNESS_SYMBOLS", "XAUUSDm,EURUSDm,BTCUSDm,USOILm")
        symbols = tuple(s.strip() for s in raw_symbols.split(",") if s.strip())
        raw_trade_symbols = os.getenv("EXNESS_TRADE_SYMBOLS", "EURUSDm,USOILm")
        trade_symbols = tuple(s.strip() for s in raw_trade_symbols.split(",") if s.strip())
        raw_symbol_map = os.getenv(
            "EXNESS_SYMBOL_MAP",
            "BTC-USD:BTCUSDm,BTCUSD:BTCUSDm,ETH-USD:ETHUSDm,ETHUSD:ETHUSDm,"
            "EUR-USD:EURUSDm,EURUSD:EURUSDm,GBP-USD:GBPUSDm,GBPUSD:GBPUSDm,"
            "XAUUSD:XAUUSDm,GOLD:XAUUSDm,USOIL:USOILm,WTI:USOILm,"
            "XAUUSDm:XAUUSDm,EURUSDm:EURUSDm,BTCUSDm:BTCUSDm,USOILm:USOILm",
        )
        return cls(
            login=login,
            password=os.getenv("EXNESS_DEMO_PASSWORD", ""),
            server=os.getenv("EXNESS_DEMO_SERVER", ""),
            terminal_path=os.getenv("EXNESS_MT5_PATH", ""),
            symbols=symbols,
            trade_symbols=trade_symbols,
            symbol_map=_parse_symbol_map(raw_symbol_map),
            enable_demo_trading=_env_bool("EXNESS_ENABLE_DEMO_TRADING", False),
            allow_min_volume_round_up=_env_bool("EXNESS_ALLOW_MIN_VOLUME_ROUND_UP", False),
            max_order_volume=_env_float("EXNESS_MAX_ORDER_VOLUME", 0.01),
            max_order_risk_usd=_env_float("EXNESS_MAX_ORDER_RISK_USD", 2.0),
            deviation_points=int(_env_float("EXNESS_DEVIATION_POINTS", 20)),
            magic=int(_env_float("EXNESS_MAGIC", 260831)),
        )

    @property
    def configured(self) -> bool:
        return bool(self.login and self.password and self.server)

    def public_dict(self) -> Dict[str, Any]:
        return {
            "configured": self.configured,
            "login": _mask_login(self.login),
            "server": self.server or None,
            "terminal_path": self.terminal_path or None,
            "symbols": list(self.symbols),
            "trade_symbols": list(self.trade_symbols),
            "demo_trading_enabled": self.enable_demo_trading,
            "allow_min_volume_round_up": self.allow_min_volume_round_up,
            "max_order_volume": self.max_order_volume,
            "max_order_risk_usd": self.max_order_risk_usd,
            "deviation_points": self.deviation_points,
            "magic": self.magic,
        }


class ExnessMT5DemoBroker:
    def __init__(self, config: Optional[ExnessMT5Config] = None, mt5_module: Any = None):
        self.config = config or ExnessMT5Config.from_env()
        self._mt5 = mt5_module
        self._connected = False
        self._last_error: Optional[str] = None
        self._connected_at: Optional[float] = None

    def _load_mt5(self) -> Any:
        if self._mt5 is not None:
            return self._mt5
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            self._last_error = "MetaTrader5 package is not installed"
            raise RuntimeError(self._last_error) from exc
        self._mt5 = mt5
        return mt5

    @property
    def configured(self) -> bool:
        return self.config.configured

    @property
    def connected(self) -> bool:
        return self._connected

    def status(self) -> Dict[str, Any]:
        package_available = self._mt5 is not None
        if self._mt5 is None:
            try:
                self._load_mt5()
                package_available = True
            except RuntimeError:
                package_available = False

        return {
            "broker": "exness_mt5",
            "mode": "demo_trading" if self.config.enable_demo_trading else "read_only_demo",
            "read_only": not (self.config.enable_demo_trading and self._connected),
            "trade_execution_enabled": self.config.enable_demo_trading and self._connected,
            "configured": self.configured,
            "connected": self._connected,
            "connected_at": self._connected_at,
            "package_available": package_available,
            "last_error": self._last_error,
            "config": self.config.public_dict(),
        }

    def connect(self) -> Dict[str, Any]:
        if not self.configured:
            self._connected = False
            self._last_error = (
                "Set EXNESS_DEMO_LOGIN, EXNESS_DEMO_PASSWORD, and "
                "EXNESS_DEMO_SERVER in backend/.env"
            )
            return self.status()

        try:
            mt5 = self._load_mt5()
            init_kwargs: Dict[str, Any] = {
                "login": self.config.login,
                "password": self.config.password,
                "server": self.config.server,
            }
            if self.config.terminal_path:
                init_kwargs["path"] = self.config.terminal_path

            if not mt5.initialize(**init_kwargs):
                self._connected = False
                self._last_error = f"MT5 initialize failed: {mt5.last_error()}"
                return self.status()

            account = mt5.account_info()
            if account is None:
                self._connected = False
                self._last_error = f"MT5 account_info failed: {mt5.last_error()}"
                return self.status()

            self._connected = True
            self._connected_at = time.time()
            self._last_error = None
            return self.status()
        except Exception as exc:
            self._connected = False
            self._last_error = str(exc)
            return self.status()

    def shutdown(self) -> Dict[str, Any]:
        try:
            if self._mt5 is not None:
                self._mt5.shutdown()
        finally:
            self._connected = False
            self._connected_at = None
        return self.status()

    def _resolve_symbol(self, symbol: str) -> str:
        requested = symbol.strip()
        mapped = self.config.symbol_map.get(requested.casefold())
        if mapped:
            return mapped
        for configured_symbol in self.config.symbols:
            if configured_symbol.casefold() == requested.casefold():
                return configured_symbol
        return requested

    def resolve_symbol(self, symbol: str) -> str:
        return self._resolve_symbol(symbol)

    def _is_demo_account(self) -> bool:
        if self._mt5 is None:
            return False
        account = _to_dict(self._mt5.account_info())
        trade_mode = account.get("trade_mode")
        demo_mode = getattr(self._mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
        return trade_mode == demo_mode

    def account_info(self) -> Dict[str, Any]:
        status = self.connect() if not self._connected else self.status()
        if not status["connected"]:
            return {"status": status, "account": None}

        account = _to_dict(self._mt5.account_info())
        safe_fields = [
            "login",
            "server",
            "name",
            "company",
            "currency",
            "balance",
            "equity",
            "margin",
            "margin_free",
            "margin_level",
            "leverage",
            "trade_mode",
        ]
        safe_account = {field: account.get(field) for field in safe_fields if field in account}
        if "login" in safe_account:
            safe_account["login"] = _mask_login(safe_account["login"])
        return {"status": self.status(), "account": safe_account}

    def positions(self) -> Dict[str, Any]:
        status = self.connect() if not self._connected else self.status()
        if not status["connected"]:
            return {"status": status, "positions": []}

        positions = []
        for position in self._mt5.positions_get() or ():
            positions.append(self._public_position(position))
        return {"status": self.status(), "positions": positions}

    def _public_position(self, position: Any) -> Dict[str, Any]:
        data = _to_dict(position)
        symbol = data.get("symbol")
        volume = float(data.get("volume") or 0)
        price_open = float(data.get("price_open") or 0)
        price_current = float(data.get("price_current") or price_open or 0)
        position_type = data.get("type")
        buy_type = getattr(self._mt5, "POSITION_TYPE_BUY", 0)
        direction = "BUY" if position_type == buy_type else "SELL"
        contract_size = 1.0
        margin_required = None
        notional_usd = None

        if symbol:
            info = _to_dict(self._mt5.symbol_info(symbol))
            contract_size = float(info.get("trade_contract_size") or 1.0)
            order_type = self._mt5.ORDER_TYPE_BUY if direction == "BUY" else self._mt5.ORDER_TYPE_SELL
            margin = self._mt5.order_calc_margin(order_type, symbol, volume, price_current)
            margin_required = round(float(margin), 2) if margin is not None else None
            notional_usd = round(price_current * volume * contract_size, 2)

        return {
            "ticket": data.get("ticket"),
            "symbol": symbol,
            "direction": direction,
            "volume_lots": volume,
            "quantity": volume * contract_size,
            "price_open": price_open,
            "price_current": price_current,
            "stop_loss": data.get("sl"),
            "take_profit": data.get("tp"),
            "profit": float(data.get("profit") or 0),
            "margin_required": margin_required,
            "notional_usd": notional_usd,
            "time": data.get("time"),
        }

    def quote(self, symbol: str) -> Dict[str, Any]:
        broker_symbol = self._resolve_symbol(symbol)
        if not broker_symbol:
            return {"status": self.status(), "quote": None, "error": "symbol is required"}

        status = self.connect() if not self._connected else self.status()
        if not status["connected"]:
            return {"status": status, "quote": None}

        self._mt5.symbol_select(broker_symbol, True)
        tick = self._mt5.symbol_info_tick(broker_symbol)
        if tick is None:
            self._last_error = f"MT5 symbol_info_tick failed for {broker_symbol}: {self._mt5.last_error()}"
            return {"status": self.status(), "quote": None}

        data = _to_dict(tick)
        return {
            "status": self.status(),
            "quote": {
                "symbol": broker_symbol,
                "bid": data.get("bid"),
                "ask": data.get("ask"),
                "last": data.get("last"),
                "time": data.get("time"),
                "time_msc": data.get("time_msc"),
            },
        }

    def market_data_payload(self, symbol: str) -> Dict[str, Any]:
        result = self.quote(symbol)
        quote = result.get("quote")
        if not quote:
            return {"status": result.get("status"), "payload": None}

        bid = float(quote.get("bid") or 0)
        ask = float(quote.get("ask") or 0)
        if bid <= 0 or ask <= 0:
            return {"status": self.status(), "payload": None}

        price = (bid + ask) / 2
        spread_bps = (ask - bid) / price * 10_000 if price > 0 else 0
        ohlcv = self._ohlcv_rates(quote["symbol"], count=240)
        return {
            "status": self.status(),
            "payload": {
                "symbol": quote["symbol"],
                "asset_class": "broker",
                "price": round(price, 6),
                "bid": round(bid, 6),
                "ask": round(ask, 6),
                "volume": 0.0,
                "timestamp": time.time(),
                "spread_bps": round(spread_bps, 2),
                "ohlcv": ohlcv,
                "ohlcv_timeframe": "M1" if ohlcv else None,
                "vix": 20.0,
            },
        }

    def _ohlcv_rates(self, symbol: str, count: int = 240) -> List[dict]:
        copy_rates = getattr(self._mt5, "copy_rates_from_pos", None)
        if copy_rates is None:
            return []
        timeframe = getattr(self._mt5, "TIMEFRAME_M1", 1)
        try:
            rates = copy_rates(symbol, timeframe, 0, count)
        except Exception as exc:
            self._last_error = f"MT5 copy_rates_from_pos failed for {symbol}: {exc}"
            return []
        if rates is None:
            return []

        candles = []
        for rate in rates:
            try:
                if isinstance(rate, dict):
                    raw = rate
                elif getattr(rate, "dtype", None) is not None and rate.dtype.names:
                    raw = {name: rate[name] for name in rate.dtype.names}
                else:
                    raw = _to_dict(rate)
                candles.append({
                    "time": _json_number(raw.get("time", 0)),
                    "open": _json_number(raw.get("open", 0)),
                    "high": _json_number(raw.get("high", 0)),
                    "low": _json_number(raw.get("low", 0)),
                    "close": _json_number(raw.get("close", 0)),
                    "tick_volume": _json_number(raw.get("tick_volume", 0)),
                    "real_volume": _json_number(raw.get("real_volume", 0)),
                })
            except (TypeError, ValueError):
                continue
        return candles

    def submit_market_order(self, order: Any) -> Dict[str, Any]:
        status = self.connect() if not self._connected else self.status()
        if not status["connected"]:
            return {"ok": False, "reason": status.get("last_error") or "broker not connected"}
        if not self.config.enable_demo_trading:
            return {"ok": False, "reason": "Set EXNESS_ENABLE_DEMO_TRADING=true to allow demo orders"}
        if not self._is_demo_account():
            return {"ok": False, "reason": "Connected account is not an MT5 demo account"}

        symbol = self._resolve_symbol(order.symbol)
        if self.config.trade_symbols and not any(
            allowed.casefold() == symbol.casefold() for allowed in self.config.trade_symbols
        ):
            return {"ok": False, "reason": f"{symbol} is not enabled in EXNESS_TRADE_SYMBOLS"}

        direction = order.direction.upper()
        if direction not in {"BUY", "SELL"}:
            return {"ok": False, "reason": f"unsupported direction {order.direction}"}

        self._mt5.symbol_select(symbol, True)
        tick = _to_dict(self._mt5.symbol_info_tick(symbol))
        if not tick:
            return {"ok": False, "reason": f"missing tick for {symbol}: {self._mt5.last_error()}"}

        raw_price = tick.get("ask") if direction == "BUY" else tick.get("bid")
        price = float(raw_price or 0)
        if price <= 0:
            return {"ok": False, "reason": f"invalid {direction} price for {symbol}"}

        symbol_info = _to_dict(self._mt5.symbol_info(symbol))
        volume_result = self._volume_for_order(order, symbol_info)
        if not volume_result["ok"]:
            return volume_result

        contract_size = float(symbol_info.get("trade_contract_size") or 1.0)
        fill_quantity = volume_result["volume"] * contract_size
        notional_usd = price * fill_quantity
        margin_required = self._calculate_margin(direction, symbol, volume_result["volume"], price)
        actual_risk_usd = self._actual_risk_usd(direction, price, order.stop_loss, fill_quantity)
        intended_risk_usd = float(getattr(order, "risk_amount_usd", 0) or 0)
        max_risk_usd = intended_risk_usd if intended_risk_usd > 0 else self.config.max_order_risk_usd
        if actual_risk_usd is not None and actual_risk_usd > max_risk_usd + 1e-9:
            return {
                "ok": False,
                "reason": (
                    f"broker minimum volume risk ${actual_risk_usd:.2f} exceeds approved "
                    f"risk ${max_risk_usd:.2f}"
                ),
                "symbol": symbol,
                "volume_lots": volume_result["volume"],
                "fill_quantity": fill_quantity,
                "notional_usd": notional_usd,
                "margin_required": margin_required,
                "actual_risk_usd": actual_risk_usd,
            }

        request = self._build_deal_request(
            symbol=symbol,
            direction=direction,
            volume=volume_result["volume"],
            price=price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
        )
        check = _to_dict(self._mt5.order_check(request))
        check_retcode = check.get("retcode")
        if check_retcode not in SUCCESSFUL_CHECK_RETCODES:
            return {
                "ok": False,
                "reason": f"MT5 order_check failed: {check_retcode} {check.get('comment')}",
                "request": _sanitize_request(request),
                "check": check,
            }

        sent = _to_dict(self._mt5.order_send(request))
        send_retcode = sent.get("retcode")
        if send_retcode not in SUCCESSFUL_SEND_RETCODES:
            return {
                "ok": False,
                "reason": f"MT5 order_send failed: {send_retcode} {sent.get('comment')}",
                "request": _sanitize_request(request),
                "check": check,
                "send": sent,
            }

        fill_price = float(sent.get("price") or price)
        fill_volume = float(sent.get("volume") or request["volume"])
        filled_quantity = fill_volume * contract_size
        filled_notional = fill_price * filled_quantity
        filled_margin = self._calculate_margin(direction, symbol, fill_volume, fill_price)
        filled_risk = self._actual_risk_usd(direction, fill_price, order.stop_loss, filled_quantity)
        return {
            "ok": True,
            "broker": "exness_mt5",
            "symbol": symbol,
            "direction": direction,
            "fill_price": fill_price,
            "fill_quantity": filled_quantity,
            "volume_lots": fill_volume,
            "position_size_usd": filled_margin if filled_margin is not None else filled_notional,
            "notional_usd": filled_notional,
            "margin_required": filled_margin,
            "actual_risk_usd": filled_risk,
            "broker_order_id": sent.get("order"),
            "broker_deal_id": sent.get("deal"),
            "retcode": send_retcode,
            "comment": sent.get("comment"),
            "request": _sanitize_request(request),
        }

    def close_all_positions(self) -> Dict[str, Any]:
        status = self.connect() if not self._connected else self.status()
        if not status["connected"]:
            return {"ok": False, "reason": status.get("last_error") or "broker not connected", "closed": []}
        if not self.config.enable_demo_trading:
            return {"ok": False, "reason": "demo trading is disabled", "closed": []}
        if not self._is_demo_account():
            return {"ok": False, "reason": "connected account is not an MT5 demo account", "closed": []}

        positions = self._mt5.positions_get() or ()
        closed = []
        for position in positions:
            closed.append(self._close_position(position))
        return {"ok": all(item.get("ok") for item in closed), "closed": closed}

    def modify_position_levels(
        self,
        *,
        symbol: str,
        stop_loss: float,
        take_profit: float,
        direction: Optional[str] = None,
        ticket: Optional[int] = None,
    ) -> Dict[str, Any]:
        status = self.connect() if not self._connected else self.status()
        if not status["connected"]:
            return {"ok": False, "reason": status.get("last_error") or "broker not connected"}
        if not self.config.enable_demo_trading:
            return {"ok": False, "reason": "demo trading is disabled"}
        if not self._is_demo_account():
            return {"ok": False, "reason": "connected account is not an MT5 demo account"}
        if stop_loss <= 0 or take_profit <= 0:
            return {"ok": False, "reason": "stop_loss and take_profit must be positive"}

        broker_symbol = self._resolve_symbol(symbol)
        requested_direction = direction.upper() if direction else None
        positions = self._matching_positions(
            symbol=broker_symbol,
            direction=requested_direction,
            ticket=ticket,
        )
        if not positions:
            return {"ok": False, "reason": f"no matching open position for {broker_symbol}"}
        if len(positions) > 1:
            return {"ok": False, "reason": "multiple matching positions; provide ticket"}

        position = _to_dict(positions[0])
        position_direction = self._position_direction(position)
        current_price = float(position.get("price_current") or position.get("price_open") or 0)
        if position_direction == "BUY" and not (stop_loss < current_price < take_profit):
            return {"ok": False, "reason": "BUY requires stop_loss < current_price < take_profit"}
        if position_direction == "SELL" and not (take_profit < current_price < stop_loss):
            return {"ok": False, "reason": "SELL requires take_profit < current_price < stop_loss"}

        request = {
            "action": getattr(self._mt5, "TRADE_ACTION_SLTP", 6),
            "position": int(position.get("ticket")),
            "symbol": broker_symbol,
            "sl": float(stop_loss),
            "tp": float(take_profit),
            "magic": self.config.magic,
            "comment": "NexusAI demo SLTP",
        }
        sent = _to_dict(self._mt5.order_send(request))
        send_retcode = sent.get("retcode")
        return {
            "ok": send_retcode in SUCCESSFUL_SEND_RETCODES,
            "symbol": broker_symbol,
            "ticket": position.get("ticket"),
            "direction": position_direction,
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "retcode": send_retcode,
            "comment": sent.get("comment"),
            "request": _sanitize_request(request),
        }

    def _matching_positions(
        self,
        *,
        symbol: str,
        direction: Optional[str] = None,
        ticket: Optional[int] = None,
    ) -> List[Any]:
        raw_positions = self._mt5.positions_get() or ()
        matches = []
        for position in raw_positions:
            data = _to_dict(position)
            if str(data.get("symbol", "")).casefold() != symbol.casefold():
                continue
            if ticket is not None and int(data.get("ticket") or 0) != int(ticket):
                continue
            if direction and self._position_direction(data) != direction:
                continue
            matches.append(position)
        return matches

    def _position_direction(self, position_data: Dict[str, Any]) -> str:
        buy_type = getattr(self._mt5, "POSITION_TYPE_BUY", 0)
        return "BUY" if position_data.get("type") == buy_type else "SELL"

    def _close_position(self, position: Any) -> Dict[str, Any]:
        data = _to_dict(position)
        symbol = data.get("symbol")
        volume = float(data.get("volume") or 0)
        ticket = data.get("ticket")
        position_type = data.get("type")
        if not symbol or volume <= 0 or ticket is None:
            return {"ok": False, "reason": "invalid broker position", "position": data}

        buy_type = getattr(self._mt5, "POSITION_TYPE_BUY", 0)
        direction = "SELL" if position_type == buy_type else "BUY"
        tick = _to_dict(self._mt5.symbol_info_tick(symbol))
        raw_price = tick.get("bid") if direction == "SELL" else tick.get("ask")
        price = float(raw_price or 0)
        if price <= 0:
            return {"ok": False, "reason": f"invalid close price for {symbol}"}

        request = self._build_deal_request(
            symbol=symbol,
            direction=direction,
            volume=volume,
            price=price,
            stop_loss=None,
            take_profit=None,
            position=ticket,
        )
        sent = _to_dict(self._mt5.order_send(request))
        send_retcode = sent.get("retcode")
        return {
            "ok": send_retcode in SUCCESSFUL_SEND_RETCODES,
            "symbol": symbol,
            "ticket": ticket,
            "volume_lots": volume,
            "price": float(sent.get("price") or price),
            "pnl": float(data.get("profit") or 0),
            "retcode": send_retcode,
            "comment": sent.get("comment"),
            "request": _sanitize_request(request),
        }

    def _build_deal_request(
        self,
        *,
        symbol: str,
        direction: str,
        volume: float,
        price: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        position: Optional[int] = None,
    ) -> Dict[str, Any]:
        request = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": self._mt5.ORDER_TYPE_BUY if direction == "BUY" else self._mt5.ORDER_TYPE_SELL,
            "price": price,
            "deviation": self.config.deviation_points,
            "magic": self.config.magic,
            "comment": "NexusAI demo agent",
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._mt5.ORDER_FILLING_IOC,
        }
        if position is not None:
            request["position"] = position
        if stop_loss and stop_loss > 0:
            request["sl"] = float(stop_loss)
        if take_profit and take_profit > 0:
            request["tp"] = float(take_profit)
        return request

    def _volume_for_order(self, order: Any, symbol_info: Dict[str, Any]) -> Dict[str, Any]:
        contract_size = float(symbol_info.get("trade_contract_size") or 1.0)
        min_volume = float(symbol_info.get("volume_min") or 0.01)
        max_volume = min(float(symbol_info.get("volume_max") or self.config.max_order_volume), self.config.max_order_volume)
        volume_step = float(symbol_info.get("volume_step") or 0.01)
        requested_volume = max(float(order.quantity or 0) / contract_size, 0.0)

        if requested_volume <= 0:
            return {"ok": False, "reason": "calculated MT5 volume is zero"}
        if requested_volume < min_volume:
            if not self.config.allow_min_volume_round_up:
                return {
                    "ok": False,
                    "reason": (
                        f"calculated volume {requested_volume:.6f} lots is below broker minimum "
                        f"{min_volume:.6f}; set EXNESS_ALLOW_MIN_VOLUME_ROUND_UP=true for demo-only testing"
                    ),
                }
            requested_volume = min_volume

        capped = min(requested_volume, max_volume)
        steps = math.floor((capped + 1e-12) / volume_step)
        volume = round(max(steps * volume_step, min_volume), 8)
        if volume > max_volume + 1e-12:
            return {"ok": False, "reason": f"calculated volume {volume:.6f} exceeds max {max_volume:.6f}"}
        return {"ok": True, "volume": volume}

    def _calculate_margin(self, direction: str, symbol: str, volume: float, price: float) -> Optional[float]:
        order_type = self._mt5.ORDER_TYPE_BUY if direction == "BUY" else self._mt5.ORDER_TYPE_SELL
        margin = self._mt5.order_calc_margin(order_type, symbol, volume, price)
        return round(float(margin), 2) if margin is not None else None

    def _actual_risk_usd(
        self,
        direction: str,
        price: float,
        stop_loss: Optional[float],
        fill_quantity: float,
    ) -> Optional[float]:
        if not stop_loss or stop_loss <= 0:
            return None
        if direction == "BUY" and stop_loss >= price:
            return None
        if direction == "SELL" and stop_loss <= price:
            return None
        return abs(price - float(stop_loss)) * fill_quantity


def _sanitize_request(request: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in request.items() if key not in {"password"}}


ExnessMT5ReadOnlyBroker = ExnessMT5DemoBroker
