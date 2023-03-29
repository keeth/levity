import abc
import logging

from django.utils import timezone

from ocpp.models.charge_point import ChargePoint
from ocpp.models.message import Message
from ocpp.models.websocket_event import WebsocketEvent
from ocpp.services.charge_point_service import ChargePointService
from ocpp.services.ocpp_message_handler import OCPPMessageHandler
from ocpp.types.actor_type import ActorType
from ocpp.types.action import Action
from ocpp.types.websocket_event_type import WebsocketEventType

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

        message = Message.objects.create(
            charge_point=charge_point,
            actor=ActorType.charge_point,
            action=Action(action),
            unique_id=unique_id,
            message_type=message_type_id,
            data=rest[0] if rest else None,
        )
        OCPPMessageHandler.handle_ocpp_message(message)


WEBSOCKET_HANDLERS = {
    WebsocketEventType.connect: ConnectHandler(),
    WebsocketEventType.disconnect: DisconnectHandler(),
    WebsocketEventType.receive: ReceiveHandler(),
}


class WebsocketEventHandler:
    @classmethod
    def handle_websocket_event(cls, event: dict):
        logger.info("RECV %s", event)
        charge_point = ChargePointService.get_or_create_charge_point(event["id"])
        event_type = WebsocketEventType(event["type"])
        WEBSOCKET_HANDLERS[event_type].handle(charge_point, event)
