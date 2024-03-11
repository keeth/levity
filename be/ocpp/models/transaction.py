from django.db import models
from ocpp.models.charge_point import ChargePoint
from ocpp.types.stop_reason import StopReason
from ocpp.utils.date import utc_now


class Transaction(models.Model):
    charge_point = models.ForeignKey(ChargePoint, on_delete=models.CASCADE)
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    connector_id = models.CharField(max_length=64)
    id_tag = models.CharField(max_length=256)
    meter_start = models.IntegerField(default=0)
    meter_stop = models.IntegerField(default=0)
    meter_correction = models.IntegerField(default=0)
    stop_reason = models.CharField(
        max_length=64, choices=StopReason.choices(), null=True, blank=True
    )

    def stop(self, reason: StopReason, meter_stop: int):
        self.meter_stop = meter_stop
        self.stop_reason = reason
        self.stopped_at = utc_now()
        self.save(update_fields=["meter_stop", "stop_reason", "stopped_at"])
        charge_point = self.charge_point
        charge_point.last_tx_stop_at = utc_now()
        charge_point.save(update_fields=["last_tx_stop_at"])
