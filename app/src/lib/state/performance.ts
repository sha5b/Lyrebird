/**
 * What is being performed, and what is selected — as one value and one pure function.
 *
 * **Why this module exists, in numbers.** This machine used to be thirteen pieces of state,
 * eleven functions and seven effects in one four-thousand-line scope, with no statement
 * anywhere of who owned what. Two bugs came out of that in a single session, and neither was
 * a typo:
 *
 * - `setChorus` was written as a *toggle* (`chorus = chorus === mode ? 'off' : mode`) because
 *   a button calls it. Four effects also called it with a mode they merely wanted to be *in*,
 *   two of them raced on the same transition, and the second arrival asked for the mode
 *   already running — which the toggle read as *stop*. Measured in a browser: after selecting
 *   a phrase and clicking away, **0 songs scheduled in 14 seconds** where the aviary managed
 *   8, and it stayed stuck at 0 for every later selection.
 * - Two flags, `chorusToResume` and `resumeGlobal`, both meant "did the whole-aviary chorus
 *   have the air when this selection took it". Either could be the one consulted.
 *
 * Both are structural, so the repair is structural. Everything here is a pure function of
 * `(state, event)`; nothing in this file touches the engine, the listener, the camera or the
 * DOM. What the engine must *do* comes back as **commands, which are data** — so
 * "select a phrase from the history, then click the stage" is an assertion in
 * `verify:performance` instead of a four-minute browser probe. The probe found these bugs and
 * is worth keeping; it is far too slow to be the only net.
 *
 * ## The two rules that were never written down
 *
 * **Precedence.** A "selection" was four independent variables — `speciesId`, `songId`,
 * `selectedSung`, `pinnedCluster` — and their ordering existed only as the shape of an
 * if-chain inside `frameNodes`. It is `subjectOf` below, said once.
 *
 * **Resume.** One flag, written on the way in, read on the way back, and cleared by any
 * explicit stop — because a chorus the user deliberately ended must not come back behind
 * them.
 */

/** Which chorus is running. */
export type Chorus = 'off' | 'solo' | 'global';
/** What a one-bird chorus sings: the repertoire, or a walk of the measured grammar. */
export type SoloMode = 'songs' | 'improvise';

export interface Performance {
	chorus: Chorus;
	soloMode: SoloMode;
	/** The chosen bird, or `''` for the whole corpus. */
	speciesId: string;
	/** The chosen call, or `''` for the whole repertoire. */
	songId: string;
	/** A phrase picked out of the history strip, or `null`. */
	sungId: number | null;
	/** A pinned knot, or `-1`. */
	knot: number;
	/**
	 * Whether the whole-aviary chorus had the air when the current selection took it.
	 *
	 * The single source of the answer. Set when a selection takes the air from `global`,
	 * read when the selection is released, and cleared by every explicit stop.
	 */
	resumeGlobal: boolean;
	/**
	 * Bumped on every transition that starts or stops a chorus.
	 *
	 * Two commands are asynchronous — the corpus fetch before the aviary starts, and a
	 * species shard before a solo does — and the old code guarded them by re-reading
	 * `chorus` after the await. That works until the state has moved *and moved back*, which
	 * is exactly what a fast double click does. A command carries the epoch it was emitted
	 * at, so the executor can drop a result that belongs to a transition already superseded.
	 */
	epoch: number;
}

export function initialPerformance(): Performance {
	return {
		chorus: 'off',
		soloMode: 'songs',
		speciesId: '',
		songId: '',
		sungId: null,
		knot: -1,
		resumeGlobal: false,
		epoch: 0
	};
}

/**
 * What the picture is *about*, in the one order that was previously implicit.
 *
 * A pinned knot is a narrower question than a phrase out of the history, which is narrower
 * than one call, which is narrower than one bird, which is narrower than the corpus. The
 * camera, the backdrop and the chorus pool all have to agree about this, and before it was
 * written here each of them re-derived it.
 */
export type Subject = 'knot' | 'sung' | 'song' | 'bird' | 'corpus';

export function subjectOf(s: Performance): Subject {
	if (s.sungId !== null) return 'sung';
	if (s.knot >= 0) return 'knot';
	if (s.speciesId && s.songId) return 'song';
	if (s.speciesId) return 'bird';
	return 'corpus';
}

/** Whether anything at all is selected — the guard `clearSelection` used to spell out. */
export function hasSelection(s: Performance): boolean {
	return s.sungId !== null || s.knot >= 0 || s.speciesId !== '';
}

// --- events ------------------------------------------------------------------------

export type Event =
	/** The species picker, or a galaxy click that resolved to a bird. */
	| { k: 'chooseBird'; id: string }
	/** A click on empty space, or the same history chip twice: give the corpus back. */
	| { k: 'releaseSelection' }
	/** A knot clicked in the cloud. `speciesId` is `''` for a knot owning no bird. */
	| { k: 'pickKnot'; knot: number; speciesId: string }
	/** A row of the call dropdown. `''` is "all songs". */
	| { k: 'chooseSong'; id: string }
	/** A phrase out of the history strip. */
	| { k: 'selectSung'; sungId: number; speciesId: string }
	/** A chorus button. Asking for the mode already running stops it. */
	| { k: 'pressChorus'; mode: 'solo' | 'global' }
	/** A programmatic move into a mode. Never stops anything by being asked twice. */
	| { k: 'setChorus'; mode: Chorus }
	/** The Songs / Improvise pair. */
	| { k: 'setSoloMode'; mode: SoloMode }
	/** An explicit stop: the Compose tab taking over, or a galaxy reload. */
	| { k: 'stop' };

// --- commands ----------------------------------------------------------------------

/**
 * What the engine and the view must do. Data, never a callback — that is the whole point:
 * a test can read the list, and the executor is the only code that needs an engine.
 */
export type Command =
	/** Cut notes already posted to the worklet. Only ever when a chorus was running. */
	| { k: 'panic' }
	/** Stop the ambient scheduler. Does not cut what is already sounding. */
	| { k: 'stopAmbient' }
	/** Drop the live trajectories, so no highlight animates through a note that will not sound. */
	| { k: 'clearPaths' }
	/** Fetch every species in one request, then start the aviary if `epoch` still holds. */
	| { k: 'startGlobal'; epoch: number }
	/** Fetch this bird's shard, then start its chorus if `epoch` still holds. */
	| { k: 'startSolo'; speciesId: string; epoch: number }
	/** Draw this bird's backdrop threads; `''` clears them. */
	| { k: 'showContext'; speciesId: string }
	/** Redraw the selected call's thread and its species backdrop. */
	| { k: 'refreshSelection' };

export interface Step {
	state: Performance;
	commands: Command[];
}

// --- the reducer -------------------------------------------------------------------

/**
 * One transition. Pure, total, and the only place `chorus` changes.
 *
 * `setChorus` **sets**; only `pressChorus` may stop a chorus by asking for the mode already
 * running. That distinction is the first of the two bugs above, and keeping the two events
 * separate is what makes it impossible to reintroduce: a programmatic caller has no event
 * available to it that toggles.
 */
export function reduce(s: Performance, e: Event): Step {
	switch (e.k) {
		case 'chooseBird': {
			if (!e.id) return reduce(s, { k: 'releaseSelection' });
			if (e.id === s.speciesId) return { state: s, commands: [] };
			// A different bird while a solo chorus runs: re-pool for it and keep going. The
			// in-flight notes are the previous bird's, and only its own species may be heard
			// in solo, so they are cut.
			if (s.chorus === 'solo') {
				const state = { ...s, speciesId: e.id, songId: '', epoch: s.epoch + 1 };
				return {
					state,
					commands: [
						{ k: 'panic' },
						{ k: 'startSolo', speciesId: e.id, epoch: state.epoch },
						{ k: 'refreshSelection' }
					]
				};
			}
			// Taking the air from the aviary, or from silence. Note what to give back to.
			const resumeGlobal = s.chorus === 'global';
			const cut: Command[] = s.chorus === 'off' ? [] : [{ k: 'panic' }];
			const next = enter({ ...s, speciesId: e.id, songId: '', resumeGlobal }, 'solo');
			return { state: next.state, commands: [...cut, ...next.commands] };
		}

		case 'releaseSelection': {
			// Nothing selected is not a transition. The old guard read the same three
			// variables in the same order and lived in `clearSelection`.
			if (!hasSelection(s)) return { state: s, commands: [] };
			const cleared = { ...s, speciesId: '', songId: '', sungId: null, knot: -1 };
			// **The bug this ordering fixes.** Releasing a selection used to be handled in
			// two places at once — `clearSelection` resumed the aviary by hand *and* the
			// species effect resumed it a tick later — and the second call stopped what the
			// first had started. There is one path now, and it is this one.
			if (s.chorus !== 'solo') {
				return { state: cleared, commands: [{ k: 'refreshSelection' }] };
			}
			return cleared.resumeGlobal
				? enter({ ...cleared, resumeGlobal: false }, 'global')
				: enter({ ...cleared, resumeGlobal: false }, 'off');
		}

		case 'pickKnot': {
			// Clicking the pinned knot again releases it, which is the toggle the old
			// `pickCluster` spelled out inline.
			const knot = s.knot === e.knot ? -1 : e.knot;
			// A knot belonging to a bird selects that bird as well: a narrower question
			// implies the broader one. A knot owning no species leaves the bird alone.
			if (knot >= 0 && e.speciesId && e.speciesId !== s.speciesId) {
				const picked = reduce({ ...s, knot }, { k: 'chooseBird', id: e.speciesId });
				return picked;
			}
			return { state: { ...s, knot }, commands: [{ k: 'showContext', speciesId: e.speciesId }] };
		}

		case 'chooseSong': {
			// The pin and the history phrase both outrank a call, so leaving either in place
			// would make choosing a call do visibly nothing.
			const state = { ...s, songId: e.id, sungId: null, knot: -1, epoch: s.epoch + 1 };
			const commands: Command[] = [];
			// Releasing a pin has to redraw the backdrop by hand: `showContext` narrows to the
			// pinned knot's own threads and nothing else recomputes it once the pin is gone.
			if (s.knot >= 0 && state.speciesId) {
				commands.push({ k: 'showContext', speciesId: state.speciesId });
			}
			// The pool follows the chosen call, so a running solo chorus re-pools.
			if (state.chorus === 'solo' && state.speciesId) {
				commands.push({ k: 'startSolo', speciesId: state.speciesId, epoch: state.epoch });
			}
			commands.push({ k: 'refreshSelection' });
			return { state, commands };
		}

		case 'selectSung': {
			// The same chip twice clears it, the same as clicking empty space.
			if (s.sungId === e.sungId) return reduce(s, { k: 'releaseSelection' });
			const withSung = { ...s, sungId: e.sungId };
			// Selecting a phrase also selects its bird, so the chorus follows it.
			return reduce(withSung, { k: 'chooseBird', id: e.speciesId });
		}

		case 'pressChorus':
			return s.chorus === e.mode ? reduce(s, { k: 'stop' }) : enter(s, e.mode);

		case 'setChorus':
			return enter(s, e.mode);

		case 'setSoloMode': {
			if (s.soloMode === e.mode) return { state: s, commands: [] };
			const state = { ...s, soloMode: e.mode, epoch: s.epoch + 1 };
			if (state.chorus !== 'solo' || !state.speciesId) return { state, commands: [] };
			// Switching mode has to stop the ambient scheduler in one direction and start it
			// in the other; `startSolo` does nothing for `improvise`, whose phrases are driven
			// by a timer in the page rather than by the engine's own scheduler.
			return {
				state,
				commands: [
					{ k: 'stopAmbient' },
					{ k: 'startSolo', speciesId: state.speciesId, epoch: state.epoch }
				]
			};
		}

		case 'stop':
			// An explicit stop clears the resume flag, so a chorus the user ended does not
			// come back behind them on the next deselect.
			return {
				state: { ...s, chorus: 'off', resumeGlobal: false, epoch: s.epoch + 1 },
				commands: [{ k: 'panic' }, { k: 'stopAmbient' }, { k: 'clearPaths' }, { k: 'showContext', speciesId: '' }, { k: 'refreshSelection' }]
			};
	}
}

/**
 * Move into a mode. The only writer of `chorus`, and never a toggle.
 *
 * `global` drops the whole selection: the aviary is the subject, and nothing should still be
 * claiming to be it — which is also the only framing in which a chorus of twelve birds makes
 * sense.
 */
function enter(s: Performance, mode: Chorus): Step {
	const epoch = s.epoch + 1;
	const base: Command[] = [{ k: 'stopAmbient' }, { k: 'clearPaths' }];

	if (mode === 'off') {
		return {
			state: { ...s, chorus: 'off', resumeGlobal: false, epoch },
			commands: [...base, { k: 'showContext', speciesId: '' }, { k: 'refreshSelection' }]
		};
	}
	if (mode === 'global') {
		return {
			state: { ...s, chorus: 'global', speciesId: '', songId: '', sungId: null, knot: -1, epoch },
			commands: [...base, { k: 'showContext', speciesId: '' }, { k: 'startGlobal', epoch }]
		};
	}
	return {
		state: { ...s, chorus: 'solo', epoch },
		commands: [...base, { k: 'startSolo', speciesId: s.speciesId, epoch }]
	};
}

/** Runs a list of events, for a test or a replay. */
export function reduceAll(s: Performance, events: Event[]): Step {
	const commands: Command[] = [];
	let state = s;
	for (const e of events) {
		const step = reduce(state, e);
		state = step.state;
		commands.push(...step.commands);
	}
	return { state, commands };
}
