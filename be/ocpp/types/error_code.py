from ocpp.utils.model.model_enum import ModelEnum


class ErrorCode(ModelEnum):
    NotImplemented = "NotImplemented"
    NotSupported = "NotSupported"
    InternalError = "InternalError"
    ProtocolError = "ProtocolError"
    SecurityError = "SecurityError"
    FormationViolation = "FormationViolation"
    PropertyConstraintViolation = "PropertyConstraintViolation"
    OccurenceConstraintViolation = "OccurenceConstraintViolation"
    TypeConstraintViolation = "TypeConstraintViolation"
    GenericError = "GenericError"
