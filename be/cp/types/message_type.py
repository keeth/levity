from cp.utils.model.model_enum import ModelEnum


class MessageType(ModelEnum):
    call = 2
    call_result = 3
    call_error = 3
