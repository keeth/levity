import abc

from cp.models.message import Message
from cp.types.actor_type import ActorType
from cp.types.message_type import MessageType


class OCPPMessageHandler(abc.ABC):
    @abc.abstractmethod
    def handle(self, message: Message) -> Message:
        pass

    def _reply(self, message: Message, data: dict) -> Message:
        return Message.objects.create(
            charge_point=message.charge_point,
            actor=ActorType.central_system,
            unique_id=message.unique_id,
            message_type=int(MessageType.call_result),
            data=data,
        )
