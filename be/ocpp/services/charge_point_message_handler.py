import abc
from functools import lru_cache

from ocpp.models.message import Message
from ocpp.services.charge_point_service import ChargePointService
from ocpp.services.ocpp.anon.auto_remote_start import AutoRemoteStartMiddleware
from ocpp.services.ocpp.base import ResponseMiddleware, OCPPRequest
from ocpp.services.ocpp.core.authorize import AuthorizeMiddleware
from ocpp.services.ocpp.core.boot_notification import BootNotificationMiddleware
from ocpp.services.ocpp.core.data_transfer import DataTransferMiddleware
from ocpp.services.ocpp.core.diagnostics_status_notification import (
    DiagnosticsStatusNotificationMiddleware,
)
from ocpp.services.ocpp.core.firmware_status_notification import (
    FirmwareStatusNotificationMiddleware,
)
from ocpp.services.ocpp.core.meter_values import MeterValuesMiddleware
from ocpp.services.ocpp.core.start_transaction import StartTransactionMiddleware
from ocpp.services.ocpp.core.status_notification import StatusNotificationMiddleware
from ocpp.services.ocpp.core.stop_transaction import StopTransactionMiddleware
from ocpp.types.action import Action
from ocpp.types.actor_type import ActorType
from ocpp.types.message_type import MessageType
from ocpp.utils.serialization import json_decode, json_encode
from ocpp.utils.settings import load_ocpp_middleware

DEFAULT_MIDDLEWARE_CONFIG = {
    (Action.Authorize, MessageType.call): [AuthorizeMiddleware],
    (Action.BootNotification, MessageType.call): [BootNotificationMiddleware],
    (Action.DataTransfer, MessageType.call): [DataTransferMiddleware],
    (Action.DiagnosticsStatusNotification, MessageType.call): [
        DiagnosticsStatusNotificationMiddleware
    ],
    (Action.FirmwareStatusNotification, MessageType.call): [
        FirmwareStatusNotificationMiddleware
    ],
    (Action.MeterValues, MessageType.call): [MeterValuesMiddleware],
    (Action.StartTransaction, MessageType.call): [StartTransactionMiddleware],
    (Action.StatusNotification, MessageType.call): [
        AutoRemoteStartMiddleware,
        StatusNotificationMiddleware,
    ],
    (Action.StopTransaction, MessageType.call): [StopTransactionMiddleware],
}


@lru_cache
def get_middleware(middleware_classes: tuple):
    middleware_classes = list(middleware_classes) + [ResponseMiddleware]
    prev = None
    cur = None
    for klass in reversed(middleware_classes):
        args = [prev] if prev else []
        cur = klass(*args)
        prev = cur
    return cur


class MessageTypeHandler(abc.ABC):
    @abc.abstractmethod
    def handle(self, message: Message):
        pass


class ChargePointCallHandler(MessageTypeHandler):
    def handle(self, message: Message):
        message_type = MessageType(message.message_type)
        action = Action(message.action)
        custom_middleware_config = load_ocpp_middleware()
        middleware_classes = custom_middleware_config.get(
            (action, message_type),
            DEFAULT_MIDDLEWARE_CONFIG.get((action, message_type), []),
        )
        middleware = get_middleware(tuple(middleware_classes))
        res = middleware.handle(OCPPRequest(message=message, extra={}))
        res.message.data = json_decode(
            json_encode(res.message.data)
        )  # make serializable
        res.message.save()
        message.reply = res.message
        message.save(update_fields=["reply"])
        charge_point = res.message.charge_point
        ChargePointService.send_message_to_charge_point(charge_point, res.message)
        # TODO: WS will need outbound message queueing if more than one side effect is returned
        for side_effect_message in res.side_effects:
            side_effect_message.save()
            ChargePointService.send_message_to_charge_point(
                charge_point, side_effect_message
            )


class ChargePointCallResultHandler(MessageTypeHandler):
    def handle(self, message: Message):
        # just link the originating call to the result message
        originating_call = Message.objects.get(
            unique_id=message.unique_id, message_type=MessageType.call
        )
        originating_call.reply = message
        originating_call.save(update_fields=["reply"])
        message.action = originating_call.action
        message.save(update_fields=["action"])
        # TODO: middleware for call_result and call_error


class ChargePointCallErrorHandler(ChargePointCallResultHandler):
    pass


MESSAGE_TYPE_HANDLERS = {
    MessageType.call: ChargePointCallHandler(),
    MessageType.call_result: ChargePointCallResultHandler(),
    MessageType.call_error: ChargePointCallErrorHandler(),
}


class ChargePointMessageHandler:
    @staticmethod
    def handle_message_from_charge_point(message: Message):
        assert (
            ActorType(message.actor) == ActorType.charge_point
        ), "Expected message from charge point"
        message_type = MessageType(message.message_type)
        MESSAGE_TYPE_HANDLERS[message_type].handle(message)
