// react-chessboard rend chaque piece deplacable comme un `role="button"` sans
// nom : un lecteur d'ecran annonce « bouton », sans dire quelle piece ni ou.
// On nomme ces elements (« Cavalier blanc en g1 ») apres chaque rendu de la
// bibliotheque, sans toucher a son fonctionnement.
import { useEffect, type RefObject } from 'react';

const PIECE: Record<string, string> = { P: 'Pion', N: 'Cavalier', B: 'Fou', R: 'Tour', Q: 'Dame', K: 'Roi' };

export function pieceLabel(code: string, square: string | null): string {
  const name = PIECE[code[1]] ?? 'Piece';
  const color = code[0] === 'w' ? 'blanc' : 'noir';
  const label = `${name} ${name === 'Dame' || name === 'Tour' ? (color === 'blanc' ? 'blanche' : 'noire') : color}`;
  return square ? `${label} en ${square}` : `${label} (reserve)`;
}

function labelPieces(root: HTMLElement) {
  for (const el of root.querySelectorAll<HTMLElement>('[role="button"]')) {
    const code = el.getAttribute('data-piece') ?? el.querySelector('[data-piece]')?.getAttribute('data-piece');
    if (!code) continue;
    const label = pieceLabel(code, el.closest('[data-square]')?.getAttribute('data-square') ?? null);
    if (el.getAttribute('aria-label') !== label) el.setAttribute('aria-label', label);
  }
}

export function useAccessiblePieces(ref: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    let frame = 0;
    labelPieces(root);
    const observer = new MutationObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => labelPieces(root));
    });
    observer.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-piece'] });
    return () => { observer.disconnect(); cancelAnimationFrame(frame); };
  }, [ref]);
}
