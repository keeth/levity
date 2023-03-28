import logging

logger = logging.getLogger(__name__)


class ChargePointService:
    @classmethod
    def handle_charge_point_message(cls, message: dict):
        logger.info("RECV %s", message)
