// Etat du moteur, verifie periodiquement : sans moteur, les seances B/C
// restent possibles, seule l'analyse est suspendue (doc 13, Lot 2).
import { useEffect, useState } from 'react';
import { settingsApi } from '../api/client';

const POLL_MS = 30_000;

export function EngineBanner() {
  const [engineOk, setEngineOk] = useState<boolean | null>(null);
  useEffect(() => {
    let stop = false;
    const check = () => settingsApi.ready().then((c) => { if (!stop) setEngineOk(c ? c.engine : false); });
    void check();
    const id = setInterval(check, POLL_MS);
    return () => { stop = true; clearInterval(id); };
  }, []);
  if (engineOk !== false) return null;
  return (
    <p role="status" className="mb-3 rounded-md border border-warning px-3 py-2 text-sm" data-testid="engine-banner">
      Moteur indisponible : les seances de calcul (B, C) restent possibles et seront analysees plus tard ;
      l'etude libre et la reference sont suspendues.{' '}
      <a href="#/settings">Installer ou choisir un moteur</a>
    </p>
  );
}
