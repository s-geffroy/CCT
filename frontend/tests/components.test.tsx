import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ChessboardAdapter, isPromotionDrop } from '../src/adapters/ChessboardAdapter';
import { MoveText } from '../src/components/MoveText';
import { VariationTree } from '../src/components/VariationTree';
import { toTreeRows } from '../src/adapters/variationTree';
import { applyEditorDrop, placementFromPosition } from '../src/features/PositionEditor';
import { fenStringToPositionObject } from 'react-chessboard';
import { nodes } from './fixtures';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

describe('ChessboardAdapter', () => {
  it('rend 64 cases depuis une FEN', () => {
    const { container } = render(<ChessboardAdapter fen={START} mode="locked" />);
    expect(container.querySelectorAll('[data-square]').length).toBe(64);
    expect(container.querySelector('[data-mode="locked"]')).not.toBeNull();
  });

  it('detecte les promotions sans en choisir la piece', () => {
    expect(isPromotionDrop('wP', 'e8')).toBe(true);
    expect(isPromotionDrop('bP', 'a1')).toBe(true);
    expect(isPromotionDrop('wQ', 'e8')).toBe(false);
    expect(isPromotionDrop('wP', 'e7')).toBe(false);
  });
});

describe('PositionEditor (fonctions pures)', () => {
  it('reconstruit la FEN de placement depuis la position react-chessboard', () => {
    expect(placementFromPosition(fenStringToPositionObject(START, 8, 8))).toBe(START.split(' ')[0]);
  });

  it('piece libre deposee, piece retiree hors echiquier', () => {
    let pos = applyEditorDrop({}, { piece: { isSparePiece: true, position: '', pieceType: 'wK' }, sourceSquare: '', targetSquare: 'e1' });
    expect(placementFromPosition(pos)).toBe('8/8/8/8/8/8/8/4K3');
    pos = applyEditorDrop(pos, { piece: { isSparePiece: false, position: 'e1', pieceType: 'wK' }, sourceSquare: 'e1', targetSquare: null });
    expect(placementFromPosition(pos)).toBe('8/8/8/8/8/8/8/8');
  });
});

describe('MoveText', () => {
  it('rend les commentaires en texte inerte et selectionne un coup', () => {
    const onSelect = vi.fn();
    const { container } = render(<MoveText nodes={nodes} rootId="r" selectedNodeId={null} onSelect={onSelect} />);
    expect(container.querySelector('b')).toBeNull();
    expect(screen.getByText(/main <b>x<\/b>/)).toBeTruthy();
    fireEvent.click(screen.getByText('1... c5!?'));
    expect(onSelect).toHaveBeenCalledWith('c5');
  });
});

describe('VariationTree (react-arborist)', () => {
  it('se rend sans glisser-deposer et affiche les coups', () => {
    render(<VariationTree rows={toTreeRows(nodes, 'r')} selectedNodeId={null} onSelect={() => {}} height={300} />);
    expect(screen.getByText('1. e4')).toBeTruthy();
    expect(screen.getByRole('tree')).toBeTruthy();
  });
});
