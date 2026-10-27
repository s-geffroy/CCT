import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { AnalysisLine, ReferenceNode, VisibleTree } from '../src/api/client';
import { formatScore } from '../src/features/analysis/format';
import { ReferenceTreeView } from '../src/features/reference/ReferenceTreeView';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1';

const line = (rank: number, uci: string, san: string, cp: number): AnalysisLine => ({
  rank, root_move_uci: uci, root_move_san: san, pv_uci: [uci], pv_san: [san], depth: 12, exact_depth: 12,
  seldepth: null, score: { kind: 'cp', value: cp, perspective: 'white', bound: null }, status: 'depth_met',
});

const node = (over: Partial<ReferenceNode>): ReferenceNode => ({
  id: 'root', parent_id: null, path_uci: [], ply: 0, move_uci: null, move_san: null, fen: START, status: 'depth_met',
  selection_reason: 'root', reanalysed: false, job_id: 'j', job_state: 'complete_depth', target_depth: 12,
  legal_moves: 20, lines: [], ...over,
});

const tree: VisibleTree = {
  id: 't', visibility: 'full', position_id: 'p', session_id: null, state: 'node_limit', revision: 3,
  settings: { budget_s: 300, max_nodes: 3, max_children: 3, node_depth: 12, auto_max_ply: 4 },
  spent_s: { auto: 12, user: 0 }, pruned_count: 5, coverage: 'selective',
  nodes: [
    node({ lines: [line(1, 'e2e4', 'e4', 30), line(2, 'd2d4', 'd4', 25)] }),
    node({ id: 'n1', parent_id: 'root', path_uci: ['e2e4'], ply: 1, move_uci: 'e2e4', move_san: 'e4', fen: AFTER_E4,
           selection_reason: 'top_rank', lines: [line(1, 'c7c5', 'c5', 20)] }),
    node({ id: 'n2', parent_id: 'root', path_uci: ['h2h4'], ply: 1, move_uci: 'h2h4', move_san: 'h4',
           selection_reason: 'user_branch', status: 'pruned_by_policy', job_id: null, job_state: null, lines: [] }),
  ],
};

describe('formatScore (positions terminales)', () => {
  it('nulle et mat deja donne', () => {
    expect(formatScore({ kind: 'draw', value: 0, perspective: 'white', bound: null })).toBe('nulle');
    expect(formatScore({ kind: 'mate', value: 0, perspective: 'white', bound: null, result: '1-0' })).toBe('mat (1-0)');
  });
});

describe('ReferenceTreeView', () => {
  it('dit pourquoi chaque noeud est la et que l arbre est selectif', () => {
    render(<ReferenceTreeView tree={tree} rootFen={START} onShow={() => {}} onExpand={async () => {}} />);
    expect(screen.getByTestId('tree-state').textContent).toContain('nombre maximal de noeuds');
    expect(screen.getByTestId('tree-state').textContent).toContain('5 branche(s) non explorees');
    expect(screen.getByText(/pas exhaustif/)).toBeTruthy();
    expect(screen.getByText('votre branche')).toBeTruthy();
    expect(screen.getByText('non analysee (plafonds)')).toBeTruthy();
  });

  it('montre la position d un noeud et propose d analyser un coup absent de l arbre', () => {
    const onShow = vi.fn();
    const onExpand = vi.fn(async () => {});
    render(<ReferenceTreeView tree={tree} rootFen={START} onShow={onShow} onExpand={onExpand} />);
    fireEvent.click(screen.getByRole('button', { name: '1. e4' }));
    expect(onShow).toHaveBeenLastCalledWith(expect.objectContaining({ fen: AFTER_E4, label: '1. e4' }));
    fireEvent.click(screen.getByRole('button', { name: 'Position etudiee' }));
    // e4 est deja dans l'arbre : seul d4 peut etre ajoute.
    const add = screen.getAllByRole('button', { name: 'Analyser ce coup' });
    expect(add).toHaveLength(1);
    fireEvent.click(add[0]);
    expect(onExpand).toHaveBeenCalledWith(['d2d4']);
  });
});
