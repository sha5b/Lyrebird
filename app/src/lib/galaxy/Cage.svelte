<script lang="ts">
	/**
	 * A faint measured ground under the corpus.
	 *
	 * The background grid was drawn in CSS — a flat lattice pinned to the window that did
	 * not move when the cloud did. Against a scatter you are orbiting, that is worse than
	 * no grid: the one thing on screen that looks like a spatial reference is the one
	 * thing that is not in the space, so rotating the galaxy slid every point across a
	 * stationary ruler and the depth cue it should have provided worked backwards.
	 *
	 * This lives inside the cloud's own group instead, so it rotates, scales and
	 * foreshortens with the points and its lines converge with the perspective.
	 *
	 * **A plane and not a box.** The first version was a cage on all six faces, which put
	 * grid lines *in front of* the corpus — a ruler drawn over the thing it is measuring,
	 * and from most angles you were reading the cloud through a fence. A single ground
	 * plane sits behind everything, gives the same convergence cue, and stays honest when
	 * you orbit beneath it: you see it from below, as a floor, which is what tells you the
	 * camera has gone under the corpus.
	 */
	import { T } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';

	interface Props {
		/** Half-width of the ground in the cloud's own units. Wider than the corpus. */
		extent?: number;
		/** Cells per edge. */
		divisions?: number;
		/** How far below the corpus the ground sits. */
		drop?: number;
		colour?: string;
		opacity?: number;
	}

	// The drop is just under the corpus, not a comfortable distance below it: the camera
	// frames the cloud, so anything much lower than its own radius falls outside the view
	// at every zoom and the ground is a floor nobody ever sees.
	let {
		extent = 3.2,
		divisions = 24,
		drop = 1.15,
		colour = '#aab4c0',
		opacity = 0.42
	}: Props = $props();

	const geometry = untrack(() => {
		const points: number[] = [];
		const step = (2 * extent) / divisions;
		for (let i = 0; i <= divisions; i++) {
			const a = -extent + i * step;
			points.push(-extent, 0, a, extent, 0, a);
			points.push(a, 0, -extent, a, 0, extent);
		}
		const g = new THREE.BufferGeometry();
		g.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
		return g;
	});

	/**
	 * Faded radially rather than cut off at the edge. A rectangular boundary would read as
	 * an object — the corpus would look like it was sitting on a table — where the point
	 * is to suggest a ground that continues past the frame.
	 *
	 * The fade has to be computed per *fragment*. Done per vertex it evaluates to zero
	 * everywhere and the grid is invisible: a line here has exactly two vertices, both at
	 * the outer edge of the plane where the fade is fully out, so every pixel between them
	 * interpolates between nothing and nothing.
	 */
	const material = new THREE.ShaderMaterial({
		// Read once; the effect below keeps colour and opacity current, and the extent is
		// baked into the geometry, so tracking them here would only rebuild the material.
		uniforms: untrack(() => ({
			uColour: { value: new THREE.Color(colour) },
			uOpacity: { value: opacity },
			uExtent: { value: extent }
		})),
		vertexShader: /* glsl */ `
			varying vec2 vGround;
			void main() {
				vGround = position.xz;
				gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
			}
		`,
		fragmentShader: /* glsl */ `
			varying vec2 vGround;
			uniform vec3 uColour;
			uniform float uOpacity;
			uniform float uExtent;
			void main() {
				float fade = 1.0 - smoothstep(0.12, 0.8, length(vGround) / uExtent);
				if (fade <= 0.001) discard;
				gl_FragColor = vec4(uColour, uOpacity * fade);
			}
		`,
		transparent: true,
		// Behind the corpus in every sense: it writes no depth, so no point is ever hidden
		// by a grid line, and it is drawn first.
		depthWrite: false,
		depthTest: false
	});

	$effect(() => {
		material.uniforms.uOpacity.value = opacity;
		(material.uniforms.uColour.value as THREE.Color).set(colour);
	});

	$effect(() => () => {
		geometry.dispose();
		material.dispose();
	});
</script>

<T.LineSegments {geometry} {material} position.y={-drop} renderOrder={-1} frustumCulled={false} />
