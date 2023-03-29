from ocpp.utils.model.model_enum import ModelEnum


class AuthorizationStatus(ModelEnum):
    Accepted = "Accepted"
    Blocked = "Blocked"
    Expired = "Expired"
    Invalid = "Invalid"
