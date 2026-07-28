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
		/**
		 * Fired when a heading is clicked, so the page can frame the region it names.
		 *
		 * A heading is the only mark on screen that names something at the scale a viewer
		 * actually navigates by — a whole bird, or every call that claims the same kind of
		 * meaning — and it was the one mark that did nothing when clicked. Reaching that
		 * region otherwise meant finding the species in a dropdown and trusting that the
		 * island under the cursor was the same one.
		 */
		onpick?: (key: string) => void;
		/** The heading whose region is currently framed, drawn as held down. */
		active?: string;
	}

	let { elements, groups, onpick, active = '' }: Props = $props();
</script>

<div class="layer">
	{#each groups as group, i (group.key)}
		<button
			class="island"
			class:active={group.key === active}
			bind:this={elements[i]}
			onclick={() => onpick?.(group.key)}
			title="Frame this region"
		>
			<span class="name">{group.label}</span>
			<span class="meta mono">
				<!-- Separator inside the expression: Svelte trims a text node's leading space,
				     so the markup form of this rendered "226 knots· real audio". -->
				{group.count} knots{#if group.hint}<span class="hint">{` · ${group.hint}`}</span>{/if}
			</span>
		</button>
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
		/* The layer stays transparent to the pointer — dragging anywhere on the view has to
		   keep orbiting the camera — and only the headings themselves take the click. */
		pointer-events: auto;
		border-top: 0;
		border-right: 0;
		border-bottom: 0;
		font: inherit;
		text-align: left;
		cursor: pointer;
	}

	.island:hover .name,
	.island:focus-visible .name {
		color: var(--ink);
	}

	.island:focus-visible {
		outline: 1px solid var(--signal);
		outline-offset: 2px;
	}

	/* Held down while its region is the thing being framed, so the heading says which one
	   you asked for rather than leaving the camera move as the only evidence. */
	.island.active {
		background: color-mix(in srgb, var(--paper) 82%, transparent);
		border-left-color: var(--signal);
	}

	.island.active .name {
		color: var(--ink);
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
