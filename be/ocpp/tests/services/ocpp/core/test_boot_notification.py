from django.test import TestCase

from ocpp.models import Message
from ocpp.services.charge_point_message_handler import ChargePointMessageHandler
from ocpp.tests.factory import ChargePointFactory


class BootNotificationTest(TestCase):
    def setUp(self) -> None:
        self.charge_point = ChargePointFactory()

    def test_boot_notification(self):
        ChargePointMessageHandler.handle_message_from_charge_point(
            Message.from_occp(
                self.charge_point,
                dict(
                    message=[
                        2,
                        "03.00003282cfc304e69",
                        "BootNotification",
                        {
                            "chargePointSerialNumber": "GRS-03.00003282c",
                            "chargePointModel": "GRS-*",
                            "chargePointVendor": "United Chargers",
                            "firmwareVersion": "05.653:GCW-10.17-05.3:7452:B29A",
                            "meterType": "SW",
                            "iccid": "-87",
                            "imsi": "1",
                        },
                    ]
                ),
            )
        )
        self.charge_point.refresh_from_db()
        assert self.charge_point.hw_firmware == "05.653:GCW-10.17-05.3:7452:B29A"
        assert self.charge_point.hw_iccid == "-87"
        assert self.charge_point.hw_imsi == "1"
        assert self.charge_point.last_boot_at
