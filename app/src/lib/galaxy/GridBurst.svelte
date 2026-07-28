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
	import { T, useTask } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';
	import type { LayoutView } from './layouts';
	import type { VisualSignal } from './shaders';

	interface Props {
		signal: VisualSignal;
		/** Where the centroids are right now, so a cross lands on its knot. */
		view: LayoutView;
		colour?: string;
		/** Half-length of each rule, in the cloud's own units. */
		reach?: number;
	}

	let { signal, view, colour = '#8e9bab', reach = 2.4 }: Props = $props();

	/** Crosses alive at once. More than this and the field stops reading as "here". */
	const MAX_BURSTS = 6;
	/** Seconds from strike to gone. */
	const LIFETIME = 1.9;
	/** Vertices per rule: the ends fade out, so each needs its own run of segments. */
	const STEPS = 10;
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

	interface Burst {
		centre: THREE.Vector3;
		age: number;
		strength: number;
	}
	const bursts: Burst[] = Array.from({ length: MAX_BURSTS }, () => ({
		centre: new THREE.Vector3(),
		age: LIFETIME,
		strength: 0
	}));
	let next = 0;
	let lastCluster = -1;

	function strike(cluster: number, strength: number) {
		if (cluster < 0 || cluster * 3 + 2 >= view.centroids.length) return;
		const b = bursts[next];
		next = (next + 1) % MAX_BURSTS;
		b.centre.set(
			view.centroids[cluster * 3],
			view.centroids[cluster * 3 + 1],
			view.centroids[cluster * 3 + 2]
		);
		b.age = 0;
		b.strength = strength;
	}

	const AXES: [number, number, number][] = [
		[1, 0, 0],
		[0, 1, 0],
		[0, 0, 1]
	];

	function rebuild() {
		let v = 0;
		for (const b of bursts) {
			if (b.age >= LIFETIME || b.strength <= 0) continue;
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
		if (best >= 0 && best !== lastCluster && signal.level > 0.04) {
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

<T.LineSegments {geometry} {material} renderOrder={-1} frustumCulled={false} />
