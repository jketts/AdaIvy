"""Phase 2 durable workspace and bounded baseline loop.

This package is an application/adapters layer around the unchanged Phase 1
trust core. Nothing here is imported by :mod:`math_research.domain`.
"""

PHASE2_SCHEMA_VERSION = "2.0.0"

# Providers admitted at the live model boundary, per ADR-0030. Defined once so
# the pricing validator, the live-run configuration validator, and both JSON
# schemas cannot drift apart. Adding a provider here does not enable it: live
# calls still require the live-gate acknowledgement, and a provider without an
# adapter and a pricing snapshot remains unreachable.
SUPPORTED_LIVE_PROVIDERS = frozenset({
    "anthropic",
    "azure_openai",
    "bedrock",
    "deepseek",
    "minimax",
    "openai",
    "qwen_dashscope",
})

