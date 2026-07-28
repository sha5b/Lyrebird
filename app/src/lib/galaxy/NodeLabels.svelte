<script lang="ts">
	/**
	 * The floating specimen tag beside every cluster.
	 *
	 * Each node carries the things you would want written on a slide next to it: what the
	 * cluster is, whose repertoire it belongs to, how many corpus points fell into it, how
	 * tight it is, and — while audio is playing — how strongly the live sound matches it.
	 * The tag stays terse until its cluster activates, then it opens up and shows the
	 * documented function and the live figures.
	 *
	 * Positioning is done by NodeProjector, which writes transforms straight onto these
	 * elements. This component owns only the markup and the styling.
	 */
	import { untrack } from 'svelte';
	import { confidenceLabel } from '$lib/lang/translate';
	import { speciesById } from '$lib/data/assets';
	import type { BirdyAssets } from '$lib/data/types';

	interface Props {
		assets: BirdyAssets;
		/** Written into by this component, read by NodeProjector. Plain array, not state. */
		elements: (HTMLElement | null)[];
		onpick?: (cluster: number) => void;
	}

	let { assets, elements, onpick }: Props = $props();

	// The corpus does not change while this is mounted, so the tags are built once.
	const centroids = untrack(() => assets.centroids.items);
	const speciesName = (id: string) => speciesById(assets.inventory, id)?.common ?? id;
</script>

<div class="layer" aria-hidden="true">
	{#each centroids as centroid, i (centroid.id)}
		<!-- `--hot` (0 or 1) and `--act` (0..1) are written per frame by NodeProjector -->
		<div class="tag" bind:this={elements[i]}>
			<button
				class="dot conf-{centroid.confidence || 'unlabelled'}"
				type="button"
				tabindex="-1"
				aria-label={centroid.label}
				onclick={() => onpick?.(i)}
			></button>
			<div class="card">
				<div class="head">
					<span class="id mono">C{String(centroid.id).padStart(2, '0')}</span>
					<span class="name">{centroid.label}</span>
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
						<span class="conf">{confidenceLabel(centroid.confidence).text}</span>
					</div>
					{#if centroid.function}
						<p class="function">{centroid.function}</p>
					{/if}
				</div>
			</div>
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
	   class, so the transitions are the browser's and no state has to cross into Svelte. */
	.dot {
		flex: none;
		width: 7px;
		height: 7px;
		margin-top: 3px;
		padding: 0;
		border-radius: 50%;
		border: 1px solid currentColor;
		background: color-mix(in srgb, currentColor calc(var(--hot, 0) * 100%), var(--paper));
		pointer-events: auto;
		cursor: pointer;
		transform: translate(-50%, -50%) scale(calc(1 + var(--hot, 0) * 0.7));
		transition:
			transform 120ms ease,
			background 120ms ease;
	}

	.conf-experimental {
		color: var(--experimental);
	}
	.conf-documented {
		color: var(--documented);
	}
	.conf-inferred {
		color: var(--inferred);
	}
	.conf-invented {
		color: var(--invented);
	}
	.conf-unlabelled {
		color: var(--unlabelled);
	}

	.card {
		margin-top: -0.35rem;
		padding: 0.15rem 0.4rem;
		max-width: 15rem;
		border-left: 1px solid
			color-mix(in srgb, var(--signal) calc(var(--hot, 0) * 100%), var(--rule));
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
		white-space: nowrap;
	}

	.id {
		font-size: 0.6rem;
		color: var(--ink-faint);
		letter-spacing: 0.04em;
	}

	.name {
		font-size: 0.72rem;
		letter-spacing: 0.01em;
		color: color-mix(in srgb, var(--ink) calc(var(--hot, 0) * 100%), var(--ink-dim));
		transition: color 140ms ease;
	}

	.meta {
		display: flex;
		gap: 0.45rem;
		font-size: 0.58rem;
		color: var(--ink-faint);
		white-space: nowrap;
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
		background: var(--signal);
	}

	.figures {
		display: flex;
		gap: 0.4rem;
		font-size: 0.58rem;
		color: var(--ink-faint);
		white-space: nowrap;
	}

	.figures .match {
		color: var(--signal);
	}

	.figures .conf {
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
