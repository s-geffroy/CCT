// Arbre utilisateur (noeuds de seance) -> format des vues d'arbre (PgnNode),
// avec une racine artificielle portant la position de depart de la seance.
import type { PgnNode, UserNode } from '../api/client';

export const USER_ROOT = 'root';

export function userTreeToNodes(nodes: Record<string, UserNode>, rootFen: string): Record<string, PgnNode> {
  const out: Record<string, PgnNode> = {
    [USER_ROOT]: {
      id: USER_ROOT, parent_id: null, ply: 0, move_number: null, color: null, uci: null, san: null,
      fen: rootFen, comment: '', starting_comment: '', nags: [], children: [],
    },
  };
  const byParent = new Map<string, UserNode[]>();
  for (const n of Object.values(nodes)) {
    const key = n.parent_id ?? USER_ROOT;
    byParent.set(key, [...(byParent.get(key) ?? []), n]);
  }
  // Parcours depuis la racine : le camp et le numero de coup se lisent sur la
  // FEN du parent, jamais sur une profondeur supposee.
  const queue: [string, string, number][] = [[USER_ROOT, rootFen, 0]];
  while (queue.length) {
    const [parentId, parentFen, ply] = queue.shift()!;
    const kids = (byParent.get(parentId) ?? []).sort((a, b) => a.order_index - b.order_index);
    const [, turn, , , , fullmove] = parentFen.split(' ');
    out[parentId].children = kids.map((k) => k.id);
    for (const k of kids) {
      out[k.id] = {
        id: k.id,
        parent_id: parentId,
        ply: ply + 1,
        move_number: Number(fullmove) || 1,
        color: turn === 'b' ? 'black' : 'white',
        uci: k.move_uci,
        san: k.move_san,
        fen: k.fen_after,
        comment: k.comment,
        starting_comment: '',
        nags: [],
        children: [],
      };
      queue.push([k.id, k.fen_after, ply + 1]);
    }
  }
  return out;
}
