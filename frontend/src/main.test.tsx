import { render, screen, waitFor } from '@testing-library/react';
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
