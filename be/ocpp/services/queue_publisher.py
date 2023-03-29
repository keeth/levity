import json
import logging

import pika
from django.conf import settings
from pika import URLParameters

logger = logging.getLogger(__name__)


class QueuePublisher:
    def __init__(self):
        self.connection = pika.BlockingConnection(URLParameters(settings.AMQP_URL))
        self.channel = self.connection.channel()

    def publish(self, queue, message):
        self.channel.basic_publish(
            exchange="", routing_key=queue, body=json.dumps(message).encode()
        )
