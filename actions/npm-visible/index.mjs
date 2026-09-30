import { appendFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';

const registry = 'https://registry.npmjs.org';
const slsa = 'https://slsa.dev/provenance/v1';
const maximumBodyBytes = 1_048_576;
const versionPattern = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/u;

class Pending extends Error {
  constructor(message, retryAfterMs = 0) {
    super(message);
    this.retryAfterMs = retryAfterMs;
  }
}

function object(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function canonicalBase64(value) {
  return typeof value === 'string' && value.length > 0
    && Buffer.from(value, 'base64').toString('base64') === value;
}

export function validateOptions(options) {
  const { name, version, integrity, tag = 'latest', timeoutMs = 1_200_000, pollMs = 5_000 } = options;
  if (typeof name !== 'string' || name.length > 214
    || !/^(?:@[a-z0-9][a-z0-9._-]*\/)?[a-z0-9][a-z0-9._-]*$/u.test(name)) {
    throw new Error('package must be a lowercase public npm package name');
  }
  if (typeof version !== 'string' || version.length > 128 || !versionPattern.test(version)) {
    throw new Error('version must be an exact canonical semantic version');
  }
  const digest = typeof integrity === 'string' && integrity.startsWith('sha512-') ? integrity.slice(7) : '';
  if (!canonicalBase64(digest) || Buffer.from(digest, 'base64').length !== 64) {
    throw new Error('integrity must be one canonical sha512 SRI from the retained archive');
  }
  if (typeof tag !== 'string' || !/^[A-Za-z][A-Za-z0-9._-]{0,63}$/u.test(tag)) {
    throw new Error('tag must start with a letter and contain at most 64 letters, digits, dots, underscores, or hyphens');
  }
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 1_200_000
    || !Number.isSafeInteger(pollMs) || pollMs < 1_000 || pollMs > 60_000) {
    throw new Error('timeout must be at most 20 minutes and the poll interval must be 1 through 60 seconds');
  }
  return { name, version, integrity, tag, timeoutMs, pollMs };
}

async function boundedJson(response) {
  if (!/^application\/json(?:\s*;|$)/iu.test(response.headers.get('content-type') ?? '')) {
    await response.body?.cancel();
    throw new Error('registry response is not JSON');
  }
  if (!response.body) throw new Error('registry response has no body');
  const reader = response.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maximumBodyBytes) {
        await reader.cancel();
        throw new Error('registry response exceeds 1 MiB');
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const text = new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks));
  return JSON.parse(text);
}

async function requestJson(url, { fetch, now, deadline }) {
  const remaining = Math.ceil(deadline - now());
  if (remaining <= 0) throw new Pending('registry deadline reached');
  const signal = AbortSignal.timeout(Math.min(20_000, remaining));
  let response;
  try {
    response = await fetch(url, {
      cache: 'no-store', redirect: 'manual', credentials: 'omit', signal,
      headers: { Accept: 'application/json', 'Cache-Control': 'no-cache, no-store', Pragma: 'no-cache' },
    });
  } catch {
    throw new Pending('registry request failed or timed out');
  }
  if (response.status !== 200) {
    const retry = response.headers.get('retry-after') ?? '';
    const retryAfterMs = /^\d+$/u.test(retry) ? Math.min(Number(retry) * 1_000, 1_200_000)
      : Math.min(Math.max(0, Date.parse(retry) - Date.now()) || 0, 1_200_000);
    await response.body?.cancel();
    if ([404, 408, 425, 429].includes(response.status) || response.status >= 500) {
      throw new Pending(`registry returned HTTP ${response.status}`, retryAfterMs);
    }
    throw new Error(`registry returned unexpected HTTP ${response.status}; redirects and authentication are unsupported`);
  }
  try {
    return await boundedJson(response);
  } catch (error) {
    if (signal.aborted) throw new Pending('registry body timed out');
    throw error;
  }
}

function attestationUrl(value, name, version) {
  if (typeof value !== 'string' || value.length > 1_024) throw new Error('registry attestation URL is invalid');
  const url = new URL(value);
  if (url.origin !== registry || url.username || url.password || url.search || url.hash
    || decodeURIComponent(url.pathname) !== `/-/npm/v1/attestations/${name}@${version}`) {
    throw new Error('registry attestation URL does not identify the exact package at registry.npmjs.org');
  }
  return url.href;
}

function matchingProvenance(document, { name, version, integrity }) {
  if (!object(document) || !Array.isArray(document.attestations)) throw new Error('registry attestations are malformed');
  const attestations = document.attestations.filter(item => object(item) && item.predicateType === slsa);
  if (attestations.length === 0) throw new Pending('SLSA provenance is not visible');
  const expectedDigest = Buffer.from(integrity.slice(7), 'base64').toString('hex');
  for (const attestation of attestations) {
    const bundle = attestation.bundle;
    const envelope = bundle?.dsseEnvelope;
    if (!object(bundle?.verificationMaterial) || envelope?.payloadType !== 'application/vnd.in-toto+json'
      || !canonicalBase64(envelope.payload) || !Array.isArray(envelope.signatures)
      || !envelope.signatures.some(signature => canonicalBase64(signature?.sig))) {
      throw new Error('registry provenance envelope is incomplete');
    }
    const statement = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.from(envelope.payload, 'base64')));
    const subjects = statement?.subject;
    if (statement?._type !== 'https://in-toto.io/Statement/v1' || statement.predicateType !== slsa
      || !Array.isArray(subjects) || subjects.length !== 1 || typeof subjects[0]?.name !== 'string'
      || decodeURIComponent(subjects[0].name) !== `pkg:npm/${name}@${version}`
      || subjects[0]?.digest?.sha512 !== expectedDigest) {
      throw new Error('registry provenance subject does not identify the expected package archive');
    }
  }
}

async function observe(options, dependencies) {
  const { name, version, integrity, tag } = options;
  const encodedName = encodeURIComponent(name);
  const metadata = await requestJson(`${registry}/${encodedName}/${encodeURIComponent(version)}`, dependencies);
  if (!object(metadata) || metadata.name !== name || metadata.version !== version) {
    throw new Error('registry version response does not identify the requested package');
  }
  if (!metadata.dist?.integrity) throw new Pending('archive integrity is not visible');
  if (metadata.dist.integrity !== integrity) throw new Error('published version has different archive bytes; do not overwrite it');
  const descriptor = metadata.dist.attestations;
  if (!descriptor?.url || !descriptor.provenance) throw new Pending('provenance metadata is not visible');
  if (descriptor.provenance.predicateType !== slsa) throw new Error('registry provenance predicate is unsupported');
  const url = attestationUrl(descriptor.url, name, version);
  const tags = await requestJson(`${registry}/-/package/${encodedName}/dist-tags`, dependencies);
  if (!object(tags)) throw new Error('registry distribution tags are malformed');
  if (tags[tag] !== version) throw new Pending(`distribution tag ${tag} does not yet identify ${version}`);
  matchingProvenance(await requestJson(url, dependencies), options);
  if (dependencies.now() >= dependencies.deadline) throw new Pending('registry deadline reached');
  return { version, integrity, attestationUrl: url };
}

export async function waitForNpm(options, dependencies = {}) {
  const checked = validateOptions(options);
  const { fetch = globalThis.fetch, now = () => performance.now(), sleep = delay, log = () => {} } = dependencies;
  const deadline = now() + checked.timeoutMs;
  let attempts = 0;
  let reason = 'registry deadline reached';
  while (now() < deadline) {
    attempts += 1;
    let retryAfterMs = 0;
    try {
      return { ...await observe(checked, { fetch, now, deadline }), attempts };
    } catch (error) {
      if (!(error instanceof Pending)) throw error;
      reason = error.message;
      retryAfterMs = error.retryAfterMs;
      log(`Attempt ${attempts}: ${reason}`);
    }
    const remaining = deadline - now();
    if (remaining <= 0) break;
    await sleep(Math.min(Math.max(checked.pollMs, retryAfterMs), remaining));
  }
  throw new Error(`npm visibility timed out after ${checked.timeoutMs / 1_000}s (${attempts} attempts): ${reason}`);
}

function seconds(value, fallback, maximum) {
  const text = value === undefined || value === '' ? fallback : value;
  if (!/^[1-9]\d*$/u.test(text) || Number(text) > maximum) throw new Error(`seconds input must be an integer from 1 through ${maximum}`);
  return Number(text) * 1_000;
}

export async function runAction(environment = process.env) {
  const result = await waitForNpm({
    name: environment.INPUT_PACKAGE, version: environment.INPUT_VERSION, integrity: environment.INPUT_INTEGRITY,
    tag: environment.INPUT_TAG || 'latest',
    timeoutMs: seconds(environment['INPUT_TIMEOUT-SECONDS'], '1200', 1_200),
    pollMs: seconds(environment['INPUT_POLL-INTERVAL-SECONDS'], '5', 60),
  }, { log: console.log });
  if (environment.GITHUB_OUTPUT) {
    await appendFile(environment.GITHUB_OUTPUT,
      `version=${result.version}\nintegrity=${result.integrity}\nattestation-url=${result.attestationUrl}\n`, 'utf8');
  }
  console.log(`${environment.INPUT_PACKAGE}@${result.version} is visible with matching integrity, tag, and provenance subject (${result.attempts} attempts)`);
  return result;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  runAction().catch(error => {
    console.error(`npm-visible: ${error.message}`);
    process.exitCode = 1;
  });
}
