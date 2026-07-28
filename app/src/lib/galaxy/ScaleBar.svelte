<script lang="ts">
	/**
	 * A ruler for the galaxy, and a statement of what it is worth.
	 *
	 * Without one, distance in this picture is uninterpretable: a viewer can see that two
	 * knots are far apart and has no way to know whether far means "different note" or
	 * "different bird" or nothing at all. The bar converts a length on screen into a
	 * distance in the layout, and then into the acoustic distance that stands behind it,
	 * using a relation fitted to this build's own centroids — see `scale.ts`.
	 *
	 * The two reference marks are the ones that make the number mean something. A knot is
	 * about 0.3 units across and two knots are typically about 1.1 apart, so a gap you can
	 * compare against both tells you immediately which side of "the same sound" it falls
	 * on. That comparison is what the projection genuinely supports; the cosine figure is
	 * offered alongside it with its correlation attached, because at r ≈ 0.76 the ordering
	 * of distances is trustworthy and their magnitude is an estimate.
	 */
	import { acousticSpan, niceUnits, type AcousticScale } from './scale';

	interface Props {
		/** Layout units one screen pixel covers, from `ScaleProbe`. */
		unitsPerPixel: number;
		scale: AcousticScale | null;
	}

	let { unitsPerPixel, scale }: Props = $props();

	/** Roughly how long the bar wants to be before it is rounded to a readable number. */
	const TARGET_PX = 132;

	const units = $derived(unitsPerPixel > 0 ? niceUnits(TARGET_PX * unitsPerPixel) : 0);
	const pixels = $derived(units > 0 && unitsPerPixel > 0 ? units / unitsPerPixel : 0);
	const cosine = $derived(scale && units > 0 ? acousticSpan(scale, units) : null);

	/** Two significant figures is the most this measurement can carry. */
	function short(value: number): string {
		if (value >= 100) return value.toFixed(0);
		if (value >= 10) return value.toFixed(1);
		if (value >= 1) return value.toFixed(2);
		return value.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
	}
</script>

{#if pixels > 8 && pixels < 900}
	<div class="ruler">
		<div class="bar" style:width={`${pixels.toFixed(1)}px`}>
			<span class="tick"></span>
			<span class="rule"></span>
			<span class="tick"></span>
		</div>
		<div class="read mono">
			{short(units)} <span class="faint">galaxy units</span>
			{#if cosine !== null}
				<span class="faint"> · ≈</span>{cosine.toFixed(2)}
				<span class="faint">apart in sound</span>
			{/if}
		</div>
		{#if scale}
			<!--
				The two lengths that make the number legible, drawn to the same scale as the
				bar above so they can be compared by eye rather than by arithmetic.
			-->
			<div class="refs">
				<span class="ref">
					<span
						class="refbar"
						style:width={`${Math.min(220, scale.knot / unitsPerPixel).toFixed(1)}px`}
					></span>
					<span class="reflabel">one knot across</span>
				</span>
				<span class="ref">
					<span
						class="refbar"
						style:width={`${Math.min(220, scale.gap / unitsPerPixel).toFixed(1)}px`}
					></span>
					<span class="reflabel">knot to knot, typical</span>
				</span>
			</div>
			<p class="caveat">
				28 dimensions drawn in 3, correlation r&nbsp;{scale.r.toFixed(2)}: which of two
				gaps is the wider is reliable, how much wider is an estimate. Any two clusters
				already differ by {scale.floor.toFixed(2)} before separation here counts at all.
			</p>
		{/if}
	</div>
{/if}

<style>
	.ruler {
		position: absolute;
		left: 1rem;
		bottom: 1rem;
		display: grid;
		gap: 0.3rem;
		padding: 0.55rem 0.7rem;
		background: color-mix(in srgb, var(--paper-raised) 88%, transparent);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		max-width: 20rem;
		pointer-events: none;
		z-index: 3;
	}

	.bar {
		display: flex;
		align-items: center;
		height: 9px;
	}

	.tick {
		width: 1px;
		height: 9px;
		background: var(--ink-dim);
	}

	.rule {
		flex: 1;
		height: 1px;
		background: var(--ink-dim);
	}

	.read {
		font-size: 0.68rem;
		color: var(--ink);
		letter-spacing: 0.01em;
	}

	.read .faint {
		color: var(--ink-faint);
	}

	.refs {
		display: grid;
		gap: 0.15rem;
	}

	.ref {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}

	/* Dashed, so a reference length is never mistaken for the measured bar above it. */
	.refbar {
		height: 0;
		min-width: 2px;
		border-top: 1px dashed var(--ink-faint);
	}

	.reflabel {
		font-size: 0.56rem;
		text-transform: uppercase;
		letter-spacing: 0.09em;
		color: var(--ink-faint);
		white-space: nowrap;
	}

	.caveat {
		margin: 0.1rem 0 0;
		font-size: 0.58rem;
		line-height: 1.35;
		color: var(--ink-faint);
	}
</style>
