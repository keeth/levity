from django.utils import timezone

from cp.models.message import Message
from cp.models.meter_value import MeterValue
from cp.models.transaction import Transaction
from cp.services.handler.ocpp.base import OCPPMessageHandler
from cp.types.authorization_status import AuthorizationStatus
from cp.types.stop_reason import StopReason


class StopTransactionHandler(OCPPMessageHandler):
    def handle(self, message: Message) -> Message:
        transaction = message.transaction_from_data()
        transaction.meter_stop = message.data["meterStop"]
        transaction.stop_reason = StopReason(message.data["reason"])
        transaction.stopped_at = timezone.now()
        transaction.save(update_fields=["meter_stop", "stop_reason", "stopped_at"])
        transaction_data = message.data.get("transactionData") or []
        for value in transaction_data:
            MeterValue.create_from_json(transaction, value)

        return self._reply(
            message,
            dict(idTagInfo=dict(status=AuthorizationStatus.Accepted)),
        )
