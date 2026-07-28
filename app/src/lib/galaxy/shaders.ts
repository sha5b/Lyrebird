/**
 * Point-cloud shaders for the embedding galaxy (docs/05-embedding-galaxy.md §5.3-5.4).
 *
 * The palettes themselves, and the reasoning behind them, are in `palette.ts`.
 *
 * Two things change per frame: a small array of per-cluster activations, and one float
 * per point. The per-point float is what makes a cluster light *from the inside out* —
 * the members closest to the live sound in the reduced feature space brighten first,
 * so an active knot shows its own internal structure instead of switching on as one
 * blob. It is a single float per point, uploaded as a dynamic attribute; at the shipped
 * corpus size that is 17 kB a frame, which is nothing next to a bloom pass.
 *
 * The palette is built for a light background: normal blending, not additive. On white,
 * additive blending drives every overlap toward the background colour and the cloud
 * dissolves; with normal blending and a low per-point alpha, dense regions read darker,
 * which is what a scatter plot is supposed to do.
 */

/**
 * How much meaning is claimed for a cluster, in three steps. This is the semantic axis
 * the corpus can actually support: the pipeline sorts each cluster's documented function
 * into a behavioural class, and those classes collapse into how strong a claim they make.
 *
 * Three and not six because this is a scatter plot: with every pair of series on screen
 * at once, only three categorical hues stay separable under colour-vision deficiency
 * (validated against the light surface — worst pair ΔE 9.2 deutan, 24.0 normal). The
 * finer six-class detail lives in the node labels, where it costs nothing to read.
 */
import { CLAIM_HOT } from './palette';

export const CLAIM_REFERENTIAL = 0;
export const CLAIM_SOCIAL = 1;
export const CLAIM_STRUCTURAL = 2;

export const CLAIM_OF_FUNCTION: Record<string, number> = {
	alarm: CLAIM_REFERENTIAL,
	recruitment: CLAIM_REFERENTIAL,
	territorial: CLAIM_SOCIAL,
	courtship: CLAIM_SOCIAL,
	contact: CLAIM_SOCIAL,
	structural: CLAIM_STRUCTURAL,
	unclassified: CLAIM_STRUCTURAL
};

export const CLAIM_LEGEND = [
	{
		id: CLAIM_REFERENTIAL,
		hex: CLAIM_HOT[CLAIM_REFERENTIAL],
		label: 'referential',
		hint: 'names something outside the bird — a predator, a direction to move'
	},
	{
		id: CLAIM_SOCIAL,
		hex: CLAIM_HOT[CLAIM_SOCIAL],
		label: 'social',
		hint: 'says something about the singer — territory, pair bond, presence'
	},
	{
		id: CLAIM_STRUCTURAL,
		hex: CLAIM_HOT[CLAIM_STRUCTURAL],
		label: 'structural',
		hint: 'a song element carrying syntax, with no referential meaning'
	}
];

/** 0 = response only, 1 = colour by how much meaning is claimed. */
export const COLOUR_RESPONSE = 0;
export const COLOUR_MEANING = 1;

export function vertexShader(clusterCount: number): string {
	return /* glsl */ `
		attribute float aCluster;
		attribute float aSeed;
		attribute float aAct;
		attribute float aSpecies;
		attribute float aClaim;
		attribute vec3 aTarget;

		uniform float uActivation[${Math.max(1, clusterCount)}];
		uniform float uTime;
		uniform float uLevel;
		uniform float uPointSize;
		uniform float uPixelRatio;
		uniform float uHighlight;
		uniform float uSizeScale;
		uniform float uFocus;
		uniform float uFocusDim;
		uniform float uMorph;

		varying float vAct;
		varying float vSeed;
		varying float vFocus;
		varying float vClaim;
		varying float vSpecies;

		void main() {
			int index = int(aCluster + 0.5);
			// aAct already folds the cluster activation into the point's own affinity; the
			// cluster array is the floor, so a scheduled node still lights every member
			// even when nothing is being matched against it.
			float act = clamp(max(aAct, uActivation[index] * 0.25), 0.0, 1.0);
			vAct = act;
			vSeed = aSeed;
			vClaim = aClaim;
			vSpecies = aSpecies;
			vFocus = (uFocus < 0.0 || abs(uFocus - aSpecies) < 0.5) ? 1.0 : uFocusDim;

			// Rearranging between layouts. Each point takes its own slightly different
			// share of the transition, so the cloud flows apart and back together instead
			// of sliding as one rigid body — you can follow individual points across.
			float lead = mix(0.75, 1.25, aSeed);
			vec3 base = mix(position, aTarget, clamp(uMorph * lead, 0.0, 1.0));

			// Active points breathe outward and jump with the input level — the "it jumps"
			// behaviour of the reference visualisation, now per point rather than per knot.
			float pulse = act * (0.5 + 0.5 * sin(uTime * 9.0 + aSeed * 6.2831853));
			vec3 p = base + normalize(base + vec3(1e-4)) * pulse * 0.07;
			p.y += pulse * 0.06 * (0.5 + uLevel * 4.0);

			vec4 mv = modelViewMatrix * vec4(p, 1.0);
			gl_Position = projectionMatrix * mv;

			// Growth follows the live level as well as the activation, and each point takes
			// its own share of it. Inflating every member by the same fixed amount is what
			// made a lit knot read as one swollen disc: it has to breathe with the sound,
			// and unevenly, or the per-point response is invisible in the size channel too.
			float grow = act * (0.35 + 0.9 * uLevel) * (0.5 + 1.0 * aSeed);
			float size = uPointSize * (1.0 + grow);
			if (abs(uHighlight - aCluster) < 0.5) size *= 1.15;
			// uPointSize is in pixels at the default camera distance (uSizeScale), which
			// keeps the cloud readable: the corpus is normalised to |coord| <= 1, so the
			// usual large perspective constant turns every point into a screen-wide blob.
			gl_PointSize = clamp(size * uPixelRatio * (uSizeScale / max(0.001, -mv.z)), 1.0, 64.0);
		}
	`;
}

export const PALETTE_SLOTS = 16;

export const fragmentShader = /* glsl */ `
	uniform vec3 uRest[${PALETTE_SLOTS}];
	uniform vec3 uHot[${PALETTE_SLOTS}];
	uniform vec3 uSurface;
	uniform float uOpacity;
	uniform float uMode;

	varying float vAct;
	varying float vSeed;
	varying float vFocus;
	varying float vClaim;
	varying float vSpecies;

	void main() {
		vec2 uv = gl_PointCoord - 0.5;
		float d = length(uv);
		if (d > 0.5) discard;

		// A soft disc with a firmer centre: the body carries the density of the cloud, the
		// centre is what sharpens when a point responds.
		float core = smoothstep(0.5, 0.12, d);
		float centre = smoothstep(0.28, 0.0, d);
		float mask = core * 0.75 + centre * 0.45;

		// Which category this point belongs to: its bird, or how much meaning its cluster
		// claims. Both palettes live in the same two uniforms; the CPU swaps them.
		float slotF = (uMode > 0.5) ? vClaim : mod(max(vSpecies, 0.0), float(${PALETTE_SLOTS}));
		int slot = int(slotF + 0.5);
		vec3 rest = uRest[slot];
		vec3 hot = uHot[slot];

		// Response walks from the pale resting tint to the saturated one along a single
		// hue, so identity never moves and intensity always does. The whole 0..1 range is
		// used: a steeper curve made everything above about half look identical, which is
		// what made an active knot read as one flat colour.
		vec3 colour = mix(rest, hot, clamp(vAct, 0.0, 1.0));

		// A ring of the surface colour around anything that is responding. This is the
		// standard remedy for overlapping marks, and it is what stops a lit knot from
		// fusing into one silhouette: every point keeps a visible edge against its
		// neighbours, so a dense response still reads as a countable spray.
		float ring = (1.0 - smoothstep(0.30, 0.42, d)) * smoothstep(0.30, 0.44, d);
		colour = mix(colour, uSurface, ring * vAct * 0.9);

		// Resting points are faint so density reads as tone and the responding ones carry
		// the eye; even at full response it stays under 1, because opaque marks stack into
		// a silhouette and the per-point detail disappears.
		float alpha = uOpacity * mask * (0.34 + vAct * 0.5) * vFocus;
		gl_FragColor = vec4(colour, clamp(alpha, 0.0, 1.0));
	}
`;

/**
 * One trajectory through the galaxy: the ordered clusters a phrase visits.
 *
 * Several exist at once. During a global chorus every bird that starts singing adds its
 * own, so the picture is many threads lighting in parallel rather than one line that
 * keeps being overwritten by whoever sang last.
 */
export interface LivePath {
	nodes: number[];
	/** Scheduled syllable windows in AudioContext time; null for a static preview. */
	times: { start: number; end: number }[] | null;
	/** Position along the path in node units while singing; -1 when not animating. */
	progress: number;
	alpha: number;
	/**
	 * False until the first note actually sounds. A queued song is not a drawn one: the
	 * chorus schedules many seconds ahead, and showing their threads would tangle the
	 * picture with phrases nobody has heard yet.
	 */
	started: boolean;
	/** Which bird this is, for the label overlay. */
	speciesId: string;
	label: string;
}

/** Per-frame signal shared between the audio loop and the renderer. Mutated in place. */
export interface VisualSignal {
	activations: Float32Array;
	/**
	 * Per-point response, 0..1. Written every frame by the listener, read straight into
	 * a GPU attribute; never reallocated, so the renderer can hold the same buffer.
	 */
	pointActivation: Float32Array;
	level: number;
	f0: number;
	/** 0..1 — how well the live input matches anything in the corpus. */
	strength: number;
	/** Index of the most active cluster, or -1. */
	best: number;
	/** Active trajectories, most recent last. */
	paths: LivePath[];
	/** Bumped whenever the set of paths changes, so the renderer rebuilds its geometry. */
	pathsVersion: number;
	/**
	 * Every song of the selected species, drawn faintly behind the selected one. Segments
	 * shared between songs overlap and so read stronger, which shows at a glance which
	 * transitions this bird reuses.
	 */
	context: number[][];
	contextVersion: number;
	/** Species index to keep at full strength; -1 shows every species equally. */
	focus: number;
}

export function createSignal(clusterCount: number, pointCount = 0): VisualSignal {
	return {
		activations: new Float32Array(Math.max(1, clusterCount)),
		pointActivation: new Float32Array(Math.max(1, pointCount)),
		level: 0,
		f0: 0,
		strength: 0,
		best: -1,
		paths: [],
		pathsVersion: 0,
		context: [],
		contextVersion: 0,
		focus: -1
	};
}

/** Trajectories are drawn as disconnected segments so separate paths never join up. */
export const MAX_PATHS = 10;

export const trajectoryVertexShader = /* glsl */ `
	attribute float aIndex;
	attribute float aPath;

	uniform float uProgress[${MAX_PATHS}];
	uniform float uAlpha[${MAX_PATHS}];
	uniform vec3 uPathColour[${MAX_PATHS}];

	varying float vIndex;
	varying float vProgress;
	varying float vAlpha;
	varying vec3 vColour;

	void main() {
		int p = int(aPath + 0.5);
		vIndex = aIndex;
		vProgress = uProgress[p];
		vAlpha = uAlpha[p];
		// Each thread wears the colour of the bird singing it, so a chorus of six reads
		// as six birds rather than six identical wires.
		vColour = uPathColour[p];
		gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
	}
`;

export const trajectoryFragmentShader = /* glsl */ `
	uniform vec3 uColdColor;

	varying float vIndex;
	varying float vProgress;
	varying float vAlpha;
	varying vec3 vColour;

	void main() {
		bool singing = vProgress >= 0.0;
		// while idle the whole path reads as one faint thread; while singing the part
		// already sung stays lit so the order of the phrase remains visible
		float passed = singing ? step(vIndex, vProgress) : 1.0;
		float peak = singing ? exp(-pow((vIndex - vProgress) / 0.45, 2.0)) : 0.0;

		float base = 0.45 + 0.35 * passed;
		vec3 colour = mix(uColdColor, vColour, clamp(0.35 + peak, 0.0, 1.0));
		gl_FragColor = vec4(colour, clamp(vAlpha * (base + peak * 0.6), 0.0, 1.0));
	}
`;

/**
 * Beads along the same polyline. A GL line is capped at one pixel wide, which disappears
 * against the cloud, so the path is also drawn as a run of small sprites — and the
 * travelling highlight becomes a bead running along the thread.
 */
export const trajectoryPointsVertexShader = /* glsl */ `
	attribute float aIndex;
	attribute float aPath;

	uniform float uProgress[${MAX_PATHS}];
	uniform float uAlpha[${MAX_PATHS}];
	uniform vec3 uPathColour[${MAX_PATHS}];
	uniform float uPixelRatio;
	uniform float uSizeScale;

	varying float vIndex;
	varying float vPeak;
	varying float vProgress;
	varying float vAlpha;
	varying vec3 vColour;

	void main() {
		int p = int(aPath + 0.5);
		vIndex = aIndex;
		vProgress = uProgress[p];
		vAlpha = uAlpha[p];
		vColour = uPathColour[p];
		bool singing = vProgress >= 0.0;
		vPeak = singing ? exp(-pow((aIndex - vProgress) / 0.45, 2.0)) : 0.0;

		vec4 mv = modelViewMatrix * vec4(position, 1.0);
		gl_Position = projectionMatrix * mv;
		gl_PointSize = clamp(
			(2.2 + vPeak * 7.0) * uPixelRatio * (uSizeScale / max(0.001, -mv.z)),
			1.0,
			64.0
		);
	}
`;

export const trajectoryPointsFragmentShader = /* glsl */ `
	uniform vec3 uColdColor;

	varying float vIndex;
	varying float vPeak;
	varying float vProgress;
	varying float vAlpha;
	varying vec3 vColour;

	void main() {
		vec2 uv = gl_PointCoord - 0.5;
		float d = length(uv);
		if (d > 0.5) discard;
		float core = smoothstep(0.5, 0.05, d);

		bool singing = vProgress >= 0.0;
		float passed = singing ? step(vIndex, vProgress) : 1.0;
		vec3 colour = mix(uColdColor, vColour, clamp(0.35 + vPeak, 0.0, 1.0));
		float alpha = vAlpha * core * (0.35 + 0.25 * passed + vPeak * 0.8);
		gl_FragColor = vec4(colour, clamp(alpha, 0.0, 1.0));
	}
`;
