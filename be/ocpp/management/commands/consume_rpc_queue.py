import logging

from django.core.management.base import BaseCommand

from ocpp.services.queue_consumer import QueueConsumer
from ocpp.services.websocket_event_handler import WebsocketEventHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        QueueConsumer.consume("rpc", WebsocketEventHandler.handle_websocket_event)
