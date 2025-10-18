# core/admin.py
from django.contrib import admin
from django.utils.text import slugify

from .models import Service, Booking

# Пытаемся импортировать Review безопасно: если модели нет — пропускаем регистрацию
try:
    from .models import Review  # type: ignore
except Exception:
    Review = None  # noqa: N816


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "price_from", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("title", "description")
    prepopulated_fields = {"slug": ("title",)}

    def save_model(self, request, obj, form, change):
        if hasattr(obj, "slug") and (not obj.slug):
            base = slugify(obj.title) or "service"
            slug = base
            i = 2
            while Service.objects.filter(slug=slug).exclude(pk=obj.pk).exists():
                slug = f"{base}-{i}"
                i += 1
            obj.slug = slug
        super().save_model(request, obj, form, change)


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "id", "created_at", "status", "name", "city",
        "service", "preferred_datetime", "user",
        "is_archived", "archived_at",
    )
    list_filter = ("status", "city", "service", "is_archived", "created_at")
    search_fields = ("name", "email", "phone", "address", "city", "description")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"

    fieldsets = (
        ("Allgemein", {"fields": ("status", "user", "is_archived", "archived_at")}),
        ("Kontakt & Adresse", {"fields": ("name", "email", "phone", "address", "city")}),
        ("Service", {"fields": ("service", "service_preset", "preferred_datetime", "description", "photo")}),
        ("Arbeits-/Fahrdaten", {"fields": ("hours", "travel_km", "travel_minutes")}),
        ("System", {"fields": ("created_at",)}),
    )

    actions = ("mark_done", "mark_cancelled", "mark_archive", "mark_restore")

    @admin.action(description="Als erledigt markieren")
    def mark_done(self, request, queryset):
        queryset.update(status="done")

    @admin.action(description="Als storniert markieren")
    def mark_cancelled(self, request, queryset):
        queryset.update(status="cancelled")

    @admin.action(description="In Archiv verschieben")
    def mark_archive(self, request, queryset):
        for b in queryset:
            try:
                b.archive()
            except Exception:
                pass

    @admin.action(description="Aus Archiv wiederherstellen")
    def mark_restore(self, request, queryset):
        for b in queryset:
            try:
                b.restore()
            except Exception:
                pass


# Регистрируем Review только если модель реально существует
if Review is not None:
    @admin.register(Review)
    class ReviewAdmin(admin.ModelAdmin):
        list_display = ("customer_name", "rating", "created_at")
        list_filter = ("rating", "created_at")
        search_fields = ("customer_name", "text")
