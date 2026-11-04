"""Small, closed boolean language: evaluation and bounded local satisfiability."""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping

from .models import Condition

MAX_LOCAL_VARIABLES = 12


def evaluate(condition: Condition, mask: int, variable_index: Mapping[str, int]) -> bool:
    """Evaluate only the validated AST; no expression strings or eval are used."""
    if condition.kind == 'const':
        return bool(condition.value)
    if condition.kind == 'var':
        actual = bool(mask & (1 << variable_index[condition.name]))
        return actual == condition.value
    if condition.kind == 'all':
        return all(evaluate(child, mask, variable_index) for child in condition.children)
    if condition.kind == 'any':
        return any(evaluate(child, mask, variable_index) for child in condition.children)
    if condition.kind == 'not':
        return not evaluate(condition.children[0], mask, variable_index)
    raise ValueError(f'未知条件类型：{condition.kind!r}')


def explain_condition(
        condition: Condition, mask: int,
        variable_index: Mapping[str, int]) -> dict[str, Any]:
    """Explain a condition against one concrete state using evaluator semantics."""
    result = evaluate(condition, mask, variable_index)
    explanation: dict[str, Any] = {'kind': condition.kind, 'result': result}
    if condition.kind == 'const':
        explanation['value'] = bool(condition.value)
        return explanation
    if condition.kind == 'var':
        actual = bool(mask & (1 << variable_index[condition.name]))
        explanation.update(
            name=condition.name,
            expected=bool(condition.value),
            actual=actual,
            satisfied=result,
        )
        return explanation
    if condition.kind in ('all', 'any', 'not'):
        explanation['children'] = [
            explain_condition(child, mask, variable_index)
            for child in condition.children
        ]
        return explanation
    raise ValueError(f'未知条件类型：{condition.kind!r}')


@lru_cache(maxsize=4096)
def referenced_variables(condition: Condition) -> tuple[str, ...]:
    names: set[str] = set()
    pending = [condition]
    while pending:
        current = pending.pop()
        if current.kind == 'var':
            names.add(current.name)
        pending.extend(current.children)
    return tuple(sorted(names))


def condition_to_json(condition: Condition) -> bool | dict[str, Any]:
    """Convert an AST back to its source-level shape for report explanations."""
    if condition.kind == 'const':
        return bool(condition.value)
    if condition.kind == 'var':
        return {'var': condition.name, 'eq': condition.value}
    if condition.kind in ('all', 'any'):
        return {condition.kind: [condition_to_json(child) for child in condition.children]}
    if condition.kind == 'not':
        return {'not': condition_to_json(condition.children[0])}
    raise ValueError(f'未知条件类型：{condition.kind!r}')


@lru_cache(maxsize=4096)
def _local_result(condition: Condition) -> tuple[str, int, bool | None, str | None]:
    names = referenced_variables(condition)
    count = len(names)
    if count > MAX_LOCAL_VARIABLES:
        return ('skipped', count, None,
                f'条件引用 {count} 个不同变量，超过局部枚举上限 {MAX_LOCAL_VARIABLES}；未判断是否矛盾。')
    index = {name: bit for bit, name in enumerate(names)}
    satisfiable = any(evaluate(condition, mask, index) for mask in range(1 << count))
    return 'completed', count, satisfiable, None


def contradiction_check(condition: Condition) -> dict[str, Any]:
    """Check all assignments of referenced variables, up to 12 distinct names.

    The cached value is immutable. Each call returns a fresh report dictionary,
    preventing a caller from accidentally changing another condition's result.
    """
    status, count, satisfiable, reason = _local_result(condition)
    return {'status': status, 'variable_count': count, 'satisfiable': satisfiable, 'reason': reason}
