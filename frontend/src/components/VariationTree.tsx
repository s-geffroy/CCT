// Vue arborescente avec react-arborist, controlee par notre modele.
// Reorganisation par glisser-deposer DESACTIVEE : deplacer une suite de coups
// sous une autre position la rendrait illegale.
import { Tree, type NodeRendererProps } from 'react-arborist';
import type { TreeRow } from '../adapters/variationTree';

type Props = {
  rows: TreeRow[];
  selectedNodeId: string | null;
  onSelect: (nodeId: string) => void;
  onLoadMore?: (nodeId: string) => void;
  height?: number;
};

function Row({ node, style }: NodeRendererProps<TreeRow>) {
  const row = node.data;
  return (
    <div style={style} className={`tree-row ${row.kind} ${node.isSelected ? 'selected' : ''}`}>
      {row.kind === 'variation' ? (
        <button type="button" className="toggle" onClick={() => node.toggle()} aria-expanded={node.isOpen}>
          {node.isOpen ? '▾' : '▸'} {row.label}
        </button>
      ) : (
        <>
          {node.children && node.children.length > 0 && (
            <button type="button" className="toggle" onClick={() => node.toggle()} aria-label="replier les variantes">
              {node.isOpen ? '▾' : '▸'}
            </button>
          )}
          <span className="san">{row.label}</span>
          {row.comment && <span className="comment"> {row.comment}</span>}
        </>
      )}
    </div>
  );
}

export function VariationTree({ rows, selectedNodeId, onSelect, onLoadMore, height = 360 }: Props) {
  return (
    <Tree<TreeRow>
      data={rows}
      selection={selectedNodeId ?? undefined}
      openByDefault
      disableDrag
      disableDrop
      disableEdit
      disableMultiSelection
      rowHeight={28}
      indent={18}
      width="100%"
      height={height}
      aria-label="Arbre des variantes"
      onActivate={(node) => {
        if (!node.data.nodeId) return;
        if (node.data.kind === 'more') onLoadMore?.(node.data.nodeId);
        else onSelect(node.data.nodeId);
      }}
    >
      {Row}
    </Tree>
  );
}
