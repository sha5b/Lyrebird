/**
 * Starts the local pipeline control surface alongside `vite dev`.
 *
 * The running app still needs no backend — the galaxy is precomputed and everything
 * audible is synthesised in the browser (`docs/06-architecture.md` §6.1). This only
 * covers the Learn tab, which drives the offline Python pipeline and therefore needs
 * `birdy-pipeline serve` alive somewhere. Asking for a second terminal to run one
 * fixed command is a step that can be taken for you, so it is.
 *
 * The rules it keeps:
 *
 * - **Never two of them.** If something already answers on the port, that process is
 *   left alone and nothing is spawned — a hand-started server with its own flags wins.
 * - **Never fatal.** No `uv`, no Python, a crash on startup: dev keeps serving and the
 *   Learn tab falls back to telling you how to start it yourself.
 * - **Dies with the dev server.** The child is killed when Vite closes, so a stale
 *   server is not left holding the port after ctrl-c.
 *
 * Off with `BIRDY_PIPELINE=0`; another port with `BIRDY_PIPELINE_PORT`.
 */

import { spawn, type ChildProcess } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import type { Plugin } from 'vite';

const PIPELINE_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'pipeline');
const DEFAULT_PORT = 8781;
const START_TIMEOUT_MS = 20_000;

/**
 * Ceiling on the "is one already up?" probe.
 *
 * **600 ms was too tight, and being too tight here is not a slow probe but a wrong answer.**
 * The status endpoint used to rebuild the harvest store per request, so on a 40 000-syllable
 * store it answered in ~1.3 s: every probe timed out, the plugin concluded the port was free,
 * and it spawned a second server that could not bind. The server side is fixed, but the
 * margin belongs here too — this decides whether a *healthy* server is seen, and the cost of
 * being generous is a few hundred milliseconds of dev startup on the one path where nothing
 * is listening (which fails fast anyway, by connection refused rather than by timeout).
 *
 * Matches `REQUEST_TIMEOUT_MS` in `src/lib/data/pipeline.ts`: the client and this should not
 * disagree about how long a status call may take.
 */
const PROBE_TIMEOUT_MS = 4000;

/** True when something already answers `/api/status` on the port. */
async function alreadyServing(port: number): Promise<boolean> {
	try {
		const res = await fetch(`http://127.0.0.1:${port}/api/status`, {
			signal: AbortSignal.timeout(PROBE_TIMEOUT_MS)
		});
		return res.ok;
	} catch {
		return false;
	}
}

/**
 * True when the port accepts a connection but does not answer in time.
 *
 * **"Nothing is listening" and "something is listening but wedged" need different messages,
 * and `alreadyServing` returns false for both.** That conflation produced a genuinely
 * baffling session: a `serve` left over from an earlier editor window sat suspended (state
 * `T`), holding the socket. `alreadyServing` timed out, so this plugin concluded the port was
 * free and spawned a replacement — which died on `EADDRINUSE`, because the suspended process
 * still had it. The result was an interface reporting the pipeline as absent and a terminal
 * reporting the address as taken, with nothing connecting the two.
 *
 * The distinction is cheap to make: the kernel completes the TCP handshake from the listen
 * backlog whether or not the process is alive enough to read from it, so a raw connect
 * succeeding while the HTTP request times out is exactly the wedged case.
 */
async function portIsSilent(port: number): Promise<boolean> {
	const socket = await import('node:net');
	return new Promise((resolve) => {
		const probe = socket.createConnection({ host: '127.0.0.1', port });
		const done = (answer: boolean) => {
			probe.destroy();
			resolve(answer);
		};
		probe.setTimeout(PROBE_TIMEOUT_MS);
		probe.once('connect', () => done(true)); // connectable, yet /api/status did not reply
		probe.once('error', () => done(false)); // refused: genuinely nothing there
		probe.once('timeout', () => done(false));
	});
}

export function birdyPipeline(): Plugin {
	const port = Number(process.env.BIRDY_PIPELINE_PORT || DEFAULT_PORT);
	let child: ChildProcess | null = null;
	let stopping = false;

	function stop() {
		stopping = true;
		if (child && child.exitCode === null) child.kill('SIGTERM');
		child = null;
	}

	return {
		name: 'birdy-pipeline',
		apply: 'serve',

		async configureServer(server) {
			const info = (msg: string) => server.config.logger.info(`  \x1b[2mpipeline\x1b[0m  ${msg}`);
			const warn = (msg: string) => server.config.logger.warn(`  pipeline  ${msg}`);

			if (process.env.BIRDY_PIPELINE === '0') return;
			// `closeBundle` covers a clean `server.close()`; this covers the rest.
			process.once('exit', stop);
			server.httpServer?.once('close', stop);

			if (await alreadyServing(port)) {
				info(`already running on 127.0.0.1:${port}, leaving it alone`);
				return;
			}

			// Spawning into an occupied port cannot succeed, so say what is wrong instead of
			// producing a second, more confusing failure. See `portIsSilent`.
			if (await portIsSilent(port)) {
				warn(
					`127.0.0.1:${port} is held by a process that accepts connections but never ` +
						`answers — most likely a suspended or wedged \`birdy-pipeline serve\` from an ` +
						`earlier session. The Learn tab will show the pipeline as not running until ` +
						`it is cleared.`
				);
				warn(
					`  find it with:  ss -tlnp | grep ${port}      ` +
						`then:  kill -CONT <pid> && kill <pid>`
				);
				warn(`  or set BIRDY_PIPELINE_PORT to use a different port.`);
				return;
			}

			// `uv run` resolves the pipeline's own virtualenv, so this works from a clean
			// checkout without anything activated. stdin is closed: it must never be able
			// to steal the terminal from Vite.
			child = spawn('uv', ['run', 'birdy-pipeline', 'serve', '--port', String(port)], {
				cwd: PIPELINE_DIR,
				stdio: ['ignore', 'pipe', 'pipe'],
				env: process.env
			});

			// Its own log is the only progress a harvest run has, so it is forwarded rather
			// than swallowed — but only once a job is actually running. Startup chatter and
			// the numba warm-up would otherwise bury Vite's own output.
			let quiet = true;
			const forward = (buf: Buffer) => {
				for (const line of buf.toString().split('\n')) {
					const text = line.trim();
					if (!text) continue;
					if (quiet && !/^(harvesting|fitting|building|wrote|skip|XC)/.test(text)) continue;
					quiet = false;
					info(text);
				}
			};
			child.stdout?.on('data', forward);
			child.stderr?.on('data', forward);

			child.on('error', (err: NodeJS.ErrnoException) => {
				child = null;
				warn(
					err.code === 'ENOENT'
						? `uv is not on PATH, so the Learn tab has no backend. Install uv, or run ` +
							`\`cd pipeline && uv run birdy-pipeline serve\` yourself.`
						: `could not start: ${err.message}`
				);
			});
			child.on('exit', (code) => {
				if (stopping || code === 0) return;
				warn(`exited with code ${code}. Run \`cd pipeline && uv run birdy-pipeline serve\` to see why.`);
				child = null;
			});

			// Report the port only once it really answers. The first start compiles the
			// numba kernels in `syrinx.py`, which takes a few seconds.
			const deadline = Date.now() + START_TIMEOUT_MS;
			while (child && Date.now() < deadline) {
				if (await alreadyServing(port)) {
					info(`control surface on http://127.0.0.1:${port} (loopback only)`);
					return;
				}
				await new Promise((r) => setTimeout(r, 400));
			}
			if (child) warn(`did not answer on 127.0.0.1:${port} within ${START_TIMEOUT_MS / 1000}s`);
		},

		buildEnd: stop,
		closeBundle: stop
	};
}
