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
  uci: string | null;
  san: string | null;
  fen: string;
  comment: string;
  starting_comment: string;
  nags: number[];
  children: string[];
};

export type PgnGame = {
  index: number;
  headers: Record<string, string>;
  root_id: string;
  nodes: Record<string, PgnNode>;
  warnings: string[];
  history_known: boolean;
};

export type PlayedMove = { uci: string; san: string; fen_after: string; outcome: string | null };

export type Meta = {
  app_version: string;
  engine: { name: string; threads: number; hash_mb: number; build: Record<string, string> } | null;
};

export const api = {
  meta: () => request<Meta>('/api/v1/meta'),
  validateFen: (fen: string) => post<FenValidation>('/api/v1/positions/validate', { fen }),
  importPgn: (pgn: string) => post<{ games: PgnGame[]; truncated: boolean }>('/api/v1/games/import-pgn', { pgn }),
  playMove: (fen: string, move: string) => post<PlayedMove>('/api/v1/moves/play', { fen, move }),
};
