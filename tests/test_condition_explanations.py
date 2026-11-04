import pytest

from branchcheck.conditions import evaluate, explain_condition
from branchcheck.loader import validate_story


VARIABLE_INDEX = {'a': 0, 'b': 1}


def parse(expr):
    story = validate_story({
        'schema_version': 1,
        'title': '条件解释测试',
        'start': 'start',
        'variables': {'a': False, 'b': False},
        'nodes': [
            {
                'id': 'start',
                'title': '起点',
                'choices': [{
                    'id': 'go',
                    'text': '继续',
                    'target': 'end',
                    'condition': expr,
                }],
            },
            {'id': 'end', 'title': '终点', 'ending': True},
        ],
    })
    return story.nodes[0].choices[0].condition


@pytest.mark.parametrize(('value', 'expected'), [(True, True), (False, False)])
def test_constant_explanation(value, expected):
    condition = parse(value)
    assert explain_condition(condition, 0, VARIABLE_INDEX) == {
        'kind': 'const',
        'result': expected,
        'value': value,
    }


def test_nested_explanation_records_each_variable_value():
    condition = parse({'all': [
        {'var': 'a', 'eq': True},
        {'not': {'var': 'b', 'eq': True}},
    ]})
    explanation = explain_condition(condition, 0b01, VARIABLE_INDEX)

    assert explanation['kind'] == 'all'
    assert explanation['result'] is True
    assert explanation['children'][0] == {
        'kind': 'var',
        'result': True,
        'name': 'a',
        'expected': True,
        'actual': True,
        'satisfied': True,
    }
    negation = explanation['children'][1]
    assert negation['kind'] == 'not'
    assert negation['result'] is True
    assert negation['children'][0]['actual'] is False
    assert negation['children'][0]['satisfied'] is False


def test_successful_any_keeps_failed_leaf_visible():
    condition = parse({'any': [
        {'var': 'a', 'eq': True},
        {'var': 'b', 'eq': True},
    ]})
    explanation = explain_condition(condition, 0b10, VARIABLE_INDEX)

    assert explanation['result'] is True
    assert [child['result'] for child in explanation['children']] == [False, True]
    assert explanation['children'][0]['satisfied'] is False
    assert explanation['children'][1]['satisfied'] is True


def test_not_fails_when_its_child_is_true():
    condition = parse({'not': {'var': 'a', 'eq': True}})
    explanation = explain_condition(condition, 0b01, VARIABLE_INDEX)

    assert explanation['kind'] == 'not'
    assert explanation['result'] is False
    assert explanation['children'][0]['result'] is True


@pytest.mark.parametrize(('expr', 'mask'), [
    (True, 0),
    ({'var': 'a', 'eq': False}, 0b10),
    ({'all': [{'var': 'a', 'eq': True}, {'var': 'b', 'eq': False}]}, 0b01),
    ({'any': [False, {'not': {'var': 'b', 'eq': True}}]}, 0),
])
def test_root_result_matches_evaluate(expr, mask):
    condition = parse(expr)
    explanation = explain_condition(condition, mask, VARIABLE_INDEX)
    assert explanation['result'] is evaluate(condition, mask, VARIABLE_INDEX)
