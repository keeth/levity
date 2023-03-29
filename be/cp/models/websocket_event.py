from django.db import models

from cp.models.charge_point import ChargePoint
from cp.types.websocket_event_type import WebsocketEventType


class WebsocketEvent(models.Model):
    charge_point = models.ForeignKey(ChargePoint, null=True, on_delete=models.CASCADE)
    type = models.CharField(max_length=64, choices=WebsocketEventType.choices())
    timestamp = models.DateTimeField()

    class Meta:
        unique_together = ("actor", "unique_id")
