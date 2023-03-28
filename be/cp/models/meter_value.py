from django.db import models

from cp.models.timestamped import Timestamped
from cp.models.transaction import Transaction


class MeterValue(Timestamped):
    transaction = models.ForeignKey(Transaction, models.CASCADE)
    measurand = models.CharField(max_length=128)
    unit = models.CharField(max_length=16)
    value = models.FloatField()
    is_final = models.BooleanField(default=False)
