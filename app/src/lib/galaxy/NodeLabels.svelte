<script lang="ts">
	/**
	 * The floating specimen tag beside a responding cluster.
	 *
	 * Each tag carries the things you would want written on a slide next to it: what the
	 * cluster is, whose repertoire it belongs to, how many corpus points fell into it, how
	 * tight it is, and — while audio is playing — how strongly the live sound matches it.
	 * The tag stays terse until its cluster activates, then it opens up and shows the
	 * documented function and the live figures.
	 *
	 * **This is a fixed pool of tags, not one tag per knot** — see labels.ts for the
	 * measurement that forced it. `slots[s]` is the centroid index bound into slot `s`,
	 * or -1 for a slot nothing is using; NodeProjector owns that array and rebinds a slot
	 * only when the set of tags on screen actually changes, which is a few times a second
	 * rather than sixty. The `{#each}` is keyed by slot, so the outer element is built
	 * once and lives for the session while Svelte re-renders only the text inside a slot
	 * that changed hands.
	 *
	 * Positioning is done by NodeProjector, which writes transforms straight onto these
	 * elements. This component owns only the markup and the styling.
	 */
	import { untrack } from 'svelte';
	import { confidenceLabel } from '$lib/lang/translate';
	import { clusterProvenance, knotHeat } from '$lib/data/assets';
	import { provenanceColourScaled, speciesColourScaled } from './palette';
	import type { BirdyAssets, Centroid } from '$lib/data/types';

	/** The tag dot's resting colour in ink mode: the same slate the context threads use. */
	const INK_NEUTRAL = '#8595ae';

	interface Props {
		assets: BirdyAssets;
		/**
		 * Centroid index bound into each slot, or -1. Owned by Galaxy, written by
		 * NodeProjector, read here. Reactive, because a rebind has to re-render the tag's
		 * text — and only a rebind does.
		 */
		slots: number[];
		/**
		 * Written into by this component, read by NodeProjector. **Slot-aligned, not
		 * centroid-aligned.** Plain array, not state.
		 */
		elements: (HTMLElement | null)[];
		/**
		 * Colour the tags by the knot's provenance class instead of by its bird, to match
		 * the point cloud while the provenance mode is on. Reactive, not baked: this is a
		 * switch the viewer flips, so the tags have to follow it live.
		 */
		prov?: boolean;
		/** Bird language: the species hue everywhere (ink mode keeps tags neutral). */
		bird?: boolean;
		onpick?: (cluster: number) => void;
	}

	let { assets, slots, elements, prov = false, bird = false, onpick }: Props = $props();

	// The corpus does not change while this is mounted, so the lookups are built once.
	// Names come from the inventory index: a tag must name its bird without fetching
	// that bird's shard first.
	const centroids = untrack(() => assets.centroids.items);
	const speciesName = (id: string) => assets.speciesCommon(id);
	// What a knot's extent is made of: real field syllables, or our own renders. The
	// ρ and r figures next to it measure that extent, so the tag says which it is.
	const evidenceLabel = (c: Centroid): string =>
		c.sources ? ((c.sources['field'] ?? 0) > 0 ? 'measured' : 'invented') : '';

	/**
	 * The tag's hue is the bird's hue — labels are where "which bird" is answered, and
	 * the points no longer carry it. The per-knot lightness is the heat rule moved off
	 * the points: the species' core knot carries the hue a touch darker (0.9), its far
	 * edge a touch lighter (1.1), same hue and saturation throughout — a slight
	 * gradient of the label colour, never a different one.
	 *
	 * With the provenance mode on, the same tag answers the other question instead: the
	 * hue becomes the knot's class, matching the points under it. Leaving the tags in
	 * species hues while the cloud switched to classes put two colour languages on the
	 * screen at once, and a violet tag over an amber knot invites the reading that the
	 * two colours are related — so the whole picture speaks one language at a time.
	 * Either way the tag still *names* the bird in words right beside the dot, which is
	 * why hue is free to carry the other axis.
	 *
	 * Both per-knot arrays are one pass over the corpus, so they stay lazy: on a build
	 * with 14 000 knots the provenance tally is not work to do before the first frame
	 * when the mode it serves may never be switched on.
	 */
	let heat: Float32Array | null = null;
	let knotClass: Float32Array | null = null;
	const knotColour = (c: Centroid, i: number): string => {
		heat ??= knotHeat(assets);
		const light = 0.9 + (heat[i] ?? 0.5) * 0.2;
		if (prov) {
			knotClass ??= clusterProvenance(assets);
			return provenanceColourScaled(knotClass[i] ?? 4, light);
		}
		return bird ? speciesColourScaled(c.speciesId, light) : INK_NEUTRAL;
	};
</script>

<div class="layer" aria-hidden="true">
	{#each slots as ci, s (s)}
		<!-- `--hot` (0 or 1) and `--act` (0..1) are written per frame by NodeProjector.
		     The wrapper is keyed by slot, so it is created once and only its contents
		     change when a different knot is bound into it. -->
		<div class="tag" bind:this={elements[s]}>
			{#if ci >= 0}
				{@const centroid = centroids[ci]}
				<button
					class="dot"
					style:color={knotColour(centroid, ci)}
					type="button"
					tabindex="-1"
					aria-label={centroid.label}
					onclick={() => onpick?.(ci)}
				></button>
				<div class="card">
					<div class="head">
						<span class="id mono">C{String(centroid.id).padStart(2, '0')}</span>
						<!-- full label on hover: learned names run long and the card caps their width -->
						<span class="name" title={centroid.label}>{centroid.label}</span>
					</div>
					<div class="meta mono">
						<span>{speciesName(centroid.speciesId)}</span>
						<span>n={centroid.count}</span>
						{#if centroid.meanDuration}<span>{Math.round(centroid.meanDuration * 1000)} ms</span>{/if}
					</div>
					<div class="detail">
						<div class="bar"><span></span></div>
						<div class="figures mono">
							<!-- written by NodeProjector, and only when the rounded value changes -->
							<span class="match" data-match>—</span>
							{#if centroid.cohesion !== undefined}<span>ρ {centroid.cohesion.toFixed(2)}</span>{/if}
							{#if centroid.radius !== undefined}<span>r {centroid.radius.toFixed(2)}</span>{/if}
							{#if evidenceLabel(centroid)}<span class="evidence">{evidenceLabel(centroid)}</span>{/if}
							<span class="conf">{confidenceLabel(centroid.confidence).text}</span>
						</div>
						{#if centroid.function}
							<p class="function">{centroid.function}</p>
						{/if}
					</div>
				</div>
			{/if}
		</div>
	{/each}
</div>

<style>
	.layer {
		position: absolute;
		inset: 0;
		overflow: hidden;
		pointer-events: none;
		z-index: 1;
	}

	.tag {
		position: absolute;
		top: 0;
		left: 0;
		display: flex;
		align-items: flex-start;
		gap: 0.4rem;
		/* moved every frame by NodeProjector; the element sits at the node and the card
		   hangs off to its right */
		will-change: transform, opacity;
		transition: opacity 140ms linear;
	}

	/* Everything that reacts is driven by `--hot` through calc/color-mix rather than by a
	   class, so the transitions are the browser's and no state has to cross into Svelte.
	   The dot's colour comes from --accent (written per frame by the projector): the
	   identity hue in bird and provenance modes, neutral at rest and the one accent
	   when hot in ink mode; the inline style is only the first frame's fallback. */
	.dot {
		flex: none;
		width: 7px;
		height: 7px;
		margin-top: 3px;
		padding: 0;
		border-radius: 50%;
		border: 1px solid var(--accent, currentColor);
		background: color-mix(
			in srgb,
			var(--accent, currentColor) calc(var(--hot, 0) * 100%),
			var(--paper)
		);
		pointer-events: auto;
		cursor: pointer;
		transform: translate(-50%, -50%) scale(calc(1 + var(--hot, 0) * 0.7));
		transition:
			transform 120ms ease,
			background 120ms ease;
	}

	.card {
		margin-top: -0.35rem;
		padding: 0.15rem 0.4rem;
		max-width: 15rem;
		border-left: 1px solid
			color-mix(in srgb, var(--accent, var(--signal)) calc(var(--hot, 0) * 100%), var(--rule));
		background: color-mix(
			in srgb,
			var(--paper) calc(78% + var(--hot, 0) * 16%),
			transparent
		);
		transition:
			border-color 140ms ease,
			background 140ms ease;
	}

	.head {
		display: flex;
		align-items: baseline;
		gap: 0.35rem;
	}

	.id {
		flex: none;
		font-size: 0.6rem;
		color: var(--ink-faint);
		letter-spacing: 0.04em;
	}

	.name {
		font-size: 0.72rem;
		letter-spacing: 0.01em;
		/* The bird's hue, whispering at rest and full when the knot answers: the tag
		   names the species in words AND carries its colour, so hue is never the sole
		   carrier of "which bird". */
		color: color-mix(
			in srgb,
			var(--accent, var(--ink)) calc(30% + var(--hot, 0) * 70%),
			var(--ink-dim)
		);
		transition: color 140ms ease;
		/* Learned labels carry the whole provenance sentence ("fulica_atra - learned
		   L01 · 1468 Hz · 69 ms"): far past the 15rem card cap on one line. The old
		   nowrap let them spill out of the card's left-ruled box; wrapping inside the
		   cap keeps tag and text the same width, and `title` on the span still gives
		   the full string in one gesture. */
		overflow-wrap: anywhere;
	}

	.meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.45rem;
		font-size: 0.58rem;
		color: var(--ink-faint);
	}

	/* Everything below only exists once the cluster responds — a resting galaxy stays a
	   readable diagram rather than 44 paragraphs. */
	.detail {
		display: grid;
		gap: 0.18rem;
		overflow: hidden;
		max-height: calc(var(--hot, 0) * 7rem);
		opacity: var(--hot, 0);
		transition:
			max-height 180ms ease,
			opacity 180ms ease;
	}

	.bar {
		height: 2px;
		margin-top: 0.2rem;
		background: var(--rule);
	}

	.bar span {
		display: block;
		height: 100%;
		width: calc(var(--act, 0) * 100%);
		background: var(--accent, var(--signal));
	}

	.figures {
		display: flex;
		gap: 0.4rem;
		font-size: 0.58rem;
		color: var(--ink-faint);
		white-space: nowrap;
	}

	.figures .match {
		color: var(--accent, var(--signal));
	}

	.figures .conf {
		color: var(--ink-faint);
		font-style: italic;
	}

	.figures .evidence {
		color: var(--ink-faint);
		font-style: italic;
	}

	.function {
		margin: 0;
		font-size: 0.62rem;
		line-height: 1.35;
		color: var(--ink-dim);
	}
</style>
