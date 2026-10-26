// Module « Positions » (Lot 1) : FEN, partie PGN a variantes ou editeur ->
// position retenue, enregistree avec son contexte (historique) cote serveur.
// Aucune donnee moteur n'est affichee ici.
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  api,
  ApiFailure,
  type CreatedPosition,
  type FenValidation,
  type Game,
  type Meta,
  type PgnNode,
  type Position,
  type PositionSource,
} from './api/client';
import { ChessboardAdapter } from './adapters/ChessboardAdapter';
import { toTreeRows } from './adapters/variationTree';
import { MoveText } from './components/MoveText';
import { VariationTree } from './components/VariationTree';
import { PositionEditor } from './features/PositionEditor';
import { RecentPositions } from './features/positions/RecentPositions';
import { RetainedPanel } from './features/positions/RetainedPanel';
import { StudyView } from './features/analysis/StudyView';
import { HistoryView } from './features/training/HistoryView';
import { TrainingView } from './features/training/TrainingView';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
type Tab = 'fen' | 'pgn' | 'editor' | 'retained';
type PlayedLine = { uci: string; san: string; fen: string }[];
type LoadedGame = { game: Game; nodes: Record<string, PgnNode> };

function message(err: unknown): string {
  return err instanceof ApiFailure ? `${err.error.message} (${err.error.code})` : 'Erreur inattendue.';
}

function gameLabel(g: Game): string {
  const h = g.headers;
  const players = [h.White, h.Black].filter((x) => x && x !== '?').join(' - ');
  return `${g.index + 1}. ${players || 'Partie'}${h.Event && h.Event !== '?' ? ` (${h.Event})` : ''}`;
}

function PositionsModule({ onTrain, onStudy }: {
  onTrain: (position: Position, mode: 'mental' | 'tree') => void;
  onStudy: (position: Position) => void;
}) {
  const [tab, setTab] = useState<Tab>('fen');
  const [error, setError] = useState<string | null>(null);

  // FEN
  const [fenInput, setFenInput] = useState(START);
  const [validation, setValidation] = useState<FenValidation | null>(null);
  const [fenRoot, setFenRoot] = useState(START);
  const [line, setLine] = useState<PlayedLine>([]);

  // PGN
  const [pgnText, setPgnText] = useState('');
  const [games, setGames] = useState<Game[]>([]);
  const [loaded, setLoaded] = useState<LoadedGame | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [treeView, setTreeView] = useState<'arborist' | 'inline'>('inline');

  // Positions enregistrees
  const [retained, setRetained] = useState<Position | CreatedPosition | null>(null);
  const [recent, setRecent] = useState<Position[]>([]);

  const refreshRecent = useCallback(() => {
    api.positions().then((page) => setRecent(page.items)).catch(() => setRecent([]));
  }, []);

  useEffect(() => {
    refreshRecent();
  }, [refreshRecent]);

  const displayedFen = useMemo(() => {
    if (tab === 'pgn' && loaded && selectedNode) return loaded.nodes[selectedNode]?.fen ?? START;
    if (tab === 'retained' && retained) return retained.fen;
    return line.length ? line[line.length - 1].fen : fenRoot;
  }, [tab, loaded, selectedNode, retained, line, fenRoot]);

  const lastMove = useMemo(() => {
    let uci: string | null | undefined = null;
    if (tab === 'pgn' && loaded && selectedNode) uci = loaded.nodes[selectedNode]?.uci;
    else if (tab === 'fen') uci = line[line.length - 1]?.uci;
    else if (tab === 'retained' && retained?.history_uci?.length) uci = retained.history_uci[retained.history_uci.length - 1];
    return uci ? { from: uci.slice(0, 2), to: uci.slice(2, 4) } : null;
  }, [tab, loaded, selectedNode, line, retained]);

  async function run(action: () => Promise<void>): Promise<boolean> {
    setError(null);
    try {
      await action();
      return true;
    } catch (err) {
      setError(message(err));
      return false;
    }
  }

  const loadFen = (fen: string) =>
    run(async () => {
      const v = await api.validateFen(fen);
      setValidation(v);
      if (v.valid && v.normalized_fen) {
        setFenRoot(v.normalized_fen);
        setLine([]);
      }
    });

  const playMove = (move: string) =>
    run(async () => {
      const played = await api.playMove(displayedFen, move);
      setLine((l) => [...l, { uci: played.uci, san: played.san, fen: played.fen_after }]);
    });

  const loadGame = (game: Game) =>
    run(async () => {
      const page = await api.tree(game.id);
      setLoaded({ game, nodes: page.nodes });
      setSelectedNode(game.root_node_id);
    });

  const importPgn = () =>
    run(async () => {
      const result = await api.importPgn(pgnText);
      setGames(result.games);
      await loadGame(result.games[0]);
    });

  const loadMore = (nodeId: string) =>
    run(async () => {
      if (!loaded) return;
      const page = await api.tree(loaded.game.id, nodeId);
      setLoaded({ game: loaded.game, nodes: { ...loaded.nodes, ...page.nodes } });
    });

  const retain = (source: PositionSource) =>
    run(async () => {
      const position = await api.createPosition(source);
      setRetained(position);
      refreshRecent();
    });

  function retainCurrent() {
    if (tab === 'pgn' && loaded && selectedNode) {
      void retain({ source: 'pgn', game_id: loaded.game.id, node_id: selectedNode });
    } else if (tab === 'fen') {
      void retain({ source: 'fen', fen: fenRoot, history_uci: line.map((m) => m.uci) });
    }
  }

  return (
    <>
      <nav role="tablist" aria-label="Source de la position">
        {(['fen', 'pgn', 'editor'] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} type="button" onClick={() => setTab(t)}>
            {{ fen: 'FEN', pgn: 'PGN', editor: 'Editeur' }[t]}
          </button>
        ))}
      </nav>
      {error && <p role="alert" className="error">{error}</p>}

      {tab === 'editor' ? (
        <PositionEditor
          initialFen={displayedFen}
          onSubmit={async (fen) => {
            // On ne quitte l'editeur que si le serveur accepte la position.
            if (await retain({ source: 'editor', fen })) setTab('retained');
          }}
        />
      ) : (
        <div className="workspace">
          <ChessboardAdapter fen={displayedFen} mode={tab === 'fen' ? 'play' : 'locked'} lastMove={lastMove} onMove={playMove} />
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
                <p>Coups joues depuis cette FEN : {line.map((m) => m.san).join(' ') || '—'}</p>
                <button type="button" onClick={() => setLine((l) => l.slice(0, -1))} disabled={!line.length}>Annuler le dernier coup</button>
              </>
            )}
            {tab === 'pgn' && (
              <>
                <textarea value={pgnText} onChange={(e) => setPgnText(e.target.value)} rows={6} cols={60} aria-label="PGN" />
                <button type="button" onClick={importPgn}>Importer</button>
                {games.length > 1 && (
                  <label>
                    Partie{' '}
                    <select
                      aria-label="Partie"
                      value={loaded?.game.id ?? ''}
                      onChange={(e) => {
                        const g = games.find((x) => x.id === e.target.value);
                        if (g) void loadGame(g);
                      }}
                    >
                      {games.map((g) => <option key={g.id} value={g.id}>{gameLabel(g)}</option>)}
                    </select>
                  </label>
                )}
                {loaded && (
                  <>
                    {loaded.game.warnings.map((w) => <p key={w} className="warning">{w}</p>)}
                    <div role="radiogroup" aria-label="Vue de l'arbre">
                      <label><input type="radio" checked={treeView === 'inline'} onChange={() => setTreeView('inline')} /> PGN en ligne</label>
                      <label><input type="radio" checked={treeView === 'arborist'} onChange={() => setTreeView('arborist')} /> Arbre</label>
                    </div>
                    {treeView === 'inline' ? (
                      <MoveText nodes={loaded.nodes} rootId={loaded.game.root_node_id} selectedNodeId={selectedNode}
                        onSelect={setSelectedNode} onLoadMore={loadMore} />
                    ) : (
                      <VariationTree rows={toTreeRows(loaded.nodes, loaded.game.root_node_id)} selectedNodeId={selectedNode}
                        onSelect={setSelectedNode} onLoadMore={loadMore} />
                    )}
                    <button type="button" onClick={() => setSelectedNode(loaded.game.root_node_id)}>Position de depart</button>
                  </>
                )}
              </>
            )}
            {(tab === 'fen' || (tab === 'pgn' && loaded)) && (
              <button type="button" className="primary" onClick={retainCurrent}>Retenir cette position</button>
            )}
          </section>
        </div>
      )}

      <div className="library">
        <RetainedPanel position={retained} displayedFen={displayedFen} onShow={() => setTab('retained')} onTrain={onTrain} onStudy={onStudy} />
        <RecentPositions
          positions={recent}
          selectedId={retained?.id ?? null}
          onSelect={(p) => {
            setRetained(p);
            setTab('retained');
          }}
        />
      </div>
    </>
  );
}

type Route = { view: 'positions' } | { view: 'history' } | { view: 'session'; id: string } | { view: 'study'; id: string };

function parseRoute(hash: string): Route {
  const m = /^#\/session\/([0-9a-f-]{36})$/.exec(hash);
  if (m) return { view: 'session', id: m[1] };
  const study = /^#\/study\/([0-9a-f-]{36})$/.exec(hash);
  if (study) return { view: 'study', id: study[1] };
  if (hash === '#/history') return { view: 'history' };
  return { view: 'positions' };
}

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.meta().then(setMeta).catch(() => setMeta(null));
    const onHash = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const go = (hash: string) => {
    window.location.hash = hash;
  };

  async function train(position: Position, mode: 'mental' | 'tree') {
    setError(null);
    try {
      const session = await api.createSession(position.id, mode);
      go(`#/session/${session.id}`);
    } catch (err) {
      setError(message(err));
    }
  }

  return (
    <main className="app">
      <header>
        <h1>Chess Calculation Trainer</h1>
        <p className="meta">
          {meta?.engine ? `${meta.engine.name} · ${meta.engine.threads} thread(s) · ${meta.engine.hash_mb} Mo` : 'moteur indisponible'}
        </p>
        <nav aria-label="Modules" className="modules">
          <a href="#/positions" aria-current={route.view === 'positions' ? 'page' : undefined}>Positions</a>
          {route.view === 'session' && <a href={`#/session/${route.id}`} aria-current="page">Seance</a>}
          {route.view === 'study' && <a href={`#/study/${route.id}`} aria-current="page">Etude</a>}
          <a href="#/history" aria-current={route.view === 'history' ? 'page' : undefined}>Historique</a>
        </nav>
      </header>
      {error && <p role="alert" className="error">{error}</p>}
      {route.view === 'positions' && <PositionsModule onTrain={train} onStudy={(p) => go(`#/study/${p.id}`)} />}
      {route.view === 'history' && <HistoryView onOpen={(id) => go(`#/session/${id}`)} />}
      {route.view === 'session' && <TrainingView key={route.id} sessionId={route.id} onExit={() => go('#/positions')} />}
      {route.view === 'study' && <StudyView key={route.id} positionId={route.id} />}
    </main>
  );
}
