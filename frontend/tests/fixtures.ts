import type { PgnNode } from '../src/api/client';

// 1. e4 e5 (1... c5 2. Nf3) 2. Nf3 {main <b>x</b>}
function n(id: string, parent: string | null, ply: number, san: string | null, children: string[], comment = '', nags: number[] = []): PgnNode {
  const move_number = ply ? Math.floor((ply + 1) / 2) : null;
  const color = ply ? (ply % 2 === 1 ? 'white' : 'black') : null;
  return { id, parent_id: parent, ply, move_number, color, uci: null, san, fen: '8/8/8/8/8/8/8/8 w - - 0 1', comment, starting_comment: '', nags, children };
}

export const nodes: Record<string, PgnNode> = {
  r: n('r', null, 0, null, ['e4']),
  e4: n('e4', 'r', 1, 'e4', ['e5', 'c5']),
  e5: n('e5', 'e4', 2, 'e5', ['nf3']),
  c5: n('c5', 'e4', 2, 'c5', ['nf3b'], '', [5]),
  nf3b: n('nf3b', 'c5', 3, 'Nf3', []),
  nf3: n('nf3', 'e5', 3, 'Nf3', [], 'main <b>x</b>'),
};
