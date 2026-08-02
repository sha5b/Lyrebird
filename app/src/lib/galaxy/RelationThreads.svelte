<script lang="ts">
	/**
	 * The selected bird's relations, drawn as hairlines between knots.
	 *
	 * relations.json says which *other* species share call shapes with the selection —
	 * nearer than two types of one bird usually are, a distance, never a claim of
	 * borrowing or kinship (§8.5, and the UI copy says so wherever these are named).
	 * Each shared type pair is one segment, from the selection's knot to the partner's
	 * knot, coloured at the partner end in the partner's hue and fading to the
	 * context slate at the selection's end: the line reads as "from here, outward to
	 * who". The hue is the same FNV-hash hue the tags carry, so a thread and a tag
	 * never disagree about who the far end is.
	 *
	 * Rebuilt only on a selection change — event-driven, never per frame — and empty
	 * when nothing is selected. Capped at 64 segments, nearest pairs first: the most
	 * connected species in the corpus carries 8 partners × up to 8 shared types each,
	 * and past 64 lines the answer to "what sounds like this" stops being readable.
	 * Style follows ContextPaths (segments, vertex colours, normal blending), with a
	 * little more ink than the backdrop threads so the relation reads over them.
	 */
	import { T } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';
	import { relationPartners } from '$lib/data/assets';
	import type { BirdyAssets } from '$lib/data/types';
	import type { LayoutView } from './layouts';
	import { speciesColourScaled } from './palette';

	interface Props {
		assets: BirdyAssets;
		/** Where the centroids are right now; seeded once at load. */
		view: LayoutView;
		/** The selected species' id; empty draws nothing. */
		speciesId?: string;
	}

	let { assets, view, speciesId = '' }: Props = $props();

	const MAX_THREADS = 64;
	const NEUTRAL = new THREE.Color('#8595ae');

	const partners = untrack(() => relationPartners(assets));

	const geometry = new THREE.BufferGeometry();
	const material = new THREE.LineBasicMaterial({
		transparent: true,
		opacity: 0.45,
		depthWrite: false,
		blending: THREE.NormalBlending,
		vertexColors: true
	});

	$effect(() => {
		const id = speciesId;
		// The centroids are seeded once by PointCloud; if this ever runs before that,
		// the version bump rebuilds rather than drawing at the raw positions.
		void view.version;
		const entries = id ? (partners.get(id) ?? []) : [];
		const all = entries.flatMap((e) =>
			e.threads.map((t) => ({ ...t, partner: e.partner }))
		);
		all.sort((x, y) => x.distance - y.distance);
		const points: number[] = [];
		const colors: number[] = [];
		const c = new THREE.Color();
		for (const t of all.slice(0, MAX_THREADS)) {
			const a = t.from * 3;
			const b = t.to * 3;
			points.push(
				view.centroids[a], view.centroids[a + 1], view.centroids[a + 2],
				view.centroids[b], view.centroids[b + 1], view.centroids[b + 2]
			);
			colors.push(NEUTRAL.r, NEUTRAL.g, NEUTRAL.b);
			c.setStyle(speciesColourScaled(t.partner, 1.0));
			colors.push(c.r, c.g, c.b);
		}
		geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
		geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
		geometry.computeBoundingSphere();
	});

	$effect(() => () => {
		geometry.dispose();
		material.dispose();
	});
</script>

<T.LineSegments {geometry} {material} frustumCulled={false} />
