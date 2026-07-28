import workletUrl from './worklets/syrinx-processor.js?url';
import type { BirdyAssets, Species, Syllable } from '$lib/data/types';
import { songSyllables, speciesById } from '$lib/data/assets';
import { applyVoice, createPopulation, type Individual } from './individual.ts';

export interface PlayOptions {
	/** AudioContext time to start at; defaults to "just now". */
	at?: number;
	gain?: number;
	/** 0 = in your hand, 1 = far across the field. Drives air absorption and reverb. */
	distance?: number;
	/** Anonymous per-rendition variation, matching the corpus jitter. */
	jitter?: number;
	/** Sing as this particular bird instead: a held voice rather than fresh randomness. */
	voice?: Individual;
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
	private inputSource: 'microphone' | 'system' | null = null;
	private recorder: MediaRecorder | null = null;
	private recordChunks: Blob[] = [];
	private ambientTimer: ReturnType<typeof setInterval> | null = null;
	private ambientUntil = 0;
	private population: Individual[] = [];
	private readonly frameBuffer: Float32Array<ArrayBuffer>;

	state: EngineState = { voices: 0, f0: 0, level: 0 };
	onState: ((state: EngineState) => void) | null = null;
	/**
	 * Fires whenever a song is scheduled, including by the ambient chorus. The visualisation
	 * subscribes to this so the trajectory follows whatever is actually singing instead of
	 * staying on whatever the menus have selected.
	 */
	onScheduled:
		| ((event: {
				speciesId: string;
				songId: string;
				scheduled: ScheduledSyllable[];
				voice?: Individual;
		  }) => void)
		| null = null;

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
		const shaped = toPlain(
			options.voice ? applyVoice(syllable, options.voice) : jitterSyllable(syllable, options.jitter ?? 0)
		);
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
		const scheduled = this.playSequence(resolved.syllables, resolved.song.gaps, options);
		this.onScheduled?.({ speciesId, songId, scheduled, voice: options.voice });
		return scheduled;
	}

	// --- ambient scheduling (Poisson, doc 02 §2.1) ---

	/**
	 * Background chorus: Poisson-distributed songs at `songsPerMinute`, drawn from a fixed
	 * roster of individual birds, with a 25 % chance that a *different* bird of the same
	 * species answers — which is what makes it a duet rather than an echo.
	 */
	startAmbient(speciesIds: string[], songsPerMinute = 12, birdsPerSpecies = 2): void {
		this.stopAmbient();
		if (!speciesIds.length) return;
		const pool = speciesIds
			.map((id) => speciesById(this.assets.inventory, id))
			.filter((s): s is Species => Boolean(s) && s!.songs.length > 0);
		if (!pool.length) return;

		// The roster is created once and held: each bird keeps its pitch, timing, timbre and
		// position for as long as the chorus runs, so you can hear the same individual twice.
		this.population = createPopulation(
			pool.map((s) => ({ id: s.id, common: s.common })),
			birdsPerSpecies
		);

		this.ambientUntil = this.ctx.currentTime;
		const rate = songsPerMinute / 60;
		this.ambientTimer = setInterval(() => {
			const horizon = this.ctx.currentTime + 0.5;
			while (this.ambientUntil < horizon) {
				// exponential inter-arrival times = Poisson process
				this.ambientUntil += -Math.log(1 - Math.random()) / rate;
				const species = pool[Math.floor(Math.random() * pool.length)];
				const birds = this.population.filter((b) => b.speciesId === species.id);
				if (!birds.length) continue;
				const bird = birds[Math.floor(Math.random() * birds.length)];
				const song = species.songs[Math.floor(Math.random() * species.songs.length)];
				const at = this.ambientUntil;
				// Distance is a scene-wide property the listener controls, so individual birds
				// vary by level and position only — calling setDistance per song would fight
				// the UI and retune the filters mid-phrase.
				this.playSong(species.id, song.id, {
					at,
					voice: bird,
					gain: 0.45 + Math.random() * 0.5,
					pan: bird.pan
				});
				if (Math.random() < 0.25) {
					const rival = birds.find((b) => b.id !== bird.id) ?? bird;
					const answer = species.songs[Math.floor(Math.random() * species.songs.length)];
					this.playSong(species.id, answer.id, {
						at: at + 0.4 + Math.random() * 0.9,
						voice: rival,
						gain: 0.6,
						pan: rival.pan
					});
				}
			}
		}, 100);
	}

	/** The birds currently present, in the order they were created. */
	get birds(): readonly Individual[] {
		return this.population;
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

	/**
	 * Opens an input and routes it into the analysis bus.
	 *
	 * `microphone` takes an optional device id. `system` uses display capture, which is
	 * the only way a browser will hand over the computer's own output; Chrome requires a
	 * video track to be requested alongside it, so one is asked for and immediately
	 * stopped — we never look at it.
	 *
	 * Every processing option is off. Echo cancellation, noise suppression and AGC are
	 * tuned for speech: they gate exactly the quiet broadband texture a distant bird is
	 * made of, and AGC would rescale the level the descriptor depends on.
	 */
	async startInput(source: 'microphone' | 'system', deviceId?: string): Promise<void> {
		this.stopInput();
		const constraints: MediaTrackConstraints = {
			echoCancellation: false,
			noiseSuppression: false,
			autoGainControl: false
		};
		let stream: MediaStream;
		if (source === 'system') {
			if (!navigator.mediaDevices.getDisplayMedia) {
				throw new Error('This browser cannot capture computer audio.');
			}
			stream = await navigator.mediaDevices.getDisplayMedia({
				audio: constraints,
				video: true
			});
			stream.getVideoTracks().forEach((t) => {
				t.stop();
				stream.removeTrack(t);
			});
			if (!stream.getAudioTracks().length) {
				throw new Error(
					'No audio came with that capture. Tick "share audio" when choosing the tab or screen.'
				);
			}
		} else {
			stream = await navigator.mediaDevices.getUserMedia({
				audio: deviceId ? { ...constraints, deviceId: { exact: deviceId } } : constraints
			});
		}
		this.micStream = stream;
		this.inputSource = source;
		this.micSource = this.ctx.createMediaStreamSource(stream);
		// analysis only — never routed to the speakers, which would feed back
		this.micSource.connect(this.analysisBus);
		await this.resume();
	}

	/** Input devices the browser will name. Labels stay blank until permission is given. */
	static async inputDevices(): Promise<MediaDeviceInfo[]> {
		if (!navigator.mediaDevices?.enumerateDevices) return [];
		const all = await navigator.mediaDevices.enumerateDevices();
		return all.filter((d) => d.kind === 'audioinput');
	}

	stopInput(): void {
		this.micSource?.disconnect();
		this.micSource = null;
		this.micStream?.getTracks().forEach((t) => t.stop());
		this.micStream = null;
		this.inputSource = null;
	}

	get micActive(): boolean {
		return this.micStream !== null;
	}

	/** Which input is open, or null. */
	get activeInput(): 'microphone' | 'system' | null {
		return this.inputSource;
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
		this.stopInput();
		await this.ctx.close();
	}
}
