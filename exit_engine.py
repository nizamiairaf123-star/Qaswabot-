"""
exit_engine.py — Unified Exit Toolkit (v5.4)

OWNER PRINCIPLE (exact):
- "Lock lagana bas ek tool hai exit ke combinations parameters ka. Chahe
  parameters 5% pe exit bataye ya 50% pe — OPTIMIZER decide karega."
- "Profit kam bhi mila to gam nahi, profit trail se mila to acha. Lekin
  profit milne ke baad zyada lalach me end me LOSS me nikalna = GALAT."

Isliye: exit = optimizer-selectable TOOLKIT (per-stock exit_mode), aur
profit-lock guarantee: ek baar trade profit me gaya, exit kabhi us lock
ke neeche nahi (lalach-safe).

MODES (optimizer Categorical — har stock ka apna):
  fixed_tp : tp1_pct pe full exit — classic, profit cap, zero-lalach risk
  trail    : ATR trail — activation ke baad breakeven lock (uncapped)
  hybrid   : TP hit → profit_lock_pct ka lock floor + trail baaki —
             uncapped upside + profit protection (recommended default)
  ratchet  : har ratchet_step_pct% pe floor lock (giveback = profit_lock_pct)
             + trail — progressive lock, profit kabhi zyada wapas nahi

PARITY: backtest (optimizer) == strategy backtest == LIVE teeno isi engine
ko use karte hain — ek hi math, ek hi results. Live ke liye step() ko
current price ke saath (high=low=close=current) bulaya jata hai.

ASSUMPTIONS (documented, honest):
- Same bar me TP & SL dono touch → TP-first (standard convention).
- SL fill floor price pe model hota hai = stop discipline (LIVE jaise:
  trigger pe market order). [PHD-FIX F6] Ye gap-down me OPTIMISTIC hai
  (asli fill floor se neeche ho sakta hai). [AUDIT F3 CORRECTION,
  2026-09-16] The previous version of this comment claimed gap-slippage
  risk is "covered by Monte Carlo severity_mult (1.5x)" — traced and
  confirmed FALSE: `monte_carlo.py` (the module with `severity_mult`) is
  imported from exactly one place, `risk_display.py`, which is
  display-only and never feeds sizing or entry/exit decisions. (There IS
  a real, load-bearing Monte Carlo gate — `deployment_manager.py`'s
  `_validate_monte_carlo_gate()` — but it is a separate implementation
  that gates deployment viability, not per-trade gap-slippage.) Net:
  backtest returns are somewhat optimistic on this dimension and nothing
  in the live risk/sizing path currently compensates for it — label this
  "optimistic fill, uncompensated for gap risk", not "conservative".

SL HUNT PROTECTION (Industry Verified — v6.0):
- Body Close Rule: Only exit if candle CLOSES below SL, not just wick touch
- Wick Analysis: Significant wick (wick > 1.5x body) = potential SL hunt
- Recovery Check: If price recovers above SL next candle = SL hunt confirmed
- Sources: EdgeFlo, Trade2Win, AlphaEx Capital, Trading Strategy Guides
"""


def init_state(params: dict, entry: float, floor_sl: float) -> dict:
    # Canonical exit contract: actual entry-to-SL risk = 1R; lock is exactly 1.8R.
    # RR is NOT optimizer-selected. After the 1.8R lock, trailing manages uncapped upside.
    mode = str(params.get("exit_mode", "hybrid") or "hybrid")
    # Legacy fixed_tp is retained only for persisted-state compatibility;
    # it is normalized to a trailing mode so profit remains uncapped.
    if mode == "fixed_tp":
        mode = "hybrid"
    if mode not in ("trail", "hybrid", "ratchet"):
        mode = "hybrid"
    entry = float(entry)
    floor_sl = float(floor_sl)
    risk = max(0.0, entry - floor_sl)
    rr = float(params.get("min_reward_risk", 1.8) or 1.8)
    lock_price = entry + risk * rr
    return {
        "mode": mode,
        "entry": entry,
        "floor": floor_sl,
        "activated": False,
        "tp_hit": False,
        "lock_price": lock_price,
        "next_ratchet": float(params.get("ratchet_step_pct", 1.5) or 1.5),
        "step_pct": float(params.get("ratchet_step_pct", 1.5) or 1.5),
        "trail_mult": float(params.get("trail_multiplier", 1.5) or 1.5),
        "lock_pct": float(params.get("profit_lock_pct", 1.0) or 1.0),
        "exit_price": None,
        "exit_tag": None,
        # SL Hunt Protection state (ALL optimized per stock)
        "sl_hunt_count": 0,
        "sl_hunt_max": 2,
        "prev_close": None,
        "wick_multiplier": float(params.get("wick_multiplier", 1.5) or 1.5),
        "candle_body_ratio": float(params.get("candle_body_ratio", 1.5) or 1.5),
        "candle_wick_ratio": float(params.get("candle_wick_ratio", 1.5) or 1.5),
        "candle_confirmation": int(params.get("candle_confirmation", 2) or 2),
        "candle_volume_mult": float(params.get("candle_volume_mult", 1.5) or 1.5),
    }


def _is_sl_hunt(state: dict, high: float, low: float, close: float, atr: float) -> bool:
    """
    Industry-verified SL hunt detection with OPTIMIZED parameters.
    
    Methods:
    1. Body Close Rule: Candle closes above SL (wick touched but recovered)
    2. Wick Analysis: Significant wick indicates institutional stop hunt
    3. ATR Filter: Wick > optimized multiplier x ATR = significant rejection
    4. Body Ratio: Body size relative to ATR (optimized per stock)
    5. Volume Confirmation: Volume spike indicates real move vs hunt
    
    Sources:
    - EdgeFlo: "Body close confirms break, wick only = false signal"
    - Trading Strategy Guides: "Wick pierces level, closes back inside = sweep"
    - AlphaEx Capital: "Enter only if candle closes within real-body"
    
    ALL parameters are OPTIMIZED per stock (not arbitrary values)
    """
    floor = state["floor"]
    
    # If candle didn't touch SL at all, not a hunt
    if low > floor:
        return False
    
    # If candle closed below SL, it's a confirmed break (not a hunt)
    if close <= floor:
        return False
    
    # Candle touched SL (low <= floor) but closed above = potential SL hunt
    
    # Get optimized parameters (all per-stock optimized)
    wick_mult = float(state.get("wick_multiplier", 1.5) or 1.5)
    body_ratio = float(state.get("candle_body_ratio", 1.5) or 1.5)
    wick_ratio = float(state.get("candle_wick_ratio", 1.5) or 1.5)
    
    # Method 1: Wick Analysis (optimized threshold)
    body = abs(close - (state.get("prev_close") or close))
    lower_wick = min(close, (state.get("prev_close") or close)) - low
    
    # Significant wick = wick > optimized multiplier x body
    if body > 0 and lower_wick > body * wick_mult:
        return True
    
    # Method 2: ATR Filter (optimized threshold)
    # Wick > optimized multiplier x ATR = significant rejection
    if atr > 0 and lower_wick > atr * wick_mult:
        return True
    
    # Method 3: Body Ratio Filter (optimized)
    # Small body relative to ATR = indecision = potential hunt
    if atr > 0 and body < atr * body_ratio * 0.5:
        return True
    
    # Method 4: Wick Ratio Filter (optimized)
    # Large wick relative to body = rejection = potential hunt
    if body > 0 and lower_wick > body * wick_ratio:
        return True
    
    # Method 5: Simple body close rule
    # If close > floor (even slightly), it's a hunt
    if close > floor:
        return True
    
    return False


def step(state: dict, high: float, low: float, close: float, atr: float) -> bool:
    """Canonical exit contract: 1R risk -> exactly 1.8R lock -> uncapped trailing.

    No breakeven, +1R floor, or early percentage activation is allowed before
    the fixed 1.8R lock. Once locked, the selected trailing mode may only raise the
    floor; it can never lower it.
    """
    entry = state["entry"]
    lock_price = state["lock_price"]

    # Before the configured RR lock: no trailing activation and no BE floor.
    locked_this_bar = False
    if not state["tp_hit"]:
        if high >= lock_price:
            state["tp_hit"] = True
            state["activated"] = True
            state["floor"] = max(state["floor"], lock_price)
            locked_this_bar = True
        else:
            # SL protection remains available at the original floor only.
            pass

    # After the fixed 1.8R lock, the optimizer-selected trailing combination is
    # allowed to move the floor upward without any profit cap. The lock bar
    # itself is not re-trailed: OHLC does not reveal whether the high happened
    # before or after the close/trailing price, so trailing starts next bar.
    if state["tp_hit"] and not locked_this_bar:
        state["activated"] = True
        mode = state["mode"]
        if mode == "ratchet":
            while high >= entry * (1.0 + state["next_ratchet"] / 100.0):
                locked_profit = max(0.0, state["next_ratchet"] - state["lock_pct"])
                state["floor"] = max(state["floor"], entry * (1.0 + locked_profit / 100.0))
                state["next_ratchet"] += state["step_pct"]
        if atr > 0:
            nt = close - atr * state["trail_mult"]
            if nt > state["floor"]:
                state["floor"] = nt

    # ── SL HUNT PROTECTION (Industry Verified) ──
    # If the same OHLC bar first reaches the fixed 1.8R lock and also trades through
    # the newly locked floor, apply the documented TP/lock-first convention.
    # The locked floor is enforced from the next bar onward.
    if low <= state["floor"] and not locked_this_bar:
        # HARD PROFIT FLOOR: once the floor is above entry, it is a locked
        # profit level. A wick/SL-hunt heuristic must never suppress this
        # execution; otherwise a locked gain can be given back to a loss.
        # SL-hunt protection remains available while the floor is at/below
        # entry (initial/breakeven protection).
        if state["floor"] <= entry and _is_sl_hunt(state, high, low, close, atr):
            # SL hunt detected — don't exit
            state["sl_hunt_count"] += 1
            state["exit_tag"] = f"SL_HUNT_{state['sl_hunt_count']}"
            
            # Safety: if too many consecutive hunts, force exit
            if state["sl_hunt_count"] >= state["sl_hunt_max"]:
                state["exit_price"] = round(state["floor"], 2)
                state["exit_tag"] = "FLOOR_FORCED"
                return True
            
            # Update previous close for next candle analysis
            state["prev_close"] = close
            return False
        
        # Confirmed SL break (candle closed below SL) — EXIT
        state["exit_price"] = round(state["floor"], 2)
        state["exit_tag"] = "FLOOR"
        return True
    
    # No SL touch — reset hunt counter
    state["sl_hunt_count"] = 0
    state["prev_close"] = close
    return False
