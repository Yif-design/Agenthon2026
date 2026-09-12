"""The three knobs the text module is allowed to turn.

This is the contract between the LLM/text stage (phase 3) and the statistical engine. The engine
never reads text; the text stage never touches draws. It only produces an `Adjustments` object:

* drift      — per asset, a shift of the distribution's centre, in units of the asset's
               *one-horizon standard deviation* at the shortest horizon (so "+0.3" means
               "move the centre up by 0.3 sd"). Applied linearly over the path.
* vol_mult   — per asset, a multiplier on the spread (1.0 = no change). >1 widens.
* scenarios  — optional branching: each scenario carries its own drift / vol_mult and a weight.
               Draws pick a scenario at random according to the weights, which produces a
               mixture (possibly multi-modal) rather than a single blob.
* tail_df    — optional Student-t degrees of freedom for an extra fat-tailed shock (None = off).

Rules from the organizers' playbook that the text stage must respect:
* only *established* facts (a decision taken, a print released) may lower vol_mult below 1;
  an *inferred* tone may move drift but must not narrow the distribution;
* when the corpus and the panel disagree, widen or split into scenarios — do not average.

`Adjustments.neutral()` is what phase 2 uses: no drift, no widening, one scenario.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Scenario:
    name: str
    weight: float
    drift: dict[str, float] = field(default_factory=dict)      # asset -> drift in horizon-sd units
    vol_mult: dict[str, float] = field(default_factory=dict)   # asset -> multiplier
    evidence: list[str] = field(default_factory=list)          # doc_ids that support it
    established: bool = False                                  # stated fact vs inferred tone


@dataclass
class Adjustments:
    scenarios: list[Scenario]
    tail_df: float | None = None
    stress_prob: float | None = None                           # prob. of a crisis-regime path (None = engine default)
    notes: list[str] = field(default_factory=list)             # free-text ledger lines for the rationale

    @classmethod
    def neutral(cls) -> "Adjustments":
        return cls(scenarios=[Scenario(name="baseline", weight=1.0)])

    def normalized(self) -> "Adjustments":
        total = sum(max(s.weight, 0.0) for s in self.scenarios)
        if total <= 0:
            return Adjustments.neutral()
        for s in self.scenarios:
            s.weight = max(s.weight, 0.0) / total
        return self

    def validate(self, assets: list[str]) -> list[str]:
        """Return a list of problems (empty = ok). Enforces the 'inferred must not narrow' rule."""
        problems: list[str] = []
        if self.stress_prob is not None and not (0.0 <= self.stress_prob <= 0.8):
            problems.append(f"stress_prob {self.stress_prob} outside [0, 0.8]")
        for s in self.scenarios:
            for a, m in s.vol_mult.items():
                if a not in assets:
                    problems.append(f"scenario {s.name!r}: unknown asset {a!r} in vol_mult")
                if m <= 0:
                    problems.append(f"scenario {s.name!r}: vol_mult for {a} must be > 0")
                if m < 1.0 and not s.established:
                    problems.append(
                        f"scenario {s.name!r}: narrows {a} (vol_mult={m}) but is not established"
                    )
            for a in s.drift:
                if a not in assets:
                    problems.append(f"scenario {s.name!r}: unknown asset {a!r} in drift")
        return problems
