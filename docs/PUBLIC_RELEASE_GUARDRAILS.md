# Public repository release guardrails

`efferents public-check` is a fail-closed preflight for a git repository that is
about to be made public or linked from a public lab.

It does not upload, push, change repository visibility, select a licence, or
provide a legal certification. It produces a redacted report that separates
machine-detected blockers from decisions that only the repository owner or an
appropriate reviewer can make.

## Usage

Run the technical scan first:

```bash
efferents public-check /path/to/repository
```

`needs_manual_review` is the expected result when there are no technical
blockers. Review every finding and the displayed attestations. Only after a
named human has completed that review, record it and save the release report:

```bash
efferents public-check /path/to/repository \
  --acknowledge-manual-review "Reviewer name" \
  --report "$HOME/.efferents/release-reports/my-lab.json"
```

Exit code `0` means `ready`. Exit code `1` means `blocked` or
`needs_manual_review`. Use `--json` for machine-readable stdout.

Keep the report outside the repository. Writing it into the repository changes
the working tree, so the next exact-release check will correctly block until
that change is deliberately committed or removed.

## Automated blockers

The built-in scan checks the tracked working tree and all reachable git history.
It blocks publication when it finds:

- no tracked top-level `LICENSE`, `LICENCE`, or `COPYING` file;
- a dirty working tree, because the reviewed state cannot be tied to one commit;
- common API tokens, authentication URLs, private-key material, payment-card
  numbers, or high-confidence hard-coded credentials;
- tracked `.env`, credential-store, keystore, Terraform-state, or private-key
  files, including filenames found in history;
- a symlink escaping the repository;
- an unavailable tracked file or incomplete history scan;
- a file over 50 MiB that the built-in scanner cannot safely clear.

Detected secret values are omitted from terminal and JSON output. If a real
credential was ever committed, revoke or rotate it. Deleting the current file
does not make a credential safe, because it remains in git history and may
already have been copied.

## Findings requiring human review

The checker surfaces, but cannot adjudicate:

- datasets, databases, logs, packet captures, and notebook outputs;
- model weights and checkpoints;
- images, audio, video, PDFs, Office documents, and archives;
- vendored material and git submodules;
- possible personal identifiers and lower-confidence credential assignments;
- files over 10 MiB and other binary content.

A named reviewer must confirm ownership and licence rights, privacy and consent,
contractual confidentiality and embargoes, export-control or sanctions duties,
and security remediation. Acknowledgement records responsibility; it does not
override an automated blocker.

## Important limits

The preflight does not determine whether a copyright exception applies, whether
personal data has a lawful publication basis, whether software or technology is
export-controlled, whether a patent filing should precede disclosure, or
whether every dependency licence is compatible. It also does not inspect remote
issues, pull requests, release assets, deleted/unreachable git objects, or LFS
objects that are absent locally.

Use it as one release control alongside appropriate legal, privacy, security,
research-ethics, and domain review. On GitHub, keep secret scanning and push
protection enabled as an additional independent control.

## Policy basis

The conservative defaults follow the practical principles that public code
should have explicit reuse terms, secrets should be blocked before publication,
personal data should be limited to what is necessary, and third-party material
requires permission or a compatible licence. Useful primary guidance:

- [GitHub: Licensing a repository](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)
- [GitHub: Push protection](https://docs.github.com/en/code-security/concepts/secret-security/push-protection)
- [ICO: Data minimisation](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-protection-principles/a-guide-to-the-data-protection-principles/data-minimisation/)
- [GOV.UK: Using somebody else's copyright](https://www.gov.uk/using-somebody-elses-intellectual-property/copyright)
- [GOV.UK: Export controls for software and technology](https://www.gov.uk/guidance/export-controls-dual-use-items-software-and-technology-goods-for-torture-and-radioactive-sources)
