<script lang="ts">
	/**
	 * Everything the pipeline can do that is not harvest, fit or build — and what it found.
	 *
	 * The Learn tab drove eight of `lyrebird-pipeline`'s twenty-two subcommands. The other
	 * fourteen are where this project's measurements live: whether a resynthesis lands
	 * nearest its own species (`placement`), whether a cosine gain is an audible gain
	 * (`specbench`), whether the browser's space map reproduces the critic's embedding
	 * (`spacemap`), whether the shipped grammar beats an HMM (`syntax`). Every one of them
	 * was reachable only from a terminal, so this page could print a cosine and could not
	 * print whether that cosine meant anything.
	 *
	 * **The form is drawn from the server's registry, not written here.** `verbs.py`
	 * declares each verb's flags, ranges, preconditions and cost, and this component
	 * renders whatever it is told. Sixteen hand-written forms would be sixteen chances for
	 * a control to fall behind the flag it drives — the failure that left a probe watching
	 * for a `<select>` that had become a combobox, reporting vacuous passes for weeks. A
	 * flag that moves in the pipeline moves here on the next fetch, or the server refuses
	 * to start.
	 *
	 * **Grouped by what a press changes, not by what it is about.** A measurement writes a
	 * report and nothing else; a corpus verb changes what everything downstream is fitted
	 * to. That is the only distinction on this page a reader cannot undo by pressing
	 * something else, so it is the one the layout carries.
	 */
	import ReportTable from '$lib/ReportTable.svelte';
	import type {
		JobStatus,
		PipelineClient,
		VerbReport,
		VerbSpec
	} from '$lib/data/pipeline';

	interface Props {
		pipeline: PipelineClient;
		job: JobStatus | null | undefined;
		jobRunning: boolean;
		pipelineBusy: boolean;
		/** Runs a pipeline call with the busy flag and the error path around it. */
		runPipeline: (fn: () => Promise<unknown>) => Promise<void>;
	}

	let { pipeline, job, jobRunning, pipelineBusy, runPipeline }: Props = $props();

	let groups = $state<{ id: string; title: string; note: string }[]>([]);
	let verbs = $state<VerbSpec[]>([]);
	let reports = $state<VerbReport[]>([]);
	/** Null until the first fetch settles, so "none" and "not asked yet" stay distinct. */
	let loaded = $state(false);
	/** Set when the running process is too old to have the routes — the usual first case. */
	let unsupported = $state(false);
	/** Chosen parameter values, per verb id. Absent keys mean "the declared default". */
	let chosen = $state<Record<string, Record<string, number | string | boolean>>>({});

	const reportOf = $derived(new Map(reports.map((r) => [r.verb, r])));

	async function loadRegistry() {
		const registry = await pipeline.verbs();
		if (registry === null) {
			unsupported = true;
			loaded = true;
			return;
		}
		unsupported = false;
		groups = registry.groups;
		verbs = registry.verbs;
		const specs = await pipeline.reports();
		if (specs) reports = specs;
		loaded = true;
	}

	/**
	 * The registry once, the reports again after every job.
	 *
	 * Keyed on the job's *identity and state* rather than on the job object: the status
	 * poll replaces `job` every 1.5 s while one is running, and refetching every report on
	 * each of those would put a file read per verb behind a timer. A report can only have
	 * changed when a run ended.
	 *
	 * `lastSettled` is deliberately not `$state`: it is written by the effect that reads
	 * it, so tracking it would make that effect re-run itself once for every fetch it
	 * kicks off. It is bookkeeping local to the effect, not state anything renders.
	 */
	let lastSettled = '';

	$effect(() => {
		loadRegistry();
	});

	$effect(() => {
		const done = job && job.state !== 'running' && job.state !== 'stopping';
		const key = done ? `${job.name}/${job.state}/${job.seconds}` : '';
		if (!key || key === lastSettled) return;
		lastSettled = key;
		pipeline.reports().then((specs) => {
			if (specs) reports = specs;
		});
	});

	function valueOf(verb: VerbSpec, name: string): number | string | boolean {
		const held = chosen[verb.id]?.[name];
		if (held !== undefined) return held;
		const declared = verb.params.find((p) => p.name === name);
		return (declared?.default ?? '') as number | string | boolean;
	}

	function set(verb: VerbSpec, name: string, value: number | string | boolean) {
		chosen[verb.id] = { ...(chosen[verb.id] ?? {}), [name]: value };
	}

	/** Only what the reader actually moved. The server fills in every default it declared. */
	function payload(verb: VerbSpec) {
		return chosen[verb.id] ?? {};
	}

	const blocked = (verb: VerbSpec) => verb.needs.filter((n) => !n.ok);

	/**
	 * The one number a slider shows beside its label.
	 *
	 * Floats print at the step's own precision rather than at a fixed two places: a ship
	 * margin steps by 0.005 and a learning rate by 0.0001, and rounding either to the
	 * other's precision would show a control that appears not to move.
	 */
	function shown(value: number | string | boolean, step?: number): string {
		if (typeof value !== 'number') return String(value);
		if (Number.isInteger(value) && (step ?? 1) >= 1) return value.toLocaleString();
		const places = step ? Math.max(0, Math.ceil(-Math.log10(step))) : 3;
		return value.toFixed(places);
	}
</script>

{#if unsupported}
	<section class="block">
		<h3 class="blocktitle">Measure and train</h3>
		<p class="note">
			This control process was started before these routes existed. Restart it and the
			twenty other pipeline verbs — the measurements, the training, the checks — appear
			here.
		</p>
		<pre class="mono">cd pipeline
uv run lyrebird-pipeline serve</pre>
	</section>
{:else if loaded && verbs.length}
	{#each groups as group (group.id)}
		{@const members = verbs.filter((v) => v.group === group.id)}
		{#if members.length}
			<section class="block">
				<h3 class="blocktitle">{group.title}</h3>
				<p class="note faint">{group.note}</p>
				{#each members as verb (verb.id)}
					{@const stops = blocked(verb)}
					{@const report = reportOf.get(verb.id)}
					{@const mine = job?.name === verb.id}
					<details class="verb" class:live={mine && jobRunning}>
						<summary>
							<span class="vtitle">{verb.title}</span>
							<span class="mono faint vcmd">{verb.command}</span>
							{#if mine && jobRunning}
								<span class="chip running">running</span>
							{:else if mine && job?.state === 'failed'}
								<span class="chip bad">failed</span>
							{:else if mine && job?.state === 'done'}
								<span class="chip good">done</span>
							{:else if report?.exists}
								<span class="chip good" title="Its report is on disk">measured</span>
							{:else if stops.length}
								<span class="chip" title={stops.map((n) => n.what).join('; ')}>needs more</span
								>
							{/if}
						</summary>

						<p class="note measures">{verb.measures}</p>

						<!--
							What a press changes, on the control's own surface. Empty `writes` is the
							common case here and it is worth stating rather than leaving blank: "writes
							nothing but its own report" is the reason most of these are safe to press,
							and a reader cannot infer it from silence.
						-->
						<p class="note faint writes" class:caution={verb.mutatesStore}>
							{#if verb.writes}
								<b>Writes:</b> {verb.writes}
							{:else}
								<b>Writes:</b> nothing but its own report.
							{/if}
						</p>
						{#if verb.mutatesStore}
							<p class="note caution">
								This rewrites a file inside the harvest store. Row <b class="mono">i</b> is
								the same syllable in the store, the typing and the shipped assets, and that
								is what every join between them keys on — so do not run this while an
								analysis is reading the store.
							</p>
						{/if}
						{#if verb.cost}
							<p class="note faint">Costs {verb.cost}.</p>
						{/if}

						{#if stops.length}
							<p class="note caution">
								Needs {stops.map((n) => n.what).join(', and ')}.
							</p>
						{/if}

						{#each verb.params.filter((p) => !p.advanced) as param (param.name)}
							{@render control(verb, param)}
						{/each}
						{#if verb.params.some((p) => p.advanced)}
							<details class="advanced">
								<summary class="note faint">
									the settings for reproducing one published run
								</summary>
								{#each verb.params.filter((p) => p.advanced) as param (param.name)}
									{@render control(verb, param)}
								{/each}
							</details>
						{/if}

						<button
							class="wide"
							disabled={jobRunning || pipelineBusy || stops.length > 0}
							title={stops.length
								? stops.map((n) => n.what).join('; ')
								: `Runs lyrebird-pipeline ${verb.command}. It cannot be interrupted — Stop takes effect only on the runs that check for it.`}
							onclick={() => runPipeline(() => pipeline.run(verb.id, payload(verb)))}
						>
							Run
						</button>

						<!--
							The measurement, which is the reason the button exists. Reports live on disk,
							so this is populated the moment the page opens rather than only for runs made
							in this session — a figure measured last week is still the current answer.
						-->
						{#if verb.report}
							<div class="result">
								{#if report?.ranAt}
									<p class="note faint">
										Measured <span class="mono">{report.ranAt.replace('T', ' ')}</span>.
									</p>
								{/if}
								<ReportTable
									table={report?.table ?? { columns: [], rows: [], path: verb.report }}
									caption={report?.headline ?? undefined}
								/>
							</div>
						{:else}
							<p class="note faint">
								This one prints its answer rather than writing a report, so the job log above
								is the readout.
							</p>
						{/if}
					</details>
				{/each}
			</section>
		{/if}
	{/each}
{/if}

<!--
	One control, drawn from its declaration. The kinds map onto the four controls this page
	already uses, so a verb's form looks like the harvest form rather than like a new thing.
-->
{#snippet control(verb: VerbSpec, param: VerbSpec['params'][number])}
	{#if param.kind === 'bool'}
		<label class="check" title={param.gloss}>
			<input
				type="checkbox"
				checked={Boolean(valueOf(verb, param.name))}
				onchange={(e) => set(verb, param.name, e.currentTarget.checked)}
			/>
			{param.label}
		</label>
	{:else if param.kind === 'choice'}
		<label class="field" title={param.gloss}>
			<span class="lbl">{param.label}</span>
			<select
				value={String(valueOf(verb, param.name))}
				onchange={(e) => set(verb, param.name, e.currentTarget.value)}
			>
				{#each param.choices ?? [] as c (c.value)}
					<option value={c.value}>{c.label}</option>
				{/each}
			</select>
		</label>
	{:else if param.kind === 'text'}
		<label class="field" title={param.gloss}>
			<span class="lbl">{param.label}</span>
			<input
				type="text"
				value={String(valueOf(verb, param.name))}
				onchange={(e) => set(verb, param.name, e.currentTarget.value)}
			/>
		</label>
	{:else}
		<label class="field" title={param.gloss}>
			<span class="lbl"
				>{param.label}
				<b class="mono">{shown(valueOf(verb, param.name), param.step)}</b></span
			>
			<input
				type="range"
				min={param.lo ?? 0}
				max={param.hi ?? 100}
				step={param.step ?? 1}
				value={Number(valueOf(verb, param.name))}
				oninput={(e) => set(verb, param.name, Number(e.currentTarget.value))}
			/>
		</label>
	{/if}
{/snippet}

<style>
	/* One verb, collapsed. Twenty of these expanded at once is a wall; the summary carries
	   the name, the command and the one chip that says whether it has ever been run, which
	   is what a reader scans for. */
	.verb {
		border-top: 1px solid var(--rule);
		padding: 0.5rem 0 0.65rem;
	}

	.verb summary {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
		cursor: pointer;
		font-size: 0.78rem;
		color: var(--ink);
	}

	.verb summary:hover {
		color: var(--signal);
	}

	.vtitle {
		flex: 1;
		min-width: 0;
	}

	/* The subcommand, so the terminal and this surface name the same thing. Hidden on a
	   narrow column rather than wrapped: it is a courtesy, not the label. */
	.vcmd {
		font-size: 0.6rem;
	}

	@media (max-width: 30rem) {
		.vcmd {
			display: none;
		}
	}

	.chip {
		flex: none;
		font-size: 0.58rem;
		letter-spacing: 0.05em;
		padding: 0.05rem 0.3rem;
		border-radius: 2px;
		color: var(--ink-faint);
		background: color-mix(in srgb, var(--ink) 6%, transparent);
	}

	.chip.good {
		color: var(--documented);
		background: color-mix(in srgb, var(--documented) 10%, transparent);
	}

	.chip.bad {
		color: var(--invented);
		background: color-mix(in srgb, var(--invented) 10%, transparent);
	}

	.chip.running {
		color: var(--signal);
		background: var(--signal-soft);
	}

	.verb.live > summary {
		animation: verb-breathe 1.6s ease-in-out infinite;
	}

	@keyframes verb-breathe {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0.55;
		}
	}

	.measures {
		margin-top: 0.4rem;
	}

	/* What a press changes. The caution colour is spent only where a press reaches a file
	   something else is keyed against — not on "this takes a while", which is a cost and
	   not a risk. */
	.writes {
		margin-top: 0.3rem;
	}

	.note.caution,
	.writes.caution {
		color: var(--invented);
	}

	.advanced {
		margin: 0.4rem 0;
	}

	.advanced > summary {
		cursor: pointer;
	}

	.result {
		margin-top: 0.6rem;
	}
</style>
