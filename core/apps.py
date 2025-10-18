import logging
import os
from django.apps import AppConfig

log = logging.getLogger(__name__)

class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # В dev runserver запускает прелоадер + рабочий процесс → подключаем сигналы только в рабочем
        if os.environ.get("RUN_MAIN") == "true" or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            import core.signals  # noqa: F401
            log.info("Сигналы core подключены (RUN_MAIN)")
        else:
            log.info("Сигналы core пропущены (не RUN_MAIN)")
