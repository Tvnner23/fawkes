# Phoenix Research Evaluation

Research quality must be measured as a collection of inspectable properties,
not hidden behind one flattering aggregate score. These are capability-quality
measurements, not Phoenix personality measurements.

## Evaluation trace

A scenario evaluator consumes the same trace shape for deterministic fixtures
and future live runs:

```text
scenario expectation
  + routing decision
  + plan/subquestions/query history
  + provider attempts and sources
  + evidence assessments/contradictions/stopping decision
  + final answer and citation validation
  -> transparent per-dimension results
```

The framework currently reports:

- whether research routing was correct;
- whether the chosen simple/standard/deep mode matched the scenario;
- query-concept and subquestion coverage;
- logical searches, provider calls, and estimated model calls;
- preferred-domain source fraction;
- invented citation URLs;
- expected claim markers with nearby approved citations;
- contradiction recording;
- sufficiency/stopping correctness;
- adversarial instruction leakage.

No composite score is produced. A system that retrieves excellent sources but
misses a contradiction should not be able to hide that failure inside an
average.

## Baseline scenarios

The committed baseline spans:

- casual conversation that must not search;
- a simple current officeholder lookup;
- the LSUA catalog-versus-current-seven-week-schedule question;
- a multi-source contradiction that should remain unresolved when evidence is
  insufficient;
- hostile web content attempting to inject instructions.

Tests use deterministic providers and evidence fixtures so regressions are
repeatable, free, and independent of a changing web. `ResearchEvaluationRunner`
accepts an arbitrary execution adapter, allowing the same scenario contracts to
run live later. Live runs must be timestamped and interpreted as sampled
measurements rather than stable unit tests.

## Known measurement limits

Current production validation proves that visible Markdown citation URLs came
from approved research sources and that at least one approved citation is
present. Scenario fixtures can measure known claim coverage. General semantic
claim-to-source entailment is not solved yet; implementing it requires a
separate citation auditor or structured claim synthesis, plus calibration
against human-reviewed examples. URL validity must not be misrepresented as
proof that every claim is supported.

Future evaluation should add freshness calibration, source-locator quality,
human source judgments, provider comparisons, latency, token/tool cost,
abstention quality, and longitudinal regression reports. Those reports remain
research-system telemetry and must never become personality optimization input.
