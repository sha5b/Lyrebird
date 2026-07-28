<script lang="ts">
	/**
	 * Puts the floating node labels where their clusters are, once per frame.
	 *
	 * It lives inside the rotating group so it inherits the same transform the points do —
	 * a label computed against the unrotated centroid would slide off its knot as the
	 * galaxy drifts. It writes to the label elements imperatively rather than through
	 * Svelte state: 44 labels at 60 fps is 2 600 reactive writes a second to move some
	 * text, and a `style.transform` costs none of that.
	 */
	import { T, useTask, useThrelte } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';
	import { buildSpeciesIndex } from '$lib/data/assets';
	import type { BirdyAssets } from '$lib/data/types';
	import type { VisualSignal } from './shaders';

	interface Props {
		assets: BirdyAssets;
		signal: VisualSignal;
		/** Filled by NodeLabels; index-aligned with `assets.centroids.items`. */
		elements: (HTMLElement | null)[];
		/** Species index to keep at full strength; -1 shows every species equally. */
		focus?: number;
		/** Cluster whose label stays expanded regardless of activation, or -1. */
		pinned?: number;
	}

	let { assets, signal, elements, focus = -1, pinned = -1 }: Props = $props();

	const { camera, size } = useThrelte();

	const centroids = untrack(() => assets.centroids.items);
	const speciesOf = untrack(() => {
		const index = buildSpeciesIndex(assets);
		return centroids.map((c) => index.get(c.speciesId) ?? -1);
	});

	let anchor = $state<THREE.Object3D | undefined>();

	const world = centroids.map((c) => new THREE.Vector3(...c.position));
	const projected = centroids.map(() => new THREE.Vector3());
	const order: number[] = centroids.map((_, i) => i);
	/** Smoothed activation per node, so a label does not strobe on a noisy frame. */
	const shown = new Float32Array(centroids.length);
	const placed: { x: number; y: number; h: number }[] = [];
	/** Cached `[data-match]` spans and their last written value, to avoid needless writes. */
	const matchEls: (HTMLElement | null)[] = centroids.map(() => null);
	const matchShown = new Int16Array(centroids.length).fill(-1);

	/**
	 * Labels closer together than this collide and the weaker one is dropped. The box is
	 * roughly the size of a tag, not a point: a tag is wide and short, so the horizontal
	 * exclusion has to be much larger than the vertical one or the text overlaps even
	 * though the anchors do not.
	 */
	const GAP_X = 168;
	const GAP_Y = 26;
	const HOT = 0.12;

	useTask(() => {
		const cam = camera.current;
		const el = elements;
		if (!cam || !anchor || !el.length) return;
		const width = size.current.width;
		const height = size.current.height;

		anchor.updateWorldMatrix(true, false);
		const matrix = anchor.matrixWorld;

		for (let i = 0; i < centroids.length; i++) {
			projected[i].copy(world[i]).applyMatrix4(matrix).project(cam);
			const act = signal.activations[i] ?? 0;
			shown[i] = shown[i] * 0.8 + act * 0.2;
		}

		// Nearest and hottest get to keep their place; anything overlapping them is hidden.
		// Without this the 44 labels pile into an unreadable stack whenever the camera
		// looks down the long axis of the cloud.
		order.sort((a, b) => {
			const hot = (shown[b] > HOT ? 1 : 0) - (shown[a] > HOT ? 1 : 0);
			return hot !== 0 ? hot : projected[a].z - projected[b].z;
		});
		placed.length = 0;

		for (const i of order) {
			const node = el[i];
			if (!node) continue;
			const p = projected[i];
			const hot = shown[i] > HOT;
			const dimmed = focus >= 0 && speciesOf[i] !== focus;
			const behind = p.z > 1 || p.z < -1;
			const x = (p.x * 0.5 + 0.5) * width;
			const y = (-p.y * 0.5 + 0.5) * height;

			const open = hot || i === pinned;
			// Selecting a bird narrows the sheet to that bird: the other species' tags go
			// away rather than greying out, which is the difference between a legible
			// diagram of one repertoire and 44 overlapping ones.
			let visible =
				!behind && x > -80 && x < width + 80 && y > -40 && y < height + 40 && !(dimmed && !hot);
			if (visible && i !== pinned) {
				// An open tag is several lines tall, so it needs a taller exclusion box than a
				// closed one. Hot tags are sorted first, so when two of them want the same
				// space the one whose cluster is actually responding keeps it.
				const gapY = open ? 70 : GAP_Y;
				for (const q of placed) {
					if (Math.abs(q.x - x) < GAP_X && Math.abs(q.y - y) < Math.max(gapY, q.h)) {
						visible = false;
						break;
					}
				}
			}
			if (visible) placed.push({ x, y, h: open ? 70 : GAP_Y });

			node.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`;
			node.style.opacity = visible ? String(Math.min(1, 0.55 + shown[i] * 3)) : '0';
			node.style.visibility = visible ? 'visible' : 'hidden';
			// Depth ordering so a near label draws over a far one.
			node.style.zIndex = String(Math.round((1 - (p.z + 1) / 2) * 1000) + (hot ? 2000 : 0));
			node.style.setProperty('--hot', open ? '1' : '0');
			node.style.setProperty('--act', shown[i].toFixed(3));

			// The one piece of text that changes while running. Written only when the
			// rounded percentage actually moves, and only for a label that is open.
			if (visible && open) {
				const pct = Math.round(shown[i] * 100);
				if (pct !== matchShown[i]) {
					matchShown[i] = pct;
					matchEls[i] ??= node.querySelector('[data-match]');
					if (matchEls[i]) matchEls[i]!.textContent = `match ${pct}%`;
				}
			}
		}
	});
</script>

<T.Object3D bind:ref={anchor} />
