/**
 * Client for the optional local pipeline control surface (`birdy-pipeline serve`).
 *
 * Everything here degrades to "not running". The galaxy is precomputed and the app
 * needs no backend to show it; this only exists so harvesting and learning can be
 * driven from the interface instead of from a terminal. If the process is not up, the
 * Learn tab says how to start it and nothing else changes.
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
	points?: number;
	clusters?: number;
	source?: string;
	sourceMix?: Record<string, number>;
}

export interface JobStatus {
	name: string;
	detail: string;
	state: 'running' | 'done' | 'failed';
	seconds: number;
	error: string | null;
	log: string[];
}

export interface PipelineStatus {
	ok: true;
	hasKey: boolean;
	ffmpeg: boolean;
	store: StoreStatus;
	learned: LearnedStatus;
	built: BuiltStatus;
	inventorySpecies: { id: string; common: string }[];
	job: JobStatus | null;
}

export class PipelineClient {
	constructor(readonly origin: string = DEFAULT_ORIGIN) {}

	private async call<T>(path: string, body?: unknown): Promise<T> {
		const res = await fetch(`${this.origin}${path}`, {
			method: body === undefined ? 'GET' : 'POST',
			headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
			body: body === undefined ? undefined : JSON.stringify(body)
		});
		const data = (await res.json()) as T & { ok?: boolean; error?: string };
		if (data.ok === false) throw new Error(data.error ?? 'the pipeline refused that');
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

	learn(options: { types?: number }) {
		return this.call<{ job: JobStatus }>('/api/learn', options);
	}

	build(options: { useLearned?: boolean; includeHarvest?: boolean; source?: string }) {
		return this.call<{ job: JobStatus }>('/api/build', options);
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
