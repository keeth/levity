import abc
import logging

from cp.models.charge_point import ChargePoint
from cp.models.message import Message
from cp.services.charge_point_service import ChargePointService
from cp.types.actor_type import ActorType
from cp.types.action import Action

logger = logging.getLogger(__name__)


class WebsocketMessageHandler(abc.ABC):
    @abc.abstractmethod
    def handle(self, cp: ChargePoint, message: dict):
        pass


class ConnectHandler(WebsocketMessageHandler):
    def handle(self, cp: ChargePoint, message: dict):
        cp.is_connected = True
        cp.save(update_fields=["is_connected"])


class DisconnectHandler(WebsocketMessageHandler):
    def handle(self, cp: ChargePoint, message: dict):
        cp.is_connected = False
        cp.save(update_fields=["is_connected"])


class ReceiveHandler(WebsocketMessageHandler):
    def handle(self, cp: ChargePoint, message: dict):
        (message_type_id, unique_id, action, *rest) = message["message"]

        Message.objects.create(
            charge_point=cp,
            actor=ActorType.charge_point,
            action=Action(action),
            unique_id=unique_id,
            message_type=message_type_id,
            data=rest[0] if rest else None,
        )


WEBSOCKET_HANDLERS = {
    "connect": ConnectHandler(),
    "disconnect": DisconnectHandler(),
    "receive": ReceiveHandler(),
}


class WebsocketEventHandler:
    @classmethod
    def handle_charge_point_message(cls, message: dict):
        logger.info("RECV %s", message)
        cp = ChargePointService.get_or_create_charge_point(message["id"])
        WEBSOCKET_HANDLERS[message["type"]].handle(cp, message)
