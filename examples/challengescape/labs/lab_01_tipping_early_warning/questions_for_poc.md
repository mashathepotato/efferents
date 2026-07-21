# Questions for the challenge point of contact — Lab 01

Asked from a position of "we built the simplest credible loop; tell us where
it's wrong," not "we solved your problem."

1. **Which tipping element matters to you operationally?** The lab's synthetic
   ensemble models generic critical slowing down; the window/lead-time
   tradeoff will look different on AMOC transports vs. ice-sheet or ecosystem
   records. Which real series should replace `datagen.py` first?
2. **What false-alarm rate is actually tolerable?** We pinned the
   series-level false-alarm rate at ~5% by construction. Is the real
   constraint per-year, per-decade, or per-decision?
3. **What lead time is actionable?** Our best detector warns ~98 steps ahead
   on a 500-step series. What does "early enough to anticipate" mean in your
   setting — months, years, decades?
4. **Is indicator choice or window choice the bigger open question?** We swept
   the window for lag-1 autocorrelation only; variance, skewness, and spatial
   indicators are the obvious next axes.
5. **Would a standing, provenance-tracked lab like this be useful to your
   group** — one that reruns the tradeoff curve automatically as new data
   arrives and writes a reviewed memo when the answer changes?
