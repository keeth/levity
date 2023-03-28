from cp.models.message import Message
from cp.services.handler.ocpp.base import OCPPMessageHandler


class BootHandler(OCPPMessageHandler):
    def handle(self, message: Message):
        pass
