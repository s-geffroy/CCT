// Dependances npm embarquees dans l'interface (production, transitives).
// Lance dans devtools : node scripts/notices_npm.mjs (sortie markdown).
import { execSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
const tree = JSON.parse(execSync('npm ls --omit=dev --all --json', { cwd: '/work/frontend' }).toString());
const seen = new Map();
const walk = (deps = {}) => {
  for (const [name, info] of Object.entries(deps)) {
    if (!info.version || seen.has(`${name}@${info.version}`)) continue;
    let license = '?';
    try {
      const pkg = JSON.parse(readFileSync(`/work/frontend/node_modules/${name}/package.json`, 'utf8'));
      license = typeof pkg.license === 'string' ? pkg.license : pkg.license?.type ?? '?';
    } catch {}
    seen.set(`${name}@${info.version}`, `| ${name} | ${info.version} | ${license} |`);
    walk(info.dependencies);
  }
};
walk(tree.dependencies);
console.log([...seen.values()].sort().join('\n'));
