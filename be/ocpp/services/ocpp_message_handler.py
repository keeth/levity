from functools import lru_cache

from ocpp.models.message import Message
from ocpp.services.charge_point_service import ChargePointService
from ocpp.services.ocpp.anon.auto_remote_start import AutoRemoteStartMiddleware
from ocpp.services.ocpp.base import ResponseMiddleware, OCPPRequest
from ocpp.services.ocpp.core.boot_notification import BootNotificationMiddleware
from ocpp.services.ocpp.core.meter_values import MeterValuesMiddleware
from ocpp.services.ocpp.core.start_transaction import StartTransactionMiddleware
from ocpp.services.ocpp.core.status_notification import StatusNotificationMiddleware
from ocpp.services.ocpp.core.stop_transaction import StopTransactionMiddleware
from ocpp.types.action import Action
from ocpp.types.actor_type import ActorType
from ocpp.types.message_type import MessageType
from ocpp.utils.serialization import json_decode, json_encode
from ocpp.utils.settings import load_ocpp_middleware

DEFAULT_MIDDLEWARE_CONFIG = {
    (Action.BootNotification, MessageType.call): [BootNotificationMiddleware],
    (Action.MeterValues, MessageType.call): [MeterValuesMiddleware],
    (Action.StartTransaction, MessageType.call): [StartTransactionMiddleware],
    (Action.StatusNotification, MessageType.call): [
        AutoRemoteStartMiddleware,
        StatusNotificationMiddleware,
    ],
    (Action.StopTransaction, MessageType.call): [StopTransactionMiddleware],
}


@lru_cache
def get_middleware(middleware_classes: tuple):
    middleware_classes = list(middleware_classes) + [ResponseMiddleware]
    prev = None
    cur = None
    for klass in reversed(middleware_classes):
        args = [prev] if prev else []
        cur = klass(*args)
        prev = cur
    return cur


class OCPPMessageHandler:
    @staticmethod
    def handle_ocpp_message(message: Message):
        assert (
            ActorType(message.actor) == ActorType.charge_point
        ), "Expected message from charge point"
        message_type = MessageType(message.message_type)
        if message_type == MessageType.call:
            action = Action(message.action)
            custom_middleware_config = load_ocpp_middleware()
            middleware_classes = custom_middleware_config.get(
                (action, message_type),
                DEFAULT_MIDDLEWARE_CONFIG.get((action, message_type), []),
            )
            middleware = get_middleware(tuple(middleware_classes))
            res = middleware.handle(OCPPRequest(message=message, extra={}))
            res.message.data = json_decode(
                json_encode(res.message.data)
            )  # make serializable
            res.message.save()
            message.reply = res.message
            message.save(update_fields=["reply"])
            charge_point = res.message.charge_point
            ChargePointService.send_message_to_charge_point(charge_point, res.message)
            # TODO: message synchronicity
            for side_effect_message in res.side_effects:
                side_effect_message.save()
                ChargePointService.send_message_to_charge_point(
                    charge_point, side_effect_message
                )
        elif message_type == MessageType.call_result:
            # just link the call_result to the original call
            originating_call = Message.objects.get(
                unique_id=message.unique_id, message_type=MessageType.call
            )
            originating_call.reply = message
            originating_call.save(update_fields=["reply"])
            message.action = originating_call.action
            message.save(update_fields=["action"])


# [2,"03.00003282cfc304e65","BootNotification",{"chargePointSerialNumber":"GRS-03.00003282c","chargePointModel":"GRS-*","chargePointVendor":"United Chargers","firmwareVersion":"05.653:GCW-10.17-05.3:7452:B29A","meterType":"SW","iccid":"-87","imsi":"1"}]

# [2,"03.00003282c0eb8ce0c","StatusNotification",{"errorCode":"NoError","status":"Preparing","timestamp":"2023-03-30T01:58:48.001Z","info":"Pilot and Charger:20h","vendorId":"UC","vendorErrorCode":"0","connectorId":1}]

# [2,"03.00003282c0eee0461","StartTransaction",{"idTag":"hvresident","timestamp":"2023-03-30T01:58:52.001Z","connectorId":1,"meterStart":0}]

# [2,"03.00003282c0f5613c2","StatusNotification",{"errorCode":"NoError","status":"Charging","timestamp":"2023-03-30T01:58:58.001Z","info":"Pilot and Charger:C1h","vendorId":"UC","vendorErrorCode":"0","connectorId":1}]

# [2,"03.00003282c15aebfbf","MeterValues",{"connectorId":1,"meterValue":[{"timestamp":"2023-03-30T02:00:45.001Z","sampledValue":[{"context":"Sample.Periodic","format":"Raw","location":"Body","phase":"L1-N","measurand":"Current.Import","unit":"A","value":"30.77"},{"context":"Sample.Periodic","format":"Raw","location":"Body","phase":"L1-N","measurand":"Power.Active.Import","unit":"W","value":"7148.96"},{"context":"Sample.Periodic","format":"Raw","location":"Body","phase":"L1-N","measurand":"Energy.Active.Import.Register","unit":"Wh","value":"70.14"}]}],"transactionId":1}]

# [2,"03.00003282c1dc63c95","StopTransaction",{"idTag":"hvresident","timestamp":"2023-03-29T20:05:06.001Z","transactionId":1,"meterStop":40330,"reason":"Remote","transactionData":[{"timestamp":"2023-03-29T20:05:06.001Z","sampledValue":[{"measurand":"Current.Import","unit":"A","value":"39.35"},{"measurand":"Power.Active.Import","unit":"W","value":"9141.55"},{"measurand":"Energy.Active.Import.Register","unit":"Wh","value":"40330.10"}]}]}]

# [2,"03.00003282c0eb8ce0e","StatusNotification",{"errorCode":"NoError","status":"Preparing","timestamp":"2023-03-30T01:58:48.001Z","info":"Pilot and Charger:20h","vendorId":"UC","vendorErrorCode":"0","connectorId":1}]

# [3,"4aecd659-8650-4d2c-a755-07952a5558a5",{"status":"Accepted"}]
