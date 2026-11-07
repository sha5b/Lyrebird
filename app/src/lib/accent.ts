/**
 * The page accent: black at rest, the chosen bird's colour once one is chosen, and moving with
 * whatever is singing.
 *
 * Three inputs and one output, the CSS variable `--signal` that every accented control reads:
 *
 * - **No bird chosen, silence:** black.
 * - **No bird chosen, something singing:** black rises toward the singer's own colour with the
 *   loudness and falls back with it, so the page breathes with the chorus.
 * - **A bird chosen:** that bird's colour. While it sings, pitch swings the hue either side of
 *   the bird's own and loudness lifts saturation and lightness.
 *
 * **Legibility is a clamp, not a hope.** The accent is also text on white (links, active
 * toggles) and the fill behind white button labels, so every colour this returns holds 4.5:1
 * against white at every level and pitch. The hash-derived species hues do not on their own: a
 * yellow at the galaxy's 45 % lightness measures about 2:1. `verify:accent` sweeps every
 * species for this.
 *
 * The driver writes the variable outside Svelte, because a reactive value at 30 Hz would re-run
 * template effects for a colour no component reads as data. It writes only when the rounded
 * colour changed, so a silent page costs one comparison a frame.
 */
import { speciesHue, speciesSaturation } from './galaxy/palette.ts';

/** WCAG AA for body text. Against white, which is the panels' ground and the worst case. */
const MIN_CONTRAST = 4.5;
/** The galaxy's species lightness (`palette.speciesColour`), where the clamp allows it. */
const BASE_LIGHTNESS = 45;
/** How far pitch may swing the hue either way, in degrees. Wide enough to see, short of a new bird. */
const HUE_SWING = 26;
/** The f0 range mapped across that swing, in Hz. Most of the corpus sings inside it. */
const PITCH_LOW_HZ = 400;
const PITCH_HIGH_HZ = 8000;
/** Loudness follows fast upward and slowly downward, the way a meter does. */
const ATTACK_S = 0.03;
const RELEASE_S = 0.32;
const PITCH_SMOOTH_S = 0.12;
/** How quickly the shown colour reaches its target, so a change of bird fades instead of cuts. */
const COLOUR_SMOOTH_S = 0.09;
/** At most this many writes a second: a colour does not need the renderer's frame rate. */
const WRITE_INTERVAL_S = 1 / 30;
/**
 * `signal.level` is already scaled for the galaxy (`extractor.level * 6`), but a chorus still
 * sits low in that range. The curve opens the quiet end so a soft phrase visibly moves the page.
 */
const LEVEL_CURVE = 0.6;
/** Below this the page is silent as far as colour goes, so black is exactly black. */
const SILENT = 0.012;

function channel(h: number, s: number, l: number, n: number): number {
	const k = (n + h / 30) % 12;
	const a = s * Math.min(l, 1 - l);
	return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, Math.min(9 - k, 1)))));
}

/** HSL (degrees, percent, percent) to 0xRRGGBB. Packed, because this runs every tick. */
export function hslToRgb(hueDeg: number, satPct: number, lightPct: number): number {
	const h = ((hueDeg % 360) + 360) % 360;
	const s = satPct / 100;
	const l = lightPct / 100;
	return (channel(h, s, l, 0) << 16) | (channel(h, s, l, 8) << 8) | channel(h, s, l, 4);
}

function linear(c8: number): number {
	const c = c8 / 255;
	return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** WCAG contrast of a packed colour against white. */
export function contrastOnWhite(rgb: number): number {
	const lum =
		0.2126 * linear((rgb >> 16) & 255) +
		0.7152 * linear((rgb >> 8) & 255) +
		0.0722 * linear(rgb & 255);
	return 1.05 / (lum + 0.05);
}

/** The lightest lightness at this hue and saturation that still holds the contrast floor. */
export function lightnessCap(hueDeg: number, satPct: number): number {
	let lo = 0;
	let hi = 60;
	for (let i = 0; i < 12; i++) {
		const mid = (lo + hi) / 2;
		if (contrastOnWhite(hslToRgb(hueDeg, satPct, mid)) >= MIN_CONTRAST) lo = mid;
		else hi = mid;
	}
	return lo;
}

/** 0 at the bottom of the mapped range, 1 at the top. Unvoiced (no pitch) sits in the middle. */
export function pitchPosition(f0Hz: number): number {
	if (!(f0Hz > 0)) return 0.5;
	const p = Math.log(f0Hz / PITCH_LOW_HZ) / Math.log(PITCH_HIGH_HZ / PITCH_LOW_HZ);
	return Math.min(1, Math.max(0, p));
}

/**
 * The accent's target colour, as a pure function so it can be swept.
 *
 * @param birdId the chosen bird, or '' for none
 * @param singerId who is sounding when no bird is chosen, or ''
 * @param level01 smoothed loudness, 0..1
 * @param pitch01 smoothed pitch position from `pitchPosition`
 */
export function accentRgb(
	birdId: string,
	singerId: string,
	level01: number,
	pitch01: number
): number {
	const level = Math.min(1, Math.max(0, level01));
	const id = birdId || (level > SILENT ? singerId : '');
	if (!id) return 0x000000;
	const swing = (pitch01 - 0.5) * 2 * HUE_SWING;
	const hue = speciesHue(id) + (level > SILENT ? swing : 0);
	const baseSat = speciesSaturation(id);
	const sat = baseSat + (100 - baseSat) * level;
	const cap = lightnessCap(hue, sat);
	const rest = Math.min(BASE_LIGHTNESS, cap);
	if (!birdId) return hslToRgb(hue, sat, rest * level);
	const quiet = rest * 0.88;
	return hslToRgb(hue, sat, Math.min(cap, quiet + (rest * 1.2 - quiet) * level));
}

export interface AccentInput {
	/** Loudness of what is sounding, 0..1. Read fresh each tick. */
	level: () => number;
	/** Fundamental of what is sounding in Hz, or 0 when unvoiced. */
	f0Hz: () => number;
}

/** The rAF loop that turns live meters into `--signal`. One per page. */
export class AccentDriver {
	birdId = '';
	/** Who most recently began to sing. Colours the page only while no bird is chosen. */
	singerId = '';
	/** A thin bar that shows the loudness directly. Written alone, so it costs no style pass. */
	pulse: HTMLElement | null = null;

	private level = 0;
	private pitch = 0.5;
	private r = 0;
	private g = 0;
	private b = 0;
	private lastWrite = 0;
	private lastTick = 0;
	private written = -1;
	private writtenPulse = -1;
	private raf = 0;
	private readonly reduced =
		typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null;

	private readonly input: AccentInput;
	private readonly root: HTMLElement;

	constructor(input: AccentInput, root: HTMLElement) {
		this.input = input;
		this.root = root;
	}

	start() {
		if (this.raf) return;
		this.raf = requestAnimationFrame(this.tick);
	}

	stop() {
		cancelAnimationFrame(this.raf);
		this.raf = 0;
		this.root.style.removeProperty('--signal');
		this.written = -1;
	}

	private tick = (nowMs: number) => {
		this.raf = requestAnimationFrame(this.tick);
		const now = nowMs / 1000;
		// Clamped so a tab coming back from the background eases rather than jumps.
		const dt = Math.min(0.1, now - this.lastTick);
		this.lastTick = now;
		const still = this.reduced?.matches ?? false;
		const target = still ? 0 : Math.max(0, this.input.level()) ** LEVEL_CURVE;
		const tau = target > this.level ? ATTACK_S : RELEASE_S;
		this.level += (target - this.level) * (1 - Math.exp(-dt / tau));
		const f0 = this.input.f0Hz();
		if (f0 > 0 && this.level > SILENT) {
			this.pitch += (pitchPosition(f0) - this.pitch) * (1 - Math.exp(-dt / PITCH_SMOOTH_S));
		}

		const goal = accentRgb(this.birdId, this.singerId, this.level, this.pitch);
		const k = 1 - Math.exp(-dt / COLOUR_SMOOTH_S);
		this.r += (((goal >> 16) & 255) - this.r) * k;
		this.g += (((goal >> 8) & 255) - this.g) * k;
		this.b += ((goal & 255) - this.b) * k;

		if (now - this.lastWrite < WRITE_INTERVAL_S) return;
		this.lastWrite = now;
		const shown = (Math.round(this.r) << 16) | (Math.round(this.g) << 8) | Math.round(this.b);
		if (shown !== this.written) {
			this.written = shown;
			this.root.style.setProperty('--signal', `#${shown.toString(16).padStart(6, '0')}`);
		}
		if (this.pulse) {
			const width = Math.round(this.level * 200);
			if (width !== this.writtenPulse) {
				this.writtenPulse = width;
				this.pulse.style.transform = `scaleX(${width / 200})`;
			}
		}
	};
}
