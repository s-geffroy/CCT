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
};
