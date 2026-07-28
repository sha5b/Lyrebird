import workletUrl from './worklets/syrinx-processor.js?url';
import type { BirdyAssets, Species, Syllable } from '$lib/data/types';
import { songSyllables, speciesById } from '$lib/data/assets';

export interface PlayOptions {
	/** AudioContext time to start at; defaults to "just now". */
	at?: number;
	gain?: number;
	/** 0 = in your hand, 1 = far across the field. Drives air absorption and reverb. */
	distance?: number;
	/** Per-individual variation: pitch/duration/level jitter, matching the corpus. */
	jitter?: number;
	pan?: number;
}

export interface ScheduledSyllable {
	syllableId: string;
	label: string;
	at: number;
	dur: number;
}

export interface EngineState {
	voices: number;
	f0: number;
	level: number;
}

/** Bird-sized reverb: a short exponentially decaying noise burst. */
function makeImpulse(ctx: AudioContext, seconds = 1.6, decay = 3.2): AudioBuffer {
	const length = Math.floor(ctx.sampleRate * seconds);
	const buffer = ctx.createBuffer(2, length, ctx.sampleRate);
	for (let ch = 0; ch < 2; ch++) {
		const data = buffer.getChannelData(ch);
		for (let i = 0; i < length; i++) {
			data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / length, decay);
		}
	}
	return buffer;
}

/**
 * Anything crossing into the AudioWorklet has to survive structured cloning, which a
 * reactive proxy does not. The payloads here are small JSON, so a round-trip is the
 * cheapest way to guarantee a plain object regardless of how the caller stored it.
 */
function toPlain<T>(value: T): T {
	return JSON.parse(JSON.stringify(value)) as T;
}

function jitterSyllable(syllable: Syllable, amount: number): Syllable {
	if (amount <= 0) return syllable;
	const r = (spread: number) => 1 + (Math.random() * 2 - 1) * spread * amount;
	const pitch = r(0.03);
	return {
		...syllable,
		dur: syllable.dur * r(0.08),
		level: Math.min(1, syllable.level * r(0.1)),
		am: syllable.am ? syllable.am * r(0.06) : syllable.am,
		contour: syllable.contour.map(([t, hz]) => [t, hz * pitch] as [number, number])
	};
}

export class BirdyEngine {
	readonly ctx: AudioContext;
	readonly analyser: AnalyserNode;
	private readonly synth: AudioWorkletNode;
	private readonly voiceGain: GainNode;
	private readonly airFilter: BiquadFilterNode;
	private readonly dry: GainNode;
	private readonly wet: GainNode;
	private readonly master: GainNode;
	private readonly analysisBus: GainNode;
	private micStream: MediaStream | null = null;
	private micSource: MediaStreamAudioSourceNode | null = null;
	private recorder: MediaRecorder | null = null;
	private recordChunks: Blob[] = [];
	private ambientTimer: ReturnType<typeof setInterval> | null = null;
	private ambientUntil = 0;
	private readonly frameBuffer: Float32Array<ArrayBuffer>;

	state: EngineState = { voices: 0, f0: 0, level: 0 };
	onState: ((state: EngineState) => void) | null = null;

	private constructor(ctx: AudioContext, synth: AudioWorkletNode, private readonly assets: BirdyAssets) {
		this.ctx = ctx;
		this.synth = synth;

		this.voiceGain = ctx.createGain();
		this.voiceGain.gain.value = 0.9;

		this.airFilter = ctx.createBiquadFilter();
		this.airFilter.type = 'lowpass';
		this.airFilter.frequency.value = 12000;

		const convolver = ctx.createConvolver();
		convolver.buffer = makeImpulse(ctx);
		this.dry = ctx.createGain();
		this.wet = ctx.createGain();
		this.dry.gain.value = 0.9;
		this.wet.gain.value = 0.1;

		this.master = ctx.createGain();
		this.master.gain.value = 0.8;

		this.analysisBus = ctx.createGain();
		this.analyser = ctx.createAnalyser();
		this.analyser.fftSize = assets.featureSpace.frameSize;
		this.analyser.smoothingTimeConstant = 0;

		synth.connect(this.voiceGain);
		this.voiceGain.connect(this.airFilter);
		this.airFilter.connect(this.dry);
		this.airFilter.connect(convolver);
		convolver.connect(this.wet);
		this.dry.connect(this.master);
		this.wet.connect(this.master);
		this.master.connect(ctx.destination);
		// The synth feeds the same analysis path as the microphone, so the galaxy reacts
		// to our own bird exactly as it reacts to a real one (closed loop).
		this.master.connect(this.analysisBus);
		this.analysisBus.connect(this.analyser);

		this.frameBuffer = new Float32Array(assets.featureSpace.frameSize);

		synth.port.onmessage = (event) => {
			if (event.data?.type === 'state') {
				this.state = { voices: event.data.voices, f0: event.data.f0, level: event.data.level };
				this.onState?.(this.state);
			}
		};
	}

	static async create(assets: BirdyAssets): Promise<BirdyEngine> {
		const ctx = new AudioContext({ sampleRate: assets.featureSpace.sampleRate, latencyHint: 'interactive' });
		await ctx.audioWorklet.addModule(workletUrl);
		const synth = new AudioWorkletNode(ctx, 'syrinx-processor', {
			numberOfInputs: 0,
			numberOfOutputs: 1,
			// stereo, because each voice carries its own pan (worklet-side equal-power pan)
			outputChannelCount: [2]
		});
		const engine = new BirdyEngine(ctx, synth, assets);
		if (assets.calibration) {
			synth.port.postMessage({ type: 'calibration', calibration: toPlain(assets.calibration) });
		}
		return engine;
	}

	get sampleRateMismatch(): boolean {
		return this.ctx.sampleRate !== this.assets.featureSpace.sampleRate;
	}

	async resume(): Promise<void> {
		if (this.ctx.state !== 'running') await this.ctx.resume();
	}

	setVolume(v: number): void {
		this.master.gain.setTargetAtTime(v, this.ctx.currentTime, 0.02);
	}

	/** Air absorption, reverb mix and pan narrowing with distance (doc 02 §2.1). */
	setDistance(d: number): void {
		const clamped = Math.min(1, Math.max(0, d));
		const now = this.ctx.currentTime;
		this.airFilter.frequency.setTargetAtTime(12000 - 9500 * clamped, now, 0.05);
		this.dry.gain.setTargetAtTime(0.9 - 0.45 * clamped, now, 0.05);
		this.wet.gain.setTargetAtTime(0.1 + 0.5 * clamped, now, 0.05);
		this.voiceGain.gain.setTargetAtTime(0.9 * (1 - 0.55 * clamped), now, 0.05);
	}

	playSyllable(syllable: Syllable, options: PlayOptions = {}): number {
		const at = options.at ?? this.ctx.currentTime + 0.05;
		const shaped = toPlain(jitterSyllable(syllable, options.jitter ?? 0));
		// pan travels with the note and is applied per voice inside the worklet, so
		// overlapping birds keep their own positions
		this.synth.port.postMessage({
			type: 'note',
			when: at,
			syllable: shaped,
			gain: options.gain ?? 1,
			pan: options.pan ?? 0
		});
		return shaped.dur;
	}

	/** Schedules a syllable sequence with the given inter-syllable gaps. */
	playSequence(syllables: Syllable[], gaps: number[], options: PlayOptions = {}): ScheduledSyllable[] {
		let cursor = options.at ?? this.ctx.currentTime + 0.08;
		const scheduled: ScheduledSyllable[] = [];
		syllables.forEach((syllable, i) => {
			const dur = this.playSyllable(syllable, { ...options, at: cursor });
			scheduled.push({ syllableId: syllable.id, label: syllable.label, at: cursor, dur });
			cursor += dur + (gaps[i] ?? 0.06);
		});
		return scheduled;
	}

	playSong(speciesId: string, songId: string, options: PlayOptions = {}): ScheduledSyllable[] {
		const species = speciesById(this.assets.inventory, speciesId);
		if (!species) return [];
		const resolved = songSyllables(species, songId);
		if (!resolved) return [];
		return this.playSequence(resolved.syllables, resolved.song.gaps, options);
	}

	// --- ambient scheduling (Poisson, doc 02 §2.1) ---

	/**
	 * Background chorus: Poisson-distributed songs at `songsPerMinute`, drawn from the
	 * given species, with a 25 % chance that a second bird answers.
	 */
	startAmbient(speciesIds: string[], songsPerMinute = 12): void {
		this.stopAmbient();
		if (!speciesIds.length) return;
		const pool = speciesIds
			.map((id) => speciesById(this.assets.inventory, id))
			.filter((s): s is Species => Boolean(s) && s!.songs.length > 0);
		if (!pool.length) return;

		this.ambientUntil = this.ctx.currentTime;
		const rate = songsPerMinute / 60;
		this.ambientTimer = setInterval(() => {
			const horizon = this.ctx.currentTime + 0.5;
			while (this.ambientUntil < horizon) {
				// exponential inter-arrival times = Poisson process
				this.ambientUntil += -Math.log(1 - Math.random()) / rate;
				const species = pool[Math.floor(Math.random() * pool.length)];
				const song = species.songs[Math.floor(Math.random() * species.songs.length)];
				const at = this.ambientUntil;
				// Distance is a scene-wide property the listener controls, so individual birds
				// vary by level and position only — calling setDistance per song would fight
				// the UI and retune the filters mid-phrase.
				this.playSong(species.id, song.id, {
					at,
					jitter: 1,
					gain: 0.45 + Math.random() * 0.5,
					pan: Math.random() * 1.6 - 0.8
				});
				if (Math.random() < 0.25) {
					const answer = species.songs[Math.floor(Math.random() * species.songs.length)];
					this.playSong(species.id, answer.id, {
						at: at + 0.4 + Math.random() * 0.9,
						jitter: 1,
						gain: 0.6,
						pan: Math.random() * 1.6 - 0.8
					});
				}
			}
		}, 100);
	}

	stopAmbient(): void {
		if (this.ambientTimer !== null) {
			clearInterval(this.ambientTimer);
			this.ambientTimer = null;
		}
	}

	panic(): void {
		this.stopAmbient();
		this.synth.port.postMessage({ type: 'panic' });
	}

	// --- microphone + recording ---

	async startMic(): Promise<void> {
		if (this.micStream) return;
		const stream = await navigator.mediaDevices.getUserMedia({
			audio: {
				echoCancellation: false,
				noiseSuppression: false,
				autoGainControl: false,
				channelCount: 1
			}
		});
		this.micStream = stream;
		this.micSource = this.ctx.createMediaStreamSource(stream);
		// analysis only — never routed to the speakers, which would feed back
		this.micSource.connect(this.analysisBus);
		await this.resume();
	}

	stopMic(): void {
		this.micSource?.disconnect();
		this.micSource = null;
		this.micStream?.getTracks().forEach((t) => t.stop());
		this.micStream = null;
	}

	get micActive(): boolean {
		return this.micStream !== null;
	}

	startRecording(): boolean {
		if (!this.micStream || this.recorder) return false;
		this.recordChunks = [];
		const recorder = new MediaRecorder(this.micStream);
		recorder.ondataavailable = (e) => {
			if (e.data.size > 0) this.recordChunks.push(e.data);
		};
		recorder.start();
		this.recorder = recorder;
		return true;
	}

	async stopRecording(): Promise<Blob | null> {
		const recorder = this.recorder;
		if (!recorder) return null;
		const done = new Promise<Blob>((resolve) => {
			recorder.onstop = () => resolve(new Blob(this.recordChunks, { type: recorder.mimeType }));
		});
		recorder.stop();
		this.recorder = null;
		return done;
	}

	get recording(): boolean {
		return this.recorder !== null;
	}

	/** Latest `frameSize` samples from the shared analysis bus. */
	frame(): Float32Array<ArrayBuffer> {
		this.analyser.getFloatTimeDomainData(this.frameBuffer);
		return this.frameBuffer;
	}

	async dispose(): Promise<void> {
		this.panic();
		this.stopMic();
		await this.ctx.close();
	}
}
