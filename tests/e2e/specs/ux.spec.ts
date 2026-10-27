// Lot 5 : accessibilite, reglages, clavier, interface jamais bloquee pendant une
// analyse, editeur a 1024 x 768, parcours mobile. Positions dediees.
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

const KEYS_FEN = 'r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3';
const BUSY_FEN = 'r1bq1rk1/ppp2ppp/2np1n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 7';
const MOBILE_FEN = 'rnbqkb1r/pppp1ppp/5n2/4p3/4P3/2N5/PPPP1PPP/R1BQKBNR w KQkq - 2 3';
const TREE_FEN = 'rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2';

async function abandonOpenSessionsOn(page: Page, fen: string) {
  const history = await (await page.request.get('/api/v1/history?limit=200')).json();
  for (const item of history.items as { id: string; state: string; fen: string }[]) {
    if (item.state !== 'active' || item.fen !== fen) continue;
    const s = await (await page.request.get(`/api/v1/sessions/${item.id}`)).json();
    await page.request.post(`/api/v1/sessions/${item.id}/abandon`, { data: { expected_revision: s.revision } });
  }
}

async function positionId(page: Page, fen: string): Promise<string> {
  return (await (await page.request.post('/api/v1/positions', { data: { source: 'fen', fen } })).json()).id;
}

async function retain(page: Page, fen: string) {
  await page.goto('/#/positions');
  await page.getByLabel('FEN', { exact: true }).fill(fen);
  await page.getByRole('button', { name: 'Charger' }).click();
  await page.getByRole('button', { name: 'Retenir cette position' }).click();
  await expect(page.getByTestId('retained-fen')).toHaveText(fen);
}

async function seriousViolations(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
  return result.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id} (${v.impact}) : ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}`);
}

test('@mobile accessibilite : aucune violation WCAG A/AA grave sur les pages principales', async ({ page }) => {
  test.setTimeout(90_000);
  await abandonOpenSessionsOn(page, TREE_FEN);
  const pid = await positionId(page, TREE_FEN);
  const session = await (await page.request.post('/api/v1/sessions', {
    data: { position_id: pid, mode: 'tree', start_analysis_in_background: false },
  })).json();
  try {
    for (const hash of ['#/positions', '#/history', '#/settings', `#/session/${session.id}`, `#/study/${pid}`]) {
      await page.goto('/' + hash);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      await page.waitForLoadState('networkidle');
      expect(await seriousViolations(page), hash).toEqual([]);
    }
  } finally {
    const s = await (await page.request.get(`/api/v1/sessions/${session.id}`)).json();
    await page.request.post(`/api/v1/sessions/${session.id}/abandon`, { data: { expected_revision: s.revision } });
  }
});

test('reglages : valeurs proposees en etude libre et point de vue des evaluations', async ({ page }) => {
  await page.goto('/#/settings');
  try {
    await page.getByLabel('Profondeur cible (etude libre)').fill('33');
    await page.getByRole('button', { name: 'Enregistrer les reglages' }).click();
    // Bornes verifiees par le serveur, message rattache au champ.
    await expect(page.getByRole('alert').filter({ hasText: 'entre 8 et 32' })).toBeVisible();
    await page.getByLabel('Profondeur cible (etude libre)').fill('12');
    await page.getByLabel('Point de vue des evaluations').selectOption('side_to_move');
    await page.getByRole('button', { name: 'Enregistrer les reglages' }).click();
    await expect(page.getByText('Reglages enregistres.')).toBeVisible();
    await expect(page.getByTestId('engine-applied')).toContainText('thread');

    await page.goto(`/#/study/${await positionId(page, KEYS_FEN)}`);
    await expect(page.getByLabel('Profondeur cible')).toHaveValue('12');
    await page.getByRole('button', { name: 'Analyser' }).click();
    await expect(page.getByTestId('job-state')).toHaveAttribute('data-state', 'complete_depth', { timeout: 60_000 });
    await expect(page.locator('table.lines th', { hasText: 'Eval. (camp au trait)' })).toBeVisible();
    await expect(page.getByText(/point de vue du camp au trait/).first()).toBeVisible();
  } finally {
    await page.request.put('/api/v1/settings', { data: { reset: true } });
  }
});

test('clavier : tableau des variantes et arbre de seance, abandon confirme', async ({ page }) => {
  test.setTimeout(120_000);
  // Tableau des variantes : fleches bas (variante) puis droite (coup suivant).
  await page.goto(`/#/study/${await positionId(page, KEYS_FEN)}`);
  await page.getByLabel('Profondeur cible').fill('10');
  await page.getByRole('button', { name: 'Analyser' }).click();
  await expect(page.getByTestId('job-state')).toHaveAttribute('data-state', 'complete_depth', { timeout: 60_000 });
  const table = page.getByRole('group', { name: /Tableau des variantes/ });
  await table.focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.locator('table.lines tr[aria-selected="true"]')).toHaveAttribute('data-rank', '1');
  await expect(page.getByTestId('pv-cursor')).toHaveText(/^1\//);
  await page.keyboard.press('ArrowRight');
  await expect(page.getByTestId('pv-cursor')).toHaveText(/^2\//);
  await page.keyboard.press('ArrowDown');
  await expect(page.locator('table.lines tr[aria-selected="true"]')).toHaveAttribute('data-rank', '2');

  // Arbre de seance : droite = suite, bas = variante soeur, gauche = retour.
  await abandonOpenSessionsOn(page, TREE_FEN);
  await retain(page, TREE_FEN);
  await page.getByRole('button', { name: 'Construire mon arbre (C)' }).click();
  // Chaque ajout doit etre termine (champ vide) avant le suivant : la reponse
  // du serveur selectionne le nouveau coup.
  const add = async (move: string) => {
    await page.getByLabel('Coup (SAN ou UCI)').fill(move);
    await page.getByRole('button', { name: 'Ajouter', exact: true }).click();
    await expect(page.getByLabel('Coup (SAN ou UCI)')).toHaveValue('');
  };
  await add('Nf3');
  await add('d6');
  await page.getByRole('button', { name: 'Position de depart' }).click();
  await add('Nc3');
  const moves = page.getByLabel('Partie et variantes');
  await moves.focus();
  await page.keyboard.press('Home');
  await page.keyboard.press('ArrowRight');
  await expect(moves.locator('[aria-current="true"]')).toHaveText('2. Nf3');
  await page.keyboard.press('ArrowRight');
  // Renumerote : la variante 2. Nc3 s'intercale avant lui dans le texte.
  await expect(moves.locator('[aria-current="true"]')).toHaveText('2... d6');
  await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('ArrowDown');
  await expect(moves.locator('[aria-current="true"]')).toHaveText('2. Nc3');

  await page.getByRole('button', { name: 'Abandonner la seance' }).click();
  const dialog = page.getByRole('alertdialog', { name: 'Abandonner la seance ?' });
  await expect(dialog).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(page.getByTestId('session-state')).toHaveText('en cours');
  await page.getByRole('button', { name: 'Abandonner la seance' }).click();
  await page.getByRole('button', { name: 'Oui, abandonner' }).click();
  await expect(page.getByTestId('session-state')).toHaveText('abandonnee');
});

test('analyse active : l interface reste fluide pendant le flux de resultats', async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto(`/#/study/${await positionId(page, BUSY_FEN)}`);
  await page.getByLabel('Profondeur cible').fill('32');
  await page.getByLabel('Budget (s)').fill('60');
  await page.getByRole('button', { name: 'Analyser' }).click();
  const state = page.getByTestId('job-state');
  await expect(state).toHaveAttribute('data-state', 'running', { timeout: 30_000 });
  await expect(page.locator('table.lines tbody tr')).toHaveCount(20, { timeout: 30_000 });
  await page.evaluate(() => {
    const w = window as unknown as { longTasks: number[] };
    w.longTasks = [];
    new PerformanceObserver((list) => { for (const e of list.getEntries()) w.longTasks.push(e.duration); })
      .observe({ type: 'longtask' });
  });
  // Pendant ~8 s de flux : selection de lignes et navigation, chaque action
  // visible a l'ecran en moins de 500 ms.
  const rows = page.locator('table.lines tbody tr');
  for (let i = 0; i < 8; i++) {
    await rows.nth(i % 5).click();
    await expect(rows.nth(i % 5)).toHaveAttribute('aria-selected', 'true', { timeout: 500 });
    await page.getByRole('button', { name: 'Coup suivant' }).click();
    await expect(page.getByTestId('pv-cursor')).toHaveText(/^2\//, { timeout: 500 });
    await page.waitForTimeout(500);
  }
  await expect(state).toHaveAttribute('data-state', 'running');
  const longTasks = await page.evaluate(() => (window as unknown as { longTasks: number[] }).longTasks);
  expect(Math.max(0, ...longTasks), `taches longues : ${longTasks.join(', ')}`).toBeLessThan(200);
  await page.getByRole('button', { name: 'Arreter' }).click();
  await expect(state).toHaveAttribute('data-state', 'cancelled', { timeout: 15_000 });
});

test('editeur : tout tient dans la fenetre, sans defilement', async ({ page }) => {
  await page.goto('/#/positions');
  await page.getByRole('tab', { name: 'Editeur' }).click();
  const validate = page.getByRole('button', { name: 'Valider cette position' });
  await expect(validate).toBeVisible();
  const viewport = page.viewportSize()!;
  for (const target of [validate, page.locator('[aria-label="Pieces blanches"]'), page.locator('.editor .board, .editor [data-square="h1"]').first()]) {
    const box = (await target.boundingBox())!;
    expect(box.y + box.height, await target.evaluate((e) => e.outerHTML.slice(0, 60))).toBeLessThanOrEqual(viewport.height);
  }
});

test('@mobile seance complete sur telephone, sans debordement horizontal', async ({ page }) => {
  test.setTimeout(200_000);
  await abandonOpenSessionsOn(page, MOBILE_FEN);
  await retain(page, MOBILE_FEN);
  await page.getByRole('button', { name: 'Construire mon arbre (C)' }).click();
  await expect(page).toHaveURL(/#\/session\//);
  await page.getByLabel('Coup (SAN ou UCI)').fill('Bc4');
  await page.getByRole('button', { name: 'Ajouter', exact: true }).click();
  await expect(page.getByRole('button', { name: '3. Bc4' })).toBeVisible();
  await page.getByRole('button', { name: 'Terminer mon calcul' }).click();
  await page.getByRole('button', { name: 'Soumettre ma tentative' }).click();
  await expect(page.getByTestId('preparation')).toContainText('prete', { timeout: 150_000 });
  await page.getByRole('button', { name: 'Reveler' }).click();
  await expect(page.getByRole('region', { name: 'Diagnostics' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Variantes Stockfish' })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.screenshot({ path: `results/screens/${test.info().project.name}-session.png`, fullPage: true });
});
