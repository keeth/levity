from django.db import models

from cp.types.charge_point_status import ChargePointStatus
from cp.utils.model.timestamped import Timestamped


class ChargePoint(Timestamped):
    id = models.CharField(max_length=128, primary_key=True)
    status = models.CharField(
        max_length=64, choices=ChargePointStatus.choices(), default="", blank=True
    )
    error_code = models.CharField(
        max_length=64, choices=ChargePointStatus.choices(), default="", blank=True
    )
    vendor_error_code = models.CharField(max_length=64, default="", blank=True)
    vendor_status_info = models.CharField(max_length=64, default="", blank=True)
    vendor_status_id = models.CharField(max_length=255, default="", blank=True)
    is_connected = models.BooleanField(default=False)
    last_heartbeat_at = models.DateTimeField(null=True)
    last_boot_at = models.DateTimeField(null=True)
    last_transaction_start_at = models.DateTimeField(null=True)
    last_transaction_stop_at = models.DateTimeField(null=True)
    ws_queue = models.CharField(max_length=256, default="", blank=True)
    hw_vendor = models.CharField(max_length=256, default="", blank=True)
    hw_model = models.CharField(max_length=256, default="", blank=True)
    hw_serial = models.CharField(max_length=256, default="", blank=True)
    hw_firmware = models.CharField(max_length=256, default="", blank=True)
