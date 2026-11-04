"""Strict JSON loading and schema validation, separate from state exploration."""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .models import Assertion, Choice, Condition, Node, Story, TRUE

_ID = re.compile(r'[A-Za-z_][A-Za-z0-9_]*', re.ASCII)
MAX_CONDITION_DEPTH = 32


class InputError(ValueError):
    """An author-facing error, with a schema path whenever one is available."""


def _fail(path: str, message: str) -> None:
    raise InputError(f'{path}: {message}')


def _object(value: object, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(path, '类型错误，应为对象')
    return value


def _array(value: object, path: str) -> list[Any]:
    if type(value) is not list:
        _fail(path, '类型错误，应为数组')
    return value


def _fields(value: dict[str, Any], path: str, required: set[str], optional: set[str]) -> None:
    for key in value:
        if key not in required | optional:
            _fail(f'{path}.{key}', '未知字段')
    for key in sorted(required):
        if key not in value:
            _fail(f'{path}.{key}', '缺少必填字段')


def _text(value: object, path: str) -> str:
    if type(value) is not str:
        _fail(path, '类型错误，应为字符串')
    if not value.strip():
        _fail(path, '字符串不能为空或仅包含空白')
    return value


def _identifier(value: object, path: str) -> str:
    if type(value) is not str:
        _fail(path, '类型错误，ID 应为字符串')
    if not _ID.fullmatch(value):
        _fail(path, '非法 ID，应符合 [A-Za-z_][A-Za-z0-9_]*')
    return value


def _boolean(value: object, path: str) -> bool:
    if type(value) is not bool:
        _fail(path, '类型错误，应为 JSON 布尔值 true/false，不能使用数字 0/1')
    return value


def _condition(value: object, path: str, variables: dict[str, bool], depth: int = 1) -> Condition:
    # Stop before recurring again, so malformed user input never reaches Python's
    # much larger and implementation-dependent recursion boundary.
    if depth > MAX_CONDITION_DEPTH:
        _fail(path, f'条件表达式最大深度为 {MAX_CONDITION_DEPTH}（根表达式深度为 1）')
    if type(value) is bool:
        return Condition('const', value=value)
    expr = _object(value, path)
    keys = set(expr)
    if keys == {'var', 'eq'}:
        name = _identifier(expr['var'], f'{path}.var')
        if name not in variables:
            _fail(f'{path}.var', f'未知变量 {name!r}，请先在 variables 中声明')
        return Condition('var', value=_boolean(expr['eq'], f'{path}.eq'), name=name)
    if len(keys) == 1 and keys <= {'all', 'any', 'not'}:
        kind = next(iter(expr))
        if kind == 'not':
            children = (_condition(expr[kind], f'{path}.not', variables, depth + 1),)
        else:
            raw_children = _array(expr[kind], f'{path}.{kind}')
            if not raw_children:
                _fail(f'{path}.{kind}', '必须是非空表达式数组')
            children = tuple(
                _condition(child, f'{path}.{kind}[{index}]', variables, depth + 1)
                for index, child in enumerate(raw_children)
            )
        return Condition(kind, children=children)
    _fail(path, '条件对象形状错误：应恰好包含 var/eq，或 all、any、not 中的一个字段')


def validate_story(data: object) -> Story:
    """Validate an already decoded JSON value; return frozen story models.

    IDs and choice order retain author input order. Variables/effects are protected
    mappings; the analyzer determines bit order by sorting the variable names.
    """
    root = _object(data, '$')
    _fields(root, '$', {'schema_version', 'title', 'start', 'variables', 'nodes'}, set())
    if type(root['schema_version']) is not int or root['schema_version'] != 1:
        _fail('schema_version', '类型或版本错误，只接受整数 1（不接受 true）')
    title = _text(root['title'], 'title')
    start = _identifier(root['start'], 'start')
    raw_variables = _object(root['variables'], 'variables')
    variables: dict[str, bool] = {}
    for key, value in raw_variables.items():
        name = _identifier(key, f'variables.{key}')
        variables[name] = _boolean(value, f'variables.{name}')

    raw_nodes = _array(root['nodes'], 'nodes')
    if not raw_nodes:
        _fail('nodes', '至少需要一个节点')
    nodes: list[Node] = []
    node_ids: set[str] = set()
    target_references: list[tuple[str, str]] = []
    for node_index, raw_node in enumerate(raw_nodes):
        path = f'nodes[{node_index}]'
        node = _object(raw_node, path)
        _fields(node, path, {'id', 'title'}, {'ending', 'assertions', 'choices'})
        node_id = _identifier(node['id'], f'{path}.id')
        if node_id in node_ids:
            _fail(f'{path}.id', f'重复节点 ID {node_id!r}')
        node_ids.add(node_id)
        node_title = _text(node['title'], f'{path}.title')
        ending = _boolean(node.get('ending', False), f'{path}.ending')

        assertions: list[Assertion] = []
        assertion_ids: set[str] = set()
        for index, raw_assertion in enumerate(_array(node.get('assertions', []), f'{path}.assertions')):
            assertion_path = f'{path}.assertions[{index}]'
            assertion = _object(raw_assertion, assertion_path)
            _fields(assertion, assertion_path, {'id', 'condition', 'message'}, set())
            assertion_id = _identifier(assertion['id'], f'{assertion_path}.id')
            if assertion_id in assertion_ids:
                _fail(f'{assertion_path}.id', f'重复断言 ID {assertion_id!r}')
            assertion_ids.add(assertion_id)
            assertions.append(Assertion(
                assertion_id,
                _condition(assertion['condition'], f'{assertion_path}.condition', variables),
                _text(assertion['message'], f'{assertion_path}.message'),
            ))

        raw_choices = _array(node.get('choices', []), f'{path}.choices')
        if ending and raw_choices:
            _fail(f'{path}.choices', 'ending=true 的节点禁止声明非空 choices')
        choices: list[Choice] = []
        choice_ids: set[str] = set()
        for index, raw_choice in enumerate(raw_choices):
            choice_path = f'{path}.choices[{index}]'
            choice = _object(raw_choice, choice_path)
            _fields(choice, choice_path, {'id', 'text', 'target'}, {'condition', 'effects'})
            choice_id = _identifier(choice['id'], f'{choice_path}.id')
            if choice_id in choice_ids:
                _fail(f'{choice_path}.id', f'重复选择 ID {choice_id!r}')
            choice_ids.add(choice_id)
            target = _identifier(choice['target'], f'{choice_path}.target')
            target_references.append((target, f'{choice_path}.target'))
            effects: dict[str, bool] = {}
            for key, value in _object(choice.get('effects', {}), f'{choice_path}.effects').items():
                name = _identifier(key, f'{choice_path}.effects.{key}')
                if name not in variables:
                    _fail(f'{choice_path}.effects.{name}', f'未知变量 {name!r}，请先在 variables 中声明')
                effects[name] = _boolean(value, f'{choice_path}.effects.{name}')
            choices.append(Choice(
                id=choice_id,
                text=_text(choice['text'], f'{choice_path}.text'),
                target=target,
                condition=_condition(choice['condition'], f'{choice_path}.condition', variables)
                if 'condition' in choice else TRUE,
                effects=MappingProxyType(effects),
            ))
        nodes.append(Node(node_id, node_title, ending, tuple(assertions), tuple(choices)))

    if start not in node_ids:
        _fail('start', f'目标不存在：{start!r}')
    for target, path in target_references:
        if target not in node_ids:
            _fail(path, f'目标不存在：{target!r}')
    return Story(title, start, MappingProxyType(variables), tuple(nodes))


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f'JSON 对象包含重复键 {key!r}')
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise InputError(f'JSON 不允许非标准数值 {value}')


def loads_story(text: str) -> Story:
    """Decode strict JSON (duplicate keys/NaN rejected), then validate the schema."""
    if type(text) is not str:
        raise InputError('输入类型错误，应为 JSON 文本字符串')
    try:
        data = json.loads(text.removeprefix('\ufeff'), object_pairs_hook=_unique_object,
                          parse_constant=_invalid_constant)
        return validate_story(data)
    except json.JSONDecodeError as exc:
        raise InputError(f'JSON 语法错误，第 {exc.lineno} 行第 {exc.colno} 列：{exc.msg}') from None
    except RecursionError:
        raise InputError('输入嵌套过深；条件表达式最大深度为 32') from None
    except InputError:
        raise
    except ValueError as exc:
        # Python also rejects pathologically long integer literals; keep this a
        # normal input error instead of showing an interpreter traceback.
        raise InputError(f'JSON 输入错误：{exc}') from None


def load_story(path: str | Path) -> Story:
    """Read UTF-8 JSON from disk. I/O errors remain OSError for CLI handling."""
    try:
        return loads_story(Path(path).read_text(encoding='utf-8-sig'))
    except UnicodeError as exc:
        raise InputError(f'文件不是有效 UTF-8 文本：{exc}') from None
