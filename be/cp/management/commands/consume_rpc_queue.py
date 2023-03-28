import logging

from django.core.management.base import BaseCommand

from cp.services.charge_point_service import ChargePointService
from cp.services.queue_consumer import QueueConsumer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        QueueConsumer.consume("rpc", ChargePointService.handle_charge_point_message)
