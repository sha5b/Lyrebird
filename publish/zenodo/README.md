# Zenodo: do this first

It is free, it is run by CERN, it accepts CC BY-NC-SA, and it gives a permanent DOI. Both
papers have a `\todo` waiting on that DOI, so nothing else finishes until this is done.

## What to upload, and what must not be

**Upload:**

| file | what it is | size |
|---|---|---|
| `docs/whitepaper/arxiv/build/main.pdf` | the system paper | ~700 kB |
| `docs/whitepaper/w0-arxiv/build/main.pdf` | the W0 paper | ~100 kB |
| `pipeline/analysis/*.json` | every gate's result sidecar | small |
| `pipeline/out/external/w0-full-meta.json` | the W0 population: which recordings, whose, which species | ~1 MB |
| `pipeline/out/external/w0-full-embeddings.npz` | frozen Perch + BirdNET features for that population | ~90 MB |
| `pipeline/out/audio-postcutoff/_catalogue_full.json` | the complete post-cutoff catalogue, so the population is reconstructible | ~30 MB |
| a source tarball of the repo | code snapshot | — |

**Must not upload:** any file under `pipeline/out/audio-postcutoff/xc*` or
`pipeline/out/audio-cache/`. That is xeno-canto and iNaturalist audio under per-recording
licences that are not ours to redistribute. `NOTICE.md` is the long form.

The embeddings are the interesting part of this release and they are safe: they are
non-invertible derived features, which is the same argument the store rests on.

## Steps

1. Log in at [zenodo.org](https://zenodo.org) with GitHub.
2. **New upload.** Drag the files above in.
3. Paste the metadata from [`zenodo-metadata.json`](zenodo-metadata.json). The web form has a
   field for each key.
4. Upload type: **Dataset** if you are archiving the derived data, **Publication → Preprint**
   if the PDFs are the point. If you want both cleanly, make **two** depositions and link
   them with `related_identifiers` — the metadata file shows how.
5. **Reserve the DOI** before publishing. Zenodo has a "Reserve DOI" button, which gives you
   the string while the record is still a draft.
6. Put that DOI into both papers, replacing `\todo{archived release DOI...}`:
   - `docs/whitepaper/arxiv/main.tex`
   - `docs/whitepaper/w0-arxiv/main.tex`
7. Rebuild both papers (`tectonic -X compile main.tex --outdir build`) so the PDFs you upload
   contain their own DOI.
8. Publish.

Step 5 to 7 is the only fiddly part: the PDF has to contain the DOI that points at the record
the PDF is in. Reserving the DOI first is what makes that possible.

## Wiring it to GitHub so future releases are automatic

Zenodo → **GitHub** in your Zenodo settings → flip the switch on this repository. From then
on every GitHub release mints a new version DOI under one concept DOI. Cite the **concept**
DOI in prose ("the archived release") and the version DOI when a specific number matters.

## A note on the licence field

Set it to **CC BY-NC-SA 4.0** for the text and code. Zenodo allows one licence per deposition,
so if you want the derived data under something more permissive, that is a second deposition.
Do not set CC BY on a deposition containing this project's prose — `NOTICE.md` is explicit
that the NC and SA terms are deliberate.
