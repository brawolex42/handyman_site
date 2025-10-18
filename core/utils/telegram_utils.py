# core/utils/telegram_utils.py
import os, requests

def _cfg():
    return {
        "enabled": os.getenv("NOTIFY_TELEGRAM","false").strip().lower() == "true",
        "bot": os.getenv("TELEGRAM_BOT_TOKEN","").strip(),
        "chat": os.getenv("TELEGRAM_CHAT_ID","").strip(),
    }

def send_telegram(text: str, parse_mode: str|None=None) -> bool:
    cfg = _cfg()
    if not (cfg["enabled"] and cfg["bot"] and cfg["chat"]):
        print(f"[tg] skip: enabled={cfg['enabled']} bot={'yes' if cfg['bot'] else 'no'} chat={'yes' if cfg['chat'] else 'no'}")
        return False

    payload = {"chat_id": int(cfg["chat"]), "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
        payload["disable_web_page_preview"] = True

    try:
        r = requests.post(f"https://api.telegram.org/bot{cfg['bot']}/sendMessage",
                          json=payload, timeout=15)
        if r.status_code != 200:
            print(f"[tg] HTTP {r.status_code}: {r.text}")
            return False
        data = r.json()
        if not data.get("ok"):
            print(f"[tg] API not ok: {data}")
            return False
        return True
    except Exception as e:
        print(f"[tg] exception: {e}")
        return False
