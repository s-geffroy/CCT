// Positions successives d'une PV moteur, pour l'affichage seulement : les coups
// viennent du serveur (deja valides par python-chess), chess.js ne fait que
// les rejouer pour dessiner l'echiquier.
import { Chess } from 'chess.js';

export function pvPositions(rootFen: string, pvUci: string[]): { fen: string; from: string; to: string }[] {
  const game = new Chess(rootFen);
  const out: { fen: string; from: string; to: string }[] = [];
  for (const uci of pvUci) {
    try {
      game.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci.length > 4 ? uci[4] : undefined });
    } catch {
      break; // divergence imprevue : on s'arrete, rien n'est invente
    }
    out.push({ fen: game.fen(), from: uci.slice(0, 2), to: uci.slice(2, 4) });
  }
  return out;
}
