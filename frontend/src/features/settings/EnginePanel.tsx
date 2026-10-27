// Moteur (Lot 7) : quel Stockfish est utilise, pourquoi d'autres ont ete
// ecartes, et telechargement de la release officielle si aucun ne convient.
// Le serveur verifie l'empreinte SHA-256 avant toute installation.
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { ApiFailure, engineApi, type EngineStatus } from '../../api/client';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';

const POLL_MS = 1_000;
const BUSY = new Set(['downloading', 'verifying', 'installing']);

const SOURCE: Record<string, string> = {
  reglage: 'chemin indique dans les reglages',
  environnement: 'variable STOCKFISH_PATH',
  path: 'PATH du systeme',
  emplacement: 'dossier d\'un logiciel d\'echecs',
  telecharge: 'telecharge par l\'application',
};

const STEP: Record<string, string> = {
  downloading: 'Telechargement',
  verifying: 'Verification de l\'empreinte',
  installing: 'Installation',
};

const mo = (bytes: number) => `${Math.round(bytes / 1_000_000)} Mo`;

export function EnginePanel({ onChange }: { onChange?: () => void }) {
  const [status, setStatus] = useState<EngineStatus | null>(null);
  const [working, setWorking] = useState(false);

  const refresh = useCallback(() => engineApi.get().then(setStatus).catch(() => undefined), []);
  useEffect(() => { void refresh(); }, [refresh]);

  const busy = status ? BUSY.has(status.download.status) : false;
  useEffect(() => {
    if (!busy) return;
    const id = setInterval(() => {
      void engineApi.get().then((s) => {
        setStatus(s);
        if (s.download.status === 'done') { toast.success('Stockfish installe et verifie.'); onChange?.(); }
        if (s.download.status === 'failed') toast.error(s.download.error ?? 'Telechargement impossible.');
      }).catch(() => undefined);
    }, POLL_MS);
    return () => clearInterval(id);
  }, [busy, onChange]);

  async function act(action: () => Promise<EngineStatus>) {
    setWorking(true);
    try {
      setStatus(await action());
      onChange?.();
    } catch (err) {
      toast.error(err instanceof ApiFailure ? err.error.message : 'Erreur inattendue.');
    } finally {
      setWorking(false);
    }
  }

  if (!status) return <p>Recherche du moteur…</p>;
  const { current, download, offer } = status;
  const percent = download.total ? Math.min(100, Math.round((download.received / download.total) * 100)) : 0;

  return (
    <section aria-label="Moteur Stockfish" className="mb-6 rounded-md border px-4 py-3" data-testid="engine-panel">
      <h3 className="mb-2">Moteur Stockfish</h3>
      {current ? (
        <p data-testid="engine-current">
          <strong>{current.name}</strong> · {SOURCE[current.source] ?? current.source}
          <br /><span className="text-xs text-muted-foreground break-all">{current.path}</span>
        </p>
      ) : (
        <p data-testid="engine-absent">
          Aucun Stockfish utilisable. Les seances de calcul (B, C) restent possibles ; l'analyse attend un moteur.
        </p>
      )}

      {status.rejected.length > 0 && (
        <details className="mt-2 text-sm">
          <summary>{status.rejected.length} moteur(s) ecarte(s)</summary>
          <ul className="mt-1 list-disc pl-5">
            {status.rejected.map((r) => (
              <li key={`${r.source}:${r.path}`}><span className="break-all">{r.path}</span> ({SOURCE[r.source] ?? r.source}) : {r.reason}</li>
            ))}
          </ul>
        </details>
      )}

      {busy && (
        <div className="mt-3 grid gap-1" role="status" aria-live="polite">
          <span className="text-sm">{STEP[download.status]}{download.status === 'downloading' && download.total
            ? ` : ${mo(download.received)} / ${mo(download.total)}` : '…'}</span>
          <Progress value={download.status === 'downloading' ? percent : 100} aria-label="Progression du telechargement" />
        </div>
      )}
      {download.status === 'failed' && download.error && (
        <p role="alert" className="mt-2 text-sm text-destructive">{download.error}</p>
      )}

      <div className="actions mt-3">
        {!current && offer && (
          <Button type="button" disabled={busy || working} onClick={() => act(engineApi.download)} data-testid="engine-download">
            Telecharger Stockfish ({offer.release.replace('sf_', '')}, {mo(offer.size)})
          </Button>
        )}
        <Button type="button" variant="outline" disabled={busy || working} onClick={() => act(engineApi.rescan)}>
          Rechercher a nouveau
        </Button>
      </div>
      {!current && offer && (
        <p className="mt-2 text-xs text-muted-foreground">
          Source : release officielle Stockfish sur GitHub (licence GPL v3), empreinte SHA-256 verifiee avant installation.
        </p>
      )}
    </section>
  );
}
