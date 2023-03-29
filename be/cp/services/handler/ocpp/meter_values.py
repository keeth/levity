import dateutil.parser

from cp.models.message import Message
from cp.models.meter_value import MeterValue
from cp.models.transaction import Transaction
from cp.services.handler.ocpp.base import OCPPMessageHandler


class MeterValuesHandler(OCPPMessageHandler):
    def handle(self, message: Message) -> Message:
        transaction = Transaction.objects.get(id=message.data["transactionId"])
        for value in message.data["meterValue"]:
            MeterValue.objects.create(
                timestamp=dateutil.parser.isoparse(value["timestamp"]),
                transaction=transaction,
                context=value.get("context"),
                format=value.get("format"),
                location=value.get("location"),
                phase=value.get("phase"),
                measurand=value.get("measurand"),
                unit=value.get("unit"),
                value=value.get("value"),
            )
        return self._reply(
            message,
            {},
        )
