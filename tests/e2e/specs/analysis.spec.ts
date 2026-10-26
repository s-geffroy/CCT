// Lot 3 : analyse Stockfish dans le navigateur (vrai moteur du conteneur app).
// Positions dediees, pour ne pas croiser les seances des autres specs : la base
// du VPS persiste entre deux executions.
import { expect, test, type Page } from '@playwright/test';

const KIWIPETE = 'r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1';
const SESSION_FEN = 'r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4';

async function retain(page: Page, fen: string) {
  await page.goto('/#/positions');
  await page.getByLabel('FEN', { exact: true }).fill(fen);
  await page.getByRole('button', { name: 'Charger' }).click();
  await page.getByRole('button', { name: 'Retenir cette position' }).click();
  await expect(page.getByTestId('retained-fen')).toHaveText(fen);
  return (await page.getByRole('region', { name: 'Position retenue' }).getAttribute('data-position-id'))!;
}

test('etude libre : tableau sous l echiquier, couverture annoncee, navigation, arret', async ({ page }) => {
  test.setTimeout(90_000);
  await retain(page, KIWIPETE);
  await page.getByRole('button', { name: 'Etude libre avec Stockfish (A)' }).click();
  await expect(page).toHaveURL(/#\/study\//);

  await page.getByLabel('Profondeur cible').fill('12');
  await page.getByRole('button', { name: 'Analyser' }).click();
  const state = page.getByTestId('job-state');
  await expect(state).toHaveAttribute('data-state', 'complete_depth', { timeout: 60_000 });
  await expect(page.getByTestId('coverage')).toContainText('20 premiers coups sur 48 coups legaux');
  const rows = page.locator('table.lines tbody tr');
  await expect(rows).toHaveCount(20);
  await expect(rows.first().locator('td').nth(3)).toHaveText(/^1[2-9]\/12$|^[2-9]\d\/12$/);

  // Le tableau est bien SOUS l'echiquier (exigence du doc 04).
  const board = await page.locator('.board').first().boundingBox();
  const table = await page.locator('table.lines').boundingBox();
  expect(table!.y).toBeGreaterThan(board!.y + board!.height - 1);

  await rows.first().click();
  await expect(page.getByTestId('pv-cursor')).toHaveText(/^1\//);
  const firstMove = await rows.first().locator('td').nth(1).innerText();
  await expect(page.getByTestId('shown-position')).toContainText(`1. ${firstMove}`);
  await page.getByRole('button', { name: 'Coup suivant' }).click();
  await expect(page.getByTestId('pv-cursor')).toHaveText(/^2\//);

  // Recherche longue, arretee a la demande.
  await page.getByLabel('Profondeur cible').fill('32');
  await page.getByLabel('Budget (s)').fill('600');
  await page.getByRole('button', { name: 'Analyser' }).click();
  await expect(state).toHaveAttribute('data-state', 'running', { timeout: 30_000 });
  await page.getByRole('button', { name: 'Arreter' }).click();
  await expect(state).toHaveAttribute('data-state', 'cancelled', { timeout: 15_000 });
});

test('seance : analyse refusee pendant le calcul, reference montree apres revelation', async ({ page }) => {
  test.setTimeout(150_000);
  const positionId = await retain(page, SESSION_FEN);
  await page.getByRole('button', { name: 'Construire mon arbre (C)' }).click();
  await expect(page).toHaveURL(/#\/session\//);
  const sessionUrl = page.url();
  await expect(page.getByTestId('preparation')).toBeVisible();

  // Tentative de contournement : etude libre de la meme position pendant la seance.
  await page.goto(`/#/study/${positionId}`);
  await page.getByRole('button', { name: 'Analyser' }).click();
  await expect(page.getByRole('alert')).toContainText('SESSION_IN_PROGRESS');

  await page.goto(sessionUrl);
  await page.getByLabel('Coup (SAN ou UCI)').fill('Ng5');
  await page.getByRole('button', { name: 'Ajouter', exact: true }).click();
  await page.getByRole('button', { name: 'Terminer mon calcul' }).click();
  await page.getByRole('button', { name: 'Soumettre ma tentative' }).click();
  // Attendre que la reference soit prete (sans rien en montrer), puis reveler.
  // L'indicateur suit le flux SSE (etat seul avant revelation).
  await expect(page.getByTestId('preparation')).toContainText('prete', { timeout: 120_000 });
  await page.getByRole('button', { name: 'Reveler' }).click();
  await expect(page.getByRole('region', { name: 'Variantes Stockfish' })).toBeVisible();
  await expect(page.getByTestId('job-state')).toHaveAttribute('data-state', /complete_depth|budget_exhausted/);
  await expect(page.locator('table.lines tbody tr').first()).toBeVisible();
  await page.screenshot({ path: `results/screens/${test.info().project.name}-reference.png`, fullPage: true });
});
