// Arbre de reference suivi par sondage tant qu'il se construit (les noeuds
// arrivent un a un ; un flux SSE par noeud serait disproportionne).
import { useEffect, useState } from 'react';
import { api, type ReferenceTree } from '../../api/client';

const POLL_MS = 2000;

export function isBuilding(tree: ReferenceTree | null): boolean {
  if (!tree) return false;
  return tree.visibility === 'full' ? tree.state === 'building' : tree.progress_category === 'running';
}

export function useTree(treeId: string | null, initial: ReferenceTree | null = null) {
  const [tree, setTree] = useState<ReferenceTree | null>(initial);
  const [tick, setTick] = useState(0);
  const building = isBuilding(tree);

  useEffect(() => {
    if (!treeId) {
      setTree(null);
      return;
    }
    let stop = false;
    const load = () => api.referenceTree(treeId).then((t) => { if (!stop) setTree(t); }).catch(() => {});
    void load();
    if (!building) return () => { stop = true; };
    const id = setInterval(load, POLL_MS);
    return () => { stop = true; clearInterval(id); };
  }, [treeId, building, tick]);

  /** Apres une demande d'expansion : l'arbre repart en construction. */
  const refresh = (next?: ReferenceTree) => {
    if (next) setTree(next);
    setTick((t) => t + 1);
  };
  return { tree, refresh };
}
