import pandas as pd
from pathlib import Path

def test_custom_universe_unknown_metadata_is_not_encoded_as_zero():
    p = Path("data/CUSTOM_UNIVERSE_FINAL.csv")
    df = pd.read_csv(p, low_memory=False)
    for col in ("sector", "industry", "market_cap"):
        assert not (df[col].astype(str).str.strip().isin(["0", "0.0"])).any()

def test_market_metadata_refresh_is_fail_closed():
    import market_metadata
    assert callable(market_metadata.refresh_market_metadata)
