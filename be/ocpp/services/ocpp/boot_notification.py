from django.utils import timezone

from ocpp.services.ocpp.base import OCPPMiddleware, OCPPResponse, OCPPRequest
from ocpp.types.registration_status import RegistrationStatus


class BootNotificationHandler(OCPPMiddleware):
    def handle(self, req: OCPPRequest) -> OCPPResponse:
        message = req.message
        charge_point = message.charge_point
        charge_point.hw_firmware = message.data.get("firmwareVersion", "")
        charge_point.hw_model = message.data.get("chargePointModel", "")
        charge_point.hw_vendor = message.data.get("chargePointVendor", "")
        charge_point.hw_serial = message.data.get("chargePointSerialNumber", "")
        charge_point.last_boot_at = timezone.now()
        charge_point.save(
            update_fields=[
                "hw_firmware",
                "hw_model",
                "hw_vendor",
                "hw_serial",
                "last_boot_at",
            ]
        )
        res = self.next.handle(req)
        res.message.data.update(
            dict(
                currentTime=timezone.now(),
                interval=14400,
                status=RegistrationStatus.Accepted,
            )
        )
        return res
