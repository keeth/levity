import csv
import datetime
import logging
import sys

import pytz
from django.core.management.base import BaseCommand
from ocpp.models import Transaction

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("report_type", type=str)
        parser.add_argument("start", type=datetime.datetime.fromisoformat)
        parser.add_argument("end", type=datetime.datetime.fromisoformat)
        parser.add_argument("--tz", type=str, default="America/Vancouver")

    def handle(self, *args, **options):
        tz = pytz.timezone(options["tz"])
        options["start"] = tz.localize(options["start"])
        options["end"] = tz.localize(options["end"])
        if options["report_type"] == "transaction":
            transactions = Transaction.objects.filter(
                stopped_at__gte=options["start"], stopped_at__lt=options["end"]
            ).order_by("started_at")
            writer = csv.writer(sys.stdout)
            writer.writerow(
                [
                    "id",
                    "charge_point",
                    "started_at",
                    "stopped_at",
                    "meter",
                    "meter_correction",
                    "stop_reason",
                ]
            )
            for tx in transactions:
                writer.writerow(
                    [
                        tx.id,
                        tx.charge_point,
                        tx.started_at.astimezone(tz).strftime(DATETIME_FORMAT),
                        tx.stopped_at.astimezone(tz).strftime(DATETIME_FORMAT),
                        tx.meter_stop - tx.meter_start,
                        tx.meter_correction,
                        tx.stop_reason,
                    ]
                )
        elif options["report_type"] == "message":
            pass
        else:
            raise ValueError("Unknown report type")
