"""CLI contracts, independent rendering, and untrusted HTML text."""
from __future__ import annotations

from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
import os
import subprocess
import sys

import pytest

from branchcheck.analyzer import analyze, invalid_report
from branchcheck.cli import main
from branchcheck.loader import validate_story
from branchcheck.models import Limits
from branchcheck.reports import render_html, render_json, render_text


def story_data() -> dict:
    return {
        'schema_version': 1, 'title': '可运行示例', 'start': 'start',
        'variables': {'flag': False},
        'nodes': [
            {'id': 'start', 'title': '起点', 'choices': [
                {'id': 'finish', 'text': '完成', 'target': 'end', 'effects': {'flag': True}},
            ]},
            {'id': 'end', 'title': '结局', 'ending': True},
        ],
    }


def write_story(tmp_path: Path, data: dict | None = None) -> Path:
    path = tmp_path / 'story.json'
    path.write_text(json.dumps(story_data() if data is None else data, ensure_ascii=False), encoding='utf-8')
    return path


def test_json_stdout_is_only_parseable_json(tmp_path, capsys):
    story = write_story(tmp_path)
    assert main(['check', str(story), '--format', 'json']) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert captured.err == ''
    assert report['overall_status'] == 'passed'
    assert report['summary']['discovered_states'] == 2


@pytest.mark.parametrize('format_name,marker', [('text', '完整通过'), ('json', '"report_version"'), ('html', '<!doctype html>')])
def test_formats_to_stdout(tmp_path, capsys, format_name, marker):
    story = write_story(tmp_path)
    assert main(['check', str(story), '--format', format_name]) == 0
    captured = capsys.readouterr()
    assert marker in captured.out
    assert captured.err == ''


@pytest.mark.parametrize('format_name,suffix', [('text', 'txt'), ('json', 'json'), ('html', 'html')])
def test_output_file_creates_parents_and_status_goes_to_stderr(tmp_path, capsys, format_name, suffix):
    story = write_story(tmp_path)
    output = tmp_path / 'new' / 'reports' / f'report.{suffix}'
    assert main(['check', str(story), '--format', format_name, '--output', str(output)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ''
    assert '报告已写入' in captured.err
    text = output.read_text(encoding='utf-8')
    if format_name == 'json':
        assert json.loads(text)['overall_status'] == 'passed'
    else:
        assert '完整通过' in text


def test_story_errors_exit_one_and_warnings_exit_zero(tmp_path, capsys):
    data = story_data()
    data['nodes'][0]['choices'] = []
    path = write_story(tmp_path, data)
    assert main(['check', str(path), '--format', 'json']) == 1
    report = json.loads(capsys.readouterr().out)
    assert report['overall_status'] == 'failed'
    assert report['summary']['error_count'] > 0
    data = story_data()
    data['nodes'].append({'id': 'unused', 'title': '预留结局', 'ending': True})
    path = write_story(tmp_path, data)
    assert main(['check', str(path), '--format', 'json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['overall_status'] == 'warning'
    assert report['summary']['error_count'] == 0
    assert report['summary']['warning_count'] == 1


@pytest.mark.parametrize('option,value', [('--max-states', '1'), ('--max-transitions', '1')])
def test_limit_exit_three(tmp_path, capsys, option, value):
    data = story_data()
    data['nodes'][0]['choices'].append({'id': 'again', 'text': '再次选择', 'target': 'end'})
    path = write_story(tmp_path, data)
    assert main(['check', str(path), '--format', 'json', option, value]) == 3
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert not report['analysis_complete']
    assert report['overall_status'] == 'incomplete'
    assert 'ANALYSIS_LIMIT_REACHED' in {d['code'] for d in report['diagnostics']}
    assert captured.err == ''


def test_incomplete_status_takes_precedence_over_proven_error(tmp_path, capsys):
    data = story_data()
    data['nodes'][0]['assertions'] = [{'id': 'rule', 'condition': False, 'message': '起点规则失败'}]
    path = write_story(tmp_path, data)
    assert main(['check', str(path), '--format', 'json', '--max-states', '1']) == 3
    report = json.loads(capsys.readouterr().out)
    assert report['summary']['error_count'] == 1
    assert report['overall_status'] == 'incomplete'


@pytest.mark.parametrize('content', ['{', '{"a": 1, "a": 2}', '{"schema_version": true}'])
def test_invalid_input_is_structured_and_exit_two(tmp_path, capsys, content):
    path = tmp_path / 'invalid.json'
    path.write_text(content, encoding='utf-8')
    assert main(['check', str(path), '--format', 'json']) == 2
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report['overall_status'] == 'invalid'
    assert report['diagnostics'][0]['code'] == 'INVALID_INPUT'
    assert report['summary']['discovered_states'] == 0
    assert 'Traceback' not in captured.out + captured.err


def test_missing_file_and_invalid_utf8_are_ordinary_input_errors(tmp_path, capsys):
    path = tmp_path / 'missing.json'
    assert main(['check', str(path), '--format', 'json']) == 2
    assert json.loads(capsys.readouterr().out)['overall_status'] == 'invalid'
    path.write_bytes(b'\xff\xfe')
    assert main(['check', str(path), '--format', 'json']) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)['overall_status'] == 'invalid'
    assert 'Traceback' not in captured.out + captured.err


def test_output_failure_exit_two(tmp_path, capsys):
    path = write_story(tmp_path)
    assert main(['check', str(path), '--output', str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert '无法写入报告' in captured.err
    assert 'Traceback' not in captured.err


@pytest.mark.parametrize('option,value', [('--max-states', '0'), ('--max-transitions', '-1'), ('--max-states', 'x'), ('--max-states', '1.5')])
def test_bad_limit_arguments_follow_argparse(tmp_path, capsys, option, value):
    path = write_story(tmp_path)
    with pytest.raises(SystemExit) as caught:
        main(['check', str(path), option, value])
    assert caught.value.code == 2
    captured = capsys.readouterr()
    assert 'usage:' in captured.err
    assert 'Traceback' not in captured.err


def test_help_entry_point_is_usable():
    result = subprocess.run([sys.executable, '-m', 'branchcheck', '--help'], capture_output=True)
    assert result.returncode == 0
    assert b'branchcheck' in result.stdout
    assert result.stderr == b''


def test_redirected_cli_json_is_utf8_with_emoji_and_no_encoding_override(tmp_path):
    data = story_data()
    data['title'] = '剧情🔍 中文与完整 Unicode'
    path = write_story(tmp_path, data)
    env = os.environ.copy()
    env.pop('PYTHONIOENCODING', None)
    result = subprocess.run([sys.executable, '-m', 'branchcheck', 'check', str(path), '--format', 'json'],
                            capture_output=True, env=env)
    assert result.returncode == 0
    assert json.loads(result.stdout.decode('utf-8'))['story_title'] == data['title']
    assert result.stderr == b''


def test_renderers_do_not_mutate_report_and_json_is_stable():
    report = analyze(validate_story(story_data()), Limits())
    before = deepcopy(report)
    first = render_json(report)
    assert json.loads(first) == report
    assert render_json(report) == first
    assert '完整通过' in render_text(report)
    assert '完整通过' in render_html(report)
    assert report == before


class Tags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


def test_html_escapes_story_text_conditions_paths_and_variables():
    attack = '<script>alert("x & y")</script> \'quoted\''
    data = story_data()
    data['title'] = attack
    data['nodes'][0]['title'] = attack
    data['nodes'][0]['choices'][0]['text'] = attack
    data['nodes'][1]['title'] = attack
    data['nodes'][1]['assertions'] = [{'id': 'failure', 'condition': False, 'message': attack}]
    report = analyze(validate_story(data), Limits())
    # Rendering also escapes dictionaries even if the producer did not enforce IDs.
    failure = next(d for d in report['diagnostics'] if d['code'] == 'ASSERTION_FAILED')
    failure['paths'][0]['final_state']['variables'][attack] = False
    report['local_condition_checks'][0]['reason'] = attack
    html = render_html(report)
    assert '<script>' not in html
    assert '&lt;script&gt;' in html
    assert '&quot;x &amp; y&quot;' in html
    assert '&#x27;quoted&#x27;' in html
    parser = Tags()
    parser.feed(html)
    assert all(tag not in ('script', 'iframe', 'img', 'link') for tag, attrs in parser.tags)
    assert all(not any(name.startswith('on') for name in attrs) for tag, attrs in parser.tags)
    assert attack in ''.join(parser.text)
    assert 'before' not in html  # Changes use Chinese table headers.
    assert '变化变量' in html
    assert '到达时完整变量快照' in html


def test_invalid_html_escapes_error_message():
    report = invalid_report('<script>alert("bad")</script> &', Limits())
    html = render_html(report)
    assert '<script>' not in html
    assert '&lt;script&gt;alert(&quot;bad&quot;)&lt;/script&gt; &amp;' in html


def test_unreachable_html_has_no_fake_execution_path():
    data = story_data()
    data['nodes'].append({'id': 'unused', 'title': '未到达'})
    data['nodes'][0]['choices'].append({'id': 'blocked', 'text': '条件关闭', 'target': 'unused', 'condition': False})
    report = analyze(validate_story(data), Limits())
    unreachable = next(d for d in report['diagnostics'] if d['code'] == 'UNREACHABLE_NODE')
    assert unreachable['paths'] == []
    html = render_html(report)
    assert '无可达路径' in html
    assert 'start / blocked' in html
    assert '条件仅为检查线索' in html


def test_zero_step_path_has_initial_snapshot_and_no_change_is_explicit():
    data = story_data()
    data['nodes'][0]['assertions'] = [{'id': 'rule', 'condition': False, 'message': '起点失败'}]
    data['nodes'][0]['choices'][0]['effects'] = {}
    data['nodes'][1]['assertions'] = [{'id': 'rule', 'condition': False, 'message': '结局失败'}]
    report = analyze(validate_story(data), Limits())
    html = render_html(report)
    assert '零步路径：问题出现在初始状态' in html
    assert '初始状态' in html
    assert '变量变化：{}（无变化）' in html


def test_dead_end_shows_blocked_conditions_and_escapes_choice_text():
    data = story_data()
    attack = '<script>alert("blocked & unsafe")</script>'
    choice = data['nodes'][0]['choices'][0]
    choice['condition'] = {'var': 'flag', 'eq': True}
    choice['text'] = attack
    report = analyze(validate_story(data), Limits())
    diagnostic = next(d for d in report['diagnostics'] if d['code'] == 'DEAD_END')
    assert diagnostic['related_conditions'][0]['condition'] == choice['condition']
    text = render_text(report)
    assert '本状态下未满足的选择条件' in text
    assert 'finish' in text
    assert '"flag"' in text
    html = render_html(report)
    assert '本状态下未满足的选择条件' in html
    assert '<script>' not in html
    assert '&lt;script&gt;alert(&quot;blocked &amp; unsafe&quot;)&lt;/script&gt;' in html
