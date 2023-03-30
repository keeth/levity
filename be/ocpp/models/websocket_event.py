from django.db import models

from ocpp.models.charge_point import ChargePoint
from ocpp.types.websocket_event_type import WebsocketEventType


class WebsocketEvent(models.Model):
    charge_point = models.ForeignKey(ChargePoint, null=True, on_delete=models.CASCADE)
    type = models.CharField(max_length=64, choices=WebsocketEventType.choices())
    timestamp = models.DateTimeField()
