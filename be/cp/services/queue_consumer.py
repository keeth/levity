import json
import logging
import time

import pika
import pika.exceptions
from django.conf import settings
from pika.connection import Parameters, URLParameters

logger = logging.getLogger(__name__)


class QueueConsumer:
    @staticmethod
    def consume(queue, fn):
        while True:
            try:
                logger.info("AMQP CONNECTING")
                connection = pika.BlockingConnection(URLParameters(settings.AMQP_URL))
                channel = connection.channel()
                channel.basic_qos(prefetch_count=1)

                def _callback(channel, method_frame, header_frame, body):
                    fn(json.loads(body))
                    channel.basic_ack(delivery_tag=method_frame.delivery_tag)

                channel.basic_consume(queue, _callback)
                channel.start_consuming()
            except pika.exceptions.AMQPChannelError as e:
                logger.exception("AMQP ERROR")
                break
            except (
                pika.exceptions.ConnectionClosedByBroker,
                pika.exceptions.AMQPConnectionError,
            ):
                logger.exception("AMQP CONNECTION CLOSED")
                time.sleep(1)
                continue
