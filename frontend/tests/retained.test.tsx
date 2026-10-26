import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { formatHistory, RetainedPanel } from '../src/features/positions/RetainedPanel';
import type { Position } from '../src/api/client';

const base: Position = {
  id: 'p1', fen: 'x w - - 0 3', initial_fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
  history_uci: ['e2e4', 'c7c5', 'c2c3', 'd7d5'], history_san: ['e4', 'c5', 'c3', 'd5'], history_complete: true,
  source_type: 'pgn', source_game_id: 'g', source_node_id: 'n', turn: 'white', legal_moves_count: 30,
  outcome: null, claimable_draw: null, created_at: '2026-10-26T00:00:00Z',
};

describe('RetainedPanel', () => {
  it('numerote l historique, y compris depuis une FEN aux Noirs', () => {
    expect(formatHistory(base)).toBe('1. e4 c5 2. c3 d5');
    expect(formatHistory({ initial_fen: '8/8/8/8/8/8/8/8 b - - 0 23', history_san: ['Kd7', 'e4'] })).toBe('23... Kd7 24. e4');
  });

  it('distingue historique complet, partiel et inconnu', () => {
    const { rerender } = render(<RetainedPanel position={base} displayedFen={base.fen} onShow={() => {}} />);
    expect(screen.getByTestId('retained-history-status').textContent).toMatch(/complet/);
    rerender(<RetainedPanel position={{ ...base, history_uci: null, history_san: null, history_complete: false }} displayedFen="autre" onShow={() => {}} />);
    expect(screen.getByTestId('retained-history-status').textContent).toMatch(/inconnu/);
    expect(screen.getByText(/differe de la position retenue/)).toBeTruthy();
  });
});
