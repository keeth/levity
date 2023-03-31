from django.db import models

from ocpp.models.charge_point import ChargePoint
from ocpp.models.transaction import Transaction
from ocpp.types.actor_type import ActorType
from ocpp.types.action import Action
from ocpp.types.error_code import ErrorCode
from ocpp.types.message_type import MessageType
from ocpp.utils.model.timestamped import Timestamped


class Message(Timestamped):
    charge_point = models.ForeignKey(ChargePoint, null=True, on_delete=models.CASCADE)
    transaction = models.ForeignKey(Transaction, null=True, on_delete=models.CASCADE)
    message_type = models.IntegerField()
    unique_id = models.CharField(max_length=128)
    actor = models.CharField(max_length=64, choices=ActorType.choices())
    action = models.CharField(
        max_length=64, choices=Action.choices(), null=True, blank=True
    )
    error_code = models.CharField(
        max_length=64, choices=ErrorCode.choices(), null=True, blank=True
    )
    error_description = models.CharField(max_length=255, null=True, blank=True)
    data = models.JSONField()
    reply = models.ForeignKey("ocpp.Message", null=True, on_delete=models.SET_NULL)

    class Meta:
        unique_together = ("actor", "unique_id")

    def transaction_from_data(self):
        transaction = Transaction.objects.get(id=self.data["transactionId"])
        if not self.transaction:
            self.transaction = transaction
            self.save(update_fields=["transaction"])
        return transaction

    def to_ocpp(self):
        message_type = MessageType(self.message_type)
        if message_type == MessageType.call:
            ocpp_message = [
                int(self.message_type),
                self.unique_id,
                str(self.action),
                self.data,
            ]
        elif message_type == MessageType.call_result:
            ocpp_message = [
                int(self.message_type),
                self.unique_id,
                self.data,
            ]
        elif message_type == MessageType.call_error:
            ocpp_message = [
                int(self.message_type),
                self.unique_id,
                str(self.error_code),
                self.error_description or "",
                self.data,
            ]
        else:
            raise ValueError("Unknown message type {}".format(self.message_type))

        return dict(id=self.charge_point.id, message=ocpp_message)

    @staticmethod
    def from_occp(charge_point: ChargePoint, ocpp_message: dict):
        message_type = MessageType(ocpp_message["message"][0])

        action = None
        error_code = None
        error_description = None
        if message_type == MessageType.call:
            (_, unique_id, action, *rest) = ocpp_message["message"]
        elif message_type == MessageType.call_result:
            (_, unique_id, *rest) = ocpp_message["message"]
        elif message_type == MessageType.call_error:
            (_, unique_id, error_code, error_description, *rest) = ocpp_message[
                "message"
            ]
        else:
            raise ValueError("Unknown message type {}".format(message_type))

        return Message.objects.create(
            charge_point=charge_point,
            message_type=message_type,
            unique_id=unique_id,
            actor=ActorType.charge_point,
            action=Action(action) if action else None,
            error_code=ErrorCode(error_code) if error_code else None,
            error_description=error_description,
            data=rest[0] if rest else None,
        )
