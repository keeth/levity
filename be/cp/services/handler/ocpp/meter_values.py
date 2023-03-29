from cp.models.message import Message
from cp.models.meter_value import MeterValue
from cp.services.handler.ocpp.base import OCPPMessageHandler


class MeterValuesHandler(OCPPMessageHandler):
    def handle(self, message: Message) -> Message:
        transaction = message.transaction_from_data()
        for value in message.data["meterValue"]:
            MeterValue.create_from_json(transaction, value)
        return self._reply(
            message,
            {},
        )
