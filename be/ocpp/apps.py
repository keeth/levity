from django.apps import AppConfig

from ocpp.utils.settings import load_ocpp_handlers


class OcppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ocpp"

    def ready(self):
        super().ready()
        load_ocpp_handlers()
