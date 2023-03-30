import json
import logging

import pika
from django.conf import settings
from pika import URLParameters
from pika.exceptions import ChannelWrongStateError, AMQPError
from retry import retry

from ocpp.utils.serialization import JSONEncoder, json_encode

logger = logging.getLogger(__name__)


class QueuePublisher:
    def __init__(self):
        self._reconnect()

    def _reconnect(self):
        self.connection = pika.BlockingConnection(URLParameters(settings.AMQP_URL))
        self.channel = self.connection.channel()

    @retry(AMQPError, tries=5, delay=1, backoff=2)
    def publish(self, queue, message):
        body = json_encode(message)
        logger.info("QUEUE SEND %s", body)
        try:
            self.channel.basic_publish(
                exchange="",
                routing_key=queue,
                body=body.encode(),
            )
        except AMQPError:
            logger.info("QUEUE RECONNECT")
            self._reconnect()
            raise  # trigger retry logic in decorator
