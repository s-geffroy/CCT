// Validation du spike Lot 0 dans un vrai navigateur : ce que jsdom ne sait pas
// faire (glisser-deposer dnd-kit, promotion, pieces libres) et le contrat
// « aucune ressource hors de l'application » (T17).
import { expect, test, type Page } from '@playwright/test';

const PROMOTION_FEN = '8/4P3/8/8/8/8/8/k6K w - - 0 1';

async function center(page: Page, selector: string) {
  const box = await page.locator(selector).first().boundingBox();
  if (!box) throw new Error(`introuvable : ${selector}`);
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/** Glisser-deposer souris, par petits pas (le capteur dnd-kit veut du mouvement). */
async function drag(page: Page, from: string, to: string | { x: number; y: number }) {
  // Laisser finir l'animation de position de react-chessboard (150 ms) : un
  // glisser commence pendant l'animation est ignore.
  if (from.includes('data-square')) await expect(page.locator(from).locator('[data-piece]')).toBeVisible();
  await page.waitForTimeout(200);
  // La souris n'atteint que la zone visible : ramener la source a l'ecran.
  await page.locator(from).first().scrollIntoViewIfNeeded();
  const a = await center(page, from);
  const b = typeof to === 'string' ? await center(page, to) : to;
  await page.mouse.move(a.x, a.y);
  await page.mouse.down();
  await page.mouse.move(a.x + 5, a.y + 5, { steps: 3 });
  await page.mouse.move(b.x, b.y, { steps: 12 });
  await page.mouse.up();
  // dnd-kit bloque tout clic sur le document pendant 50 ms apres un depot
  // (@dnd-kit/core, AbstractPointerSensor.detach) : imperceptible pour un humain,
  // mais Playwright clique plus vite.
  await page.waitForTimeout(100);
}

// Un seul echiquier visible par onglet.
const sq = (s: string) => `[data-square="${s}"]`;

async function loadFen(page: Page, fen: string) {
  await page.getByLabel('FEN', { exact: true }).fill(fen);
  await page.getByRole('button', { name: 'Charger' }).click();
}

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Chess Calculation Trainer');
});

test('echiquier rendu et moteur annonce', async ({ page }) => {
  await expect(page.locator('[data-square]')).toHaveCount(64);
  await expect(page.locator('.meta')).toContainText('Stockfish 19');
});

test('glisser e2-e4 : coup valide par le serveur, SAN calcule cote serveur', async ({ page }) => {
  await loadFen(page, 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
  await expect(page.getByText(/20 coups legaux/)).toBeVisible();
  const played = page.waitForResponse((r) => r.url().endsWith('/api/v1/moves/play'));
  await drag(page, sq('e2'), sq('e4'));
  expect((await played).status()).toBe(200);
  await expect(page.getByText('Coups joues depuis cette FEN : e4')).toBeVisible();
  await expect(page.locator('[data-square="e4"] [data-piece="wP"]')).toBeVisible();
  await expect(page.locator('[data-square="e2"] [data-piece]')).toHaveCount(0);
});

test('coup illegal refuse : message et position intacte', async ({ page }) => {
  await loadFen(page, 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
  await drag(page, sq('e2'), sq('e5'));
  await expect(page.getByRole('alert')).toContainText('ILLEGAL_MOVE');
  await expect(page.locator('[data-square="e2"] [data-piece="wP"]')).toBeVisible();
  await expect(page.locator('[data-square="e5"] [data-piece]')).toHaveCount(0);
});

test('promotion : choix explicite de la piece, jamais de dame implicite', async ({ page }) => {
  await loadFen(page, PROMOTION_FEN);
  await drag(page, sq('e7'), sq('e8'));
  const dialog = page.getByRole('dialog', { name: 'Choisir la piece de promotion' });
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Cavalier' }).click();
  await expect(page.getByText('Coups joues depuis cette FEN : e8=N')).toBeVisible();
  await expect(page.locator('[data-square="e8"] [data-piece="wN"]')).toBeVisible();
});

test('editeur : piece libre posee, piece retiree hors echiquier, FEN validee', async ({ page }) => {
  await page.getByRole('tab', { name: 'Editeur' }).click();
  await page.getByRole('button', { name: 'Vider' }).click();
  await expect(page.locator('.fen')).toHaveText('8/8/8/8/8/8/8/8 w KQkq - 0 1');

  await drag(page, '[aria-label="Pieces blanches"] [data-piece="wK"]', sq('e1'));
  await drag(page, '[aria-label="Pieces noires"] [data-piece="bK"]', sq('e8'));
  await drag(page, '[aria-label="Pieces blanches"] [data-piece="wQ"]', sq('d4'));
  await expect(page.locator('.fen')).toHaveText('4k3/8/8/8/3Q4/8/8/4K3 w KQkq - 0 1');

  // Retirer la dame : la deposer hors de l'echiquier.
  await drag(page, sq('d4'), { x: 5, y: 5 });
  await expect(page.locator('.fen')).toHaveText('4k3/8/8/8/8/8/8/4K3 w KQkq - 0 1');

  // Roques incoherents : le serveur explique, le client ne juge pas.
  await page.getByRole('button', { name: 'Valider cette position' }).click();
  await expect(page.getByText(/Droits au roque incompatibles/)).toBeVisible();
});

const PGN = `[Event "e2e"]

1. e4 e5 (1... c5 2. Nf3 {<script>window.__xss = 1</script>}) 2. Nf3 Nc6 *
`;

test('PGN a variantes : deux vues, navigation, commentaires inertes', async ({ page }) => {
  await page.getByRole('tab', { name: 'PGN' }).click();
  await page.getByLabel('PGN', { exact: true }).fill(PGN);
  await page.getByRole('button', { name: 'Importer' }).click();

  const inline = page.getByLabel('Partie et variantes');
  await expect(inline).toContainText('1... c5');
  await inline.getByRole('button', { name: '1... c5' }).click();
  await expect(page.locator('[data-square="c5"] [data-piece="bP"]')).toBeVisible();
  await expect(page.locator('[data-square="e5"] [data-piece]')).toHaveCount(0);

  // Le commentaire est affiche en texte, jamais execute.
  await expect(inline).toContainText('<script>');
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();

  // Mode PGN = consultation : l'echiquier ne se manipule pas.
  await expect(page.locator('.board[data-mode="locked"]')).toBeVisible();

  await page.getByLabel('Arbre', { exact: true }).check();
  const tree = page.getByRole('tree');
  await expect(tree).toContainText('2. Nf3');
  await tree.getByText('Nc6', { exact: true }).click();
  await expect(page.locator('[data-square="c6"] [data-piece="bN"]')).toBeVisible();
});

test('aucune ressource hors de l application (fonctionnement hors ligne)', async ({ page, baseURL }) => {
  const foreign: string[] = [];
  page.on('request', (r) => {
    if (!r.url().startsWith(baseURL!) && !r.url().startsWith('data:')) foreign.push(r.url());
  });
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await page.getByRole('tab', { name: 'Editeur' }).click();
  await page.getByRole('tab', { name: 'PGN' }).click();
  expect(foreign).toEqual([]);
});

test('capture des vues pour revue', async ({ page }, testInfo) => {
  await page.getByRole('tab', { name: 'PGN' }).click();
  await page.getByLabel('PGN', { exact: true }).fill(PGN);
  await page.getByRole('button', { name: 'Importer' }).click();
  await page.screenshot({ path: `results/screens/${testInfo.project.name}-pgn.png`, fullPage: true });
  await page.getByRole('tab', { name: 'Editeur' }).click();
  await page.screenshot({ path: `results/screens/${testInfo.project.name}-editeur.png`, fullPage: true });
});
