from cp.models.message import Message
from cp.services.handler.ocpp.base import OCPPMessageHandler


class StopTransactionHandler(OCPPMessageHandler):
    def handle(self, message: Message) -> Message:

        return self._reply(
            message,
            dict(),
        )
