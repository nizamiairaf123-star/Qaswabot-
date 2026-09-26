# QASWA Canonical Data-Source Policy

**Owner-approved requirement:**

- **Dhan is mandatory and the single source of truth for all trading data and execution:** instrument/security mapping used for orders, historical and live OHLCV, volume, indicators, signals, backtest, optimization, simulation, paper trading, live trading, orders, fills, positions and reconciliation.
- **yfinance is information-only:** company sector, industry, market capitalization, business description/inputs used by the Halal filter, and board/director information. It must never supply OHLCV, price or volume to any trading/strategy/backtest/optimization/paper/live path.
- **(2026-09-13 cross-reference, no change to the contract above):** `prd.md` Rule 15 / NDSAP (NIZAMI Data Segregation & Accumulation Protocol, owner AIRAF NIZAMI, REGISTERED NOT YET IMPLEMENTED) reaffirms this policy for OHLCV/price/volume exactly as written here, and — once implemented — would broaden the *information-only* sourcing above (currently yfinance-only) to also allow NSE and Moneycontrol as alternates for the same information-only field set, Dhan-first per field. This does not touch the OHLCV/price/volume line above in any way.
- If Dhan trading data is missing, stale or invalid, the affected calculation/trade is blocked; yfinance market data must not silently substitute it.
- Liquidity ATVR/FoT is calculated by QASWA from Dhan historical price/volume, using company market-cap information from the approved information source.
- Information that is missing or ambiguous remains UNKNOWN/BLOCKED; it is not fabricated.

Enforcement regression: `test_data_source_policy.py`.
