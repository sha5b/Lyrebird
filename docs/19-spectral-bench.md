# 19 — The spectral bench: does the cosine measure an audible fit?

Every fit decision in the pipeline — the learn inversion's gesture search, the
respfit/docrefit ship gates, the fricative routing — is judged by one number: the
cosine between the resynthesis's 28-d descriptor and the real audio's, measured in
the harvested population frame. docs/19 asks the question none of those gates could:
**is a cosine gain an audible gain?**

## 19.1 The instrument (specbench.py)

The owner-sanctioned iNat audio cache is the only place a resynthesis can meet its
original. For a fitted type: render it, take the *medoid* member's cached audio (a
typical rendition, not a lucky one), align (resample the longer clip to the shorter
— time within a syllable is relative, the assumption `features.mel_path` already
makes), channel-normalise (per-band log-mel mean of the render shifted onto the
original — channel is the measured dominant nuisance, docs/17), then:

- **MCD** — 25 mel-cepstral coefficients (the features module's own 26-band bank and
  DCT, c0 excluded), Kubichek dB, per pair band-limited to the file's own Nyquist
  (the cache is 22.05 kHz audio; above it the original floors while the 48 kHz
  render holds tract energy — not band-limiting inflates MCD by tens of dB).
- **Multi-resolution STFT error** — log-spectral distance at 512/1024/2048,
  averaged. The better-calibrated absolute scale of the two.
- **The incumbent** — the 28-d cosine, recomputed through learn's exact path
  (population frame → standardise → unit-norm → dot with the type's mean-member
  reference), not read from the inventory.

Self-test: identity scores 0.000 dB; a half-low-passed render costs +77.9 dB MCD /
+7.0 dB STFT while the cosine drops only 0.015 (the bench measures what the cosine
misses); a stationary channel tilt is corrected 105.1 → 4.3 dB, time-varying damage
survives correction.

## 19.2 The finding (n = 200 types, debug-100 store, iNat cache)

| correlation | Pearson | p | Spearman | p |
|---|---|---|---|---|
| cosine vs MCD (dB) | +0.106 | 0.136 | +0.100 | 0.157 |
| cosine vs STFT error (dB) | +0.102 | 0.151 | +0.111 | 0.118 |

**The resynthesis cosine carries essentially no information about spectral distance
to the original audio.** Neither correlation is distinguishable from zero; the
point estimates lean the wrong way. This is not a bench artifact:

- the recomputed cosine reproduces the stored one (Pearson 0.921, median |diff|
  0.002) — the bench measured the same number learn does;
- MCD and STFT, two independent distances, agree at Pearson 0.925 — they measure
  something coherent; the cosine just doesn't measure it.

A plausible mechanism for the wrong-way lean: high-cosine types are clean whistles
whose renders concentrate energy in one band while field audio carries broadband
noise everywhere else (large spectral distance); noisy buzzes score low cosine but
have broadband energy on both sides (small distance). The cosine is not broken as a
*clustering* statistic — it separates types from each other, which is what typing
and placement use it for. It is unproven as a *fidelity* ranking, and that is what
every fit gate uses it for.

One scope note, honestly: the cosine here is cluster-level (type mean vs render)
while MCD/STFT score one member's audio — within-type variation adds noise to the
correlation. At r ≈ 0.1 with two agreeing metrics, that noise cannot be hiding a
strong relationship. Distortion medians: MCD 73.9 dB (p10 45.7, p90 212.0 — MCD
magnitudes are floor-inflated), STFT 7.93 dB (p10 5.16, p90 15.7).

## 19.3 What this changes (and what it does not)

- **Not changed: docs/17's source-invariance verdict** — it was judged on kNN lift
  (structure in the embedding), which the bench says nothing about.
- **Caveated: every cosine-gated adoption** — respfit's respiration/two-voice
  winners, docrefit's texture ships, the fricative routing. Those decisions were
  made by a proxy that does not rank audible fit at type level. They are not
  necessarily wrong — each also improved the descriptor match — but "improved the
  proxy" is now a weaker claim than it read.
- **Promoted: the mel-patch/mel-path fit target.** A time-resolved spectral target
  is precisely what MCD measures. The bench's finding converts "add the 736-d patch
  as a fit target" from an improvement into the priority: the objective and the
  audible metric would finally be the same quantity. The 28-d cosine stays as the
  ungameable *clustering* guardrail, the role it is actually proven for.
- **The bench is now the verdict instrument** for any future fit-objective change:
  pre-registered gates should read MCD/STFT against cached audio, not only the
  cosine. 44 of 272 candidate types skipped for lack of cached audio — the depth
  harvest's audio-retention half is what widens this bench.
