<script lang="ts">
	import { T, useTask } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';
	import type { BirdyAssets } from '$lib/data/types';
	import { ACCENT, MONO_HOT, speciesColour } from './palette';
	import type { LayoutView } from './layouts';
	import {
		MAX_PATHS,
		SIZE_REFERENCE,
		trajectoryFragmentShader,
		trajectoryPointsFragmentShader,
		trajectoryPointsVertexShader,
		trajectoryVertexShader,
		type VisualSignal
	} from './shaders';

	interface Props {
		assets: BirdyAssets;
		signal: VisualSignal;
		/** Where the centroids are right now; moves while the cloud rearranges. */
		view: LayoutView;
		/** The scale the whole group is drawn at, from the listening distance. */
		spread?: number;
		/** The cloud's particle size; the beads are quoted against it. */
		pointSize?: number;
	}

	let { assets, signal, view, spread = 1, pointSize = 3 }: Props = $props();

	/** Samples per segment: enough that the travelling highlight moves smoothly. */
	const SUBDIVISIONS = 14;
	const MAX_NODES = 64;

	const centroids = untrack(() => assets.centroids.items);
	// Preallocated to every path we will ever draw at once, then a draw range is set per
	// rebuild — reallocating buffers on every note would churn GPU memory during a chorus.
	// Line *segments* rather than a strip, so separate paths are never joined together.
	const maxVertices = MAX_PATHS * (MAX_NODES - 1) * SUBDIVISIONS * 2;
	const positions = new Float32Array(maxVertices * 3);
	const indices = new Float32Array(maxVertices);
	const pathIds = new Float32Array(maxVertices);

	const geometry = untrack(() => {
		const g = new THREE.BufferGeometry();
		g.setAttribute('position', new THREE.BufferAttribute(positions, 3).setUsage(THREE.DynamicDrawUsage));
		g.setAttribute('aIndex', new THREE.BufferAttribute(indices, 1).setUsage(THREE.DynamicDrawUsage));
		g.setAttribute('aPath', new THREE.BufferAttribute(pathIds, 1).setUsage(THREE.DynamicDrawUsage));
		g.setDrawRange(0, 0);
		return g;
	});

	const progress = new Float32Array(MAX_PATHS).fill(-1);
	/** What is drawn: eased toward `wanted`, so nothing ever cuts. */
	const alpha = new Float32Array(MAX_PATHS);
	const wanted = new Float32Array(MAX_PATHS);
	/**
	 * The bead carries its own weight, because it fades on a different rule to the thread.
	 * See the crowd factors below.
	 */
	const beadAlpha = new Float32Array(MAX_PATHS);
	const beadWanted = new Float32Array(MAX_PATHS);
	/**
	 * The thread and the bead running along it are coloured separately.
	 *
	 * A thread is structure — which knots this phrase visits, and in what order — and it
	 * is there whether or not anything is happening on it, so it is drawn in ink. The bead
	 * is the live position, the one thing on the line that is happening *now*, and it gets
	 * the accent. Colouring both the same made the whole path look equally live and hid
	 * the only part of it that was.
	 */
	const pathColour = Array.from({ length: MAX_PATHS }, () => new THREE.Color(MONO_HOT));
	const beadColour = Array.from({ length: MAX_PATHS }, () => new THREE.Color(ACCENT));

	const shared = () => ({
		uProgress: { value: progress },
		uAlpha: { value: alpha },
		uPathColour: { value: pathColour },
		uColdColor: { value: new THREE.Color('#9aa6b8') }
	});

	const material = new THREE.ShaderMaterial({
		vertexShader: trajectoryVertexShader,
		fragmentShader: trajectoryFragmentShader,
		uniforms: shared(),
		transparent: true,
		depthWrite: false,
		blending: THREE.NormalBlending
	});

	const beadMaterial = new THREE.ShaderMaterial({
		vertexShader: trajectoryPointsVertexShader,
		fragmentShader: trajectoryPointsFragmentShader,
		uniforms: {
			...shared(),
			// its own colour and weight arrays: the bead is the live position, the thread is
			// structure, and they neither look nor fade the same
			uPathColour: { value: beadColour },
			uAlpha: { value: beadAlpha },
			uColdColor: { value: new THREE.Color(ACCENT) },
			uPixelRatio: { value: typeof window === 'undefined' ? 1 : Math.min(2, window.devicePixelRatio) },
			uPointSize: { value: untrack(() => pointSize) },
			// Rewritten from `spread`, exactly as the cloud's is; see the note in the bead
			// vertex shader for why the two cannot differ.
			uSizeScale: { value: SIZE_REFERENCE }
		},
		transparent: true,
		depthWrite: false,
		blending: THREE.NormalBlending
	});

	// Quoted against the viewing scale, exactly as the cloud's marks are. A bead that does
	// not follow the same law comes loose from the knots it runs between.
	$effect(() => {
		beadMaterial.uniforms.uSizeScale.value = SIZE_REFERENCE * spread;
	});

	$effect(() => {
		beadMaterial.uniforms.uPointSize.value = pointSize;
	});

	let builtVersion = -1;
	let builtLayout = -1;

	/** Lays every active path out as a run of short segments between cluster centroids. */
	function rebuild(paths: VisualSignal['paths']): void {
		let v = 0;
		paths.slice(0, MAX_PATHS).forEach((path, p) => {
			const nodes = path.nodes.filter((i) => i >= 0 && i < centroids.length).slice(0, MAX_NODES);
			if (nodes.length < 2) return;
			for (let n = 0; n < nodes.length - 1; n++) {
				const ai = nodes[n] * 3;
				const bi = nodes[n + 1] * 3;
				const a = [view.centroids[ai], view.centroids[ai + 1], view.centroids[ai + 2]];
				const b = [view.centroids[bi], view.centroids[bi + 1], view.centroids[bi + 2]];
				for (let s = 0; s < SUBDIVISIONS; s++) {
					// each subdivision contributes both of its endpoints, which is what
					// LineSegments expects and what keeps one path from joining the next
					for (const t of [s / SUBDIVISIONS, (s + 1) / SUBDIVISIONS]) {
						positions[v * 3] = a[0] + (b[0] - a[0]) * t;
						positions[v * 3 + 1] = a[1] + (b[1] - a[1]) * t;
						positions[v * 3 + 2] = a[2] + (b[2] - a[2]) * t;
						indices[v] = n + t;
						pathIds[v] = p;
						v++;
					}
				}
			}
		});
		geometry.attributes.position.needsUpdate = true;
		geometry.attributes.aIndex.needsUpdate = true;
		geometry.attributes.aPath.needsUpdate = true;
		geometry.setDrawRange(0, v);
		geometry.computeBoundingSphere();
	}

	useTask((delta) => {
		// Rebuild when the set of paths changes, and on every frame of a rearrangement —
		// otherwise the threads stay behind while the knots they connect move away.
		if (signal.pathsVersion !== builtVersion || view.version !== builtLayout) {
			builtVersion = signal.pathsVersion;
			builtLayout = view.version;
			rebuild(signal.paths);
		}
		progress.fill(-1);
		alpha.fill(0);
		// The more threads there are, the fainter each one is drawn — and the bead does not
		// join in.
		//
		// One bird's phrase is a figure you are meant to read; twelve birds at once is a
		// texture, and drawing all twelve at the weight of one turns the galaxy into a
		// ball of wool with the cloud invisible behind it. Falling off with the count keeps
		// the total ink roughly constant.
		//
		// That argument is about the *threads*, which are long, and it was being applied to
		// the beads, which are four pixels each. Twelve of them cost almost no ink and they
		// are the one part of a chorus worth watching — where each bird is right now — so
		// fading them by three quarters along with the wool they run through is how the
		// whole-aviary view ended up with nothing visibly moving in it. They keep a much
		// gentler falloff, just enough that a dozen accents do not read as a swarm.
		const active = Math.min(MAX_PATHS, signal.paths.length);
		const crowd = active <= 1 ? 1 : Math.pow(active, -0.55);
		const beadCrowd = active <= 1 ? 1 : Math.pow(active, -0.15);
		wanted.fill(0);
		beadWanted.fill(0);
		signal.paths.slice(0, MAX_PATHS).forEach((path, i) => {
			progress[i] = path.progress;
			wanted[i] = path.alpha * crowd;
			beadWanted[i] = path.alpha * beadCrowd;
			// Thread and bead both wear the bird's own hue — the heat field's rule,
			// applied to the one thing that *is* the bird's phrase crossing the galaxy.
			// The bead stays the brighter of the two through the peak term in its shader;
			// a path with no species falls back to ink rather than borrowing a hue.
			const hue = path.speciesId ? speciesColour(path.speciesId) : MONO_HOT;
			pathColour[i].set(hue);
			beadColour[i].set(hue);
		});

		// Weight is eased rather than assigned, so a thread never steps in brightness —
		// the crowd factor changes the moment another bird starts, and without this every
		// existing thread jumps darker on that frame. Removal is faded upstream, in the
		// listener: once a path leaves the list its geometry is gone from this buffer and
		// there is nothing left here to fade.
		const ease = Math.min(1, delta * 6);
		for (let i = 0; i < MAX_PATHS; i++) {
			alpha[i] += (wanted[i] - alpha[i]) * ease;
			if (alpha[i] < 0.002) alpha[i] = 0;
			beadAlpha[i] += (beadWanted[i] - beadAlpha[i]) * ease;
			if (beadAlpha[i] < 0.002) beadAlpha[i] = 0;
		}
	});

	$effect(() => () => {
		geometry.dispose();
		material.dispose();
		beadMaterial.dispose();
	});
</script>

<T.LineSegments {geometry} {material} frustumCulled={false} />
<T.Points {geometry} material={beadMaterial} frustumCulled={false} />
