import { useEffect, useState } from 'react';
import { api, type HistoryItem } from '../../api/client';

const MODE = { mental: 'calcul mental (B)', tree: 'arbre personnel (C)' } as const;
const STATE = { active: 'en cours', submitted: 'soumise', revealed: 'revelee', reviewed: 'debriefee', abandoned: 'abandonnee' } as const;

export function HistoryView({ onOpen }: { onOpen: (id: string) => void }) {
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  useEffect(() => {
    api.history().then((p) => setItems(p.items)).catch(() => setItems([]));
  }, []);
  if (items === null) return <p>Chargement…</p>;
  return (
    <section aria-label="Historique des seances">
      <h2>Historique</h2>
      {items.length === 0 ? (
        <p className="empty">Aucune seance.</p>
      ) : (
        <table className="history">
          <thead><tr><th>Debut</th><th>Mode</th><th>Etat</th><th>Duree</th><th>Position</th><th /></tr></thead>
          <tbody>
            {items.map((s) => (
              <tr key={s.id} data-session-id={s.id}>
                <td><time dateTime={s.started_at}>{new Date(s.started_at).toLocaleString('fr-FR')}</time></td>
                <td>{MODE[s.mode]}</td>
                <td>{STATE[s.state]}</td>
                <td>{s.duration_ms !== null ? `${Math.round(s.duration_ms / 1000)} s` : '—'}</td>
                <td><code>{s.fen.split(' ').slice(0, 2).join(' ')}</code></td>
                <td><button type="button" onClick={() => onOpen(s.id)}>{s.state === 'active' ? 'Reprendre' : 'Ouvrir'}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
