import logging
import os
import threading
import requests
from logging.handlers import RotatingFileHandler
from config import TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID, DATA_DIR

class TelegramLogHandler(logging.Handler):
    """Sends log messages to Telegram admin."""
    def __init__(self, bot_token, chat_id):
        super().__init__()
        self.bot_token = bot_token
        self.chat_id = chat_id

    def emit(self, record):
        # [F12 FIX] This handler is attached to the ROOT logger, so every
        # logger.error()/critical() anywhere in the codebase used to call
        # requests.post() synchronously right here -- on the asyncio event
        # loop if the log came from async code -- and could block it for
        # up to the 5s timeout. Same class of bug as F10, but far more
        # frequent (any error log, not just a rare API hang), and most
        # likely to fire in a cluster during exactly the network-degraded
        # incidents where responsiveness matters most. Fixed the same way
        # signal_broadcaster.py::alert_admin_sync() already does it for the
        # same kind of call: spawn a background daemon thread instead of
        # blocking the caller.
        if not self.bot_token or not self.chat_id:
            return

        log_entry = self.format(record)
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": f"🚨 *Bot Alert* 🚨\n\nLevel: {record.levelname}\n\n`{log_entry}`",
            "parse_mode": "Markdown"
        }

        def _send():
            try:
                requests.post(url, json=payload, timeout=5)
            except Exception:
                pass

        threading.Thread(target=_send, daemon=True, name="tg-log-alert").start()

def setup_advanced_logging():
    os.makedirs(DATA_DIR, exist_ok=True)
    log_file = os.path.join(DATA_DIR, 'bot.log')
    
    # Root logger configuration
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove any existing handlers
    logger.handlers.clear()
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # 1. Console Handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    # 2. Rotating File Handler (10 MB max, keep 5 backups)
    fh = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
    fh.setLevel(logging.INFO)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    # 3. Telegram Alerting for ERROR and CRITICAL
    if TELEGRAM_BOT_TOKEN and ADMIN_CHAT_ID:
        tg_handler = TelegramLogHandler(TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID)
        tg_handler.setLevel(logging.ERROR)
        tg_handler.setFormatter(formatter)
        logger.addHandler(tg_handler)
        
    logging.info("Advanced logging and alerting configured.")
