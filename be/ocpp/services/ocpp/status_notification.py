from ocpp.models.message import Message
from ocpp.services.ocpp.base import OCPPMiddleware, OCPPRequest, OCPPResponse
from ocpp.types.charge_point_status import ChargePointStatus


class StatusNotificationHandler(OCPPMiddleware):
    def handle(self, req: OCPPRequest) -> OCPPResponse:
        message = req.message
        charge_point = message.charge_point
        charge_point.status = ChargePointStatus(message.data["status"])
        charge_point.vendor_error_code = message.data.get("vendorErrorCode") or ""
        charge_point.vendor_status_info = message.data.get("info") or ""
        charge_point.vendor_status_id = message.data.get("vendorId") or ""
        charge_point.save(
            update_fields=[
                "status",
                "vendor_error_code",
                "vendor_status_info",
                "vendor_status_id",
            ]
        )
        return self.next.handle(req)
