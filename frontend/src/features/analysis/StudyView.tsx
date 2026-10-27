// Mode A : etude libre d'une position. Le tableau des variantes est sous
// l'echiquier ; le serveur refuse l'analyse si une seance non revelee porte
// sur la meme position.
import { useEffect, useState } from 'react';
import { api, ApiFailure, type AnalysisJob, type Position } from '../../api/client';
import { ChessboardAdapter } from '../../adapters/ChessboardAdapter';
import { AnalysisPanel, type ShownPosition } from './AnalysisPanel';
import { useJobStream } from './useJobStream';
import { ReferenceTreeView } from '../reference/ReferenceTreeView';
import { isBuilding, useTree } from '../reference/useTree';

function message(err: unknown): string {
  return err instanceof ApiFailure ? `${err.error.message} (${err.error.code})` : 'Erreur inattendue.';
}

export function StudyView({ positionId }: { positionId: string }) {
  const [position, setPosition] = useState<Position | null>(null);
  const [initial, setInitial] = useState<AnalysisJob | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState({ target_depth: 21, multipv_max: 20, budget_s: 300 });
  const [shown, setShown] = useState<ShownPosition | null>(null);
  const [orientation, setOrientation] = useState<'white' | 'black'>('white');
  const job = useJobStream(jobId, initial);
  const [treeId, setTreeId] = useState<string | null>(null);
  const { tree, refresh: refreshTree } = useTree(treeId);

  useEffect(() => {
    api.position(positionId).then((p) => { setPosition(p); setOrientation(p.turn); }).catch((e) => setError(message(e)));
    // Reprendre la derniere analyse de cette position, s'il y en a une.
    api.jobs(positionId).then((r) => {
      const last = r.items[0];
      if (last) { setInitial(last); setJobId(last.id); }
    }).catch(() => {});
    api.referenceTrees(positionId).then((r) => setTreeId(r.items[0]?.id ?? null)).catch(() => {});
  }, [positionId]);

  async function buildTree() {
    setError(null);
    try {
      const created = await api.createTree(positionId, settings);
      setShown(null);
      setTreeId(created.id);
      refreshTree(created);
      // L'analyse racine de l'arbre est celle de l'etude : on la suit aussi.
      if (created.visibility === 'full') {
        const rootJob = created.nodes.find((n) => n.ply === 0)?.job_id;
        if (rootJob && rootJob !== jobId) { setInitial(null); setJobId(rootJob); }
      }
    } catch (err) {
      setError(message(err));
    }
  }

  async function start() {
    setError(null);
    try {
      const created = await api.createJob(positionId, settings);
      setShown(null);
      setInitial(created);
      setJobId(created.id);
    } catch (err) {
      setError(message(err));
    }
  }

  async function stop() {
    if (jobId) await api.cancelJob(jobId).catch((err) => setError(message(err)));
  }

  if (!position) return error ? <p role="alert" className="error">{error}</p> : <p>Chargement…</p>;
  const running = job?.visibility === 'full' && (job.state === 'running' || job.state === 'queued');

  return (
    <section className="study" aria-label="Etude libre">
      <h2>Etude libre (A)</h2>
      {error && <p role="alert" className="error">{error}</p>}
      <div className="workspace">
        <div>
          <ChessboardAdapter id="study-board" fen={shown?.fen ?? position.fen} orientation={orientation} mode="locked"
                             lastMove={shown?.lastMove ?? null} />
          <p className="shown" data-testid="shown-position">
            {shown ? `Affiche : ${shown.label}` : 'Affiche : position etudiee'}
          </p>
          <button type="button" onClick={() => setOrientation((o) => (o === 'white' ? 'black' : 'white'))}>Retourner l'echiquier</button>
        </div>
        <div className="side">
          <fieldset>
            <legend>Recherche</legend>
            <label>Profondeur cible{' '}
              <input type="number" min={8} max={32} value={settings.target_depth}
                     onChange={(e) => setSettings({ ...settings, target_depth: Number(e.target.value) })} />
            </label>
            <label>Variantes (MultiPV){' '}
              <input type="number" min={1} max={20} value={settings.multipv_max}
                     onChange={(e) => setSettings({ ...settings, multipv_max: Number(e.target.value) })} />
            </label>
            <label>Budget (s){' '}
              <input type="number" min={5} max={1800} value={settings.budget_s}
                     onChange={(e) => setSettings({ ...settings, budget_s: Number(e.target.value) })} />
            </label>
          </fieldset>
          <button type="button" className="primary" onClick={start} disabled={running}>Analyser</button>
          <button type="button" onClick={stop} disabled={!running}>Arreter</button>
          <button type="button" onClick={buildTree} disabled={isBuilding(tree)}
                  title="Analyse racine, puis defenses adverses critiques et meilleures ripostes, sous plafonds">
            Construire l'arbre de reference
          </button>
          {job?.visibility === 'full' && job.reused && <p className="note">Resultat deja calcule avec ces reglages (cache).</p>}
        </div>
      </div>
      {job?.visibility === 'full' && <AnalysisPanel key={job.id} job={job} rootFen={position.fen} onShow={setShown} />}
      {job?.visibility === 'hidden' && (
        <p className="note">Analyse masquee : une seance d'entrainement non revelee porte sur cette position.</p>
      )}
      {tree?.visibility === 'full' && (
        <ReferenceTreeView tree={tree} rootFen={position.fen} onShow={setShown}
                           onExpand={(path) => api.expand(tree.id, path).then((t) => refreshTree(t))} />
      )}
    </section>
  );
}
