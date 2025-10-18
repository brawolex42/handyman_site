from __future__ import annotations

import os
import unicodedata
from datetime import datetime
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.text import slugify

User = get_user_model()

# ---------- helpers ----------

def _clean_filename(filename: str) -> str:
    base, ext = os.path.splitext(filename)
    base = unicodedata.normalize('NFKD', base)
    base = "".join(ch for ch in base if not unicodedata.combining(ch))
    base = slugify(base) or "upload"
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{base}_{stamp}{ext.lower()}"

def booking_photo_upload_to(instance: "Booking", filename: str) -> str:
    safe = _clean_filename(filename)
    return os.path.join("booking_photos", safe)

# ---------- models ----------

class Service(models.Model):
    CATEGORY_CHOICES = [
        ("appliance", "Appliance / Geräteinstallation"),
        ("electric", "Electric / Elektrik"),
        ("furniture", "Furniture / Möbel"),
        ("plumbing", "Plumbing / Sanitär"),
        ("other", "Other / Sonstiges"),
    ]

    title = models.CharField(max_length=200)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    description = models.TextField(blank=True)
    price_from = models.DecimalField(max_digits=6, decimal_places=2, default=18)
    unit = models.CharField(max_length=20, default="Std.")
    duration_estimate = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)

    slug = models.SlugField(max_length=220, unique=True, blank=True)
    seo_title = models.CharField(max_length=255, blank=True)
    seo_description = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title) or "service"
            slug = base
            i = 1
            while Service.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)


class Booking(models.Model):
    STATUS_CHOICES = [
        ("new", "Neu"),
        ("confirmed", "Bestätigt"),
        ("done", "Erledigt"),
        ("cancelled", "Storniert"),
    ]

    PAYMENT_STATUS_CHOICES = [
        ("none", "—"),
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("failed", "Failed"),
    ]
    PAYMENT_METHOD_CHOICES = [
        ("", "—"),
        ("card", "Karte"),
        ("cash", "Bar"),
        ("bank", "Überweisung"),
    ]

    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    service = models.ForeignKey(Service, null=True, blank=True, on_delete=models.SET_NULL)
    service_preset = models.CharField(max_length=50, blank=True)

    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=50)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100, default="Potsdam")

    preferred_datetime = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)
    photo = models.ImageField(upload_to=booking_photo_upload_to, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Биллинг
    hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Gearbeitete Stunden")
    travel_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True,
                                    help_text="Gefahrene Kilometer (einfach)")
    travel_minutes = models.PositiveIntegerField(null=True, blank=True,
                                                 help_text="Fahrzeit in Minuten (hin+zurück)")

    # Архив
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)

    # Оплата
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default="none")
    payment_amount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    payment_tx = models.CharField(max_length=100, blank=True)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Buchung"
        verbose_name_plural = "Buchungen"

    def __str__(self):
        return f"#{self.pk} {self.name} — {self.service.title if self.service else self.service_preset or 'Service'}"

    # Удобные методы
    def archive(self):
        from django.utils import timezone
        self.is_archived = True
        self.archived_at = timezone.now()
        self.save(update_fields=["is_archived", "archived_at"])

    def restore(self):
        self.is_archived = False
        self.archived_at = None
        self.save(update_fields=["is_archived", "archived_at"])


class Review(models.Model):
    customer_name = models.CharField(max_length=150)
    rating = models.IntegerField()
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bewertung"
        verbose_name_plural = "Bewertungen"

    def __str__(self):
        return f"{self.customer_name} ({self.rating}/5)"
