# Questions for the challenge point of contact — Lab 02

1. **Is attribution instability actually a trust-killer for forecasters,** or
   is calibration/consistency of the *forecast itself* the bigger issue? We
   operationalized trust as stability of feature-importance rankings under
   refits — is that the right first proxy?
2. **What explanation granularity do forecasters need** — global importances
   (what we measured), per-forecast attributions, or physical-mode
   consistency (e.g. does the model respect known teleconnections)?
3. **Which model family should this run against next?** Ridge is the honest
   floor; the interesting version applies the same stability index to a small
   neural forecaster on a WeatherBench2 subset.
4. **Is a skill×stability product the right headline,** or should stability
   be a constraint (maximize skill subject to stability ≥ τ)? Our sweep shows
   stability is nearly free until regularization destroys skill — does that
   match your experience with operational models?
5. **Would forecasters engage with a journal like this** — memos where every
   trust claim resolves to a recorded refit experiment, rather than a
   screenshot of a saliency map?
