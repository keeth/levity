from ocpp.models.meter_value import MeterValue
from ocpp.services.ocpp.base import OCPPMiddleware, OCPPRequest, OCPPResponse
from ocpp.types.authorization_status import AuthorizationStatus
from ocpp.types.stop_reason import StopReason


class StopTransactionMiddleware(OCPPMiddleware):
    def handle(self, req: OCPPRequest) -> OCPPResponse:
        message = req.message
        transaction = message.transaction_from_data()
        transaction.stop(StopReason(message.data["reason"]), message.data["meterStop"])
        transaction_data = message.data.get("transactionData") or []
        for meter_value in transaction_data:
            for sampled_value in meter_value["sampledValue"]:
                MeterValue.create_from_json(
                    transaction, meter_value["timestamp"], sampled_value, is_final=True
                )
        res = self.next.handle(req)
        res.message.data.update(
            dict(idTagInfo=dict(status=AuthorizationStatus.Accepted)),
        )
        res.transaction = transaction
        return res
