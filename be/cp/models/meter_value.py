from django.db import models

from cp.models.transaction import Transaction


class MeterValue(models.Model):
    timestamp = models.DateTimeField()
    transaction = models.ForeignKey(Transaction, models.CASCADE)
    context = models.CharField(max_length=128)
    format = models.CharField(max_length=128)
    location = models.CharField(max_length=128)
    measurand = models.CharField(max_length=128)
    phase = models.CharField(max_length=128)
    unit = models.CharField(max_length=16)
    value = models.FloatField()
    is_final = models.BooleanField(default=False)
