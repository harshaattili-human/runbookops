import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/dm-sans/latin-400.css';
import '@fontsource/dm-sans/latin-600.css';
import '@fontsource/manrope/latin-700.css';
import {
  Activity,
  ArrowRight,
  BookOpen,
  Check,
  ChevronRight,
  Clock3,
  FileText,
  FlaskConical,
  GitBranch,
  Layers3,
  Search,
  ShieldCheck,
  Terminal,
  X,
} from 'lucide-react';
import './style.css';

type Source = {
  id: string;
  document: string;
  title: string;
  section: string;
  start_line: number;
  end_line: number;
  text: string;
  score: number;
  matched_terms: string[];
};
type Routing = {
  category: string;
  suggested_category: string;
  score: number;
  needs_review: boolean;
  distribution: { category: string; score: number }[];
  signals: { term: string; contribution: number }[];
};
type Result = {
  request_id: string;
  query: string;
  routing: Routing;
  answer: string;
  citations: string[];
  sources: Source[];
  mode: string;
  warning: string | null;
  duration_ms: number;
};
type Evaluation = {
  classifier: {
    macro_f1: number;
    split: string;
    errors: { id: string; text: string; expected: string; predicted: string }[];
  };
  retrieval: {
    hit_rate_at_4_chunks: number;
    negative_abstention_rate: number;
    positive_cases: number;
    negative_cases: number;
  };
  limitations: string[];
};
type Overview = {
  documents: number;
  chunks: number;
  incidents: number;
  categories: string[];
  evaluation: Evaluation | null;
  runbooks: { id: string; title: string }[];
};
const samples = [
  {
    name: 'Connection pool',
    area: 'DATABASE',
    text: 'Requests time out acquiring a HikariPool database connection. Active connections are at the maximum and pending requests keep rising.',
  },
  {
    name: 'Consumer backlog',
    area: 'MESSAGING',
    text: 'Kafka consumer lag is increasing and the group keeps rebalancing. What should we inspect before considering a replay?',
  },
  {
    name: 'Stalled approval',
    area: 'WORKFLOW',
    text: 'A Camunda workflow service task exhausted its retries and the process instance is stuck after a downstream error.',
  },
  {
    name: 'Outside the corpus',
    area: 'ABSTENTION',
    text: 'How do I bake chocolate brownies for a birthday party?',
  },
];
const label = (v: string) => v.replaceAll('-', ' ');
const percent = (v: number) => (v * 100).toFixed(1) + '%';
const recordedDemo = Boolean((window as Window & { RUNBOOKOPS_DEMO?: boolean }).RUNBOOKOPS_DEMO);

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  if (!response.ok)
    throw new Error(`Request failed (${response.status}). Check the API and try again.`);
  return response.json();
}

function App() {
  const [page, setPage] = useState<'workbench' | 'library' | 'evaluation'>('workbench');
  const [query, setQuery] = useState(samples[0].text);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [useLlm, setUseLlm] = useState(false);
  const [document, setDocument] = useState<{ id: string; content: string } | null>(null);
  const [docError, setDocError] = useState('');
  const [filter, setFilter] = useState('');
  useEffect(() => {
    request<Overview>('/api/overview')
      .then(setOverview)
      .catch((e) => setError(e.message));
  }, []);
  async function analyze(text = query) {
    if (busy) return;
    setBusy(true);
    setError('');
    setResult(null);
    try {
      setResult(
        await request<Result>('/api/triage', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: text, use_llm: useLlm }),
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed.');
    } finally {
      setBusy(false);
    }
  }
  async function openDocument(id: string) {
    setDocError('');
    try {
      setDocument(
        await request<{ id: string; content: string }>(`/api/runbooks/${encodeURIComponent(id)}`),
      );
    } catch (e) {
      setDocError(e instanceof Error ? e.message : 'Could not open runbook.');
    }
  }
  const evaluation = overview?.evaluation;
  return (
    <div className="shell">
      <aside className="sidebar">
        <a
          href="#"
          className="brand"
          onClick={(e) => {
            e.preventDefault();
            setPage('workbench');
          }}
        >
          <span className="brand-icon">
            <Layers3 size={22} />
          </span>
          Runbook<span>Ops</span>
        </a>
        <div className="workspace-label">ENGINEERING WORKSPACE</div>
        <nav aria-label="Main navigation">
          <button
            className={page === 'workbench' ? 'active' : ''}
            onClick={() => setPage('workbench')}
          >
            <Terminal size={18} />
            Incident workbench
          </button>
          <button className={page === 'library' ? 'active' : ''} onClick={() => setPage('library')}>
            <BookOpen size={18} />
            Runbook library<span className="nav-count">{overview?.documents ?? '—'}</span>
          </button>
          <button
            className={page === 'evaluation' ? 'active' : ''}
            onClick={() => setPage('evaluation')}
          >
            <FlaskConical size={18} />
            Evaluation
          </button>
        </nav>
        <div className="sidebar-note">
          <span className="tiny-label">THE APPROACH</span>
          <h3>Evidence before action.</h3>
          <p>
            Inspect the source.
            <br />
            Understand the signal.
            <br />
            Keep the engineer in control.
          </p>
          <ShieldCheck size={23} />
        </div>
        <div className="profile">
          <span className="avatar">HA</span>
          <div>
            <strong>Harsha Attili</strong>
            <small>Independent portfolio project</small>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span>
            Workspace <ChevronRight size={14} />{' '}
            <strong>
              {page === 'workbench'
                ? 'Incident triage'
                : page === 'library'
                  ? 'Knowledge base'
                  : 'Model evaluation'}
            </strong>
          </span>
          <span className="status">
            <i /> {recordedDemo ? 'Recorded demo' : 'Synthetic demo'}
          </span>
        </header>
        <div className="content">
          <div className="eyebrow">
            RUNBOOKOPS /{' '}
            {page === 'workbench' ? 'INVESTIGATE' : page === 'library' ? 'EXPLORE' : 'MEASURE'}
          </div>
          <div className="page-heading">
            <div>
              <h1>
                {page === 'workbench'
                  ? 'From alert to understanding.'
                  : page === 'library'
                    ? 'A source for every suggestion.'
                    : 'Measure what actually works.'}
              </h1>
              <p>
                {page === 'workbench'
                  ? 'A calmer starting point for the next incident.'
                  : page === 'library'
                    ? 'Original, fictional runbooks. Read the evidence in full.'
                    : 'Reproducible results, with the limitations kept in view.'}
              </p>
            </div>
            <span className="version">v0.1 / LOCAL FIRST</span>
          </div>
          {error && (
            <div role="alert" className="alert">
              {error}
            </div>
          )}
          {docError && (
            <div role="alert" className="alert">
              {docError}
            </div>
          )}
          {recordedDemo && (
            <div className="inline-note">
              Interactive replay of actual API results. Choose a sample scenario; run the project
              locally to analyze your own text.
            </div>
          )}
          {page === 'workbench' && (
            <>
              <div className="stats-row">
                <div>
                  <BookOpen size={18} />
                  <strong>{overview?.documents ?? '—'}</strong>
                  <span>runbooks</span>
                </div>
                <div>
                  <Layers3 size={18} />
                  <strong>{overview?.chunks ?? '—'}</strong>
                  <span>evidence passages</span>
                </div>
                <div>
                  <GitBranch size={18} />
                  <strong>{overview?.categories.length ?? '—'}</strong>
                  <span>service areas</span>
                </div>
                <div>
                  <ShieldCheck size={18} />
                  <span>Human review built in</span>
                </div>
              </div>
              <div className="work-grid">
                <section className="investigation">
                  <form
                    className="panel input-panel"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void analyze();
                    }}
                  >
                    <div className="section-top">
                      <h2>
                        <span className="step">01</span>Describe the incident
                      </h2>
                      <span className="subtle">No raw secrets or customer data</span>
                    </div>
                    <label className="sr-only" htmlFor="incident">
                      Incident description
                    </label>
                    <textarea
                      id="incident"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      minLength={8}
                      maxLength={2000}
                      placeholder="What failed? Include the component, error, and recent change."
                      required
                      disabled={busy}
                      readOnly={recordedDemo}
                    />
                    <div className="input-footer">
                      <label className="toggle">
                        <input
                          type="checkbox"
                          checked={useLlm}
                          onChange={(e) => setUseLlm(e.target.checked)}
                          disabled={busy || recordedDemo}
                        />
                        Use configured local LLM
                      </label>
                      <button className="primary" disabled={busy || query.trim().length < 8}>
                        {busy ? 'Analyzing…' : 'Analyze incident'}
                        <ArrowRight size={17} />
                      </button>
                    </div>
                  </form>
                  <div className="examples">
                    <span>TRY A SCENARIO</span>
                    {samples.map((s) => (
                      <button
                        disabled={busy}
                        key={s.name}
                        onClick={() => {
                          setQuery(s.text);
                          void analyze(s.text);
                        }}
                      >
                        {s.name}
                        <ChevronRight size={13} />
                      </button>
                    ))}
                  </div>
                  <section className="panel answer-panel" aria-live="polite" aria-busy={busy}>
                    <div className="section-top">
                      <h2>
                        <span className="step">02</span>Review the evidence
                      </h2>
                      {result && (
                        <span className="mode">
                          {result.mode === 'local-llm'
                            ? 'LOCAL LLM'
                            : result.mode === 'extractive'
                              ? 'SOURCE EXTRACT'
                              : 'NEEDS CONTEXT'}
                        </span>
                      )}
                    </div>
                    {busy ? (
                      <div className="empty-state">
                        <Activity className="pulse" size={30} />
                        <h3>Following the signals…</h3>
                        <p>Classifying the incident and finding supporting passages.</p>
                      </div>
                    ) : !result ? (
                      <div className="empty-state">
                        <Search size={32} />
                        <h3>Start with what you know.</h3>
                        <p>
                          Describe an incident or choose a scenario above.
                          <br />
                          Every result comes with the source behind it.
                        </p>
                      </div>
                    ) : (
                      <>
                        <div className="result-heading">
                          <span
                            className={result.sources.length ? 'result-dot' : 'result-dot muted'}
                          />
                          <h3>
                            {result.sources.length
                              ? 'A useful place to start'
                              : 'More context needed'}
                          </h3>
                          <span>
                            <Clock3 size={13} />
                            {result.duration_ms} ms
                          </span>
                        </div>
                        <div className="answer-text">{result.answer}</div>
                        {result.warning && <div className="inline-note">{result.warning}</div>}
                        <div className="source-list">
                          {result.sources.map((s, i) => (
                            <button
                              className="source-card"
                              key={s.id}
                              onClick={() => void openDocument(s.document)}
                            >
                              <span className="source-number">
                                {String(i + 1).padStart(2, '0')}
                              </span>
                              <div>
                                <strong>{s.title}</strong>
                                <small>
                                  {s.section} · lines {s.start_line}–{s.end_line}
                                  {result.citations.includes(s.id) ? ' · cited in answer' : ''}
                                </small>
                                <span className="tags">
                                  {s.matched_terms.slice(0, 5).map((t) => (
                                    <em key={t}>{t}</em>
                                  ))}
                                </span>
                              </div>
                              <ChevronRight size={17} />
                            </button>
                          ))}
                        </div>
                        <div className="result-footer">
                          <ShieldCheck size={14} /> Investigation guidance only. Review before
                          acting.<span>{result.request_id}</span>
                        </div>
                      </>
                    )}
                  </section>
                </section>
                <aside className="inspector">
                  <div className="panel routing-panel">
                    <div className="tiny-label">MODEL INSPECTOR</div>
                    <h2>Why this route?</h2>
                    <p className="inspector-copy">
                      A lightweight classifier suggests where to start. Retrieval searches every
                      service area.
                    </p>
                    {result ? (
                      <>
                        <div className="route-label">{label(result.routing.category)}</div>
                        <div className="score-line">
                          <span>Top model score</span>
                          <strong>{percent(result.routing.score)}</strong>
                        </div>
                        <div className="distribution">
                          {result.routing.distribution.map((d) => (
                            <div key={d.category}>
                              <div>
                                <span>{label(d.category)}</span>
                                <small>{percent(d.score)}</small>
                              </div>
                              <span className="track">
                                <span style={{ width: percent(d.score) }} />
                              </span>
                            </div>
                          ))}
                        </div>
                        <h3 className="signal-title">Contributing terms</h3>
                        <div className="signal-tags">
                          {result.routing.signals.map((s) => (
                            <span key={s.term}>{s.term}</span>
                          ))}
                        </div>
                        <p className="fine-print">
                          Scores are uncalibrated model outputs, not a measure of real-world
                          accuracy. Weak matches require review.
                        </p>
                      </>
                    ) : (
                      <div className="inspector-empty">
                        <GitBranch size={26} />
                        <p>
                          Routing signals appear
                          <br />
                          after an analysis.
                        </p>
                      </div>
                    )}
                  </div>
                  <div className="method-note">
                    <Check size={17} />
                    <div>
                      <strong>No keys needed to start</strong>
                      <p>Default answers quote runbook text. Local LLM synthesis is optional.</p>
                    </div>
                  </div>
                </aside>
              </div>
            </>
          )}
          {page === 'library' && (
            <>
              <div className="library-search">
                <Search size={18} />
                <input
                  aria-label="Filter runbooks"
                  placeholder="Filter runbooks…"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                />
              </div>
              <div className="library-grid">
                {overview?.runbooks
                  .filter((r) => r.title.toLowerCase().includes(filter.toLowerCase()))
                  .map((r, i) => (
                    <button
                      className="panel library-card"
                      key={r.id}
                      onClick={() => void openDocument(r.id)}
                    >
                      <span className="tiny-label">RUNBOOK {String(i + 1).padStart(2, '0')}</span>
                      <FileText size={25} />
                      <h2>{r.title}</h2>
                      <span>
                        Read source <ArrowRight size={16} />
                      </span>
                    </button>
                  ))}
              </div>
            </>
          )}
          {page === 'evaluation' && (
            <>
              {evaluation ? (
                <>
                  <div className="metric-grid">
                    <Metric
                      title="Classifier macro F1"
                      value={evaluation.classifier.macro_f1.toFixed(3)}
                      note="Scenario-grouped cross-validation"
                    />
                    <Metric
                      title="Retrieval hit rate"
                      value={percent(evaluation.retrieval.hit_rate_at_4_chunks)}
                      note={`${evaluation.retrieval.positive_cases} positive smoke cases · top 4 chunks`}
                    />
                    <Metric
                      title="Negative abstention"
                      value={percent(evaluation.retrieval.negative_abstention_rate)}
                      note={`${evaluation.retrieval.negative_cases} out-of-scope smoke cases`}
                    />
                  </div>
                  <section className="panel eval-panel">
                    <h2>Read these numbers in context.</h2>
                    <p>
                      {evaluation.classifier.split}. Paraphrases stay together; preprocessing is
                      fitted only on each training fold.
                    </p>
                    <ul>
                      {evaluation.limitations.map((l) => (
                        <li key={l}>{l}</li>
                      ))}
                    </ul>
                    <code>python -m runbookops.evaluate</code>
                  </section>
                  <section className="panel eval-panel">
                    <h2>Where the classifier struggled</h2>
                    {evaluation.classifier.errors.length ? (
                      evaluation.classifier.errors.map((e) => (
                        <div className="error-row" key={e.id}>
                          <p>{e.text}</p>
                          <span>
                            Expected: {e.expected} · Predicted: {e.predicted}
                          </span>
                        </div>
                      ))
                    ) : (
                      <p>
                        No errors in this small synthetic run. This does not establish real-world
                        reliability.
                      </p>
                    )}
                  </section>
                </>
              ) : (
                <div className="panel eval-panel">
                  Run the evaluation command to generate a report.
                </div>
              )}
            </>
          )}
          <footer className="page-footer">
            <span>Built for understanding, with room to question.</span>
            <span>Python · scikit-learn · React · TypeScript</span>
          </footer>
        </div>
      </main>
      {document && (
        <div className="modal-backdrop" onClick={() => setDocument(null)}>
          <section
            className="document-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Runbook source"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setDocument(null);
            }}
          >
            <header>
              <span>
                <BookOpen size={18} /> {document.id}.md
              </span>
              <button autoFocus aria-label="Close source" onClick={() => setDocument(null)}>
                <X size={20} />
              </button>
            </header>
            <div className="source-lines">
              {document.content.split('\n').map((line, i) => (
                <div key={i}>
                  <span>{i + 1}</span>
                  <pre>{line || ' '}</pre>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
function Metric({ title, value, note }: { title: string; value: string; note: string }) {
  return (
    <div className="panel metric">
      <span className="tiny-label">{title}</span>
      <strong>{value}</strong>
      <p>{note}</p>
    </div>
  );
}
createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
