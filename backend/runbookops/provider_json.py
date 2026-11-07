"""Strict decoding for the bounded, untrusted provider response layers."""

import json
import math


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate provider JSON field')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('Non-finite provider JSON number')


def decode_provider_json(raw: str | bytes | bytearray):
    # Bytes must be UTF-8; json.loads(bytes) also auto-detects UTF-16/32.
    text = raw.decode('utf-8') if isinstance(raw, (bytes, bytearray)) else raw
    parsed = json.loads(text, object_pairs_hook=_object, parse_constant=_constant)
    pending = [parsed]
    while pending:
        value = pending.pop()
        if isinstance(value, str):
            # Escaped lone surrogates can survive JSON decoding but cannot be
            # returned by the UTF-8 HTTP serializer. Valid pairs decode normally.
            value.encode('utf-8')
        elif isinstance(value, float) and not math.isfinite(value):
            # A standard numeric spelling such as 1e999 can overflow to infinity.
            raise ValueError('Non-finite provider JSON number')
        elif isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return parsed
