<script lang="ts">
	import { T, useTask, useThrelte } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';
	import {
		CLASS_COUNT,
		buildSpeciesIndex,
		clusterProvenance,
		pointProvenance
	} from '$lib/data/assets';
	import type { BirdyAssets } from '$lib/data/types';
	import {
		FRONT_LIFE,
		FRONT_ONSET,
		SIZE_REFERENCE,
		WAVE_SOURCES,
		buildClusterMembers,
		fragmentShader,
		frontRing,
		vertexShader,
		waveClaim,
		type VisualSignal
	} from './shaders';
	import {
		ACCENT,
		PROV_ARRIVALS,
		PROV_CANDIDATE,
		PROV_DOCUMENTED,
		PROV_FIELD,
		PROV_LEARNED,
		provenanceColour,
		speciesColour
	} from './palette';
	import { buildLayout, nearestNeighbourDistances, type LayoutView } from './layouts';
	import type { GalaxyStats } from './stats';

	interface Props {
		assets: BirdyAssets;
		signal: VisualSignal;
		pointSize?: number;
		/** Species index to keep at full strength; -1 shows every species equally. */
		focus?: number;
		/** Multiplies the animation clock, so the pulse can be slowed down. */
		speed?: number;
		/** Written into as the cloud is placed, so lines and labels follow their knots. */
		view: LayoutView;
		/** The scale the whole group is drawn at, from the listening distance. */
		spread?: number;
		/**
		 * Clusters the learning pipeline is working on right now. They pulse, so the corpus
		 * shows where the work is happening rather than leaving it to a progress bar.
		 */
		learning?: number[];
		/**
		 * Neutral ink points instead of the provenance class tint. Only the points'
		 * colour language changes; activation, wave and labels keep their meanings.
		 */
		plain?: boolean;
		/**
		 * Per-class visibility in PROVENANCE order (documented, learned, field,
		 * unlabelled, candidate); false hides the class outright. The Display
		 * panel's filter — isolating the unidentified is the arrivals live view.
		 */
		provShown?: boolean[];
		/**
		 * The density governor: let the measured frame time hold the LOD frontier back
		 * instead of letting the camera alone decide how much draws. On by default —
		 * the Display panel's "adaptive detail" switch turns it off.
		 */
		adaptive?: boolean;
		/** Written, never read: how many points each pass actually drew. See stats.ts. */
		stats?: GalaxyStats;
	}

	let {
		assets,
		signal,
		pointSize = 3,
		focus = -1,
		speed = 1,
		view,
		spread = 1,
		learning = [],
		plain = false,
		provShown = [true, true, true, true, true],
		adaptive = true,
		stats
	}: Props = $props();

	// The corpus never changes while the component is alive, so the buffers are built once
	// from the initial props rather than tracked.
	const clusterCount = untrack(() => Math.max(1, assets.centroids.items.length));

	// Species index (as `focus` carries it) back to species id, for the accent's target.
	const speciesIdByIndex = untrack(() => {
		const ids: string[] = [];
		buildSpeciesIndex(assets).forEach((index, id) => (ids[index] = id));
		return ids;
	});

	/**
	 * Per-knot provenance class, and the same summary per species, so the accent can name
	 * its subject in whichever colour language the stage is speaking. Built once.
	 */
	const knotClass = untrack(() => clusterProvenance(assets));
	const speciesClass = untrack(() => {
		const index = buildSpeciesIndex(assets);
		const classes = pointProvenance(assets);
		const tally = new Map<number, Uint32Array>();
		for (let i = 0; i < classes.length; i++) {
			const s = index.get(assets.points.speciesId[i] ?? '');
			if (s === undefined) continue;
			let row = tally.get(s);
			if (!row) tally.set(s, (row = new Uint32Array(CLASS_COUNT)));
			row[classes[i]]++;
		}
		const out: number[] = [];
		tally.forEach((row, s) => {
			let best = 0;
			for (let c = 1; c < CLASS_COUNT; c++) if (row[c] > row[best]) best = c;
			out[s] = best;
		});
		return out;
	});

	/**
	 * The accent's colour is a *subject* marker, and a subject that changes without a
	 * snap. Its hue follows whoever the accent currently belongs to — the selected bird,
	 * or the cluster the sound just landed on — easing over about half a second so a
	 * chorus reads as one colour walking between subjects rather than a frame of strobe.
	 * With no subject it settles back to the interface violet, which is the "no claim
	 * about who" state.
	 *
	 * **Which hue it eases to depends on the language the stage is speaking**, and it has
	 * to, because the accent is what a knot walks toward as it lights. In provenance
	 * mode the accent is the subject's class colour — the activation speaks the same
	 * "what kind of thing" as the resting cloud. In ink mode it is the subject's own
	 * species hue, the same FNV-hash hue the labels carry: a singing bird lights in
	 * ITS hue on a neutral field, which is how the response says "who" without
	 * painting the whole cloud in hues that cannot be told apart at this density
	 * (the bird-colour point mode did exactly that, and is gone). With no
	 * identifiable species the violet stands in.
	 *
	 * What the accent *means* is untouched either way: it is still "this is the one you
	 * asked for", and it is still the only thing on the field wearing it.
	 */
	const accentNow = untrack(() => new THREE.Color(ACCENT));
	const accentTarget = new THREE.Color(ACCENT);

	function easeAccent(delta: number) {
		let hue = '';
		if (!plain) {
			// Provenance mode: the class colour.
			let cls = -1;
			if (focus >= 0) cls = speciesClass[focus] ?? -1;
			else if (waveClaim(signal)) cls = knotClass[signal.best] ?? -1;
			if (cls >= 0) hue = provenanceColour(cls);
		} else {
			// Ink mode: the subject's own hue — the selected bird, or whoever the
			// sounding knot belongs to. Empty stays violet: no claim about who.
			let subject = '';
			if (focus >= 0) subject = speciesIdByIndex[focus] ?? '';
			else if (waveClaim(signal)) subject = assets.centroids.items[signal.best]?.speciesId ?? '';
			if (subject) hue = speciesColour(subject);
		}
		accentTarget.set(hue || ACCENT);
		const eased = accentNow.lerp(accentTarget, Math.min(1, delta * 4));
		material.uniforms.uAccent.value = eased;
	}

	// One float per point, rewritten from the listener's per-point response every frame
	// that something sounds — silent frames upload nothing, see the gate in useTask.
	// A dynamic attribute rather than a texture: 4287 floats is 17 kB, and going through
	// a data texture would cost a fetch per vertex to save an upload that is already free.
	const activation = untrack(() => new Float32Array(assets.points.n));
	const activationAttribute = new THREE.BufferAttribute(activation, 1).setUsage(
		THREE.DynamicDrawUsage
	);

	// The orphan channel: one float per point, rewritten from the schedule (not the
	// matcher) while a syllable with no cluster of its own is sounding. Same dynamic-
	// attribute shape as `activation`, for the same reason.
	const orphan = untrack(() => new Float32Array(assets.points.n));
	const orphanAttribute = new THREE.BufferAttribute(orphan, 1).setUsage(THREE.DynamicDrawUsage);

	// The wavefront channel: one float per point, rewritten from the front pass below
	// while a front is travelling. The third dynamic per-point attribute — same 75 k
	// floats, same free upload as `activation` and `orphan`.
	const front = untrack(() => new Float32Array(assets.points.n));
	const frontAttribute = new THREE.BufferAttribute(front, 1).setUsage(THREE.DynamicDrawUsage);

	// One arrangement, one position buffer. The aTarget/uMorph pair it used to pair
	// with was dead weight — uMorph never left zero — and cost a vertex attribute the
	// program could not spare; see aMisc below.
	const current = untrack(() => Float32Array.from(assets.positions));
	const positionAttribute = new THREE.BufferAttribute(current, 3).setUsage(
		THREE.DynamicDrawUsage
	);

	/**
	 * Four per-point floats packed into one vec4: x = seed (phase offsets), y = bloom
	 * budget, z = blossom magnitude, w = LOD rank. Packing is not tidiness, it is
	 * budget: Mesa's Intel driver in Firefox reports fewer than 15 vertex attribute
	 * slots, and the 15-attribute program failed to link there, so four floats ride
	 * one slot (10 attributes now — the bird-colour mode's per-point hue went with
	 * the mode). The array is allocated once and each untrack
	 * block below writes the channel it owns — the geometry block the seed, the
	 * aRadDir block bloom and spread, the lod block the rank. Dynamic because the
	 * rank channel is rewritten on a focus change (`reorderCells`); that change
	 * uploads the whole packed buffer, 5.6 MB at the shipped corpus against the old
	 * rank-only 1.4 MB — still a focus change only, never a frame.
	 */
	const misc = untrack(() => new Float32Array(assets.points.n * 4));
	const miscAttribute = untrack(() =>
		new THREE.BufferAttribute(misc, 4).setUsage(THREE.DynamicDrawUsage)
	);

	const geometry = untrack(() => {
		const g = new THREE.BufferGeometry();
		g.setAttribute('position', positionAttribute);
		// aMisc lands here, on the base geometry, because the resting cells and the
		// active geometry copy this geometry's attribute objects at construction — a
		// per-point attribute added after those copies would never reach either pass.
		g.setAttribute('aMisc', miscAttribute);
		const cluster = new Float32Array(assets.points.n);
		const species = new Float32Array(assets.points.n);
		// -1 survives into the attribute rather than being clamped to 0: a point in no
		// cluster is a result the density clustering went out of its way to produce, and
		// the shader is what respects it.
		const born = new Float32Array(assets.points.n);
		const generation = assets.points.generation;
		const speciesIndex = buildSpeciesIndex(assets);
		for (let i = 0; i < assets.points.n; i++) {
			cluster[i] = assets.points.clusterId[i] ?? -1;
			species[i] = speciesIndex.get(assets.points.speciesId[i] ?? '') ?? -1;
			born[i] = generation?.[i] ?? 0;
			// The seed channel of aMisc: per-point phase offsets, the same multiply-
			// and-mod hash the shader's texture term is tuned against.
			misc[i * 4] = ((i * 2654435761) % 1000) / 1000;
		}
		g.setAttribute('aCluster', new THREE.BufferAttribute(cluster, 1));
		g.setAttribute('aSpecies', new THREE.BufferAttribute(species, 1));
		g.setAttribute('aBorn', new THREE.BufferAttribute(born, 1));
		g.setAttribute('aAct', activationAttribute);
		g.setAttribute('aProv', new THREE.BufferAttribute(pointProvenance(assets), 1));
		g.setAttribute('aOrphan', orphanAttribute);
		g.computeBoundingSphere();
		return g;
	});

	/**
	 * The three per-cluster channels as one RGB texture (see `uClusterState` in
	 * shaders.ts for why it is not three uniform arrays). Width is capped at 1024 so
	 * the texture stays within every implementation's 2D limit whatever the corpus
	 * asks for: 1 024 knots is one row, the shipped build's 14 003 is fourteen.
	 */
	const clusterTexWidth = Math.min(1024, Math.max(1, clusterCount));
	const clusterTexHeight = Math.max(1, Math.ceil(Math.max(1, clusterCount) / clusterTexWidth));
	const clusterState = untrack(
		() => new Float32Array(clusterTexWidth * clusterTexHeight * 4)
	);
	const clusterTexture = untrack(() => {
		const t = new THREE.DataTexture(
			clusterState,
			clusterTexWidth,
			clusterTexHeight,
			THREE.RGBAFormat,
			THREE.FloatType
		);
		// Nearest, no mipmaps: every read is an exact texel lookup of one cluster's
		// channels. Any filtering here would blend one knot's activation into its
		// neighbour's, which is a claim about the corpus that the sampler would be
		// making on its own.
		t.minFilter = THREE.NearestFilter;
		t.magFilter = THREE.NearestFilter;
		t.generateMipmaps = false;
		t.needsUpdate = true;
		return t;
	});

	const material = new THREE.ShaderMaterial({
		vertexShader: vertexShader(),
		fragmentShader,
		uniforms: {
			uClusterState: { value: clusterTexture },
			uClusterTexSize: {
				value: new THREE.Vector2(clusterTexWidth, clusterTexHeight)
			},
			// The live accent: `accentNow` below is mutated in place each frame, and the
			// renderer reads the colour object's channels when it uploads the uniform.
			uAccent: { value: new THREE.Color(ACCENT) },
			uProvDoc: { value: new THREE.Color(PROV_DOCUMENTED) },
			uProvLearned: { value: new THREE.Color(PROV_LEARNED) },
			uProvField: { value: new THREE.Color(PROV_FIELD) },
			uProvArrivals: { value: new THREE.Color(PROV_ARRIVALS) },
			uProvCand: { value: new THREE.Color(PROV_CANDIDATE) },
			uPlain: { value: untrack(() => (plain ? 1 : 0)) },
			// "Heard, but nothing claimed": where the nearest region breathes, and how
			// strongly. Eased in the frame task; 0 means silent.
			uUnmatchedOrigin: { value: new THREE.Vector3() },
			uUnmatchedStrength: { value: 0 },
			uTime: { value: 0 },
			uLevel: { value: 0 },
			// Smoothed loudness x match: what the resting wash gives way to. See uAnswer
			// in shaders.ts — the raw level dimmed the cloud for sounds it could not place.
			uAnswer: { value: 0 },
			uPointSize: { value: untrack(() => pointSize) },
			uPixelRatio: { value: typeof window === 'undefined' ? 1 : Math.min(2, window.devicePixelRatio) },
			uHighlight: { value: -1 },
			// Rewritten from `spread` below; the initial value only has to be sane.
			uSizeScale: { value: SIZE_REFERENCE },
			// uMorph (0 → 1 between `position` and aTarget) is gone with the one-layout
			// world: it never left zero, and its attribute was one the program could
			// not spare. If a morph ever comes back it is in git history.
			// The generation currently arriving, and how far its arrival has run. Set from
			// the manifest; 0 on an asset set built before growth existed, which makes the
			// arrival a no-op because every point then shares generation 0 and starts done.
			uGeneration: { value: untrack(() => assets.manifest?.generation ?? 0) },
			uArrival: { value: untrack(() => (assets.manifest?.generation ? 0 : 1)) },
			uFocus: { value: -1 },
			// Enough that an unselected species still reads as part of the same corpus.
			//
			// Pushed down to 0.07 while chasing "make the selection stand out" and that was
			// the wrong lever: the selected bird is only about six percent of the points, so
			// erasing the other ninety-four left the accent as the only thing on screen and
			// it looked like everything was selected. The accent, the extra size and the
			// extra weight already say which bird it is; the crowd has to stay visible for
			// there to be anything to stand out *of*.
			uFocusDim: { value: 0.22 },
			// The level-of-detail frontier, 0..1 of the priority order — rewritten every
			// frame from the camera distance by updateLod, so the initial value only has
			// to be sane for the first frame. The responding pass ignores it (see vLod).
			uLod: { value: 1 },
			// The knot blossom, 0 closed .. 1 fully open — rewritten every frame from the
			// camera distance by updateLod (opens inside 1.9 cloud radii, fully open at
			// 1.0), so the initial value only has to be sane for the first frame.
			uBlossom: { value: 0 },
			// Blends the point-size floor between 2 and 3 device pixels (1 near, 0 far) —
			// same per-frame driver as uBlossom.
			uNearFloor: { value: 0 },
			uOpacity: { value: 1 },
			uProvHide: { value: new THREE.Vector4() },
			uProvHideCand: { value: 0 },
			// Filled in every frame from the camera's distance to the cloud; the initial
			// value only has to be sane for the first frame.
			uFogRange: { value: new THREE.Vector2(2, 5) },
			uPitch: { value: 0.5 },
			uWaveK: { value: 6 },
			uWaveSpeed: { value: 0.9 },
			uWaveWidth: { value: 0.35 },
			uWaveOrigin: { value: Array.from({ length: WAVE_SOURCES }, () => new THREE.Vector3()) },
			uWaveAge: { value: new Float32Array(WAVE_SOURCES) },
			uWaveAmp: { value: new Float32Array(WAVE_SOURCES) },
			// Rewritten from the loaded corpus's own knot spacing (see below); the initial
			// value is the 149-cluster build's number, sane for the first frame.
			uWaveLocal: { value: 0.27 },
			uSurface: { value: new THREE.Color('#fafbfc') }
		},
		transparent: true,
		depthWrite: false,
		blending: THREE.NormalBlending
	});

	// The responding pass: same geometry, same uniforms (shared by reference, so the
	// per-frame writes in useTask update both), one define different. It draws after
	// the resting pass (renderOrder 1), so nothing resting can overpaint something
	// lit — the shine-through fix for "activated points buried under old points".
	// The clone deep-copies the uniforms, so they are re-shared by hand; blending
	// and depth state copy over unchanged, which keeps resting-on-resting and
	// lit-on-lit compositing bit-identical to the single-pass picture.
	const materialActive = material.clone();
	materialActive.defines = { ACTIVE_PASS: 1 };
	materialActive.uniforms = material.uniforms;

	$effect(() => {
		material.uniforms.uPointSize.value = pointSize;
	});

	$effect(() => {
		const v = material.uniforms.uProvHide.value as THREE.Vector4;
		v.set(
			provShown[0] ? 0 : 1,
			provShown[1] ? 0 : 1,
			provShown[2] ? 0 : 1,
			provShown[3] ? 0 : 1
		);
		material.uniforms.uProvHideCand.value = provShown[4] ? 0 : 1;
	});

	$effect(() => {
		material.uniforms.uFocus.value = focus;
	});

	$effect(() => {
		material.uniforms.uPlain.value = plain ? 1 : 0;
	});

	$effect(() => {
		material.uniforms.uSizeScale.value = SIZE_REFERENCE * spread;
	});

	const layout = untrack(() => buildLayout(assets));

	/**
	 * Seed the buffers from the layout, not from the raw asset.
	 *
	 * They were filled with `assets.positions` at construction, and drawing from the raw
	 * projection while the labels read the layout's centroids let any transform the
	 * layout applies drift the marks off their tags. The bounding sphere is recomputed
	 * for the same reason: the layout's knot separation (KNOT_GAP in layouts.ts) pushes
	 * points past the raw projection's bounds, and fitFog and the active geometry both
	 * read this sphere.
	 */
	untrack(() => {
		current.set(layout.positions);
		positionAttribute.needsUpdate = true;
		geometry.computeBoundingSphere();
		view.centroids.set(layout.centroids);
		view.counts.set(layout.counts);
		view.version++;
	});

	/**
	 * The wavefront's static half: per-cluster membership and true radii. Built once
	 * from the shipped geometry — the front pass below only ever recomputes the
	 * *timing*, never the structure.
	 */
	const graph = untrack(() =>
		buildClusterMembers(layout.positions, assets.points.clusterId, clusterCount)
	);

	/**
	 * The median nearest-neighbour centroid distance of the loaded build, kept next to
	 * the uniform it feeds: the knot blossom below quotes its own cap against the same
	 * spacing, so neither knot's display drift can reach into its neighbour. The
	 * initial value is the fallback the wave used to carry inline.
	 */
	let medianKnotSpacing = 0.135;

	/**
	 * How far a ripple reaches, quoted from the corpus's own spacing: twice the median
	 * nearest-neighbour centroid distance of the loaded build, so it adapts when a
	 * rebuild packs the knots tighter or looser instead of being tuned per build.
	 *
	 * The number measured on the 1024-cluster build: median nearest-neighbour centroid
	 * distance 0.057 box units, so the falloff scale is 0.11. A gaussian at that scale
	 * weighs 1.0 at the source knot's centre, ~0.78 at the rim of the nearest
	 * neighbouring knot, ~0.37 two knot-spacings out, and under 2 % at twice the
	 * scale. (On the earlier 149-cluster build the same rule produced 0.27 — tighter
	 * knots get a tighter ripple automatically.) The ripple reads as an event *at*
	 * the sounding knot and its immediate neighbours, never as a cloud-wide wash.
	 */
	untrack(() => {
		if (clusterCount < 2) return;
		const nn = nearestNeighbourDistances(layout.centroids, layout.counts, clusterCount);
		if (!nn.length) return;
		nn.sort((a, b) => a - b);
		// Four knot-spacings of reach, doubled from two at the owner's call (2026-08-01):
		// the front read as a knot-local flash, and the point of a wave is that it is
		// seen to *travel* — four spacings crosses a real share of the cloud before the
		// Gaussian takes it under.
		//
		// The median is taken over the knots that HAVE members, which is what `nn` holds —
		// so it is `nn.length >> 1`, not `clusterCount >> 1`. Indexing by the cluster count
		// on a build where some knots are empty reads past the middle of the array and, at
		// a high enough empty share, past its end entirely.
		medianKnotSpacing = nn[nn.length >> 1] ?? 0.135;
		material.uniforms.uWaveLocal.value = 4 * medianKnotSpacing;
	});

	// Registered after construction rather than in the geometry block above, because
	// the radial directions need the layout, which needs the assets, which the block
	// above only reads raw. Same one-time cost either way.
	untrack(() => {
		const n = assets.points.n;
		const radDir = new Float32Array(n * 3);
		// The knot blossom's per-point magnitude (the z channel of aMisc): how far the
		// point may drift outward along its own aRadDir once the camera closes in
		// (uBlossom in shaders.ts). sqrt(hash) gives a uniform-over-disc target radius
		// inside the knot, so interior points move most and rim points barely — the
		// knot's outline is preserved, which is what separates display jitter from
		// moved data. The target runs to 1.35 × the knot radius (up from 1.1: a tight
		// knot at 3 px a mark still fused at its rim) and the cap is 0.6 × the median
		// knot spacing, so an opened knot still cannot reach into its neighbour. The
		// hash reuses the seed's multiply-and-mod style with a different modulus
		// (104729, prime) so the spread is not correlated with the seed that already
		// drives phase, size and arrival. Unassigned points and points in a
		// zero-radius knot keep 0; a point resting exactly on its centroid has no
		// aRadDir and its magnitude is moot.
		const spreadCap = 0.6 * medianKnotSpacing;
		for (let i = 0; i < n; i++) {
			const c = assets.points.clusterId[i];
			if (c < 0 || c >= clusterCount) continue;
			const dx = layout.positions[i * 3] - layout.centroids[c * 3];
			const dy = layout.positions[i * 3 + 1] - layout.centroids[c * 3 + 1];
			const dz = layout.positions[i * 3 + 2] - layout.centroids[c * 3 + 2];
			const d = Math.hypot(dx, dy, dz);
			const h = ((i * 2654435761) % 104729) / 104729;
			const targetRadius = Math.sqrt(h) * graph.radii[c] * 1.35;
			misc[i * 4 + 2] = Math.min(spreadCap, Math.max(0, targetRadius - d));
			if (d < 1e-6) continue;
			radDir[i * 3] = dx / d;
			radDir[i * 3 + 1] = dy / d;
			radDir[i * 3 + 2] = dz / d;
		}
		geometry.setAttribute('aFront', frontAttribute);
		geometry.setAttribute('aRadDir', new THREE.BufferAttribute(radDir, 3));

		// The per-point bloom budget (the y channel of aMisc), from the knot's own
		// radius: 45 % of it, floored so a tiny knot still separates visibly, capped
		// at 0.045 (≈ 0.8 × the median knot spacing on the 1024-cluster build) so the
		// bloom stays inside the knot's neighbourhood. See aMisc in shaders.ts for the
		// measured numbers.
		for (let i = 0; i < n; i++) {
			const c = assets.points.clusterId[i];
			if (c < 0 || c >= clusterCount) continue;
			misc[i * 4 + 1] = Math.min(0.045, Math.max(0.015, 0.45 * graph.radii[c]));
		}
	});

	/**
	 * Per-cluster front state. `frontAge` is seconds since the cluster's activation
	 * crossed the onset threshold (Infinity = idle); `prevAct` is last frame's
	 * activation, so the rising edge fires exactly one front per onset rather than a
	 * front per frame for as long as a note holds.
	 */
	const frontAge = new Float32Array(clusterCount).fill(Number.POSITIVE_INFINITY);
	const prevAct = new Float32Array(clusterCount);

	/**
	 * **Level of detail: one priority order, one moving frontier.**
	 *
	 * Measured, not guessed: the per-frame CPU work of this component is 1.9 ms of a
	 * 16.7 ms budget at 214 154 points, and almost all of that is the active-index scan
	 * below. The frame is spent on the GPU instead, rasterising a quarter of a million
	 * blended sprites — so the only thing that buys frames is drawing fewer of them,
	 * and no amount of tightening the JS would have helped.
	 *
	 * The order is by knot rather than by stride, because a knot is the thing that has
	 * a name, a function and a citation: first come one representative per cluster —
	 * the member nearest its own centroid, an observed point and never an average —
	 * and every unclustered point, the ones the discovery map exists to show. The
	 * remainder follows in stride tiers. A random stride would thin the same picture;
	 * this one thins toward the structure the galaxy is *about*, and it is exactly what
	 * the reader can act on at a distance, since a knot is all a label can point at
	 * from there.
	 *
	 * What replaced the three discrete levels is a continuous frontier: the resting
	 * pass draws the first `shownFraction(viewRadii)` of the order, a cubed smoothstep
	 * from the representatives' share at LOD_FAR to everything at LOD_NEAR (the cube
	 * keeps the mid-window cheap — see the function's own comment), and the shader
	 * dissolves the band just behind the frontier in (aRank/uLod, see shaders.ts). The
	 * levels used to jump from a quarter of the corpus to all of it in one frame at
	 * LOD_NEAR — up to ~260 k sprites appearing at once, with a full 348 k index
	 * re-upload on top, exactly while the camera was moving. A frontier only ever adds
	 * or removes a frame's worth of marks, so it needs no hysteresis, and the index
	 * buffers upload once at load and once per focus change, never per swap.
	 *
	 * The resting pass is also split into 64 spatial cells (a 4×4×4 grid over the
	 * cloud's bounds), each with its own bounding sphere and frustum culling on. Both
	 * passes used to run with culling off, so a close zoom paid vertex cost for the
	 * whole corpus while up to nine tenths of it sat behind the camera — on the
	 * owner's Intel iGPU that was the close-zoom half of the frame-rate collapse. Each
	 * cell holds its points in the same global priority order, so applying the fraction
	 * within the cell keeps the semantics: the frontier is per cell, the order is the
	 * corpus's. A focused species leads every cell's order, so choosing a bird still
	 * draws its marks whole, whatever the distance.
	 */
	/**
	 * Per-frame retention of the resting wash's driver, at 60 Hz, rising and falling.
	 *
	 * Both are delta-scaled where they are used, so the half-life is the same on a 60 Hz
	 * and a 144 Hz display. It rises over about 80 ms — fast enough that the wash is out
	 * of the way by the time a syllable's second half sounds — and falls over about 250 ms,
	 * because ink coming back slower than it left reads as light rather than as a flicker.
	 */
	const ANSWER_RISE = 0.6;
	const ANSWER_FALL = 0.86;

	const LOD_FAR = 3.2;
	const LOD_NEAR = 1.6;
	/**
	 * The density governor: a cap on the frontier, driven by the measured frame time
	 * rather than by the camera. Fill rate is the budget on an integrated GPU — the
	 * owner runs Firefox on Mesa Intel — and the frontier's own curve cannot know
	 * what a frame costs, so the smoothed frameMs in `stats` steers: above 20 ms the
	 * cap falls fast (delta * 0.8 — a bad spell answers inside a second), below 13 ms
	 * it rises slowly (delta * 0.15 — the asymmetric rates are what keep it from
	 * oscillating across the threshold), clamped to [0.10, 1] so the representatives
	 * never thin out entirely. Reductions read as the frontier's own dissolve, not a
	 * pop: the aRank fade band swallows them. Off (`adaptive` false), the cap is
	 * pinned at 1 and the camera decides alone, as before.
	 *
	 * Seeded once from the GPU name, the first frame Stats has reported it: Mesa
	 * Intel (and not Arc — the discrete Intels are not the fill-bound case) starts at
	 * 0.55 rather than paying the fall from 1 down to it through the first seconds
	 * of exploring.
	 */
	let densityCap = 1;
	let capSeeded = false;
	/**
	 * Cells per axis of the resting pass's spatial split: 4³ = 64. Few enough that the
	 * extra draw calls cost nothing next to the rasterisation they save, fine enough
	 * that a close zoom leaves most of the corpus outside the frustum.
	 */
	const LOD_GRID = 4;

	/**
	 * The point's position in its cell's priority order, normalised 0..1 — the w
	 * channel of aMisc, which the shader's frontier fade quotes as `aRank`. Rewritten
	 * only when the order changes (load, and a focus change via `reorderCells`), so a
	 * manual needsUpdate, not one of the per-frame dynamics — the channel is what
	 * makes the packed attribute dynamic at all.
	 */

	interface RestCell {
		/** Grid index 0..63, stable across reorders — the {#each} key. */
		key: number;
		/** The cell's points in the global priority order; the index is a reorder of this. */
		base: Uint32Array;
		index: THREE.BufferAttribute;
		geometry: THREE.BufferGeometry;
		/** Leading points belonging to the focused species; 0 when nothing is focused. */
		focused: number;
		/** base.length - focused: the share the frontier fraction applies to. */
		rest: number;
	}

	const lod = untrack(() => {
		const n = assets.points.n;
		const cluster = geometry.attributes.aCluster.array as Float32Array;
		const pos = layout.positions;
		const centroids = view.centroids;
		// The representative of each knot: the member closest to the knot's centroid.
		const bestFor = new Map<number, { i: number; d: number }>();
		for (let i = 0; i < n; i++) {
			const c = cluster[i];
			if (c < 0) continue;
			const dx = pos[i * 3] - centroids[c * 3];
			const dy = pos[i * 3 + 1] - centroids[c * 3 + 1];
			const dz = pos[i * 3 + 2] - centroids[c * 3 + 2];
			const d = dx * dx + dy * dy + dz * dz;
			const held = bestFor.get(c);
			if (!held || d < held.d) bestFor.set(c, { i, d });
		}
		// Head of the order: every representative, plus every point in no cluster — a
		// point with no knot has nothing to stand in for it, and it is the one point
		// the discovery map exists to show, so it draws ahead of every frontier.
		const head = new Uint8Array(n);
		for (let i = 0; i < n; i++) if (cluster[i] < 0) head[i] = 1;
		for (const { i } of bestFor.values()) head[i] = 1;
		let repCount = 0;
		for (let i = 0; i < n; i++) repCount += head[i];

		// One fixed ordering: the head first, then every remaining point in stride
		// tiers (i % 4). Nested by construction — raising the frontier only ever *adds*
		// marks, which is what stops a crossing from reading as a fault.
		const priority = new Uint32Array(n);
		let k = 0;
		for (let i = 0; i < n; i++) if (head[i]) priority[k++] = i;
		for (let tier = 0; tier < 4; tier++) {
			for (let i = 0; i < n; i++) if (!head[i] && i % 4 === tier) priority[k++] = i;
		}

		// The 4×4×4 grid over the cloud's own bounds. A degenerate axis lands every
		// point in cell 0 of that axis, which is correct — they genuinely coincide.
		let minX = Infinity,
			minY = Infinity,
			minZ = Infinity;
		let maxX = -Infinity,
			maxY = -Infinity,
			maxZ = -Infinity;
		for (let i = 0; i < n; i++) {
			const x = pos[i * 3];
			const y = pos[i * 3 + 1];
			const z = pos[i * 3 + 2];
			if (x < minX) minX = x;
			if (x > maxX) maxX = x;
			if (y < minY) minY = y;
			if (y > maxY) maxY = y;
			if (z < minZ) minZ = z;
			if (z > maxZ) maxZ = z;
		}
		const sx = LOD_GRID / Math.max(1e-6, maxX - minX);
		const sy = LOD_GRID / Math.max(1e-6, maxY - minY);
		const sz = LOD_GRID / Math.max(1e-6, maxZ - minZ);
		const cellOf = (i: number) => {
			const ix = Math.min(LOD_GRID - 1, ((pos[i * 3] - minX) * sx) | 0);
			const iy = Math.min(LOD_GRID - 1, ((pos[i * 3 + 1] - minY) * sy) | 0);
			const iz = Math.min(LOD_GRID - 1, ((pos[i * 3 + 2] - minZ) * sz) | 0);
			return ix + LOD_GRID * (iy + LOD_GRID * iz);
		};

		// Each cell holds its points in the SAME global priority order, so a per-cell
		// drawRange of the one fraction keeps the frontier's meaning: anywhere you
		// look, the first marks are the knots' representatives.
		const cellCount = LOD_GRID * LOD_GRID * LOD_GRID;
		const counts = new Uint32Array(cellCount);
		for (let m = 0; m < n; m++) counts[cellOf(priority[m])]++;
		const bases: (Uint32Array | null)[] = new Array(cellCount).fill(null);
		for (let c = 0; c < cellCount; c++) {
			if (counts[c]) bases[c] = new Uint32Array(counts[c]);
		}
		const cursor = new Uint32Array(cellCount);
		for (let m = 0; m < n; m++) {
			const p = priority[m];
			const c = cellOf(p);
			bases[c]![cursor[c]++] = p;
		}

		// Reach past the point's resting position. A tight bounding sphere would let the
		// frustum test cull a cell whose marks are in fact visible, and the marks move:
		// the wave displaces resting points up to 0.06 box units (the launch cap), the
		// idle drift 0.004, the sub-discard response terms ~0.005, and a 24 px sprite
		// spans ~0.01 at a close zoom — ~0.08 against the [-1,1] box the projection
		// normalises to, measured on the shipped build (radius 1.60). 0.12 covers it
		// with margin and costs a fifth of a cell's width (cells are 0.5 across).
		const pad = 0.12;
		const cells: RestCell[] = [];
		for (let c = 0; c < cellCount; c++) {
			const base = bases[c];
			if (!base) continue;
			// Centre as the mean, radius as the farthest point: exact, and computed
			// once — the arrangement no longer morphs, so the cells never move.
			let cx = 0,
				cy = 0,
				cz = 0;
			for (let m = 0; m < base.length; m++) {
				cx += pos[base[m] * 3];
				cy += pos[base[m] * 3 + 1];
				cz += pos[base[m] * 3 + 2];
			}
			cx /= base.length;
			cy /= base.length;
			cz /= base.length;
			let r2 = 0;
			for (let m = 0; m < base.length; m++) {
				const dx = pos[base[m] * 3] - cx;
				const dy = pos[base[m] * 3 + 1] - cy;
				const dz = pos[base[m] * 3 + 2] - cz;
				const d2 = dx * dx + dy * dy + dz * dz;
				if (d2 > r2) r2 = d2;
			}
			const index = new THREE.BufferAttribute(new Uint32Array(base), 1);
			const g = new THREE.BufferGeometry();
			// The same BufferAttribute objects the base geometry holds, so all 64 cells
			// name the same GPU buffers and a per-frame upload still happens exactly
			// once. Only the index — the cell's slice of the order — is its own.
			for (const [name, attribute] of Object.entries(geometry.attributes)) {
				g.setAttribute(name, attribute as THREE.BufferAttribute);
			}
			g.setIndex(index);
			g.boundingSphere = new THREE.Sphere(
				new THREE.Vector3(cx, cy, cz),
				Math.sqrt(r2) + pad
			);
			g.setDrawRange(0, 0);
			for (let m = 0; m < base.length; m++) {
				misc[base[m] * 4 + 3] = base.length > 1 ? m / (base.length - 1) : 0;
			}
			cells.push({ key: c, base, index, geometry: g, focused: 0, rest: base.length });
		}
		return { cells, repFraction: repCount / n };
	});

	/**
	 * The share of the priority order in front of the frontier, from the
	 * representatives' share at LOD_FAR to the whole corpus at LOD_NEAR.
	 *
	 * The smoothstep is **cubed**, and the reason is measured, not aesthetic: a plain
	 * smoothstep puts ~55 % of the corpus in front of the frontier at the window's
	 * midpoint, which is exactly where the whole cloud is still inside the frustum —
	 * no cell is culled yet, and ~190 k sprites rasterise at their 3 px floor, blended,
	 * on top of each other. That midpoint was the frame-rate floor the owner hit.
	 * Density there is also worthless: at that distance the extra marks overlap into
	 * mush. The cube keeps the curve C1-smooth at both ends but holds the midpoint to
	 * ~21 % (the old mid level's quarter, which was comfortable at that distance) and
	 * pays the density out late, when a close camera has already culled most of the
	 * 64 cells and each surviving mark is big enough to read.
	 */
	function shownFraction(radii: number): number {
		const t = Math.min(1, Math.max(0, (LOD_FAR - radii) / (LOD_FAR - LOD_NEAR)));
		const s = t * t * (3 - 2 * t);
		return lod.repFraction + (1 - lod.repFraction) * s * s * s;
	}

	/**
	 * Put the focused bird's marks first in every cell, and re-rank.
	 *
	 * A chosen bird draws whole, whatever the distance: selecting it is the request to
	 * see its marks, not a summary of them. Its points take rank 0, so they never sit
	 * on the fade frontier either; the remainder keeps the global priority order and
	 * is ranked over itself, so the fraction applies to it exactly. This is the only
	 * reorder there is — it runs on a focus change, never per frame, and the uploads
	 * it triggers (64 small indices plus the packed aMisc buffer, whose w channel is
	 * the rank) happen only then.
	 */
	function reorderCells(focus: number) {
		const species = geometry.attributes.aSpecies.array as Float32Array;
		for (const cell of lod.cells) {
			const idx = cell.index.array as Uint32Array;
			let f = 0;
			if (focus >= 0) {
				for (let m = 0; m < cell.base.length; m++) {
					const p = cell.base[m];
					if (Math.abs(species[p] - focus) < 0.5) {
						idx[f++] = p;
						misc[p * 4 + 3] = 0;
					}
				}
			}
			let r = 0;
			const restCount = cell.base.length - f;
			for (let m = 0; m < cell.base.length; m++) {
				const p = cell.base[m];
				if (focus >= 0 && Math.abs(species[p] - focus) < 0.5) continue;
				idx[f + r] = p;
				misc[p * 4 + 3] = restCount > 1 ? r / (restCount - 1) : 0;
				r++;
			}
			cell.focused = f;
			cell.rest = restCount;
			cell.index.needsUpdate = true;
		}
		miscAttribute.needsUpdate = true;
	}

	let lodFocus = -2;

	/**
	 * Walk the frontier to where the camera is. A frame's work is one uniform write and
	 * 64 drawRange updates — integers into index buffers that do not move — so there
	 * is no per-frame buffer traffic here at all. The only upload is `reorderCells`,
	 * on a focus change.
	 */
	function updateLod() {
		const focus = material.uniforms.uFocus.value as number;
		if (focus !== lodFocus) {
			lodFocus = focus;
			reorderCells(focus);
		}
		const fraction = Math.min(shownFraction(viewRadii), adaptive ? densityCap : 1);
		material.uniforms.uLod.value = fraction;
		// Two more distance-driven uniforms ride the same read, one smoothstep each —
		// the same t*t*(3-2t) shape shownFraction builds on, and no per-frame cost to
		// speak of.
		//
		// The blossom opens over 1.9 → 1.0 cloud radii: closed at whole-galaxy zoom,
		// where a knot is a few pixels and spread would be invisible fill; fully open
		// just past LOD_NEAR (1.6), so the knot's marks spread to fill its measured
		// extent while the LOD frontier is still paying detail out — spacing and
		// detail arrive together rather than one after the other.
		const bloomT = Math.min(1, Math.max(0, (1.9 - viewRadii) / (1.9 - 1.0)));
		material.uniforms.uBlossom.value = bloomT * bloomT * (3 - 2 * bloomT);
		// The size floor relaxes over 3.5 → 1.8 radii: at galaxy distance a sub-3 px
		// mark is all feather, and that feather is the intended haze (with less fill
		// on an iGPU as a bonus); the crisp 3 px disc returns as the camera closes.
		const nearT = Math.min(1, Math.max(0, (3.5 - viewRadii) / (3.5 - 1.8)));
		material.uniforms.uNearFloor.value = nearT * nearT * (3 - 2 * nearT);
		let drawn = 0;
		for (const cell of lod.cells) {
			const count = cell.focused + Math.round(fraction * cell.rest);
			cell.geometry.setDrawRange(0, count);
			drawn += count;
		}
		if (stats) {
			stats.lod = fraction;
			stats.pointsDrawn = drawn;
		}
	}

	/**
	 * Each point's cluster, read straight off the attribute the shader reads, so the
	 * CPU-side active test and the GPU-side one can never disagree about membership.
	 */
	const clusterOfPoint = untrack(
		() => geometry.attributes.aCluster.array as Float32Array
	);

	/** Set by `updateFronts`: is any wavefront still travelling this frame. */
	let waveActive = false;
	/**
	 * Whether the previous frame was silent, for the upload gate below: sustained quiet
	 * skips the four GPU uploads and the O(n) active-index scan; the transition into
	 * quiet uploads zeros once, so the GPU state matches what the full path would have
	 * left behind.
	 */
	let wasQuiet = false;
	/**
	 * Consecutive silent frames, and the settle window the freeze waits for. The
	 * trackers' release is a ~0.4 s half-life ring-down (features.ts, RELEASE), so a
	 * freeze on the first silent frame would cut a mark still glowing at ~0.5. The
	 * gate keeps uploading the honestly decaying values for 90 frames (~1.5 s at
	 * 60 fps) after the four-way quiet test first holds; by then the ring-down sits at
	 * ~0.02, and the freeze's zero-fill swaps out residue no eye can see. A chorus gap
	 * shorter than the window never freezes at all — which is also what keeps widely
	 * spaced notes from blinking.
	 */
	const QUIET_SETTLE_FRAMES = 90;
	let quietFrames = 0;

	/** Scratch for the learning channel, so the texture write allocates nothing. */
	const learnPerCluster = untrack(() => new Float32Array(Math.max(1, clusterCount)));

	/**
	 * The responding pass draws only the points that can respond.
	 *
	 * **Why this exists.** Both passes used to draw the whole corpus, and the fragment
	 * shader threw away whichever half it did not want (`ACTIVE_PASS` discards
	 * everything resting, the resting pass discards everything responding). That is two
	 * full vertex passes and two full sprite rasterisations per frame for a picture in
	 * which, on a quiet frame, nothing at all is responding — 428 000 vertex
	 * invocations at 214 154 points, and it scales with the corpus, which is what made
	 * the frame rate fall when the galaxy went from 52 670 points to 214 154.
	 *
	 * The index is rebuilt per frame from the same quantities the vertex shader reads,
	 * with the thresholds set *below* the shader's cuts (0.22 against 0.25, 0.04
	 * against 0.05). A point that clears the shader's bar but not this one would vanish
	 * from both passes, so the set is deliberately a superset: it may draw a point the
	 * fragment shader then discards, and it may never omit one the shader would keep.
	 * The resting pass still draws everything, because on a quiet frame everything is
	 * resting and that is the picture.
	 */
	const activeIndex = untrack(() => new Uint32Array(Math.max(1, assets.points.n)));
	const activeIndexAttribute = untrack(() =>
		new THREE.BufferAttribute(activeIndex, 1).setUsage(THREE.DynamicDrawUsage)
	);
	const activeGeometry = untrack(() => {
		const g = new THREE.BufferGeometry();
		// The same BufferAttribute objects, so both geometries name the same GPU buffers
		// and every per-frame upload still happens exactly once.
		for (const [name, attribute] of Object.entries(geometry.attributes)) {
			g.setAttribute(name, attribute as THREE.BufferAttribute);
		}
		g.setIndex(activeIndexAttribute);
		g.boundingSphere = geometry.boundingSphere;
		g.setDrawRange(0, 0);
		return g;
	});

	function updateActiveIndex() {
		const pointAct = signal.pointActivation;
		const acts = signal.activations;
		// The scan is the most expensive thing this component does per frame — measured
		// at 1.84 ms of a 16.7 ms budget at 214 154 points — and on a quiet frame its
		// answer is always "nothing". `signal.level` is the live input, `best` the
		// current match, `waveActive` whether a front is still travelling; with none of
		// them and no learning breath, no point can clear the shader's bar, so the whole
		// pass is skipped and an idle galaxy costs nothing to explore.
		if (!signal.level && signal.best < 0 && !waveActive && !learning.length) {
			if (activeGeometry.drawRange.count !== 0) activeGeometry.setDrawRange(0, 0);
			if (stats) stats.pointsResponding = 0;
			return;
		}
		let n = 0;
		for (let i = 0; i < clusterOfPoint.length; i++) {
			const c = clusterOfPoint[i];
			let v = pointAct[i] ?? 0;
			if (c >= 0) {
				const clusterAct = (acts[c] ?? 0) * 0.25;
				if (clusterAct > v) v = clusterAct;
				const learn = learnPerCluster[c] * 0.55;
				if (learn > v) v = learn;
			}
			if (v >= 0.22 || front[i] >= 0.04) activeIndex[n++] = i;
		}
		activeIndexAttribute.needsUpdate = true;
		activeGeometry.setDrawRange(0, n);
		if (stats) stats.pointsResponding = n;
	}

	/**
	 * The per-frame front pass. Everything it draws with is a measurement:
	 *
	 * - onset: the cluster's activation crossing FRONT_ONSET upward (live match or
	 *   scheduled pulse — both arrive through `signal.activations`);
	 * - origin: the response-weighted centroid of the cluster's members, i.e. where
	 *   inside the knot the sound actually landed; the geometric centroid when the
	 *   per-point response is flat (a scheduled note, or a cluster lit by the floor);
	 * - timing: each member's true distance from that origin, normalised by the
	 *   cluster's true radius — arrival order is distance order;
	 * - amplitude: the member's own measured response, with the cluster activation as
	 *   floor, so the front ignites the most-similar members hardest.
	 *
	 * Cost is bounded by the live clusters' members, not the corpus: a frame with no
	 * front travelling touches only the fill(0), and a chorus frame a few hundred
	 * points. (A fully silent frame no longer calls this at all — see the upload gate
	 * in useTask.)
	 */
	function updateFronts(delta: number) {
		const acts = signal.activations;
		const pointAct = signal.pointActivation;
		for (let c = 0; c < clusterCount; c++) {
			const a = acts[c] ?? 0;
			if (a > FRONT_ONSET && prevAct[c] <= FRONT_ONSET) frontAge[c] = 0;
			else if (frontAge[c] < FRONT_LIFE) frontAge[c] += delta;
			prevAct[c] = a;
		}
		front.fill(0);
		// Whether any ring is still travelling this frame. Read by `updateActiveIndex`,
		// which can skip its whole pass when nothing at all is responding.
		waveActive = false;
		for (let c = 0; c < clusterCount; c++) {
			const age = frontAge[c];
			if (!(age < FRONT_LIFE)) continue;
			const mem = graph.members[c];
			if (!mem.length) continue;
			waveActive = true;
			let w = 0;
			let ox = 0;
			let oy = 0;
			let oz = 0;
			for (let m = 0; m < mem.length; m++) {
				const i = mem[m];
				const wi = pointAct[i] ?? 0;
				if (wi <= 0) continue;
				w += wi;
				ox += wi * current[i * 3];
				oy += wi * current[i * 3 + 1];
				oz += wi * current[i * 3 + 2];
			}
			if (w < 1e-4) {
				ox = view.centroids[c * 3];
				oy = view.centroids[c * 3 + 1];
				oz = view.centroids[c * 3 + 2];
			} else {
				ox /= w;
				oy /= w;
				oz /= w;
			}
			const radius = graph.radii[c];
			const floor = (acts[c] ?? 0) * 0.3;
			for (let m = 0; m < mem.length; m++) {
				const i = mem[m];
				const d =
					Math.hypot(
						current[i * 3] - ox,
						current[i * 3 + 1] - oy,
						current[i * 3 + 2] - oz
					) / radius;
				const amp = Math.min(1, Math.max(pointAct[i] ?? 0, floor) * 1.2);
				front[i] = frontRing(d, age) * amp;
			}
		}
		frontAttribute.needsUpdate = true;
	}

	const { camera } = useThrelte();
	/** Scratch, so the per-frame fog fit allocates nothing. */
	const worldCentre = new THREE.Vector3();

	/**
	 * Fit the aerial-perspective band to where the cloud actually is.
	 *
	 * Fog has to be quoted against the camera's current distance, not against a constant:
	 * the framing moves from 0.3 units (one node) to tens of units (the whole galaxy), and
	 * a fixed depth means either no fog at all or a corpus that is entirely fog. Near edge
	 * a little inside the front of the cloud, far edge a little past the back, so the
	 * gradient always spans the thing being looked at.
	 */
	function fitFog(points: THREE.Object3D | undefined) {
		const cam = camera.current;
		const sphere = geometry.boundingSphere;
		if (!cam || !points || !sphere) return;
		const scale = points.matrixWorld.getMaxScaleOnAxis();
		const radius = Math.max(1e-3, sphere.radius * scale);
		worldCentre.copy(sphere.center).applyMatrix4(points.matrixWorld);
		const distance = cam.position.distanceTo(worldCentre);
		const range = material.uniforms.uFogRange.value as THREE.Vector2;
		range.set(Math.max(0.01, distance - radius * 0.55), distance + radius * 1.15);
		// In cloud radii, so the level of detail below reads the same on any corpus,
		// whatever the projection scaled the galaxy to.
		viewRadii = distance / radius;
	}
	let viewRadii = 3;

	let points = $state<THREE.Group | undefined>();

	/**
	 * Pitch the wave is quoted against — near the middle of the corpus, in octaves. The
	 * shape is followed toward the measurement rather than set from it: f0 is a per-frame
	 * estimate that jumps an octave whenever the tracker changes its mind, and a
	 * wavelength that jumps with it looks like a fault rather than like a sound.
	 */
	const WAVE_REFERENCE_HZ = 900;
	/** Seconds a front keeps travelling before it is retired. */
	const WAVE_LIFETIME = 3.2;
	let waveK = 6;
	let pitch = 0.5;

	/**
	 * One expanding front: the knot it came from, how old it is, how hard it hit.
	 *
	 * The *knot*, not the coordinates. A front captured its origin at launch, which was
	 * correct until the arrangements arrived — now a rearrangement carries every cluster
	 * somewhere else over a second and a half, and a front already travelling kept
	 * expanding from where its knot used to be. Reading the position back every frame
	 * makes the front follow its own cluster through the move.
	 */
	const sources = Array.from({ length: WAVE_SOURCES }, () => ({
		cluster: -1,
		origin: new THREE.Vector3(),
		age: WAVE_LIFETIME,
		amp: 0
	}));
	let nextSource = 0;
	/** The cluster the last front was launched from, so one note launches one wave. */
	let lastLaunch = -1;

	/**
	 * Launch a front from the knot that is sounding.
	 *
	 * `signal.best` is the cluster the live sound matched, and the layout view knows where
	 * that cluster is *right now* — which matters, because the same knot is somewhere else
	 * after a rearrangement, and a wave that started from where it used to be would be a
	 * wave from nowhere.
	 */
	function launch(cluster: number, strength: number) {
		// A knot with no members has no real position (its centroid is the box centre by
		// arithmetic accident) — a front from it is a ripple spawned from nowhere, which
		// is exactly what this view may not show.
		if (cluster < 0 || cluster * 3 + 2 >= view.centroids.length || !view.counts[cluster]) {
			return;
		}
		const s = sources[nextSource];
		nextSource = (nextSource + 1) % WAVE_SOURCES;
		s.cluster = cluster;
		s.age = 0;
		// Half again on the match strength, capped: the front was tuned for a local
		// flash, and at whole-cloud reach (uWaveLocal ×2, 2026-08-01) the same amp read
		// thin. 1.5× keeps a full match inside 1 while lifting every partial one.
		s.amp = Math.min(1, strength * 1.5);
	}

	function fitWave(delta: number) {
		const f0 = signal.f0;
		const octaves = f0 > 60 ? Math.log2(f0 / WAVE_REFERENCE_HZ) : 0;
		// Few, broad fronts rather than many tight ones. Wound tighter, the displacement
		// stacks the points into concentric shells that a still frame reads as *density* —
		// a structure the data does not have. Kept broad, the same motion reads as the
		// cloud flexing, and only the movement carries the pitch.
		const k = Math.min(9, Math.max(1.5, 4 + octaves * 1.6));
		waveK += (k - waveK) * Math.min(1, delta * 6);
		// 0..1 over roughly four octaves of birdsong, for the gradient inside each mark
		const p = f0 > 60 ? Math.min(1, Math.max(0, (Math.log2(f0) - 8.2) / 4)) : pitch;
		pitch += (p - pitch) * Math.min(1, delta * 4);

		// A new note from a different knot starts its own front; the same knot holding on
		// does not, or a sustained call would emit a front every frame and the interference
		// would be mush rather than two crossing shells. The gate is the claim, not the
		// loudness — see `waveClaim`: a front that launched whenever the input was loud
		// moved across knots whose points stayed dark ("the wave moves but nothing
		// activates"), because loud is all a fan or a weak self-match ever is.
		const best = signal.best;
		if (best >= 0 && best !== lastLaunch && waveClaim(signal)) {
			// Deliberately small — but bigger than it used to be: 0.03 was lost inside the
			// denser 1024-knot corpus, so the cap moved to 0.04, and then to 0.06 when the
			// front still read as a tremor rather than a wave crossing the cloud. Still
			// coherent motion of a whole region rather than a per-point jump (the
			// knot-local budget lives in the wavefront, not here). Quoted in box units,
			// so the displacement scales with the listening-distance `spread` for free:
			// a front displaces the same *share* of the cloud however large the group is
			// drawn. A front is meant to be read as movement, and displacement large
			// enough to see in a still frame is large enough to smear a knot into a
			// streak — which stops being animation and starts being a wrong position.
			launch(best, Math.min(0.06, 0.02 + signal.level * 0.055));
		}
		if (best !== lastLaunch) lastLaunch = best;

		const u = material.uniforms;
		const ages = u.uWaveAge.value as Float32Array;
		const amps = u.uWaveAmp.value as Float32Array;
		const origins = u.uWaveOrigin.value as THREE.Vector3[];
		for (let i = 0; i < WAVE_SOURCES; i++) {
			const s = sources[i];
			// Follow the knot rather than the place it was in when the note sounded.
			const c = s.cluster;
			if (c >= 0 && c * 3 + 2 < view.centroids.length) {
				s.origin.set(view.centroids[c * 3], view.centroids[c * 3 + 1], view.centroids[c * 3 + 2]);
			}
			s.age += delta;
			// Fade over the life rather than cutting off — linear, not squared, since the
			// life went up: a squared fade at 3.2 s spent its first second near full
			// strength and its last two as a ghost, which read as the wave "sticking".
			const life = Math.max(0, 1 - s.age / WAVE_LIFETIME);
			ages[i] = s.age;
			amps[i] = s.amp * life;
			origins[i].copy(s.origin);
		}
		u.uWaveK.value = waveK;
		// Faster fronts for higher calls, so the pitch is in the travel as well as the
		// wavelength. Quoted in box units a second: the box is the cloud, whatever scale
		// the distance slider has it drawn at, so a front crosses the same share of the
		// picture at every setting.
		u.uWaveSpeed.value = 0.55 + pitch * 0.9;
		u.uPitch.value = pitch;
	}

	/** Seconds an arrival takes to finish, from the first frame the new points exist. */
	const ARRIVAL_SECONDS = 2.4;

	useTask((delta) => {
		const u = material.uniforms;
		u.uTime.value += delta * speed;
		if (u.uArrival.value < 1) {
			u.uArrival.value = Math.min(1, u.uArrival.value + delta / ARRIVAL_SECONDS);
		}
		// Capturing the ratio at construction leaves the sizes wrong after a drag to a
		// different-DPR monitor; it is one compare per frame to keep it honest.
		const pr = Math.min(2, window.devicePixelRatio || 1);
		if (u.uPixelRatio.value !== pr) u.uPixelRatio.value = pr;
		fitFog(points);
		fitWave(delta * speed);
		easeAccent(delta);

		u.uLevel.value = signal.level;
		// The resting wash gives way to what the corpus is *answering*, not to how loud the
		// room is. `strength` is the match, so a sound the galaxy cannot place leaves the
		// picture alone instead of dimming all of it and lighting none of it. Eased on a
		// fixed half-life, delta-scaled, so the step back is not the level's own flicker —
		// and it falls faster than it rises, because a picture that keeps dimming after the
		// sound has stopped reads as a lag.
		const answer = signal.level * signal.strength;
		const rate = answer > u.uAnswer.value ? ANSWER_RISE : ANSWER_FALL;
		u.uAnswer.value += (answer - u.uAnswer.value) * (1 - Math.pow(rate, delta * 60));
		u.uHighlight.value = signal.best;

		// **Silent frames upload nothing — after the ring-down has finished.** The four
		// GPU writes below — three corpus-length attributes (activation, orphan, front
		// ≈ 3 × 1.4 MB at the production corpus) and the cluster-state texture — used to
		// fire every frame, sounding or not: ~250 MB/s of shared-memory traffic on the
		// owner's Intel iGPU for a picture that was not changing. Quiet is the same
		// four-way idle test `updateActiveIndex` already early-outs on; a sounding
		// orphan note keeps `level` up because the extractor hears the synth's own
		// output, so the pulse channel is safe under it. Sustained quiet — the test
		// held for QUIET_SETTLE_FRAMES, so the trackers' ~0.4 s ring-down has played
		// out on screen — skips the lot, including the O(n) active-index scan; the
		// freeze frame uploads zeros once.
		const quiet = !signal.level && signal.best < 0 && !waveActive && !learning.length;
		quietFrames = quiet ? quietFrames + 1 : 0;
		if (!quiet || quietFrames <= QUIET_SETTLE_FRAMES) {
			wasQuiet = false;
			// The three channels, interleaved into the texture's RGB. One pass over the
			// clusters (a thousand, not a corpus), where the uniform-array version did three
			// bulk copies and three uniform uploads per material per frame.
			//
			// The learning pipeline breathes through its own channel, not the audio one.
			// Slower than a note and never marked as sung: this is work happening at a place
			// in the corpus, not a sound, and it must not be mistaken for one — the shader
			// turns it into a slow swell and keeps the fast pulse for actual responses.
			const acts = signal.activations;
			const sungs = signal.sung;
			const breath = learning.length ? 0.45 + 0.35 * Math.sin(u.uTime.value * 3.2) : 0;
			learnPerCluster.fill(0);
			for (const c of learning) {
				if (c >= 0 && c < clusterCount) {
					learnPerCluster[c] = Math.max(learnPerCluster[c], breath);
				}
			}
			for (let c = 0; c < clusterCount; c++) {
				const o = c * 4;
				clusterState[o] = acts[c] ?? 0;
				clusterState[o + 1] = sungs[c] ?? 0;
				clusterState[o + 2] = learnPerCluster[c];
			}
			clusterTexture.needsUpdate = true;

			activation.set(signal.pointActivation.subarray(0, activation.length));
			activationAttribute.needsUpdate = true;
			orphan.set(signal.orphanPulse.subarray(0, orphan.length));
			orphanAttribute.needsUpdate = true;
			updateFronts(delta * speed);
			updateActiveIndex();
		} else if (!wasQuiet) {
			wasQuiet = true;
			clusterState.fill(0);
			clusterTexture.needsUpdate = true;
			activation.fill(0);
			activationAttribute.needsUpdate = true;
			orphan.fill(0);
			orphanAttribute.needsUpdate = true;
			front.fill(0);
			frontAttribute.needsUpdate = true;
			// The front bookkeeping resets with the channel: a stale prevAct would
			// swallow the rising edge of the first note after the silence.
			prevAct.fill(0);
			frontAge.fill(Number.POSITIVE_INFINITY);
			learnPerCluster.fill(0);
			if (activeGeometry.drawRange.count !== 0) activeGeometry.setDrawRange(0, 0);
			if (stats) stats.pointsResponding = 0;
		}
		// The density governor runs ahead of the frontier walk, so updateLod reads the
		// cap this frame already settled on. The seed waits for the GPU's name (Stats
		// reports it after mount, so the first frames still see an empty string);
		// with no stats prop there is nothing to steer by and the cap simply stays 1.
		if (!capSeeded && stats?.renderer) {
			capSeeded = true;
			if (/intel/i.test(stats.renderer) && !/arc/i.test(stats.renderer)) densityCap = 0.55;
		}
		if (adaptive) {
			const ms = stats?.frameMs ?? 0;
			if (ms > 20) densityCap = Math.max(0.1, densityCap - delta * 0.8);
			else if (ms > 0 && ms < 13) densityCap = Math.min(1, densityCap + delta * 0.15);
		} else if (densityCap !== 1) {
			densityCap = 1;
		}
		if (stats) stats.densityCap = densityCap;
		updateLod();

		// "Heard, but nothing claimed": ease the regional breath toward the nearest
		// knot the listener reports, or back to silence. Eased rather than switched,
		// for the same reason the accent is — a state that steps reads as a glitch.
		const uStr = material.uniforms.uUnmatchedStrength;
		const uGoal = signal.unmatched >= 0 && view.counts[signal.unmatched] ? 0.8 : 0;
		uStr.value += (uGoal - uStr.value) * Math.min(1, delta * 4);
		if (uStr.value < 0.01 && uGoal === 0) uStr.value = 0;
		if (signal.unmatched >= 0 && signal.unmatched * 3 + 2 < view.centroids.length && view.counts[signal.unmatched]) {
			material.uniforms.uUnmatchedOrigin.value.set(
				view.centroids[signal.unmatched * 3],
				view.centroids[signal.unmatched * 3 + 1],
				view.centroids[signal.unmatched * 3 + 2]
			);
		}
	});

	$effect(() => () => {
		geometry.dispose();
		// Each cell disposes its own index; the attributes every geometry shares are
		// `geometry`'s to free, and freeing them twice would drop live GPU buffers.
		for (const cell of lod.cells) cell.geometry.dispose();
		activeGeometry.dispose();
		clusterTexture.dispose();
		material.dispose();
		materialActive.dispose();
	});
</script>

<!-- The resting pass, one Points per spatial cell: same material, shared attribute
	buffers, per-cell index + bounding sphere, so the frustum culls what a close zoom
	leaves behind the camera. The group stands in for the old single Points in fitFog —
	the cells carry no transform of their own, so its matrixWorld is theirs. -->
<T.Group bind:ref={points}>
	{#each lod.cells as cell (cell.key)}
		<T.Points geometry={cell.geometry} {material} frustumCulled={true} />
	{/each}
</T.Group>
<T.Points
	geometry={activeGeometry}
	material={materialActive}
	renderOrder={1}
	frustumCulled={false}
/>
