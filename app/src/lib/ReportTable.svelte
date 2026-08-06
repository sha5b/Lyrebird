<script lang="ts">
	/**
	 * A pipeline report as a table, in the inventory table's idiom.
	 *
	 * Sixteen pipeline verbs write a JSON report and, until now, every one of them was
	 * only readable by opening the file. The measurement was the point of running them,
	 * so a control surface that runs them and does not show what they measured is a
	 * button with no readout — the same failure the chorus counts had.
	 *
	 * **Generic on purpose, and it is the server that decides the columns.** Each verb's
	 * report has a different shape, and the alternative to one table driven by a column
	 * spec is sixteen bespoke tables that drift from sixteen report formats. The spec
	 * travels with the data (`verbs.py` declares it, the server fills it), so a report
	 * whose fields move takes its table with it rather than leaving a column of blanks.
	 *
	 * Not windowed, unlike `InventoryTable`: these are tens of rows, and the server caps
	 * how many it sends. The cap is stated rather than hidden — a table that silently
	 * showed the first forty of four thousand would read as the whole measurement.
	 */
	import type { ReportTable } from '$lib/data/pipeline';

	interface Props {
		table: ReportTable;
		/** Shown above the rows when the report has something to say in words. */
		caption?: string;
	}

	let { table, caption }: Props = $props();

	const columns = $derived(table.columns ?? []);
	const rows = $derived(table.rows ?? []);

	/**
	 * The grid template, built from the column spec so the header and every row are laid
	 * out by one string and cannot disagree — the same reason `InventoryTable` keeps one
	 * template for both. A column with no declared width gets a flexible track with a
	 * floor, because a numeric column at `1fr` collapses to its digits when a text column
	 * beside it is long.
	 */
	const template = $derived(
		columns
			.map((c) => c.width ?? (c.kind === 'text' ? 'minmax(5rem, 1fr)' : '4.2rem'))
			.join(' ')
	);

	/**
	 * How a cell prints, which is where the units live.
	 *
	 * `null` and `undefined` render blank rather than as `0` or `—`: a report that did not
	 * measure something and a report that measured zero are different claims, and this is
	 * the layer that would erase the difference. `pct` multiplies, because every share in
	 * these reports is stored as a fraction and printing `0.4574` under a heading of `%`
	 * is how a figure gets quoted wrong.
	 */
	function cell(value: unknown, kind: string, digits?: number): string {
		if (value === null || value === undefined || value === '') return '';
		if (kind === 'pct') {
			const n = Number(value);
			return Number.isFinite(n) ? `${(n * 100).toFixed(digits ?? 1)}%` : '';
		}
		if (kind === 'num') {
			const n = Number(value);
			if (!Number.isFinite(n)) return String(value);
			// Integers keep their thousands separators and no false precision; a fitted
			// figure prints the digits the report declared it has.
			return digits === undefined || digits === null
				? Number.isInteger(n)
					? n.toLocaleString()
					: String(n)
				: n.toFixed(digits);
		}
		return String(value);
	}
</script>

{#if !columns.length}
	<p class="empty note faint">
		This report has no table declared, so there is nothing here to lay out in columns.
		The job log is what it wrote.
	</p>
{:else if !rows.length}
	<p class="empty note faint">
		Not measured yet. Running this writes
		<span class="mono">{table.path ?? 'its report'}</span>, and the numbers appear here.
	</p>
{:else}
	{#if caption}
		<p class="cap note faint">{caption}</p>
	{/if}
	<div class="tablewrap">
		<div class="thead mono" style:grid-template-columns={template} aria-hidden="true">
			{#each columns as c (c.key)}
				<span class:num={c.kind === 'num' || c.kind === 'pct'} title={c.title}>{c.label}</span>
			{/each}
		</div>
		<div
			class="tbody"
			role="grid"
			aria-rowcount={table.truncated?.total ?? rows.length}
			aria-label={caption ?? 'A pipeline measurement'}
		>
			{#each rows as row, i (i)}
				<div
					class="trow mono"
					role="row"
					aria-rowindex={i + 1}
					class:flagged={row.__flag === 'warn'}
					title={typeof row.__title === 'string' ? row.__title : undefined}
				>
					{#each columns as c (c.key)}
						<span
							role="gridcell"
							class:num={c.kind === 'num' || c.kind === 'pct'}
							class:chip={c.kind === 'chip'}
							class="ellipsis"
						>
							{cell(row[c.key], c.kind, c.digits)}
						</span>
					{/each}
				</div>
			{/each}
		</div>
	</div>
	<!--
		The cap, said out loud. A report of four thousand types reduced to forty rows is
		still a useful reading, but only if the reader knows which forty they have — so the
		count and the file that holds the rest are both named.
	-->
	{#if table.truncated && table.truncated.total > table.truncated.shown}
		<p class="note faint">
			Showing <b class="mono">{table.truncated.shown.toLocaleString()}</b> of
			<b class="mono">{table.truncated.total.toLocaleString()}</b> rows.
			{#if table.path}
				All of them are in <span class="mono">{table.path}</span>.
			{/if}
		</p>
	{:else if table.path}
		<p class="note faint">
			Written to <span class="mono">{table.path}</span>.
		</p>
	{/if}
{/if}

<style>
	.tablewrap {
		display: flex;
		flex-direction: column;
		min-height: 0;
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		background: var(--paper-raised);
		overflow: hidden;
	}

	/* One template string for the header and every row, set inline from the column spec.
	   The two cannot disagree because there is only one of them. */
	.thead,
	.trow {
		display: grid;
		align-items: center;
		gap: 0.5rem;
		padding: 0 0.6rem;
		font-size: 0.68rem;
	}

	.thead {
		height: 20px;
		color: var(--ink-faint);
		border-bottom: 1px solid var(--rule);
		text-transform: lowercase;
		letter-spacing: 0.04em;
	}

	.tbody {
		max-height: 15rem;
		overflow-y: auto;
		overflow-x: hidden;
	}

	.trow {
		min-height: 20px;
		color: var(--ink-dim);
	}

	.trow:nth-child(even) {
		background: color-mix(in srgb, var(--ink) 2.5%, transparent);
	}

	/* A row the report itself flagged — a type that regressed, a check that failed. The
	   report decides; this only draws it, because "which rows are bad" is a claim the
	   measurement makes and not one a table should invent. */
	.trow.flagged {
		color: var(--invented);
	}

	.num {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}

	.thead .num {
		text-align: right;
	}

	.chip {
		font-size: 0.6rem;
		letter-spacing: 0.05em;
		color: var(--inferred);
	}

	.ellipsis {
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}

	.cap {
		margin: 0 0 0.4rem;
	}

	/* `.note`/`.faint` are the page's scoped styles and do not reach a component. */
	.empty,
	.cap {
		font-size: 0.72rem;
		line-height: 1.5;
		color: var(--ink-faint);
	}

	.empty {
		margin: 0;
	}
</style>
