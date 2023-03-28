from cp.models.message import Message
from cp.models.transaction import Transaction
from cp.services.handler.ocpp.base import OCPPMessageHandler


class StartTransactionHandler(OCPPMessageHandler):
    def handle(self, message: Message):
        transaction = Transaction.objects.create(
            charge_point=message.charge_point,
            connector_id=message.data["connectorId"],
            id_tag=message.data["idTag"],
        )
        # TODO: send response
