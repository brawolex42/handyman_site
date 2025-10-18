# handyman_site/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # Переключение языка
    path('i18n/', include('django.conf.urls.i18n')),

    # Все URL-ы приложения
    path('', include('core.urls')),
]

# Раздача медиа/статик в DEV
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # static() для STATIC_URL НЕ нужен, Django и так отдаёт из STATICFILES_DIRS в dev
