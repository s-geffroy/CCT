// Lot 2 : seances B et C dans un vrai navigateur, et inspection reseau
// anti-spoiler (doc 14 : « inspecter le reseau avec Playwright, aucune
// PV/score accessible »).
import { expect, test, type Page } from '@playwright/test';

const FORBIDDEN = new Set(['pv', 'pv_uci', 'pv_san', 'score', 'best_move', 'bestmove', 'rank', 'multipv', 'mate',
  'depth', 'seldepth', 'target_move', 'reference', 'reference_tree', 'analysis', 'lines', 'engine_lines']);

function forbiddenKeys(value: unknown, path = '$'): string[] {
  if (Array.isArray(value)) return value.flatMap((v, i) => forbiddenKeys(v, `${path}[${i}]`));
  if (value && typeof value === 'object') {
    return Object.entries(value).flatMap(([k, v]) => [...(FORBIDDEN.has(k) ? [`${path}.${k}`] : []), ...forbiddenKeys(v, `${path}.${k}`)]);
  }
  return [];
}

/** Collecte toutes les reponses JSON de l'API pendant la seance. */
function spy(page: Page) {
  const bodies: { url: string; body: unknown }[] = [];
  page.on('response', async (r) => {
    if (!r.url().includes('/api/') || !(r.headers()['content-type'] ?? '').includes('json')) return;
    try {
      bodies.push({ url: r.url(), body: await r.json() });
    } catch { /* corps deja consomme ou vide */ }
  });
  return bodies;
}

async function drag(page: Page, from: string, to: string) {
  await expect(page.locator(`[data-square="${from}"] [data-piece]`)).toBeVisible();
  await page.waitForTimeout(200); // animation de react-chessboard
  const a = await page.locator(`[data-square="${from}"]`).boundingBox();
  const b = await page.locator(`[data-square="${to}"]`).boundingBox();
  await page.mouse.move(a!.x + a!.width / 2, a!.y + a!.height / 2);
  await page.mouse.down();
  await page.mouse.move(a!.x + a!.width / 2 + 5, a!.y + a!.height / 2 + 5, { steps: 3 });
  await page.mouse.move(b!.x + b!.width / 2, b!.y + b!.height / 2, { steps: 12 });
  await page.mouse.up();
  await page.waitForTimeout(100); // blocage des clics par dnd-kit apres depot
}

/**
 * Hygiene : une execution interrompue peut laisser une seance ouverte sur la
 * position de depart ; la regle anti-spoiler masquerait alors toute reference
 * sur cet echiquier (comportement voulu). On abandonne ces restes via l'API.
 */
async function abandonOpenSessions(page: Page) {
  const history = await (await page.request.get('/api/v1/history?limit=200')).json();
  for (const item of history.items as { id: string; state: string; fen: string }[]) {
    if (item.state !== 'active' || !item.fen.startsWith('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w')) continue;
    const s = await (await page.request.get(`/api/v1/sessions/${item.id}`)).json();
    await page.request.post(`/api/v1/sessions/${item.id}/abandon`, { data: { expected_revision: s.revision } });
  }
}

test.beforeEach(async ({ page }) => {
  await abandonOpenSessions(page);
});

async function retainStart(page: Page) {
  await page.goto('/#/positions');
  await page.getByRole('button', { name: 'Charger' }).click();
  await page.getByRole('button', { name: 'Retenir cette position' }).click();
  await expect(page.getByTestId('retained-fen')).toContainText('rnbqkbnr/pppppppp');
}

const moves = (page: Page) => page.getByLabel('Partie et variantes');

test('mode C : arbre a branches, coup illegal refuse, annuler/retablir, soumission figee, revelation', async ({ page }) => {
  test.setTimeout(60_000); // scenario complet, une vingtaine d'actions
  const bodies = spy(page);
  await retainStart(page);
  await page.getByRole('button', { name: 'Construire mon arbre (C)' }).click();
  await page.getByRole('button', { name: 'Go', exact: true }).click();
  await expect(page).toHaveURL(/#\/session\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId('session-state')).toHaveText('en cours');

  await drag(page, 'e2', 'e4');                                    // depuis la position de depart
  await expect(moves(page)).toContainText('1. e4');
  await page.getByLabel('Coup (SAN ou UCI)').fill('e5');           // le coup ajoute est selectionne : suite
  await page.getByRole('button', { name: 'Ajouter', exact: true }).click();
  await expect(moves(page)).toContainText('1. e4 e5');

  await page.getByRole('button', { name: 'Position de depart' }).click();
  await page.getByLabel('Coup (SAN ou UCI)').fill('d4');           // alternative a la racine
  await page.getByRole('button', { name: 'Ajouter', exact: true }).click();
  await expect(moves(page)).toContainText('( 1. d4 )');

  await page.getByLabel('Coup (SAN ou UCI)').fill('Ke3');          // illegal apres 1. d4
  await page.getByRole('button', { name: 'Ajouter', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('ILLEGAL_MOVE');

  await page.getByRole('button', { name: 'Annuler', exact: true }).click();
  await expect(moves(page)).not.toContainText('d4');
  await page.getByRole('button', { name: 'Retablir' }).click();
  await expect(moves(page)).toContainText('d4');

  // Apres la variante (1. d4), le coup noir est renumerote : « 1... e5 ».
  await moves(page).getByRole('button', { name: '1... e5', exact: true }).click();
  await page.getByLabel('Commentaire du coup').fill('symetrique');
  await page.getByRole('button', { name: 'Enregistrer' }).click();
  await expect(moves(page)).toContainText('symetrique');

  // Rechargement : la seance reprend depuis le serveur.
  await page.reload();
  await expect(moves(page)).toContainText('1. e4 ( 1. d4 ) 1... e5');

  await page.screenshot({ path: `results/screens/${test.info().project.name}-seance-C.png`, fullPage: true });
  await page.getByRole('button', { name: 'Terminer mon calcul' }).click();
  await page.getByRole('button', { name: 'Soumettre ma tentative' }).click();
  await expect(page.getByTestId('session-state')).toHaveText('soumise (figee)');
  await expect(page.locator('.board[data-mode="locked"]')).toBeVisible();
  await expect(page.getByLabel('Coup (SAN ou UCI)')).toHaveCount(0);

  // Aucune donnee moteur n'a transite AVANT la revelation.
  const before = bodies.flatMap((b) => forbiddenKeys(b.body).map((k) => `${b.url} ${k}`));
  expect(before).toEqual([]);
  expect(bodies.length).toBeGreaterThan(8);

  await page.getByRole('button', { name: 'Reveler' }).click();
  await expect(page.getByTestId('session-state')).toHaveText('revelee');
  // Lot 3 : la reference moteur (preparee pendant la seance) apparait apres revelation.
  await expect(page.getByRole('region', { name: 'Variantes Stockfish' })).toBeVisible({ timeout: 60_000 });
});

test('mode B : echiquier fige, variantes jugees seulement au debriefing', async ({ page }) => {
  const bodies = spy(page);
  await retainStart(page);
  await page.getByRole('button', { name: 'Calcul mental (B)' }).click();
  await page.getByRole('button', { name: 'Go', exact: true }).click();
  await expect(page.locator('.board[data-mode="locked"]')).toBeVisible();

  // Glisser une piece ne joue rien en calcul mental.
  await drag(page, 'e2', 'e4');
  await expect(page.locator('[data-square="e2"] [data-piece="wP"]')).toBeVisible();

  await page.getByLabel('Mes variantes').fill('1. e4 e5 2. Nf3\nd4 d5 Ke3');
  await page.getByLabel('Notes').fill('je regarde le centre');
  await page.getByLabel('Notes').blur();
  // Pendant la seance : aucun verdict de legalite.
  await expect(page.getByText('ILLEGAL_MOVE')).toHaveCount(0);

  await page.getByRole('button', { name: "J'ai termine" }).click();
  await page.getByLabel('Mes coups candidats').fill('e4, d4');
  await page.getByLabel('Estimation de la position').selectOption('equal');
  await page.getByRole('button', { name: 'Soumettre ma tentative' }).click();
  await expect(page.getByTestId('session-state')).toHaveText('soumise (figee)');

  expect(bodies.flatMap((b) => forbiddenKeys(b.body))).toEqual([]);

  await page.getByRole('button', { name: 'Reveler' }).click();
  const lines = page.getByTestId('written-line');
  await expect(lines.nth(0)).toHaveText('1. e4 e5 2. Nf3');
  await expect(lines.nth(1)).toContainText('1. d4 d5');
  await expect(lines.nth(1)).toContainText('coup 3 « Ke3 »');
  await expect(page.getByRole('region', { name: 'Debriefing' })).toContainText('egalite');
  await page.screenshot({ path: `results/screens/${test.info().project.name}-debrief-B.png`, fullPage: true });
});

test('historique : la seance apparait et se rouvre', async ({ page }) => {
  await retainStart(page);
  await page.getByRole('button', { name: 'Construire mon arbre (C)' }).click();
  await page.getByRole('button', { name: 'Go', exact: true }).click();
  await expect(page).toHaveURL(/#\/session\//);
  const id = page.url().split('/').pop()!;
  await page.getByRole('link', { name: 'Historique' }).click();
  const row = page.locator(`tr[data-session-id="${id}"]`);
  await expect(row).toContainText('en cours');
  await row.getByRole('button', { name: 'Reprendre' }).click();
  await expect(page).toHaveURL(new RegExp(`#/session/${id}$`));
  // Abandon avec confirmation.
  await page.getByRole('button', { name: 'Abandonner la seance' }).click();
  await page.getByRole('button', { name: 'Oui, abandonner' }).click();
  await expect(page.getByTestId('session-state')).toHaveText('abandonnee');
});
