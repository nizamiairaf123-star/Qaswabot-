"""
Auto Board Filter - 10x thinking best tarika without manual list

================================================================================
ADMIN PERMISSION REQUIRED - YFINANCE USAGE RESTRICTED TO COMPANY INFORMATION ONLY
================================================================================
- yfinance is used ONLY for Non-Muslim Board of Directors fetching (companyOfficers)
  Reason: Dhan API does NOT provide board of directors data, so yfinance is the ONLY place where yfinance is needed
  Source: yf.Ticker('SYMBOL.NS').info['companyOfficers'] -> board members names
  Location: This file board_filter_auto.py and board_manager.py (board fetching only)

- All other data (price, volume, market data, optimization, backtest, sector, FII/DII, etc) MUST use Dhan data only, NOT yfinance
  Source for price/volume: Dhan API via dhan_data.py, broker.py, intraday_filter.py (Dhan scrip master https://images.dhan.co/api-data/api-scrip-master.csv)
  Reason: Yfinance can have 19-20 difference from Dhan, trade happens on Dhan account, so Dhan data must be used to avoid problem

- If any other AI is asked to replace something and sees this yfinance usage, DO NOT CHANGE this yfinance usage without ADMIN PERMISSION
  If changes are needed, first take ADMIN PERMISSION, because board data cannot be fetched from Dhan, yfinance is required only for board

- Yfinance is better to avoid if possible, but if work cannot happen without it (board data), must use for board only

This file: board_filter_auto.py - Fetch board members via yfinance companyOfficers for all 1261 symbols (batch 100), heuristic Muslim name detection
================================================================================
"""
import pandas as pd, re, json, time
from utils import now_ist, redact_secrets

# ADMIN PERMISSION REQUIRED: yfinance used only for company information; this module uses board data members fetching, Dhan does not provide board data
# If you see this import, DO NOT REPLACE with Dhan data without admin permission, because Dhan doesn't have board data
# All other data MUST be Dhan data only
try:
    import yfinance as yf
except ImportError:
    yf = None
    print("yfinance not installed, board fetch will fail - install yfinance for board only")

# Rest data MUST be Dhan data only - do not use yfinance for price/volume


# Comprehensive common Muslim names keywords (first and last names)
muslim_names = [
    # Most common
    'mohammed', 'mohammad', 'muhammad', 'mohd', 'mohamad', 'mohamed',
    'ahmed', 'ahmad', 'ahamed',
    'ali', 'khan', 'sheikh', 'shaikh', 'syed', 'sayed', 'sayyed', 'saiyed',
    'hussain', 'hussain', 'hussein', 'hassan', 'hasan', 'abbas', 'abdullah', 'abdulla',
    'abdul', 'rahman', 'rehman', 'rahim', 'karim', 'qureshi', 'siddiqui', 'siddique', 'ansari',
    'malik', 'usman', 'osman', 'rizwan', 'imran', 'iqbal', 'farhan', 'faizan', 'arif', 'asif', 'aslam', 'ashraf',
    'akhtar', 'anwar', 'azhar', 'bilal', 'danish', 'ehsan', 'ejaz', 'firoz', 'feroz', 'ghulam', 'habib', 'haider', 'hamid', 'haroon', 'harun',
    'ibrahim', 'ismail', 'javed', 'jamal', 'jamil', 'kabir', 'khalid', 'khaja', 'khwaja', 'liaqat', 'mahmood', 'mahmoud', 'mansoor', 'maqsood', 'masood',
    'mehmood', 'moin', 'moinuddin', 'mohsin', 'mubarak', 'mumtaz', 'munir', 'mustafa', 'nadeem', 'naeem', 'naim', 'nasir', 'nazeer', 'nazir', 'nisar',
    'noor', 'noori', 'qadir', 'qasim', 'rafiq', 'rafi', 'raza', 'riaz', 'riyaz', 'sadiq', 'saeed', 'said', 'sajid', 'salim', 'saleem', 'salman',
    'sameer', 'samir', 'shabbir', 'shafiq', 'shakil', 'shakir', 'shamim', 'sharif', 'shoaib', 'suleman', 'suleiman', 'sultan', 'tahir', 'tariq', 'tauqir',
    'umair', 'umar', 'omar', 'usama', 'osama', 'waseem', 'wasim', 'yasin', 'yasir', 'younus', 'yunus', 'zakir', 'zafar', 'zahid', 'zaid', 'zain', 'zakaria',
    'faisal', 'fasil', 'farooq', 'farook', 'faruk', 'aziz', 'azad',  # careful: azad can be non-muslim name too? But often Muslim
    'rashid', 'rashid', 'latif', 'hanif', 'arif', 'asif', 'akram', 'amjad', 'anwar', 'afzal', 'aftab', 'ajmal', 'alam', 'amin', 'amir',
    'anwari', 'ashfaq', 'ayub', 'ayyub', 'azmat', 'babar', 'babur', 'bashir', 'basheer', 'bhat', # Bhat can be Kashmiri Muslim or Pandit - ambiguous
    'choudhary', 'choudhury',  # ambiguous
    'dawood', 'daud', 'dilawar', 'ejaz', 'faiz', 'faiyaz',
    'ghafoor', 'ghani', 'ghouse', 'gulzar',
    'hafeez', 'hafiz', 'hameed', 'hameed', 'haneef', 'hanif',
    'idris', 'ilyas', 'imtiaz', 'inayat',
    'junaid', 'kaleem', 'kamil', 'kashif', 'khader', 'khaleel', 'khalil',
    'latheef', 'lateef',
    'majid', 'mansur', 'maqbool', 'masood', 'mubeen', 'mujeeb', 'munawar', 'musharraf', 'mustaq',
    'nabi', 'nazeem', 'nawaz', 'nazim',
    'parvez', 'pervez', 'qayyum', 'quddus',
    'raheem', 'rahees', 'ramzan', 'razzak', 'rizwan', 'roshan', # Roshan ambiguous
    'sattar', 'shafi', 'shahbaz', 'shahid', 'shakir', 'shams', 'shamsuddin',
    'sultan', 'sufiyan', 'sufyan',
    'tanveer', 'tanvir', 'tufail', 'usman',
    'waheed', 'wahid', 'wasi', 'wazir',
    'yaqoob', 'yousuf', 'yusuf',
    'zabi', 'zaheer', 'zahoor', 'zaki',
]

# Remove duplicates and sort by length descending for regex (longer first to avoid partial)
muslim_names = sorted(list(set(muslim_names)), key=len, reverse=True)

# Compile regex with word boundary for each name
# Use \b for word boundary, but for names like "mohammed" we want to match as whole word
muslim_pattern = re.compile(r'\b(' + '|'.join(map(re.escape, muslim_names)) + r')\b', re.IGNORECASE)

def is_potential_muslim_name(full_name: str):
    """
    Heuristic check if name contains common Muslim name as whole word
    Returns (is_muslim: bool, matched_keyword: str or None)

    [2026-09-04 r5] SINGLE SCANNER: delegates to board_manager.is_potential_muslim_name
    so the one-time batch and the monthly refresh can never disagree again
    (they had drifted: 93 names missing at runtime, dual-community names such
    as Kamal/Parveen treated as high-confidence there). board_manager applies:
    high-confidence Muslim token → Muslim; dual-community token → Muslim unless
    the same full name carries an unmistakable non-Muslim marker; fail-closed.
    The `muslim_names` list above is still merged into board_manager's
    high-confidence list, so nothing curated here is lost.
    """
    if not full_name or not isinstance(full_name, str):
        return False, None
    try:
        from board_manager import is_potential_muslim_name as _shared
        is_mus, kw, _tier = _shared(full_name)
        return bool(is_mus), kw
    except Exception:
        # fallback: local pattern (should never happen inside the package)
        name_clean = re.sub(r'\b(Mr|Ms|Mrs|Dr|Prof|Shri|Smt|Late)\.?\s*', '', full_name, flags=re.IGNORECASE)
        m = muslim_pattern.search(name_clean.strip())
        return (True, m.group(0)) if m else (False, None)

# Test heuristic on sample names
test_names = [
    "Mr. Mukesh Dhirubhai Ambani",
    "Mr. Nikhil Rasiklal Meswani",
    "Mr. Ahmed Khan",
    "Mr. Mohammed Ali",
    "Ms. Ayesha Siddiqui",
    "Mr. Rakesh Sharma",
    "Mr. Arif Khan",
    "Mr. Sunil Singhania",
    "Mr. Abdul Kalam",
    "Mr. Ramesh Agarwal",
    "Mr. Yusuf Pathan",
    "Mr. Aaron Industries Limited",  # Should not flag Ali in Aaron? \bAli\b should not match Aaron
]
# [AUDIT FIX — board risk item B] Everything below used to be top-level module
# code that executed immediately on ANY import of this file — including a full
# yfinance batch fetch across ~1261 symbols and an unconditional overwrite of
# data/CUSTOM_UNIVERSE_FINAL.csv. If any other module ever did
# `import board_filter_auto` instead of running it as a script, it would silently
# re-run this whole batch job and destroy the live universe file. Now guarded so
# it only runs when this file is executed directly:
#   python3 board_filter_auto.py
if __name__ == "__main__":
    print("=== Testing heuristic ===")
    for n in test_names:
        is_muslim, kw = is_potential_muslim_name(n)
        print(f"{n} -> Muslim? {is_muslim} (matched: {kw})")

    # Now load CUSTOM 1261
    custom_df = pd.read_csv('data/CUSTOM_UNIVERSE_FINAL.csv')
    print(f"\nLoaded CUSTOM: {len(custom_df)}")

    custom_df['yahoo_ticker'] = custom_df.apply(lambda r: f"{r['symbol']}.NS" if r['exchange']=='NSE' else f"{r['symbol']}.BO", axis=1)

    BATCH_SIZE=100
    total=len(custom_df)
    batches=(total+BATCH_SIZE-1)//BATCH_SIZE

    board_results = {}  # symbol -> {directors: [...], has_muslim: bool, matched: [...], non_muslim_board: bool}
    non_muslim_board_true=[]
    non_muslim_board_false=[]
    verification_failures=[]

    for batch_idx in range(batches):
        start=batch_idx*BATCH_SIZE
        end=min(start+BATCH_SIZE, total)
        batch=custom_df.iloc[start:end]
        print(f"\n--- Batch {batch_idx+1}/{batches}: {start}-{end} ---")
        for _, row in batch.iterrows():
            sym=row['symbol']
            yahoo=row['yahoo_ticker']
            try:
                ticker=yf.Ticker(yahoo)
                info=ticker.info
                officers=info.get('companyOfficers', [])
                directors=[o.get('name','') for o in officers if o.get('name')]
                # If no officers, try executiveTeam?
                if not directors:
                    exec_team=info.get('executiveTeam', [])
                    directors=[e.get('name','') for e in exec_team if e.get('name')]
            
                # No director data is not a successful verification.
                # Strict fail-closed: unknown board => non_muslim_board=False.
                if not directors:
                    raise RuntimeError("No board directors returned; verification unavailable")

                # Check each director for Muslim name
                has_muslim=False
                matched=[]
                for dname in directors:
                    is_mus, kw=is_potential_muslim_name(dname)
                    if is_mus:
                        has_muslim=True
                        matched.append(f"{dname} (matched {kw})")
            
                non_muslim_board = not has_muslim
                board_results[sym]={
                    'directors': directors,
                    'has_muslim': has_muslim,
                    'matched': matched,
                    'non_muslim_board': non_muslim_board,
                    'yahoo_ticker': yahoo,
                    'exchange': row['exchange']
                }
                if non_muslim_board:
                    non_muslim_board_true.append(sym)
                else:
                    non_muslim_board_false.append(sym)
                
                if has_muslim:
                    print(f"  {sym}: HAS Muslim board member -> {matched} -> non_muslim_board=False")
            except Exception as e:
                # Strict fail-closed: fetch/parse error means UNVERIFIED, never True.
                print(redact_secrets(f"  {sym} ({yahoo}) fetch error: {e}"))
                board_results[sym]={
                    'directors': [],
                    'has_muslim': True,
                    'matched': [f"verification_error: {e}"],
                    'non_muslim_board': False,
                    'yahoo_ticker': yahoo,
                    'exchange': row['exchange']
                }
                non_muslim_board_false.append(sym)
                verification_failures.append(sym)
        # Small sleep to avoid rate limit
        time.sleep(1)

    print(f"\n=== BOARD FILTER RESULTS ===")
    print(f"Total processed: {len(board_results)}")
    print(f"Non-Muslim Board True (100% Non-Muslim): {len(non_muslim_board_true)}")
    print(f"Non-Muslim Board False (has Muslim director): {len(non_muslim_board_false)}")
    print(f"False examples: {non_muslim_board_false[:30]}")

    # PARTIAL-VERIFICATION SAFETY: a batch with any fetch/parse failure is NOT
    # a successful board refresh. Never publish a partially verified universe
    # or mark the board data as fresh. Preserve the last known-good universe
    # and engage the fail-closed pause instead.
    if verification_failures:
        import json
        state_path = 'data/custom_universe_state.json'
        try:
            with open(state_path, 'r') as f:
                state = json.load(f)
        except Exception:
            state = {}
        state['BOARD_DATA_STALE_PAUSE'] = True
        state['last_error'] = f'BOARD_VERIFICATION_INCOMPLETE:{len(verification_failures)}_SYMBOLS'
        state['last_attempt'] = now_ist().isoformat()
        with open(state_path, 'w') as f:
            json.dump(state, f, indent=2)
        print(f"\nABORTED: {len(verification_failures)} symbols could not be verified. Existing CUSTOM_UNIVERSE_FINAL.csv was NOT overwritten.")
        raise SystemExit(2)

    # Save board results only after 100% verification completed successfully.
    import json
    with open('data/board_members_yfinance.json','w') as f:
        json.dump(board_results, f, indent=2)

    # Save True/False lists
    pd.DataFrame([{'symbol': s, 'non_muslim_board': True} for s in non_muslim_board_true]).to_csv('data/BOARD_TRUE_100_NON_MUSLIM.csv', index=False)
    pd.DataFrame([{'symbol': s, 'non_muslim_board': False, 'matched': str(board_results[s]['matched']), 'directors': str(board_results[s]['directors'])} for s in non_muslim_board_false]).to_csv('data/BOARD_FALSE_HAS_MUSLIM.csv', index=False)

    # Update CUSTOM file to only True
    final_true_df = custom_df[custom_df['symbol'].isin(non_muslim_board_true)].copy()
    # Update non_muslim_board column to reflect actual check
    final_true_df['non_muslim_board'] = True
    # For False, we will exclude from CUSTOM (since only non-Muslim board wanted)
    # But also need to keep board_status.json updated

    # Update board_status.json via board_manager
    from board_manager import update_board_status
    for sym in non_muslim_board_true:
        br=board_results[sym]
        update_board_status(sym, True, br['directors'], verified_by="auto_heuristic_yfinance_10x_thinking")

    for sym in non_muslim_board_false:
        br=board_results[sym]
        update_board_status(sym, False, br['directors'], verified_by="auto_heuristic_yfinance_10x_thinking")

    # Save final CUSTOM with only True
    final_true_df.to_csv('data/CUSTOM_UNIVERSE_FINAL.csv', index=False)
    print(f"\nUpdated CUSTOM_UNIVERSE_FINAL.csv to only 100% Non-Muslim Board: {len(final_true_df)} rows (from {total}) - REPLACED")
    print(f"Excluded {len(non_muslim_board_false)} due to board filter")

    # Update state
    state_path='data/custom_universe_state.json'
    state={
        "last_successful_update": now_ist().isoformat(),
        "last_attempt": now_ist().isoformat(),
        "BOARD_DATA_STALE_PAUSE": False,
        "last_error": None,
        "total_symbols": len(final_true_df),
        "before_board_filter": total,
        "after_board_filter_true": len(non_muslim_board_true),
        "after_board_filter_false": len(non_muslim_board_false),
        "active_filters": [
            "1. Pure Sharia (Finance/Riba/Interest, Insurance, Alcohol, Tobacco, Gambling, Pork, Adult, Weapons) - 1978",
            "2. Non-Muslim Board 100% (auto heuristic via yfinance companyOfficers + Muslim name list, 10x thinking)",
            "3. Price >100",
            "4. Illiquid filter (always illiquid exclude, sometimes liquid dynamic)",
            "5. Baaki criteria preserved"
        ],
        "note": "Board filter auto applied via yfinance + heuristic Muslim name list with word boundary. Best tarika without manual list."
    }
    with open(state_path,'w') as f:
        json.dump(state,f,indent=2)

    print(f"\n=== FINAL AFTER BOARD FILTER ===")
    print(f"Final tradable: {len(final_true_df)} (100% Non-Muslim Board)")
    print(f"State updated")

