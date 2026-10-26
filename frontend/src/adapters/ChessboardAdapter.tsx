// Seul point de contact avec react-chessboard (v5, API `options`).
//
// Constats du spike (v5.12.1) :
//  - onPieceDrop est SYNCHRONE (retourne un booleen) : impossible d'attendre le
//    serveur. On refuse donc le depot visuel, on envoie le coup, et la
//    position se met a jour quand le serveur l'accepte (la FEN vient du parent).
//  - aucune boite de promotion integree : on la fournit ici, jamais de dame
//    implicite.
//  - aucune option de navigation clavier : la saisie SAN textuelle reste le
//    chemin accessible (a traiter au Lot 5).
import { useState } from 'react';
import { Chessboard, type ChessboardOptions, type PieceDropHandlerArgs } from 'react-chessboard';

export type BoardMode = 'locked' | 'play';

export type ChessboardAdapterProps = {
  fen: string;
  orientation?: 'white' | 'black';
  mode: BoardMode;
  lastMove?: { from: string; to: string } | null;
  /** Coup propose en UCI ; le parent le soumet au serveur. */
  onMove?: (uci: string) => void;
  id?: string;
};

const PROMOTION_PIECES = [
  { code: 'q', label: 'Dame' },
  { code: 'r', label: 'Tour' },
  { code: 'b', label: 'Fou' },
  { code: 'n', label: 'Cavalier' },
] as const;

export function isPromotionDrop(pieceType: string, target: string): boolean {
  return pieceType.endsWith('P') && (target.endsWith('8') || target.endsWith('1'));
}

export function ChessboardAdapter({ fen, orientation = 'white', mode, lastMove, onMove, id = 'board' }: ChessboardAdapterProps) {
  const [pendingPromotion, setPendingPromotion] = useState<{ from: string; to: string } | null>(null);

  const handleDrop = ({ piece, sourceSquare, targetSquare }: PieceDropHandlerArgs): boolean => {
    if (mode !== 'play' || !targetSquare || targetSquare === sourceSquare) return false;
    if (isPromotionDrop(piece.pieceType, targetSquare)) {
      setPendingPromotion({ from: sourceSquare, to: targetSquare });
    } else {
      onMove?.(sourceSquare + targetSquare);
    }
    return false; // la FEN du parent fait foi
  };

  const squareStyles: Record<string, React.CSSProperties> = {};
  if (lastMove) {
    squareStyles[lastMove.from] = { background: 'rgba(255, 210, 0, 0.35)' };
    squareStyles[lastMove.to] = { background: 'rgba(255, 210, 0, 0.5)' };
  }

  const options: ChessboardOptions = {
    id,
    position: fen,
    boardOrientation: orientation,
    allowDragging: mode === 'play',
    allowDrawingArrows: false, // aucune fleche : rien qui ressemble a un conseil
    showAnimations: true,
    animationDurationInMs: 150,
    squareStyles,
    onPieceDrop: handleDrop,
  };

  return (
    <div className="board" data-mode={mode}>
      <Chessboard options={options} />
      {pendingPromotion && (
        <div role="dialog" aria-label="Choisir la piece de promotion" className="promotion">
          {PROMOTION_PIECES.map((p) => (
            <button
              key={p.code}
              type="button"
              onClick={() => {
                onMove?.(pendingPromotion.from + pendingPromotion.to + p.code);
                setPendingPromotion(null);
              }}
            >
              {p.label}
            </button>
          ))}
          <button type="button" onClick={() => setPendingPromotion(null)}>Annuler</button>
        </div>
      )}
    </div>
  );
}
