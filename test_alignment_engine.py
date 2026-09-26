from alignment_engine import compare, _metrics_from_returns

def test_alignment_insufficient_data():
    r=compare({"trades":10,"win_rate_pct":60,"profit_factor":1.5,"avg_return_pct":1.0}, {"trades":0})
    assert r["status"] == "INSUFFICIENT_DATA"

def test_alignment_measures_without_becoming_and_gate():
    r=compare({"trades":20,"win_rate_pct":60,"profit_factor":1.5,"avg_return_pct":1.0},
              {"trades":20,"win_rate_pct":52,"profit_factor":1.2,"avg_return_pct":0.8})
    assert r["status"] == "MEASURED"
    assert r["win_rate_gap_pct_points"] == 8
    assert "wr_within_configured_gap" in r

def test_metrics():
    m=_metrics_from_returns([1,-1,2,-0.5])
    assert m["trades"]==4
    assert m["win_rate_pct"]==50.0
    assert m["profit_factor"]==2.0
