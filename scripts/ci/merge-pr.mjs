// Fusionne une PR vers main SEULEMENT si tout est vert. Utilise par Claude Code
// (regle de permission limitee a ce script, cf. .claude/settings.local.json).
// Usage (conteneur devtools) : node scripts/ci/merge-pr.mjs <numero> <sha-complet-attendu>
// Refuse et explique si : PR fermee ou hors main, dernier commit different de
// celui annonce (push de derniere seconde), PR non fusionnable, ou l'un des
// checks obligatoires absent ou non vert sur ce commit.
import { readFileSync } from 'node:fs';

const REPO = 's-geffroy/CCT';
const REQUIRED_CHECKS = [
  'tests (pytest, vitest, image finale, Playwright)',
  'scripts Windows (PSScriptAnalyzer, Pester, PowerShell 5.1)',
];
const [number, expectedSha] = process.argv.slice(2);
const refuse = (why) => { console.log(`REFUS : ${why}`); process.exit(1); };
if (!/^\d+$/.test(number ?? '') || !/^[0-9a-f]{40}$/.test(expectedSha ?? '')) refuse('usage : merge-pr.mjs <numero> <sha complet>');

const token = readFileSync('/run/secrets/github_pat', 'utf8').trim();
const headers = { 'User-Agent': 'cct', Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
const api = async (path, init = {}) => {
  const r = await fetch(`https://api.github.com/repos/${REPO}${path}`, { headers, ...init });
  return { status: r.status, body: await r.json().catch(() => ({})) };
};

let pr;
for (let i = 0; i < 10; i++) {  // `mergeable` est calcule en differe par GitHub
  pr = (await api(`/pulls/${number}`)).body;
  if (pr.mergeable !== null) break;
  await new Promise((r) => setTimeout(r, 3000));
}
if (pr.state !== 'open') refuse(`PR #${number} ${pr.state ?? 'introuvable'}`);
if (pr.base?.ref !== 'main') refuse(`la PR vise ${pr.base?.ref}, pas main`);
if (pr.head.sha !== expectedSha) refuse(`dernier commit ${pr.head.sha}, attendu ${expectedSha}`);
if (pr.mergeable !== true) refuse('PR non fusionnable (conflit ou etat inconnu)');

const runs = (await api(`/commits/${expectedSha}/check-runs?per_page=100`)).body.check_runs ?? [];
for (const name of REQUIRED_CHECKS) {
  const run = runs.filter((r) => r.name === name).sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at))[0];
  if (!run) refuse(`check absent : ${name}`);
  if (run.status !== 'completed' || run.conclusion !== 'success') refuse(`check non vert : ${name} (${run.status} ${run.conclusion ?? ''})`);
}

const merge = await api(`/pulls/${number}/merge`, {
  method: 'PUT',
  body: JSON.stringify({ merge_method: 'merge', sha: expectedSha, commit_title: `Fusion PR #${number} : ${pr.title}` }),
});
if (merge.status !== 200) refuse(`GitHub refuse la fusion (${merge.status}) : ${merge.body.message ?? ''}`);
console.log(`FUSIONNEE : PR #${number} -> main (${merge.body.sha})`);
