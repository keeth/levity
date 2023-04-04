from django.db import models

from ocpp.models.charge_point import ChargePoint
from ocpp.types.stop_reason import StopReason


class Transaction(models.Model):
    charge_point = models.ForeignKey(ChargePoint, on_delete=models.CASCADE)
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    connector_id = models.CharField(max_length=64)
    id_tag = models.CharField(max_length=256)
    meter_start = models.IntegerField(default=0)
    meter_stop = models.IntegerField(default=0)
    stop_reason = models.CharField(
        max_length=64, choices=StopReason.choices(), null=True, blank=True
    )
