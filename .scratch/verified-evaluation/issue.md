---
title: Verified local adapter evaluation and active inference
labels:
  - ready-for-human
---

# Verified local adapter evaluation and active inference

## Goal

Provide a concrete local Transformers and PEFT evaluator for trusted frozen calibration and holdout partitions, promote only when configured task-specific gates pass, and load the promoted adapter and matching calibrator in later labeling runs.

## Status

Implemented in the verified-evaluation branch. No model weights or real trusted data were used for validation. Local project runs still need to supply an approved model, trusted source, explicit training gate, labeling policy, and task-specific promotion policy.

## Evidence

- Calibration uses the exact score method label_json_mean_log_likelihood_v2.
- Candidate and incumbent are inferred on the same persisted calibration and holdout partitions.
- Calibrators are stored by task, policy ID, and exact model digest; the configured calibration_ref is a stable policy slot.
- Promotion checks evidence content hash, task and policy identity, frozen partition digests, candidate adapter files, calibrator identity, candidate/incumbent comparison, and configured gates.
- Failed prerequisites, inference, or gates do not change the active model pointer.
- Later label and run invocations resolve the active adapter and model-bound calibrator.
- Evaluation artifacts contain minimized row-level targets, predictions, scores, opaque refs, and reason codes for metric re-derivation; prompts, features, rationales, and source row identifiers are not persisted.
- Coverage is the applied holdout fraction after rule, inference, staleness, calibration, and threshold checks; invalid results count as non-applied.
- Existing partition manifests and JSONL bytes are rebuilt from the freshly loaded registered trusted snapshot and compared before reuse.
- Cycle idempotency includes trusted snapshot, task spec, labeling policy, training gate, promotion policy, and active incumbent identity.
- Training gate digest is rechecked immediately before promotion; if authorization changes during training/evaluation the candidate is rejected and the active pointer is preserved.
- SHA-256 provides local content integrity only, not an authenticated evaluator attestation; registry promotion recomputes the metrics from persisted row-level evidence.
- Registry binds both ordered candidate/incumbent evidence rows to the exact frozen holdout JSONL targets, manifest refs, and per-row input digests; extra, missing, duplicate, or modified rows fail closed.
- See docs/verified-training-cycle.md for configuration and paths.

## Manual checks

- python3 -m compileall -q src
- git diff --check
- A temporary synthetic project without a promotion policy produced the explicit promotion_policy_missing blocked state; the seeded active pointer's bytes remained unchanged.
- Synthetic row-evidence recomputation: applied coverage 1/4 with one confident correct prediction, one below-threshold prediction, one invalid output, and one rule conflict; edited `applied` evidence was rejected.
- Synthetic frozen-manifest validation: unchanged regenerated manifest and partition bytes were accepted; edited holdout bytes and edited manifest were rejected.
- Synthetic evaluation-to-holdout binding: matching ordered refs/digests/targets were accepted; changed target, changed ref, changed input digest, reordered, and extra evidence rows were rejected.
- Synthetic cycle identity checks: unchanged identity was idempotent; changing each of snapshot/task/policy/gate/incumbent returned no prior cycle.
- Synthetic revoked-gate check: modifying the gate after its initial digest caused the pre-promotion check to fail while the active pointer remained byte-identical.
- Evaluation privacy metadata explicitly identifies minimized row-level evidence rather than claiming aggregate-only evidence.

No automated tests, model downloads, or real dataset evaluation were run.
