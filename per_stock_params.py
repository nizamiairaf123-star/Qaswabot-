"""
per_stock_params.py — Per-stock optimized parameters storage
Optimizer results yahan save hote hain — har stock ke alag params
"""

from utils import load_json, save_json, now_ist
from config import PARAMS

PER_STOCK_PARAMS_FILE = "data/per_stock_params.json"


def get_param(symbol: str, param_name: str, default=None):
    """
    Get optimized param for a specific stock.
    Falls back to global PARAMS if not found.
    """
    # OWNER CONTRACT: RR lock is immutable at exactly 1.8R.
    # Stored/legacy per-stock values must never override it.
    if param_name == "min_reward_risk":
        return 1.8
    data = load_json(PER_STOCK_PARAMS_FILE, {})
    stock_params = data.get(symbol, {})
    if param_name in stock_params:
        return stock_params[param_name]
    if default is not None:
        return default
    return PARAMS.get(param_name)


def get_all_params(symbol: str) -> dict:
    """Get all optimized params for a stock."""
    data = load_json(PER_STOCK_PARAMS_FILE, {})
    global_params = PARAMS.copy()
    stock_params = data.get(symbol, {})
    global_params.update(stock_params)
    # OWNER CONTRACT: exact 1.8R regardless of legacy/global/stored overrides.
    global_params["min_reward_risk"] = 1.8
    return global_params


def save_stock_params(symbol: str, params: dict):
    """Save optimizer results for a stock."""
    data = load_json(PER_STOCK_PARAMS_FILE, {})
    stored = dict(params)
    stored["updated_at"] = now_ist().isoformat()
    data[symbol] = stored
    save_json(PER_STOCK_PARAMS_FILE, data)


def save_bulk_params(all_params: dict):
    """Save optimizer results for all stocks at once."""
    data = load_json(PER_STOCK_PARAMS_FILE, {})
    for symbol, params in all_params.items():
        stored = dict(params)
        stored["updated_at"] = now_ist().isoformat()
        data[symbol] = stored
    save_json(PER_STOCK_PARAMS_FILE, data)


def get_params_summary() -> str:
    """Admin: summary of optimized stocks."""
    data = load_json(PER_STOCK_PARAMS_FILE, {})
    if not data:
        return "No per-stock params yet. Run /optimize first."
    lines = [f"Per-Stock Params ({len(data)} stocks optimized):"]
    for sym, params in list(data.items())[:20]:
        sl  = params.get("sl_pct", "?")
        tp  = params.get("tp1_pct", "?")
        tf  = params.get("timeframe", "?")
        lines.append(f"{sym}: SL={sl}% TP={tp}% TF={tf}")
    return "\n".join(lines)


def reset_stock_params(symbol: str):
    """Remove per-stock params — will use global defaults."""
    data = load_json(PER_STOCK_PARAMS_FILE, {})
    data.pop(symbol, None)
    save_json(PER_STOCK_PARAMS_FILE, data)


def reset_all_params():
    """Clear all per-stock params."""
    save_json(PER_STOCK_PARAMS_FILE, {})
