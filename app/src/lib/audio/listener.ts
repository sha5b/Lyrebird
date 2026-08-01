import { PitchDetector } from 'pitchy';
import {
	ActivationTracker,
	FeatureExtractor,
	PointTracker,
	SessionGate,
	standardise
} from './features.ts';
import { readActivations, type Reading } from '$lib/lang/translate';
import { createSignal, MAX_PATHS, unmatchedCluster, type LivePath, type VisualSignal } from '$lib/galaxy/shaders';
import type { BirdyAssets } from '$lib/data/types';
import type { BirdyEngine } from './engine';

/** A path with nothing scheduled behind it fades to this and stays as a faint thread. */
const IDLE_ALPHA = 0.4;
/** A finished live path is removed once it has faded this far. */
const GONE_ALPHA = 0.02;

/**
 * The live loop: analysis bus -> 28-d descriptor -> cluster activations -> per-point
 * response + galaxy uniforms + translation readout. Everything here is cheap enough to
 * run per frame (docs/05-embedding-galaxy.md §5.3); the only ML-shaped step is a
 * nearest-centroid lookup, which is why no model has to run in the browser.
 */
export class Listener {
	readonly signal: VisualSignal;
	readonly extractor: FeatureExtractor;
	private readonly tracker: ActivationTracker;
	private readonly points: PointTracker;
	private readonly pitch: PitchDetector<Float32Array>;
	private raf = 0;
	private lastReading = 0;
	private onsetTimes: number[] = [];
	private wasActive = false;

	/**
	 * The selected-but-unplayed call, drawn as a static thread. Held separately from the
	 * live paths so that starting a chorus does not erase it and finishing a song does
	 * not fade it away.
	 */
	private preview: LivePath | null = null;
	private live: LivePath[] = [];

	/**
	 * Scheduled windows for syllables that own no cluster. An orphan type still owns
	 * points — its renders and field members have real positions — so while it sounds,
	 * those points are flashed through `signal.orphanPulse`, a channel kept separate
	 * from the cluster activations because "played, but not placed" is not a knot
	 * answering (§8.5).
	 */
	private orphanPulses: { points: number[]; start: number; end: number }[] = [];
	private orphanWasActive = false;

	reading: Reading;
	onReading: ((reading: Reading) => void) | null = null;
	/**
	 * The visual signal is mutated in place for the renderer, which reads it once per frame
	 * and needs no reactivity. Anything the UI displays has to arrive as a callback instead,
	 * or Svelte never sees the change.
	 */
	onMeters:
		| ((meters: {
				level: number;
				f0: number;
				strength: number;
				active: boolean;
				session?: { flagged: boolean; score: number; threshold: number };
		  }) => void)
		| null = null;
	private lastMeters = 0;
	/**
	 * The docs/20 session gate, or null when the assets predate it (or ship it
	 * malformed — present-but-inconsistent is treated as absent, never trusted).
	 * Fed only while the microphone is open: Birdy's own chorus crosses the same
	 * analysis bus, and a session made of corpus audio is not the thing the gate
	 * is about.
	 */
	private readonly gate: SessionGate | null;

	constructor(
		private readonly engine: BirdyEngine,
		private readonly assets: BirdyAssets
	) {
		// A browser may refuse the requested rate and hand back 44100. The mel bank and the
		// bin-to-Hz mapping must then follow the *actual* rate, or every descriptor is
		// stretched in frequency and lands in the wrong cluster. The corpus statistics were
		// computed at the corpus rate, so a mismatch still costs some accuracy — the engine
		// exposes `sampleRateMismatch` so the UI can say so.
		this.extractor = new FeatureExtractor({
			...assets.featureSpace,
			sampleRate: engine.ctx.sampleRate
		});
		this.tracker = new ActivationTracker(assets.centroids, assets.featureSpace);
		this.points = new PointTracker(assets);
		const gateSpec = assets.featureSpace.embedding?.sessionGate;
		this.gate =
			gateSpec?.anchors?.length && gateSpec.anchors[0]?.length === assets.featureSpace.dims
				? new SessionGate(gateSpec, assets.featureSpace.dims)
				: null;
		this.signal = createSignal(assets.centroids.items.length, assets.points.n);
		this.pitch = PitchDetector.forFloat32Array(assets.featureSpace.frameSize);
		this.reading = readActivations(
			assets.inventory,
			assets.centroids,
			this.signal.activations,
			this.tracker.similarity,
			{ active: false, speciesName: assets.speciesCommon }
		);
	}

	/** True when each point's response is measured rather than derived from its cluster. */
	get perPointMeasured(): boolean {
		return this.points.measured;
	}

	/** Which species to keep at full strength in the cloud; -1 shows all equally. */
	setFocus(index: number): void {
		this.signal.focus = index;
	}

	private static clean(nodes: number[], times: { start: number; end: number }[] | null) {
		const keptNodes: number[] = [];
		const keptTimes: { start: number; end: number }[] = [];
		nodes.forEach((node, i) => {
			if (node < 0) return;
			keptNodes.push(node);
			if (times?.[i]) keptTimes.push(times[i]);
		});
		return {
			nodes: keptNodes,
			times: times && keptTimes.length === keptNodes.length ? keptTimes : null
		};
	}

	private publishPaths(): void {
		this.signal.paths = (this.preview ? [this.preview, ...this.live] : [...this.live]).slice(
			0,
			MAX_PATHS
		);
		this.signal.pathsVersion++;
	}

	/**
	 * The shape of a selected call, before anything plays it: a faint static thread.
	 * Nodes the corpus does not know (index < 0) are dropped.
	 */
	setPreview(nodes: number[], speciesId = '', label = ''): void {
		const cleaned = Listener.clean(nodes, null);
		this.preview =
			cleaned.nodes.length > 1
				? {
						nodes: cleaned.nodes,
						times: null,
						progress: -1,
						alpha: IDLE_ALPHA,
						// the preview is a static thread, never animated, so it is "started"
						// in the sense that nothing is waiting to happen to it
						started: true,
						speciesId,
						label
					}
				: null;
		this.publishPaths();
	}

	clearPreview(): void {
		this.preview = null;
		this.publishPaths();
	}

	/**
	 * Adds an animated trajectory for something that is being sung right now.
	 *
	 * These accumulate: during a chorus a dozen birds overlap, and each gets its own
	 * thread with its own travelling highlight, so the picture is the whole vector field
	 * coming alive rather than one line being rewritten by whoever sang last. The oldest
	 * is dropped once there are more than the renderer can draw.
	 */
	addLive(
		nodes: number[],
		times: { start: number; end: number }[],
		speciesId = '',
		label = ''
	): void {
		const cleaned = Listener.clean(nodes, times);
		if (cleaned.nodes.length < 2) return;
		this.live.push({
			nodes: cleaned.nodes,
			times: cleaned.times,
			progress: -1,
			// invisible until the first note sounds; `advancePaths` raises it
			alpha: 0,
			started: false,
			speciesId,
			label
		});
		// one slot is reserved for the preview
		while (this.live.length > MAX_PATHS - 1) this.live.shift();
		this.publishPaths();
	}

	/**
	 * Flash the points of a syllable that is being played but owns no cluster.
	 *
	 * Times are AudioContext times, exactly as for `addLive` — the chorus schedules
	 * ahead, and a pulse must not show before its note sounds. Held at full strength
	 * through the note and released over ~0.6 s afterwards, mirroring how a finished
	 * trajectory fades rather than cutting.
	 */
	addOrphanPulse(points: number[], window: { start: number; end: number }): void {
		if (!points.length) return;
		this.orphanPulses.push({ points, start: window.start, end: window.end });
		// A chorus queues songs many seconds out; cap the backlog the way paths are capped.
		while (this.orphanPulses.length > 64) this.orphanPulses.shift();
	}

	/**
	 * True while a scheduled orphan note is actually sounding (inside its window, not
	 * the release tail). This is the gate for the no-positional-effects rule above:
	 * the note is known to be playing and known to have no knot.
	 */
	private orphanSounding(): boolean {
		const now = this.engine.ctx.currentTime;
		return this.orphanPulses.some((p) => now >= p.start && now <= p.end);
	}

	/** Writes the current orphan envelopes into the signal buffer the renderer reads. */
	private stepOrphans(): void {
		const out = this.signal.orphanPulse;
		if (!this.orphanPulses.length) {
			if (this.orphanWasActive) {
				out.fill(0);
				this.orphanWasActive = false;
			}
			return;
		}
		const now = this.engine.ctx.currentTime;
		out.fill(0);
		const kept: typeof this.orphanPulses = [];
		for (const p of this.orphanPulses) {
			if (now < p.end + 0.6) kept.push(p);
			const v = now < p.start ? 0 : now <= p.end ? 1 : Math.max(0, 1 - (now - p.end) / 0.6);
			if (v <= 0) continue;
			for (const i of p.points) {
				if (i < out.length && v > out[i]) out[i] = v;
			}
		}
		this.orphanPulses = kept;
		this.orphanWasActive = true;
	}

	/** The faint backdrop of every song this bird sings; drops nodes the corpus lacks. */
	setContext(paths: number[][]): void {
		this.signal.context = paths.map((p) => p.filter((n) => n >= 0)).filter((p) => p.length > 1);
		this.signal.contextVersion++;
	}

	/**
	 * Retire every thread, letting them fade rather than cutting them.
	 *
	 * Switching bird, changing the chorus or rearranging the cloud all end up here, and
	 * dropping the array outright made a dozen lines vanish between two frames — which
	 * reads as a glitch rather than as a change. Marking them finished hands them to the
	 * same decay a phrase gets when it stops being sung, so they thin out over about a
	 * second and `advancePaths` collects them.
	 */
	clearPaths(): void {
		this.preview = null;
		this.orphanPulses = [];
		for (const path of this.live) {
			path.progress = -1;
			path.started = true;
			path.times = null;
		}
		this.publishPaths();
	}

	/**
	 * Position along one path right now, in node units, or -1 when it is not sounding.
	 * Between two syllables it keeps moving through the gap so the highlight travels along
	 * the connecting line instead of jumping.
	 *
	 * A path that has not started yet reports -1, not 0. The ambient chorus draws
	 * exponential inter-arrival times, so it queues songs many seconds — sometimes half a
	 * minute — ahead of the clock. Reporting position 0 for all of that wait lit the
	 * phrase's *first* cluster at full strength while nothing was playing, and held it
	 * there until the note finally sounded. That was the node that appeared stuck.
	 */
	private advance(path: LivePath, now: number): number {
		const times = path.times;
		if (!times || !times.length) return -1;
		if (now < times[0].start) return -1;
		const last = times[times.length - 1];
		if (now > last.end + 0.25) {
			path.times = null;
			return -1;
		}
		for (let i = 0; i < times.length; i++) {
			const { start, end } = times[i];
			if (now <= end) {
				if (now >= start) return i + (now - start) / Math.max(1e-4, end - start);
				const prevEnd = times[i - 1]?.end ?? start;
				const gap = Math.max(1e-4, start - prevEnd);
				return i - 1 + Math.min(1, (now - prevEnd) / gap);
			}
		}
		return times.length - 1;
	}

	start(): void {
		if (this.raf) return;
		const tick = () => {
			this.raf = requestAnimationFrame(tick);
			this.step();
		};
		this.raf = requestAnimationFrame(tick);
	}

	stop(): void {
		if (this.raf) cancelAnimationFrame(this.raf);
		this.raf = 0;
		this.extractor.reset();
		this.orphanPulses = [];
		this.orphanWasActive = false;
		this.gate?.reset();
		this.signal.activations.fill(0);
		this.signal.pointActivation.fill(0);
		this.signal.orphanPulse.fill(0);
		this.signal.level = 0;
		this.signal.best = -1;
	}

	private step(): void {
		const frame = this.engine.frame();
		this.extractor.push(frame);
		const active = this.extractor.active;
		const now = performance.now() / 1000;

		if (active && !this.wasActive) this.onsetTimes.push(now);
		this.wasActive = active;
		this.onsetTimes = this.onsetTimes.filter((t) => now - t < 3);
		// The pace the activation EMA tracks by: dense playing gets less smoothing, so
		// the galaxy keeps up with the audio at fast tempo (see `onsetRate` in
		// features.ts for the measured numbers). Sparse input relaxes back to the
		// flicker-killing rate.
		this.tracker.onsetRate = this.onsetTimes.length / 3;

		this.signal.level = Math.min(1, this.extractor.level * 6);

		if (active) {
			const descriptor = this.extractor.descriptor();
			if (descriptor) {
				const z = standardise(descriptor, this.assets.featureSpace);
				// The session gate sees the same z the tracker does, but only from the
				// microphone: the analysis bus also carries Birdy's own output, and a
				// "session" of our own renders is not the thing the gate is about.
				//
				// **This guard is load-bearing, not belt-and-braces.** It used to say corpus
				// audio "would never — and should never — flag", and the first half is
				// measurably false: the anchors come from the fit sessions, which are field
				// recordings, and our renders are the synthesized class. Scored against the
				// shipped anchors on the production build, synthesized-only knots reach a
				// median 5-NN of 11.02 against a 3.92 threshold while field knots sit at
				// 3.17 (verify-features.mjs states the whole table). So without this `if`,
				// playing Birdy's own voice near an open mic would light the Reading panel's
				// first branch — "off the map, positions are guesses" — about our own corpus.
				if (this.engine.micActive) this.gate?.push(z);
				// Flatness is the last element of the 28-d descriptor, and it has to be
				// handed over raw: standardising turns "this is broadband noise" into a
				// z-score whose meaning depends on how much noise the corpus contains.
				this.tracker.update(z, descriptor[descriptor.length - 1]);
				this.signal.activations.set(this.tracker.activations);
				this.signal.best = this.tracker.best().index;
			}
			const [f0, clarity] = this.pitch.findPitch(frame, this.engine.ctx.sampleRate);
			if (clarity > 0.75 && f0 > 150) this.signal.f0 = f0;
		} else {
			this.tracker.decay();
			this.signal.activations.set(this.tracker.activations);
			// The pitch readout is a live measurement, not a last-known-good value. Left
			// latched it reports several kHz over a silent aviary, which is a lie the HUD
			// has no way to qualify.
			this.signal.f0 = this.signal.f0 > 1 ? this.signal.f0 * 0.9 : 0;
		}
		this.signal.strength = this.tracker.strength;
		if (this.tracker.strength < 1e-3) this.signal.best = -1;

		// Heard, but nothing claimed: below the claim gate yet not silence, the nearest
		// region gets the slow grey breath instead of the wave — a third state the
		// picture used to show as plain nothing. A scheduled note is known, so it never
		// lands here; a confident match claims its knot and never lands here either.
		this.signal.unmatched = unmatchedCluster(this.signal, active);

		// While Birdy sings, it knows the score, so the trajectories are driven by the
		// schedule rather than by matching — a cluster lights exactly on the note instead
		// of a feature-window later. Listening still relies on the tracker above.
		const singing = this.advancePaths();

		// Rebuilt from scratch each frame: a note that has finished is no longer being
		// sung, and a stale flag would leave a cluster wearing its species colour long
		// after it stopped being the source.
		this.signal.sung.fill(0);

		if (singing) {
			// **While Birdy sings, only what it is singing lights up.**
			//
			// Two different claims were being drawn in the same channel: the scheduled node,
			// which we know, and whatever the matcher thought the output resembled, which we
			// infer. Damping the inferred ones to 30 % was not a fix — a third of full
			// brightness across a dozen clusters still reads as a dozen clusters, so one
			// bird singing flared clouds all over the galaxy and looked like a chorus.
			//
			// The rule now has no middle: known beats inferred outright. The matcher keeps
			// running — `strength`, the reading panel and the microphone path all still use
			// it — but it does not get to draw over a note whose identity is not in doubt.
			// Listening, where nothing is known, is the case the inference is for. The grey
			// breath follows the same rule: a weak self-match during a scheduled note is
			// still a known note, so "heard but nothing claimed" cannot stand while it
			// sounds (the orphan branch below already clears it; this one forgot to).
			this.signal.activations.fill(0);
			this.signal.unmatched = -1;
			this.applyScheduledPulses(this.engine.ctx.currentTime);
		} else if (this.orphanSounding()) {
			// **A note we know but cannot place fires no positional effect at all.**
			//
			// The song is scheduled, so its identity is certain — and its syllable owns no
			// cluster, so its position is certain to be *unknown*. What used to happen in
			// this gap: the tracker heard the synth's own output, matched it to some other
			// knot (often a small central one), and the wave, the knot and the label all
			// fired *there* — a positional claim about a note whose placement we explicitly
			// lack, which reads as the selected node spawning points somewhere else ("it
			// activates points that are NOT there"). The note's honest display already
			// exists: the orphan pulse, the syllable's own points at their true positions.
			// Known-unplaced beats inferred, exactly as known beats inferred above.
			this.signal.activations.fill(0);
			this.signal.best = -1;
			this.signal.unmatched = -1;
		}

		// A scheduled note is known, not matched, so it lights at full strength; anything
		// arriving through the microphone has to earn it.
		this.points.update(this.signal.activations, singing ? 1 : this.tracker.strength);
		if (singing) this.pulseScheduledPoints(this.engine.ctx.currentTime);
		this.signal.pointActivation.set(this.points.activation);
		this.stepOrphans();

		if (now - this.lastMeters > 0.05) {
			this.lastMeters = now;
			this.onMeters?.({
				level: this.signal.level,
				f0: this.signal.f0,
				strength: this.tracker.strength,
				active,
				session: this.gate
					? {
							flagged: this.gate.flagged,
							score: this.gate.score,
							threshold: this.gate.threshold
						}
					: undefined
			});
		}

		// the readout is for human eyes; 8 Hz is plenty and keeps Svelte updates cheap
		if (now - this.lastReading > 0.125) {
			this.lastReading = now;
			this.reading = readActivations(
				this.assets.inventory,
				this.assets.centroids,
				this.signal.activations,
				this.tracker.similarity,
				{
					active,
					strength: this.tracker.strength,
					onsetRate: this.onsetTimes.length / 3,
					f0: this.signal.f0,
					speciesName: this.assets.speciesCommon
				}
			);
			this.onReading?.(this.reading);
		}
	}

	/** Moves every live path along, retires the finished ones. True if any is playing. */
	private advancePaths(): boolean {
		const time = this.engine.ctx.currentTime;
		let anySinging = false;
		for (const path of this.live) {
			path.progress = this.advance(path, time);
			if (path.progress >= 0) {
				anySinging = true;
				path.started = true;
				path.alpha = 1;
			} else if (path.started) {
				// A phrase that has finished fades out rather than vanishing mid-frame, so a
				// chorus leaves a decaying trace of what has just been sung.
				path.alpha -= 0.012;
			}
		}
		// Only a phrase that has actually been sung can be finished with. A queued one is
		// held, invisible, until its turn.
		const remaining = this.live.filter((p) => !p.started || p.alpha > GONE_ALPHA);
		const changed = remaining.length !== this.live.length;
		if (changed) this.live = remaining;
		if (changed) this.publishPaths();
		return anySinging;
	}

	/**
	 * How brightly a scheduled node lights at `now`, given the path's position.
	 *
	 * Two gaussian windows, not one: position along the path, and the note's own
	 * scheduled time. Position alone was written for dense paths, where the node a
	 * half-step away is the note a tenth of a second away, and lighting it a little
	 * early reads as the syllable arriving. Learned paths are sparse — every syllable
	 * without a cluster is dropped from `nodes` (most of them, on a field-audio build),
	 * so "half a step away" can be seconds of real time and several sung syllables in
	 * between. Lit on position alone, a knot flared — particles, label and all — while
	 * notes that belong to no knot were sounding: a response knots away from the wave,
	 * reported as firing at the wrong position. The time window restores what position
	 * used to imply: a knot lights as its own note arrives, however much of the phrase
	 * was dropped between the two.
	 */
	private static scheduledPulse(path: LivePath, i: number, now: number): number {
		const offset = (path.progress - i) / 0.5;
		let pulse = Math.exp(-(offset * offset));
		const t = path.times?.[i];
		if (t && pulse > 0.01) {
			const mid = (t.start + t.end) / 2;
			const dt = (now - mid) / 0.45;
			pulse *= Math.exp(-(dt * dt));
		}
		return pulse;
	}

	private applyScheduledPulses(now: number): void {
		for (const path of this.live) {
			if (path.progress < 0) continue;
			path.nodes.forEach((node, i) => {
				const pulse = Listener.scheduledPulse(path, i, now);
				if (pulse > 0.01) {
					this.signal.activations[node] = Math.max(this.signal.activations[node], pulse);
					// This one we *know*, so it is marked as sung rather than matched — see
					// the note on `sung` in shaders.ts for why the two must look different.
					this.signal.sung[node] = Math.max(this.signal.sung[node], pulse);
				}
			});
			const current = path.nodes[Math.round(path.progress)];
			if (current !== undefined) this.signal.best = current;
		}
	}

	/**
	 * A scheduled note has no live descriptor behind it — we know which cluster it is, not
	 * which of that cluster's points it resembles — so its members light together, with a
	 * fixed per-point offset that keeps the knot from reading as a single disc.
	 */
	private pulseScheduledPoints(now: number): void {
		for (const path of this.live) {
			if (path.progress < 0) continue;
			path.nodes.forEach((node, i) => {
				const pulse = Listener.scheduledPulse(path, i, now);
				if (pulse > 0.05) this.points.pulseCluster(node, pulse);
			});
		}
	}
}
