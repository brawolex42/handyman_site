# core/migrations/0003_service_slug_and_seo.py
from django.db import migrations, models
from django.utils.text import slugify

def populate_service_slugs(apps, schema_editor):
    Service = apps.get_model('core', 'Service')
    for svc in Service.objects.all().order_by('id'):
        base = slugify(svc.title) or f"service-{svc.id}"
        slug = base
        i = 2
        # гарантируем уникальность среди уже имеющихся значений
        while Service.objects.filter(slug=slug).exclude(pk=svc.pk).exists():
            slug = f"{base}-{i}"
            i += 1
        svc.slug = slug
        svc.save(update_fields=['slug'])

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_booking_user_and_status'),  # если у тебя другой предыдущий номер — поправь тут
    ]

    operations = [
        # 1) добавляем поля (slug пока допускает null, unique не ставим)
        migrations.AddField(
            model_name='service',
            name='slug',
            field=models.SlugField(max_length=220, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='service',
            name='seo_title',
            field=models.CharField(max_length=255, blank=True),
        ),
        migrations.AddField(
            model_name='service',
            name='seo_description',
            field=models.CharField(max_length=300, blank=True),
        ),

        # 2) заполняем slug для существующих записей
        migrations.RunPython(populate_service_slugs, migrations.RunPython.noop),

        # 3) ужесточаем ограничения: уникальный, без null
        migrations.AlterField(
            model_name='service',
            name='slug',
            field=models.SlugField(max_length=220, unique=True, blank=True),
        ),
    ]
