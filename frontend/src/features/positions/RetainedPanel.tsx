// La position retenue (future racine d'exercice) et son contexte de regles,
// distincte de la position affichee : les deux reperes sont toujours visibles.
import type { CreatedPosition, Position } from '../../api/client';

const SOURCE_LABEL = { fen: 'FEN', pgn: 'partie PGN', editor: 'editeur' } as const;
const DRAW_LABEL: Record<string, string> = {
  threefold_repetition: 'nulle reclamable (triple repetition)',
  fifty_moves: 'nulle reclamable (50 coups)',
};
const OUTCOME_LABEL: Record<string, string> = {
  checkmate: 'echec et mat',
  stalemate: 'pat',
  insufficient_material: 'materiel insuffisant',
  seventyfive_moves: 'nulle (75 coups)',
  fivefold_repetition: 'nulle (quintuple repetition)',
};

export function formatHistory(position: Pick<Position, 'history_san' | 'initial_fen'>): string {
  if (!position.history_san || position.history_san.length === 0) return '';
  const [, turn, , , , fullmove] = position.initial_fen.split(' ');
  let number = Number(fullmove) || 1;
  let white = turn === 'w';
  const parts: string[] = [];
  position.history_san.forEach((san, i) => {
    if (white) parts.push(`${number}. ${san}`);
    else parts.push(i === 0 ? `${number}... ${san}` : san);
    if (!white) number++;
    white = !white;
  });
  return parts.join(' ');
}

function historyStatus(p: Position): string {
  if (p.history_uci === null) return 'historique inconnu (repetitions passees ignorees)';
  if (p.history_complete) return `historique complet depuis la position initiale (${p.history_uci.length} demi-coups)`;
  return `historique partiel : ${p.history_uci.length} demi-coups depuis une position donnee`;
}

type Props = {
  position: Position | CreatedPosition | null;
  displayedFen: string;
  onShow: () => void;
};

export function RetainedPanel({ position, displayedFen, onShow }: Props) {
  return (
    <section className="retained" aria-label="Position retenue" data-position-id={position?.id ?? ''}>
      <h2>Position retenue</h2>
      {!position ? (
        <p className="empty">Aucune. Choisissez une position (FEN, noeud d'une partie, editeur) puis « Retenir cette position ».</p>
      ) : (
        <>
          <dl>
            <dt>FEN</dt>
            <dd><code data-testid="retained-fen">{position.fen}</code></dd>
            <dt>Trait</dt>
            <dd>{position.turn === 'white' ? 'Blancs' : 'Noirs'} · {position.legal_moves_count} coups legaux</dd>
            <dt>Origine</dt>
            <dd>{SOURCE_LABEL[position.source_type]}</dd>
            <dt>Contexte</dt>
            <dd data-testid="retained-history-status">{historyStatus(position)}</dd>
            {position.history_san && position.history_san.length > 0 && (
              <>
                <dt>Coups</dt>
                <dd data-testid="retained-history">{formatHistory(position)}</dd>
              </>
            )}
            {position.outcome && (<><dt>Fin de partie</dt><dd>{OUTCOME_LABEL[position.outcome] ?? position.outcome}</dd></>)}
            {position.claimable_draw && (<><dt>Regles</dt><dd>{DRAW_LABEL[position.claimable_draw] ?? position.claimable_draw}</dd></>)}
          </dl>
          {'warnings' in position && position.warnings.map((w) => <p key={w} className="warning">{w}</p>)}
          {displayedFen !== position.fen && (
            <p className="note">La position affichee differe de la position retenue.</p>
          )}
          <button type="button" onClick={onShow}>Afficher la position retenue</button>
        </>
      )}
    </section>
  );
}
