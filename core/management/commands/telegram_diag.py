import os, requests
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = "Показать переменные Telegram и проверить доступность бота (getMe)"

    def handle(self, *args, **opts):
        enabled = os.getenv("NOTIFY_TELEGRAM")
        token   = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

        self.stdout.write(f"NOTIFY_TELEGRAM = {enabled}")
        self.stdout.write(f"BOT_TOKEN set   = {'yes' if token else 'no'}")
        self.stdout.write(f"CHAT_ID set     = {'yes' if chat_id else 'no'}")

        if not token:
            self.stdout.write("getMe → пропущено (нет токена)")
            return

        try:
            r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15)
            self.stdout.write(f"getMe → HTTP {r.status_code} {r.text[:200]}")
        except Exception as e:
            self.stdout.write(f"getMe exception: {e}")
