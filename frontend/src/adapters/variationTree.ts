// Conversion d'un arbre de coups (noeuds serveur) vers les lignes affichables.
//
// Un arbre de coups naif imbrique chaque coup sous le precedent : 40 coups,
// 40 niveaux d'indentation. On suit la convention PGN : la suite principale
// reste au meme niveau, seules les variantes s'indentent. Une variante est
// rattachee au coup qu'elle remplace, comme « 1. e4 (1. d4 ...) ».

import type { PgnNode } from '../api/client';

export type TreeRow = {
  id: string;
  kind: 'move' | 'variation' | 'more';
  nodeId: string | null; // noeud serveur (null pour un groupe « variante » ; parent a completer pour 'more')
  label: string;
  comment: string;
  origin: 'user' | 'reference' | 'imported';
  children: TreeRow[] | null;
};

const NAG_GLYPHS: Record<number, string> = { 1: '!', 2: '?', 3: '!!', 4: '??', 5: '!?', 6: '?!' };

export function moveLabel(node: PgnNode, forceNumber: boolean): string {
  // Numero et camp viennent du serveur (lus sur l'echiquier) : une partie avec
  // en-tete FEN peut commencer aux Noirs, au coup 23.
  const moveNumber = node.move_number ?? Math.floor((node.ply + 1) / 2);
  const white = node.color ? node.color === 'white' : node.ply % 2 === 1;
  const prefix = white ? `${moveNumber}. ` : forceNumber ? `${moveNumber}... ` : '';
  const glyphs = node.nags.map((n) => NAG_GLYPHS[n] ?? `$${n}`).join('');
  return `${prefix}${node.san ?? ''}${glyphs}`;
}

export function toTreeRows(
  nodes: Record<string, PgnNode>,
  rootId: string,
  origin: TreeRow['origin'] = 'imported',
): TreeRow[] {
  let variationCounter = 0;

  // Ligne qui commence par `startId` et suit les premiers enfants.
  function line(startId: string): TreeRow[] {
    const rows: TreeRow[] = [];
    let current: PgnNode | undefined = nodes[startId];
    let first = true;
    while (current) {
      const parent: PgnNode | undefined = current.parent_id ? nodes[current.parent_id] : undefined;
      const siblings = parent ? parent.children : [];
      const alternatives = siblings[0] === current.id ? siblings.slice(1).filter((id) => nodes[id]) : [];
      const variations: TreeRow[] = alternatives.map((altId) => ({
        id: `var-${++variationCounter}`,
        kind: 'variation',
        nodeId: null,
        label: 'variante',
        comment: nodes[altId]?.starting_comment ?? '',
        origin,
        children: line(altId),
      }));
      rows.push({
        id: current.id,
        kind: 'move',
        nodeId: current.id,
        label: moveLabel(current, first),
        comment: current.comment,
        origin,
        children: variations.length ? variations : null,
      });
      first = variations.length > 0; // apres une variante, on renumerote le coup noir
      const next: string | undefined = current.children[0];
      if (next && !nodes[next]) {
        // Arbre pagine : la suite existe cote serveur mais n'est pas chargee.
        rows.push({ id: `more-${current.id}`, kind: 'more', nodeId: current.id, label: '… suite non chargee', comment: '', origin, children: null });
      }
      current = next ? nodes[next] : undefined;
    }
    return rows;
  }

  const root = nodes[rootId];
  if (!root) return [];
  if (root.children.length === 0) return [];
  // Les alternatives au premier coup sont gerees par line() via le parent.
  return line(root.children[0]);
}
