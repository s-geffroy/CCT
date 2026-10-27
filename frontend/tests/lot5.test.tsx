import { describe, expect, it } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { keyTarget, MoveText } from '../src/components/MoveText';
import { toPerspective } from '../src/features/settings/prefs';
import { formatScore } from '../src/features/analysis/format';
import { userTreeToNodes, USER_ROOT } from '../src/adapters/userTree';
import type { UserNode } from '../src/api/client';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const node = (id: string, parent: string | null, order: number, uci: string, san: string, fen: string): UserNode => ({
  id, parent_id: parent, order_index: order, move_uci: uci, move_san: san, fen_after: fen, comment: '',
  human_assessment: null, created_at: '',
});
const tree = userTreeToNodes({
  e4: node('e4', null, 0, 'e2e4', 'e4', 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'),
  d4: node('d4', null, 1, 'd2d4', 'd4', 'rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1'),
  e5: node('e5', 'e4', 0, 'e7e5', 'e5', 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2'),
}, START);

describe('navigation au clavier dans un arbre de coups', () => {
  it('droite = suite, gauche = parent, bas/haut = variante soeur, Debut = racine', () => {
    expect(keyTarget(tree, USER_ROOT, null, 'ArrowRight')).toBe('e4');
    expect(keyTarget(tree, USER_ROOT, 'e4', 'ArrowRight')).toBe('e5');
    expect(keyTarget(tree, USER_ROOT, 'e5', 'ArrowLeft')).toBe('e4');
    expect(keyTarget(tree, USER_ROOT, 'e4', 'ArrowDown')).toBe('d4');
    expect(keyTarget(tree, USER_ROOT, 'd4', 'ArrowUp')).toBe('e4');
    expect(keyTarget(tree, USER_ROOT, 'd4', 'ArrowDown')).toBeUndefined();
    expect(keyTarget(tree, USER_ROOT, 'e5', 'Home')).toBe(USER_ROOT);
    expect(keyTarget(tree, USER_ROOT, 'e5', 'a')).toBeUndefined();
  });

  it('le texte des coups reagit aux fleches', () => {
    const selected: string[] = [];
    const { getByLabelText } = render(<MoveText nodes={tree} rootId={USER_ROOT} selectedNodeId="e4" onSelect={(id) => selected.push(id)} />);
    fireEvent.keyDown(getByLabelText('Partie et variantes'), { key: 'ArrowRight' });
    fireEvent.keyDown(getByLabelText('Partie et variantes'), { key: 'ArrowDown' });
    expect(selected).toEqual(['e5', 'd4']);
  });
});

describe('point de vue des evaluations', () => {
  const cp = (value: number, bound: 'lower' | 'upper' | null = null) => ({ kind: 'cp' as const, value, perspective: 'white' as const, bound });
  const black = '8/8/8/8/8/8/8/k6K b - - 0 1';
  it('Blancs par defaut, inverse pour le camp au trait quand les Noirs jouent', () => {
    expect(formatScore(toPerspective(cp(120), black, 'white'))).toBe('+1.20');
    expect(formatScore(toPerspective(cp(120), black, 'side_to_move'))).toBe('-1.20');
    expect(formatScore(toPerspective(cp(120), START, 'side_to_move'))).toBe('+1.20');
    // Une borne inferieure devient superieure quand on change de camp.
    expect(formatScore(toPerspective(cp(50, 'lower'), black, 'side_to_move'))).toBe('≤-0.50');
    expect(formatScore(toPerspective({ kind: 'mate', value: -3, perspective: 'white', bound: null }, black, 'side_to_move'))).toBe('M+3');
  });
});

describe('pieces nommees pour les lecteurs d ecran', async () => {
  const { pieceLabel } = await import('../src/adapters/boardA11y');
  it('nom, couleur accordee, case ou reserve', () => {
    expect(pieceLabel('wN', 'g1')).toBe('Cavalier blanc en g1');
    expect(pieceLabel('bQ', 'd8')).toBe('Dame noire en d8');
    expect(pieceLabel('bP', null)).toBe('Pion noir (reserve)');
  });
});
