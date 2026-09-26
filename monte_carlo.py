"""
monte_carlo.py — Gap-down day-loss estimate (Phase-2 PATCH P3.4, ADD-ONLY).

[Method: Monte Carlo simulation — Stanislaw Ulam & John von Neumann / Nicholas
         Metropolis, Los Alamos 1946; finance risk bootstrap standard]

Sawaal jiska jawab yeh deta hai:
"Agar sabhi open positions ek hi din SL pe band ho jayein (correlated gap-down,
jaise 2020/2024 ke din), to us DIN ka worst-among-99% kitna nuksaan ho sakta hai?"

Input: observed trade net returns (%) — backtest/paper/live jo available ho.
Output: dict with pct99 day-loss ₹ (risk_display isko backtest value ke saath
conservative MAX lekar dikhata hai — design doc open-item #3 resolution).

NOTE: yeh DISPLAY-ONLY estimate hai; existing risk engine (risk_manager/
capital_drawdown_manager) ka calculation isse NAHI badalta. Sirf bataya jata hai.
"""

from __future__ import annotations

import numpy as np

from config import PARAMS

mc_version = "1.1"


def estimate_max_day_loss(net_returns_pct: list, position_size_amt: float,
                          open_slots: int, n_sims: int = None,
                          severity_mult: float = 1.5, seed: int = 42) -> dict:
    """
    Bootstrap simulation:
    - Har simulated "worst day" me open_slots jitne positions ek saath gap-down se
      band hote hain. Har position ka loss = random OBSERVED losing-trade return ×
      severity_mult (gap-down SL se zyada slide karta hai — severity 1.5x conservative).
    - 99th percentile total loss = "99% cases me isse bura din nahi aayega".

    severity_mult: overnight gap me SL price se aage slip hota hai; 1.5x = SL ke
    डेढ़ guna tak slippage assume (conservative, documented assumption — koi
    verified creator nahi, custom conservative constant).
    """
    losses = [-abs(float(r)) for r in (net_returns_pct or []) if float(r) < 0]
    if not losses or position_size_amt <= 0 or open_slots <= 0:
        return {"error": "insufficient data (need >=1 losing trade or open slot)",
                "pct99_loss_amt": None}
    rng = np.random.default_rng(seed)
    losses = np.array(losses)
    _n = int(n_sims or PARAMS.get("monte_carlo_n_sims", 10000))  # v5.7 config-driven
    draws = rng.choice(losses, size=(_n, int(open_slots)), replace=True)
    day_losses_pct = draws.sum(axis=1) * severity_mult
    p99_pct = float(np.percentile(day_losses_pct, 1))  # worst 1% day
    p95_pct = float(np.percentile(day_losses_pct, float(PARAMS.get("monte_carlo_percentile", 5.0))))
    return {
        "pct99_loss_pct": round(p99_pct, 2),
        "pct95_loss_pct": round(p95_pct, 2),
        # loss NEGATIVE number: pct × position_size (₹). Display layer abs() use kare.
        "pct99_loss_amt": round(p99_pct / 100.0 * position_size_amt, 2),
        "position_size_amt": round(position_size_amt, 2),
        "open_slots": int(open_slots),
        "n_sims": n_sims,
        "severity_mult": severity_mult,
        "method": "Monte Carlo bootstrap — Metropolis & Ulam, 1946 (severity 1.5x custom-conservative)",
    }
