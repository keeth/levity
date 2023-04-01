from ocpp.utils.model.model_enum import ModelEnum


class DataTransferStatus(ModelEnum):
    Accepted = "Accepted"
    Rejected = "Rejected"
    UnknownMessageId = "UnknownMessageId"
    UnknownVendorId = "UnknownVendorId"
