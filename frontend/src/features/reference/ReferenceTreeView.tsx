// Arbre de reference : selectif, jamais exhaustif. Chaque noeud dit pourquoi
// il a ete retenu et ou en est son analyse ; « non explore » n'est jamais
// « mauvais ». Ne recoit que des arbres visibles (filtrage cote serveur).
import { useMemo, useState } from 'react';
import { ApiFailure, type ReferenceNode, type SelectionReason, type NodeStatus, type VisibleTree } from '../../api/client';
import { formatScore, numberedLine } from '../analysis/format';
import type { ShownPosition } from '../analysis/AnalysisPanel';

export const REASON_LABEL: Record<SelectionReason, string> = {
  root: 'position etudiee',
  top_rank: 'meilleur coup',
  opponent_best_defense: 'meilleure defense',
  opponent_alternative: 'defense alternative',
  user_branch: 'votre branche',
  user_requested_reanalysis: 'demande',
};

export const STATUS_LABEL: Record<NodeStatus, string> = {
  queued: 'en attente',
  provisional: 'en cours',
  depth_met: 'profondeur atteinte',
  budget_exhausted: 'budget epuise',
  incomplete: 'incomplete',
  failed: 'echec',
  pruned_by_policy: 'non analysee (plafonds)',
  terminal: 'position terminale',
};

const TREE_STATE: Record<VisibleTree['state'], string> = {
  building: 'construction en cours',
  complete: 'terminee (dans les limites de la politique)',
  budget_exhausted: 'arretee : budget de temps epuise',
  node_limit: 'arretee : nombre maximal de noeuds atteint',
  failed: 'echec de l\'analyse racine',
};

type Props = {
  tree: VisibleTree;
  rootFen: string;
  onShow: (shown: ShownPosition | null) => void;
  onExpand: (path: string[]) => Promise<unknown>;
};

export function ReferenceTreeView({ tree, rootFen, onShow, onExpand }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const byId = useMemo(() => Object.fromEntries(tree.nodes.map((n) => [n.id, n])), [tree.nodes]);
  const children = useMemo(() => {
    const out: Record<string, ReferenceNode[]> = {};
    for (const n of tree.nodes) if (n.parent_id) (out[n.parent_id] ??= []).push(n);
    return out;
  }, [tree.nodes]);
  const root = tree.nodes.find((n) => n.ply === 0);
  const selected = selectedId ? byId[selectedId] ?? null : null;

  function pathSans(node: ReferenceNode): string[] {
    const sans: string[] = [];
    for (let n: ReferenceNode | undefined = node; n && n.move_san; n = n.parent_id ? byId[n.parent_id] : undefined) sans.unshift(n.move_san);
    return sans;
  }

  function select(node: ReferenceNode) {
    setSelectedId(node.id);
    onShow(node.ply === 0 ? null : {
      fen: node.fen,
      lastMove: node.move_uci ? { from: node.move_uci.slice(0, 2), to: node.move_uci.slice(2, 4) } : null,
      label: numberedLine(rootFen, pathSans(node)),
    });
  }

  async function expand(path: string[]) {
    setError(null);
    try {
      await onExpand(path);
    } catch (err) {
      setError(err instanceof ApiFailure ? `${err.error.message} (${err.error.code})` : 'Erreur inattendue.');
    }
  }

  function renderNode(node: ReferenceNode): React.ReactNode {
    const best = node.lines[0];
    const kids = children[node.id] ?? [];
    return (
      <li key={node.id} data-path={node.path_uci.join(' ')} data-reason={node.selection_reason}>
        <button type="button" className={`move ${node.id === selectedId ? 'selected' : ''}`} onClick={() => select(node)}>
          {numberedLine(byId[node.parent_id!] ? byId[node.parent_id!].fen : rootFen, [node.move_san ?? '?'])}
        </button>
        <span className={`tag reason-${node.selection_reason}`}>{REASON_LABEL[node.selection_reason]}</span>
        <span className={`tag status-${node.status}`}>{STATUS_LABEL[node.status]}{node.reanalysed ? ' · reanalyse' : ''}</span>
        {best && <span className="score" title="evaluation apres ce coup, point de vue des Blancs">{formatScore(best.score)} (prof. {best.exact_depth})</span>}
        {kids.length > 0 && <ul>{kids.map(renderNode)}</ul>}
      </li>
    );
  }

  const inTree = new Set(tree.nodes.map((n) => n.path_uci.join(' ')));

  return (
    <section className="reference-tree" aria-label="Arbre de reference">
      <h3>Arbre de reference</h3>
      <p data-testid="tree-state" data-state={tree.state}>
        {TREE_STATE[tree.state]} · {tree.nodes.length} noeud(s)
        {tree.pruned_count > 0 && ` · ${tree.pruned_count} branche(s) non explorees (plafonds)`}
        {` · ${tree.spent_s.auto.toFixed(0)} s / ${tree.settings.budget_s} s d'exploration`}
      </p>
      <p className="coverage">
        Arbre selectif, pas exhaustif : les meilleurs coups, les defenses adverses critiques et vos propres branches,
        dans la limite de {tree.settings.max_nodes} noeuds et {tree.settings.budget_s} s. Une branche absente n'est pas une mauvaise branche.
      </p>
      {error && <p role="alert" className="error">{error}</p>}
      {root && (
        <ul className="ref-tree">
          <li>
            <button type="button" className={`move ${root.id === selectedId ? 'selected' : ''}`} onClick={() => select(root)}>Position etudiee</button>
            <ul>{(children[root.id] ?? []).map(renderNode)}</ul>
          </li>
        </ul>
      )}
      {selected && (
        <div className="node-detail" aria-label="Noeud selectionne">
          <h4>{selected.ply === 0 ? 'Position etudiee' : numberedLine(rootFen, pathSans(selected))}</h4>
          <p>
            {STATUS_LABEL[selected.status]}
            {selected.target_depth !== null && ` · profondeur visee ${selected.target_depth}`}
            {' '}
            {selected.status !== 'terminal' && (
              <button type="button" onClick={() => expand(selected.path_uci)}>Approfondir</button>
            )}
          </p>
          {selected.lines.length > 0 && (
            <div className="table-scroll">
              <table className="lines">
                <thead><tr><th>#</th><th>Coup</th><th>Eval. (Blancs)</th><th>Prof.</th><th>Suite</th><th /></tr></thead>
                <tbody>
                  {selected.lines.map((l) => {
                    const childPath = [...selected.path_uci, l.root_move_uci];
                    return (
                      <tr key={l.rank}>
                        <td>{l.rank}</td>
                        <td>{l.root_move_san ?? l.root_move_uci}</td>
                        <td className="score">{formatScore(l.score)}</td>
                        <td>{l.exact_depth}</td>
                        <td className="pv">{numberedLine(selected.fen, l.pv_san.slice(0, 10))}{l.pv_san.length > 10 ? ' …' : ''}</td>
                        <td>{!inTree.has(childPath.join(' ')) && (
                          <button type="button" onClick={() => expand(childPath)}>Analyser ce coup</button>
                        )}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
