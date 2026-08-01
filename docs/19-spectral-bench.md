# 19 — The spectral bench: does the cosine measure an audible fit?

One number judges every fit decision in the pipeline: the learn inversion's gesture
search, the respfit/docrefit ship gates, the fricative routing. The number is the
cosine between the resynthesis's 28-d descriptor and the real audio's, measured in
the harvested population frame. docs/19 asks the question none of those gates could:
**is a cosine gain an audible gain?**

## 19.1 The instrument (specbench.py)

The owner-sanctioned iNat audio cache is the only place a resynthesis can meet its
original. For a fitted type: render it, then take the *medoid* member's cached audio
(a typical rendition, not a lucky one). Align the two: resample the longer clip to the
shorter, because time within a syllable is relative, the assumption
`features.mel_path` already makes. Channel-normalize next: shift the per-band log-mel
mean of the render onto the original, because channel is the measured dominant
nuisance (docs/17). Then:

- **MCD** — 25 mel-cepstral coefficients (the features module's own 26-band bank and
  DCT, c0 excluded), Kubichek dB, per pair band-limited to the file's own Nyquist.
  The cache is 22.05 kHz audio. Above it the original floors while the 48 kHz
  render holds tract energy, so not band-limiting inflates MCD by tens of dB.
- **Multi-resolution STFT error** — log-spectral distance at 512/1024/2048,
  averaged. The better-calibrated absolute scale of the two.
- **The incumbent** — the 28-d cosine, recomputed through learn's exact path
  (population frame → standardize → unit-norm → dot with the type's mean-member
  reference), not read from the inventory.

Self-test: identity scores 0.000 dB. A half-low-passed render costs +77.9 dB MCD /
+7.0 dB STFT while the cosine drops only 0.015 (the bench measures what the cosine
misses). Correction takes a stationary channel tilt from 105.1 → 4.3 dB. Time-varying
damage survives correction.

## 19.2 The finding (n = 200 types, debug-100 store, iNat cache)

| correlation | Pearson | p | Spearman | p |
|---|---|---|---|---|
| cosine vs MCD (dB) | +0.106 | 0.136 | +0.100 | 0.157 |
| cosine vs STFT error (dB) | +0.102 | 0.151 | +0.111 | 0.118 |

**The resynthesis cosine carries essentially no information about spectral distance
to the original audio.** Neither correlation is distinguishable from zero. The
point estimates lean the wrong way. This is not a bench artifact:

- the recomputed cosine reproduces the stored one (Pearson 0.921, median |diff|
  0.002) — the bench measured the same number learn does.
- MCD and STFT, two independent distances, agree at Pearson 0.925 — they measure
  something coherent. The cosine just does not measure it.

A plausible mechanism for the wrong-way lean: high-cosine types are clean whistles.
Their renders concentrate energy in one band, while field audio carries broadband
noise everywhere else, so the spectral distance is large. Noisy buzzes score low
cosine but have broadband energy on both sides, so the distance is small.

The cosine is not broken as a *clustering* statistic. It separates types from each
other, which is what typing and placement use it for. It is unproven as a *fidelity*
ranking, and that is what every fit gate uses it for.

One scope note, honestly: the cosine here is cluster-level (type mean vs render),
while MCD/STFT score one member's audio. Within-type variation adds noise to the
correlation. At r ≈ 0.1 with two agreeing metrics, that noise cannot hide a strong
relationship. Distortion medians: MCD 73.9 dB (p10 45.7, p90 212.0 — MCD magnitudes
are floor-inflated), STFT 7.93 dB (p10 5.16, p90 15.7).

## 19.3 What this changes (and what it does not)

- **Not changed: docs/17's source-invariance verdict** — it was judged on kNN lift
  (structure in the embedding), which the bench says nothing about.
- **Caveated: every cosine-gated adoption** — respfit's respiration/two-voice
  winners, docrefit's texture ships, the fricative routing. A proxy that does not
  rank audible fit at type level made those decisions. They are not
  necessarily wrong — each also improved the descriptor match — but "improved the
  proxy" is now a weaker claim than it read.
- **Promoted: the mel-patch/mel-path fit target.** A time-resolved spectral target
  is precisely what MCD measures. The bench's finding converts "add the 736-d patch
  as a fit target" from an improvement into the priority. The objective and the
  audible metric would finally be the same quantity. The 28-d cosine stays as the
  ungameable *clustering* guardrail, the role it is actually proven for.
- **The bench is now the verdict instrument** for any future fit-objective change:
  pre-registered gates should read MCD/STFT against cached audio, not only the
  cosine. 44 of 272 candidate types skipped for lack of cached audio. The depth
  harvest's audio-retention half is what widens this bench.

## 19.4 The mel-target objective: the premise holds, with a blend (same day)

`learn.MelTargetTerm` (`learn --mel-weight w`, default 0 = bit-identical old
objective): each type's mean member `mel_path` is the target, similarity
`exp(−LSD)` (mean-over-knots RMS log-mel difference — the multi-res STFT
convention at mel resolution), blended `score = (1−w)·cosine + w·mel`. A
path-cosine form came first, and **measurement rejected it**. It shares the
cosine's blindness on the damaged-half fixture (drop 0.017 vs 0.015), where
exp(−LSD) drops 0.540. The verdict, pre-registered against this doc's bench:

| correlation (n = 200, same rows as §19.2) | Pearson | Spearman |
|---|---|---|
| cosine vs MCD | +0.106 | +0.100 |
| **melTarget vs MCD** | **−0.305** (p 1e-5) | **−0.420** (p 6e-10) |

Signs correct (higher similarity ↔ lower distortion). The r > 0.4 bar is met on
Spearman and missed on Pearson. exp(−LSD) piles near zero for poor fits, so ranking
is the strong signal, and ranking is what the gates use. The end-to-end probe (10
types, refit from the same medians, only the objective differs):

| w | MCD win/loss | median ΔMCD | median cosine drop | guardrail |
|---|---|---|---|---|
| 1.0 (pre-registered) | 7/3 | +5.62 dB better | 0.377 | **FAIL (> 0.05)** |
| 0.5 (exploratory) | 7/3 | +3.56 dB better | −0.015 (cosine *up*) | pass |
| 0.25 (exploratory) | 5/5 | −0.75 dB | −0.008 | pass |

**The mel objective alone wanders off the descriptor manifold — the RealismTerm
lesson, repeated with a better term.** w = 0.5 is the candidate shipping weight
(exploratory, n = 10, indicative only). w = 1 must not ship.

The two objectives agree only moderately on which types are good (Pearson 0.456).
They are complementary, not redundant: the cosine guards the cluster assignment, and
the mel path ranks the audible fit. Adoption into the default learn flags waits on
the owner's call and a larger probe. The machinery ships default-off like every
learned component.

## 19.5 The adoption-gate probe (n = 80): NOT adoptable as an objective

The 10-type probe did not survive n. The gate run (seed 19 sample of 80 of the 200
benched types, pairwise w=0.5 vs w=0 control from identical median+tract starts,
pre-registered: ≥ 60 % MCD wins, median ΔMCD > +1 dB, median cosine drop ≤ 0.02,
max ≤ 0.05):

| metric | result | gate | verdict |
|---|---|---|---|
| MCD win share | **31 %** (25/80) | ≥ 60 % | FAIL |
| median ΔMCD | **0.0 dB** | > +1 dB | FAIL |
| median cosine drop | 0.0 | ≤ 0.02 | pass |
| max cosine drop | **0.120** | ≤ 0.05 | FAIL |

The honest reading is more useful than a bare fail. **The objective change mostly
does nothing**: the median effect is exactly zero, because the inversion already
lands where the blend would send it. **It sometimes helps enormously**: mean
+2.07 dB, pulled by a handful of types at +13.8 dB. **It occasionally wanders**: one
type lost 0.12 cosine. An objective that is a wash on the median with an unguarded
tail is not a default. The 7/10 of the small probe was small-sample luck.

**What survives, and it matters:** the mel target is the better *measurement* but
the worse *optimizer*. §19.4's correlations stand: it ranks audible distortion where
the cosine cannot. The distinction is now load-bearing for the whole program.

Read the fit gates on the bench (MCD/STFT), while the inversion keeps climbing the
cosine. The cosine is a proxy that is wrong as a fidelity ranking, but its failure
is at least bounded and cluster-safe. "Measure spectrally, optimize descriptor-ly"
is the honest state. An objective that is both remains unfound.
