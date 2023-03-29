from django.utils import timezone

from cp.models.message import Message
from cp.services.handler.ocpp.base import OCPPMessageHandler
from cp.types.registration_status import RegistrationStatus


class BootHandler(OCPPMessageHandler):
    def handle(self, message: Message) -> Message:
        cp = message.charge_point
        cp.hw_firmware = message.data.get("firmwareVersion", "")
        cp.hw_model = message.data.get("chargePointModel", "")
        cp.hw_vendor = message.data.get("chargePointVendor", "")
        cp.hw_serial = message.data.get("chargePointSerialNumber", "")
        cp.last_boot_at = timezone.now()
        cp.save(
            update_fields=[
                "hw_firmware",
                "hw_model",
                "hw_vendor",
                "hw_serial",
                "last_boot_at",
            ]
        )
        return self._reply(
            message,
            dict(
                currentTime=timezone.now(),
                interval=14400,
                status=RegistrationStatus.Accepted,
            ),
        )
