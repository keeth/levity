from ocpp.models.meter_value import MeterValue
from ocpp.services.ocpp.base import OCPPMiddleware, OCPPRequest, OCPPResponse
from ocpp.types.authorization_status import AuthorizationStatus
from ocpp.types.stop_reason import StopReason
from ocpp.utils.date import utc_now


class StopTransactionMiddleware(OCPPMiddleware):
    def handle(self, req: OCPPRequest) -> OCPPResponse:
        message = req.message
        transaction = message.transaction_from_data()
        transaction.meter_stop = message.data["meterStop"]
        transaction.stop_reason = StopReason(message.data["reason"])
        transaction.stopped_at = utc_now()
        transaction.save(update_fields=["meter_stop", "stop_reason", "stopped_at"])
        transaction_data = message.data.get("transactionData") or []
        for meter_value in transaction_data:
            for sampled_value in meter_value["sampledValue"]:
                MeterValue.create_from_json(
                    transaction, meter_value["timestamp"], sampled_value, is_final=True
                )
        charge_point = message.charge_point
        charge_point.last_tx_stop_at = utc_now()
        charge_point.save(update_fields=["last_tx_stop_at"])
        res = self.next.handle(req)
        res.message.data.update(
            dict(idTagInfo=dict(status=AuthorizationStatus.Accepted)),
        )
        res.transaction = transaction
        return res
