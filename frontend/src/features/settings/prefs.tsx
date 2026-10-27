// Reglages partages par toute l'interface : valeurs par defaut des analyses et
// point de vue des evaluations. Charges une fois, rafraichis apres modification.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { settingsApi, type EngineScore, type SettingsValues, type SettingsView } from '../../api/client';
import { formatScore } from '../analysis/format';

export const DEFAULT_VALUES: SettingsValues = {
  engine_threads: 2, engine_hash_mb: 128, study_depth: 21, study_multipv: 20, study_budget_s: 300,
  reference_depth: 21, reference_budget_s: 300, tree_budget_s: 300, tree_max_nodes: 80, tree_node_depth: 21,
  tree_node_budget_s: 30, tree_auto_max_ply: 4, score_perspective: 'white',
};

type Prefs = { view: SettingsView | null; values: SettingsValues; setView: (v: SettingsView) => void; reload: () => void };

const PrefsContext = createContext<Prefs>({ view: null, values: DEFAULT_VALUES, setView: () => {}, reload: () => {} });

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [view, setView] = useState<SettingsView | null>(null);
  const reload = useCallback(() => { settingsApi.get().then(setView).catch(() => {}); }, []);
  useEffect(reload, [reload]);
  const value = useMemo(() => ({ view, values: view?.values ?? DEFAULT_VALUES, setView, reload }), [view, reload]);
  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>;
}

export function usePrefs(): Prefs {
  return useContext(PrefsContext);
}

/** Score au point de vue choisi. Le serveur donne toujours le point de vue des
 *  Blancs ; « camp au trait » s'entend dans la position `fen` analysee. */
export function toPerspective(score: EngineScore, fen: string, perspective: SettingsValues['score_perspective']): EngineScore {
  if (perspective === 'white' || fen.split(' ')[1] !== 'b' || score.value === null || score.kind === 'draw') return score;
  if (score.kind === 'mate' && score.value === 0) return score;
  const bound = score.bound === 'lower' ? 'upper' : score.bound === 'upper' ? 'lower' : null;
  return { ...score, value: -score.value, bound };
}

export function useScore() {
  const { values } = usePrefs();
  const perspective = values.score_perspective;
  return useMemo(() => ({
    perspective,
    format: (score: EngineScore, fen: string) => formatScore(toPerspective(score, fen, perspective)),
    /** Libelle de colonne et legende, toujours visibles. */
    label: perspective === 'white' ? 'Eval. (Blancs)' : 'Eval. (camp au trait)',
    legend: perspective === 'white'
      ? 'Evaluations au point de vue des Blancs : positif = avantage blanc ; M+n : mat pour les Blancs.'
      : 'Evaluations au point de vue du camp au trait dans la position analysee : positif = avantage pour lui ; M+n : il mate.',
  }), [perspective]);
}
