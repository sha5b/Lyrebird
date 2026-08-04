# xeno-canto forum post

These are the people whose work the entire project rests on. Two reasons to post, and the
second is the useful one:

1. **Courtesy.** 11,687 of their recordings went through this pipeline. They should hear about
   it from us rather than find it.
2. **They are the only people who can fix the confound.** Every method we tried for removing
   recordist structure from an embedding failed, four independent ways. The one thing that would
   work is not a method — it is more recordists per species, in the archive. That is entirely in
   their hands.

Post in the general forum. Do **not** frame it as "your archive has a problem". The skew is a
property of volunteer collection and nobody did anything wrong.

---

**Title:** Some measurements from 11,687 xeno-canto recordings, and one request

I have been building a system that measures bird syllables and fits a physical model of the
syrinx to them. It has run over 11,687 recordings from this archive, and I wanted to report back
to the people who made them, plus ask one thing.

**No audio is redistributed anywhere.** The pipeline decodes a recording, describes it as
numbers, and deletes the file. Nothing that ships can be turned back into a recognisable
recording. Every recordist is credited per recording in the released catalogue, and your
licences travel with your work untouched.

**What the recordings supported.** 378,224 measured syllables over 3,812 species; a fitted
physical inventory for 2,650 of them, where each syllable type is a pair of named physical
gestures (air-sac pressure and syringeal tension) rather than an opaque code. Fifty-eight
questions were registered in advance and thirty-six of them ended in a written refusal, which is
most of what I learned.

**The finding that concerns this archive, and it is not a criticism.** Machine-learning models
trained on archive recordings turn out to encode *who recorded it* very strongly — often more
strongly than which bird it is. That is not a flaw in anyone's recordings. It is a consequence
of how volunteer collection works: for most species, most recordings come from a small number of
people, so a model has no way to tell "this species" apart from "this person's gear and
patch". I tried four independent ways to remove it from the model side and all four failed.

Two foundation models the field uses, Perch and BirdNET, carry the same structure. On recordings
uploaded recently enough that neither model can have trained on them, it is still there.

**The request.** The one thing that fixes this is more *different* recordists per species,
rather than more recordings. Concretely: a species that already has fifty recordings from three
people benefits far more from a fourth person's single recording than from a fourth recording by
one of the three. If you are choosing what to record next and the species is already
well-covered by others, a species covered by only one or two recordists is worth
disproportionately more to anyone training on this archive.

Median in the part of the archive I measured is 2 recordists for species with fewer than eight
recordings, against 17 for the better-covered ones. That gap is the whole problem in one number.

Everything is public: [ZENODO DOI], [HF LINK]. Glad to answer questions, and glad to be
corrected — several of these numbers are about my own pipeline's limits as much as about birds.

Thank you. None of this exists without your recordings.

---

## Notes before posting

- Fill `[ZENODO DOI]` and `[HF LINK]`.
- The "request" paragraph is the load-bearing one. It converts a complaint into something
  actionable by the only people who can act on it.
- Keep the tone. This is a volunteer community, and a post that reads as "your data is biased"
  will get the response it deserves.
