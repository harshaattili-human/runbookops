from unittest.mock import patch

import pytest

from runbookops.information_holdout_v4 import evaluate_holdout


def test_holdout_requires_opt_in_before_any_file_read():
    with patch('runbookops.information_holdout_v4.sha256') as digest:
        with pytest.raises(ValueError, match='explicit opt-in'):
            evaluate_holdout()
        digest.assert_not_called()


def test_modified_candidate_rejected_before_loading_or_scoring_holdout():
    with patch('runbookops.information_holdout_v4.sha256', return_value='changed'), \
         patch('runbookops.information_holdout_v4.load_cases') as loader, \
         patch('runbookops.information_holdout_v4.Retriever') as retriever:
        with pytest.raises(ValueError, match='candidate/ranking changed'):
            evaluate_holdout(allow_holdout=True)
        loader.assert_not_called()
        retriever.assert_not_called()
