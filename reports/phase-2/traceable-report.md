# Durable Phase 2 Traceable Report

- Run `run.phase2.demo.fake.v1` is `awaiting_review` for dossier `dossier.even_sum.phase2.open.v1` with canonical hash `sha256:7c4a99e1b129b0bb4192094778a87cdd9c945a5d87cf0f7f6c00f6f9509408f7`. [refs: run.phase2.demo.fake.v1, dossier.even_sum.phase2.open.v1]
- The accepted target `claim.even_sum.v1` remains policy-projected as `unknown`; model/backend output did not mutate it. [refs: claim.even_sum.v1 ]
- Durable state contains 2 proposal-only artifacts and 2 jobs. [refs: proposal.run.phase2.demo.fake.v1.proposer, proposal.run.phase2.demo.fake.v1.verifier]
- Audit replay hash is `sha256:8c185deeb88a6e981bfd5376c868d62163a748f686bf04e5004b89c5d68bea9c`. [refs: run.phase2.demo.fake.v1]
- Verifier context `manifest.run.phase2.demo.fake.v1.verifier` has exact serialized hash `sha256:62b67e9db2fb06b8655dc8334a7552c8453f86978eb92b2d16aeea53aae5a46a`. [refs: manifest.run.phase2.demo.fake.v1.verifier]
- Verifier independence: context-isolated=`true`, separate-call=`true`, different-model=`false`, different-provider=`false`, fully-independent=`false`. [refs: manifest.run.phase2.demo.fake.v1.verifier]
