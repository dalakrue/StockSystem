"""Small, dependency-light contracts for the reliable Field 10 authority.

The legacy project contains many research modules.  This module is the narrow
boundary those modules must cross before their values can be published.  It is
deliberately conservative:

* timestamps and timeframe aliases have one canonical representation;
* missing or unsettled evidence is never converted into a probability;
* event uncertainty is a risk state, not a neutral score;
* ranking is deterministic and cost-aware;
* model promotion is blocked until registered out-of-sample evidence exists;
* an open trade keeps the identity of the snapshot that opened it.

It does not fetch market data, fit a model, or place a trade.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import re
from typing import Any, Iterable, Mapping, Sequence


TIMEFRAME_MINUTES: dict[str, int] = {
    "M1": 1,
    "M5": 5,
    "M10": 10,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H2": 120,
    "H3": 180,
    "H4": 240,
    "H6": 360,
    "H8": 480,
    "H12": 720,
    "D1": 1440,
}

TIMEFRAME_ALIASES = {
    "1H": "H1",
    "2H": "H2",
    "3H": "H3",
    "4H": "H4",
    "6H": "H6",
    "8H": "H8",
    "12H": "H12",
    "1D": "D1",
    "DAY": "D1",
    "DAILY": "D1",
}

UNAVAILABLE = {"", "N/A", "NA", "NAN", "NONE", "NULL", "UNAVAILABLE", "NOT AVAILABLE", "<NA>"}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted(_jsonable(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def stable_contract_hash(value: Any) -> str:
    raw = json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()[:24]


def normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "").replace("_", "").replace(" ", "")


def normalize_timeframe(value: Any, default: str = "H4") -> str:
    text = str(value or default).strip().upper().replace(" ", "")
    text = TIMEFRAME_ALIASES.get(text, text)
    if text in TIMEFRAME_MINUTES:
        return text
    match = re.fullmatch(r"(\d+)(MIN|M|H|D)", text)
    if match:
        number, unit = int(match.group(1)), match.group(2)
        candidate = f"{number}{'M' if unit in {'MIN', 'M'} else 'H' if unit == 'H' else 'D'}"
        if unit == "D":
            candidate = f"D{number}"
        elif unit == "H":
            candidate = f"H{number}"
        if candidate == "D1":
            return candidate
        if candidate in TIMEFRAME_MINUTES:
            return candidate
    return normalize_timeframe(default, default="H4") if text != default else "H4"


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text or text.upper() in UNAVAILABLE:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        # Naive provider timestamps are accepted only under the explicit UTC
        # compatibility policy.  The returned value is never local machine time.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def canonical_utc_iso(value: Any) -> str:
    parsed = _parse_datetime(value)
    return "UNAVAILABLE" if parsed is None else parsed.isoformat()


def canonical_completed_candle(value: Any, timeframe: Any, *, broker_anchor_utc_hour: int = 0) -> str:
    """Return one UTC close-boundary identity for a completed candle.

    The broker anchor is explicit.  The default UTC anchor is safe for the
    existing project; deployments with a broker-day boundary must pass that
    policy into the authority identity rather than rely on local wall-clock
    time.
    """
    parsed = _parse_datetime(value)
    if parsed is None:
        return "UNAVAILABLE"
    tf = normalize_timeframe(timeframe)
    minutes = TIMEFRAME_MINUTES[tf]
    anchor = parsed.replace(hour=broker_anchor_utc_hour, minute=0, second=0, microsecond=0)
    elapsed = int((parsed - anchor).total_seconds() // 60)
    bucket = max(0, elapsed // minutes)
    floored = anchor + timedelta(minutes=bucket * minutes)
    return floored.isoformat()


def ordered_symbols(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    for value in values:
        symbol = normalize_symbol(value)
        if symbol and symbol not in output:
            output.append(symbol)
    return output


@dataclass(frozen=True)
class AuthorityIdentity:
    canonical_symbol: str
    provider_symbol: str
    selected_timeframe: str
    broker_timezone_policy: str
    completed_candle_close_utc: str
    ordered_selected_symbols: tuple[str, ...]
    universe_set_hash: str
    provider: str
    source_id: str
    source_snapshot_hash: str
    data_revision: str
    feature_schema_hash: str
    model_version: str
    formula_version: str
    authority_key: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_authority_identity(
    *,
    canonical_symbol: Any,
    provider_symbol: Any,
    selected_timeframe: Any,
    broker_timezone_policy: str,
    completed_candle_close_utc: Any,
    ordered_selected_symbols: Sequence[Any],
    provider: Any,
    source_id: Any,
    source_snapshot_hash: Any,
    data_revision: Any,
    feature_schema_hash: Any,
    model_version: Any,
    formula_version: Any,
) -> AuthorityIdentity:
    symbols = tuple(ordered_symbols(ordered_selected_symbols))
    tf = normalize_timeframe(selected_timeframe)
    canonical_fields = {
        "canonical_symbol": normalize_symbol(canonical_symbol),
        "provider_symbol": str(provider_symbol or "").strip(),
        "selected_timeframe": tf,
        "broker_timezone_policy": str(broker_timezone_policy or "UNAVAILABLE").strip(),
        "completed_candle_close_utc": canonical_completed_candle(completed_candle_close_utc, tf),
        "ordered_selected_symbols": symbols,
        "universe_set_hash": stable_contract_hash(sorted(set(symbols))),
        "provider": str(provider or "UNAVAILABLE").strip(),
        "source_id": str(source_id or "UNAVAILABLE").strip(),
        "source_snapshot_hash": str(source_snapshot_hash or "UNAVAILABLE").strip(),
        "data_revision": str(data_revision or "UNAVAILABLE").strip(),
        "feature_schema_hash": str(feature_schema_hash or "UNAVAILABLE").strip(),
        "model_version": str(model_version or "UNAVAILABLE").strip(),
        "formula_version": str(formula_version or "UNAVAILABLE").strip(),
    }
    return AuthorityIdentity(**canonical_fields, authority_key=stable_contract_hash(canonical_fields))


def is_available(value: Any) -> bool:
    return str(value or "").strip().upper() not in UNAVAILABLE


def validate_candle_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    symbol: Any,
    timeframe: Any,
    completed_candle_close_utc: Any,
) -> dict[str, Any]:
    """Validate point-in-time candle rows without padding missing observations."""
    expected_symbol = normalize_symbol(symbol)
    tf = normalize_timeframe(timeframe)
    watermark = _parse_datetime(completed_candle_close_utc)
    errors: list[str] = []
    timestamps: list[datetime] = []
    accepted = 0
    for index, raw in enumerate(rows):
        row = dict(raw)
        row_symbol = normalize_symbol(row.get("symbol") or row.get("Symbol"))
        if row_symbol and row_symbol != expected_symbol:
            errors.append(f"row {index}: symbol mismatch")
        stamp = _parse_datetime(row.get("bar_close_utc") or row.get("close_time") or row.get("time") or row.get("Time"))
        if stamp is None:
            errors.append(f"row {index}: missing timestamp")
            continue
        timestamps.append(stamp)
        if watermark is not None and stamp > watermark:
            errors.append(f"row {index}: future candle beyond completed watermark")
        if row.get("is_complete") is False or str(row.get("is_complete", "")).upper() in {"0", "FALSE", "INCOMPLETE"}:
            errors.append(f"row {index}: incomplete candle")
        numeric: dict[str, float] = {}
        for name in ("open", "high", "low", "close"):
            value = row.get(name, row.get(name.title()))
            try:
                numeric[name] = float(value)
            except (TypeError, ValueError):
                errors.append(f"row {index}: invalid {name}")
        if len(numeric) == 4:
            if numeric["high"] < max(numeric["open"], numeric["close"]) or numeric["low"] > min(numeric["open"], numeric["close"]):
                errors.append(f"row {index}: invalid OHLC bounds")
            if numeric["low"] > numeric["high"]:
                errors.append(f"row {index}: low above high")
        accepted += 1
    if len(timestamps) != len(set(timestamps)):
        errors.append("duplicate candle timestamps")
    return {
        "ok": not errors and bool(rows),
        "symbol": expected_symbol,
        "timeframe": tf,
        "completed_candle_close_utc": canonical_utc_iso(completed_candle_close_utc),
        "accepted_rows": accepted if not errors else 0,
        "errors": errors,
        "padding_used": False,
    }


def target_outcome_from_future_rows(
    *,
    entry_price: Any,
    direction: str,
    target_distance: Any,
    future_rows: Sequence[Mapping[str, Any]],
    entry_candle_close_utc: Any,
) -> dict[str, Any]:
    """Create a settled target/MFE/MAE label from future completed candles."""
    entry = _parse_datetime(entry_candle_close_utc)
    try:
        price = float(entry_price)
        distance = abs(float(target_distance))
    except (TypeError, ValueError):
        return {"settled": False, "settlement_status": "INVALID_ENTRY_CONTRACT"}
    if entry is None or price <= 0 or distance <= 0:
        return {"settled": False, "settlement_status": "INVALID_ENTRY_CONTRACT"}
    side = str(direction or "").upper()
    if side not in {"BUY", "SELL"}:
        return {"settled": False, "settlement_status": "DIRECTION_UNAVAILABLE"}
    usable: list[Mapping[str, Any]] = []
    for raw in future_rows:
        stamp = _parse_datetime(raw.get("bar_close_utc") or raw.get("close_time") or raw.get("time") or raw.get("Time"))
        if stamp is None or stamp <= entry or raw.get("is_complete") is False:
            continue
        try:
            high = float(raw.get("high", raw.get("High")))
            low = float(raw.get("low", raw.get("Low")))
        except (TypeError, ValueError):
            continue
        usable.append({"stamp": stamp, "high": high, "low": low})
    if not usable:
        return {"settled": False, "settlement_status": "UNSETTLED_NO_FUTURE_COMPLETED_ROWS"}
    target = price + distance if side == "BUY" else price - distance
    adverse = price - distance if side == "BUY" else price + distance
    mfe = 0.0
    mae = 0.0
    target_hit_at: datetime | None = None
    adverse_hit_at: datetime | None = None
    for row in sorted(usable, key=lambda item: item["stamp"]):
        favorable = (row["high"] - price) if side == "BUY" else (price - row["low"])
        adverse_move = (price - row["low"]) if side == "BUY" else (row["high"] - price)
        mfe = max(mfe, favorable)
        mae = max(mae, adverse_move)
        if target_hit_at is None and ((row["high"] >= target) if side == "BUY" else (row["low"] <= target)):
            target_hit_at = row["stamp"]
        if adverse_hit_at is None and ((row["low"] <= adverse) if side == "BUY" else (row["high"] >= adverse)):
            adverse_hit_at = row["stamp"]
    ambiguous = target_hit_at is not None and adverse_hit_at is not None and target_hit_at == adverse_hit_at
    if ambiguous:
        status = "AMBIGUOUS_SAME_CANDLE_PATH"
        target_reached: bool | None = None
    else:
        status = "SETTLED_TARGET_REACHED" if target_hit_at is not None else "SETTLED_TARGET_NOT_REACHED"
        target_reached = target_hit_at is not None
    return {
        "settled": not ambiguous,
        "settlement_status": status,
        "target_reached": target_reached,
        "target_price": target,
        "adverse_barrier": adverse,
        "future_rows_used": len(usable),
        "future_MFE": mfe,
        "future_MAE": mae,
        "target_hit_at_utc": target_hit_at.isoformat() if target_hit_at else None,
        "adverse_hit_at_utc": adverse_hit_at.isoformat() if adverse_hit_at else None,
    }


def settled_target_probability(outcomes: Iterable[Mapping[str, Any]], *, minimum_sample: int = 100) -> dict[str, Any]:
    settled = [row for row in outcomes if bool(row.get("settled")) and isinstance(row.get("target_reached"), bool)]
    if len(settled) < int(minimum_sample):
        return {
            "probability_target_reached": None,
            "settled_sample_size": len(settled),
            "status": "INSUFFICIENT_SETTLED_OUTCOMES",
            "research_only": True,
        }
    probability = sum(bool(row["target_reached"]) for row in settled) / len(settled)
    return {
        "probability_target_reached": round(probability, 8),
        "settled_sample_size": len(settled),
        "status": "SETTLED_OUTCOME_ESTIMATE",
        "research_only": False,
    }


def event_risk_state(
    *,
    now_utc: Any,
    release_utc: Any,
    actual: Any = None,
    consensus: Any = None,
    pre_event_minutes: int = 60,
    post_event_minutes: int = 120,
) -> dict[str, Any]:
    now = _parse_datetime(now_utc)
    release = _parse_datetime(release_utc)
    if now is None or release is None:
        return {"state": "DATA_UNAVAILABLE", "permission": "BLOCK", "surprise_z": None, "reason": "event timing is unavailable"}
    delta_minutes = (now - release).total_seconds() / 60.0
    if delta_minutes < -abs(pre_event_minutes):
        state = "NORMAL"
    elif delta_minutes < 0:
        state = "PRE_EVENT"
    elif not is_available(actual):
        state = "RELEASED_UNCONFIRMED"
    elif delta_minutes <= abs(post_event_minutes):
        state = "POST_EVENT_SHOCK"
    else:
        state = "ABSORBING" if delta_minutes <= abs(post_event_minutes) * 3 else "NORMAL"
    surprise_z: float | None = None
    if is_available(actual) and is_available(consensus):
        try:
            # This is only the raw surprise ratio.  A robust historical scale
            # must be supplied by the event-response research layer.
            surprise_z = float(actual) - float(consensus)
        except (TypeError, ValueError):
            surprise_z = None
    permission = "ALLOW" if state == "NORMAL" and surprise_z is not None or state == "NORMAL" and not is_available(actual) else "BLOCK"
    if state in {"DATA_UNAVAILABLE", "PRE_EVENT", "RELEASED_UNCONFIRMED", "POST_EVENT_SHOCK"}:
        permission = "BLOCK"
    return {
        "state": state,
        "permission": permission,
        "surprise_z": surprise_z,
        "release_utc": release.isoformat(),
        "actual_available": is_available(actual),
        "consensus_available": is_available(consensus),
        "reason": "scheduled event gate; missing actual/consensus is not treated as safe" if permission == "BLOCK" else "no active high-impact event gate",
    }


def expected_net_value(
    *,
    probability_target_reached: Any,
    expected_mfe: Any,
    expected_mae: Any,
    spread_cost: Any = 0.0,
    slippage_cost: Any = 0.0,
    event_penalty: Any = 0.0,
    uncertainty_penalty: Any = 0.0,
    cvar_penalty: Any = 0.0,
    dependency_penalty: Any = 0.0,
    data_quality_penalty: Any = 0.0,
    stale_data_penalty: Any = 0.0,
    transition_penalty: Any = 0.0,
) -> float | None:
    values = (probability_target_reached, expected_mfe, expected_mae)
    try:
        probability, mfe, mae = (float(value) for value in values)
    except (TypeError, ValueError):
        return None
    if any(not math.isfinite(value) for value in (probability, mfe, mae)):
        return None
    probability = min(1.0, max(0.0, probability if probability <= 1 else probability / 100.0))
    penalties = (spread_cost, slippage_cost, event_penalty, uncertainty_penalty, cvar_penalty, dependency_penalty, data_quality_penalty, stale_data_penalty, transition_penalty)
    try:
        total_penalty = sum(float(value or 0.0) for value in penalties)
    except (TypeError, ValueError):
        return None
    return probability * mfe - (1.0 - probability) * mae - total_penalty


def deterministic_rank_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Rank only rows with a usable utility; blocked rows remain visible last."""
    prepared: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        utility = item.get("Expected Net Value")
        try:
            utility_value = float(utility)
            usable = math.isfinite(utility_value)
        except (TypeError, ValueError):
            utility_value, usable = float("-inf"), False
        permission = str(item.get("Trade Permission") or item.get("Entry Permission") or "CHECK").upper()
        hard_block = permission.startswith("BLOCK") or str(item.get("Data Quality") or "").upper() in {"FAILED", "UNKNOWN", "INSUFFICIENT_DATA"}
        item["_rank_utility"] = utility_value
        item["_rank_blocked"] = hard_block or not usable
        prepared.append(item)
    prepared.sort(key=lambda item: (item["_rank_blocked"], -item["_rank_utility"], str(item.get("Symbol") or "")))
    for rank, item in enumerate(prepared, start=1):
        item["Rank"] = rank
        item.pop("_rank_utility", None)
        item.pop("_rank_blocked", None)
    return prepared


def promotion_gate(
    *,
    settled_sample_size: int,
    out_of_sample: bool,
    calibrated: bool,
    no_lookahead: bool,
    multiple_testing_registered: bool,
    minimum_settled_sample: int = 100,
) -> dict[str, Any]:
    reasons: list[str] = []
    if int(settled_sample_size) < int(minimum_settled_sample):
        reasons.append("INSUFFICIENT_SETTLED_OUTCOMES")
    if not out_of_sample:
        reasons.append("NO_OUT_OF_SAMPLE_EVIDENCE")
    if not calibrated:
        reasons.append("PROBABILITY_NOT_CALIBRATED")
    if not no_lookahead:
        reasons.append("LOOKAHEAD_CONTROL_FAILED")
    if not multiple_testing_registered:
        reasons.append("TRIAL_NOT_REGISTERED")
    return {"promoted": not reasons, "status": "PROMOTED" if not reasons else "SHADOW_ONLY", "reasons": reasons}


@dataclass(frozen=True)
class TradeIdentity:
    trade_id: str
    symbol: str
    timeframe: str
    entry_time_utc: str
    entry_snapshot_hash: str
    provider: str
    entry_price: float
    stop_price: float | None
    target_price: float | None
    exit_reason: str | None = None
    status: str = "OPEN"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def freeze_trade_identity(
    *,
    trade_id: Any,
    symbol: Any,
    timeframe: Any,
    entry_time_utc: Any,
    entry_snapshot_hash: Any,
    provider: Any,
    entry_price: Any,
    stop_price: Any = None,
    target_price: Any = None,
) -> TradeIdentity:
    try:
        price = float(entry_price)
    except (TypeError, ValueError) as exc:
        raise ValueError("entry_price must be numeric") from exc
    stop = None if stop_price in (None, "") else float(stop_price)
    target = None if target_price in (None, "") else float(target_price)
    return TradeIdentity(
        trade_id=str(trade_id or stable_contract_hash([symbol, timeframe, entry_time_utc, entry_snapshot_hash])),
        symbol=normalize_symbol(symbol),
        timeframe=normalize_timeframe(timeframe),
        entry_time_utc=canonical_utc_iso(entry_time_utc),
        entry_snapshot_hash=str(entry_snapshot_hash or "UNAVAILABLE"),
        provider=str(provider or "UNAVAILABLE"),
        entry_price=price,
        stop_price=stop,
        target_price=target,
    )


def validate_trade_update(existing: Mapping[str, Any], requested: Mapping[str, Any]) -> dict[str, Any]:
    immutable = ("trade_id", "symbol", "timeframe", "entry_time_utc", "entry_snapshot_hash", "provider", "entry_price", "stop_price", "target_price")
    changed = [key for key in immutable if str(existing.get(key)) != str(requested.get(key))]
    return {"ok": not changed, "status": "UNCHANGED_IDENTITY" if not changed else "ENTRY_IDENTITY_MUTATION_REJECTED", "changed_fields": changed}


__all__ = [
    "AuthorityIdentity", "TradeIdentity", "TIMEFRAME_MINUTES", "build_authority_identity",
    "canonical_completed_candle", "canonical_utc_iso", "deterministic_rank_rows",
    "event_risk_state", "expected_net_value", "freeze_trade_identity", "normalize_symbol",
    "normalize_timeframe", "ordered_symbols", "promotion_gate", "settled_target_probability",
    "stable_contract_hash", "target_outcome_from_future_rows", "validate_candle_rows",
    "validate_trade_update",
]
