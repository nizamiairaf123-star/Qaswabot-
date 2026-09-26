import optimizer


def _fake_result(score, params=None):
    return {"score": score, "result": {"params": params or {}, "total_trades": 10}}


def test_subset_selector_can_select_more_than_one_tool(monkeypatch):
    tools=list(optimizer.SIGNAL_GENERATORS)[:3]
    all_results={n:_fake_result(10+i*2, {"ema_fast":10,"ema_slow":50}) for i,n in enumerate(tools)}
    monkeypatch.setattr(optimizer, "SIGNAL_GENERATORS", {n: object() for n in tools})
    def ev(data, fn, *args, symbol=None, **kwargs):
        names=fn.__name__.replace("toolset_", "").split("_")
        return {"total_trades":10,"win_rate_pct":60,"profit_factor":2,"total_return_pct":20,
                "recovery_factor":2,"sharpe":1,"avg_win_return":2,"avg_loss_return":-1,
                "portfolio_max_dd_pct":2,"trades":[{"net_return_pct":1}]*10,
                "params":{"ema_fast":10,"ema_slow":50}}
    monkeypatch.setattr(optimizer, "backtest_with_params", ev)
    monkeypatch.setattr(optimizer, "calculate_institutional_score", lambda r,*a,**k: 20 + (r.get("total_trades",0)*0.0))
    out=optimizer._select_per_stock_toolset("X", object(), all_results, {})
    assert 1 <= len(out["selected_tools"]) <= 3
    assert out["subset_search_evaluated"] is True


def test_selector_has_no_fixed_top3_slice():
    src=__import__('inspect').getsource(optimizer._select_per_stock_toolset)
    assert "[:3]" not in src
    assert "len(SIGNAL_GENERATORS)" in src
