<script lang="ts">
	/**
	 * The name of a whole island, for the arrangements that have islands.
	 *
	 * A node tag names one knot — a syllable, forty points, a few pixels across. In the
	 * Bird arrangement that is the wrong scale of answer: the thing you are looking at is
	 * a bird's entire repertoire, three thousand marks in one region, and reading which
	 * bird it is meant hunting for a legible node tag inside it and trusting that its
	 * species was the island's. Islands are the structure that arrangement creates, so
	 * they get a label of their own, at the size of the thing they name.
	 *
	 * Set well back: large, light, and behind every node tag, so it reads as a heading
	 * over a region rather than as another mark competing with the ones inside it. In the
	 * acoustic arrangement nothing is drawn at all — there are no islands there, and a
	 * label over a region of a continuous cloud would invent a boundary the projection
	 * does not have.
	 */
	interface Props {
		/** Filled by this component, positioned every frame by `IslandProjector`. */
		elements: (HTMLElement | null)[];
		groups: { key: string; label: string; count: number; hint?: string }[];
	}

	let { elements, groups }: Props = $props();
</script>

<div class="layer" aria-hidden="true">
	{#each groups as group, i (group.key)}
		<div class="island" bind:this={elements[i]}>
			<span class="name">{group.label}</span>
			<span class="meta mono">
				{group.count} knots{#if group.hint}<span class="hint"> · {group.hint}</span>{/if}
			</span>
		</div>
	{/each}
</div>

<style>
	.layer {
		position: absolute;
		inset: 0;
		overflow: hidden;
		pointer-events: none;
		/* Under the node tags (z-index 1) and over the canvas. */
		z-index: 0;
	}

	/* Same shell as a node tag — a rule down the left, the paper showing through, the
	   metadata monospaced underneath — at the scale of the thing it names. Two labels
	   built out of the same parts read as one system; two built out of different parts
	   read as two overlays that happen to share a screen. */
	.island {
		position: absolute;
		top: 0;
		left: 0;
		display: grid;
		gap: 0.05rem;
		padding: 0.1rem 0.55rem;
		/* centred on its island by the projector, which writes the translate */
		border-left: 2px solid
			color-mix(in srgb, var(--signal) calc(var(--act, 0) * 100%), var(--rule));
		background: color-mix(in srgb, var(--paper) calc(38% + var(--act, 0) * 40%), transparent);
		will-change: transform, opacity;
		transition:
			opacity 200ms linear,
			border-color 160ms ease,
			background 160ms ease;
		white-space: nowrap;
	}

	/* Responds to whatever is sounding inside it: the heading is how you see that a
	   region answered without having to find the one knot that did. */
	.name {
		font-size: 1.05rem;
		font-weight: 600;
		letter-spacing: 0.01em;
		color: color-mix(
			in srgb,
			var(--signal) calc(var(--act, 0) * 85%),
			color-mix(in srgb, var(--ink) calc(34% + var(--act, 0) * 50%), transparent)
		);
		transition: color 160ms ease;
	}

	.meta {
		font-size: 0.56rem;
		text-transform: uppercase;
		letter-spacing: 0.11em;
		color: color-mix(in srgb, var(--ink-faint) calc(65% + var(--act, 0) * 35%), transparent);
	}

	.hint {
		text-transform: none;
		letter-spacing: 0.02em;
	}
</style>
