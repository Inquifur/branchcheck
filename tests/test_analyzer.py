"""Small, independent state models exercise proofs and search boundaries."""
from pathlib import Path

import pytest

from branchcheck.analyzer import analyze
from branchcheck.conditions import evaluate
from branchcheck.loader import load_story, validate_story
from branchcheck.models import Limits


EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'


def choice(id, target, condition=True, effects=None):
    return {'id': id, 'text': id, 'target': target,
            'condition': condition, 'effects': effects or {}}


def node(id, choices=(), **kw):
    return {'id': id, 'title': id, 'choices': list(choices), **kw}


def story(nodes, variables=None, start=None):
    return validate_story({'schema_version': 1, 'title': '模型',
                           'start': start or nodes[0]['id'],
                           'variables': variables or {}, 'nodes': nodes})


def var(name, value=True):
    return {'var': name, 'eq': value}


def codes(report):
    return {d['code'] for d in report['diagnostics']}


def diagnostic(report, code, node_id=None):
    return next(d for d in report['diagnostics'] if d['code'] == code
                and (node_id is None or d['node_id'] == node_id))


def replay(story_model, path):
    """Independently replay reported choices against their source conditions."""
    current = story_model.start
    values = dict(story_model.variables)
    assert path['initial_state']['node_id'] == current
    assert path['initial_state']['variables'] == values
    index = {name: i for i, name in enumerate(sorted(values))}
    nodes = {n.id: n for n in story_model.nodes}
    for step in path['steps']:
        assert current == step['source_node_id']
        selected = next(c for c in nodes[current].choices
                        if c.id == step['choice_id'])
        mask = sum(1 << index[name] for name, value in values.items() if value)
        assert evaluate(selected.condition, mask, index)
        before = values.copy()
        values.update(selected.effects)
        assert step['changes'] == {
            name: {'before': before[name], 'after': values[name]}
            for name in sorted(values) if before[name] != values[name]}
        assert step['target_node_id'] == selected.target
        current = selected.target
    assert path['final_state']['node_id'] == current
    assert path['final_state']['variables'] == values


@pytest.mark.parametrize('filename', ['minimal_ok.json', 'mystery_fixed.json',
                                     'state_cycle_ok.json'])
def test_examples_pass(filename):
    report = analyze(load_story(EXAMPLES / filename))
    assert report['overall_status'] == 'passed'
    assert report['analysis_complete']
    assert report['diagnostics'] == []


def test_minimal_effect_before_assertion():
    report = analyze(load_story(EXAMPLES / 'minimal_ok.json'))
    assert report['summary']['discovered_states'] == 4
    assert report['summary']['transition_count'] == 3
    assert report['overall_status'] == 'passed'


def test_state_cycle_visits_same_node_with_different_assignments():
    model = story([
        node('door', [choice('get_key', 'key', var('key', False)),
                      choice('unlock', 'end', var('key'))]),
        node('key', [choice('return', 'door', effects={'key': True})]),
        node('end', ending=True),
    ], {'key': False})
    report = analyze(model)
    assert report['overall_status'] == 'passed'
    assert report['node_results'][0]['reachable_state_count'] == 2


@pytest.mark.parametrize('initial,reachable', [(False, False), (True, True)])
def test_initial_values_change_reachability(initial, reachable):
    report = analyze(story([
        node('start', [choice('locked', 'end', var('key'))]),
        node('end', ending=True)], {'key': initial}))
    assert (report['summary']['reached_ending_count'] == 1) == reachable


def test_reset_false_and_sibling_independence():
    model = story([
        node('start', [choice('reset', 'off', effects={'flag': False}),
                       choice('keep', 'on')]),
        node('off', ending=True, assertions=[{
            'id': 'off_rule', 'condition': var('flag', False), 'message': 'off'}]),
        node('on', ending=True, assertions=[{
            'id': 'on_rule', 'condition': var('flag'), 'message': 'on'}]),
    ], {'flag': True})
    assert analyze(model)['overall_status'] == 'passed'
    assert model.variables['flag'] is True


def test_reachable_dead_end_vs_unreachable_empty_node():
    report = analyze(story([node('start'), node('unused')]))
    assert diagnostic(report, 'DEAD_END')['node_id'] == 'start'
    assert len([d for d in report['diagnostics'] if d['code'] == 'DEAD_END']) == 1
    assert diagnostic(report, 'UNREACHABLE_NODE')['node_id'] == 'unused'
    assert 'NO_REACHABLE_ENDING' in codes(report)
    assert 'NO_ENDING_PATH' not in codes(report)  # exclude same dead state


def test_all_choices_disabled_still_dead_end():
    report = analyze(story([node('start', [choice('no', 'end', False)]),
                            node('end', ending=True)]))
    assert 'DEAD_END' in codes(report)


def test_initial_and_arrival_assertions_and_replay():
    model = story([
        node('start', [choice('set', 'bad', effects={'flag': True})],
             assertions=[{'id': 'initial', 'condition': False, 'message': '初始'}]),
        node('bad', [choice('end', 'end')], assertions=[{
            'id': 'arrival', 'condition': var('flag', False), 'message': '到达'}]),
        node('end', ending=True),
    ], {'flag': False})
    report = analyze(model)
    for finding in report['diagnostics']:
        for path in finding['paths']:
            replay(model, path)
    initial = diagnostic(report, 'ASSERTION_FAILED', 'start')['paths'][0]
    assert initial['steps'] == []
    arrival = diagnostic(report, 'ASSERTION_FAILED', 'bad')['paths'][0]
    assert arrival['steps'][0]['changes']['flag'] == {'before': False, 'after': True}


def test_self_loop_with_exit_is_legal_and_counts_all_transitions():
    report = analyze(story([
        node('start', [choice('loop', 'start'), choice('finish', 'end')]),
        node('end', ending=True)]))
    assert report['overall_status'] == 'passed'
    assert report['summary']['transition_count'] == 2


def test_closed_multinode_cycle_has_no_ending_path():
    report = analyze(story([
        node('a', [choice('go', 'b')]), node('b', [choice('back', 'a')]),
        node('end', ending=True)]))
    assert 'NO_REACHABLE_ENDING' in codes(report)
    assert {d['node_id'] for d in report['diagnostics']
            if d['code'] == 'NO_ENDING_PATH'} == {'a', 'b'}
    assert 'DEAD_END' not in codes(report)


def test_reverse_reachability_distinguishes_states_at_same_node():
    report = analyze(story([
        node('start', [choice('safe', 'hub', effects={'flag': True}),
                       choice('trap', 'hub')]),
        node('hub', [choice('exit', 'end', var('flag')),
                     choice('loop', 'hub', var('flag', False))]),
        node('end', ending=True),
    ], {'flag': False}))
    finding = diagnostic(report, 'NO_ENDING_PATH', 'hub')
    assert finding['affected_state_count'] == 1
    assert finding['paths'][0]['final_state']['variables'] == {'flag': False}
    assert not any(d['node_id'] == 'start' for d in report['diagnostics'])


def test_edges_to_already_discovered_state_are_preserved():
    report = analyze(story([
        node('start', [choice('left', 'a'), choice('right', 'b')]),
        node('a', [choice('join', 'join')]),
        node('b', [choice('join', 'join')]),
        node('join', [choice('end', 'end')]), node('end', ending=True)]))
    assert report['overall_status'] == 'passed'
    assert report['summary']['transition_count'] == 5


def test_logical_contradiction_never_enabled_and_unreachable_source():
    contradiction = {'all': [var('flag'), var('flag', False)]}
    report = analyze(story([
        node('start', [choice('contradiction', 'end', contradiction),
                       choice('never', 'end', var('flag')), choice('ok', 'end')]),
        node('unused', [choice('not_reachable', 'end', var('flag'))]),
        node('end', ending=True),
    ], {'flag': False}))
    assert diagnostic(report, 'CONTRADICTORY_CONDITION')['choice_id'] == 'contradiction'
    assert [d['choice_id'] for d in report['diagnostics']
            if d['code'] == 'NEVER_ENABLED_CHOICE'] == ['never']


def test_shortest_path_and_stable_ties():
    model = story([
        node('start', [choice('long', 'a'), choice('short_first', 'bad'),
                       choice('short_second', 'bad')]),
        node('a', [choice('b', 'b')]), node('b', [choice('bad', 'bad')]),
        node('bad'),
    ])
    report = analyze(model)
    path = diagnostic(report, 'DEAD_END', 'bad')['paths'][0]
    assert [s['choice_id'] for s in path['steps']] == ['short_first']
    assert report == analyze(model)


@pytest.mark.parametrize('limits,reason', [
    (Limits(max_states=2), 'max_states'),
    (Limits(max_transitions=1), 'max_transitions'),
])
def test_limits_stop_without_false_negative_claims(limits, reason):
    model = story([
        node('start', [choice('next', 'middle'), choice('never', 'end', False)]),
        node('middle', [choice('end', 'end')]), node('end', ending=True),
        node('unused'),
    ])
    report = analyze(model, limits)
    assert report['overall_status'] == 'incomplete'
    assert reason in report['stop_reason']
    assert report['summary']['discovered_states'] <= limits.max_states
    assert report['summary']['transition_count'] <= limits.max_transitions
    forbidden = {'UNREACHABLE_NODE', 'UNREACHABLE_ENDING', 'NO_ENDING_PATH',
                 'NO_REACHABLE_ENDING', 'NEVER_ENABLED_CHOICE', 'DEAD_END'}
    assert not codes(report) & forbidden
    assert report['node_results'][-1]['reachability'] == 'unknown'
    assert report['node_results'][0]['choices'][1]['status'] == 'unknown'


def test_exact_limits_are_complete_even_with_cycle():
    model = story([
        node('start', [choice('loop', 'start'), choice('end', 'end')]),
        node('end', ending=True)])
    report = analyze(model, Limits(max_states=2, max_transitions=2))
    assert report['overall_status'] == 'passed'
    assert report['summary']['expanded_states'] == 2


def test_zero_transition_story_at_state_limit_is_complete():
    report = analyze(story([node('end', ending=True)]), Limits(1, 1))
    assert report['overall_status'] == 'passed'


def test_incomplete_retains_assertions_and_proven_dead_end():
    model = story([
        node('start', [choice('bad', 'bad'), choice('queue', 'queue')]),
        node('bad', assertions=[{'id': 'bad', 'condition': False, 'message': 'bad'}]),
        node('queue', [choice('new', 'end')]), node('end', ending=True),
    ])
    report = analyze(model, Limits(max_states=3))
    assert not report['analysis_complete']
    assert {'ASSERTION_FAILED', 'DEAD_END', 'ANALYSIS_LIMIT_REACHED'} <= codes(report)
    assert diagnostic(report, 'DEAD_END')['node_id'] == 'bad'
    assert report['summary']['expanded_states'] == 2


def test_local_contradiction_check_explicitly_skips_13_variables():
    variables = {f'v{i}': True for i in range(13)}
    report = analyze(story([
        node('start', [choice('go', 'end', {'all': [var(v) for v in variables]})]),
        node('end', ending=True)], variables))
    check = report['local_condition_checks'][0]
    assert check['status'] == 'skipped'
    assert check['satisfiable'] is None
    assert check['variable_count'] == 13
    assert 'CONTRADICTORY_CONDITION' not in codes(report)


def test_aggregate_counts_distinct_states_caps_three_shortest_replayable_paths():
    variables = {'a': False, 'b': False, 'c': False, 'guard': False}
    model = story([
        node('hub', [*(choice(f'set_{v}', 'hub', effects={v: True})
                       for v in ('a', 'b', 'c')),
                     choice('problem', 'bad'), choice('exit', 'end')]),
        node('bad', [choice('exit', 'end')], assertions=[{
            'id': 'guard_rule', 'condition': var('guard'), 'message': 'need guard'}]),
        node('end', ending=True),
    ], variables)
    report = analyze(model)
    finding = diagnostic(report, 'ASSERTION_FAILED')
    assert finding['affected_state_count'] == 8
    assert finding['representative_path_count'] == len(finding['paths']) == 3
    assert [len(p['steps']) for p in finding['paths']] == [1, 2, 2]
    for path in finding['paths']:
        replay(model, path)


def test_broken_preset_errors_and_all_evidence_replay():
    model = load_story(EXAMPLES / 'mystery_broken.json')
    report = analyze(model)
    assert report['overall_status'] == 'failed'
    assert {'ASSERTION_FAILED', 'DEAD_END', 'CONTRADICTORY_CONDITION',
            'UNREACHABLE_ENDING', 'NEVER_ENABLED_CHOICE'} <= codes(report)
    assert diagnostic(report, 'ASSERTION_FAILED')['node_id'] == 'confront'
    assert diagnostic(report, 'DEAD_END')['node_id'] == 'spent_card'
    for finding in report['diagnostics']:
        for path in finding['paths']:
            replay(model, path)
        if finding['code'].startswith('UNREACHABLE'):
            assert finding['paths'] == []
            assert 'incoming_edges' in finding


@pytest.mark.parametrize('kwargs', [{'max_states': 0}, {'max_transitions': -1},
                                   {'max_states': True}, {'max_transitions': 1.5}])
def test_programmatic_limits_require_positive_integers(kwargs):
    with pytest.raises(ValueError):
        Limits(**kwargs)
