/**
 * The chorus and selection machine.
 *
 * **Both bugs this exists to prevent were measured in a browser, not read off a diff**, and
 * each took about four minutes to reproduce: drive the app, fill the history strip, click a
 * chip, click away, then sample the voice count for fourteen seconds. That probe is worth
 * keeping and is far too slow to be the only net. Every scenario below is the same question
 * asked in milliseconds.
 *
 * The two failures, restated as the assertions that would have caught them:
 *
 *  1. **`setChorus` was a toggle.** It read `chorus = chorus === mode ? 'off' : mode` because
 *     a button calls it, and four effects called it with a mode they merely wanted to be in.
 *     Two raced, and the second arrival asked for the mode already running — read as *stop*.
 *     Here: `setChorus` is idempotent into a mode, `pressChorus` is the only event that
 *     stops one by asking twice, and no sequence of programmatic events can reach `off`
 *     without an explicit `stop`.
 *  2. **Two flags meant one thing.** `chorusToResume` and `resumeGlobal` both answered "did
 *     the aviary have the air when this selection took it", and either could be the one
 *     consulted. Here: releasing a selection resumes exactly once, and an explicit stop
 *     survives the round trip.
 *
 * Run with `npm run verify:performance`. Exits non-zero on any disagreement.
 */
import {
	initialPerformance,
	reduce,
	reduceAll,
	subjectOf,
	hasSelection
} from '../src/lib/state/performance.ts';

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(58)} ok${detail ? ` (${detail})` : ''}`);
	else {
		failures++;
		console.error(`  ${name.padEnd(58)} FAIL ${detail}`);
	}
};
/** Command kinds in order, as a string — the shape a transition asks the engine for. */
const cmds = (step) => step.commands.map((c) => c.k).join(',');
const has = (step, kind) => step.commands.some((c) => c.k === kind);
const run = (events, from = initialPerformance()) => reduceAll(from, events);

// --- the regression that started this ------------------------------------------------
console.log('the deselect that went silent');

{
	// The exact reported path: aviary running, pick a phrase out of the history, click away.
	const aviary = run([{ k: 'pressChorus', mode: 'global' }]);
	ok('the aviary starts', aviary.state.chorus === 'global', aviary.state.chorus);
	ok('and it asks the engine to start', has(aviary, 'startGlobal'), cmds(aviary));

	const picked = reduce(aviary.state, { k: 'selectSung', sungId: 7, speciesId: 'sp_a' });
	ok('a history phrase takes the air for its bird', picked.state.chorus === 'solo');
	ok('the phrase is the subject', subjectOf(picked.state) === 'sung', subjectOf(picked.state));
	ok('and the aviary is noted for the way back', picked.state.resumeGlobal === true);
	ok('in-flight notes are cut', has(picked, 'panic'), cmds(picked));

	const away = reduce(picked.state, { k: 'releaseSelection' });
	ok('clicking away drops the whole selection', !hasSelection(away.state));
	// **This is the bug.** It used to end at `off` because two paths both resumed and the
	// second ask stopped the first. Measured in the browser as 0 songs in 14 s.
	ok('the aviary comes back', away.state.chorus === 'global', away.state.chorus);
	ok('and it is actually restarted', has(away, 'startGlobal'), cmds(away));
	ok('the resume flag is spent', away.state.resumeGlobal === false);

	// It stayed stuck, so the next selection has to work too.
	const again = reduce(away.state, { k: 'chooseBird', id: 'sp_b' });
	ok('the next selection still sings', again.state.chorus === 'solo', again.state.chorus);
	ok('and it re-notes the aviary', again.state.resumeGlobal === true);
}

{
	// From silence, a selection must not resume anything on the way out: an explicit stop
	// survives the round trip.
	const s = run([
		{ k: 'pressChorus', mode: 'global' },
		{ k: 'stop' },
		{ k: 'chooseBird', id: 'sp_a' },
		{ k: 'releaseSelection' }
	]);
	ok('a stop the user asked for survives a selection', s.state.chorus === 'off', s.state.chorus);
}

// --- the toggle that must not be reachable programmatically --------------------------
console.log('\nsetting a mode is not toggling it');

{
	const a = run([{ k: 'setChorus', mode: 'global' }]);
	const b = reduce(a.state, { k: 'setChorus', mode: 'global' });
	ok('setChorus into the running mode keeps it', b.state.chorus === 'global', b.state.chorus);
	ok('and still re-arms the engine', has(b, 'startGlobal'), cmds(b));
	const c = reduce(b.state, { k: 'pressChorus', mode: 'global' });
	ok('pressing the running mode stops it', c.state.chorus === 'off', c.state.chorus);
	ok('a stop cuts the voices', has(c, 'panic'), cmds(c));

	// The invariant, swept: no run of programmatic events can reach `off`.
	const PROG = [
		{ k: 'setChorus', mode: 'global' },
		{ k: 'setChorus', mode: 'solo' },
		{ k: 'chooseBird', id: 'sp_a' },
		{ k: 'chooseBird', id: 'sp_b' },
		{ k: 'chooseSong', id: 'song1' },
		{ k: 'setSoloMode', mode: 'improvise' },
		{ k: 'setSoloMode', mode: 'songs' },
		{ k: 'pickKnot', knot: 3, speciesId: 'sp_a' }
	];
	let silentRuns = 0;
	for (let i = 0; i < PROG.length; i++)
		for (let j = 0; j < PROG.length; j++)
			for (let k = 0; k < PROG.length; k++) {
				const r = run([{ k: 'setChorus', mode: 'global' }, PROG[i], PROG[j], PROG[k]]);
				if (r.state.chorus === 'off') silentRuns++;
			}
	ok('no programmatic sequence silences the chorus', silentRuns === 0, `${silentRuns} of 512 did`);
}

// --- precedence, said once ------------------------------------------------------------
console.log('\nwhat the picture is about');

{
	const s = initialPerformance();
	ok('nothing selected is the corpus', subjectOf(s) === 'corpus');
	ok('a bird', subjectOf({ ...s, speciesId: 'sp_a' }) === 'bird');
	ok('a call is narrower than its bird',
		subjectOf({ ...s, speciesId: 'sp_a', songId: 'x' }) === 'song');
	ok('a knot is narrower than a call',
		subjectOf({ ...s, speciesId: 'sp_a', songId: 'x', knot: 4 }) === 'knot');
	ok('a history phrase outranks even a knot',
		subjectOf({ ...s, speciesId: 'sp_a', songId: 'x', knot: 4, sungId: 1 }) === 'sung');
	// A call id with no bird is not a subject: `songId` is only meaningful under a species.
	ok('a call with no bird is still the corpus', subjectOf({ ...s, songId: 'x' }) === 'corpus');
}

// --- choosing things clears what they outrank ----------------------------------------
console.log('\na narrower choice replaces a broader one');

{
	const pinned = run([
		{ k: 'setChorus', mode: 'solo' },
		{ k: 'chooseBird', id: 'sp_a' },
		{ k: 'pickKnot', knot: 9, speciesId: 'sp_a' }
	]);
	ok('a knot pins', pinned.state.knot === 9, String(pinned.state.knot));
	const song = reduce(pinned.state, { k: 'chooseSong', id: 'song2' });
	ok('choosing a call releases the pin', song.state.knot === -1);
	ok('and redraws the backdrop the pin had narrowed', has(song, 'showContext'), cmds(song));
	ok('and re-pools a running chorus', has(song, 'startSolo'), cmds(song));

	const same = reduce(pinned.state, { k: 'pickKnot', knot: 9, speciesId: 'sp_a' });
	ok('the same knot again releases it', same.state.knot === -1);

	// A knot belonging to another bird selects that bird too.
	const other = reduce(pinned.state, { k: 'pickKnot', knot: 12, speciesId: 'sp_b' });
	ok('a knot of another bird takes the bird with it', other.state.speciesId === 'sp_b',
		other.state.speciesId);
	// A knot owning no species must not clear the bird.
	const orphan = reduce(pinned.state, { k: 'pickKnot', knot: 30, speciesId: '' });
	ok('a knot with no bird leaves the bird alone', orphan.state.speciesId === 'sp_a');
}

{
	// Changing bird drops the call: a call id is species-local, and `learned_bout` is a
	// universal id, so a stale selection often stays *valid* and frames the wrong thing.
	const s = run([
		{ k: 'chooseBird', id: 'sp_a' },
		{ k: 'chooseSong', id: 'learned_bout' },
		{ k: 'chooseBird', id: 'sp_b' }
	]);
	ok('a change of bird opens on the whole repertoire', s.state.songId === '', s.state.songId);
}

{
	const s = run([{ k: 'pressChorus', mode: 'global' }, { k: 'chooseBird', id: 'sp_a' }]);
	ok('choosing a bird ends the aviary framing', s.state.speciesId === 'sp_a');
	const g = reduce(s.state, { k: 'setChorus', mode: 'global' });
	ok('the aviary drops the bird', g.state.speciesId === '');
	ok('the aviary drops the pin and the phrase',
		g.state.knot === -1 && g.state.sungId === null);
}

// --- the two solo modes ---------------------------------------------------------------
console.log('\nsongs and improvise');

{
	const solo = run([{ k: 'chooseBird', id: 'sp_a' }]);
	ok('a bird sings its songs by default', solo.state.soloMode === 'songs');
	const imp = reduce(solo.state, { k: 'setSoloMode', mode: 'improvise' });
	ok('switching mode stops the ambient scheduler', has(imp, 'stopAmbient'), cmds(imp));
	ok('and re-enters solo for the new mode', has(imp, 'startSolo'), cmds(imp));
	const again = reduce(imp.state, { k: 'setSoloMode', mode: 'improvise' });
	ok('asking for the mode already set does nothing', cmds(again) === '', cmds(again));
	// The mode is remembered across a stop, which is what a segmented control implies.
	const back = run([{ k: 'stop' }, { k: 'chooseBird', id: 'sp_b' }], imp.state);
	ok('the mode survives a stop', back.state.soloMode === 'improvise', back.state.soloMode);
}

// --- every command a transition asks for is one the executor knows -------------------
console.log('\ncommands');

{
	const KNOWN = new Set(['panic','stopAmbient','clearPaths','startGlobal','startSolo',
	                       'showContext','refreshSelection']);
	const ALL = [
		{ k: 'chooseBird', id: 'sp_a' }, { k: 'releaseSelection' },
		{ k: 'pickKnot', knot: 1, speciesId: 'sp_a' }, { k: 'chooseSong', id: 's' },
		{ k: 'selectSung', sungId: 1, speciesId: 'sp_a' }, { k: 'pressChorus', mode: 'solo' },
		{ k: 'pressChorus', mode: 'global' }, { k: 'setChorus', mode: 'off' },
		{ k: 'setChorus', mode: 'solo' }, { k: 'setChorus', mode: 'global' },
		{ k: 'setSoloMode', mode: 'improvise' }, { k: 'stop' }
	];
	let unknown = [], epochBad = [];
	for (const a of ALL) for (const b of ALL) {
		const r = run([a, b]);
		for (const c of r.commands) {
			if (!KNOWN.has(c.k)) unknown.push(c.k);
			// An async command must carry the epoch it belongs to, or a superseded result
			// cannot be told from a current one.
			if ((c.k === 'startGlobal' || c.k === 'startSolo') && typeof c.epoch !== 'number')
				epochBad.push(c.k);
		}
	}
	ok('no transition emits an unknown command', unknown.length === 0, [...new Set(unknown)].join(','));
	ok('every async command carries its epoch', epochBad.length === 0, [...new Set(epochBad)].join(','));

	// A transition that starts or stops a chorus must move the epoch, or a stale async
	// result would be accepted as current.
	let stale = 0;
	for (const a of ALL) {
		const before = run([{ k: 'setChorus', mode: 'global' }]).state;
		const after = reduce(before, a);
		const changed = after.state.chorus !== before.chorus ||
		                after.commands.some((c) => c.k === 'startGlobal' || c.k === 'startSolo');
		if (changed && after.state.epoch === before.epoch) stale++;
	}
	ok('starting or stopping always moves the epoch', stale === 0, `${stale} did not`);
}

// --- totality -------------------------------------------------------------------------
console.log('\ntotality');

{
	// The reducer must be total: no event on any reachable state may throw or return a
	// state missing a field. Swept over three-event runs from every mode.
	const KEYS = Object.keys(initialPerformance());
	const ALL = [
		{ k: 'chooseBird', id: 'sp_a' }, { k: 'chooseBird', id: '' }, { k: 'releaseSelection' },
		{ k: 'pickKnot', knot: 2, speciesId: '' }, { k: 'chooseSong', id: '' },
		{ k: 'selectSung', sungId: 3, speciesId: 'sp_c' }, { k: 'pressChorus', mode: 'solo' },
		{ k: 'setChorus', mode: 'off' }, { k: 'setSoloMode', mode: 'songs' }, { k: 'stop' }
	];
	let bad = 0, threw = 0, epochs = 0;
	for (const a of ALL) for (const b of ALL) for (const c of ALL) {
		try {
			const r = run([a, b, c]);
			if (KEYS.some((k) => r.state[k] === undefined)) bad++;
			if (r.state.epoch < 0) epochs++;
		} catch { threw++; }
	}
	ok('no event sequence throws', threw === 0, `${threw} of 1000 threw`);
	ok('no event sequence loses a field', bad === 0, `${bad} of 1000 did`);
	ok('the epoch only ever moves forward', epochs === 0);
	// `chooseBird('')` is a release, so it must behave as one.
	const rel = run([{ k: 'chooseBird', id: 'sp_a' }, { k: 'chooseBird', id: '' }]);
	ok('choosing no bird releases the selection', !hasSelection(rel.state));
}

console.log(failures ? `\n${failures} failure(s)` : '\nall checks passed');
process.exit(failures ? 1 : 0);
