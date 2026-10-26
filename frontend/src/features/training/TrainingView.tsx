// Seance d'entrainement : B (calcul mental) ou C (arbre personnel), puis
// soumission figee, revelation et debriefing. Aucune donnee moteur n'est
// demandee ni affichee avant la revelation : le serveur n'en envoie pas.
import { useEffect, useMemo, useState } from 'react';
import {
  api,
  ApiFailure,
  type Assessment,
  type SelfAssessment,
  type Session,
} from '../../api/client';
import { ChessboardAdapter } from '../../adapters/ChessboardAdapter';
import { USER_ROOT, userTreeToNodes } from '../../adapters/userTree';
import { MoveText } from '../../components/MoveText';
import { formatHistory } from '../positions/RetainedPanel';

export const ASSESSMENT_LABEL: Record<Assessment, string> = {
  white_better: 'avantage blanc',
  black_better: 'avantage noir',
  equal: 'egalite',
  initiative: 'initiative',
  attack: 'attaque',
  unclear: 'incertain',
};

const STATE_LABEL: Record<Session['state'], string> = {
  active: 'en cours',
  submitted: 'soumise (figee)',
  revealed: 'revelee',
  reviewed: 'debriefee',
  abandoned: 'abandonnee',
};

function message(err: unknown): string {
  return err instanceof ApiFailure ? `${err.error.message} (${err.error.code})` : 'Erreur inattendue.';
}

function Timer({ since }: { since: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const s = Math.max(0, Math.floor((now - Date.parse(since)) / 1000));
  return <span className="timer" aria-live="off">{Math.floor(s / 60)} min {String(s % 60).padStart(2, '0')} s</span>;
}

type Props = { sessionId: string; onExit: () => void };

export function TrainingView({ sessionId, onExit }: Props) {
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string>(USER_ROOT);
  const [sanInput, setSanInput] = useState('');
  const [orientation, setOrientation] = useState<'white' | 'black'>('white');
  const [showTimer, setShowTimer] = useState(false);
  const [notesHidden, setNotesHidden] = useState(false);
  const [notes, setNotes] = useState('');
  const [lines, setLines] = useState('');
  const [finishing, setFinishing] = useState(false);
  const [assessment, setAssessment] = useState<SelfAssessment>({ candidates: '', main_threat: '', evaluation: null });
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [comment, setComment] = useState('');

  useEffect(() => {
    api.session(sessionId).then((s) => {
      setSession(s);
      setNotes(s.notes);
      setLines(s.lines_text);
      setOrientation(s.position.turn);
    }).catch((err) => setError(message(err)));
  }, [sessionId]);

  const rootFen = session?.position.fen ?? '';
  const active = session?.state === 'active';
  const revealed = session?.state === 'revealed' || session?.state === 'reviewed';
  // Apres soumission, on montre la tentative figee, pas l'arbre courant.
  const shownTree = session?.attempt?.tree ?? session?.tree.nodes ?? {};
  const nodes = useMemo(() => userTreeToNodes(shownTree, rootFen), [shownTree, rootFen]);
  const selectedNode = nodes[selected] ?? nodes[USER_ROOT];
  const userNode = session && selected !== USER_ROOT ? shownTree[selected] : undefined;

  useEffect(() => setComment(userNode?.comment ?? ''), [userNode?.id, userNode?.comment]);
  useEffect(() => {
    if (!nodes[selected]) setSelected(USER_ROOT);
  }, [nodes, selected]);

  if (!session) return error ? <p role="alert" className="error">{error}</p> : <p>Chargement…</p>;
  const s = session;

  async function act(op: () => Promise<Session | { session: Session }>, after?: (s: Session) => void) {
    setError(null);
    try {
      const result = await op();
      const next = 'session' in result ? result.session : result;
      setSession(next);
      after?.(next);
    } catch (err) {
      setError(message(err));
      // Conflit de revision : l'etat serveur fait foi.
      if (err instanceof ApiFailure && err.status === 409) api.session(s.id).then(setSession).catch(() => {});
    }
  }

  const parentForNew = selected === USER_ROOT ? null : selected;
  const addMove = (move: string) => {
    const before = new Set(Object.keys(s.tree.nodes));
    return act(() => api.addNode(s, parentForNew, move), (next) => {
      // Le nouveau coup devient le coup selectionne : on enchaine la variante.
      const created = Object.keys(next.tree.nodes).find((id) => !before.has(id));
      if (created) setSelected(created);
      setSanInput('');
    });
  };

  const saveNotes = () => {
    if (notes === s.notes && lines === s.lines_text) return Promise.resolve();
    return act(() => api.saveNotes(s, { notes, ...(s.mode === 'mental' ? { lines_text: lines } : {}) }));
  };

  const lastMove = selectedNode?.uci ? { from: selectedNode.uci.slice(0, 2), to: selectedNode.uci.slice(2, 4) } : null;

  return (
    <section className="training" aria-label="Seance d'entrainement">
      <header className="training-head">
        <h2>{s.mode === 'mental' ? 'Calcul mental (B)' : 'Arbre personnel (C)'}</h2>
        <span className="badge" data-testid="session-state">{STATE_LABEL[s.state]}</span>
        {active && (
          <label className="timer-toggle">
            <input type="checkbox" checked={showTimer} onChange={(e) => setShowTimer(e.target.checked)} /> chronometre
          </label>
        )}
        {active && showTimer && <Timer since={s.started_at} />}
        {s.duration_ms !== null && <span>duree : {Math.round(s.duration_ms / 1000)} s</span>}
      </header>
      {error && <p role="alert" className="error">{error}</p>}

      <div className="workspace">
        <div>
          <ChessboardAdapter
            id="training-board"
            fen={selectedNode?.fen ?? rootFen}
            orientation={orientation}
            mode={active && s.mode === 'tree' ? 'play' : 'locked'}
            lastMove={lastMove}
            onMove={addMove}
          />
          <button type="button" onClick={() => setOrientation((o) => (o === 'white' ? 'black' : 'white'))}>
            Retourner l'echiquier
          </button>
        </div>

        <div className="side">
          <p className="context">
            Position de la seance : trait aux {s.position.turn === 'white' ? 'Blancs' : 'Noirs'}
            {s.position.history_san?.length ? ` · apres ${formatHistory(s.position)}` : ''}
          </p>

          {s.mode === 'tree' && (
            <>
              <MoveText nodes={nodes} rootId={USER_ROOT} selectedNodeId={selected === USER_ROOT ? null : selected} onSelect={setSelected} />
              <button type="button" onClick={() => setSelected(USER_ROOT)}>Position de depart</button>
              {active && (
                <div className="tree-actions">
                  <form onSubmit={(e) => { e.preventDefault(); if (sanInput.trim()) void addMove(sanInput.trim()); }}>
                    <label>
                      Ajouter un coup {selected === USER_ROOT ? 'depuis la position de depart' : `apres ${selectedNode?.san}`}{' '}
                      <input aria-label="Coup (SAN ou UCI)" value={sanInput} onChange={(e) => setSanInput(e.target.value)} size={8} />
                    </label>
                    <button type="submit">Ajouter</button>
                  </form>
                  <button type="button" disabled={!s.can_undo} onClick={() => act(() => api.undo(s))}>Annuler</button>
                  <button type="button" disabled={!s.can_redo} onClick={() => act(() => api.redo(s))}>Retablir</button>
                  {userNode && (
                    <fieldset>
                      <legend>Coup selectionne : {selectedNode?.san}</legend>
                      <label>
                        Commentaire{' '}
                        <input value={comment} onChange={(e) => setComment(e.target.value)} size={30} aria-label="Commentaire du coup" />
                      </label>
                      <button type="button" onClick={() => act(() => api.patchNode(s, userNode.id, { comment }))}>Enregistrer</button>
                      <label>
                        Mon appreciation{' '}
                        <select
                          aria-label="Mon appreciation"
                          value={userNode.human_assessment ?? ''}
                          onChange={(e) => act(() => api.patchNode(s, userNode.id, e.target.value
                            ? { human_assessment: e.target.value as Assessment } : { clear_assessment: true }))}
                        >
                          <option value="">—</option>
                          {Object.entries(ASSESSMENT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                        </select>
                      </label>
                      <button type="button" onClick={() => act(() => api.patchNode(s, userNode.id, { promote: true }))}>
                        Promouvoir en suite principale
                      </button>
                      {!confirmDelete ? (
                        <button type="button" onClick={() => setConfirmDelete(true)}>Supprimer ce coup et sa suite</button>
                      ) : (
                        <span role="group" aria-label="Confirmer la suppression">
                          Supprimer {selectedNode?.san} et toute sa suite ?{' '}
                          <button type="button" onClick={() => { setConfirmDelete(false); void act(() => api.deleteNode(s, userNode.id)); }}>Oui, supprimer</button>
                          <button type="button" onClick={() => setConfirmDelete(false)}>Non</button>
                        </span>
                      )}
                    </fieldset>
                  )}
                </div>
              )}
            </>
          )}

          {s.mode === 'mental' && active && (
            <div className="mental">
              <p>Calculez sans toucher l'echiquier. La saisie ci-dessous est facultative ; elle n'est jugee qu'au debriefing.</p>
              {s.allow_text_notes && (
                <>
                  <button type="button" onClick={() => setNotesHidden((h) => !h)}>{notesHidden ? 'Afficher la saisie' : 'Masquer la saisie'}</button>
                  {!notesHidden && (
                    <>
                      <label className="block">
                        Mes variantes (une par ligne, notation SAN)
                        <textarea aria-label="Mes variantes" value={lines} onChange={(e) => setLines(e.target.value)} onBlur={saveNotes} rows={6} cols={50} />
                      </label>
                      <label className="block">
                        Notes
                        <textarea aria-label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} onBlur={saveNotes} rows={3} cols={50} />
                      </label>
                    </>
                  )}
                </>
              )}
            </div>
          )}

          {active && !finishing && (
            <div className="finish">
              <button type="button" className="primary" onClick={async () => { await saveNotes(); setFinishing(true); }}>
                {s.mode === 'mental' ? "J'ai termine" : 'Terminer mon calcul'}
              </button>
              {!confirmAbandon ? (
                <button type="button" onClick={() => setConfirmAbandon(true)}>Abandonner la seance</button>
              ) : (
                <span role="group" aria-label="Confirmer l'abandon">
                  Abandonner ? La seance ne pourra plus etre soumise.{' '}
                  <button type="button" onClick={() => act(() => api.abandon(s), () => setConfirmAbandon(false))}>Oui, abandonner</button>
                  <button type="button" onClick={() => setConfirmAbandon(false)}>Non</button>
                </span>
              )}
            </div>
          )}

          {active && finishing && (
            <form className="self-assessment" aria-label="Autoevaluation" onSubmit={(e) => { e.preventDefault(); void act(() => api.submit(s, assessment)); }}>
              <p>Autoevaluation facultative, avant de figer votre tentative :</p>
              <label className="block">Mes coups candidats
                <input value={assessment.candidates} onChange={(e) => setAssessment({ ...assessment, candidates: e.target.value })} />
              </label>
              <label className="block">Menace principale
                <input value={assessment.main_threat} onChange={(e) => setAssessment({ ...assessment, main_threat: e.target.value })} />
              </label>
              <label className="block">Estimation de la position
                <select value={assessment.evaluation ?? ''} onChange={(e) => setAssessment({ ...assessment, evaluation: (e.target.value || null) as Assessment | null })}>
                  <option value="">—</option>
                  {Object.entries(ASSESSMENT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
              <button type="submit" className="primary">Soumettre ma tentative</button>
              <button type="button" onClick={() => setFinishing(false)}>Continuer a calculer</button>
            </form>
          )}

          {s.state === 'submitted' && (
            <div className="submitted">
              <p>Tentative figee : elle ne peut plus etre modifiee.</p>
              <button type="button" className="primary" onClick={() => act(() => api.reveal(s))}>Reveler</button>
            </div>
          )}

          {revealed && s.attempt && <Debrief session={s} />}

          {s.state === 'abandoned' && <p>Seance abandonnee.</p>}

          <p className="exports">
            Exporter : <a href={`/api/v1/sessions/${s.id}/export`} download>JSON</a> ·{' '}
            <a href={`/api/v1/sessions/${s.id}/export?format=pgn`} download>PGN</a>
          </p>
          <button type="button" onClick={onExit}>Retour aux positions</button>
        </div>
      </div>
    </section>
  );
}

function Debrief({ session }: { session: Session }) {
  const attempt = session.attempt!;
  const sa = attempt.self_assessment;
  return (
    <section className="debrief" aria-label="Debriefing">
      <h3>Debriefing</h3>
      {attempt.no_trace && (
        <p>Seance mentale sans transcription : seule votre autoevaluation est disponible, aucun diagnostic de calcul n'est possible.</p>
      )}
      {attempt.written_lines && attempt.written_lines.length > 0 && (
        <>
          <h4>Vos variantes ecrites</h4>
          <ol className="written-lines">
            {attempt.written_lines.map((line, i) => (
              <li key={i} data-testid="written-line">
                <span>{formatHistory({ history_san: line.moves_san, initial_fen: attempt.root_fen }) || '—'}</span>
                {line.error && (
                  <span className="error"> · coup {line.error.ply} « {line.error.token} » : {line.error.message}</span>
                )}
              </li>
            ))}
          </ol>
        </>
      )}
      {sa && (sa.candidates || sa.main_threat || sa.evaluation) && (
        <dl>
          {sa.candidates && (<><dt>Candidats annonces</dt><dd>{sa.candidates}</dd></>)}
          {sa.main_threat && (<><dt>Menace principale</dt><dd>{sa.main_threat}</dd></>)}
          {sa.evaluation && (<><dt>Estimation</dt><dd>{ASSESSMENT_LABEL[sa.evaluation]}</dd></>)}
        </dl>
      )}
      {attempt.notes && <p className="notes">Notes : {attempt.notes}</p>}
      <p className="reference" data-testid="reference-status">{session.reference?.message}</p>
    </section>
  );
}
