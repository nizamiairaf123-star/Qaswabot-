# NDSAP Retention & Compaction Policy — derived from measured volume estimates

**Required deliverable of Rule 15 implementation** (prd.md Rule 15: "an
explicit retention/compaction policy must be defined from an actual
per-field data-volume/growth estimate for this archive — not an arbitrary
duration"). Prepared 2026-09-13 for the Part C implementation
(`ndsap_archive.py`). Owner: AIRAF NIZAMI.

## Measurement basis (from this tree, not guessed)
- Universe: **1057 symbols** (`data/CUSTOM_UNIVERSE_FINAL.csv`, counted 2026-09-13)
- One Dhan daily-candle row ≈ **99 bytes** canonical JSON (measured:
  open/high/low/close/volume/timestamp)
- `fetch_daily_data(days=7300)` ≈ 20y × ~245 trading days ≈ **4,900 candles
  ≈ 474 KB per symbol-response**
- Daily cache (`enable_daily_cache`, `daily_cache_stale_days=1`) ⇒ at most
  **1 Dhan daily re-fetch per symbol per trading day**
- Scheduler cadence (scheduler.py): market scan 9–15h every 5 min (cache-hit,
  no Dhan call), position monitor every 3 min (open positions only, ≤ ~10),
  market-metadata refresh **monthly**
- Trading days ≈ 21/month, 252/year

## Per-dataset volume/growth estimate

| Dataset | Source | Per event | Cadence (worst case) | Growth WITHOUT compaction | Growth WITH policy below |
|---|---|---|---|---|---|
| `historical_daily` | Dhan | ~474 KB/symbol | 1057 symbols × 1/day | **~489 MB/day ≈ 10.3 GB/month ≈ 120 GB/yr** | steady ≈ **2.4 GB** (keep_last=5 full payloads/symbol) + ~0.25 MB/day metadata rows (~78 MB/yr, never expires) |
| `intraday_minute` | Dhan | ~3.2 MB per 90-day 1-min chunk (~64 MB per symbol for 5y) | on-demand (MTF/backtest) | usage-dependent, spiky | steady ≈ 5× last fetches per symbol; compacted like daily |
| `ohlc_live` | Dhan | ~1.5 KB | ≤ 120 runs/day × ≤10 positions | ~1.8 MB/day ≈ 37 MB/month ≈ **0.45 GB/yr** | retained IN FULL (incremental — every record is new information) |
| `market_depth` | Dhan | ~5–10 KB | on-demand (display) | negligible | retained in full |
| `market_metadata` | yfinance | ~4 KB/symbol ⇒ ~4.1 MB/refresh | monthly | ~50 MB/yr | **GATED OFF** — Rule 15 ToS blocker (storage/reuse not cleared); enable only after owner ToS review |

## Policy (derived from the table, not arbitrary)

1. **Bulk-refetch datasets** (`historical_daily`, `intraday_minute`): each
   re-fetch supersedes the previous payload (same history + one new candle).
   Full PIT fidelity for the last **keep_last=5** payloads per
   (symbol, exchange, provider, dataset) — enough to reconstruct any
   revision within a trading week; older payloads expire
   (`payload_state='expired_by_compaction'`, `raw_payload→NULL`) while
   **arrival timestamp, seq, provider and content-hash are retained
   forever** — the record that data arrived, and its exact identity, never
   leaves the archive (append-only guarantee preserved; SQLite triggers
   reject any other mutation).
   Uncompacted worst case (120 GB/yr) is not VPS-viable; compacted steady
   state (~2.4 GB + metadata) is.
2. **Incremental datasets** (`ohlc_live`, `market_depth`, `market_metadata`):
   every payload is new information — **no compaction, full retention**
   (~0.5 GB/yr).
3. **Cadence**: compaction is an EXPLICIT maintenance operation, never
   automatic — `python ndsap_archive.py --compact` (weekly cron suggested,
   e.g. Sunday 02:00 IST; every run is written to `compaction_log` +
   `data/audit_log.txt`).
4. **Review cycle**: run `python ndsap_archive.py --stats` monthly; if
   measured growth deviates >2× from this estimate, revise keep_last or
   disk budget. **Disk budget: ≥10 GB free** for `data/ndsap_archive.db`.
5. **No retroactive history**: the archive starts empty at deployment —
   data before deployment does not exist in it and never will (disclosed
   Rule 15 limitation).

## Owner knobs (config.py NDSAP block / PARAMS override)
- `ndsap_archive_enabled` (default True) — master switch
- `ndsap_archive_providers` (default `["dhan"]`) — ToS gate; add
  `"yfinance"` only after clearing the Rule 15 ToS blocker
- `ndsap_compact_keep_last` (default 5) — PIT depth for bulk datasets
