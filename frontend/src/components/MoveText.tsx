// Vue PGN en ligne : suite principale en texte continu, variantes entre
// parentheses et indentees. Alternative a l'arbre react-arborist, comparee au
// spike du Lot 0. Commentaires rendus en texte (jamais en HTML).
import type { PgnNode } from '../api/client';
import { moveLabel } from '../adapters/variationTree';

type Props = {
  nodes: Record<string, PgnNode>;
  rootId: string;
  selectedNodeId: string | null;
  onSelect: (nodeId: string) => void;
};

export function MoveText({ nodes, rootId, selectedNodeId, onSelect }: Props) {
  function renderLine(startId: string, depth: number): React.ReactNode[] {
    const out: React.ReactNode[] = [];
    let current: PgnNode | undefined = nodes[startId];
    let forceNumber = true;
    while (current) {
      const node: PgnNode = current;
      out.push(
        <button
          key={node.id}
          type="button"
          className={`move ${node.id === selectedNodeId ? 'selected' : ''}`}
          aria-current={node.id === selectedNodeId}
          onClick={() => onSelect(node.id)}
        >
          {moveLabel(node, forceNumber)}
        </button>,
      );
      if (node.comment) out.push(<span key={node.id + 'c'} className="comment"> {node.comment} </span>);
      forceNumber = false;
      const parent = node.parent_id ? nodes[node.parent_id] : undefined;
      if (parent && parent.children[0] === node.id && parent.children.length > 1) {
        for (const alt of parent.children.slice(1)) {
          out.push(
            <span key={'v' + alt} className="variation" style={{ marginLeft: `${depth + 1}em` }}>
              ( {renderLine(alt, depth + 1)} )
            </span>,
          );
        }
        forceNumber = true;
      }
      const next: string | undefined = node.children[0];
      current = next ? nodes[next] : undefined;
    }
    return out;
  }

  const root = nodes[rootId];
  if (!root || root.children.length === 0) return <p className="empty">Aucun coup.</p>;
  return (
    <div className="movetext" aria-label="Partie et variantes">
      {root.comment && <p className="comment">{root.comment}</p>}
      {renderLine(root.children[0], 0)}
    </div>
  );
}
