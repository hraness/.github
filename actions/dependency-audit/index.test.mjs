import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import {
  downloadScanner, fetchBaseLockfiles, findingsFromReport, introducedFindings, isLockfile, listLockfiles, lockfileGlobs, primaryId,
  renderReport, runAction, scanner, syncIssue, upgrades,
} from './index.mjs';

const root = '/work/repo';

function vulnerability(id, { aliases = [], severity, informational, fixed = [], name = 'pkg', ecosystem = 'npm', summary = `${id} summary` } = {}) {
  return {
    id, aliases, summary,
    ...(severity ? { database_specific: { severity } } : {}),
    affected: [{
      package: { name, ecosystem },
      ...(informational ? { database_specific: { informational } } : {}),
      ranges: [{ type: 'SEMVER', events: [{ introduced: '0' }, ...fixed.map(version => ({ fixed: version }))] }],
    }],
  };
}

function report(entries) {
  return {
    results: entries.map(({ path, packages }) => ({
      source: { path, type: 'lockfile' },
      packages: packages.map(({ name, version, ecosystem = 'npm', vulnerabilities, groups }) => ({
        package: { name, version, ecosystem }, vulnerabilities, ...(groups ? { groups } : {}),
      })),
    })),
  };
}

const braces = vulnerability('GHSA-vfj7-8cjw-p6xm', { aliases: ['CVE-2026-93687'], severity: 'HIGH', name: 'braces' });
const anyioGhsa = vulnerability('GHSA-82r6-8w77-94w6', { aliases: ['CVE-2026-63374'], severity: 'CRITICAL', fixed: ['4.14.2'], name: 'anyio', ecosystem: 'PyPI' });
const anyioPysec = vulnerability('PYSEC-2026-4025', { aliases: ['CVE-2026-63374', 'GHSA-82r6-8w77-94w6'], fixed: ['4.14.2'], name: 'anyio', ecosystem: 'PyPI' });
const bincode = vulnerability('RUSTSEC-2025-0141', { informational: 'unmaintained', name: 'bincode', ecosystem: 'crates.io' });
const h2 = vulnerability('RUSTSEC-2026-0258', { aliases: ['GHSA-q83h-524g-xf6h'], fixed: ['0.4.16'], name: 'h2', ecosystem: 'crates.io' });

const sample = report([
  { path: `${root}/bun.lock`, packages: [{ name: 'braces', version: '3.0.3', vulnerabilities: [braces], groups: [{ ids: ['GHSA-vfj7-8cjw-p6xm'], max_severity: '8.7' }] }] },
  { path: `${root}/py/uv.lock`, packages: [{ name: 'anyio', version: '4.9.0', ecosystem: 'PyPI', vulnerabilities: [anyioGhsa, anyioPysec],
    groups: [{ ids: ['GHSA-82r6-8w77-94w6', 'PYSEC-2026-4025'], aliases: ['CVE-2026-63374'], max_severity: '9.1' }] }] },
  { path: `${root}/Cargo.lock`, packages: [
    { name: 'bincode', version: '1.3.3', ecosystem: 'crates.io', vulnerabilities: [bincode] },
    { name: 'h2', version: '0.4.15', ecosystem: 'crates.io', vulnerabilities: [h2] },
  ] },
]);

test('one finding per lockfile, package version and OSV group, with severity, fixes and advisories', () => {
  const findings = findingsFromReport(sample, root);
  assert.deepEqual(findings.map(finding => [finding.severity, finding.package, finding.id, finding.lockfile, finding.informational]), [
    ['CRITICAL', 'anyio', 'GHSA-82r6-8w77-94w6', 'py/uv.lock', null],
    ['HIGH', 'braces', 'GHSA-vfj7-8cjw-p6xm', 'bun.lock', null],
    ['UNKNOWN', 'bincode', 'RUSTSEC-2025-0141', 'Cargo.lock', 'unmaintained'],
    ['UNKNOWN', 'h2', 'RUSTSEC-2026-0258', 'Cargo.lock', null],
  ].sort((left, right) => ['CRITICAL', 'HIGH', 'MODERATE', 'LOW', 'UNKNOWN'].indexOf(left[0])
    - ['CRITICAL', 'HIGH', 'MODERATE', 'LOW', 'UNKNOWN'].indexOf(right[0]) || left[1].localeCompare(right[1])));
  const anyio = findings.find(finding => finding.package === 'anyio');
  assert.deepEqual(anyio.aliases, ['CVE-2026-63374', 'PYSEC-2026-4025']);
  assert.deepEqual(anyio.fixed, ['4.14.2']);
  assert.equal(findings.find(finding => finding.package === 'braces').fixed.length, 0);
});

test('severity comes from the GitHub label or the group CVSS score, whichever is higher', () => {
  const scored = report([{ path: `${root}/bun.lock`, packages: [{ name: 'a', version: '1.0.0',
    vulnerabilities: [vulnerability('GHSA-aaaa-aaaa-aaaa', { severity: 'MODERATE', name: 'a' })], groups: [{ ids: ['GHSA-aaaa-aaaa-aaaa'], max_severity: '9.8' }] }] }]);
  assert.equal(findingsFromReport(scored, root)[0].severity, 'CRITICAL');
  const labelled = report([{ path: `${root}/bun.lock`, packages: [{ name: 'a', version: '1.0.0',
    vulnerabilities: [vulnerability('GHSA-bbbb-bbbb-bbbb', { severity: 'MEDIUM', name: 'a' })] }] }]);
  assert.equal(findingsFromReport(labelled, root)[0].severity, 'MODERATE');
});

test('upgrades list only fixed versions above the installed one', () => {
  assert.deepEqual(upgrades({ version: '5.0.9', fixed: ['1.1.19', '2.1.5', '3.0.7', '5.0.10'] }), ['5.0.10']);
  assert.deepEqual(upgrades({ version: '1.1.18', fixed: ['1.1.19', '2.1.5'] }), ['1.1.19', '2.1.5']);
  assert.deepEqual(upgrades({ version: '3.0.3', fixed: [] }), []);
});

test('fixed versions are ordered numerically and ignore other packages in the advisory', () => {
  const multi = vulnerability('GHSA-cccc-cccc-cccc', { name: 'brace-expansion', fixed: ['5.0.10', '2.1.5', '3.0.7'] });
  multi.affected.push({ package: { name: 'other', ecosystem: 'npm' }, ranges: [{ events: [{ fixed: '9.9.9' }] }] });
  const findings = findingsFromReport(report([{ path: `${root}/bun.lock`, packages: [{ name: 'brace-expansion', version: '1.1.18', vulnerabilities: [multi] }] }]), root);
  assert.deepEqual(findings[0].fixed, ['2.1.5', '3.0.7', '5.0.10']);
});

test('reports without results or with sources outside the scanned tree are refused', () => {
  assert.throws(() => findingsFromReport({}, root), /without results/u);
  assert.throws(() => findingsFromReport(report([{ path: '/elsewhere/bun.lock', packages: [] }]), root), /outside the scanned tree/u);
  assert.deepEqual(findingsFromReport({ results: [] }, root), []);
});

test('primary advisory identifiers prefer GitHub, then RustSec, then CVE', () => {
  assert.equal(primaryId(['PYSEC-1', 'GHSA-x', 'CVE-1']), 'GHSA-x');
  assert.equal(primaryId(['CVE-1', 'RUSTSEC-1']), 'RUSTSEC-1');
  assert.equal(primaryId(['OSV-2', 'OSV-1']), 'OSV-1');
});

test('a pull request fails only on findings its base lockfile does not already have', () => {
  const head = findingsFromReport(sample, root);
  const base = findingsFromReport(report([
    { path: '/base/bun.lock', packages: [{ name: 'braces', version: '3.0.3', vulnerabilities: [braces] }] },
    { path: '/base/py/uv.lock', packages: [{ name: 'anyio', version: '4.9.0', ecosystem: 'PyPI', vulnerabilities: [anyioPysec] }] },
  ]), '/base');
  assert.deepEqual(introducedFindings(head, base).map(finding => finding.package).sort(), ['bincode', 'h2']);
  const moved = findingsFromReport(report([{ path: '/base/site/bun.lock', packages: [{ name: 'braces', version: '3.0.3', vulnerabilities: [braces] }] }]), '/base');
  assert.ok(introducedFindings(head, moved).some(finding => finding.package === 'braces'), 'a vulnerable version in a new lockfile is new');
  const upgraded = findingsFromReport(report([{ path: '/base/bun.lock', packages: [{ name: 'braces', version: '3.0.2', vulnerabilities: [braces] }] }]), '/base');
  assert.ok(introducedFindings(head, upgraded).some(finding => finding.package === 'braces'), 'a different vulnerable version is new');
});

test('the report escapes table cells, separates advisories, and explains how to resolve findings', () => {
  const findings = findingsFromReport(sample, root);
  findings[0].summary = 'pipe | and <tag>';
  const text = renderReport({ lockfiles: ['Cargo.lock', 'bun.lock', 'py/uv.lock'], findings, runUrl: 'https://github.com/o/r/actions/runs/1', revision: 'a'.repeat(40) });
  assert.match(text, /OSV-Scanner 2\.6\.0 checked 3 lockfiles/u);
  assert.match(text, /3 known vulnerabilities \(1 critical, 1 high, 1 unknown\)\./u);
  assert.match(text, /pipe \\\| and \\<tag\\>/u);
  assert.match(text, /\[GHSA-vfj7-8cjw-p6xm\]\(https:\/\/osv\.dev\/vulnerability\/GHSA-vfj7-8cjw-p6xm\)/u);
  assert.match(text, /### Unmaintained or unsound packages \(1\)/u);
  assert.match(text, /No fixed release/u);
  assert.match(text, /osv-scanner\.toml/u);
  assert.match(text, /Run: https:\/\/github\.com\/o\/r\/actions\/runs\/1 at `aaaaaaaaaaaa`/u);
  assert.equal(renderReport({ lockfiles: [], findings: [] }).includes('No supported lockfiles are tracked'), true);
  assert.match(renderReport({ lockfiles: ['bun.lock'], findings: [] }), /No known vulnerabilities\./u);
});

test('pull request reports name added findings and only count existing ones', () => {
  const findings = findingsFromReport(sample, root);
  const added = findings.filter(finding => finding.package === 'h2');
  const text = renderReport({ lockfiles: ['Cargo.lock'], findings, introduced: added });
  assert.match(text, /This pull request adds 1 known vulnerability \(1 unknown\) that the base branch does not have\./u);
  assert.match(text, /### Added by this pull request/u);
  assert.match(text, /The base branch already has 2 known vulnerabilities/u);
  assert.match(renderReport({ lockfiles: ['Cargo.lock'], findings, introduced: [] }), /This pull request adds no known vulnerabilities\./u);
});

test('only tracked lockfiles outside node_modules are listed', () => {
  const run = () => ({ status: 0, stdout: ['bun.lock', 'site/bun.lock', 'README.md', 'node_modules/x/package-lock.json', 'api/requirements-dev.txt',
    'crates/Cargo.lock', 'web/pnpm-lock.yaml', 'Cargo.toml'].join('\0') });
  assert.deepEqual(listLockfiles('/repo', run), ['api/requirements-dev.txt', 'bun.lock', 'crates/Cargo.lock', 'site/bun.lock', 'web/pnpm-lock.yaml']);
  assert.throws(() => listLockfiles('/repo', () => ({ status: 128, stderr: 'not a git repository' })), /git ls-files failed/u);
  assert.ok(isLockfile('go.mod') && isLockfile('a/App.deps.json') && isLockfile('requirements.txt'));
  assert.ok(!isLockfile('bun.lock.bak') && !isLockfile('Cargo.toml') && !isLockfile('node_modules/a/bun.lock'));
  assert.ok(lockfileGlobs.includes('bun.lock') && lockfileGlobs.includes('Cargo.lock') && lockfileGlobs.includes('uv.lock'));
});

test('the scanner download is refused on other platforms and on a checksum mismatch', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'dependency-audit-download-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const bytes = Buffer.from('scanner');
  const fetchImpl = async () => new Response(bytes);
  await assert.rejects(downloadScanner({ directory, fetchImpl, platform: 'darwin', arch: 'arm64' }), /Linux x64 runner/u);
  await assert.rejects(downloadScanner({ directory, fetchImpl, platform: 'linux', arch: 'x64' }), /expected ca69b3d3/u);
  await assert.rejects(downloadScanner({ directory, fetchImpl: async () => new Response('', { status: 404 }), platform: 'linux', arch: 'x64' }), /HTTP 404/u);
  const pin = { ...scanner, sha256: createHash('sha256').update(bytes).digest('hex') };
  const path = await downloadScanner({ directory, fetchImpl, platform: 'linux', arch: 'x64', pin });
  assert.equal(await readFile(path, 'utf8'), 'scanner');
  assert.equal((await stat(path)).mode & 0o777, 0o755);
});

function fakeGithub(responses = {}) {
  const calls = [];
  const github = async (path, options = {}) => {
    calls.push({ path, method: options.method ?? 'GET', body: options.body });
    const key = `${options.method ?? 'GET'} ${path.split('?')[0]}`;
    const value = responses[key];
    if (typeof value === 'function') return value(path, options);
    return value ?? { status: 200, data: [] };
  };
  return { github, calls };
}

test('the tracking issue is created, updated, deduplicated, and closed with the latest report', async () => {
  const findings = findingsFromReport(sample, root);
  const repository = 'hraness/example';
  const created = fakeGithub({ [`POST /repos/${repository}/issues`]: { status: 201, data: { number: 7 } } });
  assert.deepEqual(await syncIssue({ github: created.github, repository, findings, report: 'report' }), { action: 'created', number: 7 });
  assert.deepEqual(created.calls.map(call => `${call.method} ${call.path.split('?')[0]}`), [
    `GET /repos/${repository}/issues`, `POST /repos/${repository}/labels`, `POST /repos/${repository}/issues`,
  ]);
  assert.equal(created.calls[2].body.title, 'Dependency audit: 3 known vulnerabilities (1 critical, 1 high, 1 unknown)');
  assert.deepEqual(created.calls[2].body.labels, ['dependency-audit']);

  const open = [{ number: 9, title: 'Dependency audit: 1 known vulnerability (1 high)' }, { number: 4, title: 'Dependency audit: old' },
    { number: 5, title: 'Unrelated', pull_request: {} }];
  const updated = fakeGithub({ [`GET /repos/${repository}/issues`]: { status: 200, data: open } });
  assert.deepEqual(await syncIssue({ github: updated.github, repository, findings, report: 'report' }), { action: 'updated', number: 4 });
  assert.deepEqual(updated.calls.slice(1).map(call => [call.path, call.body.state ?? call.body.title]), [
    [`/repos/${repository}/issues/9`, 'closed'],
    [`/repos/${repository}/issues/4`, 'Dependency audit: 3 known vulnerabilities (1 critical, 1 high, 1 unknown)'],
  ]);

  const clean = fakeGithub({ [`GET /repos/${repository}/issues`]: { status: 200, data: [open[1]] } });
  const advisoriesOnly = findings.filter(finding => finding.informational);
  assert.deepEqual(await syncIssue({ github: clean.github, repository, findings: advisoriesOnly, report: 'No known vulnerabilities.' }), { action: 'closed', number: 4 });
  assert.deepEqual(clean.calls.slice(1).map(call => [call.method, call.path, call.body.state ?? call.body.body]), [
    ['POST', `/repos/${repository}/issues/4/comments`, 'No known vulnerabilities.'],
    ['PATCH', `/repos/${repository}/issues/4`, 'closed'],
  ]);
  const quiet = fakeGithub();
  assert.deepEqual(await syncIssue({ github: quiet.github, repository, findings: [], report: '' }), { action: 'none', number: null });
  assert.equal(quiet.calls.length, 1);
});

test('base lockfiles are fetched from the exact base commit and missing paths are skipped', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'dependency-audit-base-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const requested = [];
  const github = async (path, options) => {
    requested.push([path, options.accept]);
    return path.includes('site') ? { status: 404, data: null } : { status: 200, data: Buffer.from('lock') };
  };
  const fetched = await fetchBaseLockfiles({ github, repository: 'o/r', ref: 'b'.repeat(40), paths: ['bun.lock', 'site/bun.lock', 'a b/Cargo.lock'], directory });
  assert.deepEqual(fetched, ['bun.lock', 'a b/Cargo.lock']);
  assert.deepEqual(requested.map(([path]) => path), [
    `/repos/o/r/contents/bun.lock?ref=${'b'.repeat(40)}`,
    `/repos/o/r/contents/site/bun.lock?ref=${'b'.repeat(40)}`,
    `/repos/o/r/contents/a%20b/Cargo.lock?ref=${'b'.repeat(40)}`,
  ]);
  assert.ok(requested.every(([, accept]) => accept === 'application/vnd.github.raw'));
  assert.equal(await readFile(join(directory, 'a b', 'Cargo.lock'), 'utf8'), 'lock');
});

async function actionFixture(t, event, eventName, ref = 'refs/heads/main') {
  const directory = await mkdtemp(join(tmpdir(), 'dependency-audit-action-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const eventPath = join(directory, 'event.json');
  await writeFile(eventPath, JSON.stringify(event));
  const summary = join(directory, 'summary.md');
  const output = join(directory, 'output.txt');
  const environment = {
    GITHUB_WORKSPACE: root, RUNNER_TEMP: directory, GITHUB_REPOSITORY: 'hraness/example', GITHUB_EVENT_PATH: eventPath,
    GITHUB_EVENT_NAME: eventName, GITHUB_REF: ref, GITHUB_SHA: 'c'.repeat(40), GITHUB_RUN_ID: '42', GITHUB_STEP_SUMMARY: summary,
    GITHUB_OUTPUT: output, 'INPUT_GITHUB-TOKEN': 'token',
  };
  return { directory, environment, summary, output };
}

test('a pull request audit scans head and base and fails only on what it adds', async t => {
  const { environment, summary, output } = await actionFixture(t, { pull_request: { base: { sha: 'b'.repeat(40) } }, repository: { default_branch: 'main' } }, 'pull_request', 'refs/pull/3/merge');
  const scans = [];
  const scan = async (binary, directory) => {
    scans.push(directory);
    return directory === root ? sample : report([
      { path: join(directory, 'bun.lock'), packages: [{ name: 'braces', version: '3.0.3', vulnerabilities: [braces] }] },
      { path: join(directory, 'py', 'uv.lock'), packages: [{ name: 'anyio', version: '4.9.0', ecosystem: 'PyPI', vulnerabilities: [anyioGhsa] }] },
      { path: join(directory, 'Cargo.lock'), packages: [{ name: 'h2', version: '0.4.15', ecosystem: 'crates.io', vulnerabilities: [h2] }] },
    ]);
  };
  const requests = [];
  const fetchImpl = async (url, options = {}) => {
    requests.push([String(url), options.headers?.authorization]);
    if (String(url) === scanner.url) return new Response('binary');
    return new Response('lock');
  };
  const pin = { ...scanner, sha256: createHash('sha256').update('binary').digest('hex') };
  const result = await runAction(environment, { fetchImpl, platform: 'linux', arch: 'x64', scan, pin, lockfiles: () => ['Cargo.lock', 'bun.lock', 'py/uv.lock'], log: () => {} });
  assert.equal(result.failed, false, 'only the informational advisory is new');
  assert.equal(scans.length, 2);
  assert.deepEqual(requests.filter(([url]) => url.includes('/contents/')).map(([url, authorization]) => [url.replace(/\?.*/u, ''), authorization]).sort(), [
    ['https://api.github.com/repos/hraness/example/contents/Cargo.lock', 'Bearer token'],
    ['https://api.github.com/repos/hraness/example/contents/bun.lock', 'Bearer token'],
    ['https://api.github.com/repos/hraness/example/contents/py/uv.lock', 'Bearer token'],
  ]);
  assert.match(await readFile(summary, 'utf8'), /This pull request adds no known vulnerabilities\./u);
  assert.equal(await readFile(output, 'utf8'), 'vulnerabilities=3\nintroduced=0\n');
  assert.equal(result.issue.action, 'none');
});

test('a scheduled audit on the default branch fails on any vulnerability and updates the tracking issue', async t => {
  const { environment, summary } = await actionFixture(t, { repository: { default_branch: 'main' } }, 'schedule');
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push([options.method ?? 'GET', String(url).replace(/\?.*/u, '')]);
    if (String(url) === scanner.url) return new Response('binary');
    if (String(url).includes('/issues?')) return Response.json([]);
    if (String(url).endsWith('/labels')) return Response.json({}, { status: 201 });
    return Response.json({ number: 11 }, { status: 201 });
  };
  const pin = { ...scanner, sha256: createHash('sha256').update('binary').digest('hex') };
  const result = await runAction(environment, { fetchImpl, platform: 'linux', arch: 'x64', scan: async () => sample, pin, lockfiles: () => ['bun.lock'], log: () => {} });
  assert.equal(result.failed, true);
  assert.deepEqual(result.issue, { action: 'created', number: 11 });
  assert.deepEqual(calls.slice(1), [
    ['GET', 'https://api.github.com/repos/hraness/example/issues'],
    ['POST', 'https://api.github.com/repos/hraness/example/labels'],
    ['POST', 'https://api.github.com/repos/hraness/example/issues'],
  ]);
  assert.match(await readFile(summary, 'utf8'), /Run: https:\/\/github\.com\/hraness\/example\/actions\/runs\/42/u);
  const branch = await actionFixture(t, { repository: { default_branch: 'main' } }, 'workflow_dispatch', 'refs/heads/feature');
  const other = await runAction(branch.environment, { fetchImpl, platform: 'linux', arch: 'x64', scan: async () => sample, pin, lockfiles: () => [], log: () => {} });
  assert.equal(other.issue.action, 'none', 'only the default branch owns the tracking issue');
});

test('the action entrypoint fails visibly outside a Git checkout', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'dependency-audit-entry-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const entry = fileURLToPath(new URL('./main.mjs', import.meta.url));
  const result = spawnSync(process.execPath, [entry], { env: { GITHUB_WORKSPACE: directory, RUNNER_TEMP: directory, PATH: process.env.PATH }, encoding: 'utf8', timeout: 10_000 });
  assert.ifError(result.error);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /dependency-audit: git ls-files failed/u);
});
