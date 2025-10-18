from django.core.management.base import BaseCommand
from core.models import Service

ITEMS = [
    ("Исправить электричество", "electric", "Замена розеток, выключателей, светильников."),
    ("Сантехника: мелкий ремонт", "plumbing", "Протечки, сифон, смеситель."),
    ("Сборка мебели", "furniture", "IKEA и др., шкафы, столы, полки."),
    ("Перенос/перестановка мебели", "furniture", "Аккуратный перенос внутри квартиры."),
    ("Уборка территории", "other", "Двор, подъезд, гараж, вынос мусора."),
    ("Установка бытовой техники", "appliance", "Стиралки, посудомойки, ТВ на стену."),
]

class Command(BaseCommand):
    help = "Создаёт стартовый список услуг (idempotent)."

    def handle(self, *args, **options):
        created = 0
        for title, category, desc in ITEMS:
            obj, was_created = Service.objects.get_or_create(
                title=title,
                defaults=dict(
                    category=category,
                    description=desc,
                    price_from=18,
                    unit="час",
                    duration_estimate="1–2 часа",
                    is_active=True,
                ),
            )
            created += 1 if was_created else 0
        self.stdout.write(self.style.SUCCESS(f"Готово. Новых услуг создано: {created}."))
