import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, test, vi } from 'vitest';

import { App } from './main';

const overview = {
  documents: 1,
  chunks: 4,
  incidents: 90,
  categories: ['database'],
  evaluation: null,
  runbooks: [{ id: 'database-pool', title: 'Database connection pool exhaustion' }],
};

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function mockApi(runbookStatus = 200) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = String(input);
    if (path === '/api/overview') return response(overview);
    if (path === '/api/runbooks/database-pool') {
      return response(
        { id: 'database-pool', content: '# Database connection pool exhaustion\n\n## Symptoms' },
        runbookStatus,
      );
    }
    return response({ detail: 'Unexpected test request' }, 404);
  });
}

async function openLibrary(user: ReturnType<typeof userEvent.setup>) {
  render(<App />);
  await user.click(await screen.findByRole('button', { name: /Runbook library/ }));
  return screen.findByRole('button', { name: /Database connection pool exhaustion/ });
}

describe('source inspection', () => {
  beforeEach(() => mockApi());

  test('contains keyboard focus, closes with Escape, and restores the source card', async () => {
    const user = userEvent.setup();
    const sourceCard = await openLibrary(user);
    sourceCard.focus();
    await user.click(sourceCard);

    const dialog = await screen.findByRole('dialog', { name: 'database-pool.md' });
    const close = screen.getByRole('button', { name: 'Close source' });
    expect(window.document.activeElement).toBe(close);
    expect(dialog.contains(window.document.activeElement)).toBe(true);

    const shell = dialog.closest('.shell');
    expect(shell).not.toBeNull();
    const backdrop = dialog.parentElement;
    const background = Array.from(shell?.children ?? []).filter((element) => element !== backdrop);
    expect(background.length).toBeGreaterThan(0);
    expect(background.every((element) => element.hasAttribute('inert'))).toBe(true);

    await user.tab();
    expect(window.document.activeElement).toBe(close);
    await user.tab({ shift: true });
    expect(window.document.activeElement).toBe(close);

    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(window.document.activeElement).toBe(sourceCard);
    expect(background.every((element) => !element.hasAttribute('inert'))).toBe(true);
  });

  test('keeps a failed source request on the current page with an alert', async () => {
    vi.restoreAllMocks();
    mockApi(500);
    const user = userEvent.setup();
    const sourceCard = await openLibrary(user);
    sourceCard.focus();
    await user.click(sourceCard);

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Request failed (500). Check the API and try again.',
    );
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(window.document.activeElement).toBe(sourceCard);
  });
});

test('starts with an explicit empty analysis state and supports keyboard navigation', async () => {
  mockApi();
  const user = userEvent.setup();
  render(<App />);

  expect(screen.getByRole('heading', { name: 'No analysis yet' })).toBeTruthy();
  const library = await screen.findByRole('button', { name: /Runbook library/ });
  library.focus();
  await user.keyboard('{Enter}');
  expect(await screen.findByRole('heading', { name: 'Runbook library' })).toBeTruthy();

  const evaluation = screen.getByRole('button', { name: 'Evaluation' });
  evaluation.focus();
  await user.keyboard('{Enter}');
  expect(screen.getByRole('heading', { name: 'Evaluation results' })).toBeTruthy();
  expect(screen.getByText('Run the evaluation command to generate a report.')).toBeTruthy();
});

const originalHash = 'a'.repeat(64);
const updatedHash = 'b'.repeat(64);
const sourceContent = '# Database connection pool exhaustion\n\nInspect pool wait metrics.';

function analysis(documentHash: string) {
  return {
    request_id: 'synthetic-version-check',
    answer: 'Inspect pool wait metrics.',
    citations: ['database-pool:1'],
    sources: [
      {
        id: 'database-pool:1',
        document: 'database-pool',
        document_hash: documentHash,
        title: 'Database connection pool exhaustion',
        section: 'Investigation',
        start_line: 3,
        end_line: 3,
        text: 'Inspect pool wait metrics.',
        score: 0.8,
        document_coverage: 0.8,
        matched_terms: ['pool'],
      },
    ],
    routing: {
      category: 'database',
      suggested_category: 'database',
      score: 0.8,
      needs_review: false,
      distribution: [],
      signals: [],
    },
    mode: 'extractive',
    warning: null,
    duration_ms: 1,
  };
}

function versionedApi(status: number, returnedHash = originalHash) {
  let triageCalls = 0;
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = String(input);
    if (path === '/api/overview') return response(overview);
    if (path === '/api/triage') {
      triageCalls++;
      return response(analysis(triageCalls === 1 ? originalHash : updatedHash));
    }
    if (path === `/api/runbooks/database-pool?expected_hash=${updatedHash}`) {
      return response({ id: 'database-pool', content: sourceContent, content_hash: updatedHash });
    }
    if (path === `/api/runbooks/database-pool?expected_hash=${originalHash}`) {
      return response(
        { id: 'database-pool', content: sourceContent, content_hash: returnedHash },
        status,
      );
    }
    return response({ detail: 'Unexpected test request' }, 404);
  });
}

async function analyzeSample(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Connection pool' }));
  return screen.findByRole('button', { name: /Database connection pool exhaustion/ });
}

test('opens a cited source with its complete expected hash and restores card focus', async () => {
  const api = versionedApi(200);
  const user = userEvent.setup();
  render(<App />);
  const card = await analyzeSample(user);
  await user.click(card);
  const dialog = await screen.findByRole('dialog');
  expect(within(dialog).getByText('Inspect pool wait metrics.')).toBeTruthy();
  expect(api).toHaveBeenCalledWith(
    `/api/runbooks/database-pool?expected_hash=${originalHash}`,
    undefined,
  );
  await user.keyboard('{Escape}');
  expect(window.document.activeElement).toBe(card);
});

test.each([
  [409, originalHash, 'This runbook changed since the analysis.'],
  [404, originalHash, 'This runbook is no longer available.'],
  [200, updatedHash, 'This runbook changed since the analysis.'],
])(
  'keeps version failures visible and permits a fresh analysis (%i)',
  async (status, hash, message) => {
    versionedApi(status as number, hash as string);
    const user = userEvent.setup();
    render(<App />);
    const card = await analyzeSample(user);
    await user.click(card);
    expect((await screen.findByRole('alert')).textContent).toContain(message);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(window.document.activeElement).toBe(card);

    const refreshedCard = await analyzeSample(user);
    expect(screen.queryByRole('alert')).toBeNull();
    await user.click(refreshedCard);
    expect(await screen.findByRole('dialog')).toBeTruthy();
  },
);
