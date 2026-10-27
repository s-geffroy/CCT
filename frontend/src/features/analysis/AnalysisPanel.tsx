// Tableau des variantes moteur, place SOUS l'echiquier (exigence du doc 04),
// avec l'avancement de la recherche et la navigation dans une ligne.
// Ne recoit que des travaux visibles : le serveur ne transmet rien d'autre.
// Clavier (tableau focalise) : haut/bas changent de variante, gauche/droite
// parcourent ses coups, Debut/Fin vont aux extremites.
import { memo, useEffect, useMemo, useState } from 'react';
import type { AnalysisLine, EngineScore, VisibleJob } from '../../api/client';
import { Progress } from '@/components/ui/progress';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { numberedLine } from './format';
import { pvPositions } from './pv';
import { useScore } from '../settings/prefs';

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

type Filter = 'all' | 'captures' | 'checks';
const FILTER_LABEL: Record<Filter, string> = { all: 'tous les coups', captures: 'captures', checks: 'echecs' };

export type ShownPosition = { fen: string; lastMove: { from: string; to: string } | null; label: string };

type Props = {
  job: VisibleJob;
  rootFen: string;
  onShow: (shown: ShownPosition | null) => void;
};

type RowProps = {
  line: AnalysisLine;
  selected: boolean;
  target: number;
  rootFen: string;
  scoreText: (s: EngineScore) => string;
  onSelect: (rank: number) => void;
};

// Une ligne ne se redessine que si ses donnees changent (flux SSE frequent).
const LineRow = memo(function LineRow({ line: l, selected, target, rootFen, scoreText, onSelect }: RowProps) {
  const san = l.root_move_san ?? l.root_move_uci;
  return (
    <tr data-rank={l.rank} aria-selected={selected} onClick={() => onSelect(l.rank)}>
      <td>{l.rank}</td>
      <td><button type="button" className="move" tabIndex={-1}>{san}</button></td>
      <td className="score" aria-label={`evaluation ${scoreText(l.score)}${l.status === 'provisional' ? ', provisoire' : ''}`}>
        {l.status === 'provisional' ? '≈ ' : ''}{scoreText(l.score)}
      </td>
      <td title="profondeur attestee / cible" aria-label={`profondeur ${l.exact_depth} sur ${target}`}>{l.exact_depth}/{target}</td>
      <td className="pv">{numberedLine(rootFen, l.pv_san.slice(0, 12))}{l.pv_san.length > 12 ? ' …' : ''}</td>
      <td>{LINE_STATUS[l.status]}</td>
    </tr>
  );
});

export function AnalysisPanel({ job, rootFen, onShow }: Props) {
  const [selected, setSelected] = useState<number | null>(null);
  const [cursor, setCursor] = useState(0);
  const [filter, setFilter] = useState<Filter>('all');
  const score = useScore();
  const line = job.lines.find((l) => l.rank === selected) ?? null;
  const positions = useMemo(() => (line ? pvPositions(rootFen, line.pv_uci) : []), [line?.pv_uci.join(' '), rootFen]);
  const target = job.settings.target_depth;
  const running = job.state === 'running' || job.state === 'queued';
  const scoreText = useMemo(() => (s: EngineScore) => score.format(s, rootFen), [score, rootFen]);
  const visible = useMemo(() => job.lines.filter((l) => {
    const san = l.root_move_san ?? '';
    return filter === 'all' || (filter === 'captures' ? san.includes('x') : /[+#]$/.test(san));
  }), [job.lines, filter]);

  useEffect(() => {
    if (!line || cursor === 0) {
      onShow(null);
      return;
    }
    const p = positions[cursor - 1];
    if (p) onShow({ fen: p.fen, lastMove: { from: p.from, to: p.to }, label: numberedLine(rootFen, line.pv_san.slice(0, cursor)) });
  }, [line?.rank, cursor, positions]);

  const select = useMemo(() => (rank: number) => { setSelected(rank); setCursor(1); }, []);

  function onKey(e: React.KeyboardEvent) {
    const ranks = visible.map((l) => l.rank);
    const i = selected === null ? -1 : ranks.indexOf(selected);
    const keys: Record<string, () => void> = {
      ArrowDown: () => ranks.length && select(ranks[Math.min(ranks.length - 1, i + 1)]),
      ArrowUp: () => ranks.length && select(ranks[Math.max(0, i - 1)]),
      ArrowRight: () => setCursor((c) => Math.min(positions.length, c + 1)),
      ArrowLeft: () => setCursor((c) => Math.max(0, c - 1)),
      Home: () => setCursor(0),
      End: () => setCursor(positions.length),
    };
    if (keys[e.key]) {
      e.preventDefault();
      keys[e.key]();
    }
  }

  const stages = Object.entries(job.stages_reached_s).sort((a, b) => Number(a[0]) - Number(b[0]));
  const budget = job.settings.budget_s;

  return (
    <section className="analysis" aria-label="Variantes Stockfish">
      <h3>Variantes Stockfish</h3>
      <p className="analysis-state" data-testid="job-state" data-state={job.state} aria-live="polite">
        {STATE_LABEL[job.state]}
        {job.elapsed_s !== null && ` · ${job.elapsed_s.toFixed(1)} s`}
        {job.nps ? ` · ${Math.round(job.nps / 1000)} k noeuds/s` : ''}
      </p>
      {running && job.elapsed_s !== null && (
        // Temps ecoule sur le budget : jamais un « pourcentage de profondeur ».
        <Progress value={Math.min(100, (100 * job.elapsed_s) / budget)} className="max-w-md"
                  aria-label={`temps ecoule ${Math.round(job.elapsed_s)} s sur un budget de ${budget} s`} />
      )}
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
      {job.lines.length === 0 ? (
        <p className="empty">{running ? 'Premieres lignes dans un instant…' : 'Aucune ligne.'}</p>
      ) : (
        <>
          <label className="text-sm flex items-center gap-2 my-1">
            Afficher
            <NativeSelect size="sm" className="w-auto" value={filter} onChange={(e) => setFilter(e.target.value as Filter)}
                          aria-label="Filtrer les premiers coups">
              {(Object.keys(FILTER_LABEL) as Filter[]).map((f) => <NativeSelectOption key={f} value={f}>{FILTER_LABEL[f]}</NativeSelectOption>)}
            </NativeSelect>
            <span className="text-muted-foreground">(information : un filtre ne juge pas la qualite des coups)</span>
          </label>
          <div className="table-scroll" tabIndex={0} role="group" onKeyDown={onKey}
               aria-label="Tableau des variantes : fleches haut et bas pour changer de variante, gauche et droite pour la parcourir"
               aria-keyshortcuts="ArrowUp ArrowDown ArrowLeft ArrowRight Home End">
            <table className="lines">
              <thead>
                <tr><th>#</th><th>1er coup</th><th title={score.legend}>{score.label}</th><th>Profondeur</th><th>Variante</th><th>Etat</th></tr>
              </thead>
              <tbody>
                {visible.map((l) => (
                  <LineRow key={l.rank} line={l} selected={l.rank === selected} target={target} rootFen={rootFen}
                           scoreText={scoreText} onSelect={select} />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {line && (
        <div className="pv-nav" role="group" aria-label="Parcourir la variante">
          <button type="button" onClick={() => setCursor(0)} aria-label="Debut">⏮</button>
          <button type="button" onClick={() => setCursor((c) => Math.max(0, c - 1))} aria-label="Coup precedent">◀</button>
          <span data-testid="pv-cursor" aria-live="polite">{cursor}/{positions.length}</span>
          <button type="button" onClick={() => setCursor((c) => Math.min(positions.length, c + 1))} aria-label="Coup suivant">▶</button>
          <button type="button" onClick={() => setCursor(positions.length)} aria-label="Fin">⏭</button>
        </div>
      )}
      <p className="legend">{score.legend} ≈ : provisoire ; ≥ / ≤ : borne. La profondeur de recherche n'est pas la longueur de la variante affichee.</p>
    </section>
  );
}
