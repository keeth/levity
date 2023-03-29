from ocpp.utils.model.model_enum import ModelEnum


class ChargePointError(ModelEnum):
    ConnectorLockFailure = "ConnectorLockFailure"
    EVCommunicationError = "EVCommunicationError"
    GroundFailure = "GroundFailure"
    HighTemperature = "HighTemperature"
    InternalError = "InternalError"
    LocalListConflict = "LocalListConflict"
    NoError = "NoError"
    OtherError = "OtherError"
    OverCurrentFailure = "OverCurrentFailure"
    OverVoltage = "OverVoltage"
    PowerMeterFailure = "PowerMeterFailure"
    PowerSwitchFailure = "PowerSwitchFailure"
    ReaderFailure = "ReaderFailure"
    ResetFailure = "ResetFailure"
    UnderVoltage = "UnderVoltage"
    WeakSignal = "WeakSignal"
