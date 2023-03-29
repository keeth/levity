from ocpp.models.meter_value import MeterValue
from ocpp.services.ocpp.base import OCPPMiddleware, OCPPRequest, OCPPResponse


class MeterValuesMiddleware(OCPPMiddleware):
    def handle(self, req: OCPPRequest) -> OCPPResponse:
        message = req.message
        transaction = message.transaction_from_data()
        for value in message.data["meterValue"]:
            MeterValue.create_from_json(transaction, value)
        res = self.next.handle(req)
        res.transaction = transaction
        return res
