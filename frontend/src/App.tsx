// Page du spike Lot 0 : FEN -> echiquier, PGN a variantes -> arbre,
// coup joue -> legalite arbitree par le serveur, editeur a pieces libres.
// Aucune donnee moteur n'est affichee ici.
import { useEffect, useMemo, useState } from 'react';
import { api, ApiFailure, type FenValidation, type Meta, type PgnGame } from './api/client';
import { ChessboardAdapter } from './adapters/ChessboardAdapter';
import { toTreeRows } from './adapters/variationTree';
import { MoveText } from './components/MoveText';
import { VariationTree } from './components/VariationTree';
import { PositionEditor } from './features/PositionEditor';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
type Tab = 'fen' | 'pgn' | 'editor';
type PlayedLine = { uci: string; san: string; fen: string }[];

function message(err: unknown): string {
  return err instanceof ApiFailure ? `${err.error.message} (${err.error.code})` : 'Erreur inattendue.';
}

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [tab, setTab] = useState<Tab>('fen');
  const [fenInput, setFenInput] = useState(START);
  const [validation, setValidation] = useState<FenValidation | null>(null);
  const [rootFen, setRootFen] = useState(START);
  const [line, setLine] = useState<PlayedLine>([]);
  const [pgnText, setPgnText] = useState('');
  const [game, setGame] = useState<PgnGame | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [treeView, setTreeView] = useState<'arborist' | 'inline'>('inline');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.meta().then(setMeta).catch(() => setMeta(null));
  }, []);

  const shownFen = useMemo(() => {
    if (tab === 'pgn' && game && selected) return game.nodes[selected]?.fen ?? rootFen;
    return line.length ? line[line.length - 1].fen : rootFen;
  }, [tab, game, selected, line, rootFen]);

  const lastMove = useMemo(() => {
    const uci = tab === 'pgn' && game && selected ? game.nodes[selected]?.uci : line[line.length - 1]?.uci;
    return uci ? { from: uci.slice(0, 2), to: uci.slice(2, 4) } : null;
  }, [tab, game, selected, line]);

  async function loadFen(fen: string) {
    setError(null);
    try {
      const v = await api.validateFen(fen);
      setValidation(v);
      if (v.valid && v.normalized_fen) {
        setRootFen(v.normalized_fen);
        setLine([]);
      }
    } catch (err) {
      setError(message(err));
    }
  }

  async function playMove(move: string) {
    if (tab !== 'fen') return;
    setError(null);
    try {
      const played = await api.playMove(shownFen, move);
      setLine((l) => [...l, { uci: played.uci, san: played.san, fen: played.fen_after }]);
    } catch (err) {
      setError(message(err));
    }
  }

  async function importPgn() {
    setError(null);
    try {
      const result = await api.importPgn(pgnText);
      setGame(result.games[0]);
      setSelected(result.games[0].root_id);
    } catch (err) {
      setError(message(err));
    }
  }

  return (
    <main className="app">
      <header>
        <h1>Chess Calculation Trainer — spike Lot 0</h1>
        <p className="meta">
          {meta?.engine ? `${meta.engine.name} · ${meta.engine.threads} thread(s) · ${meta.engine.hash_mb} Mo` : 'moteur indisponible'}
        </p>
      </header>
      <nav role="tablist">
        {(['fen', 'pgn', 'editor'] as Tab[]).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} type="button" onClick={() => setTab(t)}>
            {{ fen: 'FEN', pgn: 'PGN', editor: 'Editeur' }[t]}
          </button>
        ))}
      </nav>
      {error && <p role="alert" className="error">{error}</p>}

      {tab === 'editor' ? (
        <PositionEditor initialFen={rootFen} onSubmit={(fen) => { setTab('fen'); setFenInput(fen); void loadFen(fen); }} />
      ) : (
        <div className="workspace">
          <ChessboardAdapter fen={shownFen} mode={tab === 'fen' ? 'play' : 'locked'} lastMove={lastMove} onMove={playMove} />
          <section className="side">
            {tab === 'fen' && (
              <>
                <label>
                  FEN <input value={fenInput} onChange={(e) => setFenInput(e.target.value)} size={60} />
                </label>
                <button type="button" onClick={() => loadFen(fenInput)}>Charger</button>
                {validation && !validation.valid && (
                  <ul className="error">{validation.errors.map((e) => <li key={e.code}>{e.message}</li>)}</ul>
                )}
                {validation?.valid && (
                  <p>
                    Trait : {validation.turn === 'white' ? 'Blancs' : 'Noirs'} · {validation.legal_moves_count} coups legaux
                    {validation.outcome && ` · position terminale (${validation.outcome})`}
                  </p>
                )}
                {validation?.warnings.map((w) => <p key={w} className="warning">{w}</p>)}
                <p>Ligne jouee : {line.map((m) => m.san).join(' ') || '—'}</p>
                <button type="button" onClick={() => setLine((l) => l.slice(0, -1))} disabled={!line.length}>Annuler le dernier coup</button>
              </>
            )}
            {tab === 'pgn' && (
              <>
                <textarea value={pgnText} onChange={(e) => setPgnText(e.target.value)} rows={6} cols={60} aria-label="PGN" />
                <button type="button" onClick={importPgn}>Importer</button>
                {game && (
                  <>
                    {game.warnings.map((w) => <p key={w} className="warning">{w}</p>)}
                    <div role="radiogroup" aria-label="Vue de l'arbre">
                      <label><input type="radio" checked={treeView === 'inline'} onChange={() => setTreeView('inline')} /> PGN en ligne</label>
                      <label><input type="radio" checked={treeView === 'arborist'} onChange={() => setTreeView('arborist')} /> Arbre</label>
                    </div>
                    {treeView === 'inline' ? (
                      <MoveText nodes={game.nodes} rootId={game.root_id} selectedNodeId={selected} onSelect={setSelected} />
                    ) : (
                      <VariationTree rows={toTreeRows(game.nodes, game.root_id)} selectedNodeId={selected} onSelect={setSelected} />
                    )}
                  </>
                )}
              </>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
