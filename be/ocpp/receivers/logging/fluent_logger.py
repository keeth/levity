from django.db.models.signals import post_save
from django.dispatch import receiver
from fluent import sender

from levity import settings
from ocpp.models import WebsocketEvent, Message


logger = (
    sender.FluentSender("ocpp", host=settings.FLUENTD_HOST, port=24224)
    if settings.FLUENTD_HOST
    else None
)


@receiver(post_save, sender=WebsocketEvent)
def log_websocket_events(instance: WebsocketEvent, created, **kwargs):
    if not logger or not created:
        return
    logger.emit(f"ws.{instance.type}", dict(id=instance.charge_point.id))


@receiver(post_save, sender=Message)
def log_messages(instance: Message, created, **kwargs):
    if not logger or not created:
        return
    logger.emit("message", instance.to_ocpp())
