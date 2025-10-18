import logging
import os
import re
from datetime import datetime
from urllib.parse import urlparse
from django.apps import apps as django_apps
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.html import escape
from django.utils import timezone
from django.db import transaction
from django.core.cache import cache
import zoneinfo

from .notifications import notify_all

log = logging.getLogger(__name__)

MODEL_LABEL = getattr(settings, "APPLICATION_MODEL", "core.Booking")
BERLIN = zoneinfo.ZoneInfo("Europe/Berlin")

def _get_model(label: str):
    try:
        app_label, model_name = label.split(".", 1)
        return django_apps.get_model(app_label, model_name)
    except Exception as e:
        log.exception("Не удалось получить модель из APPLICATION_MODEL=%r: %s", label, e)
        return None

def _phone_href(phone: str) -> str:
    if not phone:
        return "—"
    digits = re.sub(r"[^\d+]", "", phone)
    return f'<a href="tel:{digits}">{escape(phone)}</a>'

def _email_href(email: str) -> str:
    if not email:
        return "—"
    return f'<a href="mailto:{escape(email)}">{escape(email)}</a>'

def _parse_dt(val):
    """Принимает datetime|date|str|None, возвращает aware datetime (Europe/Berlin) или None."""
    if not val:
        return None
    if isinstance(val, datetime):
        dt = val
    else:
        s = str(val).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            dt = None
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except Exception:
                    pass
            if dt is None:
                return None
    if timezone.is_naive(dt):
        dt = dt.replace(tzinfo=BERLIN)
    else:
        dt = dt.astimezone(BERLIN)
    return dt

def _fmt_dt(val):
    dt = _parse_dt(val)
    return dt.strftime("%d.%m.%Y %H:%M") if dt else "—"

TargetModel = _get_model(MODEL_LABEL)

if TargetModel is None:
    log.error("Сигнал не подключён: неверная модель APPLICATION_MODEL=%r", MODEL_LABEL)
else:
    @receiver(post_save, sender=TargetModel, dispatch_uid="core.notify_created")
    def on_booking_created(sender, instance, created, **kwargs):
        log.info("[signals] post_save %s pk=%s created=%s",
                 sender.__name__, getattr(instance, "pk", None), created)
        if not created:
            return

        # Антидубль на 15 секунд
        dedupe_key = f"notify:{sender.__name__}:{getattr(instance, 'pk', 'none')}"
        if not cache.add(dedupe_key, "1", timeout=15):
            log.info("[signals] duplicate suppressed for %s pk=%s",
                     sender.__name__, getattr(instance, "pk", None))
            return

        def g(obj, name, default=""):
            return getattr(obj, name, default) or default

        name = escape(str(g(instance, "name") or g(instance, "customer_name")))
        phone = escape(str(g(instance, "phone") or g(instance, "customer_phone")))
        email = escape(str(g(instance, "email") or g(instance, "customer_email")))
        address = escape(str(g(instance, "address")))
        city = escape(str(g(instance, "city")))
        preferred_dt = g(instance, "preferred_datetime") or g(instance, "date")
        description = escape(str(g(instance, "description") or g(instance, "notes")))
        created_at = g(instance, "created_at") or g(instance, "created") or g(instance, "created_on")
        status = escape(str(g(instance, "status") or g(instance, "state")))
        preset = escape(str(g(instance, "service_preset")))

        service_title = ""
        try:
            if getattr(instance, "service", None):
                service_title = escape(str(getattr(instance.service, "title", "") or getattr(instance.service, "name", "")))
        except Exception:
            service_title = ""
        service_line = service_title or preset or "Service"

        phone_link = _phone_href(phone)
        email_link = _email_href(email)
        preferred_dt_str = _fmt_dt(preferred_dt)
        created_at_str = _fmt_dt(created_at)

        lines = [
            "<b>🆕 Новая заявка</b>",
            f"🆔 ID: {getattr(instance, 'pk', '')}",
            f"🧰 Услуга: {service_line}",
            f"👤 Имя: {name or '—'}",
            f"📞 Телефон: {phone_link}",
            f"✉️ Email: {email_link}",
            f"🏠 Адрес: {address or '—'}",
            f"🏙️ Город: {city or '—'}",
            f"🗓️ Желаемое время: {preferred_dt_str}",
            f"📝 Описание: {description or '—'}",
            f"📌 Статус: {status or '—'}",
            f"⏰ Создано: {created_at_str}",
        ]
        text = "\n".join(lines)

        # Инлайн-кнопка только для публичного домена (не localhost/127.0.0.1)
        site_domain = (os.getenv("SITE_DOMAIN", "") or "").strip()  # напр., smarthome.de или https://smarthome.de
        reply_markup = None
        if site_domain:
            base = site_domain if site_domain.startswith(("http://", "https://")) else f"https://{site_domain}"
            parsed = urlparse(base)
            host = (parsed.hostname or "").lower()
            if host and host not in ("localhost", "127.0.0.1"):
                detail_url = f"{base.rstrip('/')}/owner/booking/{getattr(instance,'pk','')}/"
                reply_markup = {"inline_keyboard": [[{"text": "🔗 Открыть заявку", "url": detail_url}]]}
            else:
                log.info("[signals] skip button: non-public host '%s'", host)

        def _send():
            ok = notify_all(text, reply_markup=reply_markup)
            log.info("[signals] Notify for %s pk=%s -> %s",
                     sender.__name__, getattr(instance, "pk", None),
                     "sent" if ok else "skipped")

        try:
            transaction.on_commit(_send)
        except Exception:
            _send()
