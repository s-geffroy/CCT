import { describe, expect, it } from 'vitest';
import { formatScore, numberedLine } from '../src/features/analysis/format';
import { pvPositions } from '../src/features/analysis/pv';

describe('formatScore (point de vue des Blancs)', () => {
  it('centipions, mats et bornes', () => {
    expect(formatScore({ kind: 'cp', value: 35, perspective: 'white', bound: null })).toBe('+0.35');
    expect(formatScore({ kind: 'cp', value: -120, perspective: 'white', bound: null })).toBe('-1.20');
    expect(formatScore({ kind: 'cp', value: 0, perspective: 'white', bound: null })).toBe('0.00');
    expect(formatScore({ kind: 'mate', value: 3, perspective: 'white', bound: null })).toBe('M+3');
    expect(formatScore({ kind: 'mate', value: -2, perspective: 'white', bound: null })).toBe('M-2');
    expect(formatScore({ kind: 'cp', value: 50, perspective: 'white', bound: 'lower' })).toBe('≥+0.50');
    expect(formatScore({ kind: 'unknown', value: null, perspective: 'white', bound: null })).toBe('?');
  });
});

describe('numberedLine', () => {
  it('numerote depuis une position aux Noirs', () => {
    expect(numberedLine('8/8/8/8/8/8/8/8 b - - 0 12', ['Kd7', 'e4', 'Kc6'])).toBe('12... Kd7 13. e4 Kc6');
  });
});

describe('pvPositions', () => {
  it('rejoue une PV valide et s arrete sur un coup impossible', () => {
    const start = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
    const ok = pvPositions(start, ['e2e4', 'e7e5']);
    expect(ok).toHaveLength(2);
    expect(ok[1].fen.startsWith('rnbqkbnr/pppp1ppp/8/4p3/4P3')).toBe(true);
    expect(pvPositions(start, ['e2e4', 'e2e4'])).toHaveLength(1);
  });
});
