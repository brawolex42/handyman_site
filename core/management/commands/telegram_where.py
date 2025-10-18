import os, re
from django.core.management.base import BaseCommand
from django.conf import settings

def clean_token(s):
    if not s: return ""
    m = re.match(r"^\s*(\d+:[A-Za-z0-9_\-]+)", s)
    return m.group(1) if m else s.strip().split()[0]

def clean_chat(s):
    if not s: return ""
    m = re.match(r"^\s*(-?\d+)", str(s))
    return m.group(1) if m else str(s).strip()

class Command(BaseCommand):
    help = "Показать TELEGRAM_* из ENV и из settings"

    def handle(self, *args, **opts):
        env_tok = os.getenv("TELEGRAM_BOT_TOKEN","")
        env_id  = os.getenv("TELEGRAM_CHAT_ID","")
        set_tok = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        set_id  = getattr(settings, "TELEGRAM_CHAT_ID", "")
        self.stdout.write(f"ENV:     token={clean_token(env_tok)[:12]}... len={len(env_tok)}  chat={clean_chat(env_id)}")
        self.stdout.write(f"SETTNGS: token={clean_token(set_tok)[:12]}... len={len(set_tok)} chat={clean_chat(set_id)}")
