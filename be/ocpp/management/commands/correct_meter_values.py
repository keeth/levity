import csv
import datetime
import logging
import sys

import pytz
from django.core.management.base import BaseCommand
from ocpp.models import Transaction

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

ENERGY_MAX_JUMP = 10000
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class Command(BaseCommand):
    """Detect and correct unrealistic jumps between meter readings"""

    def add_arguments(self, parser):
        parser.add_argument("start", type=datetime.datetime.fromisoformat)
        parser.add_argument("end", type=datetime.datetime.fromisoformat)
        parser.add_argument("--tz", type=str, default="America/Vancouver")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        csv_writer = csv.writer(sys.stdout)
        tz = pytz.timezone(options["tz"])
        options["start"] = tz.localize(options["start"])
        options["end"] = tz.localize(options["end"])
        transactions = Transaction.objects.filter(
            stopped_at__gte=options["start"], stopped_at__lt=options["end"]
        ).order_by("started_at")
        csv_writer.writerow(
            [
                "timestamp",
                "charge_point",
                "transaction.id",
                "meter_value.id",
                "meter_value.prev",
                "meter_value.cur",
                "meter_value.delta",
                "transaction.meter_stop",
                "transaction.meter_correction",
            ]
        )
        for transaction in transactions:
            meter_correction = 0
            report_rows = []
            prev = None
            for cur in transaction.metervalue_set.filter(
                measurand="Energy.Active.Import.Register"
            ).order_by("timestamp"):
                if (
                    prev
                    and prev.value
                    and cur.value
                    and cur.value - prev.value > ENERGY_MAX_JUMP
                ):
                    delta_value = cur.value - prev.value
                    report_rows.append(
                        [
                            cur.timestamp.astimezone(tz).strftime(DATETIME_FORMAT),
                            transaction.charge_point,
                            transaction.id,
                            cur.id,
                            round(prev.value, 2),
                            round(cur.value, 2),
                            round(delta_value, 2),
                        ]
                    )
                    cur.is_incorrect = True
                    if not options["dry_run"]:
                        cur.save(update_fields=["is_incorrect"])
                    meter_correction += delta_value
                prev = cur
            if meter_correction:
                transaction.meter_correction = -meter_correction
                for row in report_rows:
                    row += [
                        round(transaction.meter_stop, 2),
                        round(transaction.meter_correction, 2),
                    ]
                    csv_writer.writerow(row)
                if not options["dry_run"]:
                    transaction.save(update_fields=["meter_correction"])
