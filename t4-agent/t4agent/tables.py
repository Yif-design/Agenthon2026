"""Strict extraction of cutoff-safe observations from dated pipe tables."""

from __future__ import annotations

import csv
import math
import re
import statistics
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from .retrieve import IndexedCorpus
from .taskio import Task


DATE_HEADER_RE = re.compile(r"(?:[a-z]+_)*date", re.I)
NUMBER_RE = re.compile(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
CHANGE_TOKENS = {"change", "delta", "revision", "shift", "move"}
AMBIGUOUS_CHANGE_TOKENS = {"growth", "return"}
UNIT_TOKENS = {"bp", "bps", "basis", "point", "points", "pct", "percent", "percentage"}


@dataclass(frozen=True)
class TableRow:
    observation_date: str
    cells: tuple[str, ...]
    start: int
    end: int
    raw: str


@dataclass(frozen=True)
class DatedTable:
    header: tuple[str, ...]
    rows: tuple[TableRow, ...]


@dataclass(frozen=True)
class TableBaseline:
    value: float
    column: str
    unit: str
    doc_id: str
    quote: str
    observation_date: str
    statistic: str
    first: float
    previous: float | None
    last: float
    count: int
    median: float
    mad: float
    historical_min: float
    historical_max: float


def parse_dated_tables(text: str, cutoff: str, *, max_line_chars: int = 2000) -> list[DatedTable]:
    """Parse contiguous, increasing pipe tables without crossing malformed rows."""
    cutoff_date = _parse_date(cutoff)
    if cutoff_date is None:
        return []
    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)
    result: list[DatedTable] = []
    for index, line in enumerate(lines):
        header = _header(line.rstrip("\r\n"), max_line_chars)
        if header is None:
            continue
        row_index = index + 1
        if row_index < len(lines) and _is_separator(lines[row_index].rstrip("\r\n"), len(header)):
            row_index += 1
        rows: list[TableRow] = []
        previous_date: date | None = None
        invalid_order = False
        for current in range(row_index, len(lines)):
            raw = lines[current].rstrip("\r\n")
            cells = _pipe_cells(raw, max_line_chars)
            if cells is None or len(cells) != len(header):
                break
            observed = _parse_date(cells[0])
            if observed is None:
                break
            if observed > cutoff_date:
                break
            if previous_date is not None and observed <= previous_date:
                invalid_order = True
                break
            previous_date = observed
            start = offsets[current]
            rows.append(TableRow(cells[0], tuple(cells), start, start + len(raw), raw))
        if rows and not invalid_order:
            result.append(DatedTable(tuple(header), tuple(rows)))
    return result


def extract_generic_table_baseline(
    task: Task, entity: dict[str, Any], corpus: IndexedCorpus
) -> TableBaseline | None:
    """Return one unambiguous target-matched baseline, otherwise abstain."""
    target_name = str(task.target.get("name") or "")
    target_unit = _unit(str(task.target.get("unit") or task.target.get("units") or entity.get("unit") or entity.get("units") or ""))
    target_parts = _parts(target_name)
    if target_parts & AMBIGUOUS_CHANGE_TOKENS:
        return None
    base_parts = target_parts - CHANGE_TOKENS - UNIT_TOKENS - {"forecast", "prediction", "predicted", "next", "future"}
    identifiers = {_normalize(target_name)}
    for key in ("series_id", "series_fred"):
        value = entity.get(key) or task.target.get(key)
        if value:
            identifiers.add(_normalize(str(value)))
    identifiers.discard("")

    candidates: list[TableBaseline] = []
    for doc_id, text in corpus.doc_texts.items():
        if len(corpus.doc_texts) > 1 and not _doc_id_matches_entity(doc_id, entity):
            continue
        for table in parse_dated_tables(text, task.cutoff_date):
            matches: list[tuple[int, str, str]] = []
            for position, column in enumerate(table.header[1:], 1):
                normalized = _normalize(column)
                if normalized in identifiers:
                    matches.append((position, column, "last"))
                    continue
                column_parts = _parts(column)
                if target_parts & CHANGE_TOKENS and column_parts == base_parts:
                    matches.append((position, column, "last_minus_previous"))
                elif target_parts & CHANGE_TOKENS and column_parts - UNIT_TOKENS == base_parts:
                    matches.append((position, column, "last_minus_previous"))
            if len(matches) != 1:
                continue
            position, column, statistic = matches[0]
            values = [_number(row.cells[position]) for row in table.rows]
            if any(value is None for value in values):
                continue
            decimals = [value for value in values if value is not None]
            numeric = [float(value) for value in decimals]
            if statistic == "last_minus_previous" and len(numeric) < 2:
                continue
            source_unit = _unit_from_column_or_context(column, text, table.rows[0].start)
            effective_unit = target_unit or source_unit
            if not effective_unit or (target_unit and source_unit and target_unit != source_unit):
                if not (
                    statistic != "last"
                    and target_unit == "basis_points"
                    and source_unit == "percent"
                ):
                    continue
            value_decimal = decimals[-1] if statistic == "last" else decimals[-1] - decimals[-2]
            if target_unit == "basis_points" and source_unit == "percent" and statistic != "last":
                value_decimal *= Decimal("100")
                effective_unit = "basis_points"
            value = float(value_decimal)
            if not math.isfinite(value):
                continue
            median = statistics.median(numeric)
            deviations = [abs(item - median) for item in numeric]
            last_row = table.rows[-1]
            quote = last_row.raw
            if statistic == "last_minus_previous":
                quote = table.rows[-2].raw + "\n" + last_row.raw
            candidates.append(
                TableBaseline(
                    value=value,
                    column=column,
                    unit=effective_unit,
                    doc_id=doc_id,
                    quote=quote,
                    observation_date=last_row.observation_date,
                    statistic=statistic,
                    first=numeric[0],
                    previous=numeric[-2] if len(numeric) > 1 else None,
                    last=numeric[-1],
                    count=len(numeric),
                    median=median,
                    mad=statistics.median(deviations),
                    historical_min=min(numeric),
                    historical_max=max(numeric),
                )
            )
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: ((_parse_date(item.observation_date) or date.min).toordinal(), item.doc_id),
        reverse=True,
    )
    newest = candidates[0]
    if len(candidates) > 1 and _parse_date(candidates[1].observation_date) == _parse_date(newest.observation_date):
        return None
    return newest


def _pipe_cells(raw: str, max_chars: int) -> list[str] | None:
    if not raw or len(raw) > max_chars or "|" not in raw:
        return None
    try:
        cells = next(csv.reader([raw], delimiter="|", skipinitialspace=True, strict=True))
    except csv.Error:
        return None
    if raw.strip().startswith("|"):
        cells = cells[1:]
    if raw.strip().endswith("|"):
        cells = cells[:-1]
    return [cell.strip() for cell in cells]


def _header(raw: str, max_chars: int) -> list[str] | None:
    cells = _pipe_cells(raw, max_chars)
    if (
        cells is None
        or len(cells) < 2
        or any(not cell for cell in cells)
        or len({_normalize(cell) for cell in cells}) != len(cells)
        or DATE_HEADER_RE.fullmatch(cells[0]) is None
    ):
        return None
    return cells


def _is_separator(raw: str, width: int) -> bool:
    cells = _pipe_cells(raw, 2000)
    return cells is not None and len(cells) == width and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _parse_date(raw: str) -> date | None:
    try:
        if re.fullmatch(r"\d{4}-\d{2}", raw):
            return date.fromisoformat(raw + "-01")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return date.fromisoformat(raw)
    except ValueError:
        pass
    return None


def _number(raw: str) -> Decimal | None:
    if NUMBER_RE.fullmatch(raw) is None:
        return None
    try:
        value = Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None
    return value if value.is_finite() and abs(value) < Decimal("1e100") else None


def _normalize(value: str) -> str:
    return "".join(_tokens(value))


def _parts(value: str) -> set[str]:
    return set(_tokens(value))


def _tokens(value: str) -> list[str]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).replace("%", " percent ")
    return [part.lower() for part in re.findall(r"[A-Za-z0-9]+", separated)]


def _unit(value: str) -> str:
    tokens = _parts(value)
    if tokens & {"bps", "bp"} or {"basis", "points"} <= tokens:
        return "basis_points"
    if tokens & {"pct", "percent", "percentage"}:
        return "percent"
    if "ratio" in tokens:
        return "ratio"
    if "usd" in tokens and {"share", "per"} <= tokens:
        return "usd_per_share"
    if "usd" in tokens or tokens & {"dollar", "dollars"}:
        return "usd"
    if tokens & {"count", "number"}:
        return "count"
    return ""


def _unit_from_column_or_context(column: str, text: str, table_start: int) -> str:
    direct = _unit(column)
    if direct:
        return direct
    prior_line = text[:table_start].rstrip("\r\n").split("\n")[-1]
    match = re.fullmatch(re.escape(column) + r" observations in ([A-Za-z _%-]+)[.;]?", prior_line.strip(), re.I)
    return _unit(match.group(1)) if match else ""


def _doc_id_matches_entity(doc_id: str, entity: dict[str, Any]) -> bool:
    normalized_doc = _normalize(doc_id)
    identifiers = {
        _normalize(str(entity.get(key) or ""))
        for key in ("entity_id", "name", "ticker", "series_id", "series_fred")
    }
    return any(len(identifier) >= 3 and identifier in normalized_doc for identifier in identifiers)
