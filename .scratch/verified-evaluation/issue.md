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
- Evaluation artifacts contain aggregate metrics and hashes only; prompts, features, rationales, and source row identifiers are not persisted in evaluation evidence.
- See docs/verified-training-cycle.md for configuration and paths.

## Manual checks

- python3 -m compileall -q src
- git diff --check
- A temporary synthetic project without a promotion policy produced the explicit promotion_policy_missing blocked state; the seeded active pointer's bytes remained unchanged.

No automated tests, model downloads, or real dataset evaluation were run.
