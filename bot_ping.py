import os, time, requests

BOT_TOKEN = os.getenv("BOT_TOKEN") or "7833050610:AAGiUAOwag6_i71aC2N32NYpGhrN196j7_o"
BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

def api(method, **params):
    r = requests.get(f"{BASE}/{method}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def send(chat_id, text):
    return api("sendMessage", chat_id=chat_id, text=text)

def main():
    # Сброс вебхука на всякий случай
    api("deleteWebhook", drop_pending_updates=True)
    offset = None
    print("Polling… Ctrl+C для выхода")
    while True:
        data = api("getUpdates", timeout=50, offset=offset)
        for upd in data.get("result", []):
            offset = upd["update_id"] + 1
            msg = upd.get("message") or upd.get("edited_message")
            if not msg:
                continue
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "")
            if text.lower().startswith("/start"):
                send(chat_id, "Привет! Я на связи 🤖")
            else:
                send(chat_id, f"Эхо: {text}")
        time.sleep(0.5)

if __name__ == "__main__":
    main()
