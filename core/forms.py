# core/forms.py
from datetime import datetime, date
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

# Безопасный импорт моделей: Review может отсутствовать (чтобы не падал импорт)
try:
    from .models import Service, Booking, Review  # type: ignore
except Exception:
    from .models import Service, Booking  # type: ignore
    Review = None  # type: ignore

INPUT_CLS = "w-full mt-1 px-3 py-2 border rounded-lg focus:outline-none focus:ring focus:ring-blue-200"
TEXTAREA_CLS = "w-full mt-1 px-3 py-2 border rounded-lg h-32 focus:outline-none focus:ring focus:ring-blue-200"
SELECT_CLS = "w-full mt-1 px-3 py-2 border rounded-lg bg-white focus:outline-none focus:ring focus:ring-blue-200"

# -----------------------------
# Регистрация (исправлено: e-mail Pflicht + is_active=False)
# -----------------------------
class RegisterForm(UserCreationForm):
    email = forms.EmailField(
        label="E-Mail",
        required=True,
        help_text=_("Geben Sie eine gültige E-Mail-Adresse an."),
        widget=forms.EmailInput(attrs={"class": INPUT_CLS})
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    # Немного косметики для виджетов
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = _("Benutzername")
        self.fields["password1"].label = _("Passwort")
        self.fields["password2"].label = _("Passwort wiederholen")
        for name in ("username", "password1", "password2"):
            self.fields[name].widget.attrs.update({"class": INPUT_CLS})

    def clean_username(self):
        u = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=u).exists():
            raise forms.ValidationError(_("Ein Benutzer mit diesem Benutzernamen existiert bereits."))
        return u

    def clean_email(self):
        e = self.cleaned_data["email"].strip()
        if User.objects.filter(email__iexact=e).exists():
            raise forms.ValidationError(_("Diese E-Mail wird bereits verwendet."))
        return e

    def save(self, commit=True):
        # UserCreationForm хэширует пароль сам
        user = super().save(commit=False)
        user.username = self.cleaned_data["username"].strip()
        user.email = self.cleaned_data["email"].strip()
        # ✅ Важно: до подтверждения e-mail аккаунт неактивен
        user.is_active = False
        if commit:
            user.save()
        return user

# --------------------------------
# Бронирование (как у тебя было)
# --------------------------------
PRESET_CHOICES_DE = [
    ("", "— aus der Liste wählen —"),
    ("appliance", "Geräteinstallation"),
    ("electric", "Stromproblem beheben"),
    ("furniture_asm", "Möbel montieren"),
    ("furniture_mov", "Möbel tragen/umstellen"),
    ("plumbing", "Sanitär: kleine Reparatur"),
    ("other", "Grundstück reinigen"),
]

class BookingForm(forms.ModelForm):
    service = forms.ModelChoiceField(
        label=_("Service"),
        queryset=Service.objects.filter(is_active=True).order_by("title"),
        required=False,
        empty_label="— aus der Liste wählen —",
        widget=forms.Select(attrs={"class": SELECT_CLS}),
    )

    service_preset = forms.ChoiceField(
        label=_("Oder eine beliebte Aufgabe wählen"),
        choices=PRESET_CHOICES_DE,
        required=False,
        widget=forms.Select(attrs={"class": SELECT_CLS}),
    )

    name = forms.CharField(label="Name", max_length=150,
                           widget=forms.TextInput(attrs={"class": INPUT_CLS}))
    email = forms.EmailField(label="E-Mail",
                             widget=forms.EmailInput(attrs={"class": INPUT_CLS}))
    phone = forms.CharField(label="Telefon", max_length=50,
                            widget=forms.TextInput(attrs={"class": INPUT_CLS}))
    address = forms.CharField(label="Adresse", max_length=255,
                              widget=forms.TextInput(attrs={"class": INPUT_CLS}))
    city = forms.CharField(label="Stadt", max_length=100, initial="Potsdam",
                           widget=forms.TextInput(attrs={"class": INPUT_CLS}))

    preferred_datetime = forms.CharField(
        label=_("Bevorzugtes Datum/Uhrzeit"),
        required=False,
        widget=forms.TextInput(attrs={
            "class": INPUT_CLS,
            "placeholder": "TT.MM.JJJJ HH:MM oder nur TT.MM.JJJJ / HH:MM",
        }),
        help_text=_("Beispiele: 15.11.2025 18:30 · 15.11.2025 · 13:00"),
    )

    description = forms.CharField(
        label=_("Beschreibung"),
        required=False,
        widget=forms.Textarea(attrs={
            "class": TEXTAREA_CLS,
            "placeholder": _("Kurz die Aufgabe beschreiben…"),
        }),
    )

    photo = forms.ImageField(
        label=_("Foto (optional)"),
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/*", "class": INPUT_CLS}),
    )

    class Meta:
        model = Booking
        fields = [
            "service",
            "service_preset",
            "name",
            "email",
            "phone",
            "address",
            "city",
            "preferred_datetime",
            "description",
            "photo",
        ]

    def clean_preferred_datetime(self):
        raw = (self.cleaned_data.get("preferred_datetime") or "").strip()
        if not raw:
            return ""
        norm = raw.replace(" Uhr", "").replace("  Uhr", "").replace("–", "-")
        if ":" not in norm and "." in norm and len(norm) <= 5:
            norm = norm.replace(".", ":")

        fmts_with_date = ["%d.%m.%Y %H:%M", "%d.%m.%Y %H", "%d.%m.%Y"]
        dt = None
        for f in fmts_with_date:
            try:
                dt = datetime.strptime(norm, f)
                if f == "%d.%m.%Y":
                    dt = dt.replace(hour=9, minute=0)
                if f == "%d.%m.%Y %H":
                    dt = dt.replace(minute=0)
                break
            except ValueError:
                continue

        if dt is None:
            fmts_time_only = ["%H:%M", "%H.%M", "%H"]
            for f in fmts_time_only:
                try:
                    t = datetime.strptime(norm, f).time()
                    today = date.today()
                    hh = t.hour
                    mm = t.minute if f != "%H" else 0
                    dt = datetime(today.year, today.month, today.day, hh, mm)
                    break
                except ValueError:
                    continue

        if dt is None:
            raise forms.ValidationError(_("Bitte ein gültiges Datum und Uhrzeit eingeben."))
        return dt.strftime("%Y-%m-%d %H:%M")

    def clean(self):
        cleaned = super().clean()
        service = cleaned.get("service")
        preset = cleaned.get("service_preset")
        description = (cleaned.get("description") or "").strip()

        if not service and not preset and not description:
            raise ValidationError(_("Bitte wählen Sie einen Service oder beschreiben Sie die Aufgabe kurz."))

        for field, msg in [
            ("name",   _("Bitte ausfüllen.")),
            ("email",  _("Bitte E-Mail angeben.")),
            ("phone",  _("Bitte Telefonnummer angeben.")),
            ("address", _("Bitte Adresse angeben.")),
            ("city",   _("Bitte Stadt angeben.")),
        ]:
            if not (cleaned.get(field) or "").strip():
                self.add_error(field, msg)

        return cleaned

# Reviews — как у тебя было (fallback, если модели нет)
if Review is not None:
    class ReviewForm(forms.ModelForm):
        customer_name = forms.CharField(label=_("Ihr Name"),
                                        widget=forms.TextInput(attrs={"class": INPUT_CLS}))
        rating = forms.IntegerField(label=_("Bewertung (1–5)"), min_value=1, max_value=5,
                                    widget=forms.NumberInput(attrs={"class": INPUT_CLS, "step": 1}))
        text = forms.CharField(label=_("Bewertungstext"),
                               widget=forms.Textarea(attrs={"class": TEXTAREA_CLS}))

        class Meta:
            model = Review
            fields = ["customer_name", "rating", "text"]
else:
    class ReviewForm(forms.Form):
        customer_name = forms.CharField(label=_("Ihr Name"),
                                        widget=forms.TextInput(attrs={"class": INPUT_CLS}))
        rating = forms.IntegerField(label=_("Bewertung (1–5)"), min_value=1, max_value=5,
                                    widget=forms.NumberInput(attrs={"class": INPUT_CLS, "step": 1}))
        text = forms.CharField(label=_("Bewertungstext"),
                               widget=forms.Textarea(attrs={"class": TEXTAREA_CLS}))
