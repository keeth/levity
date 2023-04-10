import factory
from factory.django import DjangoModelFactory

from ocpp.models import ChargePoint
from ocpp.types.charge_point_status import ChargePointStatus


class ChargePointFactory(DjangoModelFactory):
    id = factory.Sequence(lambda n: "chg{0}".format(n))
    name = factory.Sequence(lambda n: "Charger {0}".format(n))
    status = ChargePointStatus.Available
    error_code = None
    is_connected = False
    vendor_error_code = ""
    vendor_status_info = ""
    vendor_status_id = ""
    ws_queue = ""
    hw_vendor = ""
    hw_model = ""
    hw_serial = ""
    hw_firmware = ""
    hw_iccid = ""
    last_heartbeat_at = None
    last_boot_at = None
    last_connect_at = None
    last_tx_start_at = None
    last_tx_stop_at = None

    class Meta:
        model = ChargePoint
