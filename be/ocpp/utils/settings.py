from functools import lru_cache
from typing import List

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from ocpp.types.action import Action
from ocpp.types.message_type import MessageType


def _import_classes(class_names: List[str]):
    classes = []
    for class_name in class_names:
        try:
            classes.append(import_string(class_name))
        except ImportError:
            raise ImproperlyConfigured(
                "Unable to import {}. Check your OCPP_MIDDLEWARE setting.".format(
                    class_name
                )
            )
    return classes


def _action(action_name: str):
    try:
        return Action(action_name)
    except ValueError:
        raise ImproperlyConfigured(
            "Unknown action {}. Check your OCPP_MIDDLEWARE setting.".format(action_name)
        )


def _message_type(message_type_id):
    try:
        return MessageType(message_type_id)
    except ValueError:
        raise ImproperlyConfigured(
            "Unknown message type {}. Check your OCPP_MIDDLEWARE setting.".format(
                message_type_id
            )
        )


@lru_cache
def _load_ocpp_middleware_from_dict(setting: dict):
    return {
        (_action(k[0]), _message_type(k[1])): _import_classes(v)
        for k, v in setting.items()
    }


def load_ocpp_middleware():
    if not hasattr(settings, "OCPP_MIDDLEWARE"):
        return {}
    ocpp_middleware = settings.OCPP_MIDDLEWARE
    assert isinstance(ocpp_middleware, dict), "OCPP_MIDDLEWARE should be a dict"
    return _load_ocpp_middleware_from_dict(ocpp_middleware)
