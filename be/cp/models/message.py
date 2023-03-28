from django.db import models

from cp.models.charge_point import ChargePoint
from cp.models.transaction import Transaction
from cp.types.actor_type import ActorType
from cp.types.message_type import MessageType
from cp.utils.model.timestamped import Timestamped


class Message(Timestamped):
    charge_point = models.ForeignKey(ChargePoint, null=True, on_delete=models.CASCADE)
    transaction = models.ForeignKey(Transaction, null=True, on_delete=models.CASCADE)
    actor = models.CharField(max_length=128, choice=ActorType.choices())
    type = models.CharField(max_length=64, choices=MessageType.choices())
    message_id = models.CharField(max_length=128)
    body = models.JSONField()
