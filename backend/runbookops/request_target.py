"""Runtime alias and validation reporting for the unchanged published v4 guard."""

import json

from .information_answerability_v4 import (
    evaluate_validation_candidate, external_information_signal,
)
from .information_dataset import ROOT

# Re-export the exact published function; no duplicate patterns or runtime evaluation.
__all__ = ['external_information_signal']


def main() -> None:
    # The frozen evaluator retains publication-time wording. Refresh lifecycle metadata
    # here without editing its pinned bytes or sending holdout queries to inference.
    report = evaluate_validation_candidate()
    report['status'] = 'validation regression; v4 holdout exposed after the single joint score'
    report['candidate']['published_commit'] = 'edcada1089c663aa7466109aa01f4114b43d7a83'
    report['candidate']['production_status'] = 'integrated in TriageService; local prototype, not deployed'
    report['candidate']['holdout_status'] = (
        'exposed after first score; this command only integrity-checks holdout, with no holdout inference')
    (ROOT / 'reports/information-validation-v4.json').write_text(
        json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in (
        'suite', 'status', 'baseline', 'candidate_result')}, indent=2))


if __name__ == '__main__':
    main()
