from django.core.management.base import BaseCommand
from core.models import Service
from collections import defaultdict

GERMAN = [
    # title, category, description, price_from, unit, duration_estimate
    ("Geräteinstallation",         "appliance",  "Waschmaschine, Spülmaschine, TV an die Wand.",             18, "Std.", "1–2 Std."),
    ("Stromproblem beheben",       "electric",   "Steckdosen/Schalter/Lampen tauschen, kleine Reparaturen.", 18, "Std.", "1–2 Std."),
    ("Möbel montieren",            "furniture",  "IKEA u.a., Schränke, Tische, Regale.",                      18, "Std.", "2–3 Std."),
    ("Möbel tragen/umstellen",     "furniture",  "Sicherer Transport innerhalb der Wohnung.",                18, "Std.", "1–2 Std."),
    ("Grundstück reinigen",        "other",      "Hof, Treppenhaus, Garage, Entsorgung von Kleinmüll.",       18, "Std.", "1–3 Std."),
    ("Sanitär: kleine Reparatur",  "plumbing",   "Tropfen, Siphon, Mischbatterie.",                           18, "Std.", "1–2 Std."),
]

class Command(BaseCommand):
    help = "Deduplicate services by category and set German titles/descriptions."

    def handle(self, *args, **options):
        # 1) удалить дубли по категории, оставить самый ранний
        groups = defaultdict(list)
        for s in Service.objects.all().order_by('id'):
            groups[s.category].append(s)

        removed = 0
        for cat, items in groups.items():
            keep = items[0]
            for extra in items[1:]:
                extra.delete()
                removed += 1

        # 2) выставить немецкие значения
        created = 0
        updated = 0
        for title, cat, desc, price, unit, dur in GERMAN:
            qs = Service.objects.filter(category=cat)
            if qs.exists():
                obj = qs.first()
                updated += 1
            else:
                obj = Service(category=cat)
                created += 1
            obj.title = title
            obj.description = desc
            obj.price_from = price
            obj.unit = unit
            obj.duration_estimate = dur
            obj.is_active = True
            obj.save()

        self.stdout.write(self.style.SUCCESS(
            f"Done. Removed duplicates: {removed}, updated: {updated}, created: {created}"
        ))
