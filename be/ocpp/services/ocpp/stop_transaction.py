from django.utils import timezone

from ocpp.models.meter_value import MeterValue
from ocpp.services.ocpp.base import OCPPMiddleware, OCPPRequest, OCPPResponse
from ocpp.types.authorization_status import AuthorizationStatus
from ocpp.types.stop_reason import StopReason


class StopTransactionHandler(OCPPMiddleware):
    def handle(self, req: OCPPRequest) -> OCPPResponse:
        message = req.message
        transaction = message.transaction_from_data()
        transaction.meter_stop = message.data["meterStop"]
        transaction.stop_reason = StopReason(message.data["reason"])
        transaction.stopped_at = timezone.now()
        transaction.save(update_fields=["meter_stop", "stop_reason", "stopped_at"])
        transaction_data = message.data.get("transactionData") or []
        for value in transaction_data:
            MeterValue.create_from_json(transaction, value)

        res = self.next.handle(req)
        res.message.data.update(
            dict(idTagInfo=dict(status=AuthorizationStatus.Accepted)),
        )
        res.transaction = transaction
        return res
