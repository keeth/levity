from cp.utils.model.model_enum import ModelEnum


class RegistrationStatus(ModelEnum):
    Accepted = "Accepted"
    Pending = "Pending"
    Rejected = "Rejected"
