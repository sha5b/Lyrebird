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

/**
 * Where the wavefront's skirt becomes a *reveal*: a point whose front value sits in
 * [REVEAL_FRONT, 0.05) without responding (vAct < 0.25) is carried into the active
 * pass as visible density — the knot's whole membership showing as the shell
 * passes, not only the members that matched. 0.015 against the response cut's 0.05:
 * the front is a gaussian of width FRONT_WIDTH, so this puts the reveal's outer
 * edge sqrt(ln(1/0.015)) ≈ 2.05 widths (≈ 0.45 knot-radii) from the shell's centre
 * against the response's 1.73 (≈ 0.38) — a thin honest skirt, not a second wave.
 * Quoted as a shader constant so the fragment discard, the reveal band and the
 * CPU's active-index scan (PointCloud) can never drift apart.
 */
export const REVEAL_FRONT = 0.015;

/**
 * The offset the cluster-state texture's A channel carries so that **0 can keep
 * meaning "this knot has no bird"** — see the channel's note in PointCloud. A knot's
 * hue is written as `HUE_FLOOR + (1 - HUE_FLOOR) * turns`, so the fragment has to take
 * the floor back off before it can treat the value as turns. It did not, for one
 * round: every knot's accent came out up to 7.2° around the circle from the hue the
 * same bird's tag and thread were drawn in, which is exactly the kind of near-match
 * that reads as "the colours do not line up". Exported so the two sides cannot drift.
 */
export const HUE_FLOOR = 0.02;

/** The point cloud's vertex stage. It no longer takes the cluster count: the three
 * per-cluster channels moved into `uClusterState` (see the uniform's comment), so the
 * shader's source is the same string for a 64-knot galaxy and a 14 000-knot one, and
 * the number of knots is no longer a compile-time constant of the renderer.
 */
export function vertexShader(): string {
	return /* glsl */ `
		#define WAVE_SOURCES ${WAVE_SOURCES}

		attribute float aCluster;
		attribute float aAct;
		attribute float aSpecies;
		/** Which build this point joined in; see the point metadata's generation array. */
		attribute float aBorn;
		/**
		 * Provenance category (assets.PROVENANCE): 0 documented, 1 learned (our
		 * synthesis of a fitted type), 2 field (a real recording of one), 3 unlabelled,
		 * 4 candidate.
		 */
		attribute float aProv;
		/**
		 * 1 where the density clustering put this sound in **no dense region**, 0 where it
		 * placed it, and 0 on any build that never measured it.
		 *
		 * This is the cross-map channel, and it exists because the two questions live in
		 * two asset sets. The shipped map is --clustering label, which gives every point
		 * a knot by construction, so on its own it can never say "none of these". The
		 * hdbscan map can, and analysis/v10_unknown_join.py joins the two by row index —
		 * legitimate because cmd_build builds one PointSet and never reorders it — and
		 * writes the verdict back into points.json as unassigned.
		 *
		 * So this is not the same thing as aCluster < 0. That says "this map placed
		 * nothing here"; this says "the *other* map, the one whose whole job is refusing,
		 * refused it". On the shipped label map aCluster < 0 is empty by construction and
		 * this channel carries the entire discovery surface.
		 */
		attribute float aDense;
		/** 1 while a scheduled orphan note — a type with points but no cluster — sounds. */
		attribute float aOrphan;
		/**
		 * The wavefront ring at this point, 0..1. Computed on the CPU from the point's
		 * true distance to the front's origin — see the note above frontRing for what
		 * drives what. Never a random phase: arrival order is distance order.
		 */
		attribute float aFront;
		/** Unit direction from the point's own cluster centroid — true geometry, at load. */
		attribute vec3 aRadDir;
		/**
		 * Four per-point floats packed into one attribute, because attribute slots are
		 * a hard budget: Mesa's Intel driver in Firefox reports fewer than 15, and the
		 * 15-attribute version of this program failed to link there — packed, and with
		 * the bird-colour mode's per-point hue gone with its mode, the program asks
		 * for 10. The old names survive as defines below, so the body reads as it
		 * always has.
		 *
		 * x — aSeed: per-point phase offsets (multiply-and-mod hash).
		 * y — aBloom: how far this point may bloom as the front passes: 45 % of its
		 *   knot's own radius (median knot measured on the 1024-cluster build: radius
		 *   0.185 → 0.083), capped at 0.045 — about 0.8 × the median knot spacing
		 *   (0.057) — so a dense knot's members clearly separate as the ring crosses,
		 *   yet a blooming member still lands inside its own knot's neighbourhood
		 *   rather than the next knot's.
		 * z — aSpread: how far this point may drift outward along aRadDir as the
		 *   camera closes in (uBlossom): sqrt(hash) × knotRadius × 1.35 minus the
		 *   resting distance from its own centroid, capped at 0.6 × the median knot
		 *   spacing. Interior points move most, rim points barely, so the knot's
		 *   outline is preserved — display jitter, the same status a scatterplot's
		 *   jitter has. Zero for the unassigned, which are already sparse.
		 * w — aRank: position in the level-of-detail priority order, 0..1 within the
		 *   point's own spatial cell's unfocused remainder; a focused bird's points
		 *   are all 0, so they never sit on the fade frontier. Representatives and
		 *   unclustered points rank lowest, so they are the last to thin as the
		 *   camera backs off. Rewritten only when the order changes — load and focus
		 *   changes — never per frame.
		 */
		attribute vec4 aMisc;
		#define aSeed aMisc.x
		#define aBloom aMisc.y
		#define aSpread aMisc.z
		#define aRank aMisc.w

		/**
		 * The three per-cluster channels, as one texture rather than three uniform arrays.
		 *
		 * **This is what the cluster count is limited by, so it is why the texture exists.**
		 * Declared as three float arrays of length N, the channels cost 3N vertex uniform
		 * floats: at N = 1024 that is 3 072, already past the WebGL2 guaranteed minimum and
		 * standing only because this machine's GPU is generous. It also put a hard ceiling
		 * on the pipeline's K_CAP, and a capped build is one where types lose their knot and the
		 * sound they name lights nothing — on the 2 143-type debug corpus, 1 231 types
		 * (57 %) had no cluster and could not light, label or draw a trajectory. A texture
		 * is sampled, not declared, so the ceiling moves to texture size and the number of
		 * knots becomes the corpus's decision again.
		 *
		 * R = activation (live match or scheduled pulse), G = sung (1 only for a note we
		 * scheduled and know the identity of), B = learning (pipeline work, a slow swell
		 * that must never read as a response — folded into R it drove the same fast jump
		 * and the same ink as a match), A = the knot's own species hue in turns, written
		 * once and never animated (see the note on the fourth channel in PointCloud):
		 * it is what lets several birds sing at once in their own colours instead of all
		 * of them borrowing the single eased uAccent uniform.
		 */
		uniform sampler2D uClusterState;
		uniform vec2 uClusterTexSize;

		/** Row-major cluster index -> its four channels, at texel centres, nearest-filtered. */
		vec4 clusterState(int index) {
			float i = float(index);
			float x = (mod(i, uClusterTexSize.x) + 0.5) / uClusterTexSize.x;
			float y = (floor(i / uClusterTexSize.x) + 0.5) / uClusterTexSize.y;
			return texture2D(uClusterState, vec2(x, y));
		}
		uniform float uTime;
		uniform float uLevel;
		uniform float uPointSize;
		uniform float uPixelRatio;
		uniform float uHighlight;
		uniform float uSizeScale;
		uniform float uFocus;
		uniform float uFocusDim;
		/**
		 * The level-of-detail frontier, 0..1 of the priority order: the CPU's drawRange
		 * cuts what lies past it, and the resting pass dissolves the band just behind
		 * it in through vLod. Continuous, so coming closer only ever adds a frame's
		 * worth of marks — the discrete levels it replaced jumped a quarter of the
		 * corpus to all of it in one frame, which read as a pop. The responding pass
		 * ignores it: vLod is 1 there, because activation is a claim and claims are
		 * not thinned by the camera.
		 */
		uniform float uLod;
		/**
		 * The knot blossom, 0..1 from the camera distance: at whole-galaxy zoom a
		 * knot's marks sit at their corpus positions; approaching, they drift outward
		 * along aRadDir to fill the knot's measured extent. Opens over 1.9 → 1.0
		 * cloud radii, so the spacing arrives with the LOD detail rather than after
		 * it. Display jitter only — nothing in the corpus moves.
		 */
		uniform float uBlossom;
		/**
		 * 1 near, 0 far, over 3.5 → 1.8 cloud radii: blends the point-size floor
		 * between 3 and 2 device pixels. Below 3 px a feathered disc is all feather —
		 * at galaxy distance that feather is the intended haze (and less fill on an
		 * iGPU); the crisp disc returns on approach.
		 */
		uniform float uNearFloor;
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
		/**
		 * Spatial reach of a ripple, in box units: twice the median nearest-neighbour
		 * centroid distance of the loaded corpus, computed at load. A ripple is a local
		 * event at the sounding knot and its immediate neighbours, never a cloud-wide
		 * wash — the measured numbers behind the scale are recorded where it is set.
		 */
		uniform float uWaveLocal;
		/**
		 * The "heard, but nothing claimed" state: where the nearest region is and how
		 * strongly it should breathe. Only ever driven below the claim gate — a match
		 * never sets it, so its slow grey breath cannot be mistaken for a response.
		 */
		uniform vec3 uUnmatchedOrigin;
		uniform float uUnmatchedStrength;
		/** 1 for neutral ink/plain points, 0 for the provenance class tint. */
		uniform float uPlain;
		/**
		 * 0..1: how far the figure and the ground have swapped.
		 *
		 * At 0 the cloud reads as it always has — the sounds a density clustering placed
		 * are the picture, and the ones it refused are drawn a third smaller and half as
		 * dark, because at equal weight a scattered haze reads as structure it has not
		 * earned.
		 *
		 * At 1 that judgement is inverted, and the inversion is the whole point of the
		 * channel. **On this corpus the refused points are the only place a sound can come
		 * out as "none of these"** — the shipped label clustering names everything — so the
		 * discovery surface was being drawn as the quietest thing on the stage. Turned up,
		 * the placed sounds become faint ground and the refused ones become the figure:
		 * larger, at full ink, in the numbers analysis/v10_unknown_join.py measured.
		 *
		 * Kept as a continuous mix rather than a boolean so the switch is a transition and
		 * not a cut — the eye keeps track of which marks moved, which is the one thing a
		 * hard swap of figure and ground destroys.
		 */
		uniform float uUnheard;

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
		/** 1 where a density clustering refused this sound — either map's verdict. */
		varying float vRefused;
		/** 0..1 while a newly added point is arriving. */
		varying float vArrive;
		/** 0..1 across the level-of-detail frontier's fade band (see aRank/uLod). */
		varying float vLod;
		/** Provenance category of this point (see aProv). */
		varying float vProv;
		/** 1 while this point's orphan type is being played (see aOrphan). */
		varying float vOrphan;
		/** The wavefront ring passing through this point (see aFront). */
		varying float vWave;
		/**
		 * The signed ripple field at this point: the sum of every live source's crest
		 * (positive) and trough (negative). Signed, so two crossing fronts amplify and
		 * cancel like water rather than each playing at full strength independently.
		 */
		varying float vRipple;
		/** This point's knot's species hue in turns, 0 for none. See the A channel. */
		varying float vHue;
		/** The slow grey breath of the nearest region when input is heard but unclaimed. */
		varying float vUnmatchedRing;

		void main() {
			vProv = aProv;
			vOrphan = aOrphan;
			vWave = aFront;
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
			// **Refused by a density clustering, from whichever of the two maps measured it.**
			// On the hdbscan map that is this map's own -1; on the shipped label map it is
			// the joined aDense channel, because the label map refuses nothing. Either
			// way it is the same claim about the same sound, so the view reads one varying
			// and the figure/ground switch below does not have to know which map is loaded.
			vRefused = max(vUnassigned, clamp(aDense, 0.0, 1.0));
			vec4 state = assigned ? clusterState(index) : vec4(0.0);
			// This knot's own bird, as a hue the fragment can wear. 0 means "no bird
			// here" — an unassigned point, or a build written before the channel existed
			// — and the fragment falls back to the single eased accent uniform.
			vHue = state.a;
			float clusterAct = state.r;
			// aAct already folds the cluster activation into the point's own affinity; the
			// cluster array is the floor, so a scheduled node still lights every member
			// even when nothing is being matched against it.
			float act = clamp(max(aAct, clusterAct * 0.25), 0.0, 1.0);
			// Learning is a slow swell, not a response: the knot brightens a little and
			// breathes at the rate the breath arrives with, but it never drives the
			// response pulse below — that motion is reserved for sound, so work and
			// audio can no longer be mistaken for each other.
			float learn = state.b;
			vAct = max(act, learn * 0.55);
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
				? ((uFocus < 0.0) ? clamp(state.g, 0.0, 1.0) : vChosen)
				: 0.0;

			// Arriving. Points added by the newest grow fade and swell in rather than
			// appearing between two frames, staggered by their own seed so a thousand of
			// them read as a drift of new material settling rather than one block.
			float born = step(uGeneration - 0.5, aBorn);
			vArrive = mix(1.0, clamp((uArrival - aSeed * 0.35) / 0.65, 0.0, 1.0), born);

			// The level-of-detail frontier, as a dissolve: points just behind it grow
			// and fade in across a narrow band of the priority ranking (the size and
			// alpha multipliers below) instead of appearing between two frames as the
			// drawRange walks past them. Two percent of a cell's order is ~110 marks on
			// the shipped corpus, so a crossing reads as a drift of detail, not a pop.
			// Points past the frontier are not drawn at all; points well behind it sit
			// at full weight. The responding pass exempts itself: a lit point is a
			// claim, and claims are not thinned by the camera.
#ifdef ACTIVE_PASS
			vLod = 1.0;
#else
			vLod = smoothstep(0.0, 0.02, uLod - aRank);
#endif

			// One arrangement, so the base is the position outright. The layout-morph
			// path this used to be (aTarget + uMorph, each point on its own share of the
			// transition) never left uMorph = 0 once the islands layout went, and its
			// attribute was one of the four the Mesa link failure cost — it is in git
			// history if a morph ever comes back.
			vec3 base = position;

			// **The wavefront is the primary motion now; the per-point jitter is texture.**
			//
			// An active knot used to animate as independent random-phase jumps — every
			// point on its own clock, so the eye read "these points are agitated" and
			// nothing else. What the data actually says is ordered: the sound landed at a
			// place in the knot, and the response reaches each member when the front
			// crosses its true distance from that place. That propagation is aFront,
			// computed on the CPU from real distances (see frontRing), and it moves the
			// point along its true radial direction, so the knot visibly inflates outward
			// in arrival order.
			//
			// The random-phase term survives only as a small unevenness on top, because a
			// knot where every member moves identically reads as one rigid disc. Its
			// amplitude is capped well under the front's, so the coherent wave is what you
			// see and the jitter only keeps the spray countable.
			//
			// The amplitude budget still has to fit inside the knot. Measured on the
			// shipped 149-cluster build, the mean member sits 0.079 from its own centroid
			// and a sixth of the assigned points already rest nearer a *neighbouring*
			// centroid than that, so the sum of both terms stays under half a cluster
			// radius (0.006 texture + 0.032 front = 0.038 at full level): a responding
			// knot swells hard in order, and never spills into the knot next door.
			//
			// The texture's clock slowed from 9.0 to 2.6 rad/s (~0.4 Hz), and its
			// amplitude from 0.007 to 0.004: at the old rate a held note buzzed, and on
			// a still frame the buzz read as flicker. The wavefront already owns the
			// attack — the onset ping is the front, not this term — so what a sustained
			// note needed was a slow swell, not a faster vibrato.
			float pulse = act * (0.5 + 0.5 * sin(uTime * 2.6 + aSeed * 6.2831853));
			float za = aSeed * 6.2831853 * 1.7;
			float zb = aSeed * 6.2831853 * 2.9;
			vec3 burst = normalize(vec3(cos(za) * sin(zb), cos(zb), sin(za) * sin(zb)) + vec3(1e-4));
			// The blossom shares aRadDir with the front: both move the point along the
			// true radial from its own centroid, the front as a passing ring, the
			// blossom as the camera's approach spreading the knot's marks to fill its
			// measured extent. Zero at galaxy distance, where uBlossom is 0 — except
			// for the selected bird, whose knots are always fully open: choosing it
			// asked for its whole cloud, and a knot that stays fused until the camera
			// closes is the selection's own marks hiding from it.
			vec3 p = base
				+ burst * pulse * 0.004 * (0.6 + uLevel * 0.9)
				+ aRadDir * (aFront * aBloom + aSpread * max(uBlossom, vChosen));

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
			//
			// Two bounds make it water rather than weather. **Local**: a second gaussian,
			// quoted against the corpus's own knot spacing (uWaveLocal), bounds the reach —
			// two knot-spacings for years, four since 2026-08-01 (owner: the knot-local
			// flash read as a flash, not as a wave), so a front visibly travels a real
			// share of the cloud and still dies before it becomes weather. **Signed**: each
			// source's contribution keeps its sign (crest positive, trough negative) and
			// the sum is never normalised or rectified, so where two fronts meet, crest on
			// crest reads double and crest on trough reads as calm — before, every source
			// pushed at full strength independently and crossing fronts only ever added
			// ink. The signed sum rides out as vRipple so the fragment can show the
			// interference, not just the displacement.
			float ph = aSeed * 6.2831853;
			float waveTotal = 0.0;
			float ripple = 0.0;
			for (int i = 0; i < WAVE_SOURCES; i++) {
				float amp = uWaveAmp[i];
				if (amp <= 0.0) continue;
				vec3 away = base - uWaveOrigin[i];
				float dist = length(away) + 1e-4;
				// Distances are in the cloud's own box, so a front travels the same share
				// of the picture whatever the viewing scale is set to.
				float front = uWaveAge[i] * uWaveSpeed;
				// Squared by hand: pow(x, 2.0) with a negative base is undefined in GLSL ES
				// (exp2/log2 drivers turn it into NaN, and NaN positions vanish the points).
				float r0 = (dist - front) / uWaveWidth;
				float env = exp(-(r0 * r0));
				float r1 = dist / uWaveLocal;
				float local = exp(-(r1 * r1));
				float phase = (dist - front) * uWaveK + aSeed * 0.35;
				float swell = sin(phase) * env * local * amp;
				p += (away / dist) * swell;
				ripple += swell;
				waveTotal += env * local * amp;
			}
			vRipple = ripple;

			// **Heard, but nothing claimed.** Below the claim gate the points stay dark
			// and no wave launches, which used to read exactly like silence — a bird the
			// corpus could not place produced the same picture as no bird at all. This
			// is the honest third state: a slow, low, grey breath around the *nearest*
			// region (where the unmatched sound would land if it were anything), never
			// the fast signed ripple of a match and never the class colour of a
			// response, so it cannot be misread as one. The breath is deliberately slow
			// (about 0.5 Hz against the ripple's several) — calm, not an event.
			float uDist = length(base - uUnmatchedOrigin) + 1e-4;
			float uNear = exp(-pow(uDist / (uWaveLocal * 1.6), 2.0));
			float uBreath = 0.5 + 0.5 * sin(uTime * 3.1);
			vUnmatchedRing = uNear * uBreath * uUnmatchedStrength;

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
			// The learning swell joins in here — size, not colour, is how slow work shows.
			// The wavefront's own term is the strongest of the three: a point nearly
			// doubles as the ring passes through it, which is what makes the propagation
			// readable across the whole knot rather than only at its landing spot.
			float grow = max(act, learn * 0.6) * (0.35 + 0.9 * uLevel) * (0.5 + 1.0 * aSeed)
				+ aFront * 0.9;
			// The signed field moves size too: a crest swells, a trough pinches, and where
			// two fronts cancel the mark keeps its resting size — the interference is
			// readable in the still frame, not only in the motion.
			grow += clamp(ripple * 5.0, -0.35, 0.7);
			// Unassigned marks are drawn smaller: they are real measurements and they are
			// not structure, and at the same weight a third of the corpus in no cluster
			// reads as a cloud that has one.
			//
			// uUnheard inverts exactly that judgement, and the two ends are one mix so
			// there is only one place the size of a refused mark is decided. At 1 the placed
			// sounds fall to 0.55 and the refused ones rise to 1.6 — the figure/ground
			// discipline of docs/25 §25.2, applied to the one channel that can answer
			// "none of these".
			float refusedSize = mix(1.0 - 0.35 * vRefused, mix(0.55, 1.6, vRefused), uUnheard);
			float size = uPointSize * (1.0 + grow) * (1.0 + 0.7 * vChosen)
				* refusedSize * mix(0.35, 1.0, vArrive) * mix(0.35, 1.0, vLod);
			// uHighlight idles at -1 in silence, which is also the unassigned marker: without
			// the guard every unassigned point drew 15 % larger whenever nothing sounded
			// (the hdbscan map's haze "breathed" at note onsets, inverting the intent).
			if (uHighlight >= 0.0 && abs(uHighlight - aCluster) < 0.5) size *= 1.15;
			// Perspective, but softened. True 1/z is right for a solid and wrong for a
			// scatter: zoomed out every mark falls under a pixel and the cloud turns to fog,
			// zoomed in the near ones become saucers that hide everything behind them. The
			// exponent keeps the *ordering* — nearer is still bigger, which is half the
			// depth cue — while compressing the range enough that a point is a legible dot
			// at every distance. The floor and ceiling catch the extremes of a hard zoom.
			// Exponent 0.7 -> 0.82 (owner: "can we do something to feel the depth more").
			// True 1/z is right for a solid and wrong for a scatter — at 1.0 the far side
			// of the corpus falls under a pixel and turns to fog while the near side
			// becomes saucers — but 0.7 had compressed the range so hard that size had
			// almost stopped being a depth cue at all, and size is the strongest one this
			// picture has after motion parallax. 0.82 restores about half the difference
			// the compression was throwing away; the floor and the 24 px ceiling below
			// still catch both extremes, so nothing new can degenerate.
			float persp = pow(uSizeScale / max(0.001, -mv.z), 0.82);
			// The floor is three device pixels up close, two at galaxy distance: below
			// three a disc has no interior left once the edge is feathered, and the mark
			// degenerates into the feather itself. Up close that is a smudge; at galaxy
			// distance the feather IS the intended haze — and a 2 px sprite is less fill
			// on an integrated GPU — so uNearFloor blends the floor down as the camera
			// backs off and the crisp disc returns on approach. The floor rises with the
			// point's own response: at whole-galaxy zoom persp pins every mark to the
			// floor, which used to erase the size channel exactly when the whole cloud
			// was visible — a responding point is now strictly larger than a resting one
			// at every distance. The ceiling dropped from 42 to 24: zoomed-in saucers
			// are the worst overdraw source on an integrated GPU — transparent sprites
			// stack, and fill rate is the budget there — and a 24 px mark is still a
			// readable disc.
			gl_PointSize = clamp(size * uPixelRatio * persp, mix(2.0, 3.0, uNearFloor) + vAct * 2.0, 24.0);
		}
	`;
}

export const fragmentShader = /* glsl */ `
	uniform vec3 uSurface;
	/** The one colour in the picture — the sung note, or the selected bird. */
	uniform vec3 uAccent;
	uniform float uOpacity;
	/** Live pitch, 0..1 over the corpus's range. Shapes the gradient inside each mark. */
	uniform float uPitch;
	/** Provenance category colours, in PROVENANCE order: authored inventory, our
	 * synthesis of a fitted type, a real recording of one, the unlabelled
	 * pseudo-species, and unidentified field audio. */
	uniform vec3 uProvDoc;
	uniform vec3 uProvLearned;
	uniform vec3 uProvField;
	uniform vec3 uProvArrivals;
	uniform vec3 uProvCand;
	/**
	 * 1 tints every resting point with its own bird's hue.
	 *
	 * A third colour language beside neutral ink and the provenance classes, and it costs no
	 * vertex attribute: the knot's species hue already rides uClusterState's A channel for
	 * the accent, so the resting point can read the same value. That matters, because the
	 * mode this replaces carried a per-point hue attribute and took the program to fifteen
	 * attributes, which failed to link on Mesa's Intel driver in Firefox.
	 *
	 * Off by default and it should stay that way: thousands of species share one hue circle, so at
	 * this density the cloud reads as confetti rather than as an answer to "which bird". It is
	 * offered because the question "where does this species sit" is a real one and no other
	 * channel answers it for the whole corpus at once.
	 */
	uniform float uBird;
	/** 1 for neutral ink/plain points, 0 for the provenance class tint. */
	uniform float uPlain;
	/** 0..1 figure/ground swap for the density verdict; see the vertex stage. */
	uniform float uUnheard;
	/** The same clock the vertex stage pulses by; the orphan pulse breathes on it. */
	uniform float uTime;
	/** Live input level, 0..1 — drives the pulse and the growth in the vertex stage. */
	uniform float uLevel;
	/**
	 * How much the corpus is actually answering, 0..1, smoothed: loudness times match
	 * strength, eased. This is what the resting wash gives way to, and it is deliberately
	 * NOT uLevel.
	 *
	 * Driving the dim off loudness alone meant a sound the corpus could not place — a pure
	 * tone matches almost no bird syllable — dimmed the whole cloud by 40 % and lit
	 * nothing, so a one-tone bird read as the galaxy flinching. And uLevel is the raw
	 * per-frame level, which flickers at audio rate, so the whole picture flickered with
	 * it. Gated on the match, the wash only steps back when there is something behind it
	 * to see; smoothed, it steps back at a speed an eye reads as light rather than as a
	 * fault.
	 */
	uniform float uAnswer;
	/** The travelling front's gaussian width, shared with the vertex stage (same
	 *  uniforms object), so the resting dim can be normalised against the same
	 *  scale the wave is drawn at rather than against a second magic number. */
	uniform float uWaveWidth;
	/** Per-class visibility (documented, learned, field, unlabelled in x..w, candidate
	 * in uProvHideCand): 1 hides the class outright — the Display panel's filter for
	 * isolating, say, only the sounds nobody has named. */
	uniform vec4 uProvHide;
	uniform float uProvHideCand;

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
	varying float vRefused;
	varying float vArrive;
	/** 0..1 across the level-of-detail frontier's fade band; 1 in the active pass. */
	varying float vLod;
	varying float vProv;
	varying float vOrphan;
	varying float vWave;
	varying float vRipple;
	varying float vUnmatchedRing;
	/** The knot's own species hue in turns, 0 = none. See uClusterState's A channel. */
	varying float vHue;

	/**
	 * Hue → RGB at the palette's fixed saturation and lightness, then sRGB → linear.
	 *
	 * The species hues are authored as hsl(h, s, 45%) strings and every other consumer
	 * hands them to THREE.Color.setStyle, which converts into the renderer's working
	 * (linear) space. A shader that skipped the second step would draw the same bird
	 * noticeably brighter here than on its own tag, so the conversion is done with the
	 * exact piecewise transfer function rather than a 2.2 approximation.
	 *
	 * Saturation is the palette's midpoint rather than the bird's own 74-90 % — the
	 * texture channel carries the hue and there is no room for a second number. The
	 * worst case is 8 points of saturation between a knot and its tag, which is under
	 * what the eye separates at this size; the hue, which is the part that says which
	 * clade answered, is exact.
	 */
	vec3 speciesHueColour(float turns) {
		float c = (1.0 - abs(2.0 * 0.45 - 1.0)) * 0.82;
		float hp = fract(turns) * 6.0;
		float x = c * (1.0 - abs(mod(hp, 2.0) - 1.0));
		vec3 rgb = hp < 1.0 ? vec3(c, x, 0.0)
			: hp < 2.0 ? vec3(x, c, 0.0)
			: hp < 3.0 ? vec3(0.0, c, x)
			: hp < 4.0 ? vec3(0.0, x, c)
			: hp < 5.0 ? vec3(x, 0.0, c)
			: vec3(c, 0.0, x);
		rgb += 0.45 - c * 0.5;
		return mix(rgb / 12.92, pow((rgb + 0.055) / 1.055, vec3(2.4)), step(0.04045, rgb));
	}

	void main() {
		// The two-pass split (PointCloud draws the same geometry twice): the resting
		// pass discards whatever is responding, the ACTIVE_PASS discards whatever is
		// not, and the responding pass draws last. With depthWrite off and normal
		// blending, paint order is the only occlusion rule there is — so without the
		// split, a resting point later in the buffer overpaints a lit one regardless
		// of response, and in a dense knot the activation visually vanishes under
		// "old points not moving". The 0.25 matches the "glow is earned" line below;
		// the wavefront rides the active pass because a passing ring *is* the response.
		// The REVEAL_FRONT band below the response cut is the reveal: the shell's
		// skirt carries the knot's whole membership into the active pass as visible
		// density — resting tone, low alpha, no accent — so a passing wave shows the
		// local cloud instead of only its responders.
	#ifdef ACTIVE_PASS
		if (vAct < 0.25 && vWave < ${REVEAL_FRONT}) discard;
	#else
		if (vAct >= 0.25 || vWave >= ${REVEAL_FRONT}) discard;
	#endif
		// 1 exactly on the reveal band: below the response cut in both channels,
		// inside the shell's skirt. Revealed points are density appearing, never an
		// answer being claimed — they keep the resting tone and take none of the
		// response's colour walk, halo or accent.
		float reveal = step(${REVEAL_FRONT}, vWave) * (1.0 - step(0.05, vWave)) * (1.0 - step(0.25, vAct));
		// The Display panel's class filter: hidden provenance classes are gone from
		// the picture entirely (both passes), not dimmed — a dimmed "hidden" class is
		// still a claim about the space it occupies.
		float provHidden = vProv < 0.5 ? uProvHide.x
			: vProv < 1.5 ? uProvHide.y
			: vProv < 2.5 ? uProvHide.z
			: vProv < 3.5 ? uProvHide.w
			: uProvHideCand;
		if (provHidden > 0.5) discard;
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
		// The wavefront earns it outright: where the ring is passing, the halo rides it,
		// so the propagation shows as a bright ring crossing the knot and not only as
		// motion — the visible ordering is the measured one (distance from the landing).
		float glow = max(smoothstep(0.25, 0.75, vAct), vWave);
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
		// **The point cloud speaks provenance, always.** Every point rests as a wash of
		// its class colour and ramps to the class colour itself as it responds — the
		// class tint says *what kind of thing* this sound is (authored inventory,
		// fitted-to-field, unidentified field audio, unlabelled arrival), and "which
		// bird" is the labels' question, answered there in the species hue.
		//
		// The wash sits at 0.5, raised from 0.34: at 0.34 the resting cloud read as a
		// grey mist on the paper (headless screenshots, confirmed by eye — the learned
		// grey majority was nearly invisible and the blue/amber/green minorities were
		// lost entirely). At 0.5 the four classes are plainly told apart at rest —
		// pairwise class distance scales linearly with the wash, 0.146 → 0.215 — and
		// activation keeps its headroom: the colour still walks the whole remaining
		// half of the ramp, and the alpha below nearly doubles on response, so a
		// brightening is unmistakable rather than a nuance. Activation shifts TONE —
		// brighter crest, darker trough via vRipple below — never hue. The accent is
		// untouched: it keeps meaning exactly one thing.
		vec3 prov = vProv < 0.5 ? uProvDoc
			: (vProv < 1.5 ? uProvLearned
			: (vProv < 2.5 ? uProvField
			: (vProv < 3.5 ? uProvArrivals : uProvCand)));
		// The points speak class or ink, never species hue: at this density a hundred
		// hues cannot be told apart, so "who" lives on the labels and on the accent —
		// which in ink mode IS the responding bird's hue, set on the CPU (easeAccent).
		vec3 classCol = prov;
		// The plain look swaps the class colours for a neutral pair and keeps every
		// other rule — same wash, same ramp, same tone shifts — so "coloured / plain"
		// changes what the points *say about provenance*, never how they respond.
		//
		// The pale end of that neutral pair is quoted against the class colours rather
		// than picked by eye, because picked by eye it was much too light: at its old
		// value the resting plain point landed at L* 85.3 on the paper, against a mean
		// of L* 75.0 for the five class colours at the same wash, so switching the
		// colours off also quietly faded the cloud by ten lightness units and the plain
		// mode read as a haze. Matching the mean puts the two modes at the same weight,
		// which is what "only the colour language changes" was always supposed to mean.
		// The bird mode substitutes the species hue for whatever the identity colour would
		// otherwise be, at both weights, so it inherits the same wash toward the surface that
		// keeps the three languages at one lightness — the comment above is the measurement
		// that wash exists for. vHue of 0 means "no bird on this knot", and those points stay
		// in the language they were already speaking rather than going black.
		float hueTurns = (vHue - ${HUE_FLOOR}) / (1.0 - ${HUE_FLOOR});
		vec3 birdCol = speciesHueColour(hueTurns);
		float bird = uBird * step(0.0001, vHue);
		vec3 ink = mix(mix(classCol, vec3(0.13, 0.16, 0.21), uPlain), birdCol, bird);
		vec3 rest = mix(
			uSurface,
			mix(mix(classCol, vec3(0.45, 0.47, 0.50), uPlain), birdCol, bird),
			0.5
		);
		// **The accent is this knot's bird, not the frame's loudest bird.**
		//
		// uAccent is one eased colour for the whole stage, chosen from whichever knot
		// won signal.best. One bird singing: correct. A chorus of five: every sounding
		// knot in the corpus wore one bird's hue, and during the ease it wore a blend of
		// two — which is the "the colours do not line up" report. In ink mode each knot
		// now takes its own species hue straight from the cluster texture's A channel,
		// so two birds answering each other are two colours. Provenance mode keeps the
		// uniform: there the accent is a *class* colour and the class is the subject's,
		// not the knot's. Hue 0 means the knot has no bird (or an older build), and the
		// uniform stands in.
		// The A channel is written with a floor so 0 can mean "no bird" (HUE_FLOOR); the floor
		// comes back off in hueTurns above, where the bird mode also reads it.
		vec3 accent = (uPlain > 0.5 && vHue > 0.0) ? birdCol : uAccent;
		vec3 end = mix(ink, accent, clamp(vAccent, 0.0, 1.0));

		// A chosen bird's points sit most of the way along their own ramp even at rest, so
		// the selection is a violet set of marks rather than the same marks in a thinner
		// crowd. Dimming everyone else was not enough on its own: a bird owns forty of a
		// hundred and seventy-six clusters scattered right across the layout, so with only
		// the dim you could see the threads joining its nodes without being able to point
		// at a single mark and say that one belongs to it. Not all the way, because
		// responding still has to be visible on top of being selected.
		vec3 base = mix(rest, end, 0.8 * vChosen);
		vec3 colour = mix(base, end, clamp(vAct, 0.0, 1.0));

		// A ring of the surface colour around anything that is responding. This is the
		// standard remedy for overlapping marks, and it is what stops a lit knot from
		// fusing into one silhouette: every point keeps a visible edge against its
		// neighbours, so a dense response still reads as a countable spray.
		float ring = (1.0 - smoothstep(0.30, 0.42, d)) * smoothstep(0.30, 0.44, d);
		colour = mix(colour, uSurface, ring * vAct * 0.9);

		// The orphan pulse. A scheduled note whose type owns no cluster cannot light a
		// knot, so its own render points breathe instead — in their provenance colour,
		// with the alpha dipping rather than rising, and with none of the growth, halo
		// or ring a responding cluster gets. "Played, but not placed in the galaxy" is
		// a different claim from "this knot is answering" and must look like one (§8.5).
		//
		// It breathes toward ink, not prov, so the plain mode stays plain. Against
		// prov the pulse kept its class hue even with the colours switched off, which
		// went unnoticed only because the class colour of nearly every point used to be
		// the same grey the plain mode draws; now that the classes carry real hues, that
		// would be an amber or green flash in the mode whose whole promise is neutrality.
		float oPulse = vOrphan * (0.35 + 0.65 * (0.5 + 0.5 * sin(uTime * 7.0 + vSeed * 6.2831853)));
		colour = mix(colour, ink, oPulse * 0.85);

		// The signed ripple, as brightness: a crest darkens toward ink, a trough pales
		// toward the paper, and a cancellation — crest meeting trough — lands back at
		// the resting colour. It is the same sum the displacement used, never
		// normalised, so two crossing fronts read as interference and not as two
		// independent events stacked at full strength. Bounded well under the response
		// ramp: the ripple is motion, not a claim about the point. It darkens toward
		// ink, the mode's own hot end, so provenance colours stay in charge of hue.
		colour = mix(colour, ink, clamp(vRipple * 4.5, 0.0, 0.28));
		colour = mix(colour, uSurface, clamp(-vRipple * 4.5, 0.0, 0.28));

		// The unmatched breath, in a flat mid grey at low weight: *visible* where a
		// sound landed-nearly, and unmistakably not a response — no class colour, no
		// brightness walk, no halo, a fifth of the ripple's tone swing at most.
		colour = mix(colour, vec3(0.45, 0.48, 0.53), clamp(vUnmatchedRing, 0.0, 1.0) * 0.28);

		// Aerial perspective: far points wash toward the paper and thin out, near ones keep
		// their weight. This is what makes a rotating scatter read as a volume rather than
		// as a disc — the size cue alone is too weak once the sizes are compressed, and
		// the eye takes contrast-with-distance as depth without being told.
		//
		// Responding points are exempted in proportion to how hard they respond: the whole
		// job of this view is to show where a sound landed, and a match that happens to be
		// at the back should not be dimmer than the paper. The selected bird gets a
		// lighter, standing version of the same exemption — its marks stay crisp at
		// depth while the selection stands, or "its full cloud" would fog out exactly
		// where the bird owns most of the volume.
		float fog = clamp((vDepth - uFogRange.x) / max(0.001, uFogRange.y - uFogRange.x), 0.0, 1.0);
		fog *= 1.0 - 0.85 * vAct;
		fog *= 1.0 - 0.4 * vChosen;
		// Wash 0.45 -> 0.62 and, new, a slight *darkening* of the near side (owner:
		// "feel the depth more"). Aerial perspective is a contrast gradient and this
		// only had half of one — the far marks paled toward the paper while the near
		// ones sat at the same tone as the middle, so the range the eye reads as depth
		// was the back half only. Pushing the front toward ink as well widens the same
		// gradient from both ends, which is what makes a scatter read as a volume, and
		// it costs one mix. Kept small: at more than a tenth the near marks start
		// reading as *responding*, which is a different claim and one this view has to
		// keep for sound.
		colour = mix(colour, ink, (1.0 - fog) * 0.1 * (1.0 - vAct));
		colour = mix(colour, uSurface, fog * 0.62);

		// Resting points are faint so density reads as tone and the responding ones carry
		// the eye; even at full response it stays under 1, because opaque marks stack into
		// a silhouette and the per-point detail disappears.
		// A chosen point also carries more ink than the same point unselected, so the bird
		// separates from the crowd by weight as well as by everyone else fading.
		// vLod is the level-of-detail dissolve (see the vertex stage): 1 everywhere
		// except the narrow band at the frontier, where it fades the new marks in.
		// The ink half of the figure/ground swap, mirroring refusedSize in the vertex
		// stage: at rest a refused mark keeps 55 % of the ink, and with uUnheard up the
		// placed ones drop to 30 % while the refused ones go to full weight.
		float refusedInk = mix(1.0 - 0.45 * vRefused, mix(0.30, 1.0, vRefused), uUnheard);
		float alpha =
			uOpacity * mask * (0.62 + vAct * 0.38) * vFocus * (1.0 + 0.35 * vChosen) *
			(1.0 - fog * 0.58) * refusedInk * vArrive * vLod;
		// The resting point also gives up a fifth of its weight, so "this knot is
		// answering" moves two channels at once — class colour to full brightness
		// above, ink weight here. Rest lands at 0.62 × 0.8 ≈ 0.50 of full alpha
		// (raised from 0.41 when the rest wash went up: the mist needed presence,
		// and the 2× jump on response is what keeps activation legible above it).
		alpha *= 0.8 + 0.2 * vAct;
		// The reveal sits at a third of a resting mark's weight on top of everything
		// above: present enough that the knot's membership reads as density while the
		// shell crosses it, quiet enough that it can never be mistaken for one of the
		// responders lighting next to it (those keep the full ramp).
		alpha *= mix(1.0, 0.38, reveal);
		// While the corpus is answering, resting ink gives up another share of its weight.
		// Paint order still lets a resting sprite overpaint a lit one behind it (the
		// ACTIVE_PASS split covers the clear responders; this softens the borderline rest),
		// so the response stays legible in the thick of the cloud. Driven by uAnswer, not
		// uLevel — see that uniform for why a loud sound the corpus cannot place must not
		// dim anything. The selected bird is exempt: the dim exists to make the answer
		// legible, and the selection's marks are the thing being read, not the crowd.
		//
		// **Local, not global** (owner, 2026-08-02: "the pointcloud gets denser when
		// activated — can we do it that this is localized"). The dim used to apply to every
		// resting mark in the corpus the moment anything answered, so one syllable restyled
		// the whole galaxy and the eye had nowhere to go. It now rides the travelling front:
		// vWave is this point's own wave amplitude, so the recession follows the shell
		// outward from the knot that sounded and the far side of the cloud is left alone.
		// A floor of 0.25 keeps a whisper of the old global behaviour, so a response is
		// still felt corpus-wide rather than being invisible outside the front.
		float dimHere = mix(0.25, 1.0, clamp(vWave / max(uWaveWidth, 1e-4), 0.0, 1.0));
		alpha *= 1.0 - 0.4 * uAnswer * dimHere * (1.0 - vAct) * (1.0 - vChosen);
		// The dim half of the orphan pulse: it breathes the mark *down* against the
		// paper, the opposite direction from a response.
		alpha *= 1.0 - 0.55 * oPulse;
		// **Throw away the fragments that would blend to nothing.**
		//
		// The shader already discards on the pass split, the class filter and the disc
		// mask — but nothing caught a fragment that survived all three and then had its
		// alpha multiplied down to invisibility by the chain above (aerial perspective,
		// the focus dim, the unassigned shrink, the arrival fade, the resting wash, the
		// answer dim, the orphan breath — seven multiplies, several of which reach zero
		// on their own). Those fragments still cost a full framebuffer read-modify-write
		// each, because this material is transparent with depthWrite off and normal
		// blending, so there is no early-Z and no cheap path for "adds nothing".
		//
		// This is the one place where fill can be cut without changing the picture: at
		// 1/255 the mark is already below what an 8-bit framebuffer can represent, so
		// discarding is not an approximation — the blend it replaces is a no-op. Fill is
		// the dominant cost here (roughly 45 M blended fragments a frame at 348 461 points
		// against ~20 MB of vertex fetch per pass), and a dimmed corpus is exactly the
		// state the galaxy spends most of its time in.
		if (alpha < 0.004) discard;
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
	/**
	 * Per node, the type's *other* knots — empty for all but the split types.
	 *
	 * A type the build split owns two knots, and both are that sound. They light and are
	 * tagged with the node itself, so no lit blob is ever left unnamed; the thread runs
	 * through `nodes` alone, because a song is a sequence in time and a forked line would
	 * say the bird sang one syllable in two places at once.
	 */
	companions: number[][] | null;
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

/**
 * One thread in the backdrop, and **which claim it makes**.
 *
 * The three kinds of faint line around a selected bird used to be drawn in one identical
 * grey: its documented songs (sequences a person authored or recorded), its measured
 * grammar (transitions counted from its own field audio), and — from `RelationThreads` —
 * hairlines out to other species that share call shapes. Three answers to three different
 * questions at one weight, which is why the web read as decoration: not that the lines
 * meant nothing, but that the picture refused to say which meaning each line had.
 *
 * `kind` is what the segment is claiming. `weight` is how strongly, and it exists because
 * the grammar already carries a measured probability that was **thrown away at draw
 * time** — the number was computed, filtered against `GRAMMAR_FLOOR`, and then every
 * surviving transition was drawn identically whether it happens nine times in ten or once
 * in twelve.
 */
export interface ContextPath {
	/** Cluster indices. Two for a grammar pair, the whole route for a song. */
	nodes: number[];
	/**
	 * `song` — an authored or recorded sequence. `grammar` — one measured transition.
	 *
	 * They are separated here rather than at the draw call because a song is a *fact about
	 * a recording* and a grammar pair is a *statistic over many*, and nothing downstream
	 * can recover the difference from a list of node indices.
	 */
	kind: 'song' | 'grammar';
	/**
	 * 0..1. The measured transition probability for `grammar`.
	 *
	 * 1 for a song, and that is not a probability standing in for one: an authored
	 * sequence either is this bird's song or is not in the corpus, so there is no measured
	 * uncertainty to draw. A song is therefore drawn at full backdrop strength and only
	 * the grammar varies, which keeps the weight channel meaning one thing.
	 */
	weight: number;
}

/** Per-frame signal shared between the audio loop and the renderer. Mutated in place. */
export interface VisualSignal {
	activations: Float32Array;
	/**
	 * Per cluster, 1 where a note is *being sung right now* and 0 where the cluster is
	 * merely responding to it.
	 *
	 * These are two different claims and the picture used to make them identically. When
	 * Lyrebird sings a Bengalese finch syllable, the scheduled node lights because we know
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
	/**
	 * Per point, 1 while a *scheduled* note whose type owns no cluster is sounding.
	 *
	 * An orphan type has render points with real positions but no knot, so it cannot
	 * light through `activations`/`sung` — those are per cluster. This channel is how
	 * it is shown anyway, and it is deliberately a separate buffer: a point flashing
	 * here says "played, but not placed in the galaxy", which is a different claim
	 * from a cluster answering and must not share its look (§8.5).
	 */
	orphanPulse: Float32Array;
	level: number;
	f0: number;
	/** 0..1 — how well the live input matches anything in the corpus. */
	strength: number;
	/** Index of the most active cluster, or -1. */
	best: number;
	/**
	 * Index of the cluster *nearest* the live input while it is heard but below the
	 * claim gate, or -1. The renderer gives that region the slow grey unmatched
	 * breath — a third state that is neither a match nor silence (§8.5).
	 */
	unmatched: number;
	/** Active trajectories, most recent last. */
	paths: LivePath[];
	/** Bumped whenever the set of paths changes, so the renderer rebuilds its geometry. */
	pathsVersion: number;
	/**
	 * The web around the selected bird: its documented songs and its measured grammar.
	 * Segments shared between songs overlap and so read stronger, which shows at a glance
	 * which transitions this bird reuses.
	 */
	context: ContextPath[];
	contextVersion: number;
	/** Species index to keep at full strength; -1 shows every species equally. */
	focus: number;
}

export function createSignal(clusterCount: number, pointCount = 0): VisualSignal {
	return {
		activations: new Float32Array(Math.max(1, clusterCount)),
		sung: new Float32Array(Math.max(1, clusterCount)),
		pointActivation: new Float32Array(Math.max(1, pointCount)),
		orphanPulse: new Float32Array(Math.max(1, pointCount)),
		level: 0,
		f0: 0,
		strength: 0,
		best: -1,
		unmatched: -1,
		paths: [],
		pathsVersion: 0,
		context: [],
		contextVersion: 0,
		focus: -1
	};
}

/** Trajectories are drawn as disconnected segments so separate paths never join up. */
export const MAX_PATHS = 10;

/**
 * Linear RGB interpolation for the trajectory gradient: t = 0 is the segment's start
 * knot, t = 1 its end knot, and the midpoint is the even blend. The gradient's whole
 * truth is in its endpoints (each knot's own species colour); the walk between them
 * is presentation.
 */
export function mixRgb(a: readonly number[], b: readonly number[], t: number): number[] {
	return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

/**
 * The activation wavefront: when a cluster starts responding, a ring leaves the place
 * the sound landed and crosses the knot, and each member pulses as the ring reaches it.
 * Every quantity in it is a measurement, mapped as follows:
 *
 * - **origin** — the response-weighted centroid of the cluster's members (computed in
 *   PointCloud from `signal.pointActivation`, the per-point measured similarity): the
 *   front starts where inside the knot the input actually landed, not at a decoration
 *   point. Falls back to the geometric centroid for a scheduled note, whose per-point
 *   response is flat by construction.
 * - **pulse time** — the point's true 3-d distance from that origin, divided by the
 *   cluster's true radius (its farthest member), so `d` is 0 at the landing spot and 1
 *   at the rim whatever the knot's real extent. The ring arrives at `d = age ·
 *   FRONT_SPEED`, so arrival order *is* distance order — the harness asserts the
 *   monotonicity.
 * - **amplitude** — the ring's height at a point is scaled by that point's own measured
 *   response (`pointActivation[i]`, with the cluster activation as floor), so the front
 *   ignites the members that really sound like the input hardest instead of switching
 *   the knot on as one blob.
 *
 * The positions below are *normalized radial units* (share of the knot's own radius),
 * not box units, because the knot's extent is the measurement that sets the scale.
 */

/** Ring speed in knot-radii per second: the front crosses a knot in about 0.42 s. */
export const FRONT_SPEED = 2.4;
/**
 * Ring thickness in knot-radii: broad enough to read as a front, tight enough to
 * order neighbours. Widened 0.16 → 0.22 (2026-08-02, owner: "propagate more and be
 * stronger") — the shell's gaussian is ~37 % broader, so the front reads as a wave
 * moving through the knot's whole neighbourhood rather than a rim flash, and the
 * reveal skirt (REVEAL_FRONT) widens with it automatically.
 */
export const FRONT_WIDTH = 0.22;
/** Seconds a front lives from onset; the ring has crossed and faded by then. */
export const FRONT_LIFE = 0.95;
/** Cluster activation rising through this starts a front; falling back through it re-arms. */
export const FRONT_ONSET = 0.15;

/**
 * Front amplitude over its life: a fast attack so the onset is visible the frame it
 * happens, then a decay once the ring has reached the rim (age ≈ 1/FRONT_SPEED), so a
 * fired front leaves the knot to its steady response rather than shimmering on.
 */
export function frontEnvelope(age: number): number {
	if (age < 0 || age > FRONT_LIFE) return 0;
	const attack = Math.min(1, age / 0.04);
	const decay = Math.exp(-Math.max(0, age - 1 / FRONT_SPEED) * 4);
	return attack * decay;
}

/**
 * The ring itself: a gaussian in normalized distance, centred where the front has
 * travelled to at `age`. This is the only place pulse time is set — true distance from
 * the origin, never a per-point random phase.
 */
export function frontRing(distNorm: number, age: number): number {
	const x = (distNorm - age * FRONT_SPEED) / FRONT_WIDTH;
	return Math.exp(-x * x) * frontEnvelope(age);
}

/**
 * Does the current best match carry enough of a claim to draw the wave at all.
 *
 * The wave and the grid cross say "a sound landed *here*" — they are the same claim
 * the points make when they light, so they must answer to the same evidence. Both used
 * to fire on loudness (`signal.level > 0.04`), which loud room tone and a weak
 * self-match of the synth both pass: the front launched from the nearest knot while
 * that knot's points stayed dark, reported as "the wave moves but nothing activates".
 * Now the gate is the claim itself: either the best cluster is visibly responding
 * (a scheduled note, or a strong match's softmax share), or the match strength is past
 * the floor at which a response becomes visible at all.
 */
export function waveClaim(signal: VisualSignal): boolean {
	const best = signal.best;
	if (best < 0) return false;
	return (signal.activations[best] ?? 0) > 0.08 || signal.strength > 0.15;
}

/**
 * The third state between a match and silence: input is voiced (`active`), something
 * is audible above the noise floor (strength > 0.02), yet the claim gate stays shut —
 * so the *nearest* cluster's region gets the slow grey unmatched breath. Returns the
 * nearest cluster's index, or -1 for either of the other two states: a claim (which
 * lights its knot and must never also breathe grey) and silence (which shows nothing).
 */
export function unmatchedCluster(signal: VisualSignal, active: boolean): number {
	if (!active || waveClaim(signal) || signal.strength <= 0.02 || signal.best < 0) return -1;
	return signal.best;
}

/** Per-cluster membership for the wavefront. */
export interface ClusterMembers {
	/** Point indices per cluster, in points.json order. */
	members: Int32Array[];
	/** Farthest member's true distance from the geometric centroid, per cluster. */
	radii: Float32Array;
}

/**
 * Which points each cluster holds, and how far its knot really extends — built once at
 * load from the shipped positions. The wavefront's timing normalization is quoted
 * against `radii`, so the front crosses every knot in the same *share* of its own
 * extent whatever the knot's true size.
 */
export function buildClusterMembers(
	positions: Float32Array,
	clusterId: ArrayLike<number>,
	k: number
): ClusterMembers {
	const n = clusterId.length;
	const lists: number[][] = Array.from({ length: k }, () => []);
	for (let i = 0; i < n; i++) {
		const c = clusterId[i];
		if (c >= 0 && c < k) lists[c].push(i);
	}
	const members = lists.map((l) => Int32Array.from(l));
	const radii = new Float32Array(k);
	for (let c = 0; c < k; c++) {
		const mem = members[c];
		if (!mem.length) continue;
		let cx = 0,
			cy = 0,
			cz = 0;
		for (const i of mem) {
			cx += positions[i * 3];
			cy += positions[i * 3 + 1];
			cz += positions[i * 3 + 2];
		}
		cx /= mem.length;
		cy /= mem.length;
		cz /= mem.length;
		let radius = 0;
		for (const i of mem) {
			const d = Math.hypot(
				positions[i * 3] - cx,
				positions[i * 3 + 1] - cy,
				positions[i * 3 + 2] - cz
			);
			if (d > radius) radius = d;
		}
		radii[c] = Math.max(radius, 1e-4);
	}
	return { members, radii };
}


/**
 * The thread with a width in pixels — two triangles a segment, offset perpendicular in
 * screen space. See `ribbon.ts` for why a GL line could not do this job.
 *
 * The width is not constant along the thread, and that is the answer to "a song playing
 * should animate its line". Three things widen it, all in the vertex shader so they move
 * the geometry rather than only its brightness:
 *
 * - the **travelling peak**, the same gaussian the bead rides, so the note passing along
 *   the phrase is a swell running through the line;
 * - the part **already sung**, held a little fuller than the part still to come, so the
 *   phrase visibly fills in as it is performed;
 * - nothing at all while idle: a selected-but-unplayed call stays the thin thread it was.
 */
export const trajectoryRibbonVertexShader = /* glsl */ `
	attribute vec3 aOther;
	attribute float aSide;
	attribute float aIndex;
	attribute float aPath;
	attribute vec3 aColour;

	uniform float uProgress[${MAX_PATHS}];
	uniform float uAlpha[${MAX_PATHS}];
	/** Drawing-buffer size in device pixels, for the pixels-to-clip conversion below. */
	uniform vec2 uResolution;
	/** Resting thread width, full width in *device* pixels (the component scales it). */
	uniform float uWidth;

	varying float vIndex;
	varying float vProgress;
	varying float vAlpha;
	varying float vPeak;
	varying float vSide;
	varying vec3 vColour;

	void main() {
		int p = int(aPath + 0.5);
		vIndex = aIndex;
		vProgress = uProgress[p];
		vAlpha = uAlpha[p];
		vColour = aColour;
		vSide = aSide;

		bool singing = vProgress >= 0.0;
		// Squared by hand — pow with a negative base is undefined in GLSL ES.
		float r = (aIndex - vProgress) / 0.45;
		vPeak = singing ? exp(-(r * r)) : 0.0;
		float passed = singing ? step(aIndex, vProgress) : 0.0;

		vec4 self = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
		vec4 other = projectionMatrix * modelViewMatrix * vec4(aOther, 1.0);

		// Screen-space direction, so the width is in pixels at any depth. Both endpoints
		// have to be in front of the camera for the perspective divide to mean anything;
		// when one is not, the ribbon collapses to its centre line rather than being
		// thrown across the screen by a division through a negative w.
		float wSelf = max(self.w, 1e-6);
		float wOther = max(other.w, 1e-6);
		vec2 screenSelf = self.xy / wSelf * uResolution;
		vec2 screenOther = other.xy / wOther * uResolution;
		vec2 delta = screenOther - screenSelf;
		float len = length(delta);
		bool visible = self.w > 0.0 && other.w > 0.0 && len > 1e-6;

		float width = uWidth * (1.0 + 0.35 * passed + 1.6 * vPeak);
		vec2 dir = visible ? delta / len : vec2(1.0, 0.0);
		vec2 normal = vec2(-dir.y, dir.x);
		// Pixels to clip space, and the two factors that look missing are cancelled:
		// a corner steps a *half* width (x0.5), and NDC spans 2 units across
		// uResolution pixels (x2.0). Their product is 1. Then clip = ndc * w.
		vec2 offset = visible
			? normal * aSide * width * self.w / uResolution
			: vec2(0.0);

		self.xy += offset;
		gl_Position = self;
	}
`;

export const trajectoryRibbonFragmentShader = /* glsl */ `
	uniform vec3 uColdColor;

	varying float vIndex;
	varying float vProgress;
	varying float vAlpha;
	varying float vPeak;
	varying float vSide;
	varying vec3 vColour;

	void main() {
		bool singing = vProgress >= 0.0;
		// while idle the whole path reads as one faint thread; while singing the part
		// already sung stays lit so the order of the phrase remains visible
		float passed = singing ? step(vIndex, vProgress) : 1.0;

		// The ribbon has real width now, so it also needs an edge. Without this the
		// quad's sides are hard pixel steps and a near-horizontal thread crawls.
		float edge = 1.0 - smoothstep(0.55, 1.0, abs(vSide));

		float base = 0.55 + 0.35 * passed;
		vec3 colour = mix(uColdColor, vColour, clamp(0.35 + vPeak, 0.0, 1.0));
		float a = vAlpha * (base + vPeak * 0.6) * edge;
		if (a < 0.004) discard;
		gl_FragColor = vec4(colour, clamp(a, 0.0, 1.0));
	}
`;

/**
 * Beads along the same polyline. Kept now that the thread has a width of its own: the
 * bead is where the note *is*, which a swell in a line says less precisely than a mark
 * running along it.
 */
export const trajectoryPointsVertexShader = /* glsl */ `
	attribute float aIndex;
	attribute float aPath;
	/** This vertex's hue along the thread's gradient (see the line shader's aColour). */
	attribute vec3 aColour;

	uniform float uProgress[${MAX_PATHS}];
	uniform float uAlpha[${MAX_PATHS}];
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
		// The bead and the wave it rides share the segment's gradient colour, so the
		// travelling highlight is the same hue as the knot it is leaving and becoming.
		vColour = aColour;
		bool singing = vProgress >= 0.0;
		// Squared by hand — pow with a negative base is undefined in GLSL ES.
		float r = (aIndex - vProgress) / 0.45;
		vPeak = singing ? exp(-(r * r)) : 0.0;

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
