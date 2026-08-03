/**
 * Client for the optional local pipeline control surface (`birdy-pipeline serve`).
 *
 * Everything here degrades to "not running". The galaxy is precomputed and the app
 * needs no backend to show it; this only exists so harvesting and learning can be
 * driven from the interface instead of from a terminal. If the process is not up, the
 * Learn page says how to start it and nothing else changes.
 */

const DEFAULT_ORIGIN = 'http://127.0.0.1:8781';

export interface StoreStatus {
	exists: boolean;
	path?: string;
	descriptors?: number;
	descriptorsSeen?: number;
	syllables?: number;
	recordings?: number;
	species?: string[];
	cap?: number;
	/** Drift of the retained sample from the full stream, in the stream's own sd. */
	meanDrift?: number;
	stdRatio?: number;
}

export interface LearnedSpecies {
	id: string;
	common: string;
	types: number;
	states: number;
	bout: string[];
}

export interface LearnedStatus {
	exists: boolean;
	path?: string;
	species?: LearnedSpecies[];
	medianCosine?: number | null;
	worstCosine?: number | null;
}

export interface BuiltStatus {
	exists: boolean;
	builtAt?: string;
	/** Bumped by every grow; 0 or absent on a galaxy that has only ever been built. */
	generation?: number;
	points?: number;
	clusters?: number;
	source?: string;
	sourceMix?: Record<string, number>;
}

export interface JobStatus {
	name: string;
	detail: string;
	/** `stopping` is after a stop request and before the job reaches its next checkpoint. */
	state: 'running' | 'stopping' | 'done' | 'stopped' | 'failed';
	seconds: number;
	error: string | null;
	cancelled: boolean;
	log: string[];
	/**
	 * What a finished job had to report beyond its log. Only jobs with something to
	 * count set it — an ingest's is `{ novel, total }`: how many of the syllables it
	 * segmented were unlike every known type centroid (docs/09 §9.2b).
	 */
	result?: Record<string, unknown> | null;
}

/**
 * The learned critic, when one has been trained (`birdy-pipeline critic train`).
 *
 * Present so the interface can say *which objective* produced the numbers next to each
 * learned syllable — a fit run with `--embed-typing` defines syllable types differently from
 * one run without it, and the resynthesis cosines are not comparable across the two. No
 * weights are involved: the server reads this from the sidecar JSON written next to them, and
 * nothing about the critic ever reaches the browser.
 */
export interface CriticStatus {
	exists: boolean;
	path?: string;
	/** Share of the fit's objective the realism logit was given. 0 is the measured default. */
	weight?: number;
	/** Whether syllable types were clustered in the learned embedding. */
	embedTyping?: boolean;
	/**
	 * The training report, verbatim from the sidecar JSON.
	 *
	 * `snake_case` because it is `dataclasses.asdict(TrainingReport)` and the field names come
	 * straight through — everything else the server sends is hand-assembled and camelCase, so
	 * this is the one block that is not. Kept as-is rather than renamed on the way out: the
	 * same JSON is what `critic train` writes next to the weights for a human to read, and
	 * having two spellings of one report is worse than one inconsistent spelling.
	 */
	report?: {
		train_species?: string[];
		holdout_species?: string[];
		/** Real-vs-resynthesis AUC on species held out of training. 0.5 is chance. */
		realism_auc_holdout?: number;
		species_accuracy?: number;
		species_chance?: number;
		/** Retrieval of a syllable's own augmented view out of 256. Chance is 0.004. */
		contrastive_top1?: number;
	};
}

export interface PipelineStatus {
	ok: true;
	hasKey: boolean;
	ffmpeg: boolean;
	store: StoreStatus;
	learned: LearnedStatus;
	built: BuiltStatus;
	/** Absent on a control process started before the critic existed. */
	critic?: CriticStatus;
	discovered?: {
		id: string;
		common: string;
		scientific: string;
		/** Recordings the discovery sweep saw for it on xeno-canto. */
		available: number;
		/** Descriptors the harvest store holds for it so far. */
		descriptors: number;
		/** `waiting for audio` | `collecting` | `fitted` — how far it has got. */
		stage: string;
	}[];
	inventorySpecies: { id: string; common: string }[];
	/**
	 * Syllables the novelty scorer judged unlike every known type centroid, store-wide
	 * (docs/09 §9.2b). Both absent on a control process started before novelty scoring
	 * existed — and a flagged syllable is still `unlabelled`: detecting that a sound is
	 * new is not knowing what it means.
	 */
	novelCount?: number;
	/** The most recent flagged syllables (at most 8), newest first. */
	recentNovel?: {
		speciesId: string;
		recordingId: string;
		/** The syllable's index within its recording. */
		order: number;
		/** Its fitted type, if a fit has assigned one; empty otherwise. */
		typeId?: string;
	}[];
	job: JobStatus | null;
}

/**
 * Ceiling on a control-surface request.
 *
 * **Without one, "not running" and "not answering" are different failures and only the first
 * degrades gracefully.** A refused connection rejects immediately, which is the case this
 * client was written for; a process that holds the socket open and never replies — starting
 * up, wedged, or a stale build compiling its kernels — leaves `fetch` pending forever. The
 * Learn page sets `pipelineChecked` only after the status call settles, so it sat on
 * "checking…" indefinitely instead of falling through to the message that explains how to
 * start the process.
 *
 * Generous, because a status call on a busy machine is allowed to be slow; the point is only
 * that it must end.
 *
 * Applied to reads only. A POST starts work — a harvest, a fit, a build — and how long the
 * process takes to acknowledge that is not something this client should have an opinion
 * about; cutting one off mid-flight risks leaving a job running that the interface has
 * stopped believing in. Reads are polled on a timer, so dropping one costs nothing.
 */
const REQUEST_TIMEOUT_MS = 4000;

export class PipelineClient {
	constructor(readonly origin: string = DEFAULT_ORIGIN) {}

	private async call<T>(path: string, body?: unknown): Promise<T> {
		const res = await fetch(`${this.origin}${path}`, {
			method: body === undefined ? 'GET' : 'POST',
			headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
			body: body === undefined ? undefined : JSON.stringify(body),
			signal: body === undefined ? AbortSignal.timeout(REQUEST_TIMEOUT_MS) : undefined
		});
		const data = (await res.json()) as T & { ok?: boolean; error?: string };
		if (data.ok === false) {
			// A route the running process has never heard of almost always means the code
			// moved on and the process did not — it is started once and outlives many
			// edits. Saying so beats "unknown endpoint", which reads like a bug in the app.
			if ((data.error ?? '').includes('unknown endpoint')) {
				throw new Error(
					`This control process does not have ${path}. It was started before that ` +
						'route existed — restart it (birdy-pipeline serve) and try again.'
				);
			}
			throw new Error(data.error ?? 'the pipeline refused that');
		}
		return data;
	}

	/** Null when the control process is not running — the normal case, not an error. */
	async status(): Promise<PipelineStatus | null> {
		try {
			return await this.call<PipelineStatus>('/api/status');
		} catch {
			return null;
		}
	}

	async job(): Promise<JobStatus | null> {
		try {
			const data = await this.call<{ job: JobStatus | null }>('/api/job');
			return data.job;
		} catch {
			return null;
		}
	}

	harvest(options: {
		species?: string | null;
		perSpecies?: number;
		quality?: string;
		cap?: number;
		maxSeconds?: number;
		fromDir?: string | null;
		dryRun?: boolean;
	}) {
		return this.call<{ job: JobStatus }>('/api/harvest', options);
	}

	/**
	 * `learnedOnly` writes the fitted repertoire on its own. The default writes it next
	 * to the documented calls, which is what keeps the citations in the app.
	 */
	learn(options: { types?: number; learnedOnly?: boolean }) {
		return this.call<{ job: JobStatus }>('/api/learn', options);
	}

	build(options: {
		useLearned?: boolean;
		includeHarvest?: boolean;
		source?: string;
		/**
		 * `kmeans` fits exactly k groups and puts every point in one; `hdbscan` finds how
		 * many dense regions there are and leaves the rest unassigned, which is the only
		 * way a sound can come out as "none of these"; `label` gives every typed point the
		 * knot of its own type and runs kmeans only over the untyped remainder, which is
		 * the answer at production scale (docs/22 §22.5).
		 */
		clustering?: 'kmeans' | 'hdbscan' | 'label';
		minClusterSize?: number;
	}) {
		return this.call<{ job: JobStatus }>('/api/build', options);
	}

	/**
	 * Adds the harvest store's newest audio to the built galaxy in place, leaving every
	 * existing point where it is. Cheaper than a build and unable to discover a cluster —
	 * the drift figures in the job log say when that has started to matter.
	 */
	grow(options: { all?: boolean } = {}) {
		return this.call<{ job: JobStatus }>('/api/grow', options);
	}

	/**
	 * Keep learning: harvest a little, fit what came in, grow the galaxy, repeat, until
	 * stopped. One job rather than three, and it runs in the control process, so closing
	 * the tab does not stop it.
	 */
	loop(options: {
		/** New species to look for at the start of each pass; 0 keeps to the birds it knows. */
		discover?: number;
		perSpecies?: number;
		quality?: string;
		types?: number;
		passes?: number;
	} = {}) {
		return this.call<{ job: JobStatus }>('/api/loop', options);
	}

	/**
	 * Asks the running job to stop. It ends at its next checkpoint — after the recording
	 * it is currently analysing, or the species it is currently fitting — so everything
	 * already done is kept rather than thrown away.
	 */
	stop() {
		return this.call<{ job: JobStatus }>('/api/stop', {});
	}

	/**
	 * Sends a recording made in the browser to the store, where the pipeline segments it
	 * with the same code it uses on downloaded audio. The file is posted as raw bytes
	 * rather than multipart because the server is 200 lines of `http.server` and parsing
	 * multipart there would be the largest thing in it.
	 */
	async ingest(blob: Blob, speciesId: string, name: string): Promise<JobStatus> {
		const query = new URLSearchParams({ species: speciesId, name });
		const res = await fetch(`${this.origin}/api/ingest?${query}`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/octet-stream' },
			body: blob
		});
		const data = (await res.json()) as { ok?: boolean; error?: string; job: JobStatus };
		if (data.ok === false) throw new Error(data.error ?? 'the pipeline refused that');
		return data.job;
	}
}
