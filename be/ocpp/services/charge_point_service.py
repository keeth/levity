import abc
import logging

from ocpp.models import Message
from ocpp.models.charge_point import ChargePoint
from ocpp.services.queue_publisher import QueuePublisher

logger = logging.getLogger(__name__)

queue_publisher = QueuePublisher()


class ChargePointService:
    @classmethod
    def update_or_create_charge_point(cls, charge_point_id: str, **kwargs):
        charge_point, _ = ChargePoint.objects.update_or_create(
            id=charge_point_id, defaults=kwargs
        )
        return charge_point

    @classmethod
    def send_message_to_charge_point(cls, charge_point: ChargePoint, message: Message):
        return queue_publisher.publish(charge_point.ws_queue, message.to_ocpp())
