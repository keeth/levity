import logging
import threading

import pika
from django.conf import settings
from pika import URLParameters
from pika.exceptions import AMQPError
from retry import retry

from ocpp.utils.serialization import json_encode

logger = logging.getLogger(__name__)


class QueuePublisher:
    def __init__(self):
        self._tl = threading.local()

    def _reconnect(self):
        if not hasattr(self._tl, "connection") or self._tl.connection.is_closed:
            self._tl.connection = pika.BlockingConnection(
                URLParameters(settings.AMQP_URL)
            )
            self._tl.channel = self._tl.connection.channel()

    @property
    def _channel(self):
        return self._tl.channel

    @retry(AMQPError, tries=5, delay=1, backoff=2)
    def publish(self, queue, message):
        body = json_encode(message)
        logger.info("SEND %s", body)
        self._reconnect()
        self._channel.basic_publish(
            exchange="",
            routing_key=queue,
            body=body.encode(),
        )
