# Durable Phase 2 Traceable Report

- Run `run.phase2.live.openai.gpt5-mini.v3` is `awaiting_review` for dossier `dossier.even_sum.phase2.open.v1` with canonical hash `sha256:7c4a99e1b129b0bb4192094778a87cdd9c945a5d87cf0f7f6c00f6f9509408f7`. [refs: run.phase2.live.openai.gpt5-mini.v3, dossier.even_sum.phase2.open.v1]
- The accepted target `claim.even_sum.v1` remains policy-projected as `unknown`; model/backend output did not mutate it. [refs: claim.even_sum.v1 ]
- Durable state contains 2 proposal-only artifacts and 2 jobs. [refs: proposal.run.phase2.live.openai.gpt5-mini.v3.proposer, proposal.run.phase2.live.openai.gpt5-mini.v3.verifier]
- Audit replay hash is `sha256:d5bb8e34704404aa3f69e44f4f19c32787a747fd5a2d70ab323028e998fcd24c`. [refs: run.phase2.live.openai.gpt5-mini.v3]
- Verifier context `manifest.run.phase2.live.openai.gpt5-mini.v3.verifier` has exact serialized hash `sha256:e625dcfdbe8ddab1f266ebb74935e0311ba2f1f3a11acf55920277c5b9e0bdd0`. [refs: manifest.run.phase2.live.openai.gpt5-mini.v3.verifier]
- Verifier independence: context-isolated=`true`, separate-call=`true`, different-model=`false`, different-provider=`false`, fully-independent=`false`. [refs: manifest.run.phase2.live.openai.gpt5-mini.v3.verifier]
- API-reported usage totals 4191 tokens; estimated cost is 4240 micro-USD, with every estimate linked to its pinned pricing snapshot. [refs: call.run.phase2.live.openai.gpt5-mini.v3.proposer.attempt.1, call.run.phase2.live.openai.gpt5-mini.v3.verifier.attempt.1]
