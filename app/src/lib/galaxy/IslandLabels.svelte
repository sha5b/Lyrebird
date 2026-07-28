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
		groups: { key: string; label: string; count: number }[];
	}

	let { elements, groups }: Props = $props();
</script>

<div class="layer" aria-hidden="true">
	{#each groups as group, i (group.key)}
		<div class="island" bind:this={elements[i]}>
			<span class="name">{group.label}</span>
			<span class="count mono">{group.count} knots</span>
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

	.island {
		position: absolute;
		top: 0;
		left: 0;
		display: grid;
		justify-items: center;
		gap: 0.1rem;
		/* centred on its island by the projector, which writes the translate */
		will-change: transform, opacity;
		transition: opacity 200ms linear;
		white-space: nowrap;
	}

	.name {
		font-size: 1.05rem;
		font-weight: 600;
		letter-spacing: 0.01em;
		/* Light enough to sit under the cloud rather than in front of it: this is a
		   heading for a region, and the points inside it are the subject. */
		color: color-mix(in srgb, var(--ink) 38%, transparent);
	}

	.count {
		font-size: 0.56rem;
		text-transform: uppercase;
		letter-spacing: 0.11em;
		color: color-mix(in srgb, var(--ink-faint) 70%, transparent);
	}
</style>
