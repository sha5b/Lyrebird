<script lang="ts">
	import { T, useTask, useThrelte } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';
	import { buildSpeciesIndex } from '$lib/data/assets';
	import type { BirdyAssets } from '$lib/data/types';
	import {
		CLAIM_COUNT,
		CLAIM_NONE,
		CLAIM_OF_FUNCTION,
		COLOUR_MEANING,
		COLOUR_MONO,
		COLOUR_RESPONSE,
		PALETTE_SLOTS,
		WAVE_SOURCES,
		fragmentShader,
		vertexShader,
		type VisualSignal
	} from './shaders';
	import { CLAIM_HOT, CLAIM_REST, MONO_HOT, MONO_REST, speciesPalette } from './palette';
	import { buildLayouts, type LayoutId, type LayoutView } from './layouts';

	interface Props {
		assets: BirdyAssets;
		signal: VisualSignal;
		pointSize?: number;
		/** Species index to keep at full strength; -1 shows every species equally. */
		focus?: number;
		/** COLOUR_RESPONSE or COLOUR_MEANING. */
		colourMode?: number;
		/** Multiplies the animation clock, so the pulse can be slowed down. */
		speed?: number;
		/** Which arrangement to show. Changing it animates the cloud into the new one. */
		layout?: LayoutId;
		/** Written into as the cloud rearranges, so lines and labels follow their knots. */
		view: LayoutView;
	}

	let {
		assets,
		signal,
		pointSize = 7,
		focus = -1,
		colourMode = COLOUR_RESPONSE,
		speed = 1,
		layout = 'acoustic',
		view
	}: Props = $props();

	// The corpus never changes while the component is alive, so the buffers are built once
	// from the initial props rather than tracked.
	const clusterCount = untrack(() => Math.max(1, assets.centroids.items.length));

	// One float per point, rewritten every frame from the listener's per-point response.
	// A dynamic attribute rather than a texture: 4287 floats is 17 kB, and going through
	// a data texture would cost a fetch per vertex to save an upload that is already free.
	const activation = untrack(() => new Float32Array(assets.points.n));
	const activationAttribute = new THREE.BufferAttribute(activation, 1).setUsage(
		THREE.DynamicDrawUsage
	);

	// A point inherits its cluster's claim class. A cluster with no documented function
	// gets `none` rather than the weakest real claim — see the note in `shaders.ts`.
	const claimOfCluster = untrack(() =>
		assets.centroids.items.map((c) =>
			c.function ? (CLAIM_OF_FUNCTION[c.functionClass ?? ''] ?? CLAIM_NONE) : CLAIM_NONE
		)
	);

	// `position` holds where the cloud is coming *from* and is rewritten at the start of
	// each rearrangement; `aTarget` is where it is going. The shader interpolates.
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
		const claim = new Float32Array(assets.points.n);
		const speciesIndex = buildSpeciesIndex(assets);
		const claimOf = claimOfCluster;
		for (let i = 0; i < assets.points.n; i++) {
			cluster[i] = assets.points.clusterId[i] ?? 0;
			species[i] = speciesIndex.get(assets.points.speciesId[i] ?? '') ?? -1;
			claim[i] = claimOf[cluster[i]] ?? CLAIM_NONE;
		}
		g.setAttribute('aCluster', new THREE.BufferAttribute(cluster, 1));
		g.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1));
		g.setAttribute('aSpecies', new THREE.BufferAttribute(species, 1));
		g.setAttribute('aClaim', new THREE.BufferAttribute(claim, 1));
		g.setAttribute('aAct', activationAttribute);
		g.computeBoundingSphere();
		return g;
	});

	const material = new THREE.ShaderMaterial({
		vertexShader: vertexShader(clusterCount),
		fragmentShader,
		uniforms: {
			uActivation: { value: new Float32Array(clusterCount) },
			uSung: { value: new Float32Array(clusterCount) },
			uNeutralHot: { value: new THREE.Color(MONO_HOT) },
			uTime: { value: 0 },
			uLevel: { value: 0 },
			uPointSize: { value: untrack(() => pointSize) },
			uPixelRatio: { value: typeof window === 'undefined' ? 1 : Math.min(2, window.devicePixelRatio) },
			uHighlight: { value: -1 },
			// The camera distance the point size is quoted at. Larger than the old 2.6
			// because the framing now backs off to hold the whole galaxy: at 2.6 every point
			// was less than half its intended size the moment nothing was selected.
			uSizeScale: { value: 4.0 },
			uMorph: { value: 1 },
			uFocus: { value: -1 },
			// Enough that an unselected species still reads as part of the same corpus,
			// little enough that the selected one is unmistakably the subject.
			uFocusDim: { value: 0.12 },
			uOpacity: { value: 1 },
			uMode: { value: COLOUR_RESPONSE },
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
			uRest: { value: Array.from({ length: PALETTE_SLOTS }, () => new THREE.Color()) },
			uHot: { value: Array.from({ length: PALETTE_SLOTS }, () => new THREE.Color()) },
			uSurface: { value: new THREE.Color('#fafbfc') }
		},
		transparent: true,
		depthWrite: false,
		blending: THREE.NormalBlending
	});

	$effect(() => {
		material.uniforms.uPointSize.value = pointSize;
	});

	$effect(() => {
		material.uniforms.uFocus.value = focus;
	});

	const species = speciesPalette();

	// Both palettes occupy the same uniforms; switching mode rewrites them rather than
	// shipping four arrays and branching in the fragment shader for every pixel.
	$effect(() => {
		const rest =
			colourMode === COLOUR_MONO
				? [MONO_REST]
				: colourMode === COLOUR_MEANING
					? CLAIM_REST
					: species.rest;
		const hot =
			colourMode === COLOUR_MONO
				? [MONO_HOT]
				: colourMode === COLOUR_MEANING
					? CLAIM_HOT
					: species.hot;
		const uRest = material.uniforms.uRest.value as THREE.Color[];
		const uHot = material.uniforms.uHot.value as THREE.Color[];
		for (let i = 0; i < PALETTE_SLOTS; i++) {
			uRest[i].set(rest[i % rest.length]);
			uHot[i].set(hot[i % hot.length]);
		}
		material.uniforms.uMode.value = colourMode;
	});

	const layouts = untrack(() =>
		buildLayouts(assets, buildSpeciesIndex(assets), claimOfCluster)
	);

	/**
	 * Seed the buffers from the layout, not from the raw asset.
	 *
	 * They were filled with `assets.positions` at construction, and the effect below only
	 * runs when `layout` *changes* — so on first load the cloud was drawn from the raw
	 * projection while the labels read `layouts.acoustic.centroids`. Any transform the
	 * acoustic layout applies was silently skipped until you switched arrangement and came
	 * back, which is both a source of drift between the marks and their tags and the
	 * reason a display setting appeared to do nothing.
	 */
	untrack(() => {
		current.set(layouts.acoustic.positions);
		target.set(layouts.acoustic.positions);
		positionAttribute.needsUpdate = true;
		targetAttribute.needsUpdate = true;
		view.centroids.set(layouts.acoustic.centroids);
		view.version++;
	});
	/** Seconds a rearrangement takes. Long enough to follow a point across it. */
	const MORPH_SECONDS = 1.5;
	let morph = 1;
	let fromLayout: LayoutId = 'acoustic';
	let toLayout: LayoutId = 'acoustic';

	/**
	 * Put every point exactly on its arrangement and forget the transition.
	 *
	 * A rearrangement is the one thing here that leaves the cloud in a state the data does
	 * not describe: mid-morph, a point is somewhere on the line between where it was and
	 * where it belongs. That is fine while it lasts and wrong the instant it stops, and it
	 * showed as long radial streaks — points strung out along their own paths toward the
	 * island layouts, which fan out from the centre — that never resolved. Landing the
	 * buffer on the target and dropping `uMorph` back to zero means the resting state is
	 * always a real arrangement, whatever happened during the move.
	 */
	/**
	 * Where the centroids were when the current transition started.
	 *
	 * It cannot be `layouts[fromLayout].centroids`, and that mismatch is what pulled the
	 * tags off their knots. Interrupting a rearrangement freezes the *points* wherever
	 * they had got to and starts them again from there, but the centroid lerp went on
	 * reading the layout they had left — so for the whole of the next move the labels, the
	 * trajectory threads and the grid strikes were all interpolating from a place the
	 * cloud was no longer at. Everything that asks "where is cluster N" reads this array,
	 * so they only agree if it starts where the points did.
	 */
	const fromCentroids = untrack(() => Float32Array.from(view.centroids));

	function settle(id: LayoutId) {
		current.set(layouts[id].positions);
		target.set(layouts[id].positions);
		positionAttribute.needsUpdate = true;
		targetAttribute.needsUpdate = true;
		material.uniforms.uMorph.value = 0;
		view.centroids.set(layouts[id].centroids);
		fromCentroids.set(layouts[id].centroids);
		view.version++;
		view.morphing = false;
		fromLayout = id;
		toLayout = id;
		morph = 1;
	}

	$effect(() => {
		if (layout === toLayout) return;
		// Freeze wherever the cloud is right now and start again from there, so
		// interrupting a rearrangement half way does not snap. The freeze has to reproduce
		// what the *shader* is drawing, per point: it eases the progress and then gives
		// every point its own share of it, so reading back a single linear `morph` put the
		// whole cloud somewhere it had never been and the interruption jumped.
		const a = layouts[fromLayout].positions;
		const b = layouts[toLayout].positions;
		const eased = Math.min(1, morph) * Math.min(1, morph) * (3 - 2 * Math.min(1, morph));
		for (let i = 0; i < current.length; i++) {
			const seed = seeds[(i / 3) | 0];
			const t = Math.min(1, eased * (0.75 + 0.5 * seed));
			current[i] = a[i] + (b[i] - a[i]) * t;
		}
		target.set(layouts[layout].positions);
		positionAttribute.needsUpdate = true;
		targetAttribute.needsUpdate = true;
		material.uniforms.uMorph.value = 0;
		// The knots restart from wherever they are on screen, exactly as the points do.
		fromCentroids.set(view.centroids);
		fromLayout = toLayout;
		toLayout = layout;
		morph = 0;
	});

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
	const WAVE_LIFETIME = 2.6;
	let waveK = 6;
	let pitch = 0.5;

	/** One expanding front: where it started, how old it is, how hard it hit. */
	const sources = Array.from({ length: WAVE_SOURCES }, () => ({
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
		if (cluster < 0 || cluster * 3 + 2 >= view.centroids.length) return;
		const s = sources[nextSource];
		nextSource = (nextSource + 1) % WAVE_SOURCES;
		s.origin.set(
			view.centroids[cluster * 3],
			view.centroids[cluster * 3 + 1],
			view.centroids[cluster * 3 + 2]
		);
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
		// would be mush rather than two crossing shells.
		const best = signal.best;
		if (best >= 0 && best !== lastLaunch && signal.level > 0.04) {
			// Deliberately small. A front is meant to be read as movement, and displacement
			// large enough to see in a still frame is large enough to smear a knot into a
			// streak — which stops being animation and starts being a wrong position.
			launch(best, Math.min(0.03, 0.012 + signal.level * 0.035));
		}
		if (best !== lastLaunch) lastLaunch = best;

		const u = material.uniforms;
		const ages = u.uWaveAge.value as Float32Array;
		const amps = u.uWaveAmp.value as Float32Array;
		const origins = u.uWaveOrigin.value as THREE.Vector3[];
		for (let i = 0; i < WAVE_SOURCES; i++) {
			const s = sources[i];
			s.age += delta;
			// Fade over the life rather than cutting off, so a front thins out as it
			// crosses the far side instead of vanishing mid-cloud.
			const life = Math.max(0, 1 - s.age / WAVE_LIFETIME);
			ages[i] = s.age;
			amps[i] = s.amp * life * life;
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

	useTask((delta) => {
		const u = material.uniforms;
		u.uTime.value += delta * speed;
		fitFog(points);
		fitWave(delta * speed);

		if (morph < 1) {
			morph = Math.min(1, morph + delta / MORPH_SECONDS);
			if (morph >= 1) {
				// Arrived: write the arrangement into the buffer rather than leaving the
				// cloud described as "all the way along a transition". See `settle`.
				settle(toLayout);
			} else {
				// smoothstep, so it eases out of the old arrangement and into the new one
				const eased = morph * morph * (3 - 2 * morph);
				u.uMorph.value = eased;
				// The centroids travel with their points, from where they actually were.
				const b = layouts[toLayout].centroids;
				for (let i = 0; i < view.centroids.length; i++) {
					view.centroids[i] = fromCentroids[i] + (b[i] - fromCentroids[i]) * eased;
				}
				view.version++;
				view.morphing = true;
			}
		}
		u.uLevel.value = signal.level;
		u.uHighlight.value = signal.best;
		const target = u.uActivation.value as Float32Array;
		target.set(signal.activations.subarray(0, target.length));
		const sung = u.uSung.value as Float32Array;
		sung.set(signal.sung.subarray(0, sung.length));

		activation.set(signal.pointActivation.subarray(0, activation.length));
		activationAttribute.needsUpdate = true;
	});

	$effect(() => () => {
		geometry.dispose();
		material.dispose();
	});
</script>

<T.Points bind:ref={points} {geometry} {material} frustumCulled={false} />
