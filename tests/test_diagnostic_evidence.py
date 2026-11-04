"""V1.1 evidence must stay tied to real states and source structure."""
from branchcheck.analyzer import analyze
from branchcheck.loader import validate_story
from branchcheck.models import Limits


def choice(id, target, condition=True, effects=None):
    return {
        'id': id, 'text': id, 'target': target,
        'condition': condition, 'effects': effects or {},
    }


def node(id, choices=(), **extra):
    return {'id': id, 'title': id, 'choices': list(choices), **extra}


def story(nodes, variables=None):
    return validate_story({
        'schema_version': 1,
        'title': 'V1.1 证据测试',
        'start': nodes[0]['id'],
        'variables': variables or {},
        'nodes': nodes,
    })


def var(name, value=True):
    return {'var': name, 'eq': value}


def diagnostic(report, code, node_id=None):
    return next(
        item for item in report['diagnostics']
        if item['code'] == code
        and (node_id is None or item['node_id'] == node_id)
    )


def variable_source(report, name):
    return next(item for item in report['variable_sources']
                if item['variable'] == name)


def test_assertion_and_choice_diagnostics_use_original_array_pointers():
    model = story([
        node('start', [
            choice('blocked', 'end', var('flag')),
        ]),
        node('end', ending=True, assertions=[{
            'id': 'rule', 'condition': var('flag'), 'message': '需要 flag',
        }]),
    ], {'flag': False})
    report = analyze(model)

    dead_end = diagnostic(report, 'DEAD_END', 'start')
    assert dead_end['source_refs'][0]['pointer'] == '/nodes/0'
    assert dead_end['source_refs'][1]['pointer'] == (
        '/nodes/0/choices/0/condition')
    assert dead_end['source_refs'][1]['role'] == '不可执行选择条件'

    # Make the assertion reachable without changing its original array index.
    reachable = story([
        node('start', [choice('go', 'end')]),
        node('end', ending=True, assertions=[{
            'id': 'rule', 'condition': var('flag'), 'message': '需要 flag',
        }]),
    ], {'flag': False})
    failure = diagnostic(analyze(reachable), 'ASSERTION_FAILED')
    assert failure['source_refs'] == [{
        'pointer': '/nodes/1/assertions/0/condition',
        'node_id': 'end',
        'node_title': 'end',
        'assertion_id': 'rule',
        'assertion_message': '需要 flag',
        'role': '失败断言',
    }]


def test_each_representative_path_explains_its_own_final_snapshot():
    model = story([
        node('hub', [
            choice('set_a', 'hub', effects={'a': True}),
            choice('set_b', 'hub', effects={'b': True}),
            choice('inspect', 'bad'),
            choice('finish', 'end'),
        ]),
        node('bad', [choice('return', 'hub')], assertions=[{
            'id': 'both',
            'condition': {'all': [var('a'), var('b')]},
            'message': '需要两项证据',
        }]),
        node('end', ending=True),
    ], {'a': False, 'b': False})
    failure = diagnostic(analyze(model), 'ASSERTION_FAILED')

    assert failure['representative_path_count'] == 3
    for path in failure['paths']:
        explanation = path['condition_explanations'][0]['explanation']
        actual = {
            child['name']: child['actual']
            for child in explanation['children']
        }
        assert actual == {
            'a': path['final_state']['variables']['a'],
            'b': path['final_state']['variables']['b'],
        }
        assert explanation['result'] is False


def test_unreachable_nodes_have_only_structural_incoming_clues():
    model = story([
        node('start', [choice('blocked', 'unused', False),
                       choice('finish', 'end')]),
        node('unused'),
        node('end', ending=True),
    ])
    unreachable = diagnostic(analyze(model), 'UNREACHABLE_NODE', 'unused')

    assert unreachable['evidence_kind'] == 'global_conclusion'
    assert unreachable['paths'] == []
    assert unreachable['source_refs'][0]['pointer'] == '/nodes/1'
    assert unreachable['incoming_edges'][0]['source_reachability'] == 'reachable'
    assert unreachable['incoming_edges'][0]['source_refs'][0]['pointer'] == (
        '/nodes/0/choices/0/target')


def test_variable_sources_separate_static_locations_from_search_observation():
    model = story([
        node('start', [
            choice('turn_off', 'end', effects={'ready': False}),
            choice('blocked_write', 'end', var('gate'), {'gate': True}),
        ]),
        node('end', ending=True),
    ], {'ready': True, 'gate': False, 'initial_only': True})
    report = analyze(model)

    ready = variable_source(report, 'ready')
    assert ready['initial_value'] is True
    assert ready['writes'][0]['value'] is False
    assert ready['writes'][0]['observation_status'] == 'triggered'

    gate = variable_source(report, 'gate')
    assert gate['writes'][0]['source_reachability'] == 'reachable'
    assert gate['writes'][0]['observation_status'] == 'not_triggered'
    assert gate['writes'][0]['evidence_kind'] == 'static_write_location'

    initial_only = variable_source(report, 'initial_only')
    assert initial_only['initial_value'] is True
    assert initial_only['writes'] == []


def test_incomplete_search_marks_unobserved_writes_unknown():
    model = story([
        node('start', [
            choice('first', 'end', effects={'first': True}),
            choice('second', 'end', effects={'second': True}),
        ]),
        node('end', ending=True),
    ], {'first': False, 'second': False})
    report = analyze(model, Limits(max_transitions=1))

    assert report['analysis_complete'] is False
    assert variable_source(report, 'first')['writes'][0][
        'observation_status'] == 'triggered'
    second = variable_source(report, 'second')['writes'][0]
    assert second['source_reachability'] == 'reachable'
    assert second['observation_status'] == 'unknown'


def test_contradiction_reports_all_assignments_local_proof():
    condition = {'all': [var('flag'), var('flag', False)]}
    report = analyze(story([
        node('start', [choice('impossible', 'end', condition),
                       choice('finish', 'end')]),
        node('end', ending=True),
    ], {'flag': False}))
    contradiction = diagnostic(report, 'CONTRADICTORY_CONDITION')

    assert contradiction['evidence_kind'] == 'local_proof'
    assert contradiction['local_proof'] == {
        'proof_kind': 'all_assignments',
        'assignment_count': 2,
        'status': 'completed',
        'variable_count': 1,
        'satisfiable': False,
        'reason': None,
    }
    assert contradiction['paths'] == []
