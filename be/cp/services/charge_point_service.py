import abc
import logging

from cp.models.charge_point import ChargePoint

logger = logging.getLogger(__name__)


class ChargePointService:
    @classmethod
    def get_or_create_charge_point(cls, id: str, **kwargs):
        cp, _ = ChargePoint.objects.get_or_create(id=id, defaults=kwargs)
        return cp
