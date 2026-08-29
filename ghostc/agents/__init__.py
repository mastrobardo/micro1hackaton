"""Agent roles in the workflow. Contracts are frozen here; implementations land later.

EntityDiscoveryAgent
    in:  real repo, privacy.yaml, mapping store
    out: candidate entities [{id, kind, level, strategy, occurrences}]
    rule: never invents a replacement silently; reuses mapping identities;
          new `restricted` entities require human approval before use.

VerificationAgent
    in:  ghost repo, mapping store
    out: PASS | BLOCK + reasons
    rule: fail closed. BLOCK on any real value present in the ghost, any
          unresolved `restricted` entity, or a failing `yarn lint`.

PRConsistencyAgent
    in:  real diff, task text
    out: verdict + flags (unexpected real entities, scope drift)
    rule: advisory only; feeds a human review gate, never merges.
"""
