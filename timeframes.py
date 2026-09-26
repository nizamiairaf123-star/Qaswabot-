"""
mtf/timeframes.py — TF menu + grammar helpers (ADD-ONLY).

[Method: Multiple Time Frame Analysis — Dr. Alexander Elder, 1986]
[Method: 15-pair tournament grammar — Elder 1986 (HTF=trend/LTF=entry) + Pardo 2008 (selection)]
[Custom engineering] — pair occupancy machine-decide hogi, human sirf grammar define karta hai
(user directive: "HTF and LTF optimization se decide hona chahiye, tum decide nahi kar sakte").
"""

from config import MTF_TIMEFRAMES, MTF_DOWNLOAD_TFS, MTF_DERIVED_TFS

# TF → minutes (1D treated as session-length ordering bucket)
TF_MINUTES = {"5m": 5, "15m": 15, "30m": 30, "60m": 60, "2H": 120, "1D": 999999}

# Dhan intraday API intervals (verified from existing dhan_data.py usage)
DHAN_INTERVAL_MAP = {"5m": "5", "15m": "15", "60m": "60"}


def all_tfs() -> list:
    """COMPLETE TF menu — koi drop nahi."""
    return list(MTF_TIMEFRAMES)


def is_download_tf(tf: str) -> bool:
    """Dhan se directly aane wala TF?"""
    return tf in MTF_DOWNLOAD_TFS


def is_derived_tf(tf: str) -> bool:
    """Resample se banne wala FREE TF? (30m←15m, 2H←60m)"""
    return tf in MTF_DERIVED_TFS


def source_tf(tf: str) -> str:
    """Derived TF ke liye source TF, warna khud."""
    return MTF_DERIVED_TFS.get(tf, tf)


def tf_rank(tf: str) -> int:
    """Higher = higher timeframe (trend side)."""
    return TF_MINUTES[tf]


def htf_ltf_pairs() -> list:
    """
    15 pairs: C(6,2) jahan HTF rank > LTF rank.
    Grammar (Elder, 1986): HTF trend define karta hai, LTF entry timing.
    Kaun pair jeet-ta hai — yeh P2 tournament (Pardo WFV) decide karega, human nahi.
    """
    tfs = sorted(MTF_TIMEFRAMES, key=tf_rank)
    pairs = []
    for ltf in tfs:
        for htf in tfs:
            if tf_rank(htf) > tf_rank(ltf):
                pairs.append((htf, ltf))
    assert len(pairs) == 15, f"Expected 15 pairs, got {len(pairs)}"
    return pairs


if __name__ == "__main__":
    print("TFs:", all_tfs())
    print("Download:", MTF_DOWNLOAD_TFS, "| Derived:", MTF_DERIVED_TFS)
    for h, l in htf_ltf_pairs():
        print(f"  HTF={h:>3}  LTF={l}")
