"""Strict JSON decoding shared by captured files and RPC responses."""

import json
import math


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key.")
        result[key] = value
    return result


def _constant(_value):
    raise ValueError("Non-finite JSON numbers are not supported.")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON numbers are not supported.")
    return number


def loads(raw):
    """Reject ambiguous objects and non-standard numeric constants."""
    return json.loads(
        raw, object_pairs_hook=_unique_pairs, parse_constant=_constant, parse_float=_finite_float
    )
