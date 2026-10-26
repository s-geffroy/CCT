// Client REST minimal. Le serveur arbitre toute legalite ; le client affiche.

export type ApiError = { code: string; message: string; details: Record<string, unknown> };

export class ApiFailure extends Error {
  constructor(public readonly status: number, public readonly error: ApiError) {
    super(error.message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const error: ApiError = body?.error ?? { code: 'HTTP_' + res.status, message: 'Erreur reseau.', details: {} };
    throw new ApiFailure(res.status, error);
  }
  return body as T;
}

const post = <T>(path: string, payload: unknown) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(payload) });

export type FenValidation = {
  valid: boolean;
  normalized_fen: string | null;
  turn: 'white' | 'black' | null;
  legal_moves_count: number | null;
  outcome: string | null;
  errors: { code: string; message: string }[];
  warnings: string[];
};

export type PgnNode = {
  id: string;
  parent_id: string | null;
  ply: number;
  move_number: number | null;
  color: 'white' | 'black' | null;
  uci: string | null;
  san: string | null;
  fen: string;
  comment: string;
  starting_comment: string;
  nags: number[];
  children: string[];
};

export type Game = {
  id: string;
  import_id: string;
  index: number;
  headers: Record<string, string>;
  warnings: string[];
  history_known: boolean;
  root_node_id: string;
  nodes_count: number;
  imported_at: string;
};

export type TreePage = {
  game_id: string;
  root_id: string;
  nodes: Record<string, PgnNode>;
  truncated: boolean;
  frontier: string[];
};

export type Position = {
  id: string;
  fen: string;
  initial_fen: string;
  history_uci: string[] | null;
  history_san: string[] | null;
  history_complete: boolean;
  source_type: 'fen' | 'pgn' | 'editor';
  source_game_id: string | null;
  source_node_id: string | null;
  turn: 'white' | 'black';
  legal_moves_count: number;
  outcome: string | null;
  claimable_draw: string | null;
  created_at: string;
};

export type CreatedPosition = Position & { created: boolean; warnings: string[] };

export type PositionSource =
  | { source: 'fen'; fen: string; history_uci?: string[] }
  | { source: 'editor'; fen: string }
  | { source: 'pgn'; game_id: string; node_id: string };

export type PlayedMove = { uci: string; san: string; fen_after: string; outcome: string | null };

export type Meta = {
  app_version: string;
  schema_version: number;
  engine: { name: string; threads: number; hash_mb: number; build: Record<string, string> } | null;
};

type Page<T> = { items: T[]; limit: number; offset: number };

export type Assessment = 'white_better' | 'black_better' | 'equal' | 'initiative' | 'attack' | 'unclear';

export type UserNode = {
  id: string;
  parent_id: string | null;
  order_index: number;
  move_uci: string;
  move_san: string;
  fen_after: string;
  comment: string;
  human_assessment: Assessment | null;
  created_at: string;
};

export type WrittenLine = {
  text: string;
  moves_uci: string[];
  moves_san: string[];
  error: { ply: number; token: string; code: string; message: string } | null;
};

export type SelfAssessment = { candidates: string; main_threat: string; evaluation: Assessment | null };

export type Attempt = {
  submitted_at: string;
  mode: 'mental' | 'tree';
  root_fen: string;
  notes: string;
  self_assessment: SelfAssessment | null;
  tree: Record<string, UserNode>;
  written_lines?: WrittenLine[];
  no_trace: boolean;
};

export type Session = {
  id: string;
  mode: 'mental' | 'tree';
  state: 'active' | 'submitted' | 'revealed' | 'reviewed' | 'abandoned';
  revision: number;
  started_at: string;
  submitted_at: string | null;
  revealed_at: string | null;
  abandoned_at: string | null;
  duration_ms: number | null;
  allow_text_notes: boolean;
  notes: string;
  lines_text: string;
  self_assessment: SelfAssessment | null;
  position: Position;
  tree: { nodes: Record<string, UserNode> };
  can_undo: boolean;
  can_redo: boolean;
  attempt: Attempt | null;
  preparation?: { job_id: string; progress_category: string; is_ready: boolean };
  reference?: { status: 'available'; job: AnalysisJob } | { status: 'not_available'; message: string };
};

export type EngineScore = { kind: 'cp' | 'mate' | 'unknown'; value: number | null; perspective: 'white'; bound: 'lower' | 'upper' | null };

export type AnalysisLine = {
  rank: number;
  root_move_uci: string;
  root_move_san: string | null;
  pv_uci: string[];
  pv_san: string[];
  depth: number;
  exact_depth: number;
  seldepth: number | null;
  score: EngineScore;
  status: 'provisional' | 'depth_met' | 'budget_exhausted' | 'cancelled' | 'incomplete';
};

export type JobState = 'queued' | 'running' | 'complete_depth' | 'budget_exhausted' | 'incomplete' | 'cancelled' | 'failed' | 'interrupted' | 'terminal';

export type VisibleJob = {
  id: string;
  position_id: string;
  visibility: 'full';
  purpose: 'study' | 'initial_reference';
  state: JobState;
  revision: number;
  settings: { target_depth: number; multipv_max: number; budget_s: number };
  stages_reached_s: Record<string, number>;
  target_depth_met: boolean;
  legal_moves: number | null;
  multipv: number | null;
  root_coverage: 'all_root_moves' | 'top_moves_only' | null;
  elapsed_s: number | null;
  nps: number | null;
  error: string | null;
  cancel_requested: boolean;
  lines: AnalysisLine[];
  reused?: boolean;
};

export type HiddenJob = { id: string; visibility: 'hidden'; progress_category: string; is_ready: boolean };
export type AnalysisJob = VisibleJob | HiddenJob;

export const FINAL_JOB_STATES: JobState[] = ['complete_depth', 'budget_exhausted', 'incomplete', 'cancelled', 'failed', 'interrupted', 'terminal'];

export type HistoryItem = {
  id: string;
  mode: 'mental' | 'tree';
  state: Session['state'];
  started_at: string;
  submitted_at: string | null;
  revealed_at: string | null;
  duration_ms: number | null;
  position_id: string;
  fen: string;
};

const send = <T>(method: string, path: string, payload?: unknown) =>
  request<T>(path, { method, body: payload === undefined ? undefined : JSON.stringify(payload) });

export const api = {
  meta: () => request<Meta>('/api/v1/meta'),
  validateFen: (fen: string) => post<FenValidation>('/api/v1/positions/validate', { fen }),
  playMove: (fen: string, move: string) => post<PlayedMove>('/api/v1/moves/play', { fen, move }),
  importPgn: (pgn: string) => post<{ import_id: string; games: Game[]; truncated: boolean }>('/api/v1/games/import-pgn', { pgn }),
  tree: (gameId: string, root?: string) =>
    request<TreePage>(`/api/v1/games/${gameId}/tree` + (root ? `?root=${encodeURIComponent(root)}` : '')),
  createPosition: (source: PositionSource) => post<CreatedPosition>('/api/v1/positions', source),
  position: (id: string) => request<Position>(`/api/v1/positions/${id}`),
  positions: (limit = 20) => request<Page<Position>>(`/api/v1/positions?limit=${limit}`),

  createSession: (position_id: string, mode: Session['mode'], allow_text_notes = true) =>
    post<Session>('/api/v1/sessions', { position_id, mode, allow_text_notes }),
  session: (id: string) => request<Session>(`/api/v1/sessions/${id}`),
  addNode: (s: Session, parent: string | null, move: string) =>
    post<{ node: UserNode; session: Session }>(`/api/v1/sessions/${s.id}/nodes`, {
      parent_node_id: parent, move, expected_revision: s.revision,
    }),
  patchNode: (s: Session, nodeId: string, patch: { comment?: string; human_assessment?: Assessment; clear_assessment?: boolean; promote?: boolean }) =>
    send<Session>('PATCH', `/api/v1/sessions/${s.id}/nodes/${nodeId}`, { expected_revision: s.revision, ...patch }),
  deleteNode: (s: Session, nodeId: string) =>
    send<Session>('DELETE', `/api/v1/sessions/${s.id}/nodes/${nodeId}?expected_revision=${s.revision}`),
  undo: (s: Session) => post<Session>(`/api/v1/sessions/${s.id}/undo`, { expected_revision: s.revision }),
  redo: (s: Session) => post<Session>(`/api/v1/sessions/${s.id}/redo`, { expected_revision: s.revision }),
  saveNotes: (s: Session, notes: { notes?: string; lines_text?: string }) =>
    send<Session>('PUT', `/api/v1/sessions/${s.id}/notes`, { expected_revision: s.revision, ...notes }),
  submit: (s: Session, self_assessment: SelfAssessment | null) =>
    post<Session>(`/api/v1/sessions/${s.id}/submit`, { expected_revision: s.revision, self_assessment }),
  reveal: (s: Session) => post<Session>(`/api/v1/sessions/${s.id}/reveal`, { expected_revision: s.revision }),
  abandon: (s: Session) => post<Session>(`/api/v1/sessions/${s.id}/abandon`, { expected_revision: s.revision }),
  createJob: (position_id: string, settings: { target_depth: number; multipv_max: number; budget_s: number }) =>
    post<AnalysisJob>('/api/v1/analysis-jobs', { position_id, ...settings }),
  job: (id: string) => request<AnalysisJob>(`/api/v1/analysis-jobs/${id}`),
  jobs: (positionId: string) => request<{ items: AnalysisJob[] }>(`/api/v1/analysis-jobs?position_id=${positionId}`),
  cancelJob: (id: string) => post<AnalysisJob>(`/api/v1/analysis-jobs/${id}/cancel`, {}),
  history: (limit = 50) => request<Page<HistoryItem>>(`/api/v1/history?limit=${limit}`),
};
