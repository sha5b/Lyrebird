<script lang="ts">
	/**
	 * Puts the floating node labels where their clusters are, once per frame.
	 *
	 * It lives inside the rotating group so it inherits the same transform the points do —
	 * a label computed against the unrotated centroid would slide off its knot as the
	 * galaxy drifts. It writes to the label elements imperatively rather than through
	 * Svelte state: 26 labels at 60 fps is 1 500 reactive writes a second to move some
	 * text, and a `style.transform` costs none of that.
	 *
	 * **The per-frame work is bounded by the pool, not by the corpus.** This used to
	 * project every centroid, sort every centroid, and write seven style properties to a
	 * DOM element for every centroid, every frame. At the debug-100 4 298-knot build that is
	 * ~30 000 style mutations a frame to draw at most 26 tags, and it is what took the
	 * browser to about one frame a second; at a production build's knot count it
	 * would be ~98 000. See labels.ts. Now a cheap scalar pass over the activations picks
	 * the handful of knots that could carry a tag at all, and only those are projected,
	 * sorted, culled and written. On a silent galaxy with nothing selected that set is
	 * empty, which is also the honest answer: nothing has been asked, so nothing is named.
	 */
	import { T, useTask, useThrelte } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';
	import { buildSpeciesIndex, clusterProvenance, knotHeat } from '$lib/data/assets';
	import type { BirdyAssets } from '$lib/data/types';
	import { provenanceColourScaled, speciesColourScaled } from './palette';
	import { LABEL_SLOTS, MAX_LABELS } from './labels';
	import type { LayoutView } from './layouts';
	import type { VisualSignal } from './shaders';
	import type { GalaxyStats } from './stats';

	interface Props {
		assets: BirdyAssets;
		signal: VisualSignal;
		/** Filled by NodeLabels; **slot-aligned**, length `LABEL_SLOTS`. */
		elements: (HTMLElement | null)[];
		/** Centroid index bound into each slot, or -1. Written here, read by NodeLabels —
		 * hence `$bindable`: Svelte 5 warns when a child mutates an unbound prop. */
		slots: number[];
		/** Species index to keep at full strength; -1 shows every species equally. */
		focus?: number;
		/** Cluster whose label stays expanded regardless of activation, or -1. */
		pinned?: number;
		/** Where the centroids are right now; moves while the cloud rearranges. */
		view: LayoutView;
		/** Provenance language for the tag accent, matching the points and threads. */
		prov?: boolean;
		/**
		 * Knots the selection's relations end at (RelationThreads' set), allowed a tag
		 * while the selection stands even though the focus dimms their species. Low
		 * priority by construction: they are never hot, so the sort and the collision
		 * pass decide them exactly like any resting knot.
		 */
		related?: number[];
		/** Written, never read: what the stage cost this frame. */
		stats?: GalaxyStats;
	}

	let {
		assets,
		signal,
		elements,
		slots = $bindable(),
		focus = -1,
		pinned = -1,
		view,
		prov = false,
		related = [],
		stats
	}: Props = $props();

	const { camera, size } = useThrelte();

	/** The related knots as a Set, rebuilt only when the selection changes them. */
	const relatedSet = $derived(new Set(related));

	const centroids = untrack(() => assets.centroids.items);
	const speciesOf = untrack(() => {
		const index = buildSpeciesIndex(assets);
		return centroids.map((c) => index.get(c.speciesId) ?? -1);
	});
	/**
	 * Which knots belong to each species, so choosing a bird does not mean a scan of the
	 * whole corpus every frame to find its handful of knots.
	 */
	const knotsBySpecies = untrack(() => {
		const by = new Map<number, number[]>();
		speciesOf.forEach((s, i) => {
			const list = by.get(s);
			if (list) list.push(i);
			else by.set(s, [i]);
		});
		return by;
	});
	/** Has a documented function: worth a tag before an unnamed field cluster is. */
	const namedOf = untrack(() => centroids.map((c) => Boolean(c.function)));

	/**
	 * The tag's hue: the bird's id-hashed colour with the heat rule's slight lightness
	 * shift (see knotColour in NodeLabels — same mapping, kept here because the projector
	 * writes --accent every frame and a string rebuild per frame per tag would churn). In
	 * provenance mode the class colour takes over, the same swap NodeLabels makes — a tag
	 * may not speak two languages at once.
	 *
	 * Cached per knot on first use rather than built for the whole corpus: at 14 000 knots
	 * a full rebuild on every mode toggle is 14 000 colour strings for the 26 that will be
	 * read. The cache is dropped when the language changes, which is the only thing that
	 * moves it.
	 */
	let heat: Float32Array | null = null;
	let knotClass: Float32Array | null = null;
	let colourKey = '';
	const colourCache = new Map<number, string>();
	function knotColour(i: number): string {
		const key = prov ? 'prov' : 'hue';
		if (key !== colourKey) {
			colourKey = key;
			colourCache.clear();
		}
		const held = colourCache.get(i);
		if (held !== undefined) return held;
		heat ??= knotHeat(assets);
		const light = 0.9 + (heat[i] ?? 0.5) * 0.2;
		let out: string;
		if (prov) {
			knotClass ??= clusterProvenance(assets);
			out = provenanceColourScaled(knotClass[i] ?? 4, light);
		} else {
			out = speciesColourScaled(centroids[i].speciesId, light);
		}
		colourCache.set(i, out);
		return out;
	}

	let anchor = $state<THREE.Object3D | undefined>();

	/** Smoothed activation per node, so a label does not strobe on a noisy frame. */
	const shown = new Float32Array(centroids.length);
	/**
	 * How long a tag stays up after its cluster has gone quiet.
	 *
	 * **Kept separate from the activation on purpose.** A syllable lasts a tenth of a
	 * second; a person reading "Black-capped chickadee — D note" needs a second or two.
	 * Driving visibility straight off the activation meant a tag appeared and vanished
	 * inside one note, so the label was technically correct and never once legible —
	 * during a chorus it read as flicker.
	 *
	 * Slowing the activation itself would have been the wrong fix: that number is also
	 * the match percentage and the tag's own accent, and a smoothed version of it would
	 * report a match that had already stopped. So the *figure* stays honest and fast, and
	 * only the decision to keep the tag on screen is slow: it rises with the activation
	 * instantly and then bleeds away linearly, which is predictable to read and easy to
	 * reason about.
	 *
	 * It is also what makes the candidate scan cheap: a knot with no activation and no
	 * remaining linger is skipped in one comparison, and on a quiet frame that is every
	 * knot in the corpus.
	 */
	const LINGER_SECONDS = 2.6;
	const linger = new Float32Array(centroids.length);
	/** Below this, an envelope is snapped to zero so the scan's skip test stays true. */
	const REST_EPSILON = 1e-4;

	/** Scratch, reused every frame: the knots that could carry a tag this frame. */
	const candidates: number[] = [];
	/**
	 * Per candidate, which of its knot's drawn patches this site is: 0 the knot's own
	 * anchor, 1 the second lobe of a knot the projection tore. Parallel to `candidates`
	 * and only ever written through `addSite`, so the two cannot come out of step.
	 */
	const candidateLobe: number[] = [];
	/** Scratch: one entry per tag that survived culling, in draw order. */
	interface Chosen {
		ci: number;
		x: number;
		y: number;
		near: number;
		z: number;
		hot: boolean;
		open: boolean;
	}
	const chosen: Chosen[] = [];
	const world = new THREE.Vector3();
	/** Projected position per candidate, index-aligned with `candidates`. */
	const projected: THREE.Vector3[] = [];
	/** Candidate slots in draw order. Reused, so a live frame allocates nothing. */
	const order: number[] = [];
	const placed: { x: number; y: number; h: number }[] = [];

	/** Which centroid each slot holds, or -1. The authority; `slots` mirrors it for Svelte. */
	const bound = new Int32Array(LABEL_SLOTS).fill(-1);
	/** Cached `[data-match]` spans and their last written value, **per slot**. */
	const matchEls: (HTMLElement | null)[] = Array.from({ length: LABEL_SLOTS }, () => null);
	const matchShown = new Int16Array(LABEL_SLOTS).fill(-1);
	/** Last visibility written per slot, so `visibility` is not rewritten every frame. */
	const wasVisible = new Int8Array(LABEL_SLOTS).fill(-1);

	/**
	 * Labels closer together than this collide and the weaker one is dropped. The box is
	 * roughly the size of a tag, not a point: a tag is wide and short, so the horizontal
	 * exclusion has to be much larger than the vertical one or the text overlaps even
	 * though the anchors do not.
	 */
	const GAP_X = 168;
	const GAP_Y = 26;
	const HOT = 0.12;

	useTask((delta) => {
		const cam = camera.current;
		const el = elements;
		if (!cam || !anchor || !el.length) return;
		const width = size.current.width;
		const height = size.current.height;

		anchor.updateWorldMatrix(true, false);
		const matrix = anchor.matrixWorld;

		// The one fixed-per-frame ease in the file: 0.8/0.2 per *frame* reacts twice as
		// fast at 120 Hz as at 60 Hz. Scaled by delta it is the same half-life on every
		// display (0.2 at 60 fps, identical behaviour to what it replaces there).
		const ease = 1 - Math.pow(0.8, delta * 60);
		const acts = signal.activations;

		// **Pass one: the envelopes, and who is a candidate.** Scalar only — no matrix
		// work, no DOM, no allocation. A knot at rest with nothing lingering costs one
		// comparison, and on a quiet frame that is the whole corpus.
		candidates.length = 0;
		candidateLobe.length = 0;
		/**
		 * Add a knot as a tag site — and its second patch too, when the projection drew it
		 * in two places (`layouts.ts::drawnLobes`).
		 *
		 * Both patches light when the knot sings, because `pulseCluster` lights by cluster
		 * id and knows nothing about position. Naming only the first is what leaves the
		 * other one lit and anonymous, which is the report this exists to answer. Every
		 * per-knot array below is still indexed by the knot, which is correct: the two
		 * patches are the same type, the same bird and the same activation. Only the
		 * position differs.
		 */
		const addSite = (i: number) => {
			candidates.push(i);
			candidateLobe.push(0);
			if (view.lobes.has[i]) {
				candidates.push(i);
				candidateLobe.push(1);
			}
		};
		for (let i = 0; i < shown.length; i++) {
			const act = acts[i] ?? 0;
			if (act === 0 && shown[i] === 0 && linger[i] === 0) continue;
			shown[i] += (act - shown[i]) * ease;
			const decayed = linger[i] - delta / LINGER_SECONDS;
			linger[i] = Math.max(shown[i], decayed > 0 ? decayed : 0);
			if (linger[i] > 0) {
				addSite(i);
			} else if (act === 0 && shown[i] < REST_EPSILON) {
				// Snap to exact rest so the skip test above catches this knot from now on.
				shown[i] = 0;
				linger[i] = 0;
			}
		}
		// A chosen bird's knots and a pinned knot get a tag whether or not they are
		// responding — that is what choosing them asked for. Neither can already be in
		// the set: everything above has `linger > 0`, and these are the ones that do not.
		if (focus >= 0) {
			for (const i of knotsBySpecies.get(focus) ?? []) {
				if (linger[i] <= 0 && i !== pinned) addSite(i);
			}
		}
		// The selection's relations join at the same rule: a knot a thread ends at may
		// be named while the selection stands. The related set changes only with the
		// selection, so the Set is rebuilt by the derivation above, never per frame.
		if (relatedSet.size) {
			for (const i of relatedSet) {
				if (i < shown.length && (linger[i] ?? 0) <= 0 && i !== pinned) candidates.push(i);
			}
		}
		if (pinned >= 0 && pinned < shown.length && linger[pinned] <= 0) addSite(pinned);

		// **Pass two: project the candidates only.** Two matrix multiplies each, and the
		// set is bounded by what is sounding plus one bird's repertoire.
		for (let c = 0; c < candidates.length; c++) {
			const i = candidates[c];
			// read from the shared view, so a tag stays on its knot through a rearrangement
			// A torn knot's second patch is drawn at its own lobe's most central member;
			// the primary is the knot's own anchor. Both are real places with points under
			// them, which a mean between two lobes is not.
			const src = candidateLobe[c] === 1 ? view.lobes.anchors : view.centroids;
			world.set(src[i * 3], src[i * 3 + 1], src[i * 3 + 2]);
			projected[c] ??= new THREE.Vector3();
			projected[c].copy(world).applyMatrix4(matrix).project(cam);
		}

		// Who gets a tag, in order: whatever is responding, then whatever has something to
		// say, then whatever is nearest. The middle term is the one that matters now that
		// most clusters are field audio — a cluster with a documented function carries a
		// name, a citation and a claim, and "unlabelled field cluster" repeated forty times
		// carries none of that, so it should not be what crowds the named ones out.
		//
		// The sort is over the candidates, so it is a couple of dozen comparisons on a
		// live frame instead of `k log k` over the corpus on every frame including the
		// silent ones.
		order.length = candidates.length;
		for (let c = 0; c < candidates.length; c++) order[c] = c;
		order.sort((a, b) => {
			const ia = candidates[a];
			const ib = candidates[b];
			const hot = (linger[ib] > HOT ? 1 : 0) - (linger[ia] > HOT ? 1 : 0);
			if (hot !== 0) return hot;
			const named = (namedOf[ib] ? 1 : 0) - (namedOf[ia] ? 1 : 0);
			if (named !== 0) return named;
			return projected[a].z - projected[b].z;
		});

		// **Pass three: cull.** Same rules as before — off-screen, behind the camera,
		// dimmed by a focus, colliding with a tag already placed, or past the budget.
		placed.length = 0;
		chosen.length = 0;
		let budget = MAX_LABELS;
		for (const c of order) {
			const i = candidates[c];
			const p = projected[c];
			// `hot` is what keeps a tag on screen, so it reads the lingering envelope; the
			// figures inside the tag still read the live activation.
			const hot = linger[i] > HOT;
			const dimmed = focus >= 0 && speciesOf[i] !== focus;			const behind = p.z > 1 || p.z < -1;
			const x = (p.x * 0.5 + 0.5) * width;
			const y = (-p.y * 0.5 + 0.5) * height;

			const open = hot || i === pinned;
			// Selecting a bird narrows the sheet to that bird: the other species' tags go
			// away rather than greying out, which is the difference between a legible
			// diagram of one repertoire and 44 overlapping ones.
			//
			// **With nothing selected, only what is responding gets a tag at all.** The
			// whole-corpus view had every cluster's name on screen at once, which at 176
			// knots is a sheet of text with a galaxy somewhere behind it — and none of it
			// answers a question anyone asked, because nothing has been chosen. The island
			// headings say where you are; the small tags are for what is happening, so
			// they appear when something happens and leave when it stops.
			const idle = focus < 0 && !hot && i !== pinned;
			let visible =
				!behind &&
				!idle &&
				x > -80 &&
				x < width + 80 &&
				y > -40 &&
				y < height + 40 &&
				// A related knot is exempt from the focus dim: it is on screen because
				// the selection's relations point at it, so dimming it away would name
				// the thread's far end invisible at exactly the moment it matters.
				!(dimmed && !hot && !relatedSet.has(i)) &&
				(budget > 0 || i === pinned || hot);
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
			if (!visible) continue;
			placed.push({ x, y, h: open ? 70 : GAP_Y });
			budget--;
			// Depth: a tag on the far side of the cloud is written over everything in
			// front of it, and at 176 knots that reads as one flat sheet with no sense of
			// which name belongs to which depth. Fading with distance restores the cue the
			// cloud itself already has — the points behind are washed toward the paper —
			// and costs nothing, because a far tag is the one you were least likely to be
			// reading. `p.z` is normalised device depth, -1 at the near plane to 1 at the
			// far one, so this is the same curve the aerial perspective in the shader uses.
			const depth = Math.min(1, Math.max(0, (p.z + 1) * 0.5));
			chosen.push({ ci: i, x, y, near: 1 - 0.65 * depth * depth, z: p.z, hot, open });
			// The pool is two above the budget, so this can only bite if the budget itself
			// is raised past it; stopping is better than evicting a tag being read.
			if (chosen.length >= LABEL_SLOTS) break;
		}

		// **Pass four: bind the winners to slots**, keeping a knot in the slot it already
		// has. Stability is not cosmetic: a rebind re-renders the tag's text and restarts
		// its CSS transitions, so a tag that stayed on screen must keep its element.
		for (let s = 0; s < LABEL_SLOTS; s++) {
			const held = bound[s];
			if (held < 0) continue;
			let stillWanted = false;
			for (const ch of chosen) {
				if (ch.ci === held) {
					stillWanted = true;
					break;
				}
			}
			if (!stillWanted) {
				bound[s] = -1;
				slots[s] = -1;
				matchEls[s] = null;
				matchShown[s] = -1;
			}
		}
		for (const ch of chosen) {
			if (bound.includes(ch.ci)) continue;
			const s = bound.indexOf(-1);
			if (s < 0) break;
			bound[s] = ch.ci;
			slots[s] = ch.ci;
			matchEls[s] = null;
			matchShown[s] = -1;
		}

		// **Pass five: write the styles**, at most `LABEL_SLOTS` elements' worth.
		for (const ch of chosen) {
			const s = bound.indexOf(ch.ci);
			if (s < 0) continue;
			const node = el[s];
			if (!node) continue;
			const i = ch.ci;
			node.style.transform = `translate3d(${ch.x.toFixed(1)}px, ${ch.y.toFixed(1)}px, 0)`;
			node.style.opacity = String(Math.min(1, (0.35 + linger[i] * 3) * ch.near));
			if (wasVisible[s] !== 1) {
				node.style.visibility = 'visible';
				wasVisible[s] = 1;
			}
			// Depth ordering so a near label draws over a far one.
			node.style.zIndex = String(Math.round((1 - (ch.z + 1) / 2) * 1000) + (ch.hot ? 2000 : 0));
			node.style.setProperty('--hot', ch.open ? '1' : '0');
			node.style.setProperty('--act', shown[i].toFixed(3));
			// The tag's accent is the identity colour in both languages — the bird's
			// hue in ink mode, the knot's class colour in provenance — at rest and hot
			// alike; how much of it shows is --hot's job, not the colour's. It is also
			// the same hue the cloud's response accent lights in (easeAccent), so a
			// singing knot and its tag can never disagree about who is sounding.
			node.style.setProperty('--accent', knotColour(i));

			// The one piece of text that changes while running. Written only when the
			// rounded percentage actually moves, and only for a label that is open.
			if (ch.open) {
				const pct = Math.round(shown[i] * 100);
				if (pct !== matchShown[s]) {
					// Re-queried after a rebind: the span belongs to the knot now in the slot,
					// and on the frame of the rebind Svelte has not rendered it yet, so a null
					// here simply means "try again next frame".
					matchEls[s] ??= node.querySelector('[data-match]');
					if (matchEls[s]) {
						matchEls[s]!.textContent = `match ${pct}%`;
						matchShown[s] = pct;
					}
				}
			}
		}
		// Slots nothing is using are hidden, once, and then left alone.
		for (let s = 0; s < LABEL_SLOTS; s++) {
			if (bound[s] >= 0 || wasVisible[s] === 0) continue;
			const node = el[s];
			if (!node) continue;
			node.style.visibility = 'hidden';
			node.style.opacity = '0';
			wasVisible[s] = 0;
		}

		if (stats) stats.tagsDrawn = chosen.length;
	});
</script>

<T.Object3D bind:ref={anchor} />
