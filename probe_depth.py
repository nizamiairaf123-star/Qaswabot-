"""
mtf/probe_depth.py — Dhan intraday depth PROBE (VPS pe fresh token ke saath chalana).

Kyun: design doc ka open item #1 — Dhan intraday kitne purana data deta hai,
docs me claim hai "up to 5 years" par VERIFY nahi hua. Ye script RELIANCE pe
3 intervals (5/15/60 min) ka earliest/latest candle bata degi.

Chalana (VPS pe):
    cd trading-bot && ./.venv/bin/python3 -m mtf.probe_depth

[Custom engineering] — sirf READ karta hai, kuch save/order nahi karta. Safe.
"""

from dhan_data import fetch_intraday_data

PROBE_SYMBOL = "RELIANCE"


def main():
    print(f"Probing Dhan intraday depth for {PROBE_SYMBOL} ...")
    print("(Rate-limit friendly: 3 calls, ~5 sec)")
    for interval, days in [("60", 1825), ("15", 1825), ("5", 365)]:
        try:
            df = fetch_intraday_data(PROBE_SYMBOL, interval=interval, days=days)
            if df is None or df.empty:
                print(f"  {interval:>3}min: NO DATA")
                continue
            print(f"  {interval:>3}min: rows={len(df):,}  earliest={df.index.min()}  latest={df.index.max()}")
        except Exception as e:
            print(f"  {interval:>3}min: ERROR {type(e).__name__}: {e}")
    print("\nRule (design doc 1.1): jo depth mile, warehouse usi tak bharega —")
    print("jo TF deep hai (expected 60m ~5y), derived 2H bhi utna deep. Short ho to honestly report hoga.")


if __name__ == "__main__":
    main()
