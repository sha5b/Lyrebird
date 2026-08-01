# NOTICE

This file is the scope statement for [`LICENSE`](LICENSE). Read the two together.

Lyrebird's own code and prose are licensed **CC BY-NC-SA 4.0**. This file says what
that covers, what it does not, and why the difference matters. Three categories are
kept apart on purpose, because they belong to three different sets of people:

1. **Lyrebird's own work** — ours to license, and licensed.
2. **Third-party dependencies and models** — theirs, under their own terms.
3. **The harvested recordings** — the recordists', under per-recording licences that
   we cannot change and must carry forward.

The rule for anyone extending this project: adding a dependency or an archive means
adding a row here. A licence nobody wrote down is a licence nobody can honour.

---

## 1. Lyrebird's own work

Copyright (c) 2026 the Lyrebird authors. Licensed CC BY-NC-SA 4.0.

| what | where |
|---|---|
| the offline pipeline | `pipeline/src/birdy_pipeline/`, `pipeline/analysis/` |
| the browser application | `app/src/`, `app/scripts/`, `app/*.ts` |
| the research record | `docs/*.md`, `README.md`, `AGENTS.md`, `HANDOFF.md` |
| the hand-authored inventory | `data/inventory.json` — our own reading of the cited literature |
| the syrinx implementation | `pipeline/src/birdy_pipeline/syrinx.py` and its JS mirror `app/src/lib/audio/worklets/syrinx-processor.js` |

The syrinx model itself is **published physics, not our invention**. The ODE is the
normal form of the Laje & Mindlin / Amador & Mindlin lineage, term for term
(`docs/21-syrinx-fidelity.md`, `docs/07-references.md`). Our implementation of it is
ours; the model is theirs and is cited, not licensed.

`app/src/routes/`, `app/src/app.html` and `app/src/app.css` began as the SvelteKit
`sv` scaffold (MIT, © the Svelte contributors) and have since been rewritten.

**Note on the package name.** The distribution is `birdy-pipeline` and the Python
package is `birdy_pipeline`. Those are identifiers, not the product name. The product
is Lyrebird. The identifiers were left alone deliberately — renaming them would break
the shipped asset contract at `app/static/birdy/`.

---

## 2. Third-party dependencies and models

None of the following is relicensed by `LICENSE`. All of it is a dependency rather
than a vendored copy: nothing in this list is redistributed from this repository, and
each is resolved at install time by `uv` or `npm`.

### 2.1 Python — required (`pipeline/pyproject.toml`)

| package | licence |
|---|---|
| numpy | BSD-3-Clause (with 0BSD, MIT, Zlib and CC0-1.0 components) |
| scipy (transitive) | BSD-3-Clause |
| numba | BSD-2-Clause |
| llvmlite (transitive) | BSD-2-Clause AND Apache-2.0 WITH LLVM-exception |
| umap-learn | BSD-3-Clause |
| scikit-learn | BSD-3-Clause |
| soundfile | BSD-3-Clause (wraps libsndfile, LGPL-2.1-or-later) |
| hatchling (build backend) | MIT |

`soundfile` is a binding to **libsndfile**, which is LGPL-2.1-or-later. The LGPL
attaches to libsndfile, not to callers of it, and libsndfile is not redistributed
from this repository.

### 2.2 Python — optional extras

| extra | package | licence | note |
|---|---|---|---|
| `critic` | torch | BSD-3-Clause | |
| `sources` | kaggle | Apache-2.0 | |
| `sources`, `perch` | huggingface_hub | Apache-2.0 | |
| `perch` | onnxruntime | MIT | |
| `perch` | kagglehub | Apache-2.0 | |
| `analysis` | **harmonypy** | **GPL-3.0-or-later** | see the warning below |
| `analysis` | pandas | BSD-3-Clause | |
| `whitepaper` | python-docx | MIT | |
| `whitepaper` | matplotlib | Matplotlib licence (BSD-style, PSF-derived) | |
| `whitepaper` | pillow | MIT-CMU (HPND) | |

> **`harmonypy` is GPL-3.0-or-later, and that is a real interaction with this
> project's own licence.** GPL-3.0 is copyleft and does not permit the addition of a
> NonCommercial restriction to the GPL'd work or to a combined work derived from it.
> `batcheffect.py` imports it lazily and the module's baseline arms run on numpy
> alone, so the extra is genuinely optional and nothing GPL'd is vendored here. What
> follows from that: this repository's own code stays CC BY-NC-SA, and **anyone who
> distributes a built environment containing both this code and harmonypy is
> distributing a combination whose terms need their own reading.** The `analysis`
> extra is a research tool for reproducing docs/23 W1; it is not part of the shipped
> app, and no result in this repository depends on redistributing it.

### 2.3 Browser — `app/package.json`

MIT unless stated: three, @threlte/core, @threlte/extras, meyda, pitchy, svelte,
@sveltejs/kit, @sveltejs/adapter-static, @sveltejs/adapter-auto,
@sveltejs/vite-plugin-svelte, vite, svelte-check, @types/node, @types/three.
**typescript is Apache-2.0.**

### 2.4 Models this project measures against or ports

Model weights are **never vendored into this repository and never shipped to the
browser** (`AGENTS.md`, hard constraints). They are fetched at run time into a user
cache. Their licences apply to the weights wherever they land.

| model | licence | how it is used here |
|---|---|---|
| **Perch / Perch 2.0** (Google) | Apache-2.0 | ONNX inference in `perch.py`; pseudo-labelling and the docs/23 W6 second opinion. Weights land in `~/.cache/huggingface`. |
| **BirdNET** (Cornell) | **CC BY-NC-SA** | compared against in docs/23 §23.6. Non-commercial, which this project already is — but this is why BirdNET must not be built into a commercial derivative. |
| **AVES / BirdAVES**, **avex** (Earth Species Project) | MIT | referenced in docs/03, docs/13; the AVEX arm of docs/17 §17.6. |
| **BirdMAE**, **NatureLM-audio**, **BioLingual** | per their own publications | referenced only. |
| **BEANS**, **BirdSet**, **DCASE Task 5** | per dataset; see §3 | benchmarks, referenced and in BirdSet's case fetched. |

Cited literature (`docs/07-references.md`) is under conventional academic copyright.
Our summaries of it are ours. The papers are not.

---

## 3. The harvested recordings — not ours to relicense

**This is the part that is easiest to get wrong, so it is stated at length.**

Every field recording this project reads was made by somebody else and released by
that person under a specific licence, one recording at a time. `LICENSE` does not
reach any of it. CC BY-NC-SA 4.0 in that file is a statement about *our* code and
prose, and it grants nothing over *their* recordings — a reader must not take the
project's NC/SA as though it had been applied to the corpus.

Two obligations travel with every recording, and with the descriptors, embeddings,
fitted syllables and galaxy positions derived from it:

- **the recording's own licence**, exactly as the archive reported it, and
- **the recordist's name.**

### 3.1 Where the attribution lives

`harvest.py` writes a `CREDITS.md` into each store: one row per recording, carrying
the id, species, recordist, licence and source URL. That file is the attribution
record, and it is written for every recording that contributes so much as a single
descriptor.

**Known gap, recorded rather than papered over:** the store lives under
`pipeline/out/`, which is gitignored, and the assets in `app/static/birdy/` carry no
recordist or licence field at all. So the shipped galaxy is derived from ~10 000
attributed recordings and ships none of the attribution. See
`docs/DOC-AUDIT-FINDINGS.md` — this is a finding, not a resolved question.

### 3.2 Archives, and the terms each one comes with

| archive | terms | adapter |
|---|---|---|
| **xeno-canto** | per-recording Creative Commons, chosen by the recordist. CC BY-NC-SA is the most common. Some recordings are CC BY-NC-**ND**. | `harvest.py` |
| **iNaturalist / iNatSounds 2024** (AWS Open Data) | per-observation Creative Commons. The adapter accepts CC0, BY, BY-NC, BY-NC-SA, BY-SA and **excludes NoDerivatives at ingest** (`sources.LICENCES_OK`, ids 2 and 5 refused — 531 of 111 029 Aves files). iNaturalist's own terms forbid redistribution of the archive. | `sources.py` |
| **Internet Archive — `xccoverbl_2014`** | a xeno-canto mirror; per-file CC licences carried through | `sources.py` |
| **Internet Archive — `warblrb10k_public`, `ff1010bird`** | bird/no-bird control sets, per their dataset terms | `sources.py` |
| **Zenodo — XCDC soundscapes** | per-record licence, read from the Zenodo record metadata and stored | `sources.py` |
| **Kaggle — BirdCLEF** | **competition rules, not a plain CC licence.** The adapter records the competition page as the licence field. Competition terms typically restrict use to the competition. | `sources.py` |
| **Hugging Face — BirdSet** | mixed xeno-canto licences, recorded as such | `sources.py` |
| **Bengalese Finch Song Repository**, **Zenodo 5545872** (zebra finch syllables) | per their own records | reference corpora |

### 3.3 What the pipeline refuses

Two refusals are implemented, and both are refusals rather than oversights
(`harvest.CACHEABLE_LICENCES`, `harvest.audio_may_be_cached`, pinned by
`harvest.self_test`):

- **NoDerivatives is refused for audio retention.** Everything downstream produces
  derived measurements, and ND is the one clause where that is not clearly covered.
  9.7 % of the production corpus.
- **An unrecorded licence is refused.** Absence of a licence is not permission. An
  unknown or unparseable licence string returns `False`, so a new source reporting
  something the gate has never seen withholds rather than assumes.

### 3.4 Audio retention — the current policy (owner decision, 2026-08-01)

The older blanket rule was that audio is always deleted immediately. That is no
longer the whole truth, and the difference matters for licensing:

- **Deleting is still the default.** Without `--keep-audio`, a recording is fetched,
  decoded, reduced to descriptors and deleted before the next one starts.
- **`harvest --keep-audio DIR` may keep the audio on this machine** where the licence
  permits, gated per recording by the two refusals above. Measured when it shipped:
  **90.3 % of the production store's 10 184 recordings pass, and all 10 184 carry a
  recordist**, so attribution exists for every kept file.
- **Nothing audio ships to the browser.** The owner declined that half on the same
  day. `pipeline/out/audio-cache/` and its siblings stay local and out of every asset
  set. Retention is not redistribution; this is the line that keeps it so.

The reason to keep audio is measured rather than convenient: an external model
(Perch, BirdNET) and any per-syllable re-measurement need the waveform, and docs/23
§23.6 could only run on the 6 453 of 10 184 recordings whose audio still existed.

### 3.5 Why no audio is synthesised from samples

Lyrebird plays no recordings back. Every note is integrated from the syrinx ODE. That
is a scientific claim first — the app shows what a physical model of a bird does — and
a licensing consequence second: there is no sample bank in the shipped assets to
attribute, because there is no sample bank.

---

## 4. If you want to use this commercially

You cannot, under `LICENSE`, and the licence is not the only obstacle. Even with a
different grant from us, a commercial derivative would have to clear:

- **the recordings**, per recording — the majority of the xeno-canto corpus is
  CC BY-NC-**SA**, which is non-commercial in its own right and not ours to waive;
- **BirdNET**, CC BY-NC-SA, if any part of the comparison work is retained (Perch,
  Apache-2.0, is the commercially clear alternative — see
  `docs/06-architecture.md` §6.2);
- **harmonypy**, GPL-3.0-or-later, if the `analysis` extra is retained;
- **BirdCLEF**, whose competition terms are not a redistribution licence at all.

The short version: the non-commercial position is not only a preference we chose. For
most of the corpus it is what the recordists chose.
