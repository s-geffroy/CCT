// Debriefing (doc 07) : dimensions separees, diagnostics avec preuves et
// incertitudes. Pas de note globale. Provisoire tant que l'arbre se construit.
import { useEffect, useState } from 'react';
import {
  api,
  ApiFailure,
  type Attempt,
  type DiagnosticCategory,
  type NodeVerdict,
  type Review,
} from '../../api/client';
import { formatScore, numberedLine } from '../analysis/format';
import type { ShownPosition } from '../analysis/AnalysisPanel';

const POLL_MS = 3000;

export const CATEGORY_LABEL: Record<DiagnosticCategory, string> = {
  candidate_found: 'Candidat trouve',
  candidate_omitted: 'Candidat non envisage',
  critical_defense_omitted: 'Defense critique oubliee',
  illegal_continuation: 'Coup illegal',
  evaluation_mismatch: 'Appreciation contredite',
  acceptable_alternative: 'Alternative acceptable',
  tactical_refutation: 'Refutation',
  unverified: 'Non verifie',
  no_trace: 'Sans trace',
};

const CERTAINTY_LABEL = { certain: 'certain', verified: 'verifie par le moteur', uncertain: 'incertain', undetermined: 'non determine' } as const;

export const VERDICT_LABEL: Record<NodeVerdict['verdict'], string> = {
  concordant: 'concordant',
  acceptable: 'deviant mais acceptable',
  refuted: 'refute',
  unverified: 'non evalue',
  best_defense: 'meilleure defense',
  plausible_reply: 'reponse plausible',
  weaker_reply: 'reponse plus faible',
};

const QUALITY_TEXT = {
  final: 'Rapport etabli : arbre de reference termine.',
  provisional: 'Rapport provisoire : l\'arbre de reference se construit encore.',
  insufficient: 'Reference insuffisante : aucun verdict sur vos coups.',
} as const;

type Props = {
  sessionId: string;
  attempt: Attempt;
  rootFen: string;
  onShow: (shown: ShownPosition | null) => void;
  /** Change quand l'arbre de reference change : le rapport est alors recalcule. */
  refreshKey?: number;
};

export function ReviewPanel({ sessionId, attempt, rootFen, onShow, refreshKey = 0 }: Props) {
  const [review, setReview] = useState<Review | null>(null);
  const [error, setError] = useState<string | null>(null);
  const provisional = review?.status === 'available' && review.quality === 'provisional';

  useEffect(() => {
    let stop = false;
    const load = () => api.review(sessionId)
      .then((r) => { if (!stop) setReview(r); })
      .catch((err) => { if (!stop) setError(err instanceof ApiFailure ? err.error.message : 'Erreur inattendue.'); });
    void load();
    if (review !== null && !provisional) return () => { stop = true; };
    const id = setInterval(load, POLL_MS);
    return () => { stop = true; clearInterval(id); };
  }, [sessionId, provisional, review === null, refreshKey]);

  if (error) return <p role="alert" className="error">{error}</p>;
  if (!review) return <p>Debriefing en preparation…</p>;
  if (review.status === 'hidden') return <p className="note">{review.message}</p>;

  const d = review.dimensions;
  const tree = attempt.tree;
  const userNodes = Object.values(tree).map((n) => ({ node: n, verdict: review.node_verdicts[n.id] }))
    .filter((x) => x.verdict)
    .sort((a, b) => a.verdict.path_uci.length - b.verdict.path_uci.length || a.node.order_index - b.node.order_index);

  function pathSans(nodeId: string): string[] {
    const sans: string[] = [];
    for (let id: string | null = nodeId; id && tree[id]; id = tree[id].parent_id) sans.unshift(tree[id].move_san);
    return sans;
  }

  function showFen(fen: unknown, label: string) {
    if (typeof fen === 'string') onShow({ fen, lastMove: null, label });
  }

  return (
    <section className="review" aria-label="Diagnostics" data-quality={review.quality}>
      <h4>Diagnostics</h4>
      <p className={`quality quality-${review.quality}`} data-testid="review-quality">
        {QUALITY_TEXT[review.quality]}
        {review.quality_notes.length > 0 && ` (${review.quality_notes.join(' ; ')})`}
      </p>
      <p className="legend">
        Une evaluation n'est une preuve que si elle est exacte et atteint la profondeur {review.policy.min_verdict_depth} ;
        une refutation exige un changement de resultat (gagnant, equilibre, perdant), pas seulement un ecart de centipions.
      </p>

      {(d.coverage || d.anticipation || d.accuracy || d.horizon || d.evaluation) && (
        <dl className="dimensions">
          {d.coverage && (<><dt>Candidats pertinents</dt><dd>{d.coverage.status === 'determined'
            ? `${d.coverage.found} / ${d.coverage.known_relevant} (${(d.coverage.relevant ?? []).join(', ')})` : 'non determine'}</dd></>)}
          {d.anticipation && (<><dt>Defenses adverses</dt><dd>{d.anticipation.found} trouvee(s), {d.anticipation.missed} manquee(s), {d.anticipation.unverified} non verifiee(s)</dd></>)}
          {d.accuracy && (<><dt>Lignes restituees</dt><dd>{d.accuracy.legal_moves}/{d.accuracy.moves_total} coups legaux ; {d.accuracy.lines_without_refutation} ligne(s) sans refutation demontree, {d.accuracy.lines_refuted} refutee(s), {d.accuracy.lines_unverified} non verifiee(s)</dd></>)}
          {d.horizon && (<><dt>Horizon restitue</dt><dd>{d.horizon.max_plies} demi-coups au plus, {d.horizon.median_plies} en mediane ({d.horizon.lines} ligne(s))</dd></>)}
          {d.evaluation && (<><dt>Vos appreciations</dt><dd>{d.evaluation.concordant} concordante(s), {d.evaluation.mismatch} contredite(s), {d.evaluation.not_comparable} non comparable(s)</dd></>)}
        </dl>
      )}

      <ol className="diagnostics">
        {review.diagnostics.map((diag, i) => {
          const fen = diag.evidence.turning_point_fen ?? diag.evidence.fen;
          return (
            <li key={i} className={`diag diag-${diag.category}`} data-category={diag.category}>
              <strong>{CATEGORY_LABEL[diag.category]}</strong>{' '}
              <span className="certainty">({CERTAINTY_LABEL[diag.certainty]})</span> : {diag.explanation}
              {typeof fen === 'string' && (
                <> {' '}<button type="button" onClick={() => showFen(fen, CATEGORY_LABEL[diag.category])}>Voir la position</button></>
              )}
            </li>
          );
        })}
      </ol>

      {userNodes.length > 0 && (
        <div className="table-scroll">
          <table className="verdicts">
            <caption>Vos coups</caption>
            <thead><tr><th>Ligne</th><th>Verdict</th><th>Eval. (Blancs)</th><th>Reference</th></tr></thead>
            <tbody>
              {userNodes.map(({ node, verdict }) => (
                <tr key={node.id} data-verdict={verdict.verdict}>
                  <td><button type="button" className="move" onClick={() => onShow({
                    fen: node.fen_after, lastMove: { from: node.move_uci.slice(0, 2), to: node.move_uci.slice(2, 4) },
                    label: numberedLine(rootFen, pathSans(node.id)),
                  })}>{numberedLine(rootFen, pathSans(node.id))}</button></td>
                  <td>{VERDICT_LABEL[verdict.verdict]}{verdict.reason ? ` (${verdict.reason})` : ''}
                    {verdict.transposition_of ? ' · transposition d\'une branche de reference' : ''}</td>
                  <td className="score">{verdict.score ? `${formatScore(verdict.score)} (prof. ${verdict.depth})` : '—'}</td>
                  <td>{verdict.best_move_san && verdict.best_score ? `${verdict.best_move_san} ${formatScore(verdict.best_score)}` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
