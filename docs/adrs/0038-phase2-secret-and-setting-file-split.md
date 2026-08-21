# ADR-0038: Credentials and operator settings in separate uncommitted files

- **Status:** accepted
- **Date:** 2026-08-21
- **Blueprint requirement:** Phase 2 opt-in provider credentials, secret
  redaction, and versioned non-secret run configuration
- **Decision owners:** repository owner and operator

## Context

ADR-0030 grew the credential surface from one key to fourteen entries and noted
that five of them are "non-secret operational settings": `AWS_REGION`,
`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`,
and `MINIMAX_GROUP_ID`. It put all fourteen in one `.env` and recorded the
non-secret five as an exception list, `NON_SECRET_PROVIDER_KEYS`, consulted
wherever the difference mattered.

That created three problems, each observed rather than hypothesised.

- The one file an operator is careful about held two kinds of thing. "Keep
  credentials out of git" and "keep account-specific settings out of git" are
  both true, but the first is the one people internalise, and a setting had no
  file of its own to live in.
- `ProviderSpec.required_credentials` listed all four Azure entries, so the
  preflight reported a missing endpoint as a missing credential. The distinction
  existed in a set literal in `env_file.py` and nowhere in the type.
- Being non-secret was treated as being harmless. It is not.
  `AZURE_OPENAI_ENDPOINT` is the host a credential is sent to, so an attacker
  who can rewrite that one line redirects the key without ever reading it. The
  setting needs integrity protection even though it needs no confidentiality.

The owner's requirement is that no operator-specific value reaches git, with
separate files as needed. `.gitignore` already excluded `.env` and `.env.*`
while allowing `.env.example`, so more than one uncommitted file was free.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt one `.env` and keep the exception list | Status quo since ADR-0030 | No migration | The file people guard holds settings too; a missing endpoint reports as a missing credential; the secret/non-secret split lives in a hand-kept literal | Rejected |
| Wrap: `.env` for secrets, `.env.settings` for operator settings, split enforced by the loaders | `.gitignore` already covers `.env.*`; the registry already separated required from optional | One file to guard and one to configure; the two key sets partition by construction; a misfiled key is refused by name with the file it belongs in | Two files to create; a migration for anyone with an existing `.env` | Selected; a credential in the settings file and a setting in the secret file must both be hard errors |
| Move the non-secret settings into the versioned run configuration JSON | ADR-0030 says non-secret configuration is versioned JSON | Deployment and `model_identifier` would share one content hash, making the mismatch ADR-0037 hit structurally impossible | Commits the operator's resource and deployment names to git, which is what the owner ruled out | Rejected on that ground; the binding problem it would have solved is recorded as unresolved below |
| Support arbitrary per-provider env files | None requested | Flexible | Multiplies the number of files to protect and gives one key several homes | Rejected |

## Decision

Two files, one purpose each, and the separation is enforced by the loader rather
than left to convention.

- `.env` holds the nine credential keys and nothing else. A setting written here
  is an `EnvFileError` naming the key, the line, and `.env.settings`.
- `.env.settings` holds the five non-secret operational settings and nothing
  else. A credential written here is an `EnvFileError` naming the key and `.env`,
  and the message never contains the value.
- `PROVIDER_SECRET_KEYS` and `PROVIDER_SETTING_KEYS` partition
  `PROVIDER_ENV_KEYS`. `NON_SECRET_PROVIDER_KEYS` keeps its name, aliased to the
  setting set, so it is now true by construction rather than maintained.
- `ProviderSpec` gains `required_settings` and `optional_settings`.
  `required_credentials` sheds the three Azure non-secrets and `AWS_REGION`;
  every one of them stays required, and the preflight scans both lists into the
  same `missing_variables`. Which file holds a variable changed; whether it is
  needed did not.
- `.env.settings` carries the same file controls as `.env` -- regular file, no
  symlink, mode 0600 -- for integrity, not confidentiality, because it names the
  host that receives the credential.
- `load_provider_environment` loads both into one mapping, and the CLI uses it.
  A caller that loaded only credentials would pass the preflight with an
  unresolved endpoint and fail inside the adapter.
- `.env.settings.example` is versioned and blank, alongside `.env.example`, and
  `.gitignore` negates both.

## Consequences

- Operational: an existing populated `.env` must have its five settings moved,
  or the loader refuses the file by name. That is deliberate -- a silent accept
  would leave the value in the wrong file indefinitely.
- Security: one file to guard for confidentiality, both for integrity. A
  credential can no longer be typed into the file that is treated as
  non-sensitive, because that is now an error rather than a merge.
- Reproducibility: unchanged. Neither file is read by `make check`, and live
  calls were already excluded from canonical replay.
- Testing: each example file is asserted against its own key set, with a
  negative assertion that it contains none of the other's -- checking the union
  against one file would let a secret be documented as a setting while the
  totals still agreed. Both misfiling directions are asserted, and every
  declared `ProviderSpec` requirement is asserted to have a home in exactly one
  of the two sets.
- Negative, and unresolved: on Azure the deployment in the URL selects the
  model, and the deployment now lives in an uncommitted file while
  `model_identifier` lives in a committed, content-hashed run configuration.
  Those two can disagree, and nothing offline can detect it -- exactly the
  mismatch ADR-0037 found and corrected by hand. The rejected third option would
  have made it impossible, at the cost of committing operator-specific values.
  Until that is resolved, a run's recorded model identity is only as good as the
  operator keeping the two in step, and the audit record cannot prove which
  deployment answered.
- Negative: `MINIMAX_GROUP_ID` moved from an optional *credential* to an optional
  *setting*. It is not a secret, but a group id is an account identifier, so
  anyone reasoning about disclosure should read the settings file as
  account-identifying rather than as public.

## Blueprint deviation

Partial, recorded here rather than buried. `TECHNICAL_BLUEPRINT.md` and ADR-0030
both say non-secret run configuration belongs in versioned JSON. Five settings
now sit in an uncommitted env file instead. The necessity is the owner's
requirement that no operator-specific value reach git; the trade is the
model-to-deployment binding described above. Revisit if the audit record needs to
prove which deployment served a run, in which case the deployment belongs in the
content-hashed configuration and the exclusion has to be solved another way --
for example by keeping operator-specific configurations in an uncommitted
`config/` subdirectory generated by the existing `live-config-create` command.

## Validation and revisit trigger

`make check` stays green with no new skips. The acceptance assertions are: the
two key sets partition the supported keys; each example file documents exactly
its own set and is blank; a setting in `.env` and a credential in
`.env.settings` are both refused by name, with the settings-file refusal proved
not to echo the value; a world-readable settings file is refused; the process
environment is never overridden by either file and a blank entry reports as
unconfigured; loading both fills one mapping; and every declared provider
requirement resolves from exactly one of the two files.

Revisit if a key's classification changes -- a setting that becomes
account-sensitive should move to `.env` rather than gain an exception -- or if
the deployment-to-model binding needs to be verifiable rather than
operator-maintained.
