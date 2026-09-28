# Cross-family error matrix — 2026-09-28 v2

Baseline commit: `848f18df6ec57cd9e1c7ed409591eb01441ff38a`.

This matrix summarizes current evidence after the direct/hybrid, retrieval, typed-schema, citation,
calibration and House-failure experiments. Public smoke is an interface gate, not outcome accuracy.

| Layer | Shared evidence | Current failure or uncertainty | Families / target types | Priority |
|---|---|---|---|---|
| L1 architecture | Signal extraction plus deterministic solvers beats tested direct and 50/50 hybrid variants; baseline is written before network calls | Official Development House is unavailable, so end-to-end production behavior remains approximate | All | Monitor |
| L1/L2 API | 25-call cap, retry/circuit logic, context-local recovery and single-row splitting have deterministic fault coverage | Deferred single-row recovery protects normal batches, but no published serving context ceiling exists | Model-required classification, regression and unknown ranking | Medium |
| L2 routing | Anchored names plus unique complete structural signatures recover known shapes and reject collisions | Renamed tasks with changed or partial fields remain generic by design | All target types | Medium |
| L2 retrieval | Scope/router alignment, punctuation, semantic schema terms, prompt terms and exact-score recency ties are accepted | Lexical aliases and paraphrases remain unresolved; broad query changes caused citation churn | All; strongest uncertainty on unknown families | High when independently labelable |
| L2 evidence | Exact quote, document scope, span and numeric containment fail closed; saved official NLI lower bound covers all public units | Evidence-ID remains deferred; formatting-only recovery covered classification only, and quote-local context supplied unique identity-plus-target terms only for CPI regression; the official NLI pair still has no remote path | EPS, credit, rates and CPI; classification and regression | High, deferred until broader saved or remote evidence |
| L2 unknown schema | Generic scalar projection, target-aware baselines, explicit-unit validation, arbitrary-label role mapping and prompt/schema retrieval are accepted; an explicit matched change baseline now uses a cross-domain development-selected 0.5 shrinkage | Fraction-to-percent normalization restored semantic scale but worsened CPI/COT MAE; generic classification/direction quality remains unmeasured | Unknown classification, regression and ranking | High |
| L3 classification | Deterministic labels are schema-safe; post-earnings ticker prior improved held-out accuracy | Post-earnings candidate lacks fresh prediction-bound NLI; direct labels underperformed | Reaction and unknown classification | High but faithfulness-blocked |
| L3 regression | Target-aware generic baselines avoid unrelated metadata; shared change shrinkage improves CPI and macro-revision MAE on test and confirmation periods | No common learned tabular baseline or calibrated selector; real outcome support varies by family | Bank EPS, rates, CPI, auction, macro revision | Medium |
| L3 ranking | Point forecasts and rank permutation are normalized correctly; positive change shrinkage improves COT point MAE while preserving Spearman exactly | Only COT has real outcome diagnostics | Positioning and unknown ranking | Medium |
| L3 intervals | EPS YoY and several family intervals have time-split calibration evidence | Bank interval candidate needs new NLI; rates confirmation did not distinguish candidate | Regression and numeric classification | Medium |
| L4 family | CPI, auction, COT and EPS calculators have recorded historical panels | Rates and public post-earnings point quality remain weak; macro age matching and bank damping were rejected | Rates, reaction, macro revision, bank EPS | High after shared candidates |

Next-selection rule: first seek an L2 candidate with deterministic cross-family evidence and unchanged
prediction hypotheses. If none is falsifiable without new NLI, move to a family outcome model whose
held-out metric and citations can both be evaluated without heavy local inference.
