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
