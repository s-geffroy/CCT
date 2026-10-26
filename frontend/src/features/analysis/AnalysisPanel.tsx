// Tableau des variantes moteur, place SOUS l'echiquier (exigence du doc 04),
// avec l'avancement de la recherche et la navigation dans une ligne.
// Ne recoit que des travaux visibles : le serveur ne transmet rien d'autre.
import { useEffect, useMemo, useState } from 'react';
import type { AnalysisLine, VisibleJob } from '../../api/client';
import { formatScore, numberedLine } from './format';
import { pvPositions } from './pv';

const STATE_LABEL: Record<VisibleJob['state'], string> = {
  queued: 'en attente',
  running: 'calcul en cours',
  complete_depth: 'profondeur cible atteinte',
  budget_exhausted: 'budget de temps epuise',
  incomplete: 'arretee avant la profondeur cible',
  cancelled: 'arretee a votre demande',
  failed: 'echec du moteur',
  interrupted: 'interrompue (redemarrage)',
  terminal: 'position terminale',
};

const LINE_STATUS: Record<AnalysisLine['status'], string> = {
  provisional: 'provisoire',
  depth_met: 'terminee',
  budget_exhausted: 'budget epuise',
  cancelled: 'arretee',
  incomplete: 'incomplete',
};

export type ShownPosition = { fen: string; lastMove: { from: string; to: string } | null; label: string };

type Props = {
  job: VisibleJob;
  rootFen: string;
  onShow: (shown: ShownPosition | null) => void;
};

export function AnalysisPanel({ job, rootFen, onShow }: Props) {
  const [selected, setSelected] = useState<number | null>(null);
  const [cursor, setCursor] = useState(0);
  const line = job.lines.find((l) => l.rank === selected) ?? null;
  const positions = useMemo(() => (line ? pvPositions(rootFen, line.pv_uci) : []), [line, rootFen]);
  const target = job.settings.target_depth;
  const running = job.state === 'running' || job.state === 'queued';

  useEffect(() => {
    if (!line || cursor === 0) {
      onShow(null);
      return;
    }
    const p = positions[cursor - 1];
    if (p) onShow({ fen: p.fen, lastMove: { from: p.from, to: p.to }, label: numberedLine(rootFen, line.pv_san.slice(0, cursor)) });
  }, [line, cursor, positions]);

  const stages = Object.entries(job.stages_reached_s).sort((a, b) => Number(a[0]) - Number(b[0]));

  return (
    <section className="analysis" aria-label="Variantes Stockfish">
      <h3>Variantes Stockfish</h3>
      <p className="analysis-state" data-testid="job-state" data-state={job.state}>
        {STATE_LABEL[job.state]}
        {job.elapsed_s !== null && ` · ${job.elapsed_s.toFixed(1)} s`}
        {job.nps ? ` · ${Math.round(job.nps / 1000)} k noeuds/s` : ''}
      </p>
      <p className="stages" aria-label="Paliers de profondeur">
        Paliers : {[8, 12, 16, 21].filter((d) => d <= target).concat(target > 21 ? [target] : []).map((d) => {
          const t = job.stages_reached_s[String(d)];
          return <span key={d} className={t !== undefined ? 'stage done' : 'stage'}>{d}{t !== undefined ? ` (${t.toFixed(1)} s)` : ''}</span>;
        })}
        {stages.length === 0 && running && ' …'}
      </p>
      {job.legal_moves !== null && job.multipv !== null && (
        <p className="coverage" data-testid="coverage">
          {job.root_coverage === 'all_root_moves'
            ? `Les ${job.multipv} coups legaux sont classes ; chaque ligne n'est qu'une suite possible, pas toutes les suites.`
            : `${job.multipv} premiers coups sur ${job.legal_moves} coups legaux : selection du moteur, pas une liste exhaustive.`}
        </p>
      )}
      {job.error && <p className="error">{job.error}</p>}
      <div className="table-scroll">
        <table className="lines">
          <thead>
            <tr><th>#</th><th>1er coup</th><th title="point de vue des Blancs">Eval. (Blancs)</th><th>Profondeur</th><th>Variante</th><th>Etat</th></tr>
          </thead>
          <tbody>
            {job.lines.map((l) => (
              <tr key={l.rank} data-rank={l.rank} aria-selected={l.rank === selected}
                  onClick={() => { setSelected(l.rank); setCursor(1); }}>
                <td>{l.rank}</td>
                <td><button type="button" className="move">{l.root_move_san ?? l.root_move_uci}</button></td>
                <td className="score">{l.status === 'provisional' ? '≈ ' : ''}{formatScore(l.score)}</td>
                <td title="profondeur attestee / cible">{l.exact_depth}/{target}</td>
                <td className="pv">{numberedLine(rootFen, l.pv_san.slice(0, 12))}{l.pv_san.length > 12 ? ' …' : ''}</td>
                <td>{LINE_STATUS[l.status]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {line && (
        <div className="pv-nav" role="group" aria-label="Parcourir la variante">
          <button type="button" onClick={() => setCursor(0)} aria-label="Debut">⏮</button>
          <button type="button" onClick={() => setCursor((c) => Math.max(0, c - 1))} aria-label="Coup precedent">◀</button>
          <span data-testid="pv-cursor">{cursor}/{positions.length}</span>
          <button type="button" onClick={() => setCursor((c) => Math.min(positions.length, c + 1))} aria-label="Coup suivant">▶</button>
          <button type="button" onClick={() => setCursor(positions.length)} aria-label="Fin">⏭</button>
        </div>
      )}
      <p className="legend">Evaluations en pions au point de vue des Blancs ; M+n : mat pour les Blancs, M-n : mat pour les Noirs ; ≈ : provisoire. La profondeur de recherche n'est pas la longueur de la variante affichee.</p>
    </section>
  );
}
