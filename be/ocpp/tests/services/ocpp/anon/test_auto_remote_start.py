from unittest.mock import patch

from django.test import TestCase

from ocpp.models import Message
from ocpp.services.charge_point_message_handler import ChargePointMessageHandler
from ocpp.tests.factory import ChargePointFactory
from ocpp.types.action import Action


@patch(
    "ocpp.services.charge_point_service.ChargePointService.send_message_to_charge_point"
)
class AutoRemoteStartTest(TestCase):
    def setUp(self) -> None:
        self.charge_point = ChargePointFactory()

    def test_auto_remote_start(self, send_message_to_charge_point):
        message = Message.from_occp(
            self.charge_point,
            dict(
                message=[
                    2,
                    "03.00003282c0eb8ce0h",
                    "StatusNotification",
                    {
                        "errorCode": "NoError",
                        "status": "Preparing",
                        "timestamp": "2023-03-30T01:58:48.001Z",
                        "info": "Pilot and Charger:20h",
                        "vendorId": "UC",
                        "vendorErrorCode": "0",
                        "connectorId": 1,
                    },
                ]
            ),
        )
        ChargePointMessageHandler.handle_message_from_charge_point(message)
        self.charge_point.refresh_from_db()
        reply_messages = [c[1][1] for c in send_message_to_charge_point.mock_calls]
        assert len(reply_messages) == 2
        assert Action(reply_messages[1].action) == Action.RemoteStartTransaction
