from cp.utils.model.model_enum import ModelEnum


class WebsocketEventType(ModelEnum):
    connect = "connect"
    disconnect = "disconnect"
    receive = "receive"
