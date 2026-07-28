import { PitchDetector } from 'pitchy';
import { ActivationTracker, FeatureExtractor, standardise } from './features.ts';
import { readActivations, type Reading } from '$lib/lang/translate';
import { createSignal, type VisualSignal } from '$lib/galaxy/shaders';
import type { BirdyAssets } from '$lib/data/types';
import type { BirdyEngine } from './engine';

/**
 * The live loop: analysis bus -> 28-d descriptor -> cluster activations -> galaxy
 * uniforms + translation readout. Everything here is cheap enough to run per frame
 * (docs/05-embedding-galaxy.md §5.3); the only ML-shaped step is a nearest-centroid
 * lookup, which is why no model has to run in the browser.
 */
export class Listener {
	readonly signal: VisualSignal;
	readonly extractor: FeatureExtractor;
	private readonly tracker: ActivationTracker;
	private readonly pitch: PitchDetector<Float32Array>;
	private raf = 0;
	private lastReading = 0;
	private onsetTimes: number[] = [];
	private wasActive = false;

	/** Scheduled syllable windows in AudioContext time, when a phrase is playing. */
	private pathTimes: { start: number; end: number }[] | null = null;

	reading: Reading;
	onReading: ((reading: Reading) => void) | null = null;
	/**
	 * The visual signal is mutated in place for the renderer, which reads it once per frame
	 * and needs no reactivity. Anything the UI displays has to arrive as a callback instead,
	 * or Svelte never sees the change.
	 */
	onMeters: ((meters: { level: number; f0: number; active: boolean }) => void) | null = null;
	private lastMeters = 0;

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
		this.signal = createSignal(assets.centroids.items.length);
		this.pitch = PitchDetector.forFloat32Array(assets.featureSpace.frameSize);
		this.reading = readActivations(
			assets.inventory,
			assets.centroids,
			this.signal.activations,
			this.tracker.similarity,
			{ active: false }
		);
	}

	/**
	 * Sets the trajectory through the galaxy.
	 *
	 * With `times`, the path animates: a travelling highlight follows the schedule, so the
	 * galaxy lights each cluster exactly as its syllable sounds. Without them the path is
	 * drawn as a faint thread — that is what a selected-but-unplayed call looks like.
	 * Nodes the corpus does not know (index < 0) are dropped along with their times.
	 */
	setPath(nodes: number[], times: { start: number; end: number }[] | null = null): void {
		const keptNodes: number[] = [];
		const keptTimes: { start: number; end: number }[] = [];
		nodes.forEach((node, i) => {
			if (node < 0) return;
			keptNodes.push(node);
			if (times?.[i]) keptTimes.push(times[i]);
		});
		this.signal.path = keptNodes;
		this.signal.pathVersion++;
		this.pathTimes = times && keptTimes.length === keptNodes.length ? keptTimes : null;
		this.signal.pathProgress = -1;
		this.signal.pathAlpha = keptNodes.length > 1 ? 1 : 0;
	}

	clearPath(): void {
		this.signal.path = [];
		this.signal.pathVersion++;
		this.signal.pathProgress = -1;
		this.signal.pathAlpha = 0;
		this.pathTimes = null;
	}

	/**
	 * Position along the path right now, in node units, or -1 once the phrase is over.
	 * Between two syllables it keeps moving through the gap so the highlight travels along
	 * the connecting line instead of jumping.
	 */
	private advancePath(now: number): number {
		const times = this.pathTimes;
		if (!times || !times.length) return -1;
		if (now < times[0].start) return 0;
		const last = times[times.length - 1];
		if (now > last.end + 0.25) {
			// leave the path on screen as a faint completed thread
			this.pathTimes = null;
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
		this.signal.activations.fill(0);
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

		this.signal.level = Math.min(1, this.extractor.level * 6);

		if (active) {
			const descriptor = this.extractor.descriptor();
			if (descriptor) {
				const z = standardise(descriptor, this.assets.featureSpace);
				this.tracker.update(z);
				this.signal.activations.set(this.tracker.activations);
				this.signal.best = this.tracker.best().index;
			}
			const [f0, clarity] = this.pitch.findPitch(frame, this.engine.ctx.sampleRate);
			if (clarity > 0.75 && f0 > 150) this.signal.f0 = f0;
		} else {
			this.tracker.decay();
			this.signal.activations.set(this.tracker.activations);
		}

		// While Birdy sings, it knows the score, so the trajectory is driven by the schedule
		// rather than by matching — the cluster lights exactly on the note instead of a
		// feature-window later. Listening still relies on the tracker above.
		const progress = this.advancePath(this.engine.ctx.currentTime);
		this.signal.pathProgress = progress;
		if (progress >= 0) {
			// The matched activations stay visible but are damped: the analysis window spans
			// ~0.7 s, so it lights every cluster of a short phrase at once, which blurs the
			// order. Damping them lets the scheduled node read as "this syllable, now".
			for (let i = 0; i < this.signal.activations.length; i++) this.signal.activations[i] *= 0.3;
			this.signal.path.forEach((node, i) => {
				const offset = (progress - i) / 0.5;
				const pulse = Math.exp(-(offset * offset));
				if (pulse > 0.01) {
					this.signal.activations[node] = Math.max(this.signal.activations[node], pulse);
				}
			});
			const current = this.signal.path[Math.round(progress)];
			if (current !== undefined) this.signal.best = current;
		} else if (this.signal.pathAlpha > 0 && !this.pathTimes) {
			// fade the finished path down to a faint thread, then leave it
			this.signal.pathAlpha = Math.max(0.45, this.signal.pathAlpha - 0.02);
		}

		if (now - this.lastMeters > 0.05) {
			this.lastMeters = now;
			this.onMeters?.({ level: this.signal.level, f0: this.signal.f0, active });
		}

		// the readout is for human eyes; 8 Hz is plenty and keeps Svelte updates cheap
		if (now - this.lastReading > 0.125) {
			this.lastReading = now;
			this.reading = readActivations(
				this.assets.inventory,
				this.assets.centroids,
				this.signal.activations,
				this.tracker.similarity,
				{ active, onsetRate: this.onsetTimes.length / 3, f0: this.signal.f0 }
			);
			this.onReading?.(this.reading);
		}
	}
}
