import type { EngineScore } from '../../api/client';

/** Evaluation au point de vue des Blancs : +0.35, -1.20, M+3, M-2 ; bornes ≥ / ≤. */
export function formatScore(score: EngineScore): string {
  const bound = score.bound === 'lower' ? '≥' : score.bound === 'upper' ? '≤' : '';
  if (score.kind === 'draw') return 'nulle';
  if (score.kind === 'mate' && score.value === 0) return score.result ? `mat (${score.result})` : 'mat';
  if (score.kind === 'mate' && score.value !== null) return `${bound}M${score.value > 0 ? '+' : '-'}${Math.abs(score.value)}`;
  if (score.kind === 'cp' && score.value !== null) {
    const pawns = score.value / 100;
    return `${bound}${pawns > 0 ? '+' : ''}${pawns.toFixed(2)}`;
  }
  return '?';
}

/** Numerote une suite SAN a partir d'une FEN (trait et numero du coup). */
export function numberedLine(fen: string, sans: string[]): string {
  const [, turn, , , , fullmove] = fen.split(' ');
  let n = Number(fullmove) || 1;
  let white = turn !== 'b';
  return sans
    .map((san, i) => {
      const text = white ? `${n}. ${san}` : i === 0 ? `${n}... ${san}` : san;
      if (!white) n++;
      white = !white;
      return text;
    })
    .join(' ');
}
