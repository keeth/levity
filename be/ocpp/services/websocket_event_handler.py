import abc
import json
import logging

from ocpp.models.charge_point import ChargePoint
from ocpp.models.message import Message
from ocpp.models.websocket_event import WebsocketEvent
from ocpp.services.charge_point_message_handler import ChargePointMessageHandler
from ocpp.services.charge_point_service import ChargePointService
from ocpp.types.websocket_event_type import WebsocketEventType
from ocpp.utils.date import utc_now

logger = logging.getLogger(__name__)


class WebsocketEventHandler(abc.ABC):
    @abc.abstractmethod
    def handle(self, charge_point: ChargePoint, event: dict):
        pass


class ConnectHandler(WebsocketEventHandler):
    def handle(self, charge_point: ChargePoint, event: dict):
        charge_point.is_connected = True
        charge_point.last_connect_at = utc_now()
        charge_point.save(update_fields=["is_connected", "last_connect_at"])
        WebsocketEvent.objects.create(
            charge_point=charge_point,
            timestamp=utc_now(),
            type=WebsocketEventType.connect,
        )


class DisconnectHandler(WebsocketEventHandler):
    def handle(self, charge_point: ChargePoint, event: dict):
        charge_point.is_connected = False
        charge_point.save(update_fields=["is_connected"])
        WebsocketEvent.objects.create(
            charge_point=charge_point,
            timestamp=utc_now(),
            type=WebsocketEventType.disconnect,
        )


class ReceiveHandler(WebsocketEventHandler):
    def handle(self, charge_point: ChargePoint, event: dict):
        message = Message.from_occp(charge_point, event)
        ChargePointMessageHandler.handle_message_from_charge_point(message)


WEBSOCKET_HANDLERS = {
    WebsocketEventType.connect: ConnectHandler(),
    WebsocketEventType.disconnect: DisconnectHandler(),
    WebsocketEventType.receive: ReceiveHandler(),
}


class WebsocketEventHandler:
    @classmethod
    def handle_websocket_event(cls, event: dict):
        logger.info("RECV %s", json.dumps(event))
        charge_point = ChargePointService.update_or_create_charge_point(
            event["id"], ws_queue=event["queue"]
        )
        event_type = WebsocketEventType(event["type"])
        WEBSOCKET_HANDLERS[event_type].handle(charge_point, event)
