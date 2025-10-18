import logging
import os
import re
import requests
from django.conf import settings

log = logging.getLogger(__name__)

def _bool(v) -> bool:
    return str(v or "").strip().lower() == "true"

# "<digits>:<payload>"
_TOKEN_RE = re.compile(r"^\s*(\d+:[A-Za-z0-9_\-]+)\s*$")
def _clean_token(raw: str) -> str:
    if not raw:
        return ""
    m = _TOKEN_RE.match(raw)
    return m.group(1) if m else raw.strip().split()[0]

# допускаем отрицательные chat_id (каналы/группы)
_CHAT_RE = re.compile(r"^\s*(-?\d+)")
def _clean_chat(raw: str) -> str:
    if not raw:
        return ""
    m = _CHAT_RE.match(str(raw))
    return m.group(1) if m else str(raw).strip()

def _cfg():
    enabled = _bool(os.getenv("NOTIFY_TELEGRAM", getattr(settings, "NOTIFY_TELEGRAM", False)))
    env_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    set_token = (getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "").strip()
    env_chat  = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    set_chat  = (getattr(settings, "TELEGRAM_CHAT_ID", "") or "").strip()

    tok_env = _clean_token(env_token)
    tok_set = _clean_token(set_token)
    chat_env= _clean_chat(env_chat)
    chat_set= _clean_chat(set_chat)

    # если в ENV попалась заглушка/слишком короткий токен — используем settings
    is_placeholder = tok_env.endswith("AAA...") or len(tok_env) < 30
    token = tok_set if (is_placeholder or not tok_env) else tok_env
    chat  = chat_set if (not chat_env) else chat_env

    return enabled, token, chat, env_token, env_chat

def send_telegram_message(text: str, reply_markup: dict | None = None) -> bool:
    enabled, bot, chat, raw_tok, raw_chat = _cfg()
    token_hint = (bot[:9] + "..." + bot[-6:]) if bot else "—"
    log.info("[notify] tg cfg enabled=%s token=%s raw_len=%d chat='%s' raw_chat='%s'",
             enabled, token_hint, len(raw_tok or ""), chat, raw_chat)

    if not enabled:
        log.info("[notify] Telegram disabled (NOTIFY_TELEGRAM=false)")
        return False
    if not bot:
        log.error("[notify] Telegram BOT token is empty (after clean)")
        return False
    if not chat:
        log.error("[notify] Telegram CHAT_ID is empty (after clean)")
        return False
    if not text:
        log.warning("[notify] Skip telegram: empty text")
        return False

    # sanity-check токена
    try:
        gm = requests.get(f"https://api.telegram.org/bot{bot}/getMe", timeout=10)
        if not (gm.ok and gm.json().get("ok", False)):
            log.error("[notify] getMe failed: HTTP %s %s", gm.status_code, gm.text[:200])
            return False
    except Exception as e:
        log.exception("[notify] getMe exception: %s", e)
        return False

    url = f"https://api.telegram.org/bot{bot}/sendMessage"
    payload = {
        "chat_id": int(chat),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.ok and r.json().get("ok"):
            log.info("[notify] Telegram sent ok")
            return True
        log.error("[notify] Telegram error: HTTP %s %s", r.status_code, r.text[:300])
    except Exception as e:
        log.exception("[notify] Telegram send failed: %s", e)
    return False

def send_whatsapp_message(text: str) -> bool:
    enabled = _bool(os.getenv("NOTIFY_WHATSAPP", getattr(settings, "NOTIFY_WHATSAPP", False)))
    token   = (os.getenv("WHATSAPP_TOKEN")    or getattr(settings, "WHATSAPP_TOKEN", "")    or "").strip()
    phone_id= (os.getenv("WHATSAPP_PHONE_ID") or getattr(settings, "WHATSAPP_PHONE_ID", "") or "").strip()
    to      = (os.getenv("WHATSAPP_TO")       or getattr(settings, "WHATSAPP_TO", "")       or "").strip()

    if not enabled:
        return False
    if not (token and phone_id and to):
        log.warning("[notify] WhatsApp creds missing")
        return False
    if not text:
        log.warning("[notify] Skip whatsapp: empty text")
        return False

    url = f"https://graph.facebook.com/v20.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"messaging_product":"whatsapp","to":to,"type":"text","text":{"body":text}}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        if r.ok:
            log.info("[notify] WhatsApp sent ok")
            return True
        log.error("[notify] WhatsApp error: %s", r.text)
    except Exception as e:
        log.exception("[notify] WhatsApp send failed: %s", e)
    return False

def notify_all(text: str, reply_markup: dict | None = None) -> bool:
    sent = False
    if send_telegram_message(text, reply_markup=reply_markup):
        sent = True
    if send_whatsapp_message(text):
        sent = True
    if not sent:
        log.info("[notify] No notification sent")
    return sent
