import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { runAction, validateOptions, waitForNpm } from './index.mjs';

test('the actual action entrypoint cannot silently succeed under a symlink', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'npm-visible-entry-test-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const actionDirectory = fileURLToPath(new URL('.', import.meta.url));
  const entry = /^  main: (.+)$/mu.exec(await readFile(join(actionDirectory, 'action.yml'), 'utf8'))[1];
  await symlink(actionDirectory, join(directory, 'alias'), 'dir');
  const result = spawnSync(process.execPath, [join(directory, 'alias', entry)], {
    env: { INPUT_PACKAGE: '../invalid' }, encoding: 'utf8', timeout: 5_000,
  });
  assert.ifError(result.error);
  assert.equal(result.status, 1, 'Invalid inputs must fail even when the runner uses a symlink');
  assert.match(result.stderr, /npm-visible: package must/u);
});

const integrity = `sha512-${Buffer.alloc(64, 7).toString('base64')}`;
const options = { name: '@example/tool', version: '1.2.3', integrity, timeoutMs: 3_000, pollMs: 1_000 };
const slsa = 'https://slsa.dev/provenance/v1';
const url = 'https://registry.npmjs.org/-/npm/v1/attestations/@example%2ftool@1.2.3';
const archiveUrl = 'https://registry.npmjs.org/@example/tool/-/tool-1.2.3.tgz';

function fixtures(input = options) {
  const statement = {
    _type: 'https://in-toto.io/Statement/v1', predicateType: slsa,
    subject: [{ name: `pkg:npm/${input.name.replaceAll('@', '%40')}@${input.version}`, digest: { sha512: Buffer.from(input.integrity.slice(7), 'base64').toString('hex') } }],
  };
  return {
    metadata: { name: input.name, version: input.version, dist: { integrity: input.integrity, tarball: archiveUrl, attestations: { url, provenance: { predicateType: slsa } } } },
    install: { name: input.name, 'dist-tags': { latest: input.version }, versions: {
      [input.version]: { version: input.version, dist: { integrity: input.integrity, tarball: archiveUrl } },
    } },
    tags: { latest: input.version },
    // Structural fixture only. The consumer's signature verification is separate.
    attestations: { attestations: [{ predicateType: slsa, bundle: {
      verificationMaterial: { certificate: { rawBytes: 'AA==' } },
      dsseEnvelope: { payloadType: 'application/vnd.in-toto+json', payload: Buffer.from(JSON.stringify(statement)).toString('base64'), signatures: [{ sig: 'AA==' }] },
    } }] },
  };
}

function json(value, status = 200, headers = {}) {
  return new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json', ...headers } });
}

function harness(mutate = () => {}, respond) {
  let clock = 0;
  const calls = [];
  const waits = [];
  const messages = [];
  const data = fixtures();
  mutate(data);
  let attempt = 0;
  const dependencies = {
    now: () => clock,
    sleep: async ms => { waits.push(ms); clock += ms; },
    log: message => messages.push(message),
    fetch: async (requestUrl, requestOptions) => {
      const key = requestOptions.method === 'HEAD' ? 'archive' : requestUrl.includes('/-/npm/v1/attestations/') ? 'attestations'
        : requestUrl.endsWith('/dist-tags') ? 'tags' : requestUrl.endsWith(`/${options.name.replaceAll('/', '%2f')}`) ? 'install' : 'metadata';
      if (key === 'metadata') attempt += 1;
      calls.push({ url: requestUrl, options: requestOptions });
      return respond?.({ key, attempt, data, advance: ms => { clock += ms; } })
        ?? (key === 'archive' ? new Response(null) : json(data[key]));
    },
  };
  return { dependencies, calls, waits, messages, data };
}

test('matching scoped version, tag and provenance return exact evidence without waiting', async () => {
  const h = harness();
  assert.deepEqual(await waitForNpm(options, h.dependencies), { version: '1.2.3', integrity, attestationUrl: url, attempts: 1 });
  assert.equal(h.calls.length, 5);
  assert.deepEqual(h.calls.map(call => call.url), [
    'https://registry.npmjs.org/@example%2ftool/1.2.3',
    'https://registry.npmjs.org/@example%2ftool',
    'https://registry.npmjs.org/-/package/@example%2ftool/dist-tags', url, archiveUrl,
  ]);
  assert.equal(h.calls[1].options.headers.Accept, 'application/vnd.npm.install-v1+json');
  assert.equal(h.calls.at(-1).options.method, 'HEAD');
  assert.deepEqual(h.waits, []);
  for (const call of h.calls) {
    assert.equal(new URL(call.url).origin, 'https://registry.npmjs.org');
    assert.equal(call.options.redirect, 'manual');
    assert.equal(call.options.credentials, 'omit');
    assert.equal(call.options.cache, 'no-store');
    assert.match(call.options.headers['Cache-Control'], /no-cache/u);
    assert.equal(Object.keys(call.options.headers).some(key => /authorization/iu.test(key)), false);
    assert.ok(call.options.signal instanceof AbortSignal);
  }
});

test('404, missing metadata, and stale tags retry before success', async () => {
  const h = harness(() => {}, ({ key, attempt, data }) => {
    if (attempt === 1) return json({}, 404);
    if (attempt === 2 && key === 'metadata') return json({ ...data.metadata, dist: { integrity } });
    if (attempt === 3 && key === 'tags') return json({ latest: '1.2.2' });
  });
  const result = await waitForNpm({ ...options, timeoutMs: 5_000 }, h.dependencies);
  assert.equal(result.attempts, 4);
  assert.deepEqual(h.waits, [1_000, 1_000, 1_000]);
});

for (const status of [408, 425, 429, 500, 503]) {
  test(`HTTP ${status} remains bounded and respects Retry-After`, async () => {
    const h = harness(() => {}, () => json({}, status, { 'retry-after': '600' }));
    await assert.rejects(waitForNpm(options, h.dependencies), /timed out.*1 attempts/u);
    assert.deepEqual(h.waits, [3_000]);
    assert.equal(h.calls.length, 1);
  });
}

for (const status of [301, 302, 401, 403]) {
  test(`HTTP ${status} fails without retry or following a location`, async () => {
    const h = harness(() => {}, () => json({}, status, { location: 'https://other.example/private' }));
    await assert.rejects(waitForNpm(options, h.dependencies), /unexpected HTTP/u);
    assert.equal(h.calls.length, 1);
    assert.deepEqual(h.waits, []);
  });
}

test('a network failure retries until the total deadline', async () => {
  const h = harness();
  h.dependencies.fetch = async () => { throw new Error('network down'); };
  await assert.rejects(waitForNpm(options, h.dependencies), /timed out.*3 attempts/u);
  assert.deepEqual(h.waits, [1_000, 1_000, 1_000]);
});

test('HTTP time is part of the total deadline and cannot yield late success', async () => {
  const h = harness(() => {}, ({ key, advance }) => { if (key === 'attestations') advance(3_001); });
  await assert.rejects(waitForNpm(options, h.dependencies), /timed out/u);
  assert.equal(h.calls.length, 4);
  assert.deepEqual(h.waits, []);
});

test('a stalled HTTP body is aborted within the total deadline', async () => {
  const keepAlive = setInterval(() => {}, 1_000);
  try {
    await assert.rejects(waitForNpm({ ...options, timeoutMs: 20 }, {
      fetch: async (_url, { signal }) => new Response(new ReadableStream({
        start(controller) { signal.addEventListener('abort', () => controller.error(signal.reason), { once: true }); },
      }), { headers: { 'content-type': 'application/json' } }),
    }), /timed out/u);
  } finally {
    clearInterval(keepAlive);
  }
});

test('a different immutable archive fails immediately', async () => {
  const h = harness(data => { data.metadata.dist.integrity = `sha512-${Buffer.alloc(64, 9).toString('base64')}`; });
  await assert.rejects(waitForNpm(options, h.dependencies), /different archive bytes/u);
  assert.equal(h.calls.length, 1);
  assert.deepEqual(h.waits, []);
});

for (const field of ['name', 'version']) {
  test(`a wrong metadata ${field} cannot be accepted`, async () => {
    const h = harness(data => { data.metadata[field] = 'wrong'; });
    await assert.rejects(waitForNpm(options, h.dependencies), /does not identify the requested package/u);
    assert.equal(h.calls.length, 1);
  });
}

for (const target of [
  'http://registry.npmjs.org/-/npm/v1/attestations/@example%2ftool@1.2.3',
  'https://registry.npmjs.org.evil.example/-/npm/v1/attestations/@example%2ftool@1.2.3',
  'https://token@registry.npmjs.org/-/npm/v1/attestations/@example%2ftool@1.2.3',
  `${url}?token=secret`, `${url}#fragment`, url.replace('1.2.3', '9.9.9'),
]) {
  test(`an unsafe attestation URL is rejected: ${target}`, async () => {
    const h = harness(data => { data.metadata.dist.attestations.url = target; });
    await assert.rejects(waitForNpm(options, h.dependencies), /attestation URL/u);
    assert.equal(h.calls.length, 1);
  });
}

test('missing provenance cannot pass with a publish-only attestation', async () => {
  const h = harness(data => { data.attestations.attestations[0].predicateType = 'publish'; });
  await assert.rejects(waitForNpm(options, h.dependencies), /timed out.*SLSA provenance/u);
});

for (const corruption of ['subject', 'digest', 'predicate', 'signature', 'payload']) {
  test(`provenance with a wrong ${corruption} fails`, async () => {
    const h = harness(data => {
      const envelope = data.attestations.attestations[0].bundle.dsseEnvelope;
      const statement = JSON.parse(Buffer.from(envelope.payload, 'base64'));
      if (corruption === 'subject') statement.subject[0].name = 'pkg:npm/other@1.2.3';
      if (corruption === 'digest') statement.subject[0].digest.sha512 = '0'.repeat(128);
      if (corruption === 'predicate') statement.predicateType = 'other';
      if (corruption === 'signature') envelope.signatures = [];
      envelope.payload = corruption === 'payload' ? 'not base64!' : Buffer.from(JSON.stringify(statement)).toString('base64');
    });
    await assert.rejects(waitForNpm(options, h.dependencies), /provenance (subject|envelope)/u);
    assert.deepEqual(h.waits, []);
  });
}

test('HTML, invalid JSON, and oversized bodies fail without poll loops', async () => {
  for (const response of [
    new Response('<html>oops</html>', { headers: { 'content-type': 'text/html' } }),
    new Response('{', { headers: { 'content-type': 'application/json' } }),
    new Response(' '.repeat(1_048_577), { headers: { 'content-type': 'application/json' } }),
  ]) {
    const h = harness(() => {}, () => response);
    await assert.rejects(waitForNpm(options, h.dependencies));
    assert.equal(h.calls.length, 1);
    assert.deepEqual(h.waits, []);
  }
});

test('invalid request inputs cannot reach the network', async () => {
  for (const override of [
    { name: '../other' }, { name: '@scope/../../other' }, { name: 'https://other.example' }, { name: 'name\ncommand' },
    { version: 'latest' }, { version: 'v1.2.3' }, { version: '01.2.3' }, { version: '1.2.3-01' }, { version: '1.2.3+build.2' },
    { integrity: 'sha512-AA==' }, { integrity: `${integrity} sha256-AA==` }, { tag: '../latest' },
    { timeoutMs: 1_200_001 }, { timeoutMs: Number.NaN }, { pollMs: 0 },
  ]) {
    const h = harness();
    await assert.rejects(waitForNpm({ ...options, ...override }, h.dependencies));
    assert.deepEqual(h.calls, []);
  }
  assert.equal(validateOptions({ ...options, version: '1.2.3-rc.1' }).version, '1.2.3-rc.1');
});

test('custom tags are checked instead of latest', async () => {
  const h = harness(data => { data.tags = { beta: '1.2.3', latest: '1.1.0' }; data.install['dist-tags'] = data.tags; });
  assert.equal((await waitForNpm({ ...options, tag: 'beta' }, h.dependencies)).attempts, 1);
});

for (const field of ['versions', 'dist-tags']) {
  test(`stale npm install ${field} prevents early success`, async () => {
    const h = harness(() => {}, ({ key, attempt, data }) => {
      if (key === 'install' && attempt === 1) return json({ ...data.install, [field]: {} });
    });
    assert.equal((await waitForNpm(options, h.dependencies)).attempts, 2);
    assert.deepEqual(h.waits, [1_000]);
  });
}

test('conflicting npm install integrity fails before an archive is used', async () => {
  const h = harness(data => { data.install.versions['1.2.3'].dist.integrity = `sha512-${Buffer.alloc(64, 9).toString('base64')}`; });
  await assert.rejects(waitForNpm(options, h.dependencies), /install metadata identifies different archive bytes/u);
  assert.deepEqual(h.waits, []);
  assert.equal(h.calls.some(call => call.options.method === 'HEAD'), false);
});

test('malformed install versions fail immediately instead of consuming the poll budget', async () => {
  for (const value of [null, 0, 'pending', []]) {
    const h = harness(data => { data.install.versions['1.2.3'] = value; });
    await assert.rejects(waitForNpm(options, h.dependencies), /install version is malformed/u);
    assert.deepEqual(h.waits, []);
  }
});

for (const document of ['metadata', 'install']) {
  test(`unsafe archive URLs in ${document} cannot be requested`, async () => {
    const h = harness(data => {
      const target = document === 'metadata' ? data.metadata : data.install.versions['1.2.3'];
      target.dist.tarball = 'https://other.example/archive.tgz';
    });
    await assert.rejects(waitForNpm(options, h.dependencies), /tarball URL/u);
    assert.equal(h.calls.some(call => new URL(call.url).origin !== 'https://registry.npmjs.org'), false);
    assert.equal(h.calls.some(call => call.options.method === 'HEAD'), false);
  });
}

for (const endpoint of ['tags', 'attestations', 'archive']) {
  test(`missing ${endpoint} retries even when version metadata is ready`, async () => {
    const h = harness(() => {}, ({ key, attempt }) => {
      if (key === endpoint && attempt === 1) return new Response(null, { status: 404 });
    });
    assert.equal((await waitForNpm(options, h.dependencies)).attempts, 2);
    assert.deepEqual(h.waits, [1_000]);
  });
}

test('a connection reset during a body read retries within the deadline', async () => {
  const h = harness(() => {}, ({ key, attempt }) => {
    if (key === 'metadata' && attempt === 1) return new Response(new ReadableStream({
      start(controller) { controller.error(new TypeError('terminated')); },
    }), { headers: { 'content-type': 'application/json' } });
  });
  assert.equal((await waitForNpm(options, h.dependencies)).attempts, 2);
  assert.deepEqual(h.waits, [1_000]);
});

test('an HTTP-date Retry-After remains capped by the total deadline', async () => {
  const future = new Date(Date.now() + 600_000).toUTCString();
  const h = harness(() => {}, () => json({}, 429, { 'retry-after': future }));
  await assert.rejects(waitForNpm(options, h.dependencies), /timed out/u);
  assert.deepEqual(h.waits, [3_000]);
});

test('install metadata uses its vendor media type and separate larger bound', async () => {
  const h = harness(data => { data.install.padding = 'x'.repeat(1_048_577); }, ({ key, data }) => {
    if (key === 'install') return json(data.install, 200, { 'content-type': 'application/vnd.npm.install-v1+json' });
  });
  assert.equal((await waitForNpm(options, h.dependencies)).attempts, 1);
  const tooLarge = harness(() => {}, ({ key }) => {
    if (key === 'install') return new Response(new Uint8Array(32 * 1_048_576 + 1), { headers: { 'content-type': 'application/json' } });
  });
  await assert.rejects(waitForNpm(options, tooLarge.dependencies), /exceeds 32 MiB/u);
  assert.deepEqual(tooLarge.waits, []);
});

test('one valid provenance statement cannot hide a conflicting second one', async () => {
  const h = harness(data => { data.attestations.attestations.push({ predicateType: slsa, bundle: {} }); });
  await assert.rejects(waitForNpm(options, h.dependencies), /provenance envelope/u);
  assert.deepEqual(h.waits, []);
});

test('an inherited tag name cannot match a version', async () => {
  const h = harness();
  await assert.rejects(waitForNpm({ ...options, tag: 'constructor' }, h.dependencies), /timed out/u);
});

test('action inputs produce outputs only after complete matching evidence', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'npm-visible-test-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const output = join(directory, 'output');
  await writeFile(output, 'previous=kept\n');
  const h = harness();
  t.mock.method(globalThis, 'fetch', h.dependencies.fetch);
  t.mock.method(console, 'log', () => {});
  const environment = { INPUT_PACKAGE: options.name, INPUT_VERSION: options.version, INPUT_INTEGRITY: integrity,
    'INPUT_TIMEOUT-SECONDS': '1', 'INPUT_POLL-INTERVAL-SECONDS': '1', GITHUB_OUTPUT: output };
  await runAction(environment);
  const expected = `previous=kept\nversion=1.2.3\nintegrity=${integrity}\nattestation-url=${url}\n`;
  assert.equal(await readFile(output, 'utf8'), expected);
  await assert.rejects(runAction({ ...environment, INPUT_INTEGRITY: `sha512-${Buffer.alloc(64, 9).toString('base64')}` }), /different archive bytes/u);
  await assert.rejects(runAction({ ...environment, 'INPUT_TIMEOUT-SECONDS': '1e3' }), /seconds input/u);
  assert.equal(await readFile(output, 'utf8'), expected);
});
