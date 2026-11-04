import copy
import json

import pytest

from branchcheck.loader import InputError, load_story, loads_story, validate_story
from branchcheck.models import TRUE


def base_story():
    return {
        'schema_version': 1, 'title': '校验样例', 'start': 'start',
        'variables': {'flag': False},
        'nodes': [
            {'id': 'start', 'title': '起点', 'assertions': [
                {'id': 'rule', 'condition': True, 'message': '规则说明'},
            ], 'choices': [
                {'id': 'go', 'text': '离开', 'target': 'end'},
            ]},
            {'id': 'end', 'title': '结束', 'ending': True},
        ],
    }


def put(data, path, value):
    current = data
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = value


def test_defaults_and_utf8_file_with_bom(tmp_path):
    source = base_story()
    path = tmp_path / '故事.json'
    path.write_text(json.dumps(source, ensure_ascii=False), encoding='utf-8-sig')
    story = load_story(path)
    assert story.title == '校验样例'
    assert story.nodes[0].choices[0].condition == TRUE
    assert not story.nodes[0].ending
    assert not story.nodes[0].choices[0].effects
    assert story.nodes[1].assertions == ()
    assert story.nodes[1].choices == ()
    with pytest.raises(TypeError):
        story.variables['flag'] = True


@pytest.mark.parametrize(('path', 'value', 'expected'), [
    (('schema_version',), True, 'schema_version'),
    (('schema_version',), 1.0, 'schema_version'),
    (('schema_version',), 2, 'schema_version'),
    (('title',), '', 'title'),
    (('title',), '  \n', 'title'),
    (('title',), False, 'title'),
    (('start',), 'missing', '目标不存在'),
    (('start',), '汉字', '非法 ID'),
    (('variables',), [], 'variables'),
    (('variables', 'flag'), 0, 'variables.flag'),
    (('variables', 'flag'), 1, 'variables.flag'),
    (('variables', 'flag'), 'false', 'variables.flag'),
    (('nodes',), [], 'nodes'),
    (('nodes',), {}, 'nodes'),
    (('nodes', 0), None, 'nodes[0]'),
    (('nodes', 0, 'id'), 'bad-id', 'nodes[0].id'),
    (('nodes', 0, 'id'), True, 'nodes[0].id'),
    (('nodes', 0, 'title'), '', 'nodes[0].title'),
    (('nodes', 0, 'ending'), 1, 'nodes[0].ending'),
    (('nodes', 0, 'assertions'), {}, 'nodes[0].assertions'),
    (('nodes', 0, 'assertions', 0, 'message'), '', 'message'),
    (('nodes', 0, 'assertions', 0, 'id'), '1rule', '非法 ID'),
    (('nodes', 0, 'choices'), {}, 'nodes[0].choices'),
    (('nodes', 0, 'choices', 0, 'id'), '', 'nodes[0].choices[0].id'),
    (('nodes', 0, 'choices', 0, 'text'), None, 'nodes[0].choices[0].text'),
    (('nodes', 0, 'choices', 0, 'target'), 'missing', 'nodes[0].choices[0].target'),
    (('nodes', 0, 'choices', 0, 'effects'), [], 'effects'),
    (('nodes', 0, 'choices', 0, 'effects'), {'missing': True}, '未知变量'),
    (('nodes', 0, 'choices', 0, 'effects'), {'flag': 1}, 'effects.flag'),
])
def test_wrong_types_values_and_references(path, value, expected):
    data = base_story()
    put(data, path, value)
    with pytest.raises(InputError) as caught:
        validate_story(data)
    assert expected in str(caught.value)


@pytest.mark.parametrize('path', [
    (), ('nodes', 0), ('nodes', 0, 'choices', 0), ('nodes', 0, 'assertions', 0),
])
def test_unknown_fields_are_rejected_at_every_schema_level(path):
    data = base_story()
    current = data
    for part in path:
        current = current[part]
    current['conditon'] = True
    with pytest.raises(InputError, match='未知字段'):
        validate_story(data)


@pytest.mark.parametrize('path', [
    ('title',), ('schema_version',), ('start',), ('variables',), ('nodes',),
    ('nodes', 0, 'id'), ('nodes', 0, 'title'),
    ('nodes', 0, 'choices', 0, 'id'), ('nodes', 0, 'choices', 0, 'text'),
    ('nodes', 0, 'choices', 0, 'target'), ('nodes', 0, 'assertions', 0, 'condition'),
    ('nodes', 0, 'assertions', 0, 'message'),
])
def test_required_fields_are_not_silently_defaulted(path):
    data = base_story()
    current = data
    for part in path[:-1]:
        current = current[part]
    del current[path[-1]]
    with pytest.raises(InputError, match='缺少必填字段'):
        validate_story(data)


@pytest.mark.parametrize('condition', [
    0, 1, None, 'flag == true', [], {}, {'var': 'flag'},
    {'var': 'flag', 'eq': 1}, {'var': 'flag', 'eq': True, 'extra': 0},
    {'var': 'missing', 'eq': True}, {'var': 0, 'eq': True},
    {'all': []}, {'any': []}, {'all': True}, {'any': {}},
    {'not': [True]}, {'all': [True], 'not': False}, {'any': [None]},
])
def test_malformed_condition_shapes(condition):
    data = base_story()
    data['nodes'][0]['choices'][0]['condition'] = condition
    with pytest.raises(InputError) as caught:
        validate_story(data)
    assert 'nodes[0].choices[0].condition' in str(caught.value)


@pytest.mark.parametrize(('where', 'expected'), [
    ('node', '重复节点 ID'), ('choice', '重复选择 ID'), ('assertion', '重复断言 ID'),
])
def test_repeated_ids(where, expected):
    data = base_story()
    if where == 'node':
        data['nodes'].append(copy.deepcopy(data['nodes'][0]))
    else:
        field = 'choices' if where == 'choice' else 'assertions'
        data['nodes'][0][field].append(copy.deepcopy(data['nodes'][0][field][0]))
    with pytest.raises(InputError, match=expected):
        validate_story(data)


@pytest.mark.parametrize('text', [
    '{"schema_version": 1, "schema_version": 1}',
    '{"variables": {"flag": true, "flag": false}}',
    '{"x": 1, "\u0078": 2}',
])
def test_duplicate_json_keys_even_when_values_match(text):
    with pytest.raises(InputError, match='重复键'):
        loads_story(text)


@pytest.mark.parametrize('token', ['NaN', 'Infinity', '-Infinity'])
def test_non_standard_json_constants(token):
    with pytest.raises(InputError, match='非标准数值'):
        loads_story('{"x": ' + token + '}')


def test_json_syntax_error_has_line_and_column():
    text = '{\n "schema_version": 1,\n}'
    # Python versions can locate a trailing comma at the comma or closing brace.
    # The wrapper must preserve the active decoder's exact line and column.
    with pytest.raises(json.JSONDecodeError) as decoded:
        json.loads(text)
    with pytest.raises(InputError) as caught:
        loads_story(text)
    expected = decoded.value
    assert f'第 {expected.lineno} 行第 {expected.colno} 列' in str(caught.value)
    assert str(caught.value).startswith('JSON 语法错误，')


def test_depth_boundary_and_extreme_nesting():
    condition = True
    for _ in range(31):
        condition = {'not': condition}
    data = base_story()
    data['nodes'][0]['choices'][0]['condition'] = condition
    validate_story(data)  # exactly 32 expression levels
    data['nodes'][0]['choices'][0]['condition'] = {'not': condition}
    with pytest.raises(InputError, match='最大深度为 32'):
        loads_story(json.dumps(data))
    with pytest.raises(InputError, match='嵌套过深'):
        loads_story('[' * 10000 + 'true' + ']' * 10000)


def test_endings_are_terminal_and_empty_choices_are_allowed():
    data = base_story()
    data['nodes'][1]['choices'] = []
    validate_story(data)
    data['nodes'][1]['choices'] = [{'id': 'again', 'text': '再来', 'target': 'start'}]
    with pytest.raises(InputError, match='ending=true'):
        validate_story(data)


def test_identifiers_use_ascii_and_choice_ids_are_scoped_to_node():
    data = base_story()
    data['nodes'][1]['ending'] = False
    data['nodes'][1]['choices'] = [{'id': 'go', 'text': '返回', 'target': 'start'}]
    validate_story(data)
    data['variables']['invalid-id'] = True
    with pytest.raises(InputError, match='非法 ID'):
        validate_story(data)


def test_utf8_decoding_and_missing_file_errors(tmp_path):
    invalid = tmp_path / 'bad.json'
    invalid.write_bytes(b'\xff\xfe\x80')
    with pytest.raises(InputError, match='UTF-8'):
        load_story(invalid)
    with pytest.raises(OSError):
        load_story(tmp_path / 'does-not-exist.json')


@pytest.mark.parametrize('value', [None, True, [], 1, 'story'])
def test_top_level_must_be_object(value):
    with pytest.raises(InputError, match='类型错误'):
        validate_story(value)
