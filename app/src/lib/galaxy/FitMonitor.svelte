<script lang="ts">
	/**
	 * A window inside the window: what the fit is trying, and where it is failing, live.
	 *
	 * Learning is the one part of Birdy that happens on a timescale a person can watch and
	 * was the one part with nothing to watch. The Learn tab streamed a log, which says which
	 * step is running and, two or three seconds per species later, one summary line — so the
	 * question you actually have while it runs ("is this working?") was answered only after
	 * it had stopped mattering.
	 *
	 * What it draws is the comparison the whole exercise turns on. A fitted voice is worth
	 * shipping if it resembles the call it was fitted to *more than it resembles a different
	 * call by the same bird*, and both numbers arrive together per type. So each row is one
	 * bar — how close the resynthesis landed — with a rule drawn at the best rival. When the
	 * rule sits inside the fill the fit held its own; when it sits past the end, the
	 * oscillator has produced something that sounds more like another of this bird's calls
	 * than like the one it was asked for, and that row is marked lost. On the current harvest
	 * about half of them are, which is the honest state of the model and not a bug to hide:
	 * a cosine of 0.55 against its own type and 0.53 against a rival is a fit that reached
	 * the pitch and missed the timbre, and seeing forty of those in a row is the clearest
	 * available statement of what a two-parameter oscillator cannot do.
	 *
	 * Parsed out of the job log rather than fed by a second channel. `learn` prints one
	 * `FIT` line per type as it lands, the log is already streamed and already polled, and a
	 * parallel protocol would be one more thing that can disagree with the log a reader is
	 * looking at.
	 */
	interface Fit {
		species: string;
		id: string;
		f0: number;
		dur: number;
		cos: number;
		rival: number;
		own: boolean;
		f0err: number;
		members: number;
	}

	interface Props {
		/** The running job's log, newest last — exactly as the control process reports it. */
		log: string[];
		/** Hidden entirely when no fit is running and nothing has been fitted yet. */
		show?: boolean;
		/** What the job is called, for the heading. */
		jobName?: string;
		/** The line the pipeline printed most recently, when it is not a `FIT` line. */
		doing?: string;
		/**
		 * Whether a job is running at all, so a build can report progress here too.
		 *
		 * A build emits no `FIT` lines — it is a global re-fit, not a per-type search — so this
		 * panel used to sit empty for the two minutes it takes and got gated off entirely. Empty
		 * was the right call; *absent* is not, because a rebuild is the longest thing the
		 * pipeline does and the picture it will replace looks identical until the moment it
		 * changes. What can honestly be shown is the phase and, where the log carries a counter,
		 * how far through that phase it is. Not arriving nodes: during a build every point moves
		 * and none of the intermediate positions exist.
		 */
		running?: boolean;
		/** Common name lookup, so a row names a bird rather than a genus id. */
		commonOf?: (speciesId: string) => string;
		onclose?: () => void;
	}

	let {
		log,
		show = true,
		jobName = '',
		doing = '',
		running = false,
		commonOf,
		onclose
	}: Props = $props();

	/** `  descriptors 1200/4224` and friends — the only counters the build log carries. */
	const PROGRESS = /(\d+)\s*\/\s*(\d+)/;
	const progress = $derived.by(() => {
		const m = PROGRESS.exec(doing ?? '');
		if (!m) return null;
		const done = Number(m[1]);
		const total = Number(m[2]);
		if (!total || done > total) return null;
		return { done, total, share: done / total };
	});

	const FIT_LINE =
		/^\s*FIT (\S+) (\S+) f0=([\d.]+) dur=([\d.]+) cos=(-?[\d.]+) rival=(-?[\d.]+) own=([01]) f0err=([\d.]+) members=(\d+)/;

	/** Newest first, because the interesting one is the one that just happened. */
	const fits = $derived.by(() => {
		const out: Fit[] = [];
		for (let i = log.length - 1; i >= 0 && out.length < 40; i--) {
			const m = FIT_LINE.exec(log[i]);
			if (!m) continue;
			out.push({
				species: m[1],
				id: m[2],
				f0: Number(m[3]),
				dur: Number(m[4]),
				cos: Number(m[5]),
				rival: Number(m[6]),
				own: m[7] === '1',
				f0err: Number(m[8]),
				members: Number(m[9])
			});
		}
		return out;
	});

	const lost = $derived(fits.filter((f) => !f.own).length);
	/** The bird the newest row belongs to: what the fit is working on right now. */
	const current = $derived(fits.length ? (commonOf?.(fits[0].species) ?? fits[0].species) : '');

	/** Bars are drawn against 1.0 but never reach it, so the useful range is stretched. */
	const FLOOR = 0.2;
	function pct(v: number): number {
		return Math.max(0, Math.min(100, ((v - FLOOR) / (1 - FLOOR)) * 100));
	}
</script>

{#if show}
	<div class="pip">
		<div class="head">
			<!-- The separators are inside the expression because Svelte trims the leading
			     whitespace of a text node, which turned "loop · Siberian jay" into "loop·". -->
			<span class="what">{jobName || 'fitting'}{current ? ` · ${current}` : ''}</span>
			{#if fits.length}
				<span class="tally mono">
					{fits.length} types{#if lost}<span class="warn">{` · ${lost} lost`}</span>{/if}
				</span>
			{:else if progress}
				<!-- The counter itself, since the bar below has no numbers on it. -->
				<span class="tally mono">{progress.done}/{progress.total}</span>
			{/if}
			{#if onclose}
				<button class="x" onclick={onclose} aria-label="Hide the fit monitor">×</button>
			{/if}
		</div>

		{#if fits.length}
			<div class="rows">
				{#each fits as f (f.species + f.id + f.cos)}
					<div class="row" class:lost={!f.own}>
						<span class="id mono">{f.id}</span>
						<span class="spec mono">{f.f0.toFixed(0)}Hz · {f.dur.toFixed(0)}ms</span>
						<span
							class="bar"
							style="--fill: {pct(f.cos)}%; --rival: {pct(f.rival)}%"
							title="resynthesis {f.cos.toFixed(3)} vs best rival {f.rival.toFixed(3)}"
						>
							<span class="fill"></span>
							<span class="rule"></span>
						</span>
						<span class="num mono">{f.cos.toFixed(2)}</span>
						<span class="err mono">{f.f0err.toFixed(1)}%</span>
					</div>
				{/each}
			</div>
			<p class="legend">
				Bar is how close the resynthesis landed to the call it was fitted to; the rule is
				its best rival. Rule past the fill means it sounds more like another of this
				bird's calls — the fit reached the pitch and missed the timbre.
			</p>
		{:else if running}
			<p class="waiting mono">{doing || 'starting…'}</p>
			{#if progress}
				<span class="progress" style="--share: {(progress.share * 100).toFixed(1)}%">
					<span class="progressfill"></span>
				</span>
			{/if}
		{/if}
	</div>
{/if}

<style>
	/* Built out of the same parts as a node tag — hairline rule down the left, paper showing
	   through, monospaced metadata — because two overlays made of the same parts read as one
	   system and two made of different parts read as two things sharing a screen. */
	.pip {
		position: absolute;
		left: 1rem;
		bottom: 3.4rem;
		z-index: 3;
		width: min(24rem, calc(100vw - 2rem));
		display: grid;
		gap: 0.3rem;
		padding: 0.5rem 0.6rem 0.45rem;
		background: color-mix(in srgb, var(--paper) 94%, transparent);
		border: 1px solid var(--rule);
		border-left: 2px solid var(--signal);
		backdrop-filter: blur(3px);
	}

	.head {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
	}

	.what {
		font-size: 0.72rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.11em;
		color: var(--ink);
	}

	.tally {
		font-size: 0.58rem;
		color: var(--ink-faint);
		margin-left: auto;
	}

	.warn {
		color: var(--invented);
	}

	.x {
		border: 0;
		background: none;
		cursor: pointer;
		padding: 0 0.1rem;
		font-size: 0.9rem;
		line-height: 1;
		color: var(--ink-faint);
	}

	.x:hover {
		color: var(--ink);
	}

	/* Capped and scrolling: a loop fits a hundred types and the panel is a window onto the
	   newest, not a transcript. */
	.rows {
		display: grid;
		gap: 0.12rem;
		max-height: 13rem;
		overflow-y: auto;
	}

	.row {
		display: grid;
		grid-template-columns: 2.6rem 6.6rem 1fr 1.9rem 2.4rem;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.6rem;
	}

	.id {
		color: var(--ink);
	}

	.spec,
	.num,
	.err {
		color: var(--ink-faint);
	}

	.num {
		text-align: right;
	}

	.err {
		text-align: right;
		font-size: 0.55rem;
	}

	.bar {
		position: relative;
		display: block;
		height: 0.42rem;
		background: color-mix(in srgb, var(--rule) 55%, transparent);
	}

	.fill {
		position: absolute;
		inset: 0 auto 0 0;
		width: var(--fill);
		background: color-mix(in srgb, var(--signal) 72%, transparent);
	}

	/* The comparison, not a decoration: everything left of it the fit won. */
	.rule {
		position: absolute;
		top: -1px;
		bottom: -1px;
		left: var(--rival);
		width: 1px;
		background: var(--ink);
	}

	.row.lost .fill {
		background: color-mix(in srgb, var(--invented) 60%, transparent);
	}

	.row.lost .rule {
		background: var(--invented);
		width: 2px;
	}

	.row.lost .id {
		color: var(--invented);
	}

	/* One bar, because the build log's counters are the only honest measure of how far it has
	   got — phases have no comparable duration and a spinner would be a guess. */
	.progress {
		position: relative;
		display: block;
		height: 0.35rem;
		background: color-mix(in srgb, var(--rule) 55%, transparent);
	}

	.progressfill {
		position: absolute;
		inset: 0 auto 0 0;
		width: var(--share);
		background: color-mix(in srgb, var(--signal) 72%, transparent);
		transition: width 240ms linear;
	}

	.legend,
	.waiting {
		margin: 0;
		font-size: 0.55rem;
		line-height: 1.35;
		color: var(--ink-faint);
	}
</style>
