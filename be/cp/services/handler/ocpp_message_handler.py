from django.db.models.signals import post_save
from django.dispatch import receiver

from cp.models.message import Message
from cp.types.actor_type import ActorType
from cp.types.message_type import MessageType

OCPP_HANDLERS = {}


@receiver(post_save, sender=Message)
def handle_ocpp_message(instance: Message, created, *args, **kwargs):
    if not created:
        return
    if ActorType(instance.actor) != ActorType.charge_point:
        return
    if MessageType(instance.message_type) != MessageType.call:
        return
