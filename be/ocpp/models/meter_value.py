import dateutil.parser

from django.db import models

from ocpp.models.transaction import Transaction


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
    def create_from_json(
        transaction: Transaction, timestamp: str, sample: dict, is_final=False
    ):
        return MeterValue.objects.create(
            timestamp=dateutil.parser.isoparse(timestamp),
            transaction=transaction,
            value=sample.get("value"),
            measurand=sample.get("measurand") or "Energy.Active.Import.Register",
            unit=sample.get("unit") or "Wh",
            context=sample.get("context") or "Sample.Periodic",
            format=sample.get("format") or "Raw",
            location=sample.get("location") or "Outlet",
            phase=sample.get("phase") or "",
            is_final=is_final,
        )
