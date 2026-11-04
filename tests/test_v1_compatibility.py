"""Lock the V1 sample semantics while V1.1 adds report-only evidence."""
import json
from pathlib import Path

import pytest

import branchcheck
from branchcheck.analyzer import analyze
from branchcheck.cli import main
from branchcheck.loader import load_story


EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'


def test_v12_package_and_report_versions_are_explicit():
    report = analyze(load_story(EXAMPLES / 'minimal_ok.json'))

    assert branchcheck.__version__ == '1.2.0'
    assert report['report_version'] == 2


@pytest.mark.parametrize(('filename', 'exit_code'), [
    ('minimal_ok.json', 0),
    ('mystery_broken.json', 1),
    ('mystery_fixed.json', 0),
    ('state_cycle_ok.json', 0),
])
def test_v1_sample_cli_exit_codes_remain_stable(filename, exit_code, capsys):
    actual = main([
        'check', str(EXAMPLES / filename), '--format', 'json',
    ])
    captured = capsys.readouterr()

    assert actual == exit_code
    assert captured.err == ''
    assert json.loads(captured.out)['analysis_complete'] is True


@pytest.mark.parametrize(('filename', 'states', 'transitions'), [
    ('minimal_ok.json', 4, 3),
    ('mystery_fixed.json', 68, 115),
    ('state_cycle_ok.json', 5, 5),
])
def test_v1_passing_sample_search_counts_remain_stable(
        filename, states, transitions):
    report = analyze(load_story(EXAMPLES / filename))

    assert report['analysis_complete'] is True
    assert report['overall_status'] == 'passed'
    assert report['diagnostics'] == []
    assert report['summary']['discovered_states'] == states
    assert report['summary']['transition_count'] == transitions


def test_v1_broken_sample_diagnostics_and_search_counts_remain_stable():
    report = analyze(load_story(EXAMPLES / 'mystery_broken.json'))

    assert report['analysis_complete'] is True
    assert report['overall_status'] == 'failed'
    assert report['summary']['discovered_states'] == 36
    assert report['summary']['transition_count'] == 52
    assert report['summary']['error_count'] == 2
    assert report['summary']['warning_count'] == 7
    assert [
        (item['code'], item['node_id'], item['choice_id'],
         item['assertion_id'], item['affected_state_count'])
        for item in report['diagnostics']
    ] == [
        ('ASSERTION_FAILED', 'confront', None, 'photo_required', 4),
        ('DEAD_END', 'spent_card', None, None, 2),
        ('UNREACHABLE_NODE', 'photo_room', None, None, 0),
        ('UNREACHABLE_ENDING', 'hidden_end', None, None, 0),
        ('CONTRADICTORY_CONDITION', 'foyer', 'impossible', None, 0),
        ('NEVER_ENABLED_CHOICE', 'permit_desk', 'issue', None, 4),
        ('NEVER_ENABLED_CHOICE', 'lab_entry', 'enter', None, 4),
        ('NEVER_ENABLED_CHOICE', 'confront', 'secret', None, 4),
        ('NEVER_ENABLED_CHOICE', 'spent_card', 'submit', None, 2),
    ]
