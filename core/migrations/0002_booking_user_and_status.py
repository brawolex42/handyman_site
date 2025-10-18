from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='user',
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='bookings'
            ),
        ),
        migrations.AddField(
            model_name='booking',
            name='status',
            field=models.CharField(
                max_length=32,
                choices=[
                    ("new", "Neu"),
                    ("cancelled_customer", "Storniert (Kunde)"),
                    ("cancelled_admin", "Storniert (Admin)"),
                    ("done", "Erledigt"),
                ],
                default='new'
            ),
        ),
        migrations.AddField(
            model_name='booking',
            name='cancelled_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
