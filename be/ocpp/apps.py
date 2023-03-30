from django.apps import AppConfig


class OcppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ocpp"

    def ready(self):
        super().ready()
        from ocpp.utils.settings import load_ocpp_middleware

        load_ocpp_middleware()
