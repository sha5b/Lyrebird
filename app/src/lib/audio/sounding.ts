/**
 * Which note is sounding right now.
 *
 * The engine schedules a whole phrase at once — `onScheduled` hands over every syllable of
 * a song with its AudioContext start time, and then the audio clock runs on its own. So
 * nothing in the app knows, at any given instant, which of those notes is the one you are
 * hearing; the renderer does not need to (it draws envelopes from the same windows) but a
 * table that follows playback does.
 *
 * This is that missing reading, and it is a pure function of a window list and a time so
 * that it can be checked. The failure it exists to prevent is the plausible one: picking
 * the *first* matching window rather than the latest, which during a chorus of several
 * birds marks whichever bird started earliest and reads as the table lagging by a phrase
 * rather than as a bug.
 */

/** One scheduled note, in AudioContext seconds. */
export interface SoundingWindow {
	/** `speciesId/syllableId` — the key `inventory-rows` indexes by. */
	key: string;
	start: number;
	end: number;
}

/**
 * A bounded, append-only log of scheduled notes.
 *
 * Bounded because the global chorus schedules for as long as the app is open, and an
 * unbounded array of every note ever sung is a leak that only shows up after an hour.
 * `cap` is generous next to what can be sounding at once: a phrase is a dozen notes and
 * a handful of voices overlap, so the oldest entries are always finished.
 */
export class SoundingLog {
	private windows: SoundingWindow[] = [];
	private readonly cap: number;

	// A plain field and an assignment, not a parameter property: node's strip-only type
	// stripping refuses those, and `verify:inventory-table` imports this file directly.
	// `cluster-lookup.ts` was split out of `assets.ts` for exactly this reason.
	constructor(cap = 512) {
		this.cap = cap;
	}

	/** Records a scheduled phrase. Windows may overlap — several birds sing at once. */
	add(windows: readonly SoundingWindow[]): void {
		if (!windows.length) return;
		this.windows.push(...windows);
		if (this.windows.length > this.cap) {
			this.windows.splice(0, this.windows.length - this.cap);
		}
	}

	/** Forgets everything. Called when the audio graph is replaced by a galaxy reload. */
	clear(): void {
		this.windows.length = 0;
	}

	get size(): number {
		return this.windows.length;
	}

	/**
	 * The key of the note sounding at `now`, or `''` if none is.
	 *
	 * **The latest-starting match wins**, not the first found. Notes are appended in
	 * schedule order, which is not start order once two voices interleave, so the scan
	 * compares starts rather than trusting position. When a bird's note is still ringing
	 * as another bird begins, the newer note is the one a viewer is attending to and the
	 * one whose row should be marked.
	 */
	at(now: number): string {
		let bestKey = '';
		let bestStart = -Infinity;
		for (const w of this.windows) {
			if (now < w.start || now >= w.end) continue;
			if (w.start > bestStart) {
				bestStart = w.start;
				bestKey = w.key;
			}
		}
		return bestKey;
	}
}
