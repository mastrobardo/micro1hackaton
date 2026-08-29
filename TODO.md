# Privacy Agent — Long-Term Goal & Development Roadmap

## Long-term goal

Build a **privacy-preserving software delivery bridge** that allows external AI coding agents to work effectively on private and client-owned codebases without exposing information that must remain inside the company trust boundary.

The system should maintain a **persistent, semantically useful ghost representation of a real repository**.

The ghost repository should:

* preserve the structure and behaviorally relevant semantics of the real repository;
* remove, replace, or abstract information according to company privacy policy;
* remain usable by ordinary coding agents such as Codex or Copilot;
* be continuously synchronized with the real repository;
* never expose the real-to-ghost mapping outside the company trust boundary;
* provide an auditable record of what information was transformed and why;
* allow a coding agent to work autonomously on the ghost repository;
* translate the resulting changes back into a real repository PR;
* verify that the resulting real PR is consistent with the original task and privacy policy;
* provide humans with clear approval points whenever risk or ambiguity warrants intervention.

The ultimate workflow should be:

```text
Jira / task specification
        │
        ▼
Company-side planning agent
        │
        │ understands real repository
        ▼
Implementation plan
        │
        ▼
Human approval
        │
        ▼
Privacy compiler
        │
        ├── AST / code graph
        ├── entity detection
        ├── privacy classification
        ├── semantic transformation
        └── mapping
        │
        ▼
Persistent Ghost Repository
        │
        ▼
Sanitized implementation specification
        │
        ▼
External coding agent
        │
        ▼
Ghost PR
        │
        ▼
Patch / reverse compiler
        │
        ▼
Real PR
        │
        ▼
Evaluation / verification
        │
        ▼
Human review
        │
        ▼
Merge
        │
        ▼
Incremental Ghost Repository synchronization
```

The system should ultimately make the privacy boundary explicit:

```text
                    COMPANY TRUST BOUNDARY
─────────────────────────────────────────────────────

Real repository
Jira
Company agents
Privacy policies
Real ↔ Ghost mappings
Evaluation
Audit logs
Secrets

────────────────────── PRIVACY BOUNDARY ─────────────

                    EXTERNAL AI

Ghost repository
Ghost specification
Ghost PR
Sanitized dependencies/context

─────────────────────────────────────────────────────
```

The external agent should never require access to the real repository or the real mapping.

---

# Guiding principles

These principles should guide implementation decisions throughout the project.

## 1. Privacy by construction

Do not rely primarily on asking an external model to "not look at" sensitive information.

The external agent should receive a repository that is already safe to expose.

## 2. Semantic preservation over redaction

Prefer:

```text
Stripe → PaymentProviderA
```

over:

```text
Stripe → REDACTED
```

when the former preserves useful implementation semantics without exposing the real entity.

The objective is not merely to hide strings. It is to preserve enough meaning for software development.

## 3. Full ghost repository first

The primary model is a complete, persistent ghost repository.

Do not make task-specific repository slicing a prerequisite for the core architecture.

Task-specific projections may become a later optimization.

## 4. Stable mappings

A real entity should have a stable ghost identity.

For example:

```text
Stripe
    ↓
PaymentProviderA
```

should remain consistent across files, branches, PRs and synchronization runs.

## 5. Incremental synchronization

The initial repository analysis may be expensive.

After initialization, synchronization should operate primarily on changes introduced by merged PRs rather than recompiling the entire repository.

## 6. External agents should behave normally

The ghost repository should look like an ordinary Git repository.

Avoid requiring external coding agents to use a proprietary filesystem or specialized API unless a later security requirement makes this necessary.

## 7. Human approval at consequential boundaries

Automate routine transformations.

Require human approval when:

* classification is ambiguous;
* a new sensitive entity is discovered;
* a transformation could materially change semantics;
* an external AI task is about to be released;
* a resulting real PR has unexpected changes.

## 8. Everything important must be observable

The system must make it possible to answer:

* What was transformed?
* Why was it transformed?
* Which policy caused the transformation?
* Which files were affected?
* Which mappings were used?
* Which ghost files were exposed to the external agent?
* What did the external agent change?
* What was translated back?
* Were any policy violations detected?
* Which human approved the operation?

Monitoring and auditability are first-class features, not post-hoc additions.

---

# Roadmap

## Phase 0 — Foundation and documentation

### Goal

Establish the project structure, contracts and security model before adding complexity.

### Tasks

* [ ] Define repository architecture.
* [ ] Define terminology:

  * [ ] real repository
  * [ ] ghost repository
  * [ ] ghost branch
  * [ ] mapping
  * [ ] entity
  * [ ] privacy policy
  * [ ] privacy compiler
  * [ ] reverse compiler
  * [ ] evaluator
* [ ] Define trust boundaries.
* [ ] Define what information is allowed to leave the company boundary.
* [ ] Define initial privacy levels:

  * [ ] public
  * [ ] internal
  * [ ] confidential
  * [ ] restricted
* [ ] Document security assumptions.
* [ ] Document known limitations.
* [ ] Define configuration schema.
* [ ] Define mapping schema.
* [ ] Define audit event schema.
* [ ] Define versioning strategy for mappings and transformations.
* [ ] Create `README.md`.
* [ ] Create `ARCHITECTURE.md`.
* [ ] Create `SECURITY.md`.
* [ ] Create `ROADMAP.md`.
* [ ] Create `THREAT_MODEL.md`.
* [ ] Create `PRIVACY_POLICY.md` describing the initial classification model.

### Exit criteria

A new contributor should be able to understand:

```text
what the system does
why it exists
what crosses the privacy boundary
what must never cross it
how the major components interact
```

without reading implementation code.

---

# Phase 1 — Deterministic whole-repository privacy compiler

### Goal

Create the first working compiler:

```text
real repo + config
       ↓
ghost repo
```

### Tasks

* [ ] Implement Python CLI.
* [ ] Accept input repository.
* [ ] Accept output repository.
* [ ] Accept privacy configuration.
* [ ] Scan the complete repository.
* [ ] Implement default exclusions.
* [ ] Build initial Python AST representation.
* [ ] Build lightweight code graph.
* [ ] Detect configured entities.
* [ ] Implement deterministic transformations.
* [ ] Implement stable mappings.
* [ ] Preserve repository structure.
* [ ] Create fresh Git repository in output.
* [ ] Never copy the original `.git` directory by default.
* [ ] Keep mapping outside the ghost repository.
* [ ] Implement dry-run mode.
* [ ] Implement deterministic output.
* [ ] Add unit tests.
* [ ] Add fixture repositories.
* [ ] Add integration tests.

### Exit criteria

Given:

```text
real-repository/
```

and:

```text
privacy.yaml
```

the tool reliably produces:

```text
ghost-repository/
```

which is independently usable as a Git repository and contains no configured sensitive information in its original representation.

---

# Phase 2 — Privacy entity model and semantic transformation

### Goal

Move from string replacement toward a real privacy/entity model.

### Tasks

* [ ] Define entity types.
* [ ] Define sensitivity levels.
* [ ] Define transformation strategies.
* [ ] Define entity identity independent from replacement text.
* [ ] Detect entities through code context.
* [ ] Track occurrences across files.
* [ ] Track relationships between entities and symbols.
* [ ] Preserve identifiers where semantics require them.
* [ ] Handle filenames.
* [ ] Handle configuration files.
* [ ] Handle documentation.
* [ ] Handle environment variable names.
* [ ] Handle URLs.
* [ ] Handle IP addresses.
* [ ] Handle service names.
* [ ] Handle vendor names.
* [ ] Handle commercial relationships.
* [ ] Avoid corrupting unrelated strings/identifiers.
* [ ] Add transformation provenance.

Example:

```text
entity_id: vendor_001
real: Stripe
ghost: PaymentProviderA
kind: vendor
sensitivity: commercial
strategy: semantic
```

### Exit criteria

The ghost repository is not merely redacted; it is a coherent representation that retains useful software semantics.

---

# Phase 3 — Company-provided assisting model

### Goal

Introduce an internal/company-controlled AI capability without allowing the external coding agent to access real information.

The internal assisting model should operate **inside the company trust boundary**.

### Tasks

* [ ] Define `EntityClassifier` interface.
* [ ] Define `TransformationPlanner` interface.
* [ ] Keep deterministic implementation as fallback.
* [ ] Add company-provided AI implementation.
* [ ] Send only required repository context to the internal AI tool.
* [ ] Ask the model to classify ambiguous entities.
* [ ] Ask the model to recommend semantic replacements.
* [ ] Validate model output against schemas.
* [ ] Require deterministic validation before applying transformations.
* [ ] Record model decisions in audit logs.
* [ ] Make AI-assisted decisions reproducible where practical.
* [ ] Support human override.
* [ ] Never send the mapping or real repository to an external coding agent.

### Exit criteria

Ambiguous entities can be classified by a company-controlled assisting model while the external AI boundary remains unchanged.

---

# Phase 4 — Persistent Ghost Repository

### Goal

Turn the one-shot compiler into a persistent mirror.

```text
real/main
    ↕
ghost/main
```

where `ghost/main` is continuously synchronized and privacy-safe.

### Tasks

* [ ] Define synchronization model.
* [ ] Store ghost repository identity.
* [ ] Associate real commits with ghost commits.
* [ ] Detect merged PR changes.
* [ ] Transform only changed files where safe.
* [ ] Detect deleted files.
* [ ] Detect renamed files.
* [ ] Detect moved symbols.
* [ ] Update mappings incrementally.
* [ ] Detect newly introduced sensitive entities.
* [ ] Block synchronization on unresolved restricted entities.
* [ ] Support mapping versioning.
* [ ] Handle mapping changes safely.
* [ ] Detect ghost/real divergence.
* [ ] Implement reconciliation.
* [ ] Add synchronization audit events.
* [ ] Add recovery mechanism after failed synchronization.

### Exit criteria

After initial bootstrap:

```text
real/main
```

and:

```text
ghost/main
```

remain synchronized through normal repository merges without requiring full repository recompilation.

---

# Phase 5 — Specification compiler

### Goal

Allow a company-side agent to transform a real implementation task into a ghost-safe implementation specification.

Input:

```text
Jira issue
+
real repository
```

Output:

```text
ghost implementation specification
```

### Tasks

* [ ] Define implementation-spec schema.
* [ ] Read Jira issue.
* [ ] Analyze real repository.
* [ ] Identify affected architecture.
* [ ] Identify affected files.
* [ ] Identify relevant interfaces/contracts.
* [ ] Produce implementation plan.
* [ ] Identify privacy-sensitive references.
* [ ] Translate real entities into ghost entities.
* [ ] Preserve API contracts.
* [ ] Preserve behavioral requirements.
* [ ] Remove unnecessary real-world context.
* [ ] Validate that the specification is understandable without real entity names.
* [ ] Store original specification only inside company boundary.
* [ ] Store ghost specification separately.
* [ ] Add human approval step.

Example:

```text
REAL SPECIFICATION

Replace Stripe with PayPal.
Preserve PaymentService semantics.
Implement PayPal webhooks.
```

becomes:

```text
GHOST SPECIFICATION

Replace PaymentProviderA with PaymentProviderB.
Preserve PaymentService semantics.
Implement ProviderB webhook contract.
```

### Exit criteria

An external coding agent can implement the task from the ghost specification without receiving the original sensitive specification.

---

# Phase 6 — External coding-agent integration

### Goal

Allow Codex/Copilot or another coding agent to work normally on the ghost repository.

### Tasks

* [ ] Define external agent contract.
* [ ] Create ghost feature branch from ghost/main.
* [ ] Provide ghost implementation specification.
* [ ] Allow external coding agent to clone/use the ghost repository.
* [ ] Ensure real repository credentials are unavailable.
* [ ] Ensure mapping store is unavailable.
* [ ] Restrict external network access to approved services.
* [ ] Capture agent execution metadata.
* [ ] Capture commands where infrastructure allows.
* [ ] Capture file modifications.
* [ ] Capture final Git diff.
* [ ] Create ghost PR.
* [ ] Record task/branch/commit relationships.

### Exit criteria

The external coding agent can autonomously implement a realistic task using only:

```text
ghost repository
+
ghost specification
```

---

# Phase 7 — Monitoring, audit and observability

### Goal

Make every important privacy operation observable.

This phase is mandatory and should not be postponed until after the core product works.

### Tasks

* [ ] Define structured audit events.
* [ ] Generate unique operation IDs.
* [ ] Track repository compilation.
* [ ] Track synchronization operations.
* [ ] Track entity detection.
* [ ] Track transformations.
* [ ] Track mapping creation.
* [ ] Track mapping changes.
* [ ] Track human approvals.
* [ ] Track ghost branches.
* [ ] Track ghost PRs.
* [ ] Track external agent executions.
* [ ] Track files exposed to external agents.
* [ ] Track files modified by external agents.
* [ ] Track reverse translations.
* [ ] Track rejected operations.
* [ ] Track policy violations.
* [ ] Track unresolved entities.
* [ ] Avoid logging sensitive values.
* [ ] Define log retention.
* [ ] Define access controls for audit data.

Useful metrics:

```text
repository_files
ghost_files
files_transformed
entities_detected
entities_transformed
new_entities
unresolved_entities
files_exposed
sensitive_entities_exposed
ghost_prs
real_prs
translation_failures
policy_blocks
human_approvals
```

A particularly important metric:

```text
sensitive information exposed to external AI
```

The desired value should be:

```text
0
```

### Exit criteria

For every external AI task, we can reconstruct:

```text
what task was requested
what information was exposed
why it was exposed
what the agent changed
what was translated back
who approved consequential operations
```

without exposing sensitive information through the monitoring system itself.

---

# Phase 8 — Reverse / Patch compiler

### Goal

Translate a ghost PR into a real PR.

Do not simply "deanonymize the repository."

Translate the **patch**.

```text
ghost PR
   ↓
patch compiler
   ↓
real PR
```

### Tasks

* [ ] Parse ghost diff.
* [ ] Resolve ghost entities.
* [ ] Resolve stable mappings.
* [ ] Validate mapping version.
* [ ] Apply patch to correct real commit.
* [ ] Handle changed identifiers.
* [ ] Handle changed filenames.
* [ ] Handle configuration.
* [ ] Handle deleted files.
* [ ] Handle newly created files.
* [ ] Detect unmapped ghost entities.
* [ ] Detect unexpected real entities.
* [ ] Reject ambiguous translations.
* [ ] Generate real PR.
* [ ] Record translation provenance.
* [ ] Preserve the ghost PR as an audit artifact.

### Exit criteria

A realistic ghost PR becomes a clean, reviewable real PR with no manual deanonymization required.

---

# Phase 9 — Evaluation and verification

### Goal

Determine whether privacy transformation and reverse translation preserve the properties we care about.

This should be implemented as a separate component rather than embedding evaluation into the privacy compiler.

### Evaluate privacy

* [ ] Search ghost repository for known sensitive values.
* [ ] Detect accidental leakage.
* [ ] Detect mapping leakage.
* [ ] Detect secrets.
* [ ] Detect sensitive filenames.
* [ ] Detect sensitive configuration.
* [ ] Detect sensitive comments/documentation.
* [ ] Test external network boundaries.

### Evaluate semantic preservation

* [ ] Compare repository structure.
* [ ] Compare AST-level properties.
* [ ] Compare public interfaces.
* [ ] Compare dependency relationships.
* [ ] Compare buildability.
* [ ] Run tests where possible.
* [ ] Compare test behavior.
* [ ] Detect broken imports.
* [ ] Detect broken configuration.

### Evaluate coding-agent effectiveness

Measure:

```text
task success
time to completion
number of iterations
number of context requests
number of failed builds
number of human interventions
```

Compare:

```text
real repository
vs
ghost repository
```

where doing so is safe and useful for controlled evaluation.

### Exit criteria

We can provide evidence that:

1. sensitive information is not leaked;
2. the ghost repository remains useful;
3. external agents can perform meaningful work;
4. translated patches remain correct.

---

# Phase 10 — GitHub / Jira workflow integration

### Goal

Make the system fit into the team's existing workflow.

### GitHub

* [ ] GitHub Action for ghost synchronization.
* [ ] GitHub Action for task creation.
* [ ] Ghost branch creation.
* [ ] Ghost PR creation.
* [ ] Real PR creation.
* [ ] Status checks.
* [ ] PR comments.
* [ ] Human approval through GitHub.
* [ ] Link Jira issue ↔ real PR ↔ ghost task.

### Jira

* [ ] Read issue specification.
* [ ] Link issue to task.
* [ ] Report status.
* [ ] Link real PR.
* [ ] Optionally expose privacy status.
* [ ] Keep sensitive mappings out of Jira.

Desired developer experience:

```text
Jira issue
    ↓
Approve plan
    ↓
Ghost task runs
    ↓
External coding agent works
    ↓
Normal real PR appears
    ↓
Developer reviews normally
```

The developer should not need to manually manage ghost branches.

---

# Phase 11 — Production security hardening

### Goal

Move from prototype security assumptions to a defensible production architecture.

### Tasks

* [ ] Threat model external AI provider.
* [ ] Threat model compromised coding agent.
* [ ] Threat model compromised ghost repository.
* [ ] Threat model mapping store.
* [ ] Threat model CI infrastructure.
* [ ] Secure mapping storage.
* [ ] Encryption at rest.
* [ ] Encryption in transit.
* [ ] Credential isolation.
* [ ] Short-lived credentials.
* [ ] External network allowlisting.
* [ ] Secret scanning.
* [ ] Access control.
* [ ] Audit log protection.
* [ ] Mapping rotation/versioning.
* [ ] Incident response procedure.
* [ ] Data retention policy.
* [ ] Repository deletion policy.
* [ ] Secure cleanup of temporary workspaces.
* [ ] Security tests.
* [ ] Dependency scanning.
* [ ] Supply-chain controls.

---

# Phase 12 — Performance and scale

### Goal

Make the architecture viable for large consultancy repositories.

### Tasks

* [ ] Benchmark initial bootstrap.
* [ ] Benchmark incremental synchronization.
* [ ] Cache AST analysis.
* [ ] Cache code graph.
* [ ] Incrementally update graph.
* [ ] Parallelize file analysis.
* [ ] Optimize entity detection.
* [ ] Optimize transformations.
* [ ] Measure memory consumption.
* [ ] Measure repository size overhead.
* [ ] Test monorepositories.
* [ ] Test large multi-language repositories.

Important target:

```text
Initial bootstrap:
acceptable one-time cost

Normal PR merge:
incremental and fast
```

---

# Phase 13 — Multi-language support

### Goal

Support the languages used by real consultancy projects.

### Tasks

* [ ] Introduce Tree-sitter or equivalent parser abstraction.
* [ ] TypeScript.
* [ ] JavaScript.
* [ ] Java.
* [ ] Go.
* [ ] C#.
* [ ] SQL.
* [ ] YAML/JSON/TOML.
* [ ] Shell.
* [ ] Dockerfiles.
* [ ] Infrastructure-as-code.

Maintain a language-independent entity and mapping model.

---

# Phase 14 — Advanced privacy transformations

### Goal

Handle information that cannot safely be represented through simple aliases.

Potential strategies:

```text
literal replacement
semantic alias
synthetic identifier
synthetic endpoint
synthetic IP
structural transformation
aggregation
generalization
removal
```

Examples:

```text
Stripe
    → PaymentProviderA

10.42.18.13
    → PRIVATE_IP_001

client-prod-eu-west-1
    → production-region-A

customer ACME Corporation
    → CustomerA
```

Investigate where semantic preservation requires more than string substitution.

---

# Phase 15 — Adaptive/task-specific privacy projection

This is optional and should come only after the full ghost repository works reliably.

### Goal

Reduce the amount of information exposed to an external agent while preserving its ability to complete a task.

Potential architecture:

```text
ghost/main
    ↓
task analysis
    ↓
minimal relevant projection
    ↓
external agent
```

Use the code graph to identify relevant context.

Monitor:

* files exposed;
* entities exposed;
* dependency distance;
* agent requests for additional context.

Do not make this a prerequisite for the core architecture.

The persistent full ghost repository remains the source of truth.

---

# Phase 16 — Continuous privacy verification

### Goal

Treat privacy as a continuously enforced invariant.

For every synchronization:

```text
real change
    ↓
transform
    ↓
privacy scan
    ↓
policy verification
    ↓
ghost/main
```

Never update `ghost/main` if verification fails.

Potential checks:

```text
known sensitive values
known secrets
mapping leakage
unexpected identifiers
new external endpoints
new vendors
new internal services
new client information
```

A failed privacy check should produce:

```text
SYNC BLOCKED
Reason:
New restricted entity detected

Human review required.
```

---

# Definition of the final system

The mature system should provide this experience:

```text
Developer
    │
    ▼
Jira issue
    │
    ▼
Company planning agent
    │
    ▼
Human approval
    │
    ▼
Ghost task generated
    │
    ├── ghost specification
    └── ghost feature branch
            │
            ▼
      External coding agent
            │
            ▼
        Ghost PR
            │
            ▼
      Privacy/effect checks
            │
            ▼
       Patch compiler
            │
            ▼
          Real PR
            │
            ▼
        Human review
            │
            ▼
           Merge
            │
            ▼
     Incremental ghost sync
            │
            ▼
        Ghost main
```

At no point should the external coding agent require:

```text
real repository
real Jira details
real client names
real internal service names
real commercial relationships
real credentials
real mapping
```

The system should make the privacy boundary technically enforceable, observable and auditable rather than relying solely on model instructions.

---

# Near-term implementation order

Do not attempt to implement the entire roadmap at once.

The recommended immediate sequence is:

```text
1. Whole-repository deterministic compiler
        ↓
2. Stable entity/mapping model
        ↓
3. AST/code graph
        ↓
4. Semantic transformations
        ↓
5. Company-provided assisting model
        ↓
6. Persistent ghost/main synchronization
        ↓
7. Monitoring + audit
        ↓
8. Ghost task/specification generation
        ↓
9. External coding agent
        ↓
10. Reverse patch compiler
        ↓
11. Evaluation
        ↓
12. GitHub/Jira automation
```

Every phase should produce a usable artifact and should not require the next phase to exist.

---

# What success looks like

The project is successful if we can demonstrate a realistic task such as:

```text
Jira:

"Replace Stripe with PayPal"
```

and execute:

```text
real repository
      ↓
company agent understands task
      ↓
human approves
      ↓
ghost repository

Stripe
   ↓
PaymentProviderA

PayPal
   ↓
PaymentProviderB

      ↓
external coding agent
      ↓
ghost PR

PaymentProviderA
   ↓
PaymentProviderB

      ↓
reverse patch compiler
      ↓
real PR

Stripe
   ↓
PayPal

      ↓
normal developer review
```

while demonstrating that:

```text
✓ external agent never receives Stripe
✓ external agent never receives the real client identity
✓ external agent never receives the mapping
✓ ghost repository remains usable
✓ changes can be translated back
✓ every privacy transformation is auditable
✓ every consequential operation has an appropriate approval point
✓ merged changes can incrementally update ghost/main
```

The long-term goal is therefore not simply **"anonymize code."**

It is:

> **Create a continuously synchronized, privacy-safe software representation that lets external AI agents participate in software development without crossing the company's information boundary.**
