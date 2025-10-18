import os, requests, re
from django.core.management.base import BaseCommand

def clean_chat_id(val: str):
    if val is None:
        return None
    val = val.strip().lstrip("\ufeff")
    m = re.match(r"-?\d+", val)
    return int(m.group(0)) if m else None

class Command(BaseCommand):
    help = "Отправить тестовое сообщение в Telegram из .env"

    def add_arguments(self, parser):
        parser.add_argument("text", nargs="*", help="Текст сообщения")
        parser.add_argument("--force", action="store_true", help="Игнорировать NOTIFY_TELEGRAM и отправить всё равно")

    def handle(self, *args, **opts):
        text = " ".join(opts.get("text") or []) or "Привет Aleksandr! 👋 Тест из Django"
        raw_enabled = os.getenv("NOTIFY_TELEGRAM", "false")
        enabled = (raw_enabled.strip().lower() == "true")
        token   = os.getenv("TELEGRAM_BOT_TOKEN", "") or ""
        raw_chat= os.getenv("TELEGRAM_CHAT_ID", "") or ""
        chat_id = clean_chat_id(raw_chat)
        force   = bool(opts.get("force"))

        token_hint = (token[:9] + "..." + token[-6:]) if token else "—"
        self.stdout.write(f"RAW_ENABLED='{raw_enabled}' ENABLED={enabled} FORCE={force}")
        self.stdout.write(f"TOKEN={token_hint} RAW_CHAT='{raw_chat}' PARSED_CHAT={chat_id}")

        if not force and not enabled:
            self.stderr.write("Отключено флагом NOTIFY_TELEGRAM=false. Запусти с --force или исправь .env.")
            return

        if not (token and chat_id is not None):
            self.stderr.write("Не отправлено: проверь TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID.")
            return

        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=15
            )
            self.stdout.write(f"HTTP {r.status_code} {r.text[:300]}")
            ok = False
            try:
                ok = r.json().get("ok", False)
            except Exception:
                pass
            if ok:
                self.stdout.write(self.style.SUCCESS("Отправлено! ✅"))
            else:
                self.stderr.write(self.style.ERROR("Не отправлено. См. ответ выше."))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Исключение: {e}"))
