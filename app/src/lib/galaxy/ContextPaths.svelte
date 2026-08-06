<script lang="ts">
	/**
	 * The backdrop threads, and they now say which claim each one makes.
	 *
	 * Two passes, because the two kinds are two different statements about the bird:
	 *
	 *   songs    a sequence a person authored or recorded. Neutral slate, even weight —
	 *            the established backdrop ink, unchanged.
	 *   grammar  one transition counted from this bird's own field audio, drawn in **that
	 *            bird's hue**, at an alpha set by **its measured probability**, walked from
	 *            dark to light **in the direction of the transition**.
	 *
	 * `RelationThreads` draws the third kind (out to other species that share call shapes)
	 * and distinguishes itself by carrying the partner's hue at the far end. So three claims
	 * have three inks, where they used to share one grey.
	 *
	 * The grammar ink used to be a flat `PROV_LEARNED` amber, on the argument that the app
	 * says amber for a fitted thing wherever provenance is the language. That argument holds
	 * for a *point*, whose class is the only thing it can be asked; it fails for a thread,
	 * because a transition already knows two things a constant cannot say — whose grammar it
	 * is, and which way it runs. Amber said neither, so a hundred birds' graphs were one
	 * colour and every arrow was drawn as a plain stick. The hue and the walk are in
	 * `context-threads.ts` with the alpha, and for the same reason: a wrong colour here is a
	 * legible line, not an error, so it needs an instrument rather than a look.
	 *
	 * Songs keep the slate. The split reads as a sentence now: **a hued thread is counted
	 * from the bird, a slate thread is an order somebody chose.**
	 *
	 * Weight is carried as per-vertex alpha rather than line width: `linewidth` is ignored
	 * by every WebGL renderer, so width is not a channel this project has.
	 *
	 * Which pass a thread belongs in and what alpha it gets are in `context-threads.ts`,
	 * where `verify:context-threads` can prove them — a wrong alpha is a slightly faint
	 * line, not an error, so it needs an instrument rather than a look.
	 */
	import { T, useTask } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';
	import { clusterProvenance } from '$lib/data/assets';
	import type { LyrebirdAssets } from '$lib/data/types';
	import { provenanceColourScaled } from './palette';
	import { contextSegments, grammarEnds, type ThreadSegment } from './context-threads';
	import type { LayoutView } from './layouts';
	import type { ContextPath, VisualSignal } from './shaders';

	interface Props {
		assets: LyrebirdAssets;
		signal: VisualSignal;
		/** Where the centroids are right now; moves while the cloud rearranges. */
		view: LayoutView;
		/** Provenance language: each segment takes its knot's class colour. */
		prov?: boolean;
	}

	let { assets, signal, view, prov = false }: Props = $props();

	const centroids = untrack(() => assets.centroids.items);
	const klass = untrack(() => clusterProvenance(assets));

	// Disconnected segments rather than one polyline, so separate songs are not joined to
	// each other. Overlap is the point: where two songs share a transition the segment is
	// drawn twice and the accumulated alpha reads darker, so the bird's reused paths stand
	// out — on a light ground that means normal blending, not additive.
	// Colours follow the stage's language: neutral slate in ink mode (the backdrop the
	// accent reads against — the bird's hue lives on the tags and the response, not on
	// every thread), the class colour in provenance mode — per-vertex, so a thread
	// never speaks two languages at once.
	const NEUTRAL = new THREE.Color('#8595ae');

	const geometry = new THREE.BufferGeometry();
	const material = new THREE.LineBasicMaterial({
		transparent: true,
		opacity: 0.28,
		depthWrite: false,
		blending: THREE.NormalBlending,
		vertexColors: true
	});

	// The weighted pass carries its strength per vertex, so its own opacity is 1 and the
	// alpha in the colour attribute is the only thing setting how a segment reads. Two
	// places multiplying into one appearance is how a weight channel goes quietly wrong.
	const weighted = new THREE.BufferGeometry();
	const weightedMaterial = new THREE.LineBasicMaterial({
		transparent: true,
		opacity: 1,
		depthWrite: false,
		blending: THREE.NormalBlending,
		vertexColors: true
	});

	let builtVersion = -1;
	let builtLayout = -1;

	const c = new THREE.Color();

	/** One pass's vertices. `alphas` is written only for the weighted pass (itemSize 4). */
	function fill(segments: ThreadSegment[], withAlpha: boolean) {
		const points: number[] = [];
		const colors: number[] = [];
		for (const seg of segments) {
			const a = seg.a * 3;
			const b = seg.b * 3;
			points.push(
				view.centroids[a], view.centroids[a + 1], view.centroids[a + 2],
				view.centroids[b], view.centroids[b + 1], view.centroids[b + 2]
			);
			// Both knots of a transition belong to one bird — `grammarPathsOf` resolves `to`
			// within the same species — so either end names the hue. Read from whichever end
			// has a species tag, because a knot's `speciesId` is its members' majority and an
			// all-synthetic knot can carry none.
			const ends = withAlpha
				? grammarEnds(centroids[seg.a]?.speciesId || centroids[seg.b]?.speciesId || '')
				: null;
			for (const [end, knot] of [seg.a, seg.b].entries()) {
				if (prov) c.setStyle(provenanceColourScaled(klass[knot] ?? 4, 1.0));
				else if (ends) c.setStyle(end === 0 ? ends.from : ends.to);
				else c.copy(NEUTRAL);
				colors.push(c.r, c.g, c.b);
				if (withAlpha) colors.push(seg.alpha);
			}
		}
		return { points, colors };
	}

	function rebuild(paths: ContextPath[]): void {
		const { songs, grammar } = contextSegments(paths, centroids.length);
		const s = fill(songs, false);
		// three.js only reads per-vertex alpha when the colour attribute's itemSize is 4.
		const g = fill(grammar, true);
		geometry.setAttribute('position', new THREE.Float32BufferAttribute(s.points, 3));
		geometry.setAttribute('color', new THREE.Float32BufferAttribute(s.colors, 3));
		geometry.computeBoundingSphere();
		weighted.setAttribute('position', new THREE.Float32BufferAttribute(g.points, 3));
		weighted.setAttribute('color', new THREE.Float32BufferAttribute(g.colors, 4));
		weighted.computeBoundingSphere();
	}

	useTask(() => {
		if (signal.contextVersion !== builtVersion || view.version !== builtLayout) {
			builtVersion = signal.contextVersion;
			builtLayout = view.version;
			rebuild(signal.context);
		}
	});

	$effect(() => {
		// A language switch does not bump the context version; force the repaint.
		void prov;
		builtVersion = -1;
	});

	$effect(() => () => {
		geometry.dispose();
		material.dispose();
		weighted.dispose();
		weightedMaterial.dispose();
	});
</script>

<T.LineSegments {geometry} {material} frustumCulled={false} />
<T.LineSegments geometry={weighted} material={weightedMaterial} frustumCulled={false} />
