// Lot 1 (DoD) : depuis un PGN avec variante, choisir un noeud, voir sa position
// et conserver son contexte ; le retrouver apres rechargement (persistance).
// La base du VPS persiste entre deux executions : les tests ne supposent jamais
// une base vide (un meme contexte renvoie le meme instantane).
import { expect, test, type Page } from '@playwright/test';

async function drag(page: Page, from: string, to: string) {
  // Voir spike.spec.ts : attendre la piece et la fin de l'animation.
  await expect(page.locator(`[data-square="${from}"] [data-piece]`)).toBeVisible();
  await page.waitForTimeout(200);
  await page.locator(`[data-square="${from}"]`).scrollIntoViewIfNeeded();
  const a = await page.locator(`[data-square="${from}"]`).boundingBox();
  const b = await page.locator(`[data-square="${to}"]`).boundingBox();
  if (!a || !b) throw new Error('case introuvable');
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(a.x + a.width / 2 + 5, a.y + a.height / 2 + 5, { steps: 3 });
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 12 });
  await page.mouse.up();
  // dnd-kit bloque tout clic sur le document pendant 50 ms apres un depot
  // (@dnd-kit/core, AbstractPointerSensor.detach) : imperceptible pour un humain,
  // mais Playwright clique plus vite.
  await page.waitForTimeout(100);
}

async function importPgn(page: Page, pgn: string) {
  await page.getByRole('tab', { name: 'PGN' }).click();
  await page.getByLabel('PGN', { exact: true }).fill(pgn);
  await page.getByRole('button', { name: 'Importer' }).click();
  await expect(page.getByLabel('Partie et variantes')).toBeVisible();
}

const retained = (page: Page) => page.getByRole('region', { name: 'Position retenue' });

test.beforeEach(async ({ page }) => {
  await page.goto('/');
});

test('PGN : noeud de sous-variante retenu avec son historique, retrouve apres rechargement', async ({ page }) => {
  await importPgn(page, '[Event "Lot 1"]\n\n1. e4 e5 (1... c5 2. c3 d5) 2. Nf3 *\n');
  const moves = page.getByLabel('Partie et variantes');
  await moves.getByRole('button', { name: 'd5', exact: true }).click();
  await expect(page.locator('[data-square="d5"] [data-piece="bP"]')).toBeVisible();
  await expect(page.locator('[data-square="c5"] [data-piece="bP"]')).toBeVisible();

  await page.getByRole('button', { name: 'Retenir cette position' }).click();
  await expect(page.getByTestId('retained-history')).toHaveText('1. e4 c5 2. c3 d5');
  await expect(page.getByTestId('retained-history-status')).toContainText('historique complet');
  const id = await retained(page).getAttribute('data-position-id');
  expect(id).toBeTruthy();

  // Rechargement complet : rien ne vient de l'etat du navigateur.
  await page.reload();
  await expect(retained(page)).toContainText('Aucune');
  await page.locator(`.recent [data-position-id="${id}"]`).click();
  await expect(page.getByTestId('retained-history')).toHaveText('1. e4 c5 2. c3 d5');
  await expect(page.locator('[data-square="d5"] [data-piece="bP"]')).toBeVisible();
  await expect(page.locator('.board[data-mode="locked"]')).toBeVisible();
});

test('FEN + coups joues sur l echiquier : historique depuis la position initiale', async ({ page }) => {
  await page.getByRole('button', { name: 'Charger' }).click();
  await drag(page, 'e2', 'e4');
  await expect(page.getByText('Coups joues depuis cette FEN : e4')).toBeVisible();
  await drag(page, 'e7', 'e5');
  await expect(page.getByText('Coups joues depuis cette FEN : e4 e5')).toBeVisible();
  await page.getByRole('button', { name: 'Retenir cette position' }).click();
  await expect(page.getByTestId('retained-history')).toHaveText('1. e4 e5');
  await expect(page.getByTestId('retained-history-status')).toContainText('historique complet');
});

test('repetition connue grace a l historique PGN', async ({ page }) => {
  await importPgn(page, '[Event "Rep"]\n\n1. Nf3 Nf6 2. Ng1 Ng8 3. Nf3 Nf6 4. Ng1 Ng8 *\n');
  const moves = page.getByLabel('Partie et variantes');
  await moves.getByRole('button', { name: 'Ng8', exact: true }).last().click();
  await page.getByRole('button', { name: 'Retenir cette position' }).click();
  await expect(retained(page)).toContainText('nulle reclamable (triple repetition)');
});

test('editeur : position sans historique, refus explique si incoherente', async ({ page }) => {
  await page.getByRole('tab', { name: 'Editeur' }).click();
  await page.getByRole('button', { name: 'Vider' }).click();
  for (const [piece, square] of [['wK', 'e1'], ['bK', 'e8'], ['wR', 'a1']] as const) {
    const source = page.locator(`[aria-label="Pieces ${piece[0] === 'w' ? 'blanches' : 'noires'}"] [data-piece="${piece}"]`);
    await source.scrollIntoViewIfNeeded();
    const a = await source.boundingBox();
    const b = await page.locator(`[data-square="${square}"]`).boundingBox();
    await page.mouse.move(a!.x + a!.width / 2, a!.y + a!.height / 2);
    await page.mouse.down();
    await page.mouse.move(a!.x + a!.width / 2 + 5, a!.y + a!.height / 2 + 5, { steps: 3 });
    await page.mouse.move(b!.x + b!.width / 2, b!.y + b!.height / 2, { steps: 12 });
    await page.mouse.up();
    await page.waitForTimeout(100); // voir drag() : blocage des clics par dnd-kit
  }
  // Le dernier depot doit etre pris en compte avant de cliquer ailleurs.
  await expect(page.locator('.fen')).toHaveText('4k3/8/8/8/8/8/8/R3K3 w KQkq - 0 1');
  // Roques KQkq par defaut : impossibles ici. Le serveur refuse, on reste dans l'editeur.
  await page.getByRole('button', { name: 'Valider cette position' }).click();
  await expect(page.getByRole('alert')).toContainText('BAD_CASTLING_RIGHTS');
  await expect(page.getByRole('button', { name: 'Vider' })).toBeVisible();

  await page.getByLabel('Roques').fill('Q');
  await page.getByRole('button', { name: 'Valider cette position' }).click();
  await expect(page.getByTestId('retained-fen')).toHaveText('4k3/8/8/8/8/8/8/R3K3 w Q - 0 1');
  await expect(page.getByTestId('retained-history-status')).toContainText('historique inconnu');
  await expect(retained(page)).toContainText('modifiee librement');
});

test('PGN a plusieurs parties : choix de la partie', async ({ page }) => {
  await importPgn(page, '[White "Alice"]\n[Black "Bob"]\n\n1. d4 *\n\n[White "Carla"]\n[Black "Dan"]\n\n1. c4 e5 *\n');
  const select = page.getByLabel('Partie', { exact: true });
  await expect(select.locator('option')).toHaveText(['1. Alice - Bob', '2. Carla - Dan']);
  await select.selectOption({ label: '2. Carla - Dan' });
  const moves = page.getByLabel('Partie et variantes');
  await expect(moves).toContainText('1. c4 e5');
  await expect(moves).not.toContainText('d4');
});
