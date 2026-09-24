# Jev Governor

A local-first coding-session governor: observe verified progress and inference usage, detect unproductive loops, and recommend when to continue, diagnose, escalate, or verify.

## Project status

This is a new research-and-developer-tool project. This initial commit establishes the repository; it is not a working application and contains no validated savings or trained policy.

The detailed implementation brief is being prepared on `bootstrap/project-brief` as a reviewable pull request. Coding agents should inspect open pull requests before starting, use that foundation if it remains unmerged, and avoid duplicating the documentation baseline.

## Direction

Train a small controller, not the coding model. Keep Jev optional as a semantic feature provider. The first useful product is an advisory companion for local Codex sessions with an evidence ledger, honest usage accounting, a deterministic baseline, and reproducible offline tests.

The longer-term research question is whether evidence-informed interventions can lower total cost per verified successful repository change without unacceptable regressions or extra human intervention. Controlled continuation experiments and held-out evaluation come before autonomous learned routing.

## Credentials

Offline development and synthetic demonstrations must require no API key and no paid calls. Live Jev evaluation requires a TypeSafe API key supplied locally as `TYPESAFE_API_KEY`; get it from the [TypeSafe dashboard](https://console.typesafe.ai). See the [official quick start](https://docs.typesafe.ai/introduction/quickstart).

Local Codex tests use the user's existing supported authentication. Do not copy login credentials into this repository, silently switch billing methods, or assume that the presence of a credential authorizes paid experiments.

## Non-negotiable boundaries

Keep verification requirements, authorization, sandbox settings, and budget permissions outside the learned policy. Model judgments and imported transcripts are not authoritative evidence of success. Missing usage is unknown, not zero. Synthetic demonstrations are not evidence of real-world savings.

Implementation work belongs on an isolated branch with tests and an open pull request. Do not merge, deploy, publish packages, or commit secrets without explicit owner authorization.
