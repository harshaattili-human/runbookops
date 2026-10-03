"""Supervised routing baseline, with feature contributions and abstention."""

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline


def make_pipeline() -> Pipeline:
    return Pipeline([
        ('text', TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words='english')),
        ('classifier', LogisticRegression(C=4.0, max_iter=1000, random_state=42)),
    ])


class IncidentClassifier:
    threshold = .40
    minimum_margin = .08

    def __init__(self, rows: list[dict]):
        self.pipeline = make_pipeline().fit([r['text'] for r in rows],
                                             [r['category'] for r in rows])

    def predict(self, text: str) -> dict:
        features = self.pipeline['text'].transform([text])
        model = self.pipeline['classifier']
        probabilities = model.predict_proba(features)[0]
        ranked = np.argsort(-probabilities)
        best = int(ranked[0])
        confidence = float(probabilities[best])
        margin = confidence - float(probabilities[ranked[1]])
        review = features.nnz == 0 or confidence < self.threshold or margin < self.minimum_margin
        contributions = features.toarray()[0] * model.coef_[best]
        names = self.pipeline['text'].get_feature_names_out()
        strongest = [int(i) for i in np.argsort(-contributions)[:6] if contributions[i] > 0]
        return {
            'category': 'needs-review' if review else str(model.classes_[best]),
            'suggested_category': str(model.classes_[best]),
            'score': round(confidence, 4), 'margin': round(margin, 4),
            'needs_review': review,
            'score_note': 'Model score, not calibrated confidence or operational accuracy.',
            'distribution': [{'category': str(model.classes_[i]), 'score': round(float(probabilities[i]), 4)}
                             for i in ranked],
            'signals': [{'term': str(names[i]), 'contribution': round(float(contributions[i]), 4)}
                        for i in strongest],
        }
