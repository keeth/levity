from uuid import uuid4

from ocpp.models import Message
from ocpp.services.ocpp.base import OCPPMiddleware, OCPPRequest, OCPPResponse
from ocpp.types.action import Action
from ocpp.types.actor_type import ActorType
from ocpp.types.charge_point_status import ChargePointStatus
from ocpp.types.message_type import MessageType


class AutoRemoteStartMiddleware(OCPPMiddleware):
    """
    When a charge point transitions to Preparing, automatically start a transaction, using an anonymous ID tag
    """

    def handle(self, req: OCPPRequest) -> OCPPResponse:
        res = self.next.handle(req)
        message = req.message
        assert Action(message.action) == Action.StatusNotification
        if ChargePointStatus(message.data["status"]) == ChargePointStatus.Preparing:
            charge_point = message.charge_point
            res.side_effects.append(
                Message.objects.create(
                    charge_point=charge_point,
                    action=Action.RemoteStartTransaction,
                    actor=ActorType.central_system,
                    unique_id=str(uuid4()),
                    message_type=int(MessageType.call),
                    data=dict(idTag="anonymous"),
                )
            )
        return res
