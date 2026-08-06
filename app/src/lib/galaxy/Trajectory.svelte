<script lang="ts">
	import { T, useTask, useThrelte } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';
	import { clusterProvenance, knotHeat } from '$lib/data/assets';
	import type { LyrebirdAssets } from '$lib/data/types';
	import { ACCENT, provenanceColourScaled, speciesColourScaled } from './palette';
	import type { LayoutView } from './layouts';
	import {
		MAX_PATHS,
		SIZE_REFERENCE,
		mixRgb,
		trajectoryPointsFragmentShader,
		trajectoryPointsVertexShader,
		trajectoryRibbonFragmentShader,
		trajectoryRibbonVertexShader,
		type VisualSignal
	} from './shaders';
	import { allocateRibbon, buildRibbon, RIBBON_VERTICES_PER_SEGMENT } from './ribbon';

	interface Props {
		assets: LyrebirdAssets;
		signal: VisualSignal;
		/** Where the centroids are right now; moves while the cloud rearranges. */
		view: LayoutView;
		/** The scale the whole group is drawn at, from the listening distance. */
		spread?: number;
		/** The cloud's particle size; the beads are quoted against it. */
		pointSize?: number;
		/** Colour the threads by the knot's provenance class instead of leaving them neutral. */
		prov?: boolean;
	}

	let { assets, signal, view, spread = 1, pointSize = 3, prov = false }: Props = $props();

	/** Samples per segment: enough that the travelling highlight moves smoothly. */
	const SUBDIVISIONS = 14;
	const MAX_NODES = 64;

	const centroids = untrack(() => assets.centroids.items);
	/**
	 * Each knot's hue as RGB, with the label mapping's per-knot lightness shift — the
	 * trajectory gradient's endpoints. Computed once; the walk between two knots is
	 * baked per vertex in `rebuild`.
	 *
	 * Both languages are built once and the switch picks between them, rather than
	 * rebuilding a palette every time the viewer flips it: the two arrays together are a
	 * few thousand floats, and a rebuild during a chorus is the one thing this component
	 * is written to avoid. There is no species-hue palette: the bird's hue lives on
	 * the tags and the response accent, and on every thread at once it read as the
	 * ball of wool the crowd factor below exists to prevent.
	 */
	const knotPalettes = untrack(() => {
		const heat = knotHeat(assets);
		const classes = clusterProvenance(assets);
		const light = (i: number) => 0.9 + (heat[i] ?? 0.5) * 0.2;
		return {
			provenance: centroids.map(
				(_, i) => new THREE.Color(provenanceColourScaled(classes[i] ?? 4, light(i)))
			),
			// **Ink mode: the knot's own bird, not one flat slate** (owner, 2026-08-02:
			// "end and start are the node colour they connect and the gradient between").
			//
			// This used to hand every knot the same `#8595ae`, so the per-vertex gradient
			// below was interpolating slate into slate and the threads read as one dead
			// colour however far apart their endpoints were. The gradient was never broken;
			// it was being fed two identical colours. Provenance mode has the same problem
			// for a different reason — 94 % of knots are the `recorded` class, so nearly
			// every segment there is green into green.
			//
			// Ink mode's rule is the one the owner stated: points stay greyscale, and hue
			// answers "whose sound is this" wherever it can be read — the tags, the
			// activation, and now the threads. `light()` is the same per-knot heat shift
			// the tags use, so two knots of ONE bird still differ along the thread instead
			// of collapsing to a single hue.
			ink: centroids.map(
				(c, i) => new THREE.Color(speciesColourScaled(c.speciesId, light(i)))
			)
		};
	});
	const knotColours = $derived(prov ? knotPalettes.provenance : knotPalettes.ink);
	// Preallocated to every path we will ever draw at once, then a draw range is set per
	// rebuild — reallocating buffers on every note would churn GPU memory during a chorus.
	// Line *segments* rather than a strip, so separate paths are never joined together.
	const maxVertices = MAX_PATHS * (MAX_NODES - 1) * SUBDIVISIONS * 2;
	const positions = new Float32Array(maxVertices * 3);
	const indices = new Float32Array(maxVertices);
	const pathIds = new Float32Array(maxVertices);
	const colours = new Float32Array(maxVertices * 3);

	const geometry = untrack(() => {
		const g = new THREE.BufferGeometry();
		g.setAttribute('position', new THREE.BufferAttribute(positions, 3).setUsage(THREE.DynamicDrawUsage));
		g.setAttribute('aIndex', new THREE.BufferAttribute(indices, 1).setUsage(THREE.DynamicDrawUsage));
		g.setAttribute('aPath', new THREE.BufferAttribute(pathIds, 1).setUsage(THREE.DynamicDrawUsage));
		g.setAttribute('aColour', new THREE.BufferAttribute(colours, 3).setUsage(THREE.DynamicDrawUsage));
		g.setDrawRange(0, 0);
		return g;
	});

	/**
	 * The thread itself, as ribbons. One quad per node-to-node segment — no subdivisions,
	 * because the travelling swell is computed per vertex and interpolated, so a straight
	 * segment needs exactly two ends. The bead geometry above keeps its subdivisions:
	 * those are the marks running *along* the thread and there has to be a run of them.
	 */
	const MAX_SEGMENTS = MAX_PATHS * (MAX_NODES - 1);
	const ribbon = untrack(() => allocateRibbon(MAX_SEGMENTS));
	const ribbonGeometry = untrack(() => {
		const g = new THREE.BufferGeometry();
		const dyn = (a: Float32Array, n: number) =>
			new THREE.BufferAttribute(a, n).setUsage(THREE.DynamicDrawUsage);
		g.setAttribute('position', dyn(ribbon.position, 3));
		g.setAttribute('aOther', dyn(ribbon.other, 3));
		g.setAttribute('aSide', dyn(ribbon.side, 1));
		g.setAttribute('aIndex', dyn(ribbon.index, 1));
		g.setAttribute('aPath', dyn(ribbon.path, 1));
		g.setAttribute('aColour', dyn(ribbon.colour, 3));
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

	const shared = () => ({
		uProgress: { value: progress },
		uAlpha: { value: alpha },
		uColdColor: { value: new THREE.Color('#9aa6b8') }
	});

	/**
	 * Resting thread width in CSS pixels.
	 *
	 * 2.2 against the cloud's 2-3 px marks: a thread has to be legible over a dense
	 * scatter without becoming the loudest thing on the stage, and the ordering the
	 * project keeps is that the points are the data and the thread is a relation drawn
	 * between them. The travelling swell takes it to about 5.7 px, which is where it
	 * reads as a note passing rather than as a second cloud.
	 */
	const THREAD_WIDTH = 2.2;

	const material = new THREE.ShaderMaterial({
		vertexShader: trajectoryRibbonVertexShader,
		fragmentShader: trajectoryRibbonFragmentShader,
		uniforms: {
			...shared(),
			uResolution: { value: new THREE.Vector2(1, 1) },
			uWidth: { value: THREAD_WIDTH }
		},
		transparent: true,
		depthWrite: false,
		// A ribbon is two triangles and the camera orbits, so it is seen from both sides.
		side: THREE.DoubleSide,
		blending: THREE.NormalBlending
	});

	const beadMaterial = new THREE.ShaderMaterial({
		vertexShader: trajectoryPointsVertexShader,
		fragmentShader: trajectoryPointsFragmentShader,
		uniforms: {
			...shared(),
			// its own weight array: the bead is the live position, the thread is
			// structure, and they do not fade on the same rule
			uAlpha: { value: beadAlpha },
			// Rewritten from `prov` below; the initial value is the ink mode's.
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

	/**
	 * The ribbon's width is in pixels, so it needs the drawing buffer's actual size — and
	 * it changes with the window, so this is read every frame in the task below rather
	 * than once. `getSize` is the CSS size; `getDrawingBufferSize` is what the shader's
	 * clip-space arithmetic is against, and on a retina display they differ by two.
	 */
	const { renderer } = useThrelte();
	const bufferSize = new THREE.Vector2();
	function syncResolution(): void {
		if (!renderer) return;
		renderer.getDrawingBufferSize(bufferSize);
		const res = material.uniforms.uResolution.value as THREE.Vector2;
		if (res.x === bufferSize.x && res.y === bufferSize.y) return;
		res.set(Math.max(1, bufferSize.x), Math.max(1, bufferSize.y));
		// uWidth is quoted in CSS pixels and the resolution is in device pixels, so the
		// ratio between them is exactly the pixel ratio and does not need asking for.
		const ratio = renderer.getPixelRatio ? renderer.getPixelRatio() : 1;
		material.uniforms.uWidth.value = THREAD_WIDTH * ratio;
	}

	let builtVersion = -1;
	let builtLayout = -1;

	// The gradient is baked per vertex, so switching the colour language has to invalidate
	// what was baked. Without this the threads keep the old hues until the next note.
	$effect(() => {
		void prov;
		builtVersion = -1;
	});

	/**
	 * The bead's resting colour, and the reason the spline looked untouched by the mode.
	 *
	 * A bead is drawn as `mix(uColdColor, knotHue, 0.35 + peak)`, so away from the
	 * travelling peak it is roughly two thirds its cold colour — and the bead's cold
	 * colour is the violet accent. Baking the class hues into the gradient therefore
	 * changed almost nothing anyone could see: the phrase still read as a violet dotted
	 * line, because violet is what two thirds of every resting bead was made of.
	 *
	 * In provenance mode the cold end becomes the same cool grey the thread already
	 * rests at, which hands the bead's hue over to the knot it is passing — so the
	 * animation running along a phrase is the class colour of whatever it is crossing.
	 * The accent stays the cold end in ink mode, where it is the only thing marking
	 * the live position.
	 */
	$effect(() => {
		(beadMaterial.uniforms.uColdColor.value as THREE.Color).set(prov ? '#9aa6b8' : ACCENT);
	});

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
				// The segment's gradient: the start knot's hue at t=0, the end knot's at
				// t=1, baked per vertex (mixRgb keeps the blend linear and assertable).
				const colA = knotColours[nodes[n]];
				const colB = knotColours[nodes[n + 1]];
				for (let s = 0; s < SUBDIVISIONS; s++) {
					// each subdivision contributes both of its endpoints, which is what
					// LineSegments expects and what keeps one path from joining the next
					for (const t of [s / SUBDIVISIONS, (s + 1) / SUBDIVISIONS]) {
						positions[v * 3] = a[0] + (b[0] - a[0]) * t;
						positions[v * 3 + 1] = a[1] + (b[1] - a[1]) * t;
						positions[v * 3 + 2] = a[2] + (b[2] - a[2]) * t;
						const c = mixRgb([colA.r, colA.g, colA.b], [colB.r, colB.g, colB.b], t);
						colours[v * 3] = c[0];
						colours[v * 3 + 1] = c[1];
						colours[v * 3 + 2] = c[2];
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
		geometry.attributes.aColour.needsUpdate = true;
		geometry.setDrawRange(0, v);
		geometry.computeBoundingSphere();

		// The same paths again as ribbons. Built from the node list rather than from the
		// subdivided run above: a straight segment needs two ends, and the swell that
		// travels along it is interpolated from them.
		const ribbonPaths = paths.slice(0, MAX_PATHS).map((path, p) => ({
			nodes: path.nodes.filter((i) => i >= 0 && i < centroids.length).slice(0, MAX_NODES),
			pathId: p
		}));
		const rv = buildRibbon(
			ribbon,
			ribbonPaths,
			(k) => [view.centroids[k * 3], view.centroids[k * 3 + 1], view.centroids[k * 3 + 2]],
			(k) => {
				const c = knotColours[k];
				return [c.r, c.g, c.b];
			},
			MAX_SEGMENTS
		);
		for (const name of ['position', 'aOther', 'aSide', 'aIndex', 'aPath', 'aColour']) {
			ribbonGeometry.attributes[name].needsUpdate = true;
		}
		ribbonGeometry.setDrawRange(0, rv);
		// Bounded by hand: the ribbon's vertices sit on the centre line and the shader
		// pushes them outward, so a bounding sphere fitted to the buffer is a little small
		// — and the frustum culling that would use it is off anyway, as it is for the
		// cloud, because the whole galaxy is one object that is always partly on screen.
		ribbonGeometry.computeBoundingSphere();
	}

	useTask((delta) => {
		syncResolution();
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
		ribbonGeometry.dispose();
		material.dispose();
		beadMaterial.dispose();
	});
</script>

<T.Mesh geometry={ribbonGeometry} {material} frustumCulled={false} />
<T.Points {geometry} material={beadMaterial} frustumCulled={false} />
