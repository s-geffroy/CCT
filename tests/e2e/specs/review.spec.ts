// Lot 4 : debriefing et arbre de reference dans le navigateur, vrai moteur.
// Position dediee (dame offerte sur f7 defendu) ; reglages par defaut de
// l'application : le rapport peut rester provisoire pendant la construction.
import { expect, test, type Page } from '@playwright/test';

const BLUNDER_FEN = 'rnbqkbnr/ppp2ppp/8/3pp3/4P3/5Q2/PPPP1PPP/RNB1KBNR w KQkq - 0 3';

async function abandonOpenSessionsOn(page: Page, fen: string) {
  const history = await (await page.request.get('/api/v1/history?limit=200')).json();
  for (const item of history.items as { id: string; state: string; fen: string }[]) {
    if (item.state !== 'active' || item.fen !== fen) continue;
    const s = await (await page.request.get(`/api/v1/sessions/${item.id}`)).json();
    await page.request.post(`/api/v1/sessions/${item.id}/abandon`, { data: { expected_revision: s.revision } });
  }
}

test('debriefing : refutation prouvee, branche du joueur dans l arbre de reference', async ({ page }) => {
  test.setTimeout(240_000);
  await abandonOpenSessionsOn(page, BLUNDER_FEN);
  await page.goto('/#/positions');
  await page.getByLabel('FEN', { exact: true }).fill(BLUNDER_FEN);
  await page.getByRole('button', { name: 'Charger' }).click();
  await page.getByRole('button', { name: 'Retenir cette position' }).click();
  await page.getByRole('button', { name: 'Construire mon arbre (C)' }).click();
  await expect(page).toHaveURL(/#\/session\//);

  // Avant la revelation : aucune section de debriefing ni d'arbre.
  await expect(page.getByRole('region', { name: 'Diagnostics' })).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Arbre de reference' })).toHaveCount(0);

  await page.getByLabel('Coup (SAN ou UCI)').fill('Qxf7+');
  await page.getByRole('button', { name: 'Ajouter', exact: true }).click();
  await page.getByRole('button', { name: 'Terminer mon calcul' }).click();
  await page.getByRole('button', { name: 'Soumettre ma tentative' }).click();
  await expect(page.getByTestId('preparation')).toContainText('prete', { timeout: 120_000 });
  await page.getByRole('button', { name: 'Reveler' }).click();

  const review = page.getByRole('region', { name: 'Diagnostics' });
  await expect(review).toBeVisible();
  await expect(page.getByTestId('review-quality')).toHaveText(/Rapport (provisoire|etabli)/);
  // La branche du joueur est analysee en priorite, puis jugee avec sa preuve.
  const tree = page.getByRole('region', { name: 'Arbre de reference' });
  await expect(tree.locator('li[data-path="f3f7"][data-reason="user_branch"]')).toBeVisible({ timeout: 60_000 });
  await expect(review.locator('tr[data-verdict="refuted"]')).toBeVisible({ timeout: 90_000 });
  const refutation = review.locator('li[data-category="tactical_refutation"]');
  await expect(refutation).toContainText('Kxf7');
  await refutation.getByRole('button', { name: 'Voir la position' }).click();
  await expect(page.getByTestId('shown-position')).toContainText('Refutation');
  await expect(tree.getByText(/pas exhaustif/)).toBeVisible();
  await page.screenshot({ path: `results/screens/${test.info().project.name}-review.png`, fullPage: true });
});
