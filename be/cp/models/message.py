from django.db import models

from cp.models.charge_point import ChargePoint
from cp.models.transaction import Transaction
from cp.types.actor_type import ActorType
from cp.types.action import Action
from cp.utils.model.timestamped import Timestamped


class Message(Timestamped):
    charge_point = models.ForeignKey(ChargePoint, null=True, on_delete=models.CASCADE)
    transaction = models.ForeignKey(Transaction, null=True, on_delete=models.CASCADE)
    message_type = models.IntegerField()
    unique_id = models.CharField(max_length=128)
    actor = models.CharField(max_length=64, choices=ActorType.choices())
    action = models.CharField(
        max_length=64, choices=Action.choices(), null=True, blank=True
    )
    data = models.JSONField()
    reply = models.ForeignKey("cp.Message", on_delete=models.SET_NULL)

    class Meta:
        unique_together = ("actor", "unique_id")

    def transaction_from_data(self):
        transaction = Transaction.objects.get(id=self.data["transactionId"])
        if not self.transaction:
            self.transaction = transaction
            self.save(update_fields=["transaction"])
        return transaction
