from __future__ import annotations

from typing import Any

from ..family_specs import FamilySpec
from ..retrieve import IndexedCorpus
from ..taskio import Task
from .auction import solve as solve_auction
from .bank_eps import extract_parameters as extract_bank_eps_parameters
from .bank_eps import solve as solve_bank_eps
from .common import ModelOutput
from .cpi import solve as solve_cpi
from .credit import solve as solve_credit
from .eps_consensus import solve as solve_eps_consensus
from .eps_yoy import solve as solve_eps_yoy
from .generic import solve as solve_generic
from .macro_revision import solve as solve_macro_revision
from .positioning import solve as solve_positioning
from .rates import solve as solve_rates
from .reaction import solve as solve_reaction


SOLVERS = {
    "eps_consensus": solve_eps_consensus,
    "eps_yoy": solve_eps_yoy,
    "bank_eps": solve_bank_eps,
    "credit": solve_credit,
    "reaction": solve_reaction,
    "rates": solve_rates,
    "cpi": solve_cpi,
    "macro_revision": solve_macro_revision,
    "auction": solve_auction,
    "positioning": solve_positioning,
    "generic": solve_generic,
}


def extract_parameters(
    entity: dict[str, Any], spec: FamilySpec, corpus: IndexedCorpus
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Run family-owned deterministic extractors before asking the model."""
    if spec.key == "bank_eps":
        return extract_bank_eps_parameters(entity, corpus)
    return {}, []


def solve(
    task: Task,
    entity: dict[str, Any],
    spec: FamilySpec,
    signals: dict[str, int],
    parameters: dict[str, float | None],
    corpus: IndexedCorpus,
    row_index: int,
    row_count: int,
) -> ModelOutput:
    solver = SOLVERS.get(spec.key, solve_generic)
    return solver(task, entity, signals, parameters, corpus, row_index, row_count)
