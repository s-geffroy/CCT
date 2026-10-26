// Flux SSE d'un travail d'analyse. EventSource se reconnecte seul ; le serveur
// renvoie l'etat complet a chaque connexion. Les evenements d'un autre travail
// sont ignores (jamais de lignes d'une ancienne position, T11).
import { useEffect, useState } from 'react';
import { FINAL_JOB_STATES, type AnalysisJob } from '../../api/client';

export function useJobStream(jobId: string | null, initial: AnalysisJob | null = null): AnalysisJob | null {
  const [job, setJob] = useState<AnalysisJob | null>(initial);

  useEffect(() => {
    setJob(initial && initial.id === jobId ? initial : null);
    if (!jobId) return;
    const source = new EventSource(`/api/v1/analysis-jobs/${jobId}/events`);
    const accept = (data: AnalysisJob) => {
      if (data.id !== jobId) return;
      setJob(data);
      if (data.visibility === 'full' && FINAL_JOB_STATES.includes(data.state)) source.close();
    };
    source.addEventListener('analysis-snapshot', (e) => accept(JSON.parse((e as MessageEvent).data)));
    source.addEventListener('analysis-status', (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      accept({ id: d.job_id, visibility: 'hidden', progress_category: d.progress_category, is_ready: d.is_ready });
    });
    return () => source.close();
  }, [jobId]);

  return job;
}
