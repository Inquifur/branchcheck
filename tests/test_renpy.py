"""Semantic oracle: handwritten references and explicit source-level outcomes."""
from collections import deque
from copy import deepcopy
import json
from pathlib import Path

import pytest

from branchcheck.analyzer import analyze
from branchcheck.cli import main
from branchcheck.conditions import evaluate
from branchcheck.loader import load_story, validate_story
from branchcheck.models import Limits
from branchcheck.renpy import ImportError, loads_renpy, load_renpy, project_report
from branchcheck.reports import render_html, render_text

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples' / 'renpy'


def states(model):
    story = validate_story(model)
    index = {v: i for i, v in enumerate(sorted(story.variables))}
    initial = sum(1 << index[v] for v, value in story.variables.items() if value)
    nodes = {n.id: n for n in story.nodes}
    seen = {(story.start, initial)}
    queue = deque(seen)
    while queue:
        nid, mask = queue.popleft()
        if nodes[nid].ending:
            continue
        for c in nodes[nid].choices:
            if evaluate(c.condition, mask, index):
                values = {v: bool(mask & 1 << bit) for v, bit in index.items()}
                values.update(c.effects)
                target = (c.target, sum(1 << index[v] for v in values if values[v]))
                if target not in seen:
                    seen.add(target)
                    queue.append(target)
    return {(nid, tuple((v, bool(mask & 1 << bit)) for v, bit in index.items()))
            for nid, mask in seen}


def ending_values(model):
    endings = {n['id'] for n in model['nodes'] if n.get('ending')}
    return {values for nid, values in states(model) if nid in endings}


@pytest.mark.parametrize('name,reference,expected', [
    ('elif_priority', 'elif_priority', [{'first': True, 'second': True, 'result_first': True, 'result_second': False}]),
    ('menu_fallback', 'menu_fallback', [{'has_access': False, 'continued': True}]),
    ('nested_flow', 'nested_flow_assignment_merge', [
        {'has_clue': True, 'alarmed': False, 'reviewed': True},
        {'has_clue': False, 'alarmed': False, 'reviewed': True},
        {'has_clue': False, 'alarmed': False, 'reviewed': False}]),
])
def test_handwritten_equivalence_and_human_expected(name, reference, expected):
    imported = load_renpy(EXAMPLES / (name + '.rpy'))
    manual = json.loads((EXAMPLES / 'reference' / (reference + '.json')).read_text(encoding='utf-8'))
    assert ending_values(imported.model) == ending_values(manual) == {
        tuple(sorted(values.items())) for values in expected}
    assert analyze(imported.story)['analysis_complete']
    assert analyze(imported.story)['summary']['error_count'] == 0


def test_exact_source_locations_stability_and_fallthrough():
    imported = load_renpy(EXAMPLES / 'minimal_ok.rpy')
    assert imported == load_renpy(EXAMPLES / 'minimal_ok.rpy')
    assert 'D:' not in json.dumps(imported.sources)
    src = next(r for r in imported.sources['mappings'] if r['statement_type'] == 'assign' and not r['choice_id'])
    assert src['start_line'] == 6
    assert src['snippet'] == '$ has_photo = True'
    assert all(r['pointer'].startswith(('/nodes/', '/variables/')) for r in imported.sources['mappings'])
    fallthrough = load_renpy(EXAMPLES / 'label_fallthrough.rpy')
    assert ending_values(fallthrough.model) == {(('crossed', True),)}


def test_menu_choice_sequences_and_no_skip():
    imported = load_renpy(EXAMPLES / 'nested_flow.rpy')
    nodes = {n['id']: n for n in imported.model['nodes']}
    refs = {(r['node_id'], r['choice_id']): r for r in imported.sources['mappings']}
    for captions, label, expected in [
        (['搜索档案室', '带走线索'], 'truth', (True, True)),
        (['搜索档案室', '只做记录'], 'leave', (False, True)),
        (['直接撤离'], 'empty', (False, False)),
    ]:
        values = dict(imported.model['variables'])
        position = imported.model['start']
        choices = iter(captions)
        index = {v: i for i, v in enumerate(sorted(values))}
        validated = {n.id: n for n in imported.story.nodes}
        for _ in range(100):
            if nodes[position].get('ending'):
                break
            mask = sum(1 << index[v] for v in values if values[v])
            enabled = [c for c in validated[position].choices if evaluate(c.condition, mask, index)]
            menu = [c for c in enabled if refs[(position, c.id)].get('guard_role') == 'menu_option']
            if menu:
                assert len(menu) == len(enabled)  # no unconditional menu skip
                caption = next(choices)
                selected = next(c for c in menu if c.text == '玩家选择：' + caption)
            else:
                assert len(enabled) == 1
                selected = enabled[0]
            values.update(selected.effects)
            position = selected.target
        else:
            pytest.fail('source path failed to terminate')
        assert refs[(position, None)]['label'] == label
        assert (values['has_clue'], values['reviewed']) == expected


@pytest.mark.parametrize('body,expected', [
    ('if False:\n        $ x = True', False),
    ('if x:\n        $ x = False\n    elif True:\n        $ x = True', False),
    ('menu:\n        "a":\n            $ x = False\n        "b":\n            pass', None),
])
def test_assignment_branch_isolation_and_merge(body, expected):
    imported = loads_renpy('default x = True\nlabel start:\n    ' + body + '\n    return\n')
    actual = ending_values(imported.model)
    if expected is None:
        assert actual == {(('x', True),), (('x', False),)}
    else:
        # no-else false leaves the initial True unchanged
        assert actual == {(('x', True if body.startswith('if False') else expected),)}


def test_default_after_label_bom_crlf_quotes_repeated_text():
    text = '\ufefflabel start:\r\n    "same # :" # \' comment\r\n    "same # :"\r\n    $ x = False\r\n    return\r\ndefault x = True\r\n'
    imported = loads_renpy(text, '/not/exposed/story.rpy')
    narrations = [r['start_line'] for r in imported.sources['mappings'] if r['statement_type'] == 'narration' and not r['choice_id']]
    assert narrations == [2, 3]
    assert ending_values(imported.model) == {(('x', False),)}
    assert imported.sources['file'] == 'story.rpy'


@pytest.mark.parametrize('expression', ['True', 'False', 'x', 'not x', 'x == True', 'x != False', '(x and True) or not False', 'not not x'])
def test_allowed_expression_forms(expression):
    imported = loads_renpy(f'default x = True\nlabel start:\n    if {expression}:\n        pass\n    return\n')
    assert analyze(imported.story)['analysis_complete']


@pytest.mark.parametrize('expression', ['x == True == True', 'True == x', 'x is True', 'x.a', 'x[0]', 'f()', '1', 'x + 1', '(x := True)', 'x == 1', 'unknown', 'x != x'])
def test_expression_whitelist_rejects(expression):
    with pytest.raises(ImportError, match='story.rpy:3:'):
        loads_renpy(f'default x = True\nlabel start:\n    if {expression}:\n        pass\n    return\n')


@pytest.mark.parametrize('statement', [
    'call other', 'python:', '$ x = not x', '$ do_something()',
    'jump expression target', 'return True', 'while True:', 'scene bg',
    'show e', 'hide e', 'with dissolve', 'play music "x"', 'screen a:',
    'e "hello"', 'menu named:', 'define a = True', 'init:', 'image a = "a"',
    '"[x]"', '"{b}text"', 'r"text"', '"a" "b"', '"""text"""',
    '"\\x5b"', 'elif True:', 'else:', '$ unknown = False',
])
def test_reject_even_unreachable_source(statement):
    with pytest.raises(ImportError) as exc:
        loads_renpy('default x = False\nlabel start:\n    return\nlabel unused:\n    ' + statement + '\n    return\n')
    assert exc.value.source['start_line'] == 5


@pytest.mark.parametrize('text', [
    'label start:\n\treturn', 'label start:\n  return', 'label start:\n        return',
    'label start:\nlabel other:\n    return', 'label .start:\n    return',
    'label start(x):\n    return', 'label start:\n    pass',
    'label start:\n    jump missing', 'label start:\n    return\nlabel start:\n    return',
    'default x = True\ndefault x = False\nlabel start:\n    return',
    'default x = 1\nlabel start:\n    return', 'label other:\n    return',
    'label start:\n    menu:\n        "prompt"\n    return',
    'label start:\n    if True:\n    return',
])
def test_malformed_input_rejected(text):
    with pytest.raises(ImportError):
        loads_renpy(text)


def test_closed_loop_projection_and_unknown_limits():
    imported = loads_renpy('label start:\n    jump start\nlabel unused:\n    return\n')
    report = project_report(analyze(imported.story), imported)
    assert report['overall_status'] == 'failed'
    assert any(d['code'] == 'NO_REACHABLE_ENDING' for d in report['diagnostics'])
    assert any(d['code'] == 'UNREACHABLE_NODE' for d in report['diagnostics'])
    assert any(d['code'] == 'NO_ENDING_PATH' for d in report['diagnostics'])
    limit = project_report(analyze(imported.story, Limits(1, 1)), imported)
    assert limit['overall_status'] == 'incomplete'
    assert {d['code'] for d in limit['diagnostics']} == {'ANALYSIS_LIMIT_REACHED'}


def test_original_menu_conditions_and_ordered_guard_not_hidden():
    imported = load_renpy(EXAMPLES / 'menu_fallback.rpy')
    report = project_report(analyze(imported.story), imported)
    assert any(d['code'] == 'NEVER_ENABLED_CHOICE' for d in report['diagnostics'])
    imported = loads_renpy('label start:\n    if True:\n        pass\n    elif True:\n        pass\n    return\n')
    report = project_report(analyze(imported.story), imported)
    finding = next(d for d in report['diagnostics'] if d['code'] == 'CONTRADICTORY_CONDITION')
    assert finding['condition_scope'] == 'effective_guard'
    assert '不是原表达式' in finding['message']
    assert report['raw_diagnostics']


def test_html_escaped_source_and_boundary():
    imported = loads_renpy('label start:\n    "<script>attack & \\"quote\\"</script>"\n    jump start\n')
    report = project_report(analyze(imported.story), imported)
    html = render_html(report)
    assert '<script>' not in html
    assert '&lt;script&gt;' in html
    assert '单文件受限子集' in html
    assert 'synthetic' in html
    assert 'story.rpy:2-2' in render_text(report)


def test_resource_limits_no_recursion_traceback():
    for text in ['#' * 1_048_577, 'label start:\n' + '    if True:\n' * 100,
                 'label start:\n    if ' + 'not ' * 40 + 'True:\n        pass\n    return']:
        with pytest.raises(ImportError):
            loads_renpy(text)


def test_early_return_and_static_jump_do_not_continue():
    original = (EXAMPLES / 'nested_flow.rpy').read_text(encoding='utf-8')
    imported = loads_renpy(original.replace('default alarmed = False', 'default alarmed = True'))
    endings = {r['node_id']: r for r in imported.sources['mappings'] if r['statement_type'] == 'return' and r['choice_id'] is None}
    observed = {(endings[nid]['label'], values) for nid, values in states(imported.model) if nid in endings}
    assert observed == {
        ('start', (('alarmed', True), ('has_clue', False), ('reviewed', False))),
        ('empty', (('alarmed', True), ('has_clue', False), ('reviewed', False))),
    }


def test_expression_and_compile_resource_budgets():
    # A shallow, wide chain must be bounded even though recursion is small.
    wide = ' or '.join(['x'] * 150)
    with pytest.raises(ImportError, match='资源上限|AST 节点'):
        loads_renpy(f'default x = True\nlabel start:\n    if {wide}:\n        pass\n    return')
    branches = '    if x:\n        pass\n' + '    elif x:\n        pass\n' * 400
    with pytest.raises(ImportError, match='编译守卫累计'):
        loads_renpy('default x = False\nlabel start:\n' + branches + '    return')


@pytest.mark.parametrize('name', ['True', 'False', 'not'])
def test_reserved_default_rejected(name):
    with pytest.raises(ImportError):
        loads_renpy(f'default {name} = True\nlabel start:\n    return')


def test_second_output_replace_failure_restores_pair(tmp_path, capsys, monkeypatch):
    import branchcheck.cli as cli
    output = tmp_path / 'model.json'
    sidecar = tmp_path / 'model.sources.json'
    output.write_text('previous model', encoding='utf-8')
    sidecar.write_text('previous mapping', encoding='utf-8')
    real_replace = cli.os.replace
    def replace(source, target):
        if target == sidecar:
            raise OSError('simulated second replace failure')
        real_replace(source, target)
    monkeypatch.setattr(cli.os, 'replace', replace)
    assert main(['import-renpy', str(EXAMPLES / 'minimal_ok.rpy'), '--output', str(output)]) == 2
    assert output.read_text(encoding='utf-8') == 'previous model'
    assert sidecar.read_text(encoding='utf-8') == 'previous mapping'
    assert '未更新' in capsys.readouterr().err
    assert not list(tmp_path.glob('.branchcheck-*'))


def test_cli_export_check_errors_and_preservation(tmp_path, capsys):
    output = tmp_path / 'model.json'
    assert main(['import-renpy', str(EXAMPLES / 'minimal_ok.rpy'), '--output', str(output)]) == 0
    capsys.readouterr()
    assert load_story(output)
    sidecar = output.with_name('model.sources.json')
    original = (output.read_bytes(), sidecar.read_bytes())
    assert main(['import-renpy', str(EXAMPLES / 'unsupported.rpy'), '--output', str(output)]) == 2
    assert original == (output.read_bytes(), sidecar.read_bytes())
    assert '本次未更新' in capsys.readouterr().err
    assert main(['check', str(output), '--format', 'json']) == 0
    assert 'import_context' not in json.loads(capsys.readouterr().out)
    for name, code in [('minimal_ok', 0), ('unsupported', 2)]:
        assert main(['check-renpy', str(EXAMPLES / (name+'.rpy')), '--format', 'json']) == code
        r = json.loads(capsys.readouterr().out)
        assert r['import_complete'] == (code == 0)
        if code == 2:
            assert r['analysis_started'] is False
            assert r['summary']['discovered_states'] == 0
            assert r['diagnostics'][0]['importer']['source']['start_line'] == 2
    assert main(['check-renpy', str(EXAMPLES / 'minimal_ok.rpy'), '--max-states', '1', '--format', 'json']) == 3
    assert json.loads(capsys.readouterr().out)['overall_status'] == 'incomplete'


def test_no_script_overwrite_or_side_effect(tmp_path, capsys):
    path = tmp_path / 'source.rpy'
    content = 'label start:\n    return\n'
    path.write_text(content, encoding='utf-8')
    for command in ('import-renpy', 'check-renpy'):
        assert main([command, str(path), '--output', str(path)]) == 2
        capsys.readouterr()
        assert path.read_text(encoding='utf-8') == content
    marker = tmp_path / 'must_not_exist'
    with pytest.raises(ImportError):
        loads_renpy(f'label start:\n    if __import__("pathlib").Path({str(marker)!r}).touch():\n        pass\n    return')
    assert not marker.exists()


def test_fault_in_test_copy_then_restore(tmp_path, capsys):
    path = tmp_path / 'adapted_copy.rpy'
    clean = 'label start:\n    return\n'
    path.write_text(clean, encoding='utf-8')
    assert main(['check-renpy', str(path), '--format', 'json']) == 0
    assert json.loads(capsys.readouterr().out)['overall_status'] == 'passed'
    path.write_text(clean.replace('return', 'jump start'), encoding='utf-8')
    assert main(['check-renpy', str(path), '--format', 'json']) == 1
    assert 'NO_REACHABLE_ENDING' in {d['code'] for d in json.loads(capsys.readouterr().out)['diagnostics']}
    path.write_text(clean, encoding='utf-8')
    assert main(['check-renpy', str(path), '--format', 'json']) == 0
    assert json.loads(capsys.readouterr().out)['diagnostics'] == []
