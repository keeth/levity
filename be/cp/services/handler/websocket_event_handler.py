import abc
import logging

from django.utils import timezone

from cp.models.charge_point import ChargePoint
from cp.models.message import Message
from cp.models.websocket_event import WebsocketEvent
from cp.services.charge_point_service import ChargePointService
from cp.types.actor_type import ActorType
from cp.types.action import Action
from cp.types.websocket_event_type import WebsocketEventType

logger = logging.getLogger(__name__)


class WebsocketMessageHandler(abc.ABC):
    @abc.abstractmethod
    def handle(self, charge_point: ChargePoint, message: dict):
        pass


class ConnectHandler(WebsocketMessageHandler):
    def handle(self, charge_point: ChargePoint, message: dict):
        charge_point.is_connected = True
        charge_point.save(update_fields=["is_connected"])
        WebsocketEvent.objects.create(
            charge_point=charge_point,
            timestamp=timezone.now(),
            type=WebsocketEventType.connect,
        )


class DisconnectHandler(WebsocketMessageHandler):
    def handle(self, charge_point: ChargePoint, message: dict):
        charge_point.is_connected = False
        charge_point.save(update_fields=["is_connected"])
        WebsocketEvent.objects.create(
            charge_point=charge_point,
            timestamp=timezone.now(),
            type=WebsocketEventType.disconnect,
        )


class ReceiveHandler(WebsocketMessageHandler):
    def handle(self, charge_point: ChargePoint, message: dict):
        (message_type_id, unique_id, action, *rest) = message["message"]

        Message.objects.create(
            charge_point=charge_point,
            actor=ActorType.charge_point,
            action=Action(action),
            unique_id=unique_id,
            message_type=message_type_id,
            data=rest[0] if rest else None,
        )


WEBSOCKET_HANDLERS = {
    WebsocketEventType.connect: ConnectHandler(),
    WebsocketEventType.disconnect: DisconnectHandler(),
    WebsocketEventType.receive: ReceiveHandler(),
}


class WebsocketEventHandler:
    @classmethod
    def handle_charge_point_message(cls, message: dict):
        logger.info("RECV %s", message)
        charge_point = ChargePointService.get_or_create_charge_point(message["id"])
        event_type = WebsocketEventType(message["type"])
        WEBSOCKET_HANDLERS[event_type].handle(charge_point, message)
