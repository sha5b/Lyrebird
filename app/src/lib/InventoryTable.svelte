<script lang="ts">
	/**
	 * The learned inventory as a table that follows what is sounding.
	 *
	 * Owner: *"while it plays it jumps around in the list."* That is the whole
	 * specification, and it is a good one — the galaxy says where a sound is and says
	 * nothing about what was fitted to produce it. Every number in these columns was
	 * measured by the pipeline and, until now, was only reachable by reading
	 * `learned-v*.json` by hand.
	 *
	 * **Windowed, not paged.** 16 283 rows over 2 650 species, drawn over a canvas already
	 * spending its budget on 387 287 points: one DOM node per row costs more than the
	 * picture behind it. Only the visible slice exists, held in place by two spacers, so
	 * the scrollbar still measures the whole corpus and the browser's own find-in-page is
	 * the price. The arithmetic is in `inventory-rows.ts` and `verify:inventory-table`
	 * checks it, because an off-by-one here shows as a row that never highlights rather
	 * than as an error.
	 */
	import { rowWindow, followRow, type InventoryRow } from '$lib/data/inventory-rows';

	interface Props {
		rows: InventoryRow[];
		/** Row index of the note sounding now, or -1. */
		active: number;
		/** Whether the list is pulled to the sounding row. Off, it stays where you put it. */
		follow?: boolean;
		/** A species' hue, for the swatch — the same one the cloud draws it in. */
		colourOf?: (speciesId: string) => string;
		/** Clicking a row asks the galaxy to go to that knot. */
		onpick?: (row: InventoryRow) => void;
	}

	let { rows, active, follow = true, colourOf, onpick }: Props = $props();

	/**
	 * Row height in pixels, and it has to be a constant rather than measured: the window
	 * arithmetic multiplies by it to place a slice of rows inside the full scroll height,
	 * so a row that sizes to its content would put every row below it in the wrong place.
	 * The CSS below fixes it to the same number.
	 */
	const ROW_PX = 24;

	let scrollEl: HTMLDivElement | undefined = $state(undefined);
	let scrollTop = $state(0);
	let viewportPx = $state(600);

	const view = $derived(rowWindow(scrollTop, viewportPx, ROW_PX, rows.length));
	const slice = $derived(rows.slice(view.first, view.end));

	/**
	 * The pull toward the sounding row.
	 *
	 * Keyed on `active` alone: reading `scrollTop` here would re-run the effect on every
	 * scroll event and fight a hand scroll for the rest of the phrase. The current offset
	 * is read out of the element instead, untracked by construction.
	 */
	$effect(() => {
		const index = active;
		if (!follow || index < 0 || !scrollEl) return;
		const to = followRow(index, scrollEl.scrollTop, viewportPx, ROW_PX, rows.length);
		if (to !== null) scrollEl.scrollTop = to;
	});

	function onscroll(e: Event) {
		scrollTop = (e.currentTarget as HTMLDivElement).scrollTop;
	}

	/**
	 * The hover text, which is where the row says what kind of claim it is making.
	 *
	 * A documented call cites sources and names a function; a fitted one does neither, and
	 * saying so on the row is cheaper than expecting every reader to have read the legend.
	 */
	function rowTitle(row: InventoryRow): string {
		const what = row.fitted
			? `fitted from ${row.members ?? 0} field syllables — the name describes its waveform, not its meaning: no source has said what this call is for`
			: `documented — “${row.name}” is the name the literature gives this call${row.refs ? `, from ${row.refs} cited source${row.refs === 1 ? '' : 's'}` : ''}`;
		const where =
			row.knot < 0
				? 'It has no knot in this build, so it lights nothing when it sounds.'
				: 'Click to go to its knot.';
		return `${row.common} · ${row.syllableId}\n${what}.\n${where}`;
	}
</script>

<div class="tablewrap">
	<div class="thead mono" aria-hidden="true">
		<span class="c-bird">bird</span>
		<span class="c-type">id</span>
		<!-- `src`, not `source`: the column is 2.4rem because its values are three letters,
		     and the longer heading was clipped to `sourc`. -->
		<span class="c-src">src</span>
		<span class="c-label">sound</span>
		<span class="c-num">Hz</span>
		<span class="c-num">ms</span>
		<span class="c-num">fit</span>
		<span class="c-num">from</span>
		<span class="c-knot">knot</span>
	</div>
	<!--
		`onscroll` rather than an IntersectionObserver: the offset IS the state the window
		is computed from, so observing sentinels would be a second source of truth for it.
	-->
	<div
		class="tbody"
		bind:this={scrollEl}
		bind:clientHeight={viewportPx}
		{onscroll}
		role="grid"
		aria-rowcount={rows.length}
		aria-label="The learned inventory, one row per syllable type"
		tabindex="-1"
	>
		{#if !rows.length}
			<p class="empty">
				The inventory is still loading. Every bird arrives at once when the whole-corpus
				chorus starts, so this fills as soon as something sings.
			</p>
		{:else}
			<div style:height={`${view.padTop}px`}></div>
			{#each slice as row, i (row.key)}
				{@const index = view.first + i}
				<!--
					`aria-rowindex` on a wrapping row, and it is the one piece of ARIA this table
					genuinely needs: only about forty rows exist in the DOM at a time, so without
					it a screen reader is told the list is forty long and the position of every
					row in it is wrong. Announcing the true index costs one div per *drawn* row,
					not per row in the corpus.

					The cell is a button because this is the one place in the app where a type can
					be reached by name rather than by hearing it, so it has to be
					keyboard-reachable.
				-->
				<div class="rowwrap" role="row" aria-rowindex={index + 1}>
					<button
						class="trow mono"
						role="gridcell"
						class:on={index === active}
						class:fitted={row.fitted}
						class:noknot={row.knot < 0}
						aria-current={index === active ? 'true' : undefined}
						title={rowTitle(row)}
						onclick={() => onpick?.(row)}
					>
						<span class="c-bird">
							<span class="dot" style:background={colourOf?.(row.speciesId) ?? 'var(--ink-faint)'}
							></span>
							<span class="ellipsis">{row.common}</span>
						</span>
						<!-- Ellipsised, because a documented id is the source's own word for the call
						     and some of those are long: `hawkPerched` used to run straight over the
						     column beside it. -->
						<span class="c-type ellipsis">{row.syllableId}</span>
						<!--
							The distinction the ids were carrying on their own, said out loud. A reader
							seeing `jar` next to `L33` has no way to know that the first is a name from
							the literature and the second is a serial number.
						-->
						<span class="c-src">{row.fitted ? 'fit' : 'doc'}</span>
						<span class="c-label ellipsis">{row.name}</span>
						<span class="c-num">{row.hz || ''}</span>
						<span class="c-num">{row.durMs}</span>
						<!-- Blank, not a dash and not a zero: a documented call was never fitted, so
						     it has no fit to report and any number here would be an invention. -->
						<span class="c-num">{row.cosine != null ? row.cosine.toFixed(2) : ''}</span>
						<span class="c-num">{row.members ?? ''}</span>
						<span class="c-knot">{row.knot >= 0 ? row.knot : 'none'}</span>
					</button>
				</div>
			{/each}
			<div style:height={`${view.padBottom}px`}></div>
		{/if}
	</div>
</div>

<style>
	.tablewrap {
		display: flex;
		flex-direction: column;
		min-height: 0;
		flex: 1;
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		background: var(--paper-raised);
	}

	/* One grid template for the header and every row, so the two cannot disagree.
	   The id column is 7rem because the documented ids are the sources' own words for a
	   call and run to `hawkSearching`; at 3.2rem that ran over the column beside it. */
	.thead,
	.trow {
		display: grid;
		grid-template-columns:
			minmax(6rem, 1.2fr) 7rem 2.4rem minmax(8rem, 1.5fr)
			3.2rem 3.2rem 2.6rem 3rem 3.4rem;
		align-items: center;
		gap: 0.5rem;
		padding: 0 0.6rem;
		font-size: 0.72rem;
	}

	.thead {
		height: 22px;
		color: var(--ink-faint);
		border-bottom: 1px solid var(--rule);
		text-transform: lowercase;
		letter-spacing: 0.04em;
	}

	.tbody {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		overflow-x: hidden;
	}

	/* The wrapper carries the height so the row's own box cannot disagree with it. */
	.rowwrap {
		height: 24px;
	}

	.trow {
		/* Fixed, and the same number as ROW_PX above. A row that grew to fit its content
		   would put every row below it somewhere the window arithmetic does not expect. */
		height: 24px;
		width: 100%;
		border: 0;
		border-radius: 0;
		background: none;
		color: var(--ink-dim);
		text-align: left;
	}

	.trow:hover {
		background: var(--signal-soft);
		color: var(--ink);
	}

	/* Fitted from field audio. Documented calls are the quieter of the two here because
	   the numbers in the fit columns are the reason to open this table at all. */
	.trow.fitted {
		color: var(--ink);
	}

	.trow.on {
		background: var(--signal);
		color: var(--paper-raised);
	}

	.trow.on .c-knot,
	.trow.on .c-num {
		color: inherit;
	}

	/* A type with no knot sings and lights nothing. This is the only place that says so. */
	.trow.noknot .c-knot {
		color: var(--invented);
	}

	.c-bird {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		min-width: 0;
	}

	.dot {
		flex: none;
		width: 6px;
		height: 6px;
		border-radius: 50%;
	}

	.ellipsis {
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}

	.c-num,
	.c-knot {
		text-align: right;
		color: var(--ink-faint);
	}

	/* `doc` and `fit` are the two kinds of claim in the corpus, and they get the two colours
	   the app already spends on exactly that distinction — the same ones the provenance mode
	   paints the cloud in, so the word and the points agree. */
	.c-src {
		font-size: 0.62rem;
		letter-spacing: 0.06em;
		color: var(--documented);
	}

	.trow.fitted .c-src {
		color: var(--inferred);
	}

	.trow.on .c-src {
		color: inherit;
	}

	/* `.note`/`.faint` live in the page's scoped styles and do not reach a component, so
	   the one paragraph in here carries its own. */
	.empty {
		margin: 0;
		padding: 1rem;
		max-width: 34rem;
		font-size: 0.8rem;
		line-height: 1.5;
		color: var(--ink-faint);
	}
</style>
