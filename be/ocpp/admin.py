from django.contrib import admin

from ocpp.models import ChargePoint, Transaction


@admin.register(ChargePoint)
class ChargePointAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "status", "error_code", "is_connected")
    search_fields = (
        "id",
        "name",
    )
    readonly_fields = (
        "id",
        "status",
        "error_code",
        "is_connected",
        "vendor_error_code",
        "vendor_status_info",
        "vendor_status_id",
        "ws_queue",
        "hw_vendor",
        "hw_model",
        "hw_serial",
        "hw_firmware",
        "last_heartbeat_at",
        "last_boot_at",
        "last_connect_at",
        "last_tx_start_at",
        "last_tx_stop_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "charge_point",
        "started_at",
        "stopped_at",
        "meter_start",
        "meter_stop",
        "stop_reason",
    )
    search_fields = (
        "charge_point__id",
        "charge_point__name",
    )

    def has_add_permission(self, request, obj=None):
        return False
