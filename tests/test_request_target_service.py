import asyncio
import json

from fastapi.testclient import TestClient

from runbookops.api import app
from runbookops.service import ROOT, TriageService


def test_service_matches_fixed_validation_candidate_without_scoring_holdout():
    report = json.loads((ROOT / 'reports/information-validation-v4.json').read_text())
    service = TriageService()
    for case in report['cases']:
        result = service.triage(case['query'])
        assert bool(result['sources']) == case['candidate_answered'], case['id']
        assert result['answerability']['coverage'] == case['document_coverage']
        assert result['answerability']['external_information_signal'] == case['candidate_signal']
        if result['sources']:
            assert result['sources'][0]['document'] == case['top_document']
        else:
            assert result['mode'] == 'abstained'
            assert result['citations'] == []
            assert result['routing']['needs_review']


def test_direct_external_value_never_enters_generation_sync_or_async(monkeypatch):
    service = TriageService()
    async def unexpected_generation(*args):
        raise AssertionError('generation must not run for a withheld request target')
    monkeypatch.setattr(service, '_synthesize', unexpected_generation)
    query = ('JWT validation fails after a signing-key rollout. '
             'An accepted raw bearer token for this caller.')
    results = [service.triage(query, use_llm=True),
               asyncio.run(service.triage_async(query, use_llm=True))]
    for result in results:
        assert result['answerability']['coverage'] >= .33
        assert result['answerability']['external_information_signal'] == 'sensitive_value'
        assert result['mode'] == 'abstained'
        assert result['sources'] == result['citations'] == []


def test_http_explains_request_target_abstention_and_preserves_descriptive_incidents():
    with TestClient(app) as client:
        withheld = client.post('/api/triage', json={
            'query': 'Database pool connections are exhausted. Pool maximum: 80 connections on each replica.',
            'use_llm': True,
        })
        assert withheld.status_code == 200
        result = withheld.json()
        assert result['mode'] == 'abstained'
        assert result['answerability']['external_information_signal'] == 'literal_configuration'
        assert result['sources'] == result['citations'] == []
        assert 'external value, decision, or procedure' in result['answer']
        ordinary = client.post('/api/triage', json={
            'query': 'Active connections are at the maximum and pending requests keep rising.',
        }).json()
        assert ordinary['mode'] == 'extractive'
        assert ordinary['answerability']['external_information_signal'] is None
        assert ordinary['sources'][0]['document'] == 'database-pool'
