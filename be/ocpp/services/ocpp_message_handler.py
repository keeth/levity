from functools import lru_cache

from ocpp.models.message import Message
from ocpp.services.ocpp.base import ResponseMiddleware, OCPPRequest
from ocpp.services.ocpp.boot_notification import BootNotificationMiddleware
from ocpp.services.ocpp.meter_values import MeterValuesMiddleware
from ocpp.services.ocpp.start_transaction import StartTransactionMiddleware
from ocpp.services.ocpp.status_notification import StatusNotificationMiddleware
from ocpp.services.ocpp.stop_transaction import StopTransactionMiddleware
from ocpp.services.queue_publisher import QueuePublisher
from ocpp.types.action import Action
from ocpp.types.actor_type import ActorType
from ocpp.types.message_type import MessageType
from ocpp.utils.settings import load_ocpp_middleware

DEFAULT_MIDDLEWARE_CONFIG = {
    Action.BootNotification: [BootNotificationMiddleware],
    Action.MeterValues: [MeterValuesMiddleware],
    Action.StartTransaction: [StartTransactionMiddleware],
    Action.StatusNotification: [StatusNotificationMiddleware],
    Action.StopTransaction: [StopTransactionMiddleware],
}

queue_publisher = QueuePublisher()


@lru_cache
def get_middleware(middleware_classes: list):
    middleware_classes = middleware_classes + [ResponseMiddleware]
    prev = None
    cur = None
    for klass in reversed(middleware_classes):
        args = [prev] if prev else []
        cur = klass(*args)
        prev = cur
    return cur


class OCPPMessageHandler:
    @staticmethod
    def handle_ocpp_message(message: Message):
        assert (
            ActorType(message.actor) == ActorType.charge_point
        ), "Expected message from charge point"
        assert (
            MessageType(message.message_type) == MessageType.call
        ), "Expected message of type CALL (2)"
        action = Action(message.action)
        custom_middleware_config = load_ocpp_middleware()
        middleware_classes = custom_middleware_config.get(
            action, DEFAULT_MIDDLEWARE_CONFIG.get(action, [])
        )
        middleware = get_middleware(middleware_classes)
        res = middleware.handle(OCPPRequest(message=message, extra={}))
        res.message.save()
        charge_point = res.message.charge_point
        queue_publisher.publish(
            charge_point.ws_queue,
            dict(
                id=charge_point.id,
                message=[
                    int(res.message.message_type),
                    res.message.unique_id,
                    res.message.data,
                ],
            ),
        )
