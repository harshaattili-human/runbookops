# Two-minute walkthrough

1. Start at the incident workbench and select **Connection pool**.
2. Explain the difference between the service-area classifier and retrieval. The
   suggested label does not filter documents, so a routing error cannot hide evidence.
3. Open a source card. Show the exact Markdown lines and the passage used in the answer.
4. Select **Outside the corpus**. Show that the app declines to invent an answer.
5. Open **Evaluation**. Explain grouped splitting and point out the errors, not just
   the headline score. Emphasize that every example is synthetic.
6. Explain the optional local LLM: it summarizes the evidence, while invalid citation
   IDs and provider failures fall back to source text. Valid IDs do not prove factuality.

## Project description

RunbookOps is an independent, AI-assisted portfolio project combining supervised
incident routing, sparse hybrid retrieval, and an evidence-linked React workbench.
It reflects interests in backend engineering, workflow operations, and applied AI.
It is not an employer project or a claim of production deployment.

## Discussion points to understand before an interview

- Why TF-IDF and logistic regression are a reasonable small-data baseline.
- Why random row splitting leaks paraphrase scenarios across train and test.
- Why ranking scores and classifier probabilities are not calibrated confidence.
- Why retrieval should remain independent of classification.
- Why citation validity is weaker than citation entailment.
- Which evaluation gaps need closing before any real-world deployment.
