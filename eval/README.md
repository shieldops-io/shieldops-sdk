# Evaluation harness (placeholder)

This directory will host the public-facing eval harness for the F1
intent-inference scorer cascade described in PRD-009. The harness is
scheduled to land **post-v1.0 GA**; this README is a placeholder so the
directory exists in the carved-out public repository and downstream
links resolve.

## Expected contents (post-GA)

| Component | Purpose |
|-----------|---------|
| `adapters/agentdojo.py`  | Adapter for [AgentDojo](https://agentdojo.spylab.ai/) benchmarks. |
| `adapters/injecagent.py` | Adapter for the INJECAGENT prompt-injection suite. |
| `adapters/toolemu.py`    | Adapter for [ToolEmu](https://toolemu.com/) tool-call hazard scenarios. |
| `adapters/advbench.py`   | Adapter for AdvBench jailbreak prompts. **Eval-only, never replayed into production.** |
| `scorer/`                | F1 scorer cascade: intent inference, policy decision, outcome evaluator. |
| `scripts/`               | Reproducibility scripts: seed pinning, dataset hashes, result artifact upload. |
| `fixtures/`              | Small curated snippets used by unit tests. Large datasets are fetched at eval time and cached. |

## Why this directory exists now

Publishing the eval harness alongside the SDK is a deliberate product
decision, not a marketing move. It lets customers and independent
researchers reproduce our safety claims on their own infrastructure,
which is load-bearing for the F1 primitive's trust story. Shipping the
directory skeleton with v0.9.0-pre keeps the future import paths
stable.

## Before the harness lands

- Do **not** copy proprietary benchmarks into this directory. All
  adapters must fetch datasets from their upstream source at runtime.
- AdvBench and similar jailbreak corpora are evaluation inputs only.
  They must never be committed, logged, or replayed into production
  pipelines.
- Reproducibility scripts pin the Python version, dataset revision,
  model version, and random seeds. We publish the result JSON and the
  hash of every input artifact.

Track progress in the PRD-009 epic.
