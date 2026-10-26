import { describe, expect, it } from 'vitest';
import { USER_ROOT, userTreeToNodes } from '../src/adapters/userTree';
import { moveLabel } from '../src/adapters/variationTree';
import type { UserNode } from '../src/api/client';

const node = (id: string, parent: string | null, order: number, uci: string, san: string, fen: string): UserNode => ({
  id, parent_id: parent, order_index: order, move_uci: uci, move_san: san, fen_after: fen, comment: '', human_assessment: null, created_at: '',
});

describe('userTreeToNodes', () => {
  it('ordonne les alternatives et lit camp et numero sur la FEN du parent', () => {
    const root = '4k3/8/8/8/8/8/4P3/4K3 b - - 0 23';
    const tree = {
      b: node('b', null, 1, 'e8d8', 'Kd8', '3k4/8/8/8/8/8/4P3/4K3 w - - 1 24'),
      a: node('a', null, 0, 'e8d7', 'Kd7', '8/3k4/8/8/8/8/4P3/4K3 w - - 1 24'),
      c: node('c', 'a', 0, 'e2e4', 'e4', '8/3k4/8/8/4P3/8/8/4K3 b - - 0 24'),
    };
    const nodes = userTreeToNodes(tree, root);
    expect(nodes[USER_ROOT].children).toEqual(['a', 'b']);
    expect(moveLabel(nodes.a, true)).toBe('23... Kd7');
    expect(moveLabel(nodes.c, false)).toBe('24. e4');
    expect(nodes.c.ply).toBe(2);
  });
});
