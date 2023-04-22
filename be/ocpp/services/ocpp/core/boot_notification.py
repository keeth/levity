from django.conf import settings

from ocpp.services.ocpp.base import OCPPMiddleware, OCPPResponse, OCPPRequest
from ocpp.types.registration_status import RegistrationStatus
from ocpp.utils.date import utc_now


class BootNotificationMiddleware(OCPPMiddleware):
    def handle(self, req: OCPPRequest) -> OCPPResponse:
        message = req.message
        charge_point = message.charge_point
        charge_point.hw_firmware = message.data.get("firmwareVersion", "")
        charge_point.hw_model = message.data.get("chargePointModel", "")
        charge_point.hw_vendor = message.data.get("chargePointVendor", "")
        charge_point.hw_serial = message.data.get("chargePointSerialNumber", "")
        charge_point.hw_iccid = message.data.get("iccid", "")
        charge_point.hw_imsi = message.data.get("imsi", "")
        charge_point.last_boot_at = utc_now()
        charge_point.save(
            update_fields=[
                "hw_firmware",
                "hw_model",
                "hw_vendor",
                "hw_serial",
                "last_boot_at",
                "hw_iccid",
                "hw_imsi",
            ]
        )
        res = self.next.handle(req)
        res.message.data.update(
            dict(
                currentTime=utc_now(),
                interval=settings.OCPP_HEARTBEAT_INTERVAL,
                status=RegistrationStatus.Accepted,
            )
        )
        return res
