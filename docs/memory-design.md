# Memory Design
* **Entities and Authorized Scopes**: Memories are isolated by `tenant` and `domain`. `account` acts as the relevance key.
* **Retained Event Types**: `observed_transition`, `successful_intervention`, `failed_intervention`, `fact`, `preference`, `rule_correction`.
* **Recall / Retention Triggers**: Hindsight semantic recall is triggered upon estimating a new order's timeline. Validated evidence is retained to the local store and Hindsight backend.
* **Correction and Conflicting-Fact Policy**: Explicit `superseded_by` rules take absolute precedence. Otherwise, the most recent confirmed claim wins.
* **Dependency-Outage Behavior**: If the Hindsight API is unavailable, the system falls back to scope-wide local typed hydration (`degraded=true`).
