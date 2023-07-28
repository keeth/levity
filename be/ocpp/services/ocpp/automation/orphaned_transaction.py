import logging

from ocpp.models import Transaction
from ocpp.services.ocpp.base import OCPPMiddleware, OCPPRequest, OCPPResponse
from ocpp.types.action import Action
from ocpp.types.stop_reason import StopReason

logger = logging.getLogger(__name__)


class OrphanedTransactionMiddleware(OCPPMiddleware):
    """
    When a new transaction is started, close out any unclosed previous transactions for the same CP
    """

    def handle(self, req: OCPPRequest) -> OCPPResponse:
        message = req.message
        assert Action(message.action) == Action.StartTransaction
        for orphaned_tx in Transaction.objects.filter(
            charge_point=message.charge_point, stopped_at__isnull=True
        ):
            last_meter_value = (
                orphaned_tx.metervalue_set.filter(
                    measurand="Energy.Active.Import.Register"
                )
                .order_by("timestamp")
                .last()
            )
            meter_stop = last_meter_value.value if last_meter_value else 0
            orphaned_tx.stop(StopReason.Other, meter_stop)
            logger.info(
                "Stopped orphaned transaction %s with meter value %d",
                orphaned_tx,
                meter_stop,
            )

        return self.next.handle(req)
