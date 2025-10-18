# core/views.py
import re
import hmac, hashlib, base64, json, uuid
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from datetime import datetime as _dt
import requests

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.mail import send_mail, EmailMessage, EmailMultiAlternatives
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.encoding import iri_to_uri, force_bytes, force_str
from django.utils.translation import gettext as _
from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncMonth
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

# ✅ Новые импорты для активации
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.auth import get_user_model

from .forms import RegisterForm, BookingForm, ReviewForm
from .models import Service, Booking, Review
from .tokens import account_activation_token

User = get_user_model()

# =========================
#         Публичные
# =========================

def home(request):
    featured = Service.objects.filter(is_active=True).order_by('title')[:6]
    last_reviews = Review.objects.order_by('-created_at')[:5]
    ctx = {
        'featured': featured,
        'last_reviews': last_reviews,
        'rate': getattr(settings, 'HOURLY_RATE_EUR', 18),
    }
    if request.user.is_authenticated and request.user.is_staff:
        ctx['staff_last'] = Booking.objects.order_by('-created_at')[:5]
    return render(request, 'home.html', ctx)


def services(request):
    items = Service.objects.filter(is_active=True).order_by('title')
    return render(request, 'services.html', {
        'services': items,
        'rate': getattr(settings, 'HOURLY_RATE_EUR', 18)
    })


def service_detail(request, pk):
    service = get_object_or_404(Service, pk=pk)
    return render(request, 'service_detail.html', {
        'service': service,
        'rate': getattr(settings, 'HOURLY_RATE_EUR', 18)
    })


def _service_from_preset(preset_key: str):
    if not preset_key:
        return None
    preset_to_category = {
        "appliance": "appliance",
        "electric": "electric",
        "furniture_asm": "furniture",
        "furniture_mov": "furniture",
        "plumbing": "plumbing",
        "other": "other",
    }
    cat = preset_to_category.get(preset_key)
    if not cat:
        return None
    return Service.objects.filter(is_active=True, category=cat).order_by('id').first()


def booking_create(request):
    initial = {}
    sid = request.GET.get('service')
    if sid and sid.isdigit():
        try:
            initial['service'] = Service.objects.get(pk=int(sid), is_active=True)
        except Service.DoesNotExist:
            pass

    if request.method == 'POST':
        form = BookingForm(request.POST, request.FILES or None)
        if form.is_valid():
            booking = form.save(commit=False)
            service = form.cleaned_data.get('service')
            preset = form.cleaned_data.get('service_preset')
            if not service and preset:
                service = _service_from_preset(preset)
            booking.service = service
            if request.user.is_authenticated:
                booking.user = request.user
            booking.save()

            owner_email = getattr(settings, 'OWNER_NOTIFICATION_EMAIL', None)
            if owner_email:
                subject = f"Neue Anfrage: {booking.name} — {booking.city}"
                message = (
                    "Neue Buchung erhalten:\n\n"
                    f"Name: {booking.name}\n"
                    f"E-Mail: {booking.email}\n"
                    f"Telefon: {booking.phone}\n"
                    f"Adresse: {booking.address}, {booking.city}\n"
                    f"Wunschtermin: {booking.preferred_datetime or '—'}\n"
                    f"Service: {booking.service.title if booking.service else '—'}\n"
                    f"Beschreibung:\n{booking.description or '—'}\n\n"
                    "— Website Mann für eine Stunde"
                )
                try:
                    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [owner_email], fail_silently=True)
                except Exception:
                    pass
            messages.success(request, _("Ihre Anfrage wurde gesendet. Wir melden uns bald."))
            return redirect('thanks')
        else:
            messages.error(request, _("Bitte prüfen Sie die Eingabefelder."))
    else:
        form = BookingForm(initial=initial)

    return render(request, 'booking_form.html', {'form': form})


@login_required
def booking_cancel(request, pk: int):
    booking = get_object_or_404(Booking, pk=pk)
    if not (request.user.is_staff or (booking.user_id and booking.user_id == request.user.id)):
        return HttpResponseForbidden(_("Sie dürfen diesen Auftrag nicht stornieren."))

    booking.status = 'cancelled'
    if hasattr(booking, 'cancelled_at'):
        booking.cancelled_at = timezone.now()
    booking.save(update_fields=[f for f in ['status', 'cancelled_at'] if hasattr(booking, f)])

    messages.success(request, _("Auftrag wurde storniert."))
    return redirect('dashboard')


def reviews(request):
    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Danke für Ihre Bewertung!"))
            return redirect('reviews')
        else:
            messages.error(request, _("Bitte prüfen Sie die Eingabefelder."))
    else:
        form = ReviewForm()
    items = Review.objects.order_by('-created_at')
    return render(request, 'reviews.html', {'form': form, 'items': items})


@login_required
def dashboard(request):
    qs = Booking.objects.all().order_by('-created_at')
    if request.user.is_staff:
        bookings = qs[:100]
    else:
        bookings = qs.filter(user=request.user, is_archived=False)[:100]
    return render(request, 'dashboard.html', {'bookings': bookings})


def thanks(request):
    return render(request, 'thanks.html')


# =========================
#   Регистрация/Логин
# =========================

# ✅ Новое: отправка письма активации (DE)
def _send_activation_email(request, user):
    current_site = get_current_site(request)
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = account_activation_token.make_token(user)
    activate_url = request.build_absolute_uri(
        reverse('activate', kwargs={'uidb64': uidb64, 'token': token})
    )
    ctx = {
        'user': user,
        'site_name': current_site.name or current_site.domain,
        'activate_url': activate_url,
    }
    subject = "Bitte bestätigen Sie Ihre E-Mail-Adresse"
    text_body = render_to_string('emails/activation_email.txt', ctx)
    html_body = render_to_string('emails/activation_email.html', ctx)

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@example.com'),
        to=[user.email],
    )
    email.attach_alternative(html_body, "text/html")
    email.send(fail_silently=True)

def register_view(request):
    """Создаёт пользователя и отправляет письмо для E-Mail-Bestätigung (без автологина)."""
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()  # RegisterForm ставит is_active=False
            _send_activation_email(request, user)
            messages.success(
                request,
                "Wir haben Ihnen eine E-Mail mit einem Aktivierungslink gesendet. "
                "Bitte bestätigen Sie Ihre E-Mail-Adresse."
            )
            return redirect("login")
        return render(request, "auth_register.html", {"form": form}, status=400)
    else:
        form = RegisterForm()
    return render(request, "auth_register.html", {"form": form})

# ✅ Новое: обработчик активации
def activate_account(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and account_activation_token.check_token(user, token):
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=['is_active'])
        messages.success(request, "Ihr Konto wurde aktiviert! Sie können sich jetzt anmelden.")
        return redirect('login')
    messages.error(request, "Der Aktivierungslink ist ungültig oder abgelaufen.")
    return redirect('login')

# ✅ Новое: повторная отправка
def resend_activation(request):
    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip()
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            messages.error(request, "Kein Benutzer mit dieser E-Mail gefunden.")
            return redirect('resend_activation')
        if user.is_active:
            messages.info(request, "Dieses Konto ist bereits aktiviert.")
            return redirect('login')
        _send_activation_email(request, user)
        messages.success(request, "Der Aktivierungslink wurde erneut gesendet.")
        return redirect('login')
    return render(request, 'resend_activation.html')

# =========================
#        Владелец
# =========================

def is_staff(user):
    return user.is_authenticated and user.is_staff


@user_passes_test(is_staff)
def owner_dashboard(request):
    status = request.GET.get('status') or ''
    city = request.GET.get('city') or ''
    q = request.GET.get('q') or ''
    scope = (request.GET.get('scope') or 'active').lower()
    if scope not in {'active', 'archiv', 'all'}:
        scope = 'active'

    qs = Booking.objects.all()

    if scope == 'active':
        qs = qs.filter(is_archived=False)
    elif scope == 'archiv':
        qs = qs.filter(is_archived=True)

    if status in ['new', 'done', 'cancelled', 'confirmed']:
        qs = qs.filter(status=status)
    if city:
        qs = qs.filter(city__icontains=city)
    if q:
        qs = qs.filter(
            Q(name__icontains=q) |
            Q(email__icontains=q) |
            Q(phone__icontains=q) |
            Q(address__icontains=q) |
            Q(description__icontains=q)
        )

    ctx = {
        'bookings': qs.order_by('-created_at')[:500],
        'status': status,
        'city': city,
        'q': q,
        'scope': scope,
        'count_all': Booking.objects.count(),
        'count_active': Booking.objects.filter(is_archived=False).count(),
        'count_archiv': Booking.objects.filter(is_archived=True).count(),
    }
    return render(request, 'owner_dashboard.html', ctx)


@user_passes_test(is_staff)
def owner_booking_detail(request, pk):
    b = get_object_or_404(Booking, pk=pk)
    return render(request, 'owner_booking_detail.html', {'b': b})


@user_passes_test(is_staff)
@require_POST
def owner_booking_archive(request, pk: int):
    b = get_object_or_404(Booking, pk=pk)
    b.archive()
    messages.success(request, _("In Archiv verschoben."))
    return redirect(request.POST.get('next') or request.GET.get('next') or 'owner_booking_detail', pk=pk)

@user_passes_test(is_staff)
@require_POST
def owner_booking_restore(request, pk: int):
    b = get_object_or_404(Booking, pk=pk)
    b.restore()
    messages.success(request, _("Aus dem Archiv wiederhergestellt."))
    return redirect(request.POST.get('next') or request.GET.get('next') or 'owner_booking_detail', pk=pk)


# ====== Биллинг: парсинг часов, формат, округление ======

def _parse_hours_input(text: str) -> Decimal:
    s = (text or "").strip().lower()
    if not s:
        raise ValueError("empty")

    m = re.match(r'^(\d+)\s*:\s*([0-5]?\d)$', s)  # HH:MM
    if m:
        h = int(m.group(1)); mm = int(m.group(2))
        total = Decimal(h) + (Decimal(mm) / Decimal(60))
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if re.match(r'^(?=.*h)(?=.*m).*$', s):        # Xh Ym
        h = re.search(r'(\d+)\s*h', s)
        mm = re.search(r'(\d+)\s*m', s)
        hours = int(h.group(1)) if h else 0
        mins = int(mm.group(1)) if mm else 0
        total = Decimal(hours) + (Decimal(mins) / Decimal(60))
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    m = re.match(r'^(\d+)\s*(m|min)$', s)         # только минуты: 33m
    if m:
        mins = int(m.group(1))
        total = Decimal(mins) / Decimal(60)
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    s_norm = s.replace(',', '.')
    if re.match(r'^\d+(\.\d+)?$', s_norm):        # десятичные часы
        total = Decimal(s_norm)
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    raise ValueError("invalid format")

def _fmt_de(value: Decimal | float) -> str:
    return f"{Decimal(value):.2f}".replace('.', ',')

def _round_up_minutes(total_minutes: int, step_minutes: int) -> int:
    if step_minutes <= 0:
        return total_minutes
    return ((total_minutes + step_minutes - 1) // step_minutes) * step_minutes


@user_passes_test(is_staff)
def owner_booking_set_hours(request, pk):
    b = get_object_or_404(Booking, pk=pk)
    if request.method == 'POST':
        raw_hours = request.POST.get('hours', '')
        raw_km = request.POST.get('travel_km', '')
        raw_min = request.POST.get('travel_minutes', '')
        try:
            hours_val = _parse_hours_input(raw_hours)
            if hours_val < 0:
                raise ValueError

            travel_km_val = None
            if str(raw_km).strip():
                travel_km_val = Decimal(str(raw_km).replace(',', '.'))
                if travel_km_val < 0:
                    raise ValueError

            travel_min_val = None
            if str(raw_min).strip():
                travel_min_val = int(raw_min)
                if travel_min_val < 0:
                    raise ValueError

            b.hours = hours_val
            b.travel_km = travel_km_val
            b.travel_minutes = travel_min_val
            b.save(update_fields=['hours', 'travel_km', 'travel_minutes'])

            messages.success(request, _("Daten gespeichert."))
        except Exception:
            messages.error(
                request,
                _("Ungültige Eingabe. Beispiele Stunden: 1.5 · 1,5 · 1:30 · 45m; km: 7.5; Minuten: 30")
            )
    return redirect('owner_booking_detail', pk=pk)


@user_passes_test(is_staff)
def owner_booking_done(request, pk):
    b = get_object_or_404(Booking, pk=pk)
    b.status = 'done'
    b.save(update_fields=['status'])

    if b.email:
        try:
            subject = f"Leistungsnachweis – Auftrag #{b.pk}"
            body = (
                "Guten Tag,\n\n"
                "anbei erhalten Sie den Leistungsnachweis zu Ihrem Auftrag.\n"
                "Vielen Dank für Ihr Vertrauen!\n"
                "Mit freundlichen Grüßen\n"
                "AleksHome Service"
            )
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@example.com')
            to = [b.email]

            email = EmailMessage(subject, body, from_email, to)
            filename = f"Leistungsnachweis_{b.pk}.pdf"
            pdf_bytes = _render_booking_pdf_bytes(b)
            email.attach(filename, pdf_bytes, "application/pdf")

            owner_copy = getattr(settings, 'OWNER_NOTIFICATION_EMAIL', '')
            if owner_copy:
                email.cc = [owner_copy]

            email.send(fail_silently=True)
        except Exception:
            messages.warning(request, _("PDF konnte per E-Mail nicht versendet werden."))
    else:
        messages.info(request, _("Keine E-Mail-Adresse vorhanden – PDF nicht gesendet."))

    messages.success(request, _("Auftrag als erledigt markiert."))
    return redirect('owner_booking_detail', pk=pk)


@user_passes_test(is_staff)
def owner_export_bookings_csv(request):
    import csv
    from django.utils.timezone import localtime

    fields = {f.name for f in Booking._meta.get_fields()}
    has_payment = {'payment_status', 'payment_amount'}.issubset(fields)
    has_method = 'payment_method' in fields
    has_archiv = 'is_archived' in fields

    resp = HttpResponse(content_type='text/csv; charset=utf-8')
    resp['Content-Disposition'] = 'attachment; filename="bookings.csv"'
    w = csv.writer(resp, delimiter=';')

    header = ["Erstellt", "Wunschtermin", "Name", "E-Mail", "Telefon",
              "Service", "Adresse", "Stadt", "Status"]
    if has_payment:
        header += ["Zahlung", "Betrag"]
    if has_method:
        header += ["Зahlungsart"]
    if has_archiv:
        header += ["Archiv"]
    w.writerow(header)

    qs = Booking.objects.order_by('-created_at')
    if has_archiv and (request.GET.get('include_archiv') not in ('1', 'true', 'yes')):
        qs = qs.filter(is_archived=False)

    for b in qs:
        row = [
            localtime(b.created_at).strftime("%d.%m.%Y %H:%M"),
            b.preferred_datetime or "",
            b.name, b.email, b.phone,
            (b.service.title if b.service else ""),
            b.address, b.city, b.status,
        ]
        if has_payment:
            ps = getattr(b, "payment_status", "—")
            pa = getattr(b, "payment_amount", None)
            pa_str = (str(pa).replace('.', ',')) if pa is not None else ""
            row += [ps, pa_str]
        if has_method:
            pm = getattr(b, "payment_method", "") or "—"
            row += [pm]
        if has_archiv:
            row += ["JA" if getattr(b, "is_archived", False) else "NEIN"]
        w.writerow(row)

    return resp


# =========================
#           PDF
# =========================

def _draw_header(c, x, y, title):
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, "AleksHome Service – Handyman")
    c.setFont("Helvetica", 10)
    c.drawString(x, y - 12, "Ausgeführt von: Aleksandr Sakilev")
    c.drawString(x, y - 24, "Telefon: +49 1522 908 4569    E-Mail: sakilev.aleksandr@gmail.com")
    c.drawString(x, y - 36, "Adresse: An der Kirche 3, 14476 Potsdam")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y - 56, title)
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(x, y - 62, x + 175*mm, y - 62)

def _label_value(c, label, value, x, y, label_w=40*mm, font="Helvetica", size=10):
    c.setFont(font, size)
    c.drawString(x, y, f"{label}")
    c.drawString(x + label_w, y, f"{value or ''}")

def _box_title(c, title, x, y):
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, title)

def _multi_line(c, text, x, y, max_width_mm=170, leading=14):
    if not text:
        return y
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    max_chars = int(max_width_mm * 2)
    lines = []
    for paragraph in text.split("\n"):
        p = paragraph.strip()
        while len(p) > max_chars:
            cut = p.rfind(" ", 0, max_chars)
            cut = cut if cut != -1 else max_chars
            lines.append(p[:cut])
            p = p[cut:].lstrip()
        lines.append(p)
    c.setFont("Helvetica", 10)
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y

def _fmt_de(value: Decimal | float) -> str:
    return f"{Decimal(value):.2f}".replace('.', ',')

def _round_up_minutes(total_minutes: int, step_minutes: int) -> int:
    if step_minutes <= 0:
        return total_minutes
    return ((total_minutes + step_minutes - 1) // step_minutes) * step_minutes

def _render_booking_pdf_bytes(booking) -> bytes:
    buf = BytesIO()
    width, height = A4
    c = canvas.Canvas(buf, pagesize=A4)
    margin_x = 20*mm
    y = height - 20*mm

    _draw_header(c, margin_x, y, "Leistungsnachweis / Auftragsbestätigung")
    y -= 80

    _label_value(c, "Datum:", _dt.now().strftime("%d.%m.%Y"), margin_x, y)
    _label_value(c, "Auftrags-Nr.:", f"#{booking.pk}", margin_x + 80*mm, y)
    y -= 16

    _box_title(c, "Kundendaten:", margin_x, y); y -= 12
    _label_value(c, "Name:", booking.name, margin_x, y); y -= 14
    _label_value(c, "Adresse:", booking.address, margin_x, y); y -= 14
    _label_value(c, "PLZ / Ort:", booking.city, margin_x, y); y -= 14
    _label_value(c, "Telefon / E-Mail:", f"{booking.phone} / {booking.email}", margin_x, y); y -= 20

    service_title = ""
    try:
        if booking.service:
            service_title = booking.service.title or ""
    except Exception:
        service_title = ""
    service_line = service_title or booking.service_preset or "Service"

    _box_title(c, "Leistung:", margin_x, y); y -= 12
    _label_value(c, "Bezeichnung:", service_line, margin_x, y); y -= 14
    _label_value(c, "Wunschtermin:", booking.preferred_datetime, margin_x, y); y -= 20

    rate = float(getattr(settings, 'HOURLY_RATE_EUR', 18))
    tax_rate = float(getattr(settings, 'TAX_RATE_PERCENT', 19.0))
    tax_mode = getattr(settings, 'TAX_MODE', 'add')
    min_hours = float(getattr(settings, 'MIN_BILLABLE_HOURS', 1.0))
    step_min = int(getattr(settings, 'BILLING_ROUNDING_MINUTES', 30))
    bill_travel_time = bool(getattr(settings, 'BILL_TRAVEL_TIME', True))
    pauschale = float(getattr(settings, 'ANFAHRT_PAUSCHALE_EUR', 10.0))
    per_km = float(getattr(settings, 'PER_KM_EUR', 0.5))
    included_km = float(getattr(settings, 'INCLUDED_KM', 5.0))

    hrs = float(booking.hours) if getattr(booking, 'hours', None) is not None else None
    travel_km = float(booking.travel_km) if getattr(booking, 'travel_km', None) is not None else 0.0
    travel_min = int(booking.travel_minutes) if getattr(booking, 'travel_minutes', None) is not None else 0

    def _hrs_label(h):
        total_min = int(round(h * 60))
        hh = total_min // 60
        mm = total_min % 60
        if hh >= 1 and mm > 0:
            return f"{_fmt_de(h)} h ({hh}:{mm:02d} Std.)"
        elif hh == 0 and mm > 0:
            return f"{_fmt_de(h)} h ({mm} Min.)"
        else:
            return f"{_fmt_de(h)} h"

    actual_hours = hrs if hrs is not None else None
    travel_hours = (travel_min / 60.0) if bill_travel_time and travel_min > 0 else 0.0

    if actual_hours is not None:
        total_minutes_raw = int(round(actual_hours * 60.0)) + int(round(travel_hours * 60.0))
        total_minutes_rounded = _round_up_minutes(total_minutes_raw, step_min) if step_min > 0 else total_minutes_raw
        billed_hours = max(total_minutes_rounded / 60.0, min_hours)
    else:
        billed_hours = None

    extra_km = max(travel_km - included_km, 0.0)
    travel_cost_eur = (extra_km * per_km) + (pauschale if (travel_km > 0 or travel_min > 0) else 0.0)

    _box_title(c, "Abrechnung / Zahlung:", margin_x, y); y -= 12

    if actual_hours is None:
        _label_value(c, "Arbeitszeit (tatsächlich):", "________ h", margin_x, y); y -= 14
        _label_value(c, "Anfahrtzeit:", f"{travel_min} Min." if travel_min else "—", margin_x, y); y -= 14
        _label_value(c, "Abrechnungszeit:", "________ h", margin_x, y); y -= 12
        note_parts = []
        if min_hours and min_hours > 0:
            note_parts.append(f"min. {int(round(min_hours))} h")
        if step_min and step_min > 0:
            note_parts.append(f"Rundung {step_min} Min.")
        if note_parts:
            c.setFont("Helvetica", 8); c.setFillColor(colors.grey)
            c.drawString(margin_x + 40*mm, y, " · ".join(note_parts))
            c.setFillColor(colors.black); y -= 10
        else:
            y -= 2
    else:
        _label_value(c, "Arbeitszeit (tatsächlich):", _hrs_label(actual_hours), margin_x, y); y -= 14
        _label_value(c, "Anfahrtzeit:", (f"{travel_min} Min." if travel_min else "—") + (" (berechnet)" if bill_travel_time and travel_min else ""), margin_x, y); y -= 14
        _label_value(c, "Abrechnungszeit:", _hrs_label(billed_hours), margin_x, y); y -= 12

    _label_value(c, "Stundensatz:", f"{_fmt_de(rate)} € / Stunde", margin_x, y); y -= 14

    if actual_hours is None:
        _label_value(c, "Arbeitsleistung (netto):", "________ €", margin_x, y); y -= 14
    else:
        work_subtotal = billed_hours * rate
        _label_value(c, "Arbeitsleistung (netto):", f"{_fmt_de(work_subtotal)} €", margin_x, y); y -= 14

    anfahrt_text = []
    if pauschale: anfahrt_text.append(f"Pauschale { _fmt_de(pauschale) } €")
    if per_km:    anfahrt_text.append(f"{_fmt_de(per_km)} €/km (inkl. {_fmt_de(included_km)} km)")
    _label_value(c, "Anfahrtkosten:", " + ".join(anfahrt_text) if anfahrt_text else "—", margin_x, y); y -= 14
    _label_value(c, "Anfahrt (berechnet):", f"{_fmt_de(travel_cost_eur)} €" if (travel_km or travel_min) else "—", margin_x, y); y -= 14

    rate_val = rate
    if actual_hours is None:
        _label_value(c, "Zwischensumme (netto):", "________ €", margin_x, y); y -= 14
        if tax_mode == 'add':
            _label_value(c, f"MwSt ({_fmt_de(tax_rate)}%):", "________ €", margin_x, y); y -= 14
            _label_value(c, "Gesamtbetrag (brutto):", "________ €", margin_x, y); y -= 18
        else:
            _label_value(c, f"Steuerabzug ({_fmt_de(tax_rate)}%):", "________ €", margin_x, y); y -= 14
            _label_value(c, "Auszahlungsbetrag (netto):", "________ €", margin_x, y); y -= 18
    else:
        subtotal = (billed_hours * rate_val) + travel_cost_eur
        tax_amount = subtotal * (tax_rate / 100.0)
        if tax_mode == 'add':
            total = subtotal + tax_amount
            _label_value(c, "Zwischensumme (netto):", f"{_fmt_de(subtotal)} €", margin_x, y); y -= 14
            _label_value(c, f"MwSt ({_fmt_de(tax_rate)}%):", f"{_fmt_de(tax_amount)} €", margin_x, y); y -= 14
            _label_value(c, "Gesamtbetrag (brutto):", f"{_fmt_de(total)} €", margin_x, y); y -= 18
        else:
            total = max(subtotal - tax_amount, 0.0)
            _label_value(c, "Zwischensumme:", f"{_fmt_de(subtotal)} €", margin_x, y); y -= 14
            _label_value(c, f"Steuerabzug ({_fmt_de(tax_rate)}%):", f"-{_fmt_de(tax_amount)} €", margin_x, y); y -= 14
            _label_value(c, "Auszahlungsbetrag (netто):", f"{_fmt_de(total)} €", margin_x, y); y -= 18

    pay_line = "[  ] Barzahlung   [  ] Karte   [  ] Überweisung"
    try:
        method = getattr(booking, "payment_method", "")
        if method == "cash":
            pay_line = "[X] Barzahlung   [  ] Karte   [  ] Überweisung"
        elif method == "card":
            pay_line = "[  ] Barzahlung   [X] Karte   [  ] Überweisung"
        elif method == "bank":
            pay_line = "[  ] Barzahlung   [  ] Karte   [X] Überweisung"
    except Exception:
        pass

    c.setFont("Helvetica", 10)
    c.drawString(margin_x, y, "Zahlungsart:")
    c.drawString(margin_x + 30*mm, y, pay_line)
    y -= 16
    _label_value(c, "Betrag erhalten:", "________ €", margin_x, y); y -= 20

    _box_title(c, "Bestätigung des Kunden:", margin_x, y); y -= 12
    para = ("Ich bestätige, dass die oben aufgeführten Leistungen ordnungsgemäß "
            "und vollständig erbracht wurden.")
    y = _multi_line(c, para, margin_x, y, max_width_mm=175, leading=14); y -= 10

    c.setFont("Helvetica", 10)
    c.drawString(margin_x, y, "Ort / Datum:")
    c.line(margin_x + 26*mm, y - 2, margin_x + 90*mm, y - 2)

    c.drawString(margin_x, y - 22, "Unterschrift Kunde:")
    c.line(margin_x + 38*mm, y - 24, margin_x + 90*mm, y - 24)

    c.drawString(margin_x, y - 44, "Unterschrift Handwerker:")
    c.line(margin_x + 52*mm, y - 46, margin_x + 90*mm, y - 46)

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.grey)
    c.drawRightString(width - margin_x, 12*mm, "AleksHome Service • https://example.com")

    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes

@user_passes_test(is_staff)
def booking_pdf(request, pk: int):
    booking = get_object_or_404(Booking, pk=pk)
    filename = f"Leistungsnachweis_{booking.pk}.pdf"
    pdf_bytes = _render_booking_pdf_bytes(booking)
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{iri_to_uri(filename)}"'
    response.write(pdf_bytes)
    return response


@user_passes_test(is_staff)
@require_POST
def owner_booking_delete(request, pk):
    b = get_object_or_404(Booking, pk=pk)
    b.delete()
    messages.success(request, _("Auftrag wurde gelöscht."))
    return redirect('owner_dashboard')


def _compute_booking_total(b) -> float | None:
    rate = float(getattr(settings, 'HOURLY_RATE_EUR', 18))
    tax_rate = float(getattr(settings, 'TAX_RATE_PERCENT', 19.0))
    tax_mode = getattr(settings, 'TAX_MODE', 'add')
    min_hours = float(getattr(settings, 'MIN_BILLABLE_HOURS', 1.0))
    step_min = int(getattr(settings, 'BILLING_ROUNDING_MINUTES', 30))
    bill_travel_time = bool(getattr(settings, 'BILL_TRAVEL_TIME', True))
    pauschale = float(getattr(settings, 'ANFAHRT_PAUSCHALE_EUR', 10.0))
    per_km = float(getattr(settings, 'PER_KM_EUR', 0.5))
    included_km = float(getattr(settings, 'INCLUDED_KM', 5.0))

    def _round_up_minutes(total_minutes: int, step_minutes: int) -> int:
        if step_minutes <= 0:
            return total_minutes
        return ((total_minutes + step_minutes - 1) // step_minutes) * step_minutes

    hrs = float(b.hours) if getattr(b, 'hours', None) is not None else None
    travel_km = float(b.travel_km) if getattr(b, 'travel_km', None) is not None else 0.0
    travel_min = int(b.travel_minutes) if getattr(b, 'travel_minutes', None) is not None else 0

    if hrs is None:
        return None

    travel_hours = (travel_min / 60.0) if bill_travel_time and travel_min > 0 else 0.0
    total_minutes_raw = int(round(hrs * 60.0)) + int(round(travel_hours * 60.0))
    total_minutes_rounded = _round_up_minutes(total_minutes_raw, step_min) if step_min > 0 else total_minutes_raw
    billed_hours = max(total_minutes_rounded / 60.0, min_hours)

    work_subtotal = billed_hours * rate
    extra_km = max(travel_km - included_km, 0.0)
    travel_cost_eur = (extra_km * per_km) + (pauschale if (travel_km > 0 or travel_min > 0) else 0.0)

    subtotal = work_subtotal + travel_cost_eur
    tax_amount = subtotal * (tax_rate / 100.0)
    total = (subtotal + tax_amount) if tax_mode == 'add' else max(subtotal - tax_amount, 0.0)
    return round(total, 2)


@user_passes_test(is_staff)
@require_POST
def sumup_charge(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    booking_id = data.get("booking_id")
    if not booking_id:
        return JsonResponse({"ok": False, "error": "missing_booking_id"}, status=400)

    b = get_object_or_404(Booking, pk=booking_id)

    amount = data.get("amount")
    if amount is None:
        amount = _compute_booking_total(b)
        if amount is None:
            return JsonResponse({"ok": False, "error": "hours_not_set"}, status=400)

    base = getattr(settings, "SUMUP_API_BASE", "https://api.sumup.com")
    api_key = getattr(settings, "SUMUP_API_KEY", "")
    merchant = getattr(settings, "SUMUP_MERCHANT_CODE", "")
    reader_id = getattr(settings, "SUMUP_SOLO_READER_ID", "")
    if not (api_key and merchant and reader_id):
        return JsonResponse({"ok": False, "error": "sumup_not_configured"}, status=500)

    checkout_reference = f"BOOKING-{b.pk}-{uuid.uuid4().hex[:8]}"

    url = f"{base}/v0.1/merchants/{merchant}/readers/{reader_id}/checkout"
    payload = {
        "description": f"AleksHome Auftrag #{b.pk}",
        "checkout_reference": checkout_reference,
        # "amount": amount, "currency": "EUR"
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        r.raise_for_status()
        resp = r.json()
        client_tx = (resp.get("data") or {}).get("client_transaction_id")
        if not client_tx:
            return JsonResponse({"ok": False, "error": "no_client_transaction_id", "detail": resp}, status=502)
    except requests.RequestException as e:
        return JsonResponse({"ok": False, "error": "sumup_api_error", "detail": str(e)}, status=502)

    b.payment_amount = amount
    b.payment_reference = checkout_reference
    b.payment_tx = client_tx
    b.payment_status = "pending"
    b.payment_method = "card"
    b.save(update_fields=["payment_amount", "payment_reference", "payment_tx", "payment_status", "payment_method"])

    return JsonResponse({"ok": True, "client_transaction_id": client_tx, "amount": amount})


@csrf_exempt
@require_POST
def sumup_webhook(request):
    secret = getattr(settings, "SUMUP_WEBHOOK_SECRET", "")
    if not secret:
        return JsonResponse({"ok": False, "error": "webhook_secret_not_set"}, status=500)

    raw = request.body
    sig = request.headers.get("x-payload-signature") or request.headers.get("X-Payload-Signature")
    if not sig:
        return JsonResponse({"ok": False, "error": "missing_signature"}, status=400)

    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    if not hmac.compare_digest(expected, sig):
        return JsonResponse({"ok": False, "error": "invalid_signature"}, status=400)

    try:
        event = json.loads(raw.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    reference = event.get("reference") or event.get("checkout_reference")
    status_payload = (event.get("status") or "").lower()

    booking = None
    if reference and str(reference).startswith("BOOKING-"):
        try:
            bid = int(str(reference).split("-")[1])
            booking = Booking.objects.filter(pk=bid).first()
        except Exception:
            booking = None

    status_final = None
    if status_payload in ("paid", "successful", "success", "paid_out"):
        status_final = "paid"
    elif status_payload in ("failed", "cancelled"):
        status_final = "failed"

    if booking:
        if status_final == "paid":
            booking.payment_status = "paid"
            booking.payment_method = "card"
            booking.paid_at = timezone.now()
            if booking.status != 'done':
                booking.status = 'done'
            booking.save(update_fields=["payment_status", "payment_method", "paid_at", "status"])

            if booking.email:
                try:
                    subject = f"Leistungsnachweis – Auftrag #{booking.pk}"
                    body = (
                        "Guten Tag,\n\n"
                        "anbei erhalten Sie den Leistungsnachweis zu Ihrem Auftrag.\n"
                        "Vielen Dank für Ihr Vertrauen!\n\n"
                        "Mit freundlichen Grüßen\n"
                        "AleksHome Service"
                    )
                    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@example.com')
                    to = [booking.email]

                    email = EmailMessage(subject, body, from_email, to)
                    filename = f"Leistungsnachweis_{booking.pk}.pdf"
                    pdf_bytes = _render_booking_pdf_bytes(booking)
                    email.attach(filename, pdf_bytes, "application/pdf")

                    owner_copy = getattr(settings, 'OWNER_NOTIFICATION_EMAIL', '')
                    if owner_copy:
                        email.cc = [owner_copy]

                    email.send(fail_silently=True)
                except Exception:
                    pass
        elif status_final == "failed":
            booking.payment_status = "failed"
            booking.save(update_fields=["payment_status"])

    return JsonResponse({"ok": True})


@user_passes_test(is_staff)
@require_POST
def owner_booking_cash_pay(request, pk: int):
    b = get_object_or_404(Booking, pk=pk)

    raw_amount = (request.POST.get("amount") or "").replace(",", ".").strip()
    amount = None
    if raw_amount:
        try:
            amount = Decimal(raw_amount)
            if amount < 0:
                raise ValueError
        except Exception:
            messages.error(request, _("Ungültiger Betrag."))
            return redirect('owner_booking_detail', pk=pk)
    else:
        total = _compute_booking_total(b)
        if total is None:
            messages.error(request, _("Bitte erst Arbeitszeit/Anfahrt eintragen – Betrag unbekannt."))
            return redirect('owner_booking_detail', pk=pk)
        amount = Decimal(str(total))

    b.payment_status = "paid"
    b.payment_method = "cash"
    b.payment_amount = amount
    b.paid_at = timezone.now()
    if b.status != 'done':
        b.status = 'done'
    b.save(update_fields=["payment_status", "payment_method", "payment_amount", "paid_at", "status"])

    if b.email:
        try:
            subject = f"Leistungsnachweis – Auftrag #{b.pk}"
            body = (
                "Guten Tag,\n\n"
                "anbei erhalten Sie den Leistungsnachweis zu Ihrem Auftrag.\n"
                "Vielen Dank für Ihr Vertrauen!\n\n"
                "Mit freundlichen Grüßen\n"
                "AleksHome Service"
            )
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@example.com')
            to = [b.email]
            email = EmailMessage(subject, body, from_email, to)
            filename = f"Leistungsnachweis_{b.pk}.pdf"
            pdf_bytes = _render_booking_pdf_bytes(b)
            email.attach(filename, pdf_bytes, "application/pdf")
            owner_copy = getattr(settings, 'OWNER_NOTIFICATION_EMAIL', '')
            if owner_copy:
                email.cc = [owner_copy]
            email.send(fail_silently=True)
        except Exception:
            pass

    messages.success(request, _("Barzahlung erfasst."))
    return redirect('owner_booking_detail', pk=pk)


@user_passes_test(is_staff)
def owner_stats(request):
    from datetime import timedelta
    from django.utils import timezone as _tz

    field_names = {f.name for f in Booking._meta.get_fields()}
    has_payment = {'payment_status','payment_amount','paid_at'}.issubset(field_names)
    has_archiv = 'is_archived' in field_names

    total = Booking.objects.count()
    active = Booking.objects.filter(is_archived=False).count() if has_archiv else total
    archived = Booking.objects.filter(is_archived=True).count() if has_archiv else 0

    by_status = (
        Booking.objects.values('status')
        .annotate(c=Count('id'))
        .order_by()
    )
    status_map = {row['status']: row['c'] for row in by_status}

    paid_cnt = pending_cnt = failed_cnt = none_cnt = 0
    revenue_paid = Decimal("0.00")
    total_expected = Decimal("0.00")
    total_outstanding = Decimal("0.00")
    total_pending = Decimal("0.00")

    receivables = []
    now = _tz.now()
    year_ago = now - timedelta(days=365)
    monthly = []

    if not has_payment:
        qs = Booking.objects.all()
        if has_archiv:
            qs = qs.filter(is_archived=False)
        for b in qs:
            amt = _compute_booking_total(b)
            if amt is None:
                continue
            total_expected += Decimal(str(amt))
            receivables.append({
                "id": b.id, "created_at": b.created_at, "name": b.name, "city": b.city,
                "status": b.status, "payment_status": "—", "amount": Decimal(str(amt)),
            })
    else:
        base_qs = Booking.objects.all()
        if has_archiv:
            base_qs = base_qs.filter(is_archived=False)

        for b in base_qs:
            amt = _compute_booking_total(b)
            if amt is None:
                continue
            amt = Decimal(str(amt))
            total_expected += amt

            ps = (b.payment_status or 'none')
            if ps == 'paid':
                revenue_paid += (Decimal(str(b.payment_amount)) if b.payment_amount else amt)
            elif ps == 'pending':
                total_pending += (Decimal(str(b.payment_amount)) if b.payment_amount else amt)
                receivables.append({
                    "id": b.id, "created_at": b.created_at, "name": b.name, "city": b.city,
                    "status": b.status, "payment_status": "pending", "amount": amt
                })
            elif ps in ('failed', 'none'):
                total_outstanding += amt
                receivables.append({
                    "id": b.id, "created_at": b.created_at, "name": b.name, "city": b.city,
                    "status": b.status, "payment_status": ps, "amount": amt
                })

        paid_cnt = Booking.objects.filter(payment_status='paid').count()
        pending_cnt = Booking.objects.filter(payment_status='pending').count()
        failed_cnt = Booking.objects.filter(payment_status='failed').count()
        none_cnt = Booking.objects.filter(payment_status='none').count()

        monthly = (
            Booking.objects.filter(payment_status='paid', paid_at__gte=year_ago)
            .annotate(month=TruncMonth('paid_at'))
            .values('month')
            .annotate(amount=Sum('payment_amount'))
            .order_by('month')
        )

    def _order_key(r):
        rank = {"pending": 0, "none": 1, "failed": 2, "—": 1}.get(r["payment_status"], 1)
        return (rank, r["created_at"])
    receivables.sort(key=_order_key, reverse=True)

    bank = {
        "holder": getattr(settings, "BANK_ACCOUNT_HOLDER", ""),
        "name": getattr(settings, "BANK_NAME", ""),
        "iban": getattr(settings, "BANK_IBAN", ""),
        "bic": getattr(settings, "BANK_BIC", ""),
    }

    ctx = {
        'total': total,
        'active': active,
        'archived': archived,
        'status_map': status_map,

        'revenue': revenue_paid,
        'total_expected': total_expected,
        'total_outstanding': total_outstanding,
        'total_pending': total_pending,

        'paid_cnt': paid_cnt,
        'pending_cnt': pending_cnt,
        'failed_cnt': failed_cnt,
        'none_cnt': none_cnt,

        'monthly': monthly,
        'receivables': receivables,
        'bank': bank,
        'has_payment': has_payment,
    }
    return render(request, 'owner_stats.html', ctx)
