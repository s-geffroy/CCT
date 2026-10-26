import type { Position } from '../../api/client';

const SOURCE_LABEL = { fen: 'FEN', pgn: 'partie', editor: 'editeur' } as const;

type Props = {
  positions: Position[];
  selectedId: string | null;
  onSelect: (position: Position) => void;
};

export function RecentPositions({ positions, selectedId, onSelect }: Props) {
  return (
    <section className="recent" aria-label="Positions enregistrees">
      <h2>Positions enregistrees</h2>
      {positions.length === 0 ? (
        <p className="empty">Aucune position enregistree.</p>
      ) : (
        <ul>
          {positions.map((p) => (
            <li key={p.id}>
              <button type="button" data-position-id={p.id} aria-current={p.id === selectedId} onClick={() => onSelect(p)}>
                <code>{p.fen.split(' ').slice(0, 2).join(' ')}</code>{' '}
                <span className="source">{SOURCE_LABEL[p.source_type]}</span>{' '}
                <time dateTime={p.created_at}>{new Date(p.created_at).toLocaleString('fr-FR')}</time>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
