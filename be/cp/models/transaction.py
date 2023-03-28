from django.db import models

from cp.models.charge_point import ChargePoint


class Transaction(models.Model):
    charge_point = models.ForeignKey(ChargePoint, on_delete=models.CASCADE)
    started_at = models.DateTimeField(null=True)
    stopped_at = models.DateTimeField(null=True)
    remote_started_at = models.DateTimeField(null=True)
    remote_stopped_at = models.DateTimeField(null=True)
    connector_id = models.CharField(max_length=64)
    id_tag = models.CharField(max_length=256)
