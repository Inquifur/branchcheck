import pytest

from branchcheck.conditions import (
    condition_to_json, contradiction_check, evaluate, referenced_variables,
)
from branchcheck.loader import validate_story


def parse(expr, variables=None):
    names = {'a': False, 'b': False} if variables is None else variables
    data = {
        'schema_version': 1, 'title': '表达式测试', 'start': 's', 'variables': names,
        'nodes': [{'id': 's', 'title': '起点', 'choices': [
            {'id': 'go', 'text': '前进', 'target': 'e', 'condition': expr},
        ]}, {'id': 'e', 'title': '终点', 'ending': True}],
    }
    return validate_story(data).nodes[0].choices[0].condition


@pytest.mark.parametrize(('expr', 'expected'), [
    (True, [True, True, True, True]),
    (False, [False, False, False, False]),
    ({'var': 'a', 'eq': True}, [False, True, False, True]),
    ({'var': 'b', 'eq': False}, [True, True, False, False]),
    ({'all': [{'var': 'a', 'eq': True}, {'var': 'b', 'eq': True}]},
     [False, False, False, True]),
    ({'any': [{'var': 'a', 'eq': True}, {'var': 'b', 'eq': True}]},
     [False, True, True, True]),
    ({'not': {'var': 'a', 'eq': True}}, [True, False, True, False]),
    ({'not': {'not': {'var': 'a', 'eq': True}}}, [False, True, False, True]),
    ({'all': [True, {'any': [False, {'not': {'var': 'b', 'eq': False}}]}]},
     [False, False, True, True]),
])
def test_boolean_truth_tables_and_round_trip(expr, expected):
    condition = parse(expr)
    assert [evaluate(condition, mask, {'a': 0, 'b': 1}) for mask in range(4)] == expected
    assert condition_to_json(condition) == expr


def test_reference_names_are_unique_and_sorted():
    condition = parse({'all': [
        {'var': 'b', 'eq': False}, {'not': {'var': 'a', 'eq': True}},
        {'var': 'b', 'eq': True},
    ]})
    assert referenced_variables(condition) == ('a', 'b')
    assert referenced_variables(parse(True)) == ()


@pytest.mark.parametrize(('expr', 'satisfiable'), [
    (True, True), (False, False),
    ({'all': [{'var': 'a', 'eq': True}, {'var': 'a', 'eq': False}]}, False),
    ({'any': [{'var': 'a', 'eq': True}, {'var': 'a', 'eq': False}]}, True),
    ({'not': {'any': [{'var': 'a', 'eq': True}, {'var': 'a', 'eq': False}]}}, False),
    ({'var': 'a', 'eq': True}, True),  # false in initial state is not a contradiction
])
def test_contradiction_means_false_for_all_assignments(expr, satisfiable):
    condition = parse(expr)
    result = contradiction_check(condition)
    assert result['status'] == 'completed'
    assert result['satisfiable'] is satisfiable
    assert result['reason'] is None
    result['satisfiable'] = 'mutated'
    assert contradiction_check(condition)['satisfiable'] is satisfiable


def test_twelve_variable_boundary_and_skipped_thirteen_variable_check():
    variables = {f'v{i}': False for i in range(13)}
    clauses = [{'var': name, 'eq': True} for name in variables]
    twelve = contradiction_check(parse({'all': clauses[:12]}, variables))
    assert twelve['variable_count'] == 12
    assert twelve['status'] == 'completed'
    assert twelve['satisfiable'] is True
    thirteen = contradiction_check(parse({'all': [False, *clauses]}, variables))
    assert thirteen['status'] == 'skipped'
    assert thirteen['variable_count'] == 13
    assert thirteen['satisfiable'] is None
    assert '13' in thirteen['reason'] and '12' in thirteen['reason']
