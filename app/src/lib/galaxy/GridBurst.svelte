<script lang="ts">
	/**
	 * The background grid, but only where something is singing.
	 *
	 * A flat lattice over the whole window is a poor reference for an orbiting scatter: it
	 * does not move with the cloud, so it fights the depth it is supposed to establish. A
	 * ground plane fixed that and brought its own problem — a permanent floor under a
	 * corpus that has no floor, drawn whether or not anything was happening.
	 *
	 * This draws grid lines only where a bird actually sounds. Each note lays a cross of
	 * three axis-aligned rules through the knot it came from, they brighten as the note
	 * arrives and run back out as it ends. The result is a measured field that appears
	 * around the sound and dissolves afterwards, so the strongest lines on screen are
	 * always at the place worth looking at, and the rest of the window stays empty.
	 *
	 * It shares its sources with the wave in the point cloud — same clusters, same
	 * lifetimes — so the rules and the wavefront belong to the same event rather than
	 * being two decorations that happen to fire together.
	 */
	import { T, useTask, useThrelte } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';
	import type { LayoutView } from './layouts';
	import { waveClaim, type VisualSignal } from './shaders';

	interface Props {
		signal: VisualSignal;
		/** Where the centroids are right now, so a cross lands on its knot. */
		view: LayoutView;
		colour?: string;
		/**
		 * Half-length of each rule as a share of the visible height, rather than a fixed
		 * distance in the cloud's units. A fixed length is only right at one zoom: framed
		 * on the whole corpus it is a short tick, framed on one knot it runs off every
		 * edge of the screen and the "cross" has no ends. Quoting it against what the
		 * camera can actually see keeps a strike the same size on the page at every zoom.
		 */
		reachOfView?: number;
	}

	// 1.2 of the visible half-height: the rule runs past the edge of the frame, which is
	// what makes it read as a ruled line across the background rather than as a small
	// cross sitting on a knot. Quoted against the view so that holds at every zoom.
	let { signal, view, colour = '#8e9bab', reachOfView = 1.2 }: Props = $props();

	/** Crosses alive at once. More than this and the field stops reading as "here". */
	const MAX_BURSTS = 6;
	/** Seconds from strike to gone. */
	const LIFETIME = 1.9;
	/**
	 * Segments per rule, which is what sets the *dash* length: a rule spans `reach` and is
	 * drawn as this many alternating on/off pieces, so each dash is `reach / STEPS` long.
	 * Raising it makes the dashing finer without shortening the line — those are two
	 * separate things and conflating them once already made the rules tiny instead of
	 * finely dashed.
	 */
	const STEPS = 20;
	const SEGMENTS_PER_BURST = 3 * STEPS;
	const VERTS = MAX_BURSTS * SEGMENTS_PER_BURST * 2;

	const positions = new Float32Array(VERTS * 3);
	/** Distance along the rule, 0 at the centre and 1 at the tip, for the fade. */
	const spans = new Float32Array(VERTS);
	/** How far the rule has grown, and how bright it is. */
	const growth = new Float32Array(VERTS);
	const alphas = new Float32Array(VERTS);

	const geometry = untrack(() => {
		const g = new THREE.BufferGeometry();
		g.setAttribute('position', new THREE.BufferAttribute(positions, 3).setUsage(THREE.DynamicDrawUsage));
		g.setAttribute('aSpan', new THREE.BufferAttribute(spans, 1).setUsage(THREE.DynamicDrawUsage));
		g.setAttribute('aGrowth', new THREE.BufferAttribute(growth, 1).setUsage(THREE.DynamicDrawUsage));
		g.setAttribute('aAlpha', new THREE.BufferAttribute(alphas, 1).setUsage(THREE.DynamicDrawUsage));
		g.setDrawRange(0, 0);
		return g;
	});

	const material = new THREE.ShaderMaterial({
		// Read once; the effect below keeps it current.
		uniforms: untrack(() => ({ uColour: { value: new THREE.Color(colour) } })),
		vertexShader: /* glsl */ `
			attribute float aSpan;
			attribute float aGrowth;
			attribute float aAlpha;
			varying float vFade;
			void main() {
				// The rule runs out from the centre: everything past the growth front is not
				// drawn yet, and the tip is always softer than the root.
				float reached = 1.0 - smoothstep(aGrowth - 0.18, aGrowth, aSpan);
				vFade = aAlpha * reached * (1.0 - smoothstep(0.1, 1.0, aSpan));
				gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
			}
		`,
		fragmentShader: /* glsl */ `
			uniform vec3 uColour;
			varying float vFade;
			void main() {
				if (vFade <= 0.002) discard;
				gl_FragColor = vec4(uColour, vFade);
			}
		`,
		transparent: true,
		depthWrite: false
	});

	$effect(() => {
		(material.uniforms.uColour.value as THREE.Color).set(colour);
	});

	/**
	 * A strike belongs to a *knot*, not to a place, so it remembers which cluster it came
	 * from and reads that cluster's position fresh on every frame.
	 *
	 * Storing the coordinates at strike time was fine for as long as knots never moved,
	 * and wrong the moment the arrangements arrived. Rearranging carries every cluster to
	 * a new position over a second and a half, and a live strike went on drawing its cross
	 * where its knot used to be — most visibly switching to Bird, which moves a knot most
	 * of the way across the box, leaving a set of rules ruled through empty space with
	 * nothing sounding there. The wave fronts in the point cloud had the same fault and
	 * the same fix.
	 */
	interface Burst {
		cluster: number;
		centre: THREE.Vector3;
		age: number;
		strength: number;
	}
	const bursts: Burst[] = Array.from({ length: MAX_BURSTS }, () => ({
		cluster: -1,
		centre: new THREE.Vector3(),
		age: LIFETIME,
		strength: 0
	}));
	let next = 0;
	let lastCluster = -1;

	/** Where a burst's knot is now. Returns false if the cluster has gone out of range. */
	function follow(b: Burst): boolean {
		const c = b.cluster;
		if (c < 0 || c * 3 + 2 >= view.centroids.length) return false;
		b.centre.set(view.centroids[c * 3], view.centroids[c * 3 + 1], view.centroids[c * 3 + 2]);
		return true;
	}

	function strike(cluster: number, strength: number) {
		if (cluster < 0 || cluster * 3 + 2 >= view.centroids.length) return;
		const b = bursts[next];
		next = (next + 1) % MAX_BURSTS;
		b.cluster = cluster;
		follow(b);
		b.age = 0;
		b.strength = strength;
	}

	const AXES: [number, number, number][] = [
		[1, 0, 0],
		[0, 1, 0],
		[0, 0, 1]
	];

	const { camera } = useThrelte();
	let anchor = $state<THREE.Object3D | undefined>();
	const anchorWorld = new THREE.Vector3();

	/**
	 * Rule half-length in the cloud's own units, for the camera's current framing.
	 *
	 * The visible height at the cloud's distance is `2 * d * tan(fov/2)`; dividing by the
	 * group's scale converts it into the local units the geometry is built in, so the
	 * rules stay the same length on screen whatever the distance slider and the framing
	 * are doing.
	 */
	function reachNow(): number {
		const cam = camera.current as THREE.PerspectiveCamera | undefined;
		if (!cam || !anchor) return 1.2;
		anchor.updateWorldMatrix(true, false);
		anchorWorld.setFromMatrixPosition(anchor.matrixWorld);
		const scale = anchor.matrixWorld.getMaxScaleOnAxis() || 1;
		const distance = cam.position.distanceTo(anchorWorld);
		const halfHeight = distance * Math.tan((((cam.fov ?? 55) * Math.PI) / 180) / 2);
		return Math.max(0.15, (halfHeight * reachOfView) / scale);
	}

	function rebuild() {
		const reach = reachNow();
		let v = 0;
		for (const b of bursts) {
			if (b.age >= LIFETIME || b.strength <= 0) continue;
			// Re-read every frame, so a strike rides its knot through a rearrangement.
			if (!follow(b)) continue;
			const t = b.age / LIFETIME;
			// out fast, back slower — a rule that snaps away reads as a glitch
			const grow = Math.min(1, t * 3.2);
			const alpha = b.strength * (1 - t) * (1 - t);
			for (const [ax, ay, az] of AXES) {
				for (let s = 0; s < STEPS; s++) {
					for (const end of [s / STEPS, (s + 1) / STEPS]) {
						// Both halves of the rule at once: the span is symmetric, so the sign
						// alternates with the segment index and one pass draws the whole cross.
						const sign = s % 2 === 0 ? 1 : -1;
						const d = end * reach * sign;
						positions[v * 3] = b.centre.x + ax * d;
						positions[v * 3 + 1] = b.centre.y + ay * d;
						positions[v * 3 + 2] = b.centre.z + az * d;
						spans[v] = end;
						growth[v] = grow;
						alphas[v] = alpha;
						v++;
					}
				}
			}
		}
		geometry.attributes.position.needsUpdate = true;
		geometry.attributes.aSpan.needsUpdate = true;
		geometry.attributes.aGrowth.needsUpdate = true;
		geometry.attributes.aAlpha.needsUpdate = true;
		geometry.setDrawRange(0, v);
	}

	useTask((delta) => {
		const best = signal.best;
		// The cross is the same claim the wave makes, so it answers the same gate:
		// the cluster visibly responding, not the input merely being loud.
		if (best >= 0 && best !== lastCluster && waveClaim(signal)) {
			strike(best, Math.min(1, 0.35 + signal.level * 1.2));
		}
		lastCluster = best;
		let any = false;
		for (const b of bursts) {
			if (b.age < LIFETIME) {
				b.age += delta;
				any = true;
			}
		}
		if (any) rebuild();
		else geometry.setDrawRange(0, 0);
	});

	$effect(() => () => {
		geometry.dispose();
		material.dispose();
	});
</script>

<T.Object3D bind:ref={anchor} />
<T.LineSegments {geometry} {material} renderOrder={-1} frustumCulled={false} />
