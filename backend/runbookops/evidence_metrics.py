"""Mechanical cited-span coverage; no dataset loading, inference or entailment."""


def _interval(value: dict) -> tuple[int, int]:
    start, end = value['start_line'], value['end_line']
    if type(start) is not int or type(end) is not int or start < 1 or end < start:
        raise ValueError('Evidence intervals must be ordered positive integer lines')
    return start, end


def evidence_supported_and_answered(response: dict, expected_document: str,
                                    expected_evidence: dict) -> bool:
    """Require an extractive answer and full annotation coverage by cited sources.

    Inputs are a retained service response and a frozen supported annotation. Line
    coordinates are trusted only after the evaluator checks corpus/code hashes.
    This checks interval coverage, not whether answer prose entails the request.
    Invalid/ambiguous evidence raises instead of silently improving a denominator.
    """
    start, end = _interval(expected_evidence)
    if not isinstance(expected_document, str) or not expected_document:
        raise ValueError('Expected document must be a nonempty identifier')
    if response['mode'] not in {'extractive', 'abstained'}:
        raise ValueError('Passage evaluation requires the extractive path')
    sources = {}
    for source in response['sources']:
        source_id = source['id']
        if not isinstance(source_id, str) or not source_id or source_id in sources:
            raise ValueError('Source IDs must be nonempty and unique')
        _interval(source)
        sources[source_id] = source
    citations = response['citations']
    if not isinstance(citations, list) or any(
            not isinstance(item, str) or item not in sources for item in citations):
        raise ValueError('Citations must resolve to returned sources')
    if response['mode'] == 'abstained':
        return False
    if not isinstance(response['answer'], str) or not response['answer'].strip():
        return False

    # Merge only cited intervals from the annotated document. Sorting is essential:
    # taking min/max would incorrectly accept a missing line between citations.
    intervals = sorted(_interval(sources[item]) for item in set(citations)
                       if sources[item]['document'] == expected_document)
    next_line = start
    for left, right in intervals:
        if right < next_line:
            continue
        if left > next_line:
            return False
        next_line = right + 1
        if next_line > end:
            return True
    return False
