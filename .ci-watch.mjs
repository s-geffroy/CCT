// Suit l'execution de la CI pour un commit jusqu'a sa fin (API publique, sans jeton).
const sha = process.argv[2];
const h = { 'User-Agent': 'cct' };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
for (let i = 0; i < 25; i++) {
  const runs = (await (await fetch(`https://api.github.com/repos/s-geffroy/CCT/actions/runs?head_sha=${sha}`, { headers: h })).json()).workflow_runs ?? [];
  const run = runs[0];
  if (run && run.status === 'completed') {
    console.log('RUN', run.id, run.conclusion, run.html_url);
    const jobs = (await (await fetch(run.jobs_url, { headers: h })).json()).jobs ?? [];
    for (const j of jobs) {
      console.log('JOB', j.name, j.conclusion, j.id);
      for (const s of j.steps ?? []) if (s.conclusion !== 'success' && s.conclusion !== 'skipped') console.log('   STEP', s.name, s.conclusion);
    }
    const ann = await (await fetch(`https://api.github.com/repos/s-geffroy/CCT/check-runs/${jobs.find((j) => j.conclusion === 'failure')?.id ?? 0}/annotations`, { headers: h })).json().catch(() => []);
    if (Array.isArray(ann)) for (const a of ann) console.log('ANN', a.annotation_level, a.path, a.start_line, a.message.slice(0, 400));
    process.exit(0);
  }
  await sleep(180000);
}
console.log('TIMEOUT');
