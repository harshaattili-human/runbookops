"""Provider protocol syntax checks; these do not evaluate generated claims."""

import pytest

from runbookops.provider_json import decode_provider_json


@pytest.mark.parametrize('raw', [
    '{"done":false,"done":true}',
    '{"nested":[{"a":1,"\\u0061":2}]}',
    '{"metadata":NaN}', '{"metadata":Infinity}', '{"metadata":-Infinity}',
    '{"metadata":1e999}', '{"metadata":-1e999}',
    '{"answer":"\\ud800"}', '{"answer":"\\udfff"}', '{"\\ud800":0}',
    b'\xff', '{"ok":true}'.encode('utf-16'), '{"ok":true}'.encode('utf-32'),
])
def test_rejects_ambiguous_or_unserializable_values(raw):
    with pytest.raises(ValueError):
        decode_provider_json(raw)


def test_preserves_valid_unicode_numbers_and_repeated_array_values():
    raw = '{"answer":"caf\\u00e9 \\ud83d\\ude00", "ids":["x","x"], "score":0.25}'
    expected = {'answer': 'café 😀', 'ids': ['x', 'x'], 'score': .25}
    assert decode_provider_json(raw) == expected
    assert decode_provider_json(raw.encode()) == expected
