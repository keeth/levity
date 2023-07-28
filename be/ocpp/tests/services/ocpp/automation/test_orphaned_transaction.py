from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase

from ocpp.models import Message, Transaction
from ocpp.services.charge_point_message_handler import ChargePointMessageHandler
from ocpp.tests.factory import ChargePointFactory, TransactionFactory, MeterValueFactory
from ocpp.utils.date import utc_now


@patch(
    "ocpp.services.charge_point_service.ChargePointService.send_message_to_charge_point"
)
class OrphanedTransactionTest(TestCase):
    def setUp(self) -> None:
        self.charge_point = ChargePointFactory()

    def test_auto_remote_start(self, send_message_to_charge_point):
        orphaned_tx = TransactionFactory(
            charge_point=self.charge_point, started_at=utc_now()
        )
        MeterValueFactory(
            timestamp=utc_now() - timedelta(minutes=1),
            transaction=orphaned_tx,
            measurand="Energy.Active.Import.Register",
            value=5,
        )
        MeterValueFactory(
            timestamp=utc_now(),
            transaction=orphaned_tx,
            measurand="Energy.Active.Import.Register",
            value=10,
        )
        message = Message.from_occp(
            self.charge_point,
            dict(
                message=[
                    2,
                    "x",
                    "StartTransaction",
                    {
                        "idTag": "x",
                        "timestamp": "2023-03-30T01:58:52.001Z",
                        "connectorId": 1,
                        "meterStart": 0,
                    },
                ]
            ),
        )
        ChargePointMessageHandler.handle_message_from_charge_point(message)
        self.charge_point.refresh_from_db()
        orphaned_tx.refresh_from_db()
        assert orphaned_tx.stopped_at
        assert orphaned_tx.meter_stop == 10

        # make sure it doesn't affect the new transaction
        assert Transaction.objects.filter(
            charge_point=self.charge_point, stopped_at__isnull=True, meter_stop=0
        ).exists()
