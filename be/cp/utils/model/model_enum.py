from enum import Enum


class ModelEnum(Enum):
    @classmethod
    def choices(cls):
        return [(i.value, i.value) for i in cls]

    def __str__(self):
        return self.value
