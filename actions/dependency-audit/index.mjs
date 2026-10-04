import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { appendFile, chmod, mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';

export const scanner = Object.freeze({
  version: '2.6.0',
  url: 'https://github.com/google/osv-scanner/releases/download/v2.6.0/osv-scanner_linux_amd64',
  sha256: 'ca69b3d3cd08f889a49dc0a383122f71cc528b83803671df5fd874d97485b108',
});

export const lockfileGlobs = Object.freeze(JSON.parse(readFileSync(new URL('./lockfiles.json', import.meta.url), 'utf8')));
const lockfileNames = lockfileGlobs.map(glob => new RegExp(`^${glob.replace(/[.+?^${}()|[\]\\]/gu, '\\$&').replaceAll('*', '[^/]*')}$`, 'u'));

export function isLockfile(path) {
  const parts = path.split('/');
  const name = parts.at(-1);
  return !parts.includes('node_modules') && lockfileNames.some(pattern => pattern.test(name));
}

export const severities = Object.freeze(['CRITICAL', 'HIGH', 'MODERATE', 'LOW', 'UNKNOWN']);
const issueLabel = 'dependency-audit';
const maximumRows = 150;
const maximumIssueBody = 60_000;

function object(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function list(value) {
  return Array.isArray(value) ? value : [];
}

function severityFromScore(score) {
  const value = Number.parseFloat(score);
  if (!Number.isFinite(value) || value <= 0) return 'UNKNOWN';
  return value >= 9 ? 'CRITICAL' : value >= 7 ? 'HIGH' : value >= 4 ? 'MODERATE' : 'LOW';
}

function severityFromLabel(label) {
  const value = String(label ?? '').toUpperCase();
  if (value === 'MEDIUM') return 'MODERATE';
  return severities.includes(value) ? value : 'UNKNOWN';
}

function higher(left, right) {
  return severities.indexOf(left) <= severities.indexOf(right) ? left : right;
}

const idPreference = ['GHSA-', 'RUSTSEC-', 'CVE-', 'GO-', 'PYSEC-'];

export function primaryId(ids) {
  const sorted = [...new Set(ids)].sort();
  for (const prefix of idPreference) {
    const match = sorted.find(id => id.startsWith(prefix));
    if (match) return match;
  }
  return sorted[0];
}

function compareVersions(left, right) {
  const parts = value => value.split(/[.+-]/u).map(part => (/^\d+$/u.test(part) ? Number(part) : part));
  const a = parts(left);
  const b = parts(right);
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    if (a[index] === undefined) return -1;
    if (b[index] === undefined) return 1;
    if (a[index] === b[index]) continue;
    if (typeof a[index] === 'number' && typeof b[index] === 'number') return a[index] - b[index];
    return String(a[index]).localeCompare(String(b[index]));
  }
  return 0;
}

function fixedVersions(vulnerabilities, name, ecosystem) {
  const fixed = new Set();
  for (const vulnerability of vulnerabilities) {
    for (const affected of list(vulnerability.affected)) {
      const pkg = object(affected.package) ? affected.package : {};
      if (pkg.name !== undefined && pkg.name !== name) continue;
      if (pkg.ecosystem !== undefined && ecosystem !== undefined
        && String(pkg.ecosystem).split(':')[0] !== String(ecosystem).split(':')[0]) continue;
      for (const range of list(affected.ranges)) {
        for (const event of list(range.events)) {
          if (typeof event?.fixed === 'string' && event.fixed.length > 0 && event.fixed.length <= 64) fixed.add(event.fixed);
        }
      }
    }
  }
  return [...fixed].sort(compareVersions);
}

function informational(vulnerability) {
  for (const affected of list(vulnerability.affected)) {
    const kind = object(affected.database_specific) ? affected.database_specific.informational : undefined;
    if (typeof kind === 'string' && kind.length > 0) return kind;
  }
  const kind = object(vulnerability.database_specific) ? vulnerability.database_specific.informational : undefined;
  return typeof kind === 'string' && kind.length > 0 ? kind : null;
}

function posixPath(path) {
  return path.split(sep).join('/');
}

export function findingsFromReport(report, root) {
  if (!object(report) || !Array.isArray(report.results)) throw new Error('OSV-Scanner returned a report without results');
  const findings = [];
  for (const result of report.results) {
    const source = object(result?.source) ? String(result.source.path ?? '') : '';
    const absolute = isAbsolute(source) ? source : resolve(root, source);
    const lockfile = posixPath(relative(root, absolute));
    if (!lockfile || lockfile.startsWith('..')) throw new Error(`OSV-Scanner reported a source outside the scanned tree: ${source}`);
    for (const entry of list(result.packages)) {
      const pkg = object(entry?.package) ? entry.package : {};
      const vulnerabilities = list(entry.vulnerabilities).filter(object);
      const byId = new Map(vulnerabilities.map(vulnerability => [String(vulnerability.id), vulnerability]));
      const groups = list(entry.groups).filter(group => list(group.ids).length > 0);
      const grouped = new Set(groups.flatMap(group => list(group.ids).map(String)));
      for (const vulnerability of vulnerabilities) {
        if (!grouped.has(String(vulnerability.id))) groups.push({ ids: [String(vulnerability.id)] });
      }
      for (const group of groups) {
        const members = list(group.ids).map(String).map(id => byId.get(id)).filter(Boolean);
        if (members.length === 0) continue;
        const ids = [...new Set([...list(group.ids).map(String), ...list(group.aliases).map(String),
          ...members.flatMap(member => list(member.aliases).map(String))])];
        let severity = severityFromScore(group.max_severity);
        for (const member of members) {
          severity = higher(severity, severityFromLabel(object(member.database_specific) ? member.database_specific.severity : undefined));
        }
        const kinds = members.map(informational);
        const id = primaryId(list(group.ids).map(String));
        findings.push({
          lockfile,
          ecosystem: String(pkg.ecosystem ?? ''),
          package: String(pkg.name ?? ''),
          version: String(pkg.version ?? ''),
          id,
          aliases: ids.filter(alias => alias !== id).sort(),
          summary: String(members.find(member => member.summary)?.summary ?? '').replace(/\s+/gu, ' ').trim().slice(0, 160),
          severity,
          informational: kinds.every(Boolean) ? kinds[0] : null,
          fixed: fixedVersions(members, pkg.name, pkg.ecosystem),
        });
      }
    }
  }
  return findings.sort(compareFindings);
}

export function compareFindings(left, right) {
  return severities.indexOf(left.severity) - severities.indexOf(right.severity)
    || left.package.localeCompare(right.package)
    || compareVersions(left.version, right.version)
    || left.id.localeCompare(right.id)
    || left.lockfile.localeCompare(right.lockfile);
}

export function findingKey(finding) {
  const advisories = [finding.id, ...finding.aliases].sort().join(',');
  return [finding.lockfile, finding.ecosystem, finding.package, finding.version, advisories].join('\u0000');
}

export function introducedFindings(head, base) {
  const existing = new Set(base.map(findingKey));
  const existingIds = new Map();
  for (const finding of base) {
    const key = [finding.lockfile, finding.ecosystem, finding.package, finding.version].join('\u0000');
    const ids = existingIds.get(key) ?? new Set();
    for (const id of [finding.id, ...finding.aliases]) ids.add(id);
    existingIds.set(key, ids);
  }
  return head.filter(finding => {
    if (existing.has(findingKey(finding))) return false;
    const ids = existingIds.get([finding.lockfile, finding.ecosystem, finding.package, finding.version].join('\u0000'));
    return !ids || ![finding.id, ...finding.aliases].some(id => ids.has(id));
  });
}

function escapeCell(value) {
  return String(value).replace(/[\\|`*_[\]<>]/gu, character => `\\${character}`).replace(/\r?\n/gu, ' ');
}

function advisoryLink(id) {
  return `[${escapeCell(id)}](https://osv.dev/vulnerability/${encodeURIComponent(id)})`;
}

export function rows(findings) {
  const merged = new Map();
  for (const finding of findings) {
    const key = [finding.ecosystem, finding.package, finding.version, finding.id].join('\u0000');
    const row = merged.get(key) ?? { ...finding, lockfiles: [] };
    row.lockfiles.push(finding.lockfile);
    merged.set(key, row);
  }
  return [...merged.values()].sort(compareFindings);
}

export function upgrades(finding) {
  return finding.fixed.filter(version => compareVersions(version, finding.version) > 0);
}

function table(findings, limit = maximumRows) {
  const merged = rows(findings);
  const lines = ['| Severity | Package | Version | Advisory | Fixed in | Lockfiles | Summary |', '| --- | --- | --- | --- | --- | --- | --- |'];
  for (const row of merged.slice(0, limit)) {
    const lockfiles = [...new Set(row.lockfiles)].sort();
    lines.push(`| ${row.severity} | ${escapeCell(row.package)} | ${escapeCell(row.version)} | ${advisoryLink(row.id)} | `
      + `${upgrades(row).length > 0 ? escapeCell(upgrades(row).slice(0, 3).join(', ')) : 'No fixed release'} | `
      + `${escapeCell(lockfiles.slice(0, 3).join(', '))}${lockfiles.length > 3 ? ` and ${lockfiles.length - 3} more` : ''} | `
      + `${escapeCell(row.summary)} |`);
  }
  if (merged.length > limit) lines.push('', `${merged.length - limit} more rows are omitted; the run log lists every finding.`);
  return lines.join('\n');
}

function counts(findings) {
  const merged = rows(findings);
  const bySeverity = Object.fromEntries(severities.map(severity => [severity, merged.filter(row => row.severity === severity).length]));
  return { total: merged.length, bySeverity };
}

function countLine(findings) {
  const { total, bySeverity } = counts(findings);
  const parts = severities.filter(severity => bySeverity[severity] > 0).map(severity => `${bySeverity[severity]} ${severity.toLowerCase()}`);
  return `${total} known ${total === 1 ? 'vulnerability' : 'vulnerabilities'}${parts.length > 0 ? ` (${parts.join(', ')})` : ''}`;
}

export function renderReport({ lockfiles, findings, introduced = null, runUrl = '', revision = '' }) {
  const vulnerable = findings.filter(finding => !finding.informational);
  const advisories = findings.filter(finding => finding.informational);
  const lines = ['## Dependency audit', ''];
  const scanned = lockfiles.length === 0
    ? 'No supported lockfiles are tracked in this repository.'
    : `OSV-Scanner ${scanner.version} checked ${lockfiles.length} ${lockfiles.length === 1 ? 'lockfile' : 'lockfiles'}: `
      + `${lockfiles.slice(0, 12).map(path => `\`${path}\``).join(', ')}${lockfiles.length > 12 ? ` and ${lockfiles.length - 12} more` : ''}.`;
  lines.push(scanned, '');
  if (introduced !== null) {
    const added = introduced.filter(finding => !finding.informational);
    lines.push(added.length === 0
      ? 'This pull request adds no known vulnerabilities.'
      : `This pull request adds ${countLine(added)} that the base branch does not have.`, '');
    if (added.length > 0) lines.push('### Added by this pull request', '', table(added), '');
    if (vulnerable.length > added.length) {
      lines.push(`The base branch already has ${countLine(vulnerable.filter(finding => !added.includes(finding)))}; `
        + 'the scheduled audit on the default branch tracks them in an issue.', '');
    }
  } else {
    lines.push(vulnerable.length === 0 ? 'No known vulnerabilities.' : `${countLine(vulnerable)}.`, '');
    if (vulnerable.length > 0) lines.push(table(vulnerable), '');
  }
  if (advisories.length > 0) {
    lines.push(`### Unmaintained or unsound packages (${rows(advisories).length})`, '',
      'These advisories report no exploitable vulnerability and do not fail the audit.', '', table(advisories), '');
  }
  if (vulnerable.length > 0 && introduced === null) {
    lines.push('Update each package to a fixed version, or to a version whose dependents no longer pin it. '
      + 'When no fixed release exists, replace the dependency or record a reviewed, dated exception in `osv-scanner.toml` '
      + '(`[[IgnoredVulns]]` with `id`, `ignoreUntil`, and `reason`).', '');
  }
  if (runUrl) lines.push(`Run: ${runUrl}${revision ? ` at \`${revision.slice(0, 12)}\`` : ''}`);
  return lines.join('\n').trimEnd();
}

export function listLockfiles(workspace, run = spawnSync) {
  const result = run('git', ['-C', workspace, 'ls-files', '-z'], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  if (result.error || result.status !== 0) throw new Error(`git ls-files failed: ${result.error?.message ?? result.stderr}`);
  return result.stdout.split('\0').filter(path => path.length > 0 && isLockfile(path)).sort();
}

export async function downloadScanner({ directory, fetchImpl = fetch, platform = process.platform, arch = process.arch, pin = scanner }) {
  if (platform !== 'linux' || arch !== 'x64') throw new Error(`the pinned OSV-Scanner build needs a Linux x64 runner, not ${platform}/${arch}`);
  const response = await fetchImpl(pin.url, { redirect: 'follow' });
  if (!response.ok) throw new Error(`downloading OSV-Scanner ${pin.version} failed with HTTP ${response.status}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  const digest = createHash('sha256').update(bytes).digest('hex');
  if (digest !== pin.sha256) throw new Error(`OSV-Scanner ${pin.version} has SHA-256 ${digest}, expected ${pin.sha256}`);
  const path = join(directory, 'osv-scanner');
  await writeFile(path, bytes);
  await chmod(path, 0o755);
  return path;
}

export function runScanner(binary, directory, output) {
  return new Promise((done, fail) => {
    const child = spawn(binary, ['scan', 'source', '--recursive', '--allow-no-lockfiles', '--format', 'json', '--output-file', output, directory],
      { stdio: ['ignore', 'inherit', 'pipe'] });
    let stderr = '';
    child.stderr.on('data', chunk => {
      stderr = `${stderr}${chunk}`.slice(-20_000);
      process.stderr.write(chunk);
    });
    child.on('error', fail);
    child.on('close', async code => {
      if (code !== 0 && code !== 1) {
        fail(new Error(`OSV-Scanner exited with ${code}: ${stderr.trim().split('\n').slice(-3).join(' ')}`));
        return;
      }
      try {
        done(JSON.parse(await readFile(output, 'utf8')));
      } catch (error) {
        fail(new Error(`OSV-Scanner wrote no readable JSON report: ${error.message}`));
      }
    });
  });
}

export function githubClient({ token, apiUrl = 'https://api.github.com', fetchImpl = fetch }) {
  return async (path, { method = 'GET', body, accept = 'application/vnd.github+json', allow = [] } = {}) => {
    const response = await fetchImpl(`${apiUrl}${path}`, {
      method,
      headers: {
        accept,
        authorization: `Bearer ${token}`,
        'x-github-api-version': '2022-11-28',
        ...(body === undefined ? {} : { 'content-type': 'application/json' }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (allow.includes(response.status)) return { status: response.status, data: null };
    if (!response.ok) {
      const detail = (await response.text()).slice(0, 300);
      throw new Error(`GitHub API ${method} ${path} failed with HTTP ${response.status}: ${detail}`);
    }
    if (response.status === 204) return { status: 204, data: null };
    const data = accept.includes('raw') ? Buffer.from(await response.arrayBuffer()) : await response.json();
    return { status: response.status, data };
  };
}

function contentsPath(repository, path, ref) {
  return `/repos/${repository}/contents/${path.split('/').map(encodeURIComponent).join('/')}?ref=${encodeURIComponent(ref)}`;
}

export async function fetchBaseLockfiles({ github, repository, ref, paths, directory }) {
  const fetched = [];
  for (const path of paths) {
    const { status, data } = await github(contentsPath(repository, path, ref), { accept: 'application/vnd.github.raw', allow: [404] });
    if (status === 404) continue;
    const target = join(directory, ...path.split('/'));
    await mkdir(dirname(target), { recursive: true });
    await writeFile(target, data);
    fetched.push(path);
  }
  return fetched;
}

export async function syncIssue({ github, repository, findings, report }) {
  const vulnerable = findings.filter(finding => !finding.informational);
  const open = await github(`/repos/${repository}/issues?state=open&labels=${issueLabel}&per_page=100`, { allow: [410] });
  if (open.status === 410) return { action: 'disabled', number: null };
  const existing = list(open.data).filter(issue => !issue.pull_request && issue.title.startsWith('Dependency audit:'));
  const [current, ...duplicates] = existing.sort((left, right) => left.number - right.number);
  for (const duplicate of duplicates) {
    await github(`/repos/${repository}/issues/${duplicate.number}`, { method: 'PATCH', body: { state: 'closed', state_reason: 'not_planned' } });
  }
  if (vulnerable.length === 0) {
    if (current) {
      await github(`/repos/${repository}/issues/${current.number}/comments`, { method: 'POST', body: { body: report } });
      await github(`/repos/${repository}/issues/${current.number}`, { method: 'PATCH', body: { state: 'closed', state_reason: 'completed' } });
      return { action: 'closed', number: current.number };
    }
    return { action: 'none', number: null };
  }
  const body = report.length > maximumIssueBody ? `${report.slice(0, maximumIssueBody)}\n\nThe run summary has the complete report.` : report;
  const title = `Dependency audit: ${countLine(vulnerable)}`;
  if (current) {
    await github(`/repos/${repository}/issues/${current.number}`, { method: 'PATCH', body: { title, body } });
    return { action: 'updated', number: current.number };
  }
  await github(`/repos/${repository}/labels`, {
    method: 'POST', allow: [422],
    body: { name: issueLabel, color: 'b60205', description: 'Known vulnerabilities reported by the scheduled dependency audit' },
  });
  const created = await github(`/repos/${repository}/issues`, { method: 'POST', body: { title, body, labels: [issueLabel] } });
  return { action: 'created', number: created.data?.number ?? null };
}

async function readEvent(path) {
  if (!path) return {};
  try {
    return JSON.parse(await readFile(path, 'utf8'));
  } catch {
    return {};
  }
}

export async function runAction(environment = process.env, dependencies = {}) {
  const {
    fetchImpl = fetch, platform = process.platform, arch = process.arch, scan = runScanner, lockfiles: listTracked = listLockfiles,
    log = console.log, pin = scanner,
  } = dependencies;
  const workspace = environment.GITHUB_WORKSPACE || process.cwd();
  const temp = await mkdtemp(join(environment.RUNNER_TEMP || process.env.TMPDIR || '/tmp', 'dependency-audit-'));
  const repository = environment.GITHUB_REPOSITORY ?? '';
  const event = await readEvent(environment.GITHUB_EVENT_PATH);
  const token = environment['INPUT_GITHUB-TOKEN'] || environment.GITHUB_TOKEN || '';
  const github = githubClient({ token, apiUrl: environment.GITHUB_API_URL || 'https://api.github.com', fetchImpl });
  const runUrl = environment.GITHUB_RUN_ID
    ? `${environment.GITHUB_SERVER_URL || 'https://github.com'}/${repository}/actions/runs/${environment.GITHUB_RUN_ID}` : '';

  const tracked = listTracked(workspace);
  const binary = await downloadScanner({ directory: temp, fetchImpl, platform, arch, pin });
  const findings = findingsFromReport(await scan(binary, workspace, join(temp, 'head.json')), workspace);

  let introduced = null;
  if (environment.GITHUB_EVENT_NAME === 'pull_request' && event.pull_request?.base?.sha) {
    const baseDirectory = join(temp, 'base');
    await mkdir(baseDirectory, { recursive: true });
    const paths = [...new Set(findings.map(finding => finding.lockfile))];
    await fetchBaseLockfiles({ github, repository, ref: event.pull_request.base.sha, paths, directory: baseDirectory });
    const base = findingsFromReport(await scan(binary, baseDirectory, join(temp, 'base.json')), baseDirectory);
    introduced = introducedFindings(findings, base);
  }

  const report = renderReport({ lockfiles: tracked, findings, introduced, runUrl, revision: environment.GITHUB_SHA ?? '' });
  if (environment.GITHUB_STEP_SUMMARY) await appendFile(environment.GITHUB_STEP_SUMMARY, `${report}\n`, 'utf8');
  for (const finding of findings) {
    log(`${finding.informational ? 'advisory' : finding.severity.toLowerCase()}: ${finding.package}@${finding.version} ${finding.id} in ${finding.lockfile}`);
  }

  const vulnerable = findings.filter(finding => !finding.informational);
  const added = introduced === null ? [] : introduced.filter(finding => !finding.informational);
  const defaultBranch = event.repository?.default_branch;
  const untracked = { action: 'none', number: null };
  let issue = untracked;
  if (introduced === null && defaultBranch && environment.GITHUB_REF === `refs/heads/${defaultBranch}`
    && ['schedule', 'workflow_dispatch', 'push'].includes(environment.GITHUB_EVENT_NAME)) {
    issue = await syncIssue({ github, repository, findings, report });
    if (issue.number !== null) log(`Tracking issue #${issue.number} ${issue.action}`);
    if (issue.action === 'disabled') log('Issues are disabled in this repository, so the run fails while vulnerabilities remain.');
  }
  if (environment.GITHUB_OUTPUT) {
    await appendFile(environment.GITHUB_OUTPUT, `vulnerabilities=${rows(vulnerable).length}\nintroduced=${rows(added).length}\n`, 'utf8');
  }
  const issueKept = issue !== untracked && issue.action !== 'disabled';
  const failed = introduced === null ? vulnerable.length > 0 && !issueKept : added.length > 0;
  log(introduced === null
    ? (vulnerable.length === 0 ? 'No known vulnerabilities.' : `${countLine(vulnerable)}.`)
    : (added.length === 0 ? 'This pull request adds no known vulnerabilities.' : `This pull request adds ${countLine(added)}.`));
  return { failed, findings, introduced, issue, report };
}
