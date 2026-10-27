// Editeur de position : echiquier + pieces libres (SparePiece de react-chessboard,
// qui exige un ChessboardProvider commun). La FEN produite est validee par le
// serveur ; le client ne juge pas la legalite.
import { useMemo, useRef, useState } from 'react';
import { useAccessiblePieces } from '../adapters/boardA11y';
import {
  Chessboard,
  ChessboardProvider,
  SparePiece,
  fenStringToPositionObject,
  type ChessboardOptions,
  type PieceDropHandlerArgs,
  type PositionDataType,
} from 'react-chessboard';

const WHITE = ['wK', 'wQ', 'wR', 'wB', 'wN', 'wP'];
const BLACK = ['bK', 'bQ', 'bR', 'bB', 'bN', 'bP'];
const FILES = 'abcdefgh';

export function placementFromPosition(position: PositionDataType): string {
  const ranks: string[] = [];
  for (let rank = 8; rank >= 1; rank--) {
    let row = '';
    let empty = 0;
    for (const file of FILES) {
      const piece = position[`${file}${rank}`];
      if (!piece) {
        empty++;
        continue;
      }
      if (empty) row += String(empty);
      empty = 0;
      const [color, kind] = piece.pieceType;
      row += color === 'w' ? kind.toUpperCase() : kind.toLowerCase();
    }
    if (empty) row += String(empty);
    ranks.push(row);
  }
  return ranks.join('/');
}

export function applyEditorDrop(position: PositionDataType, args: PieceDropHandlerArgs): PositionDataType {
  const next = { ...position };
  const { piece, sourceSquare, targetSquare } = args;
  if (!piece.isSparePiece) delete next[sourceSquare];
  if (targetSquare) next[targetSquare] = { pieceType: piece.pieceType };
  return next;
}

export type EditorProps = { initialFen: string; onSubmit: (fen: string) => void };

export function PositionEditor({ initialFen, onSubmit }: EditorProps) {
  const [position, setPosition] = useState<PositionDataType>(() => fenStringToPositionObject(initialFen, 8, 8));
  const [turn, setTurn] = useState<'w' | 'b'>('w');
  const editorRef = useRef<HTMLDivElement>(null);
  useAccessiblePieces(editorRef);
  const [castling, setCastling] = useState('KQkq');
  const [ep, setEp] = useState('-');

  const fen = useMemo(
    () => `${placementFromPosition(position)} ${turn} ${castling || '-'} ${ep || '-'} 0 1`,
    [position, turn, castling, ep],
  );

  const options: ChessboardOptions = {
    id: 'editor',
    position,
    allowDragOffBoard: true, // deposer hors de l'echiquier retire la piece
    allowDrawingArrows: false,
    onPieceDrop: (args) => {
      setPosition((p) => applyEditorDrop(p, args));
      return true;
    },
  };

  return (
    <ChessboardProvider options={options}>
      <div className="editor" ref={editorRef}>
        <div className="editor-board">
          <div className="spares" aria-label="Pieces noires">{BLACK.map((t) => <SparePiece key={t} pieceType={t} />)}</div>
          <Chessboard />
          <div className="spares" aria-label="Pieces blanches">{WHITE.map((t) => <SparePiece key={t} pieceType={t} />)}</div>
        </div>
        <div className="editor-side">
        <p className="text-sm text-muted-foreground">Glissez les pieces depuis les reserves ; hors de l'echiquier pour les retirer.</p>
        <fieldset>
          <legend>Contexte de la position</legend>
          <label>
            Trait{' '}
            <select value={turn} onChange={(e) => setTurn(e.target.value as 'w' | 'b')}>
              <option value="w">Blancs</option>
              <option value="b">Noirs</option>
            </select>
          </label>
          <label>
            Roques <input value={castling} onChange={(e) => setCastling(e.target.value)} size={5} />
          </label>
          <label>
            En passant <input value={ep} onChange={(e) => setEp(e.target.value)} size={3} />
          </label>
          <button type="button" onClick={() => setPosition({})}>Vider</button>
          <button type="button" onClick={() => setPosition(fenStringToPositionObject(initialFen, 8, 8))}>Reinitialiser</button>
          <button type="button" className="primary" onClick={() => onSubmit(fen)}>Valider cette position</button>
        </fieldset>
        <code className="fen">{fen}</code>
        </div>
      </div>
    </ChessboardProvider>
  );
}
