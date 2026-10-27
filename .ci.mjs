const h = { 'User-Agent': 'cct' };
const runs = (await (await fetch('https://api.github.com/repos/s-geffroy/CCT/actions/runs?per_page=3', { headers: h })).json()).workflow_runs;
for (const r of runs) {
  console.log(r.id, r.name, r.event, r.head_sha.slice(0, 7), r.status, r.conclusion ?? '', r.created_at);
  const jobs = (await (await fetch(r.jobs_url, { headers: h })).json()).jobs ?? [];
  for (const j of jobs) {
    console.log('   ', j.name, '|', j.status, j.conclusion ?? '');
    for (const s of j.steps ?? []) if (s.conclusion === 'failure' || s.status === 'in_progress') console.log('       ->', s.name, s.status, s.conclusion ?? '');
  }
}
