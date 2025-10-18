import os, requests
from django.core.management.base import BaseCommand

API = "https://api.telegram.org/bot{token}/{method}"

class Command(BaseCommand):
    help = "Показать chat_id из последних апдейтов (личка, группы, каналы)."

    def handle(self, *args, **opts):
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not token:
            self.stderr.write("Нет TELEGRAM_BOT_TOKEN в .env")
            return

        # На всякий случай удалим вебхук, чтобы getUpdates работал
        try:
            requests.get(API.format(token=token, method="deleteWebhook"), params={"drop_pending_updates": False}, timeout=15)
        except Exception:
            pass

        try:
            r = requests.get(API.format(token=token, method="getUpdates"), params={"timeout": 5}, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            self.stderr.write(f"Ошибка getUpdates: {e}")
            return

        if not data.get("ok"):
            self.stderr.write(f"API not ok: {data}")
            return

        seen = set()
        for upd in data.get("result", []):
            msg = upd.get("message") or upd.get("edited_message") or upd.get("channel_post") or upd.get("edited_channel_post")
            if not msg:
                continue
            chat = msg.get("chat") or {}
            cid = chat.get("id")
            title = chat.get("title") or chat.get("username") or chat.get("first_name")
            ctype = chat.get("type")
            if cid in seen:
                continue
            seen.add(cid)
            self.stdout.write(f"chat_id={cid} | type={ctype} | title={title}")

        if not seen:
            self.stdout.write("Нет апдейтов. Напиши боту /start в личке или добавь его в группу/канал и пришли сообщение, затем повтори команду.")
