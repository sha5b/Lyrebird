<script lang="ts">
	/**
	 * The species chooser, as a search box with a list under it rather than a native
	 * `<select>`.
	 *
	 * A native select cannot search, cannot mark an entry, and styles its drop-down
	 * however the OS feels like. All three matter here: the corpus is long enough that
	 * scrolling it is the slow way to find a bird, a species the learning loop discovered
	 * has to be marked next to the documented ones, and the popover should look like the
	 * panel it hangs from.
	 */
	interface Option {
		id: string;
		common: string;
		/** Found by the learning loop rather than documented — marked, never hidden. */
		discovered?: boolean;
	}

	interface Props {
		options: Option[];
		value: string;
		/** The entry that means "no narrowing", always first in the list. */
		allLabel?: string;
		onchange?: (id: string) => void;
	}

	let { options, value = $bindable(''), allLabel = 'all birds', onchange }: Props = $props();

	let open = $state(false);
	let query = $state('');
	let searchEl: HTMLInputElement | undefined = $state(undefined);

	const current = $derived(options.find((o) => o.id === value) ?? null);
	const filtered = $derived.by(() => {
		const q = query.trim().toLowerCase();
		if (!q) return options;
		return options.filter((o) => o.common.toLowerCase().includes(q));
	});

	function choose(id: string) {
		value = id;
		onchange?.(id);
		close();
	}

	function toggle() {
		open = !open;
		query = '';
		if (open) requestAnimationFrame(() => searchEl?.focus());
	}

	function close() {
		open = false;
		query = '';
	}

	function onkeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			close();
		} else if (e.key === 'Enter' && filtered.length) {
			// The search has already said which bird is meant; Enter just confirms it.
			choose(filtered[0].id);
		}
	}
</script>

<div class="picker" class:open>
	<button
		type="button"
		class="picker-btn"
		aria-expanded={open}
		aria-haspopup="listbox"
		onclick={toggle}
	>
		<span class="picker-current" class:all={!current}>{current?.common ?? allLabel}</span>
		{#if current?.discovered}
			<span class="disc-dot"></span>
		{/if}
		<span class="chevron" aria-hidden="true"></span>
	</button>
	{#if open}
		<!-- one click past the popover closes it, the same as clicking its button again -->
		<button class="picker-backdrop" aria-label="Close" tabindex="-1" onclick={close}></button>
		<div class="picker-pop">
			<input
				bind:this={searchEl}
				bind:value={query}
				class="picker-search"
				type="text"
				placeholder="search species…"
				{onkeydown}
			/>
			<ul class="picker-list" role="listbox">
				<li>
					<button
						type="button"
						role="option"
						aria-selected={value === ''}
						class:on={value === ''}
						onclick={() => choose('')}
					>
						<span class="picker-name all">{allLabel}</span>
					</button>
				</li>
				{#each filtered as o (o.id)}
					<li>
						<button
							type="button"
							role="option"
							aria-selected={value === o.id}
							class:on={value === o.id}
							onclick={() => choose(o.id)}
						>
							<span class="picker-name">{o.common}</span>
							{#if o.discovered}<span class="disc-dot"></span>{/if}
						</button>
					</li>
				{:else}
					<li class="picker-empty">no bird matches “{query.trim()}”</li>
				{/each}
			</ul>
		</div>
	{/if}
</div>

<style>
	.picker {
		position: relative;
	}

	/* Same box the native select drew, so swapping it in changes nothing around it. */
	.picker-btn {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		width: 100%;
		padding: 0.35rem 0.45rem;
		color: var(--ink);
		text-align: left;
	}

	.picker.open .picker-btn {
		border-color: var(--signal);
	}

	.picker-current {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}

	.picker-current.all,
	.picker-name.all {
		color: var(--ink-dim);
	}

	.chevron {
		flex: none;
		width: 0;
		height: 0;
		border: 4px solid transparent;
		border-top-color: var(--ink-faint);
		transform: translateY(2px);
	}

	.picker.open .chevron {
		border-top-color: var(--signal);
	}

	.picker-backdrop {
		position: fixed;
		inset: 0;
		z-index: 8;
		padding: 0;
		background: none;
		border: none;
		border-radius: 0;
		cursor: default;
	}

	.picker-pop {
		position: absolute;
		top: calc(100% + 4px);
		left: 0;
		right: 0;
		z-index: 9;
		display: grid;
		gap: 0.3rem;
		padding: 0.4rem;
		background: var(--paper-raised);
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
	}

	.picker-search {
		padding: 0.3rem 0.4rem;
		font-size: 0.76rem;
	}

	.picker-search:focus-visible {
		outline: 2px solid var(--signal);
		outline-offset: -1px;
		border-color: var(--signal);
	}

	.picker-list {
		margin: 0;
		padding: 0;
		list-style: none;
		max-height: 15rem;
		overflow-y: auto;
	}

	.picker-list button {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		width: 100%;
		padding: 0.3rem 0.4rem;
		background: none;
		border: none;
		border-radius: 2px;
		text-align: left;
		font-size: 0.78rem;
		color: var(--ink);
	}

	.picker-list button:hover {
		background: var(--paper);
		color: var(--ink);
	}

	.picker-list button.on {
		background: var(--signal-soft);
		color: var(--signal);
	}

	.picker-name {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}

	.picker-empty {
		padding: 0.4rem;
		font-size: 0.72rem;
		color: var(--ink-faint);
	}

	/* The one mark a discovered bird carries everywhere it is listed. */
	.disc-dot {
		flex: none;
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--invented);
	}
</style>
