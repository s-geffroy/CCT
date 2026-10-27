// Reglages bornes (doc 08). Les bornes viennent du serveur, qui valide aussi :
// l'interface ne fait que les afficher. Threads et hash s'appliquent apres la
// recherche en cours.
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { ApiFailure, settingsApi, type SettingField, type SettingsValues } from '../../api/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { usePrefs } from './prefs';

const GROUPS: Record<SettingField['group'], { title: string; help: string }> = {
  moteur: { title: 'Moteur', help: 'Pris en compte apres la recherche en cours. Plus de threads accelere le calcul mais ralentit le reste du PC.' },
  etude: { title: 'Etude libre (A)', help: 'Valeurs proposees au lancement d\'une analyse.' },
  seance: { title: 'Reference des seances', help: 'Analyse racine lancee au debut d\'une seance, masquee jusqu\'a la revelation.' },
  arbre: { title: 'Arbre de reference', help: 'Plafonds de l\'exploration automatique ; les branches du joueur ont une enveloppe identique et separee.' },
  affichage: { title: 'Affichage', help: '' },
};

const CHOICE_LABEL: Record<string, string> = { white: 'Blancs (par defaut)', side_to_move: 'Camp au trait' };

export function SettingsView() {
  const { view, setView } = usePrefs();
  const [draft, setDraft] = useState<Partial<Record<keyof SettingsValues, string>>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (view) setDraft(Object.fromEntries(Object.entries(view.values).map(([k, v]) => [k, String(v)])));
  }, [view]);

  if (!view) return <p>Chargement des reglages…</p>;
  const fields = view.fields;

  async function save(reset = false) {
    setSaving(true);
    setErrors({});
    const patch: Record<string, number | string> = {};
    if (!reset) {
      for (const f of fields) {
        const raw = draft[f.key as keyof SettingsValues] ?? '';
        const value = f.choices ? raw : Number(raw);
        if (value !== view!.values[f.key as keyof SettingsValues]) patch[f.key] = value;
      }
    }
    try {
      // Un champ a la fois en cas d'erreur : le serveur nomme le reglage fautif.
      setView(await settingsApi.put(reset ? { reset: true } : patch));
      toast.success(reset ? 'Reglages par defaut retablis.' : 'Reglages enregistres.');
    } catch (err) {
      if (err instanceof ApiFailure) {
        const key = String(err.error.details.key ?? '');
        setErrors(key ? { [key]: err.error.message } : {});
        toast.error(err.error.message);
      } else {
        toast.error('Erreur inattendue.');
      }
    } finally {
      setSaving(false);
    }
  }

  const engine = view.engine;
  return (
    <section aria-label="Reglages" className="max-w-3xl">
      <h2>Reglages</h2>
      <form noValidate onSubmit={(e) => { e.preventDefault(); void save(); }} className="flex flex-col gap-4">
        {(Object.keys(GROUPS) as SettingField['group'][]).map((group) => (
          <fieldset key={group} className="!block">
            <legend>{GROUPS[group].title}</legend>
            {GROUPS[group].help && <p className="text-sm text-muted-foreground mb-2">{GROUPS[group].help}</p>}
            <div className="grid gap-3 sm:grid-cols-2">
              {fields.filter((f) => f.group === group).map((f) => {
                const id = `setting-${f.key}`;
                const value = draft[f.key as keyof SettingsValues] ?? '';
                return (
                  <div key={f.key} className="grid gap-1">
                    <Label htmlFor={id}>{f.label}{f.unit ? ` (${f.unit})` : ''}</Label>
                    {f.choices ? (
                      <NativeSelect id={id} value={value} onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}>
                        {f.choices.map((c) => <NativeSelectOption key={c} value={c}>{CHOICE_LABEL[c] ?? c}</NativeSelectOption>)}
                      </NativeSelect>
                    ) : (
                      <Input id={id} type="number" inputMode="numeric" min={f.minimum} max={f.maximum} value={value}
                             aria-invalid={errors[f.key] ? true : undefined} aria-describedby={`${id}-help`}
                             onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })} />
                    )}
                    <span id={`${id}-help`} className="text-xs text-muted-foreground">
                      {f.choices ? '' : `de ${f.minimum} a ${f.maximum} · defaut ${f.default}`}
                    </span>
                    {errors[f.key] && <span role="alert" className="text-sm text-destructive">{errors[f.key]}</span>}
                  </div>
                );
              })}
            </div>
            {group === 'moteur' && (
              <p className="text-sm mt-2" data-testid="engine-applied">
                {engine.applied ? `Moteur actuel : ${engine.applied.threads} thread(s), ${engine.applied.hash_mb} Mo.` : 'Moteur indisponible.'}
                {engine.pending && ` En attente : ${engine.pending.threads} thread(s), ${engine.pending.hash_mb} Mo (apres la recherche en cours).`}
              </p>
            )}
          </fieldset>
        ))}
        <div className="actions">
          <Button type="submit" disabled={saving}>Enregistrer les reglages</Button>
          <Button type="button" variant="outline" disabled={saving} onClick={() => save(true)}>Retablir les valeurs par defaut</Button>
        </div>
      </form>
    </section>
  );
}
