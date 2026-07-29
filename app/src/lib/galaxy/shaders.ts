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
 * How much meaning is claimed for a cluster. The pipeline sorts each cluster's documented
 * function into a behavioural class, and those classes collapse into how strong a claim
 * they make.
 *
 * **Nothing draws with this at the moment.** The Meaning arrangement, which grouped the
 * cloud by claim and gave the unclaimed clusters an island of their own, has been taken
 * out; `functionClass` is still on every centroid in `centroids.json`, so the taxonomy and
 * the reasoning below are kept intact rather than deleted with the view that used them.
 *
 * **`none` is not a claim, and keeping it separate is the whole point.** It used to fall
 * into `structural`, which reads as "a song element carrying syntax" — a real assertion
 * about a bird. Most clusters are now fitted to field recordings and carry no documented
 * function at all, so that default silently turned "we do not know" into "we know this is
 * song structure" for two thirds of the galaxy. They are their own group now, which is what
 * lets the share of the corpus that has no documented function be counted honestly.
 *
 * Four and not six because this is a scatter plot: only three categorical hues stay
 * separable under colour-vision deficiency (validated against the light surface — worst
 * pair ΔE 9.2 deutan, 24.0 normal), and the fourth is a neutral, which does not compete
 * with them. The finer six-class detail lives in the node labels.
 */
export const CLAIM_REFERENTIAL = 0;
export const CLAIM_SOCIAL = 1;
export const CLAIM_STRUCTURAL = 2;
export const CLAIM_NONE = 3;
export const CLAIM_COUNT = 4;

/**
 * What each claim island is called, and what its claim amounts to. Ordered from the
 * strongest claim to none at all.
 */
export const CLAIM_LABELS: Record<number, string> = {
	0: 'referential',
	1: 'social',
	2: 'structural',
	3: 'no documented meaning'
};

export const CLAIM_HINTS: Record<number, string> = {
	0: 'names something outside the bird',
	1: 'says something about the singer',
	2: 'carries syntax, refers to nothing',
	3: 'real audio, nothing documented'
};

export const CLAIM_OF_FUNCTION: Record<string, number> = {
	alarm: CLAIM_REFERENTIAL,
	recruitment: CLAIM_REFERENTIAL,
	territorial: CLAIM_SOCIAL,
	courtship: CLAIM_SOCIAL,
	contact: CLAIM_SOCIAL,
	structural: CLAIM_STRUCTURAL,
	unclassified: CLAIM_NONE
};

/**
 * Simultaneous waves. Three, because a chorus is several birds at once and the point of
 * the interference is that you can see two of them meet; a fourth adds cost and nothing
 * legible on top of three overlapping fronts.
 */
export const WAVE_SOURCES = 3;

/**
 * The camera distance a mark's pixel size is quoted at, at a viewing scale of 1. Both
 * the cloud and the trajectory beads multiply it by the current scale, and they have to
 * agree or the beads come loose from the knots they run between.
 *
 * Quoting it against the scale is the whole point, and the fact that it was a bare
 * constant is why the animation stopped being visible. The distance slider scales the
 * group the cloud lives in, and the framing then backs the camera off to hold the same
 * thing in view — so the picture stays the same size on screen while `-mv.z` grows in
 * proportion to the scale. Measured against a fixed reference that reads as "the cloud
 * moved away", and every mark shrinks toward its floor: taking the top of the slider to
 * 12 quietly cut the points, and the travelling beads with them, to about a third of the
 * size they were designed at, which for a bead is the difference between a moving
 * highlight and a slightly brighter pixel. Scaling the reference with the group cancels
 * it exactly — a viewing distance should not be a resolution control.
 */
export const SIZE_REFERENCE = 4.0;

export function vertexShader(clusterCount: number): string {
	return /* glsl */ `
		#define WAVE_SOURCES ${WAVE_SOURCES}

		attribute float aCluster;
		attribute float aSeed;
		attribute float aAct;
		attribute float aSpecies;
		/** Which build this point joined in; see the point metadata's generation array. */
		attribute float aBorn;
		attribute vec3 aTarget;

		uniform float uActivation[${Math.max(1, clusterCount)}];
		/** 1 where this cluster is the note being sung, 0 where it merely resembles it. */
		uniform float uSung[${Math.max(1, clusterCount)}];
		uniform float uTime;
		uniform float uLevel;
		uniform float uPointSize;
		uniform float uPixelRatio;
		uniform float uHighlight;
		uniform float uSizeScale;
		uniform float uFocus;
		uniform float uFocusDim;
		uniform float uMorph;
		/** The newest generation, and how far its arrival has run (0..1). */
		uniform float uGeneration;
		uniform float uArrival;
		/** Wavefronts per unit of the box, from the live pitch. */
		uniform float uWaveK;
		/** Box units per second the front travels outward at, also from the pitch. */
		uniform float uWaveSpeed;
		/** Thickness of the travelling shell, in box units. */
		uniform float uWaveWidth;
		/** Per source: where it started, how old it is, and how hard it hit. */
		uniform vec3 uWaveOrigin[${WAVE_SOURCES}];
		uniform float uWaveAge[${WAVE_SOURCES}];
		uniform float uWaveAmp[${WAVE_SOURCES}];

		varying float vAct;
		varying float vSeed;
		varying float vFocus;
		varying float vDepth;
		varying float vChosen;
		/**
		 * How much of the accent this point is entitled to. One channel, because the accent
		 * only ever answers one question and the answer depends on whether a bird has been
		 * chosen — see the note where it is set.
		 */
		varying float vAccent;
		/** 1 where the pipeline placed this sound in no cluster at all. */
		varying float vUnassigned;
		/** 0..1 while a newly added point is arriving. */
		varying float vArrive;

		void main() {
			// **A point can belong to no cluster, and that is a result, not a gap.**
			//
			// Density clustering leaves sounds in no dense region — too rare or too unlike
			// anything else to call a type yet — and those arrive with aCluster = -1. Read
			// naively that truncates to index 0 and the whole of the unknown borrows the
			// first knot's activation, which would light a scattered haze every time
			// cluster 0 sounded and assert a membership the pipeline explicitly refused.
			//
			// The threshold is -0.5 and not 0.5. Written as "-0.5 + 1.0" it excluded
			// **cluster 0** along with the unassigned: 48 points of the shipped corpus were
			// drawn a third smaller, at half the ink, with their cluster's activation
			// discarded and the accent withheld — flagged as "in no cluster" while sitting in
			// the middle of one.
			bool assigned = aCluster >= -0.5;
			int index = assigned ? int(aCluster + 0.5) : 0;
			vUnassigned = assigned ? 0.0 : 1.0;
			float clusterAct = assigned ? uActivation[index] : 0.0;
			// aAct already folds the cluster activation into the point's own affinity; the
			// cluster array is the floor, so a scheduled node still lights every member
			// even when nothing is being matched against it.
			float act = clamp(max(aAct, clusterAct * 0.25), 0.0, 1.0);
			vAct = act;
			vSeed = aSeed;
			// Selection is a two-sided change, not just a dimming of everyone else. With
			// only the dim, the chosen bird's points stayed exactly as they were and you
			// could see the threads between its nodes without ever seeing *which* marks
			// they joined. Its points now also grow and gain weight, so the bird reads as
			// standing out of the crowd rather than the crowd receding from it.
			bool chosen = uFocus >= 0.0 && abs(uFocus - aSpecies) < 0.5;
			vFocus = (uFocus < 0.0 || chosen) ? 1.0 : uFocusDim;
			vChosen = chosen ? 1.0 : 0.0;

			// **The accent answers one question, and which question depends on the selection.**
			//
			// With no bird chosen — how the app opens, and what a whole-aviary chorus looks
			// like — the question is *what is sounding right now*, so the accent goes to the
			// cluster being sung. uSung is 1 only for a note we scheduled and know the
			// identity of; the clusters that merely resemble it stay in ink, which is the
			// distinction the whole view exists to draw.
			//
			// With a bird chosen the question becomes *where is this bird*, so the accent
			// goes to its points and nothing else gets any — including its own sung notes,
			// which already have it. Letting another species' note flare violet while a bird
			// is selected would answer a question nobody asked, in the colour reserved for
			// the one they did.
			// An unassigned point is never the note being sung: it is not in the cluster
			// that is sounding, because it is not in a cluster.
			vAccent = assigned
				? ((uFocus < 0.0) ? clamp(uSung[index], 0.0, 1.0) : vChosen)
				: 0.0;

			// Arriving. Points added by the newest grow fade and swell in rather than
			// appearing between two frames, staggered by their own seed so a thousand of
			// them read as a drift of new material settling rather than one block.
			float born = step(uGeneration - 0.5, aBorn);
			vArrive = mix(1.0, clamp((uArrival - aSeed * 0.35) / 0.65, 0.0, 1.0), born);

			// Rearranging between layouts. Each point takes its own slightly different
			// share of the transition, so the cloud flows apart and back together instead
			// of sliding as one rigid body — you can follow individual points across.
			float lead = mix(0.75, 1.25, aSeed);
			vec3 base = mix(position, aTarget, clamp(uMorph * lead, 0.0, 1.0));

			// Active points breathe and jump with the input level — the "it jumps" behaviour
			// of the reference visualisation, per point rather than per knot.
			//
			// Each point takes its own fixed direction on the unit sphere, so a responding
			// knot *inflates* in three dimensions. The previous version pushed every point
			// along normalize(base) — away from the centre of the whole box — and then
			// added a term straight up Y. For a knot sitting off-centre those are nearly
			// the same direction for all of its members, so the knot slid bodily sideways
			// and upward instead of swelling: a three-dimensional response rendered as a
			// one-dimensional twitch.
			float pulse = act * (0.5 + 0.5 * sin(uTime * 9.0 + aSeed * 6.2831853));
			float za = aSeed * 6.2831853 * 1.7;
			float zb = aSeed * 6.2831853 * 2.9;
			vec3 burst = normalize(vec3(cos(za) * sin(zb), cos(zb), sin(za) * sin(zb)) + vec3(1e-4));
			vec3 p = base + burst * pulse * 0.07 * (0.6 + uLevel * 2.0);

			// Waves, plural, each expanding from the knot that is actually sounding.
			//
			// The first version put one wave at the centre of the box, which is nowhere in
			// particular: the cloud pulsed as a whole and said only "something is
			// happening". A sound in this galaxy has a *place* — the cluster it matched —
			// and a wave that starts there and spreads outward says which knot spoke and
			// how the rest of the corpus sits relative to it. Three at once, because a
			// chorus is several birds, and where two fronts cross they add and cancel like
			// real ones. That interference is not decoration: it is the only thing on
			// screen that shows two calls arriving in the same region of the space.
			//
			// Each is a travelling shell rather than an endless ripple — a Gaussian
			// envelope riding out from the source at a speed set by the pitch — so what you
			// see is a front crossing the volume, not a standing corrugation.
			float ph = aSeed * 6.2831853;
			float waveTotal = 0.0;
			for (int i = 0; i < WAVE_SOURCES; i++) {
				float amp = uWaveAmp[i];
				if (amp <= 0.0) continue;
				vec3 away = base - uWaveOrigin[i];
				float dist = length(away) + 1e-4;
				// Distances are in the cloud's own box, so a front travels the same share
				// of the picture whatever the viewing scale is set to.
				float front = uWaveAge[i] * uWaveSpeed;
				float env = exp(-pow((dist - front) / uWaveWidth, 2.0));
				float phase = (dist - front) * uWaveK + aSeed * 0.35;
				p += (away / dist) * sin(phase) * env * amp;
				waveTotal += env * amp;
			}

			// The old drift survives only as what the cloud does in silence, and fades out
			// as the waves come up so the two never fight.
			float idle = 0.004 * (1.0 - clamp(waveTotal * 40.0, 0.0, 1.0));
			p += vec3(
				sin(uTime * 0.55 + ph),
				sin(uTime * 0.41 + ph * 1.7),
				cos(uTime * 0.48 + ph * 2.3)
			) * idle;

			vec4 mv = modelViewMatrix * vec4(p, 1.0);
			gl_Position = projectionMatrix * mv;
			vDepth = -mv.z;

			// Growth follows the live level as well as the activation, and each point takes
			// its own share of it. Inflating every member by the same fixed amount is what
			// made a lit knot read as one swollen disc: it has to breathe with the sound,
			// and unevenly, or the per-point response is invisible in the size channel too.
			float grow = act * (0.35 + 0.9 * uLevel) * (0.5 + 1.0 * aSeed);
			// Unassigned marks are drawn smaller: they are real measurements and they are
			// not structure, and at the same weight a third of the corpus in no cluster
			// reads as a cloud that has one.
			float size = uPointSize * (1.0 + grow) * (1.0 + 0.7 * vChosen)
				* (1.0 - 0.35 * vUnassigned) * mix(0.35, 1.0, vArrive);
			if (abs(uHighlight - aCluster) < 0.5) size *= 1.15;
			// Perspective, but softened. True 1/z is right for a solid and wrong for a
			// scatter: zoomed out every mark falls under a pixel and the cloud turns to fog,
			// zoomed in the near ones become saucers that hide everything behind them. The
			// exponent keeps the *ordering* — nearer is still bigger, which is half the
			// depth cue — while compressing the range enough that a point is a legible dot
			// at every distance. The floor and ceiling catch the extremes of a hard zoom.
			float persp = pow(uSizeScale / max(0.001, -mv.z), 0.7);
			// The floor is three device pixels rather than two: below that a disc has no
			// interior left once the edge is feathered, and the mark degenerates into the
			// feather itself — which is exactly what a haze is.
			gl_PointSize = clamp(size * uPixelRatio * persp, 3.0, 42.0);
		}
	`;
}

export const fragmentShader = /* glsl */ `
	/** The pale end of the response ramp, and the paper it is mixed toward. */
	uniform vec3 uRest;
	uniform vec3 uSurface;
	/** The dark end: where any point lands when it responds and has earned no accent. */
	uniform vec3 uInk;
	/** The one colour in the picture — the sung note, or the selected bird. */
	uniform vec3 uAccent;
	uniform float uOpacity;
	/** Live pitch, 0..1 over the corpus's range. Shapes the gradient inside each mark. */
	uniform float uPitch;

	/**
	 * View-space depth at which aerial perspective starts (x) and is complete (y).
	 * Rewritten every frame from the camera's actual distance to the cloud, because a
	 * fixed depth is wrong at every zoom but one — quoted against a constant, the whole
	 * corpus sits past the far plane when you back off and the picture turns to fog.
	 */
	uniform vec2 uFogRange;

	varying float vAct;
	varying float vSeed;
	varying float vFocus;
	varying float vDepth;
	varying float vChosen;
	varying float vAccent;
	varying float vUnassigned;
	varying float vArrive;

	void main() {
		vec2 uv = gl_PointCoord - 0.5;
		float d = length(uv);
		if (d > 0.5) discard;

		// A hard-edged disc with a one-pixel feather, plus a halo that belongs to whatever
		// is responding.
		//
		// The feather is measured with fwidth rather than fixed in sprite coordinates,
		// and that is the whole difference between a dot and a smudge. A constant
		// smoothstep band is a constant *fraction* of the sprite, so at the sizes most of
		// this corpus is drawn at — five or six pixels once the camera holds the whole
		// galaxy — the entire mark is ramp and never reaches full opacity. Feathering by
		// the actual screen-space derivative keeps the ramp one pixel wide at every point
		// size, so a distant point is a small crisp dot instead of a faint blur.
		float aa = max(fwidth(d), 0.0015);
		float disc = 1.0 - smoothstep(0.40 - aa, 0.40 + aa, d);

		// The inner gradient tightens with pitch. A high call draws a small hard nucleus,
		// a low one a broad soft centre, so the same mark carries the frequency of what is
		// sounding as well as how strongly it responds — and there is something to look at
		// inside a point rather than a flat wafer.
		float bright = mix(0.26, 0.11, uPitch);
		float centre = smoothstep(bright, 0.01, d);

		// The afterglow has to be *earned*. Scaled by vAct alone it turned on at the
		// residual activation every point carries during a chorus, and thirty thousand
		// faint halos are indistinguishable from the fog this shader just stopped drawing:
		// after any sound the cloud stopped looking like it did on load. Below a quarter
		// response there is no glow at all.
		float glow = smoothstep(0.25, 0.75, vAct);
		float halo = smoothstep(0.5, 0.24, d) * glow;
		float mask = disc * 0.88 + centre * (0.22 + 0.5 * glow) + halo * 0.45;

		// **Where this point's response ends up: ink, unless it has earned the accent.**
		//
		// Source and resemblance are not the same claim, so they are not the same colour.
		// The accent belongs to the note that is actually sounding — or, once a bird is
		// chosen, to that bird. A cluster that merely resembles what is sounding walks to
		// ink instead, so a phrase reads as one violet thread with a grey field of
		// relatives around it. Rendered identically, as they were, five clusters lighting
		// at once looked like five birds singing rather than one bird and its four nearest
		// neighbours in the corpus — which is the relation the view exists to show, and the
		// opposite of what it appeared to say.
		//
		// Nothing is hidden by this: the resembling clusters light exactly as brightly as
		// they would have, and the reading panel still names them. Only the colour is
		// withheld, and only from the points that did not earn it.
		vec3 end = mix(uInk, uAccent, clamp(vAccent, 0.0, 1.0));

		// A chosen bird's points sit most of the way along their own ramp even at rest, so
		// the selection is a violet set of marks rather than the same marks in a thinner
		// crowd. Dimming everyone else was not enough on its own: a bird owns forty of a
		// hundred and seventy-six clusters scattered right across the layout, so with only
		// the dim you could see the threads joining its nodes without being able to point
		// at a single mark and say that one belongs to it. Not all the way, because
		// responding still has to be visible on top of being selected.
		vec3 base = mix(uRest, end, 0.8 * vChosen);
		vec3 colour = mix(base, end, clamp(vAct, 0.0, 1.0));

		// A ring of the surface colour around anything that is responding. This is the
		// standard remedy for overlapping marks, and it is what stops a lit knot from
		// fusing into one silhouette: every point keeps a visible edge against its
		// neighbours, so a dense response still reads as a countable spray.
		float ring = (1.0 - smoothstep(0.30, 0.42, d)) * smoothstep(0.30, 0.44, d);
		colour = mix(colour, uSurface, ring * vAct * 0.9);

		// Aerial perspective: far points wash toward the paper and thin out, near ones keep
		// their weight. This is what makes a rotating scatter read as a volume rather than
		// as a disc — the size cue alone is too weak once the sizes are compressed, and
		// the eye takes contrast-with-distance as depth without being told.
		//
		// Responding points are exempted in proportion to how hard they respond: the whole
		// job of this view is to show where a sound landed, and a match that happens to be
		// at the back should not be dimmer than the paper.
		float fog = clamp((vDepth - uFogRange.x) / max(0.001, uFogRange.y - uFogRange.x), 0.0, 1.0);
		fog *= 1.0 - 0.85 * vAct;
		colour = mix(colour, uSurface, fog * 0.45);

		// Resting points are faint so density reads as tone and the responding ones carry
		// the eye; even at full response it stays under 1, because opaque marks stack into
		// a silhouette and the per-point detail disappears.
		// A chosen point also carries more ink than the same point unselected, so the bird
		// separates from the crowd by weight as well as by everyone else fading.
		float alpha =
			uOpacity * mask * (0.55 + vAct * 0.45) * vFocus * (1.0 + 0.35 * vChosen) *
			(1.0 - fog * 0.45) * (1.0 - 0.45 * vUnassigned) * vArrive;
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
	 * Per cluster, 1 where a note is *being sung right now* and 0 where the cluster is
	 * merely responding to it.
	 *
	 * These are two different claims and the picture used to make them identically. When
	 * Birdy sings a Bengalese finch syllable, the scheduled node lights because we know
	 * it is that note, and a handful of clusters belonging to other birds light because
	 * they sound like it. Drawn the same way, in their own species hues, the galaxy
	 * appeared to say that a finch and a chickadee were both singing.
	 *
	 * They are not the same and the difference is the whole content of the view: one is
	 * ground truth, the other is the acoustic relation you came here to see. The shader
	 * gives the sung node its category colour and renders resemblance in neutral ink, so
	 * the picture reads "this is the note, and these are the parts of the corpus it
	 * resembles" instead of "these birds are singing".
	 */
	sung: Float32Array;
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
		sung: new Float32Array(Math.max(1, clusterCount)),
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

		// A GL line is one pixel whatever the zoom, so as the dots shrink toward their
		// floor the thread is the only thing still joining them, and it has to hold a
		// little more ink to do that job than it needed when the dots were large.
		float base = 0.55 + 0.35 * passed;
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
	/**
	 * The cloud's particle size, so a bead is quoted against the marks it runs between.
	 *
	 * The ratios below are calibrated at a particle size of **3**, which is the default —
	 * they were first written against 6, and then the default halved, which quietly
	 * halved every bead with it. That is why the thread went thin.
	 */
	uniform float uPointSize;

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
		// The same softened perspective law as the cloud, quoted at the same distance.
		// It has to be the same or the thread comes loose from the points it connects:
		// under true 1/z the beads shrank twice as fast as the knots they run between, so
		// backing off to hold the whole galaxy left visible nodes joined by nothing.
		float persp = pow(uSizeScale / max(0.001, -mv.z), 0.7);
		float bead = uPointSize * (0.85 + vPeak * 2.4);
		// **The floor rises with the travelling peak, and that is the whole fix.**
		//
		// Both the cloud and the thread shrink together as you back away, which is right,
		// and both stop at a floor, which is also right — below three pixels a mark has no
		// interior left. What was wrong is that they stopped at *different* floors: the
		// cloud held at 3 while the bead kept falling to 2. So the further out you went the
		// worse the ratio got, and past a certain zoom the travelling highlight was
		// **smaller than a resting cloud point** — measured, 0.67 of one, where near the
		// cloud it is 3.3 times one. The animation did not fade out, it inverted.
		//
		// Giving the peak its own floor keeps the relation instead of the absolute size:
		// a bead at full peak is never under ten pixels however far out the camera is, and
		// the resting dots of the thread floor at 3 alongside the cloud they run through.
		float bottom = 3.0 + vPeak * 7.0;
		gl_PointSize = clamp(bead * uPixelRatio * persp, bottom, 64.0);
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
		// Crisp like the cloud's marks, with the glow reserved for the travelling bead.
		float aa = max(fwidth(d), 0.0015);
		float core = (1.0 - smoothstep(0.38 - aa, 0.38 + aa, d)) + smoothstep(0.5, 0.2, d) * vPeak * 0.6;

		bool singing = vProgress >= 0.0;
		float passed = singing ? step(vIndex, vProgress) : 1.0;
		vec3 colour = mix(uColdColor, vColour, clamp(0.35 + vPeak, 0.0, 1.0));
		float alpha = vAlpha * core * (0.35 + 0.25 * passed + vPeak * 0.8);
		gl_FragColor = vec4(colour, clamp(alpha, 0.0, 1.0));
	}
`;
