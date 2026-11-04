"""End-to-end checks for the adapted V1.1 investigation case study."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from branchcheck.analyzer import analyze
from branchcheck.conditions import evaluate
from branchcheck.loader import load_story, validate_story


CASE_DIR = Path(__file__).resolve().parents[1] / 'examples' / 'case_study'
BASE_NAME = 'investigation_ok.json'
MISSING = object()


def raw_case(filename: str) -> dict:
    return json.loads((CASE_DIR / filename).read_text(encoding='utf-8'))


def diagnostics(report: dict, code: str) -> list[dict]:
    return [item for item in report['diagnostics'] if item['code'] == code]


def pointer_token(value: object) -> str:
    return str(value).replace('~', '~0').replace('/', '~1')


def json_differences(before: object, after: object, path: str = '') -> list[tuple[str, object, object]]:
    if type(before) is not type(after):
        return [(path, before, after)]
    if isinstance(before, dict):
        differences = []
        for key in before.keys() | after.keys():
            child_path = f'{path}/{pointer_token(key)}'
            if key not in before:
                differences.append((child_path, MISSING, after[key]))
            elif key not in after:
                differences.append((child_path, before[key], MISSING))
            else:
                differences.extend(json_differences(before[key], after[key], child_path))
        return differences
    if isinstance(before, list):
        if len(before) != len(after):
            return [(path, before, after)]
        differences = []
        for index, (left, right) in enumerate(zip(before, after, strict=True)):
            differences.extend(json_differences(left, right, f'{path}/{index}'))
        return differences
    return [] if before == after else [(path, before, after)]


def set_pointer(document: object, pointer: str, value: object) -> None:
    tokens = [part.replace('~1', '/').replace('~0', '~')
              for part in pointer.removeprefix('/').split('/')]
    current = document
    for token in tokens[:-1]:
        current = current[int(token)] if isinstance(current, list) else current[token]
    final = tokens[-1]
    if isinstance(current, list):
        current[int(final)] = value
    else:
        current[final] = value


def replay_choice_ids(story, choice_ids: list[str]) -> tuple[str, dict[str, bool]]:
    nodes = {node.id: node for node in story.nodes}
    values = dict(story.variables)
    variable_index = {name: index for index, name in enumerate(sorted(values))}
    current = story.start
    for choice_id in choice_ids:
        choice = next(item for item in nodes[current].choices if item.id == choice_id)
        mask = sum(1 << variable_index[name]
                   for name, enabled in values.items() if enabled)
        assert evaluate(choice.condition, mask, variable_index), (
            f'{current}.{choice_id} is not enabled for {values}')
        values.update(choice.effects)
        current = choice.target
    return current, values


def replay_report_path(story, path: dict) -> None:
    nodes = {node.id: node for node in story.nodes}
    values = dict(story.variables)
    variable_index = {name: index for index, name in enumerate(sorted(values))}
    current = story.start
    assert path['initial_state']['node_id'] == current
    assert path['initial_state']['variables'] == values

    for step in path['steps']:
        assert step['source_node_id'] == current
        choice = next(item for item in nodes[current].choices
                      if item.id == step['choice_id'])
        mask = sum(1 << variable_index[name]
                   for name, enabled in values.items() if enabled)
        assert evaluate(choice.condition, mask, variable_index)
        before = values.copy()
        values.update(choice.effects)
        assert step['changes'] == {
            name: {'before': before[name], 'after': values[name]}
            for name in sorted(values) if before[name] != values[name]
        }
        assert step['target_node_id'] == choice.target
        current = choice.target

    assert path['final_state']['node_id'] == current
    assert path['final_state']['variables'] == values


def test_adapted_case_shape_and_clean_baseline():
    raw = raw_case(BASE_NAME)
    story = validate_story(raw)
    report = analyze(story)

    assert raw['title'].startswith('改编试用案例')
    assert 15 <= len(raw['nodes']) <= 30
    assert 6 <= len(raw['variables']) <= 12
    assert sum(node.get('ending', False) for node in raw['nodes']) >= 2
    assert report['analysis_complete']
    assert report['overall_status'] == 'passed'
    assert report['diagnostics'] == []


def test_archive_first_and_lab_first_routes_unlock_same_lobby_review():
    story = load_story(CASE_DIR / BASE_NAME)
    archive_first = [
        'ask_reception', 'get_archive_pass',
        'visit_archive', 'enter_archive', 'copy_memo',
        'visit_witness', 'start_interview', 'show_memo', 'record_statement',
        'ask_reception', 'get_lab_access',
        'visit_lab', 'enter_lab', 'inspect_camera', 'take_photo',
        'visit_lab', 'enter_lab', 'inspect_sample', 'test_sample',
        'review_evidence',
    ]
    lab_first = [
        'ask_reception', 'get_lab_access',
        'visit_lab', 'enter_lab', 'inspect_camera', 'take_photo',
        'visit_lab', 'enter_lab', 'inspect_sample', 'test_sample',
        'visit_witness', 'start_interview', 'ask_without_memo',
        'return_after_refusal',
        'ask_reception', 'get_archive_pass',
        'visit_archive', 'enter_archive', 'copy_memo',
        'visit_witness', 'start_interview', 'show_memo', 'record_statement',
        'review_evidence',
    ]

    for route in (archive_first, lab_first):
        node_id, values = replay_choice_ids(story, route)
        assert node_id == 'evidence_review'
        assert all(values[name] for name in (
            'has_memo', 'witness_interviewed', 'has_photo', 'photo_logged',
            'has_sample_result'))


@pytest.mark.parametrize(('filename', 'pointer', 'before', 'after'), [
    ('fault_missing_photo_effect.json',
     '/nodes/10/choices/0/effects/has_photo', True, MISSING),
    ('fault_wrong_exit_condition.json',
     '/nodes/3/choices/0/condition/eq', True, False),
    ('fault_wrong_target.json',
     '/nodes/12/choices/1/target', 'timeline_check', 'truth_end'),
])
def test_fault_is_one_independent_json_change_and_can_be_restored(
        filename, pointer, before, after):
    baseline = raw_case(BASE_NAME)
    faulty = raw_case(filename)
    differences = json_differences(baseline, faulty)

    assert len(differences) == 1
    actual_pointer, actual_before, actual_after = differences[0]
    assert actual_pointer == pointer
    assert actual_before == before
    assert actual_after is after if after is MISSING else actual_after == after

    restored = copy.deepcopy(faulty)
    set_pointer(restored, pointer, before)
    assert restored == baseline
    assert analyze(validate_story(restored)) == analyze(validate_story(baseline))


def test_missing_photo_effect_fails_photo_assertion_with_replayable_evidence():
    story = load_story(CASE_DIR / 'fault_missing_photo_effect.json')
    report = analyze(story)
    failures = diagnostics(report, 'ASSERTION_FAILED')

    assert report['overall_status'] == 'failed'
    assert len(failures) == 1
    failure = failures[0]
    assert failure['node_id'] == 'photo_briefing'
    assert failure['assertion_id'] == 'photo_must_exist'
    assert failure['affected_state_count'] == 1
    assert failure['paths'][0]['final_state']['variables']['photo_logged'] is True
    assert failure['paths'][0]['final_state']['variables']['has_photo'] is False
    replay_report_path(story, failure['paths'][0])


def test_wrong_exit_condition_creates_reachable_dead_end_with_replayable_paths():
    story = load_story(CASE_DIR / 'fault_wrong_exit_condition.json')
    report = analyze(story)
    dead_ends = diagnostics(report, 'DEAD_END')

    assert report['overall_status'] == 'failed'
    assert len(dead_ends) == 1
    dead_end = dead_ends[0]
    assert dead_end['node_id'] == 'archive_room'
    assert dead_end['affected_state_count'] >= 1
    assert dead_end['paths']
    for path in dead_end['paths']:
        assert path['final_state']['variables']['has_archive_pass'] is True
        replay_report_path(story, path)


def test_wrong_target_reaches_existing_but_invalid_ending_with_replayable_evidence():
    story = load_story(CASE_DIR / 'fault_wrong_target.json')
    report = analyze(story)
    failures = diagnostics(report, 'ASSERTION_FAILED')

    assert report['overall_status'] == 'failed'
    assert len(failures) == 1
    failure = failures[0]
    assert failure['node_id'] == 'truth_end'
    assert failure['assertion_id'] == 'truth_requires_review'
    path = failure['paths'][0]
    assert path['steps'][-1]['choice_id'] == 'compare_timeline'
    assert path['steps'][-1]['target_node_id'] == 'truth_end'
    assert path['final_state']['variables']['case_ready'] is False
    replay_report_path(story, path)
