# WILDLABS post

[WILDLABS.net](https://wildlabs.net) is a free community of conservation-technology
practitioners with an active acoustics group. These are the people **deploying** BirdNET and
Perch on real hardware in real places, which makes them the audience for whom the recordist
result is not academic.

Post in the **Acoustics** group. Keep it short — this is a forum, not a paper.

---

**Title:** What a recordist-blocked evaluation split costs a bioacoustic foundation model

Most of us know deployment performance disappoints relative to benchmark numbers. Here is one
measurable cause and a price for it.

Benchmarks for bird sound classification split recordings at random. In the archives those
recordings come from volunteers, and for many species most of them come from a handful of
people. A recordist is not only a person — they are a microphone, a preamp, a set of habits, a
geographic range and a time of day. When one person's recordings land on both sides of a random
split, a model can reach the right species by recognising the person.

That is functionally the same failure as deploying on a new recorder at a new site, which is
the transition we all know goes badly.

**What we measured.** On xeno-canto recordings uploaded *after* both models' training snapshots
— so neither Perch 2.0 nor BirdNET V2.4 can have seen them — a linear probe over frozen
features loses **18.5 points of top-1 on Perch and 21.6 on BirdNET** when the split is blocked by
recordist instead of random. Both are about **2.0x the errors**. On 884 species from 646
recordists, and blocking was worse in 20 of 20 paired folds on both models.

**Two things worth knowing if you evaluate your own models.**

Species carried by a single recordist cannot be scored under a blocked split at all — they land
wholly on one side and become an empty test class. Dropping them is correct; counting them as
errors manufactures the result you were looking for.

And the two foundation models disagree with each other about the size of this by more than
either differs from a small 32-d space we trained on one corpus. Perch carries 16.5 % less
recordist structure, BirdNET 24 % more, on identical rows. If recorder invariance came from
archive-scale training, both would be below. We read it as a property of the archives that any
model trained on them inherits.

**What this means for a deployment.** If your birds will be heard by a new recorder in a new
place, the blocked figure is the closer estimate, and the gap above is the scale of the optimism
in the random one.

Everything is reproducible: embeddings, metadata and the catalogue at [HF LINK], code and
archive at [ZENODO DOI]. No audio is redistributed — the recordings stay the recordists'.

Happy to answer questions about the design. The thing I would most like from this group is
whether the gap looks like what you see going from archive training to field deployment.

---

## Notes before posting

- The numbers are filled in from `pipeline/analysis/w0_full.json`. Only `[HF LINK]` and
  `[ZENODO DOI]` are still open, and both need accounts.
- The closing question is deliberate. This community has field experience that the paper does
  not, and their answer is worth more than the post.
- Do not lead with the syllable inventory. It is the larger project but it is not what this
  audience needs, and it makes the post about us instead of about their problem.
