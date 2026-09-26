"""
news_analyzer.py — News sentiment filter (supplementary entry gate)

Method: Loughran & McDonald 2011 ("When Is a Liability Not a Liability?
Textual Analysis, Dictionaries, and 10-Ks", Journal of Finance 66(1)) —
finance-specific sentiment word lists (Negative/Positive/Uncertainty/
Litigious) with negation handling. Academic finance ka standard news-
sentiment method — generic NLP dictionaries finance me biased hote hain,
isliye yehi single engine hai (koi fallback engine nahi).

TIME-AWARE: headlines PRE-MARKET prefetch hoti hain (scheduler 09:11 job →
data/news_sentiment_cache.json). Trade-time par sirf cache read hota hai —
trading window ke andar koi network scrape NAHI (trade miss = bug).
Cache stale/missing → fail-open (True) kyunki ye supplementary filter hai;
primary entry gates iske bina bhi fail-closed hain.
"""

import csv
import logging
import os
import re
from datetime import datetime

import requests

from utils import append_log, load_json, save_json, now_ist
from config import AUDIT_LOG_FILE, PARAMS

logger = logging.getLogger(__name__)

DEFAULT_NEWS_THRESHOLD = -0.3  # per-stock optimizer-configurable (get_param)

NEWS_CACHE_FILE = "data/news_sentiment_cache.json"

_NEGATION = {
    "not", "no", "never", "neither", "nor", "without",
    "cannot", "cant", "wont", "dont", "doesnt", "isnt", "arent",
    "wasnt", "werent", "hasnt", "havent", "hadnt",
}

_lm_words_cache = None


def _load_lm_words() -> dict:
    """LM 2011 word lists (lazy, process-cached).
    Returns {"neg", "pos", "uncert", "litig"} sets."""
    global _lm_words_cache
    if _lm_words_cache is not None:
        return _lm_words_cache
    words = {"neg": set(), "pos": set(), "uncert": set(), "litig": set()}
    path = PARAMS.get("lm_wordlist_file", "data/lm_finance_wordlists.csv")
    if not os.path.exists(path):
        logger.warning(f"LM wordlist missing: {path} — news filter fail-open")
        _lm_words_cache = words
        return words
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                w = (row.get("Word") or "").strip().lower()
                if not w:
                    continue
                try:
                    neg_v = int(float(row.get("Negative") or 0))
                    pos_v = int(float(row.get("Positive") or 0))
                    unc_v = int(float(row.get("Uncertainty") or 0))
                    lit_v = int(float(row.get("Litigious") or 0))
                except (TypeError, ValueError):
                    continue
                if neg_v > 0:
                    words["neg"].add(w)
                if pos_v > 0:
                    words["pos"].add(w)
                if unc_v > 0:
                    words["uncert"].add(w)
                if lit_v > 0:
                    words["litig"].add(w)
    except Exception as e:
        logger.warning(f"LM wordlist parse failed: {type(e).__name__}: {e} — news filter fail-open")
    _lm_words_cache = words
    return words


def _tokenize(text: str) -> list:
    return re.findall(r"[a-z]+", str(text).lower())


def _lm_lexicon_sentiment(texts: list) -> float:
    """
    [Method: Loughran-McDonald 2011] finance-lexicon polarity.
    Negation handling: negation word ke baad news_negation_window tokens
    flip hote hain (standard LM usage convention). Returns [-1, +1];
    0.0 jab koi finance word na mile.
    """
    wl = _load_lm_words()
    if not wl["neg"] and not wl["pos"]:
        return 0.0
    window = int(PARAMS.get("news_negation_window", 3))
    pos = neg = 0
    for text in texts:
        toks = _tokenize(text)
        negated = set()
        for i, t in enumerate(toks):
            if t in _NEGATION:
                for j in range(i + 1, min(i + 1 + window, len(toks))):
                    negated.add(j)
        for i, t in enumerate(toks):
            if t in wl["neg"]:
                if i in negated:
                    pos += 1  # negated negative → positive signal
                else:
                    neg += 1
            elif t in wl["pos"]:
                if i in negated:
                    neg += 1
                else:
                    pos += 1
    total = pos + neg
    if total == 0:
        return 0.0
    return round(max(-1.0, min(1.0, (pos - neg) / total)), 3)


def fetch_headlines(symbol: str) -> list:
    """Yahoo Finance RSS headlines — PRE-MARKET job ONLY (trade-time nahi)."""
    try:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}.NS&region=IN&lang=en-US"
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "xml")
        max_n = int(PARAMS.get("news_max_headlines", 5))
        return [item.title.text for item in soup.find_all("item")][:max_n]
    except requests.exceptions.RequestException as e:
        logger.debug(f"fetch_headlines: request failed for {symbol}: {type(e).__name__}: {e}")
        return []
    except Exception as e:
        logger.debug(f"fetch_headlines: parse failed for {symbol}: {type(e).__name__}: {e}")
        return []


def get_sentiment(symbol: str) -> float:
    """
    TRADE-TIME: sirf fresh cache read (koi network nahi).
    Returns score ya None (cache stale/missing → caller fail-open).
    """
    try:
        cache = load_json(NEWS_CACHE_FILE, {})
        entry = cache.get(symbol)
        if not isinstance(entry, dict):
            return None
        fetched = entry.get("fetched_at")
        if not fetched:
            return None
        now_dt = now_ist()
        fetched_dt = datetime.fromisoformat(str(fetched))
        if now_dt.tzinfo is not None and fetched_dt.tzinfo is None:
            fetched_dt = fetched_dt.replace(tzinfo=now_dt.tzinfo)
        elif now_dt.tzinfo is None and fetched_dt.tzinfo is not None:
            now_dt = now_dt.replace(tzinfo=fetched_dt.tzinfo)
        age_min = (now_dt - fetched_dt).total_seconds() / 60.0
        if age_min < 0 or age_min > float(PARAMS.get("news_cache_ttl_min", 240)):
            return None
        return float(entry.get("score", 0.0))
    except (TypeError, ValueError, KeyError) as e:
        logger.debug(f"get_sentiment: cache read failed for {symbol}: {type(e).__name__}: {e}")
        return None


def prefetch_news_cache(symbols: list = None) -> dict:
    """
    PRE-MARKET job (09:11): tradeable universe ke headlines fetch + LM score
    cache me save. Trading window ke ANDAR kabhi nahi chalana.
    """
    if symbols is None:
        try:
            from stock_selector import get_tradeable_universe
            symbols = get_tradeable_universe()
        except Exception as e:
            logger.warning(f"prefetch_news_cache: universe load failed: {type(e).__name__}: {e}")
            symbols = []
    cap = int(PARAMS.get("news_prefetch_max_symbols", 100))
    symbols = list(symbols)[:cap]
    cache = load_json(NEWS_CACHE_FILE, {})
    updated = 0
    for sym in symbols:
        try:
            titles = fetch_headlines(str(sym))
            if not titles:
                continue
            score = _lm_lexicon_sentiment(titles)
            cache[sym] = {
                "score": score,
                "headlines": len(titles),
                "fetched_at": now_ist().isoformat(),
            }
            updated += 1
        except Exception as e:
            logger.debug(f"prefetch_news_cache: {sym} failed: {type(e).__name__}: {e}")
    save_json(NEWS_CACHE_FILE, cache)
    append_log(AUDIT_LOG_FILE,
               f"NEWS PREFETCH: {updated}/{len(symbols)} symbols cached (Loughran-McDonald 2011 lexicon)")
    return cache


def is_sentiment_ok(symbol: str) -> bool:
    """
    Supplementary filter: False sirf jab FRESH cache me score threshold se
    neeche ho (threshold per-stock optimizer-configurable).
    Cache stale/missing → True (fail-open) — news ki wajah se trade miss
    nahi hoga; primary gates fail-closed hain.
    """
    from per_stock_params import get_param
    threshold = float(get_param(symbol, "news_threshold", DEFAULT_NEWS_THRESHOLD) or DEFAULT_NEWS_THRESHOLD)
    score = get_sentiment(symbol)
    if score is None:
        return True
    if score < threshold:
        append_log(AUDIT_LOG_FILE,
                   f"NEWS BLOCK: {symbol} sentiment={score:.2f} below threshold {threshold} (LM 2011)")
        return False
    return True
