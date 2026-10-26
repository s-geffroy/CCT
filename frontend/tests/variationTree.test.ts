import { describe, expect, it } from 'vitest';
import { toTreeRows } from '../src/adapters/variationTree';
import { nodes } from './fixtures';

describe('toTreeRows', () => {
  it('garde la suite principale au meme niveau et indente les variantes', () => {
    const rows = toTreeRows(nodes, 'r');
    expect(rows.map((r) => r.label)).toEqual(['1. e4', 'e5', '2. Nf3']);
    const e5 = rows[1];
    expect(e5.children).toHaveLength(1);
    const variation = e5.children![0];
    expect(variation.kind).toBe('variation');
    expect(variation.children!.map((r) => r.label)).toEqual(['1... c5!?', '2. Nf3']);
  });

  it('renumerote le coup noir qui suit une variante', () => {
    const rows = toTreeRows(nodes, 'r');
    expect(rows[2].label).toBe('2. Nf3');
  });

  it('arbre vide sans coup', () => {
    expect(toTreeRows({ r: { ...nodes.r, children: [] } }, 'r')).toEqual([]);
  });
});
