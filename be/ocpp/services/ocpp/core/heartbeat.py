from ocpp.services.ocpp.base import OCPPMiddleware, OCPPRequest, OCPPResponse
from ocpp.utils.date import utc_now


class MeterValuesMiddleware(OCPPMiddleware):
    def handle(self, req: OCPPRequest) -> OCPPResponse:
        charge_point = req.message.charge_point
        charge_point.last_heartbeat_at = utc_now()
        charge_point.save(update_fields=["last_heartbeat_at"])
        return self.next.handle(req)
