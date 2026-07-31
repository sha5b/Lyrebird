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
	import { buildLayout, type LayoutView } from './layouts';

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
		provShown = [true, true, true, true, true]
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
	 * to, because the accent is what a knot walks toward as it lights. Left on the species
	 * hue while the provenance mode was on, the one thing the eye actually follows — the
	 * node that just sounded, and the bead running along the phrase — was the only thing
	 * still answering "which bird" after everything around it had switched to answering
	 * "what kind of thing". So an amber knot flared violet-blue mid-note and the mode
	 * looked broken exactly where it mattered most. In provenance mode the accent is the
	 * subject's class colour instead, which keeps the "one language at a time" rule
	 * through the activation as well as at rest.
	 *
	 * What the accent *means* is untouched either way: it is still "this is the one you
	 * asked for", and it is still the only thing on the field wearing it.
	 */
	const accentNow = untrack(() => new THREE.Color(ACCENT));
	const accentTarget = new THREE.Color(ACCENT);

	function easeAccent(delta: number) {
		let hue = '';
		if (plain) {
			let subject = '';
			if (focus >= 0) subject = speciesIdByIndex[focus] ?? '';
			else if (waveClaim(signal)) subject = assets.centroids.items[signal.best]?.speciesId ?? '';
			if (subject) hue = speciesColour(subject);
		} else {
			let cls = -1;
			if (focus >= 0) cls = speciesClass[focus] ?? -1;
			else if (waveClaim(signal)) cls = knotClass[signal.best] ?? -1;
			if (cls >= 0) hue = provenanceColour(cls);
		}
		accentTarget.set(hue || ACCENT);
		const eased = accentNow.lerp(accentTarget, Math.min(1, delta * 4));
		material.uniforms.uAccent.value = eased;
	}

	// One float per point, rewritten every frame from the listener's per-point response.
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

	// The wavefront channel: one float per point, rewritten every frame from the front
	// pass below. The third dynamic per-point attribute — same 75 k floats, same free
	// upload as `activation` and `orphan`.
	const front = untrack(() => new Float32Array(assets.points.n));
	const frontAttribute = new THREE.BufferAttribute(front, 1).setUsage(THREE.DynamicDrawUsage);

	// `position` and `aTarget` hold the same arrangement: the shader still interpolates
	// between them, but with the islands layout gone there is nothing to morph to, so
	// both are seeded with the acoustic layout and `uMorph` never leaves zero.
	const current = untrack(() => Float32Array.from(assets.positions));
	const target = untrack(() => Float32Array.from(assets.positions));
	const positionAttribute = new THREE.BufferAttribute(current, 3).setUsage(
		THREE.DynamicDrawUsage
	);
	const targetAttribute = new THREE.BufferAttribute(target, 3).setUsage(THREE.DynamicDrawUsage);

	/**
	 * Per-point phase offsets. Kept out here because the CPU has to reproduce the shader's
	 * per-point transition progress when a rearrangement is interrupted.
	 */
	const seeds = untrack(() => {
		const s = new Float32Array(assets.points.n);
		for (let i = 0; i < s.length; i++) s[i] = ((i * 2654435761) % 1000) / 1000;
		return s;
	});

	const geometry = untrack(() => {
		const g = new THREE.BufferGeometry();
		g.setAttribute('position', positionAttribute);
		g.setAttribute('aTarget', targetAttribute);
		const cluster = new Float32Array(assets.points.n);
		const seed = seeds;
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
		}
		g.setAttribute('aCluster', new THREE.BufferAttribute(cluster, 1));
		g.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1));
		g.setAttribute('aSpecies', new THREE.BufferAttribute(species, 1));
		g.setAttribute('aBorn', new THREE.BufferAttribute(born, 1));
		g.setAttribute('aAct', activationAttribute);
		g.setAttribute('aProv', new THREE.BufferAttribute(pointProvenance(assets), 1));
		g.setAttribute('aOrphan', orphanAttribute);
		g.computeBoundingSphere();
		return g;
	});

	const material = new THREE.ShaderMaterial({
		vertexShader: vertexShader(clusterCount),
		fragmentShader,
		uniforms: {
			uActivation: { value: new Float32Array(clusterCount) },
			uSung: { value: new Float32Array(clusterCount) },
			uLearning: { value: new Float32Array(clusterCount) },
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
			uPointSize: { value: untrack(() => pointSize) },
			uPixelRatio: { value: typeof window === 'undefined' ? 1 : Math.min(2, window.devicePixelRatio) },
			uHighlight: { value: -1 },
			// Rewritten from `spread` below; the initial value only has to be sane.
			uSizeScale: { value: SIZE_REFERENCE },
			// Never leaves zero now that there is one arrangement: the shader interpolates
			// between `position` and `aTarget`, and both hold the same layout.
			uMorph: { value: 0 },
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
			// value is the shipped build's number, sane for the first frame.
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
	 * layout applies drift the marks off their tags.
	 */
	untrack(() => {
		current.set(layout.positions);
		target.set(layout.positions);
		positionAttribute.needsUpdate = true;
		targetAttribute.needsUpdate = true;
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
	 * How far a ripple reaches, quoted from the corpus's own spacing: twice the median
	 * nearest-neighbour centroid distance of the loaded build, so it adapts when a
	 * rebuild packs the knots tighter or looser instead of being tuned per build.
	 *
	 * The number on the shipped 1024-cluster build: median nearest-neighbour centroid
	 * distance 0.057 box units, so the falloff scale is 0.11. A gaussian at that scale
	 * weighs 1.0 at the source knot's centre, ~0.78 at the rim of the nearest
	 * neighbouring knot, ~0.37 two knot-spacings out, and under 2 % at twice the
	 * scale. (On the earlier 149-cluster build the same rule produced 0.27 — tighter
	 * knots get a tighter ripple automatically.) The ripple reads as an event *at*
	 * the sounding knot and its immediate neighbours, never as a cloud-wide wash.
	 */
	untrack(() => {
		const cents = layout.centroids;
		const k = clusterCount;
		if (k < 2) return;
		const nn: number[] = [];
		for (let i = 0; i < k; i++) {
			let best = Infinity;
			for (let j = 0; j < k; j++) {
				if (j === i) continue;
				const d = Math.hypot(
					cents[i * 3] - cents[j * 3],
					cents[i * 3 + 1] - cents[j * 3 + 1],
					cents[i * 3 + 2] - cents[j * 3 + 2]
				);
				if (d < best) best = d;
			}
			nn.push(best);
		}
		nn.sort((a, b) => a - b);
		material.uniforms.uWaveLocal.value = 2 * (nn[k >> 1] ?? 0.135);
	});

	// Registered after construction rather than in the geometry block above, because
	// the radial directions need the layout, which needs the assets, which the block
	// above only reads raw. Same one-time cost either way.
	untrack(() => {
		const n = assets.points.n;
		const radDir = new Float32Array(n * 3);
		for (let i = 0; i < n; i++) {
			const c = assets.points.clusterId[i];
			if (c < 0 || c >= clusterCount) continue;
			const dx = layout.positions[i * 3] - layout.centroids[c * 3];
			const dy = layout.positions[i * 3 + 1] - layout.centroids[c * 3 + 1];
			const dz = layout.positions[i * 3 + 2] - layout.centroids[c * 3 + 2];
			const d = Math.hypot(dx, dy, dz);
			if (d < 1e-6) continue;
			radDir[i * 3] = dx / d;
			radDir[i * 3 + 1] = dy / d;
			radDir[i * 3 + 2] = dz / d;
		}
		geometry.setAttribute('aFront', frontAttribute);
		geometry.setAttribute('aRadDir', new THREE.BufferAttribute(radDir, 3));

		// The per-point bloom budget, from the knot's own radius: 45 % of it, floored
		// so a tiny knot still separates visibly, capped at 0.045 (≈ 0.8 × the median
		// knot spacing on the shipped build) so the bloom stays inside the knot's
		// neighbourhood. See aBloom in shaders.ts for the measured numbers.
		const bloom = new Float32Array(n);
		for (let i = 0; i < n; i++) {
			const c = assets.points.clusterId[i];
			if (c < 0 || c >= clusterCount) continue;
			bloom[i] = Math.min(0.045, Math.max(0.015, 0.45 * graph.radii[c]));
		}
		geometry.setAttribute('aBloom', new THREE.BufferAttribute(bloom, 1));
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
	 * Cost is bounded by the live clusters' members, not the corpus: a resting frame
	 * touches only the two fill(0)s, and a chorus frame a few hundred points.
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
		for (let c = 0; c < clusterCount; c++) {
			const age = frontAge[c];
			if (!(age < FRONT_LIFE)) continue;
			const mem = graph.members[c];
			if (!mem.length) continue;
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
	function fitFog(points: THREE.Points | undefined) {
		const cam = camera.current;
		const sphere = geometry.boundingSphere;
		if (!cam || !points || !sphere) return;
		const scale = points.matrixWorld.getMaxScaleOnAxis();
		const radius = Math.max(1e-3, sphere.radius * scale);
		worldCentre.copy(sphere.center).applyMatrix4(points.matrixWorld);
		const distance = cam.position.distanceTo(worldCentre);
		const range = material.uniforms.uFogRange.value as THREE.Vector2;
		range.set(Math.max(0.01, distance - radius * 0.55), distance + radius * 1.15);
	}

	let points = $state<THREE.Points | undefined>();

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
		s.amp = strength;
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
		u.uHighlight.value = signal.best;
		const target = u.uActivation.value as Float32Array;
		target.set(signal.activations.subarray(0, target.length));
		const sung = u.uSung.value as Float32Array;
		sung.set(signal.sung.subarray(0, sung.length));

		// The learning pipeline breathes through its own channel, not the audio one.
		// Slower than a note and never marked as sung: this is work happening at a place
		// in the corpus, not a sound, and it must not be mistaken for one — the shader
		// turns it into a slow swell and keeps the 9 Hz jump for actual responses.
		const learn = u.uLearning.value as Float32Array;
		learn.fill(0);
		if (learning.length) {
			const breath = 0.45 + 0.35 * Math.sin(u.uTime.value * 3.2);
			for (const c of learning) {
				if (c >= 0 && c < learn.length) learn[c] = Math.max(learn[c], breath);
			}
		}

		activation.set(signal.pointActivation.subarray(0, activation.length));
		activationAttribute.needsUpdate = true;
		orphan.set(signal.orphanPulse.subarray(0, orphan.length));
		orphanAttribute.needsUpdate = true;
		updateFronts(delta * speed);

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
		material.dispose();
		materialActive.dispose();
	});
</script>

<T.Points bind:ref={points} {geometry} {material} frustumCulled={false} />
<T.Points {geometry} material={materialActive} renderOrder={1} frustumCulled={false} />
