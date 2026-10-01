from __future__ import annotations
import heapq
from collections import defaultdict

from ..schemas import TransitionRule, PathStep
from .domain import Domain
from .guard import evaluate_guard

def applicable_rules(rules: list[TransitionRule], state: dict) -> list[TransitionRule]:
    out = []
    for r in rules:
        try:
            if evaluate_guard(r.guard_expression, state):
                out.append(r)
        except Exception:
            continue
    return out

def _rank(domain: Domain, r: TransitionRule) -> tuple:
    return (1 if r.intervention else 0, domain.guard_specificity(r.guard_id), r.confidence, -r.value)

def best_edges(domain: Domain, rules: list[TransitionRule]) -> dict:
    best: dict[tuple[str, str], TransitionRule] = {}
    for r in rules:
        key = (r.from_state, r.to_state)
        cur = best.get(key)
        if cur is None:
            best[key] = r
            continue
        if _rank(domain, r) > _rank(domain, cur):
            best[key] = r
    return best

def shortest_path(domain: Domain, state: dict, rules: list[TransitionRule]):
    applicable = applicable_rules(rules, state)
    edges = best_edges(domain, applicable)

    adjacency: dict[str, list] = defaultdict(list)
    for (u, v), rule in edges.items():
        adjacency[u].append((v, rule))

    start, goal = domain.initial_state, domain.terminal_state
    dist: dict[str, float] = {start: 0.0}
    prev: dict[str, tuple] = {}
    visited: set = set()
    pq: list = [(0.0, start)]

    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        if u == goal:
            break
        for v, rule in adjacency.get(u, []):
            nd = d + rule.value
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = (u, rule)
                heapq.heappush(pq, (nd, v))

    if goal not in dist:
        return None, float("inf"), 0.0

    path: list[PathStep] = []
    node = goal
    min_conf = 1.0
    while node != start:
        u, rule = prev[node]
        path.append(PathStep(
            rule_id=rule.id, from_state=u, to_state=node, value=rule.value,
            confidence=rule.confidence, guard_id=rule.guard_id,
            derived_from=rule.derived_from, status=rule.status,
        ))
        min_conf = min(min_conf, rule.confidence)
        node = u
    path.reverse()
    return path, dist[goal], min_conf
