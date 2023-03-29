from ocpp.models.transaction import Transaction
from ocpp.services.ocpp.base import OCPPMiddleware, OCPPRequest, OCPPResponse
from ocpp.types.authorization_status import AuthorizationStatus


class StartTransactionMiddleware(OCPPMiddleware):
    def handle(self, req: OCPPRequest) -> OCPPResponse:
        message = req.message
        transaction = Transaction.objects.create(
            charge_point=message.charge_point,
            connector_id=message.data["connectorId"],
            id_tag=message.data["idTag"],
            meter_start=message.data["meterStart"],
        )
        message.transaction = transaction
        message.save(update_fields=["transaction"])
        res = self.next.handle(req)
        res.message.data.update(
            dict(
                transactionId=transaction.id,
                idTagInfo=dict(status=AuthorizationStatus.Accepted),
            )
        )
        res.transaction = transaction
        return res
