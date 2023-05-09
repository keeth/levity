from django.db.models.signals import post_save
from django.dispatch import receiver
from prometheus_client import Counter

from ocpp.models import WebsocketEvent, Message
from ocpp.types.action import Action
from ocpp.types.actor_type import ActorType
from ocpp.types.message_type import MessageType
from ocpp.types.websocket_event_type import WebsocketEventType

WEBSOCKET_COUNTERS = {
    WebsocketEventType.disconnect: Counter(
        "ocpp_charge_point_ws_disconnect",
        "OCPP charge point websocket disconnect",
        labelnames=["charge_point_id"],
    ),
}


@receiver(post_save, sender=WebsocketEvent)
def count_websocket_events(instance: WebsocketEvent, created, **kwargs):
    event_type = WebsocketEventType(instance.type)
    if created and event_type in WEBSOCKET_COUNTERS:
        WEBSOCKET_COUNTERS[event_type].labels(
            charge_point_id=instance.charge_point_id
        ).inc()


MESSAGE_COUNTERS = {
    (ActorType.charge_point, MessageType.call, Action.BootNotification): Counter(
        "ocpp_charge_point_boot",
        "OCPP charge point boot",
        labelnames=["charge_point_id"],
    ),
}


@receiver(post_save, sender=Message)
def count_messages(instance: Message, created, **kwargs):
    action = Action(instance.action) if instance.action else None
    k = (
        ActorType(instance.actor),
        MessageType(instance.message_type),
        action,
    )
    if created and k in MESSAGE_COUNTERS:
        MESSAGE_COUNTERS[k].labels(charge_point_id=instance.charge_point_id).inc()
