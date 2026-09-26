"""
dhan_client.py — DhanHQ v2.2.0 client factory
FIX: Token health validation + Rate limiting + Exponential backoff
"""

import logging
import time
import threading
from dhanhq import DhanContext, dhanhq

logger = logging.getLogger(__name__)

# ── Rate Limiter (Thread-Safe) ──
_rate_lock = threading.Lock()
_last_request_time = 0
MIN_REQUEST_INTERVAL_SEC = 0.08  # 80ms minimum between requests


def _rate_limit_pace():
    """Thread-safe rate limiter — ensures minimum interval between API calls."""
    global _last_request_time
    with _rate_lock:
        now = time.monotonic()
        elapsed = now - _last_request_time
        if elapsed < MIN_REQUEST_INTERVAL_SEC:
            time.sleep(MIN_REQUEST_INTERVAL_SEC - elapsed)
        _last_request_time = time.monotonic()


def create_dhan_client(client_id: str, access_token: str):
    """Create Dhan client with rate limiting wrapper."""
    client_id = str(client_id or "").strip()
    access_token = str(access_token or "").strip()

    if not client_id or not access_token:
        raise ValueError("Dhan client_id/access_token missing")

    context = DhanContext(client_id, access_token)
    return dhanhq(context)


def validate_token_health(client_id: str = None, access_token: str = None) -> tuple:
    """
    Pre-market token health validation.
    
    Returns: (is_valid: bool, message: str, data: dict)
    
    - HTTP 200 → (True, "Token Valid", funds_data)
    - HTTP 401/403 → (False, "Token Expired", None)
    - Network error → (False, "Connection Failed", None)
    """
    try:
        from config import DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN, TOKEN_FILE
        from utils import load_json
        
        # Get credentials
        cid = client_id or DHAN_CLIENT_ID
        at = access_token or DHAN_ACCESS_TOKEN
        
        if not cid or not at:
            # Try loading from token file
            token_data = load_json(TOKEN_FILE, {})
            cid = cid or token_data.get("client_id")
            at = at or token_data.get("access_token")
        
        if not cid or not at:
            return (False, "No credentials found. Use /settoken CLIENT_ID ACCESS_TOKEN", None)
        
        # Rate limit before API call
        _rate_limit_pace()
        
        # Create client and test
        client = create_dhan_client(cid, at)
        result = client.get_fund_limits()
        
        if result and isinstance(result, dict):
            balance = result.get("availabelBalance", 0)
            return (True, f"Token Valid (Balance: ₹{float(balance):,.2f})", result)
        else:
            return (False, "Invalid response from Dhan API", None)
            
    except Exception as e:
        error_msg = str(e).lower()
        if "401" in error_msg or "403" in error_msg or "unauthorized" in error_msg or "token" in error_msg:
            logger.warning(f"[DHAN AUTH] Access token invalid or expired: {e}")
            return (False, "Dhan Access Token Expired or Invalid. Please update DHAN_ACCESS_TOKEN in .env", None)
        elif "timeout" in error_msg or "connection" in error_msg:
            logger.warning(f"[DHAN NETWORK] Connection failed: {e}")
            return (False, f"Network error: {e}", None)
        else:
            logger.warning(f"[DHAN ERROR] Validation failed: {e}")
            return (False, f"Validation error: {e}", None)


def api_call_with_retry(api_func, max_retries: int = 3, *args, **kwargs):
    """
    Smart exponential backoff & retry decorator for all API calls.
    
    Retries on:
    - ConnectionError, TimeoutError
    - HTTP 429 (rate limit), 502, 503
    
    Delay: 0.5s → 1.0s → 2.0s
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Rate limit before each attempt
            _rate_limit_pace()
            
            result = api_func(*args, **kwargs)
            return {"success": True, "data": result, "error": None}
            
        except Exception as e:
            last_error = e
            error_msg = str(e).lower()
            
            # Check if retryable
            is_retryable = any(x in error_msg for x in [
                "timeout", "connection", "429", "502", "503", 
                "rate limit", "too many requests", "temporarily"
            ])
            
            if not is_retryable or attempt == max_retries - 1:
                logger.error(f"[DHAN API] Failed after {attempt + 1} attempts: {e}")
                return {"success": False, "data": None, "error": str(e)}
            
            # Exponential backoff: 0.5s, 1.0s, 2.0s
            delay = 0.5 * (2 ** attempt)
            logger.warning(f"[DHAN API] Retry {attempt + 1}/{max_retries} after {delay}s: {e}")
            time.sleep(delay)
    
    return {"success": False, "data": None, "error": str(last_error)}
