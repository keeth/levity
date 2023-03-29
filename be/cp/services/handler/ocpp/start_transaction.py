from cp.models.message import Message
from cp.models.transaction import Transaction
from cp.services.handler.ocpp.base import OCPPMessageHandler
from cp.types.authorization_status import AuthorizationStatus


class StartTransactionHandler(OCPPMessageHandler):
    def handle(self, message: Message) -> Message:
        transaction = Transaction.objects.create(
            charge_point=message.charge_point,
            connector_id=message.data["connectorId"],
            id_tag=message.data["idTag"],
        )
        return self._reply(
            message,
            dict(
                transactionId=transaction.id,
                idTagInfo=dict(status=AuthorizationStatus.Accepted),
            ),
        )
