import dateutil.parser

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

    @staticmethod
    def create_from_json(transaction: Transaction, value: dict):
        sample = value["sampledValue"]
        return MeterValue.objects.create(
            timestamp=dateutil.parser.isoparse(value["timestamp"]),
            transaction=transaction,
            context=sample.get("context"),
            format=sample.get("format"),
            location=sample.get("location"),
            phase=sample.get("phase"),
            measurand=sample.get("measurand"),
            unit=sample.get("unit"),
            value=sample.get("value"),
        )
