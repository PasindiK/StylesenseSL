"""Minimal local six compatibility shim for the training/evaluation runtime."""

from __future__ import annotations

import _thread
import sys
import types
import winreg

PY2 = False
PY3 = True

string_types = (str,)
integer_types = (int,)
text_type = str
binary_type = bytes


def iteritems(mapping):
    return mapping.items()


def itervalues(mapping):
    return mapping.values()


def advance_iterator(iterator):
    return next(iterator)


def raise_from(value, from_value):
    raise value from from_value


def add_metaclass(metaclass):
    def wrapper(cls):
        attributes = dict(cls.__dict__)
        attributes.pop("__dict__", None)
        attributes.pop("__weakref__", None)
        return metaclass(cls.__name__, cls.__bases__, attributes)

    return wrapper


_moves = types.ModuleType("six.moves")
_moves._thread = _thread
_moves.range = range
_moves.winreg = winreg
sys.modules["six.moves"] = _moves
moves = _moves
