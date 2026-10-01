from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
import yaml

from ..errors import UnknownDomain
from ..schemas import Invariant
from .guard import referenced_names

_DOMAIN_NAME = re.compile(r"^[a-z][a-z0-9_]{0,40}$")

class _SafeDict(dict):
    def __missing__(self, key):
        return "unknown"

@dataclass
class Domain:
    name: str
    initial_state: str
    terminal_state: str
    metric_name: str
    metric_unit: str
    deviation_tolerance: float
    min_support: int
    invariants: list
    guard_hypotheses: dict
    confidence_buffer_threshold: float
    conservative_buffer: float
    recall_limit: int
    recall_query_template: str
    hard_keys: list = field(default_factory=list)
    interventions: dict = field(default_factory=dict)
    recency_half_life_days: float = 30.0
    projection: str = ""
    projection_start_field: str = ""
    required_state_fields: set = field(default_factory=set)
    raw: dict = field(repr=False, default_factory=dict)

    def guard_specificity(self, guard_id: str) -> int:
        return self.guard_hypotheses.get(guard_id, {}).get("specificity", 0)

    def guard_expression(self, guard_id: str) -> str:
        return self.guard_hypotheses.get(guard_id, {}).get("expression", "true")

    def render_recall_query(self, state: dict, scope=None) -> str:
        """Fill the YAML template from scope + state. Missing fields render as
        'unknown' rather than aborting the whole substitution (the old behaviour
        sent the raw '{account}' template to Hindsight)."""
        ctx = _SafeDict()
        if scope is not None:
            ctx.update({k: v for k, v in scope.model_dump().items() if v is not None})
        ctx.update(state)
        try:
            return self.recall_query_template.format_map(ctx)
        except (ValueError, IndexError, AttributeError):
            return self.recall_query_template

    @classmethod
    def load(cls, domains_dir, name: str) -> "Domain":
        # `name` comes straight from API requests: never let it escape domains_dir.
        if not isinstance(name, str) or not _DOMAIN_NAME.match(name):
            raise UnknownDomain(f"unknown domain {name!r}")
        path = Path(domains_dir) / f"{name}.yaml"
        if not path.is_file():
            raise UnknownDomain(f"unknown domain {name!r}")
        raw = yaml.safe_load(path.read_text())
        guards = {g["id"]: g for g in raw.get("guard_hypotheses", [])}
        invariants = [Invariant(**inv) for inv in raw.get("invariants", [])]
        prefs = raw.get("preferences", {})
        recall = raw.get("recall", {})
        comp = raw["compilation"]
        metric = raw["metric"]
        interventions = {i["id"]: i for i in raw.get("interventions", [])}

        # Fields that guards/invariants read. A request missing one of these cannot
        # be evaluated safely, so the service rejects it instead of silently
        # skipping the rule (which used to make the SLA invariant fail open).
        required: set = set()
        for g in guards.values():
            required |= referenced_names(g["expression"])
        for inv in invariants:
            required |= referenced_names(inv.applies_when)
            required |= referenced_names(inv.expression) - {metric["name"]}

        return cls(
            name=raw["domain"],
            initial_state=raw["process"]["initial_state"],
            terminal_state=raw["process"]["terminal_state"],
            metric_name=metric["name"],
            metric_unit=metric["unit"],
            deviation_tolerance=comp["deviation_tolerance"],
            min_support=comp["min_support"],
            invariants=invariants,
            guard_hypotheses=guards,
            confidence_buffer_threshold=prefs.get("confidence_buffer_threshold", 0.6),
            conservative_buffer=prefs.get("conservative_buffer", 1.0),
            recall_limit=recall.get("limit", 25),
            recall_query_template=recall.get("query_template", ""),
            hard_keys=list(raw.get("scope", {}).get("hard_keys", [])),
            interventions=interventions,
            recency_half_life_days=float(comp.get("recency_half_life_days", 30)),
            projection=metric.get("projection", ""),
            projection_start_field=metric.get("projection_start_field", ""),
            required_state_fields=required,
            raw=raw,
        )
