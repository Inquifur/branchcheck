"""Source pointers use author order and static clues make no search claims."""
import json

import pytest

from branchcheck.loader import validate_story
from branchcheck.source_context import (
    build_source_context,
    escape_pointer_token,
    json_pointer,
)


def source_story():
    return validate_story({
        'schema_version': 1,
        'title': 'Source order',
        'start': 'second',
        'variables': {'ready': True, 'flag': False, 'untouched': False},
        'nodes': [
            {
                'id': 'first',
                'title': 'First declared node',
                'choices': [{
                    'id': 'clear',
                    'text': 'Clear the flag',
                    'target': 'end',
                    'condition': False,
                    'effects': {'flag': False},
                }],
            },
            {
                'id': 'second',
                'title': 'Second declared node',
                'assertions': [{
                    'id': 'must_be_ready',
                    'condition': {'var': 'ready', 'eq': True},
                    'message': 'Ready is required',
                }],
                'choices': [{
                    'id': 'set',
                    'text': 'Set both values',
                    'target': 'first',
                    'condition': {'var': 'ready', 'eq': True},
                    'effects': {'flag': True, 'ready': False},
                }],
            },
            {'id': 'end', 'title': 'End', 'ending': True},
        ],
    })


def test_rfc_6901_token_escaping_and_root_pointer():
    assert escape_pointer_token('plain') == 'plain'
    assert escape_pointer_token('a~/b') == 'a~0~1b'
    assert json_pointer() == ''
    assert json_pointer('nodes', 3, 'a~/b') == '/nodes/3/a~0~1b'


def test_refs_follow_original_arrays_and_return_role_specific_copies():
    context = build_source_context(source_story())

    assert context.node_ref('first', role='target node') == {
        'pointer': '/nodes/0',
        'node_id': 'first',
        'node_title': 'First declared node',
        'role': 'target node',
    }
    assert context.node_ref('second')['pointer'] == '/nodes/1'

    choice = context.choice_ref(
        'second', 'set', field='condition', role='blocked condition')
    assert choice == {
        'pointer': '/nodes/1/choices/0/condition',
        'node_id': 'second',
        'node_title': 'Second declared node',
        'choice_id': 'set',
        'choice_text': 'Set both values',
        'target_node_id': 'first',
        'role': 'blocked condition',
    }
    assert context.choice_ref('second', 'set', field='target')['pointer'] == (
        '/nodes/1/choices/0/target')
    assert context.choice_ref('second', 'set', field='effects')['pointer'] == (
        '/nodes/1/choices/0/effects')

    assertion = context.assertion_ref(
        'second', 'must_be_ready', field='condition', role='failed assertion')
    assert assertion['pointer'] == '/nodes/1/assertions/0/condition'
    assert assertion['assertion_id'] == 'must_be_ready'
    assert assertion['assertion_message'] == 'Ready is required'
    assert assertion['role'] == 'failed assertion'

    # Returned dictionaries are fresh report values, not mutable index storage.
    choice['pointer'] = '/changed'
    assert context.choice_ref('second', 'set')['pointer'] == '/nodes/1/choices/0'
    with pytest.raises(ValueError, match='unsupported source field'):
        context.choice_ref('second', 'set', field='text')


def test_variable_sources_include_all_static_writes_without_execution_claims():
    context = build_source_context(source_story())

    flag = context.variable_source('flag')
    assert flag['initial_value'] is False
    assert flag['initial_pointer'] == '/variables/flag'
    assert flag['writes'] == [
        {
            'pointer': '/nodes/0/choices/0/effects/flag',
            'value': False,
            'node_id': 'first',
            'node_title': 'First declared node',
            'choice_id': 'clear',
            'choice_text': 'Clear the flag',
            'target_node_id': 'end',
        },
        {
            'pointer': '/nodes/1/choices/0/effects/flag',
            'value': True,
            'node_id': 'second',
            'node_title': 'Second declared node',
            'choice_id': 'set',
            'choice_text': 'Set both values',
            'target_node_id': 'first',
        },
    ]
    # The first write has condition=false, but still belongs in this static index.
    assert all('reachable' not in write and 'triggered' not in write
               for write in flag['writes'])

    ready = context.variable_source('ready')
    assert ready['initial_value'] is True
    assert ready['writes'][0]['value'] is False
    assert context.variable_source('untouched')['writes'] == []
    assert [item['variable'] for item in context.all_variable_sources()] == [
        'ready', 'flag', 'untouched']

    # Every public result contains only JSON-compatible values.
    json.dumps(context.all_variable_sources(), ensure_ascii=False)
