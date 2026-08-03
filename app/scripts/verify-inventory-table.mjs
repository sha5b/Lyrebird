/**
 * The inventory table's arithmetic, and the cursor that drives it.
 *
 * **Neither half fails loudly.** A windowed list with an off-by-one in `first` draws the
 * right number of rows in the wrong places — it looks like a working table until the row
 * you are looking for is one line above where it highlights. A `padTop` that disagrees
 * with `first` looks correct at the top of the list and drifts as you scroll, which reads
 * as a rendering glitch rather than as arithmetic. And the cursor's failure is the worst
 * of the three: picking the first matching window rather than the latest marks whichever
 * bird in a chorus started earliest, which reads as the table lagging a phrase behind.
 *
 * So all three are pure functions and all three are checked here:
 *  - `buildInventoryRows` — the inventory's own order, a species with no shard loaded
 *    contributing nothing, and blank rather than invented numbers on a documented call;
 *  - `rowWindow` — every drawn row is inside the window, the spacers plus the slice sum
 *    to the full scroll height, and the edges are clamped;
 *  - `followRow` — a row already comfortably visible does not move the list, one that has
 *    left the band is centred, and the scroll cannot run past either end;
 *  - `SoundingLog` — the latest-starting note wins, a finished note is not sounding, and
 *    the log stays bounded.
 *
 * Two more, added when the table stopped calling a fitted type `L33`:
 *  - `syllable-name` — and the check that matters here is not legibility but **honesty**: a
 *    documented call keeps the name its sources gave it, a fitted one is described by its
 *    form, and no word in a described name may be a functional claim. That last one is a
 *    blunt scan against a forbidden list, deliberately: if `alarm` or `contact` ever enters
 *    the vocabulary, this fails rather than shipping a claim with no source behind it.
 *
 * Run with `npm run verify:inventory-table`. Exits non-zero on any disagreement.
 */
import {
	buildInventoryRows,
	indexRows,
	rowWindow,
	followRow
} from '../src/lib/data/inventory-rows.ts';
import { SoundingLog } from '../src/lib/audio/sounding.ts';
import {
	contourShape,
	describeForm,
	formatPitch,
	medianPitch,
	nameSource,
	syllableName,
	toneWords
} from '../src/lib/data/syllable-name.ts';

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(52)} ok${detail ? ` (${detail})` : ''}`);
	else {
		failures++;
		console.error(`  ${name.padEnd(52)} FAIL ${detail}`);
	}
};

// --- rows ------------------------------------------------------------------------
console.log('the rows');

const syl = (id, extra = {}) => ({
	id,
	label: `call ${id}`,
	function: '',
	confidence: 'documented',
	refs: [],
	dur: 0.25,
	level: 1,
	timbre: 'pure',
	contour: [],
	...extra
});

const inventory = {
	version: 1,
	note: '',
	refs: {},
	banks: {},
	species: [
		{
			id: 'sp_b',
			common: 'Bird B',
			scientific: '',
			bank: '',
			summary: '',
			songs: [],
			syllables: [syl('A'), syl('L01', { learned: { members: 31, resynthesisCosine: 0.812 } })]
		},
		{
			id: 'sp_a',
			common: 'Bird A',
			scientific: '',
			bank: '',
			summary: '',
			songs: [],
			syllables: [syl('B')]
		}
	]
};

// The build's order, deliberately the opposite of the array order above: the table has to
// follow the index every picker in the app follows, not whichever shard happened to land
// first. A shard that has not arrived (`sp_c`) is in the index and holds no entry.
const order = [
	{ id: 'sp_a', common: 'Bird A' },
	{ id: 'sp_b', common: 'Bird B' },
	{ id: 'sp_c', common: 'Bird C' }
];

// Two of the three types are placed; `sp_b/A` is not, which is the type-coverage shortfall
// the table is the only surface in the app that admits to.
const placed = { 'sp_b/L01': 0, 'sp_a/B': 1 };
const knotOf = (sp, syl) => placed[`${sp}/${syl}`] ?? -1;

const rows = buildInventoryRows(inventory, order, knotOf);

ok('a species with no shard contributes no rows', rows.length === 3, `got ${rows.length}`);
ok(
	'rows follow the build order, not the array order',
	rows.map((r) => r.key).join(' ') === 'sp_a/B sp_b/A sp_b/L01',
	rows.map((r) => r.key).join(' ')
);
ok('a fitted syllable carries its fit', rows[2].cosine === 0.812 && rows[2].members === 31);
ok(
	'a documented call carries no fit at all',
	rows[0].cosine === null && rows[0].members === null && rows[0].fitted === false
);
ok('a placed type carries its knot', rows[2].knot === 0 && rows[1].knot === -1,
	`L01 -> ${rows[2].knot}, A -> ${rows[1].knot}`);
ok('duration is whole milliseconds', rows[0].durMs === 250, `got ${rows[0].durMs}`);

const index = indexRows(rows);
ok('every row is reachable by its key', index.get('sp_b/L01') === 2 && index.get('sp_a/B') === 0);
ok('a key that never sang is absent', index.get('sp_z/Q') === undefined);
// Without a lookup — a corpus with no clusters at all — every row still exists and is
// honestly marked as placed nowhere, rather than the table being empty.
const unplaced = buildInventoryRows(inventory, order, null);
ok('no lookup still yields rows, all unplaced',
	unplaced.length === 3 && unplaced.every((r) => r.knot === -1));

// --- the window ------------------------------------------------------------------
console.log('\nthe window');

const ROW = 24;
const VIEW = 600;
const TOTAL = 13748;

{
	const w = rowWindow(0, VIEW, ROW, TOTAL);
	ok('at the top the window starts at 0', w.first === 0, `got ${w.first}`);
	ok('the top window has no padding above it', w.padTop === 0);
}

// The invariant that matters: whatever the offset, the spacers plus the drawn rows are
// exactly the height the scrollbar is measuring. If they are not, the list drifts.
let heightsAgree = true;
let rowsCovered = true;
for (const top of [0, 1, 23, 24, 25, 600, 1000, 12345, TOTAL * ROW - VIEW, TOTAL * ROW]) {
	const w = rowWindow(top, VIEW, ROW, TOTAL);
	const total = w.padTop + (w.end - w.first) * ROW + w.padBottom;
	if (total !== TOTAL * ROW) {
		heightsAgree = false;
		console.error(`    at scrollTop ${top}: ${total} != ${TOTAL * ROW}`);
	}
	// Every row the viewport actually exposes has to be inside [first, end).
	const firstSeen = Math.floor(Math.min(top, (TOTAL - 1) * ROW) / ROW);
	const lastSeen = Math.min(TOTAL - 1, Math.floor((Math.min(top, TOTAL * ROW) + VIEW) / ROW));
	if (firstSeen < w.first || lastSeen >= w.end) {
		rowsCovered = false;
		console.error(`    at scrollTop ${top}: sees ${firstSeen}..${lastSeen}, draws ${w.first}..${w.end - 1}`);
	}
}
ok('spacers plus slice always equal the scroll height', heightsAgree);
ok('every visible row is inside the drawn window', rowsCovered);

{
	const w = rowWindow(-500, VIEW, ROW, TOTAL);
	ok('a negative offset clamps to the top', w.first === 0 && w.padTop === 0);
}
{
	// One frame after the row count drops, scrollTop can still be past the new end.
	const w = rowWindow(999999, VIEW, ROW, 10);
	ok('an offset past the end stays inside the rows',
		w.first <= 10 && w.end <= 10 && w.padBottom >= 0, `${w.first}..${w.end}`);
}
{
	const w = rowWindow(0, VIEW, ROW, 0);
	ok('an empty list draws nothing', w.first === 0 && w.end === 0 && w.padTop === 0);
}

// --- following playback ----------------------------------------------------------
console.log('\nfollowing playback');

// A row in the middle of the viewport is comfortable, and the list must not twitch.
ok('a centred row does not move the list', followRow(30, 30 * ROW - 288, VIEW, ROW, TOTAL) === null);
ok('no sounding row does not move the list', followRow(-1, 0, VIEW, ROW, TOTAL) === null);
ok('a row past the end does not move the list', followRow(TOTAL, 0, VIEW, ROW, TOTAL) === null);

{
	// A row far below: centred, and the maths says where.
	const to = followRow(1000, 0, VIEW, ROW, TOTAL);
	const expected = 1000 * ROW - (VIEW - ROW) / 2;
	ok('a row below the band is centred', to === expected, `got ${to}, expected ${expected}`);
}
{
	const to = followRow(2, 5000, VIEW, ROW, TOTAL);
	ok('a row above the band scrolls back and clamps at 0', to === 0, `got ${to}`);
}
{
	const to = followRow(TOTAL - 1, 0, VIEW, ROW, TOTAL);
	ok('the last row cannot scroll past the end', to === TOTAL * ROW - VIEW, `got ${to}`);
}
{
	// band = 1 means "only when fully out of the viewport", which is the loosest setting.
	// A row just inside the bottom edge is left alone at band 1 and pulled at band 0.5.
	const justInside = Math.floor(VIEW / ROW) - 1;
	ok('a wider band leaves an edge row alone',
		followRow(justInside, 0, VIEW, ROW, TOTAL, 1) === null);
	ok('the default band pulls the same row back',
		followRow(justInside, 0, VIEW, ROW, TOTAL, 0.5) !== null);
}

// --- the cursor -------------------------------------------------------------------
console.log('\nthe sounding cursor');

{
	const log = new SoundingLog();
	log.add([
		{ key: 'sp_a/A', start: 0, end: 1 },
		{ key: 'sp_a/B', start: 1, end: 2 }
	]);
	ok('nothing sounds before the first note', log.at(-0.5) === '');
	ok('the first note sounds inside its window', log.at(0.5) === 'sp_a/A');
	// Half-open: the instant a note ends is the instant the next one starts, and exactly
	// one of them may be sounding at it.
	ok('a window is half-open at its end', log.at(1) === 'sp_a/B');
	ok('nothing sounds after the last note', log.at(2) === '');
}

{
	// The failure this exists to prevent. Bird A is holding a long note; bird B starts a
	// short one inside it. The newer note is the one to mark — and it is second in the
	// array, so a scan that stops at the first match gets this wrong.
	const log = new SoundingLog();
	log.add([{ key: 'sp_a/long', start: 0, end: 10 }]);
	log.add([{ key: 'sp_b/short', start: 4, end: 5 }]);
	ok('the latest-starting overlapping note wins', log.at(4.5) === 'sp_b/short',
		`got ${log.at(4.5)}`);
	ok('the held note resumes when the newer one ends', log.at(6) === 'sp_a/long');
}

{
	// Appended out of start order, which is what interleaved voices produce.
	const log = new SoundingLog();
	log.add([{ key: 'late', start: 5, end: 9 }]);
	log.add([{ key: 'early', start: 1, end: 9 }]);
	ok('start time decides, not position in the log', log.at(6) === 'late', `got ${log.at(6)}`);
}

{
	const log = new SoundingLog(4);
	for (let i = 0; i < 20; i++) log.add([{ key: `n${i}`, start: i, end: i + 1 }]);
	ok('the log stays bounded', log.size === 4, `got ${log.size}`);
	ok('the newest notes are the ones kept', log.at(19.5) === 'n19');
	ok('the oldest are forgotten', log.at(0.5) === '');
	log.clear();
	ok('clearing empties it', log.size === 0 && log.at(19.5) === '');
}

{
	const log = new SoundingLog();
	log.add([]);
	ok('an empty phrase is not recorded', log.size === 0);
}

// --- naming a type nobody named -----------------------------------------------------
console.log('\nnaming');

// **The rule this whole module exists to keep.** A documented call is named by the
// literature, with a citation; a fitted one has no source and must never be given a name
// that reads like one. Checked first because it is the only check here that is about
// honesty rather than about legibility.
{
	const documented = syl('jar', { label: 'jar note', confidence: 'documented', refs: ['suzuki2014'] });
	ok('a documented call keeps its source\'s name', syllableName(documented) === 'jar note',
		syllableName(documented));
	ok('and is marked as documented', nameSource(documented) === 'documented');

	const fitted = syl('L33', {
		label: 'learned L33 · 554 Hz · 29 ms',
		confidence: 'unlabelled',
		dur: 0.0293,
		timbre: 'buzz',
		contour: [[0, 554.7], [1, 552.6]],
		am: 140,
		amDepth: 0.8,
		learned: { members: 1, resynthesisCosine: 0.79 }
	});
	ok('a fitted type is described, not named', syllableName(fitted) !== fitted.label,
		syllableName(fitted));
	ok('and is marked as fitted', nameSource(fitted) === 'fitted');
	ok('the description is form only', describeForm(fitted) === 'buzzy rattling flat',
		describeForm(fitted));
	// No word in a described name may be a functional claim. This is a blunt check and that
	// is the point: if someone adds "alarm" or "contact" to the vocabulary it fails here.
	const FORBIDDEN = ['alarm', 'contact', 'song', 'call', 'mate', 'warning', 'threat', 'begging'];
	const words = describeForm(fitted).split(/[\s,]+/);
	ok('no functional word in a described name', !words.some((w) => FORBIDDEN.includes(w)),
		describeForm(fitted));
}

// The shape read off the pitch track. A two-point contour that does not move is flat, and
// most of the corpus is exactly that, so getting it wrong would mislabel thousands of rows.
{
	const shape = (contour) => contourShape({ contour });
	ok('a level track is flat', shape([[0, 1000], [1, 1000]]) === 'flat');
	ok('a track with no points is flat', shape([]) === 'flat');
	ok('a rising track rises', shape([[0, 1000], [1, 1300]]) === 'rise',
		shape([[0, 1000], [1, 1300]]));
	ok('a falling track falls', shape([[0, 1300], [1, 1000]]) === 'fall',
		shape([[0, 1300], [1, 1000]]));
	ok('an octave up is steep', shape([[0, 500], [1, 1000]]) === 'steep rise',
		shape([[0, 500], [1, 1000]]));
	// Under the sweep threshold nothing is claimed: a semitone of drift is not a shape.
	ok('a semitone of drift is not a sweep', shape([[0, 1000], [1, 1050]]) === 'flat',
		shape([[0, 1000], [1, 1050]]));
	ok('a peak in the middle arches', shape([[0, 1000], [0.5, 1600], [1, 1000]]) === 'arch',
		shape([[0, 1000], [0.5, 1600], [1, 1000]]));
	ok('a trough in the middle dips', shape([[0, 1600], [0.5, 1000], [1, 1600]]) === 'dip',
		shape([[0, 1600], [0.5, 1000], [1, 1600]]));
	ok('a bent sweep says both', shape([[0, 1000], [0.5, 1900], [1, 1500]]) === 'rise, arching',
		shape([[0, 1000], [0.5, 1900], [1, 1500]]));
}

// At most one modulation word. The corpus's own distribution put four types in five in the
// "trilled" band before the thresholds were raised, and a word every row carries describes
// nothing.
{
	const tone = (extra) => toneWords({ timbre: 'pure', dur: 0.1, contour: [], ...extra });
	ok('timbre alone gives one word', tone({}).join(' ') === 'clear', tone({}).join(' '));
	ok('shallow modulation earns no word', tone({ am: 140, amDepth: 0.15 }).join(' ') === 'clear',
		tone({ am: 140, amDepth: 0.15 }).join(' '));
	ok('fast deep AM rattles', tone({ am: 140, amDepth: 0.8 }).join(' ') === 'clear rattling');
	ok('slow deep AM trills', tone({ am: 12, amDepth: 0.8 }).join(' ') === 'clear trilled');
	ok('deep vibrato warbles', tone({ vib: { rate: 4, depth: 0.4 } }).join(' ') === 'clear warbling');
	ok('never two modulation words',
		tone({ am: 140, amDepth: 0.8, vib: { rate: 4, depth: 0.4 }, two: true }).length === 2,
		tone({ am: 140, amDepth: 0.8, vib: { rate: 4, depth: 0.4 }, two: true }).join(' '));
	ok('two voices only when nothing louder is happening',
		tone({ two: true }).join(' ') === 'clear two-voiced');
	ok('shallow vibrato does not displace two voices',
		tone({ two: true, vib: { rate: 4, depth: 0.01 } }).join(' ') === 'clear two-voiced');
}

// Pitch, in the unit a reader thinks in.
{
	ok('median of an odd track', medianPitch({ contour: [[0, 100], [0.5, 900], [1, 200]] }) === 200);
	ok('median of an even track', medianPitch({ contour: [[0, 100], [1, 300]] }) === 200);
	ok('a zero in the track is ignored',
		medianPitch({ contour: [[0, 0], [0.5, 400], [1, 400]] }) === 400);
	ok('no track is no pitch', medianPitch({ contour: [] }) === 0);
	ok('under a kilohertz reads in Hz', formatPitch(554.7) === '555 Hz', formatPitch(554.7));
	ok('over a kilohertz reads in kHz', formatPitch(5249) === '5.2 kHz', formatPitch(5249));
	ok('no pitch reads as a dash', formatPitch(0) === '—');
}

console.log(failures ? `\n${failures} failure(s)` : '\nall checks passed');
process.exit(failures ? 1 : 0);
