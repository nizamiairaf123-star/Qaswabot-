# QASWA Cross-Environment Alignment

## Objective

Backtest, Paper and Live should execute the same strategy decision contract and produce materially similar behavior/results after allowing for real execution effects such as spread, slippage, latency and partial fills.

## Architecture

- **Backtest:** historical replay of the same strategy/exit logic.
- **Paper:** runtime path with `PAPER` state and no real orders.
- **Live:** runtime path with `LIVE_STAGED`/`LIVE_FULL` and real broker execution.
- **Alignment monitor:** `alignment_engine.py` compares Backtest↔Paper, Backtest↔Live and Paper↔Live using observed closed-trade metrics.
- Runtime trade records now carry `execution_environment` (`PAPER`, `LIVE`, or `UNKNOWN`) so future samples cannot be silently mixed.

## What is compared

- trade count / sample sufficiency
- win-rate gap
- profit-factor gap
- average return gap

The existing owner-approved `max_wr_gap_vs_backtest` is used for the configured WR-drift check. Other gaps are reported as evidence rather than assigned invented hard thresholds.

## Gate semantics

Alignment is a **robustness and model-drift objective, not a blanket AND gate**. A missing Paper/Live sample is reported as `INSUFFICIENT_DATA`; it is not falsely marked as aligned. Mandatory Sharia/compliance, tradeability, broker-safety, capital and risk gates remain hard gates.

A production decision must therefore distinguish:

1. **Engineering parity:** same code path/contracts are wired.
2. **Observed alignment:** enough Paper/Live evidence exists and measured drift is acceptable.
3. **External execution evidence:** broker/VPS/market behavior has been independently verified.

No green Paper/Live alignment claim is permitted before the relevant real samples exist.
