# 1 — The reference artifact: what the viral image actually depicts

The image shows a dark 3D scatter plot floating above a photo of a nightingale.
Colored clusters (magenta, blue, red, green) connect through thin trajectory
lines. The headline reads **"AI is decoding what birds have been saying all
along"**.

## 1.1 Origin tracing

The exact headline does not appear in any indexed news article (Guardian/NYT/Wired/New
Scientist). It is almost certainly a **content-farm reel** (TikTok/Instagram) that
composites three real things:

1. **The narrative** — from the Earth Species Project media cycle (Aza Raskin,
   "decoding animal communication with AI", 2022–2025). Manifesto paper: Rutz et al.,
   *Using machine learning to decode animal communication*, Science 2023
   (DOI 10.1126/science.adg7314).
2. **The bird** — a nightingale. The classic Hultsch & Todt (FU Berlin) research
   shows that a male nightingale has ~180–200 discrete song types delivered in
   rule-governed order. This is the canonical "birds have a vocabulary" result.
3. **The visualization** — a UMAP/t-SNE embedding plot of bird vocalizations. The
   canonical sources of exactly this figure style:
   - Sainburg, Thielk & Gentner, *Finding, visualizing, and quantifying latent
     structure across diverse animal vocal repertoires*, PLOS Comp. Biol. 2020
     (3D latent space, colored clusters, temporal trajectory lines).
     https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1008228
   - Goffinet et al., *Low-dimensional learned feature spaces…*, eLife 2021 (VAE+UMAP).
   - **Google Creative Lab "Bird Sounds" experiment** (Kyle McDonald, Manny Tan, Yotam
     Mann, 2016): t-SNE map of thousands of bird recordings, dark background, sounds
     light up on playback. This is the single most relevant prior art and it is open
     source (Apache 2.0): https://github.com/googlecreativelab/aiexperiments-bird-sounds

## 1.2 What the point cloud means technically

- Each **point** = one segmented syllable/note.
- **Position** = a 2D/3D projection of a high-dimensional feature vector (deep
  embedding or handcrafted acoustic features), via UMAP/t-SNE/VAE latent space.
- **Colors** = discovered cluster / syllable type.
- **Thin lines** = temporal trajectories connecting consecutive syllables of one song —
  a "path" through the vocal repertoire.
- When a bird sings, the active region lights up. That is the "it jumps when the tone
  and melody works" effect Lyrebird recreates (see `05-embedding-galaxy.md`).

## 1.3 Implication for Lyrebird

The reel is a composite, but everything it implies is buildable. The embedding
galaxy has open-source prior art. The vocabulary framing comes from
nightingale/great-tit ethology. The live reactivity uses standard Web Audio +
shaders. The app can deliver the *honest version* of the promise the reel makes.
