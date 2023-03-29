import abc
import dataclasses
from typing import Optional

from ocpp.models.message import Message
from ocpp.models.transaction import Transaction
from ocpp.types.actor_type import ActorType
from ocpp.types.message_type import MessageType


@dataclasses.dataclass
class OCPPRequest:
    message: Message
    extra: dict


@dataclasses.dataclass
class OCPPResponse:
    message: Message
    transaction: Optional[Transaction]
    extra: dict


class ResponseMiddleware:
    def handle(self, req: OCPPRequest):
        return OCPPResponse(
            message=Message.objects.create(
                charge_point=req.message.charge_point,
                actor=ActorType.central_system,
                unique_id=req.message.unique_id,
                message_type=int(MessageType.call_result),
                data={},
            ),
            transaction=None,
            extra={},
        )


class OCPPMiddleware(abc.ABC):
    def __int__(self, next_middleware):
        self.next = next_middleware

    @abc.abstractmethod
    def handle(self, req: OCPPRequest) -> OCPPResponse:
        pass
