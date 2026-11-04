"""Pure, deterministic report renderers. All HTML content is escaped text."""
from __future__ import annotations

from html import escape
import json
from typing import Any, Mapping


STATUS_LABELS = {
    'invalid': '输入无效',
    'incomplete': '分析未完成',
    'failed': '发现错误',
    'warning': '有警告',
    'passed': '完整通过',
}
REACHABILITY_LABELS = {
    'reachable': '可达', 'unreachable': '不可达', 'unknown': '未知',
    'enabled': '已触发', 'never_enabled': '从未可用',
    'source_unreachable': '源节点不可达',
}
OBSERVATION_LABELS = {
    'triggered': '实际搜索已触发',
    'not_triggered': '完整搜索中未观察到触发',
    'unknown': '尚未观察到 / 未知',
}
EVIDENCE_KIND_LABELS = {
    'input_error': '输入错误',
    'specific_state': '具体状态证据',
    'global_conclusion': '完整搜索得出的全局结论',
    'global_conclusion_with_state_samples': '全局结论与代表状态样本',
    'local_proof': '局部穷举证明',
    'analysis_status': '分析状态',
    'static_variable_index': '静态变量索引',
    'static_write_location': '静态写入位置',
}
SUMMARY_LABELS = {
    'node_count': '节点', 'variable_count': '变量',
    'declared_ending_count': '声明结局', 'reached_ending_count': '已到达结局',
    'discovered_states': '发现状态', 'expanded_states': '展开状态',
    'transition_count': '有效转移', 'error_count': '错误', 'warning_count': '警告',
}
MODEL_BOUNDARY = (
    '“完整通过”仅表示在该布尔模型和已声明规则下未发现相应问题，'
    '不代表故事质量保证；不会推测作者未声明的剧情规则。'
)


def render_json(report: dict[str, Any]) -> str:
    """No time stamps or generated IDs: equal report data yields equal text."""
    return json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _bool_text(value: Any) -> str:
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    return '未知'


def _result_text(value: Any) -> str:
    if value is True:
        return '满足'
    if value is False:
        return '不满足'
    return '未知'


def _evidence_label(value: Any) -> str:
    return EVIDENCE_KIND_LABELS.get(str(value), str(value or '未标注'))


def _ordered_diagnostics(report: dict[str, Any]) -> list[dict[str, Any]]:
    # Stable sort retains analyzer order within the same severity.
    return sorted(report.get('diagnostics', ()),
                  key=lambda d: {'error': 0, 'warning': 1}.get(d['severity'], 2))


def _source_ref_text(ref: Mapping[str, Any]) -> str:
    labels = []
    for key in ('node_id', 'choice_id', 'assertion_id'):
        if ref.get(key):
            labels.append(f'{key}={ref[key]}')
    if ref.get('role'):
        labels.append(str(ref['role']))
    suffix = f"（{'；'.join(labels)}）" if labels else ''
    source = ref.get('renpy_source')
    origin = ''
    if source:
        origin = (f" {source['file']}:{source['start_line']}-{source['end_line']} "
                  f"label {source['label']} · {source['snippet']} "
                  f"({'自动执行' if source['synthetic'] else '原始语句/玩家选择'})")
    return f"{ref.get('pointer', '') or '/'}{suffix}{origin}"


def _text_variable_sources(lines: list[str], sources: list[dict[str, Any]]) -> None:
    if not sources:
        return
    lines.append('变量赋值位置线索（静态声明不等于执行证据）：')
    for source in sources:
        lines.append(
            f"  {source.get('variable', '未知变量')}：初始值 "
            f"{_bool_text(source.get('initial_value'))}；"
            f"{source.get('initial_pointer', '')}")
        writes = source.get('writes', ())
        if source.get('renpy_source'):
            lines.append('    ' + _source_ref_text(source))
        if not writes:
            lines.append('    无显式 effects 写入位置。')
        for write in writes:
            if write.get('renpy_source'):
                lines.append('    ' + _source_ref_text(write))
            reachability = REACHABILITY_LABELS.get(
                write.get('source_reachability'),
                write.get('source_reachability', '未知'))
            observation = OBSERVATION_LABELS.get(
                write.get('observation_status'),
                write.get('observation_status', '未知'))
            lines.append(
                f"    静态写入 {write.get('pointer', '')}：设为 "
                f"{_bool_text(write.get('value'))}；源节点{reachability}；"
                f"{observation}")


def render_text(report: dict[str, Any]) -> str:
    status = report['overall_status']
    summary = report['summary']
    diagnostics = _ordered_diagnostics(report)
    lines = [
        f"BranchCheck · {report['story_title'] or '未载入剧情'}",
        f"状态：{STATUS_LABELS.get(status, status)} ({status})",
        f"分析完整性：{'完整' if report['analysis_complete'] else '未完成'}",
    ]
    if not report['analysis_complete'] and status == 'incomplete':
        lines.append('重要：搜索未完成；未访问节点和未观察到的选择保持未知，不能据此认定不可达或通过。')
    if report['stop_reason']:
        lines.append(f"停止原因：{report['stop_reason']}")
    lines.append('；'.join(
        f"{label} {summary[key]}" for key, label in SUMMARY_LABELS.items()))
    lines.append(
        f"诊断目录：错误 {summary['error_count']}；警告 {summary['warning_count']}")
    for index, diagnostic in enumerate(diagnostics, start=1):
        lines.append(
            f"  {index}. [{diagnostic['severity']}] {diagnostic['code']}："
            f"{diagnostic['message']}")
    lines.append(
        f"上限：状态 {report['limits']['max_states']}；"
        f"转移 {report['limits']['max_transitions']}")

    for index, diagnostic in enumerate(diagnostics, start=1):
        location = ', '.join(
            f"{name}={diagnostic[name]}"
            for name in ('node_id', 'choice_id', 'assertion_id')
            if diagnostic.get(name))
        paths = list(diagnostic.get('paths', ()))[:3]
        lines.extend([
            '',
            f"诊断 {index} [{diagnostic['severity']}] {diagnostic['code']}"
            + (f' ({location})' if location else ''),
            diagnostic['message'],
            f"证据类型：{_evidence_label(diagnostic.get('evidence_kind'))}",
            f"受影响状态：{diagnostic.get('affected_state_count', 0)}；"
            f"代表路径：{len(paths)}（最多 3 条，代表路径不等同于全部路径）",
        ])
        refs = diagnostic.get('source_refs', ())
        if refs:
            lines.append(f"主要源位置：{_source_ref_text(refs[0])}")
        if diagnostic.get('condition') is not None:
            lines.append(f"条件：{_json(diagnostic['condition'])}")
        if diagnostic.get('local_proof'):
            proof = diagnostic['local_proof']
            lines.append(
                f"局部证明：{proof.get('status')}；"
                f"变量 {proof.get('variable_count')}；"
                f"可满足={_bool_text(proof.get('satisfiable'))}")
        if diagnostic.get('related_conditions'):
            lines.append('本状态下未满足的选择条件：')
            for choice in diagnostic['related_conditions']:
                pointer = ''
                if choice.get('source_refs'):
                    pointer = f"；{choice['source_refs'][0].get('pointer', '')}"
                lines.append(
                    f"  {choice['choice_id']} {choice['text']}："
                    f"{_json(choice['condition'])}{pointer}")
        if diagnostic['code'] in ('UNREACHABLE_NODE', 'UNREACHABLE_ENDING'):
            lines.append('无可达路径。以下声明入边及条件仅为检查线索，不是执行路径：')
            for edge in diagnostic.get('incoming_edges', ()):
                reachability = REACHABILITY_LABELS.get(
                    edge.get('source_reachability'),
                    edge.get('source_reachability', '未知'))
                pointer = ''
                if edge.get('source_refs'):
                    pointer = f"；{edge['source_refs'][0].get('pointer', '')}"
                lines.append(
                    f"  {edge['source_node_id']} / {edge['choice_id']}；"
                    f"源节点{reachability}；条件 {_json(edge['condition'])}{pointer}")
            if not diagnostic.get('incoming_edges'):
                lines.append('  无声明入边。')
        for number, path in enumerate(paths, start=1):
            initial = path['initial_state']
            lines.append(
                f"  路径 {number}：起点 {initial['node_title']} "
                f"({initial['node_id']}) {_json(initial['variables'])}")
            for step in path['steps']:
                lines.append(
                    f"    {step['source_title']} ({step['source_node_id']}) "
                    f"--[{step['choice_id']} {step['choice_text']}]--> "
                    f"{step['target_title']} ({step['target_node_id']})；"
                    f"变化 {_json(step['changes'])}")
            final = path['final_state']
            lines.append(
                f"    最终状态：{final['node_title']} "
                f"({final['node_id']}) {_json(final['variables'])}")
            for explanation in path.get('condition_explanations', ()):
                root = explanation.get('explanation', {})
                pointer = ''
                if explanation.get('source_refs'):
                    pointer = f"；{explanation['source_refs'][0].get('pointer', '')}"
                lines.append(
                    f"    条件解释：{explanation.get('role', '相关条件')}；"
                    f"根结果：{_result_text(root.get('result'))}{pointer}")
        _text_variable_sources(lines, diagnostic.get('variable_sources', []))

    skipped = [
        item for item in report.get('local_condition_checks', ())
        if item['status'] == 'skipped'
    ]
    if skipped:
        lines.extend(['', f'局部条件检查 skipped：{len(skipped)} 项（不代表通过）。'])
        lines.extend(
            f"  {item['node_id']}/{item['choice_id']}："
            f"{item.get('reason') or '超过枚举规模'}"
            for item in skipped)
    lines.extend(['', MODEL_BOUNDARY])
    if report.get('import_context'):
        context = report['import_context']
        lines.insert(0, context['boundary'])
        lines.insert(1, f"作者视图抑制 {report['projection']['suppressed_count']} 条自动守卫警告；raw_diagnostics 保留全部原始诊断。")
    return '\n'.join(lines) + '\n'


def _e(value: Any) -> str:
    return escape(str(value), quote=True)


def _pre(value: Any) -> str:
    return '<pre>' + _e(json.dumps(
        value, ensure_ascii=False, indent=2, sort_keys=True)) + '</pre>'


def _source_refs_html(
        refs: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        node_anchors: Mapping[str, str], *, heading: str = '源位置') -> str:
    if not refs:
        return ''
    parts = [f'<div class="source-refs"><h4>{_e(heading)}</h4><ul>']
    for ref in refs:
        parts.append('<li>')
        if ref.get('role'):
            parts.append(f'<span class="role">{_e(ref["role"])}</span> ')
        parts.append(
            f'<code class="pointer" tabindex="0">'
            f'{_e(ref.get("pointer", "") or "/")}</code>')
        ids = []
        node_id = ref.get('node_id')
        if node_id:
            label = f'node_id={node_id}'
            anchor = node_anchors.get(str(node_id))
            if anchor:
                ids.append(
                    f'<a href="#{_e(anchor)}"><code>{_e(label)}</code></a>')
            else:
                ids.append(f'<code>{_e(label)}</code>')
        for key in ('choice_id', 'assertion_id'):
            if ref.get(key):
                ids.append(f'<code>{_e(key)}={_e(ref[key])}</code>')
        if ids:
            parts.append('<span class="source-ids">' + ' · '.join(ids) + '</span>')
        title = ref.get('choice_text') or ref.get('assertion_message') or ref.get('node_title')
        if title:
            parts.append(f'<span class="source-title">{_e(title)}</span>')
        source = ref.get('renpy_source')
        if source:
            label = ('自动执行（synthetic，锚定原结构）' if source['synthetic']
                     else '原始语句 / 玩家选择')
            parts.append(f'<details><summary>{_e(label)} · {_e(source["file"])}:{source["start_line"]}-{source["end_line"]} · label {_e(source["label"])}</summary>')
            parts.append(_pre(source['snippet']))
            if 'original_condition' in source:
                parts.append('<p>原表达式 / 编译有效守卫（含前序分支约束时不能视为独立原条件证明）</p>')
                parts.append(_pre({'original': source['original_condition'], 'effective': source['effective_guard']}))
            parts.append('</details>')
        parts.append('</li>')
    parts.append('</ul></div>')
    return ''.join(parts)


def _state_html(
        state: dict[str, Any], label: str,
        node_anchors: Mapping[str, str], *, full_snapshot: bool = False) -> str:
    node_id = state['node_id']
    anchor = node_anchors.get(node_id)
    node_label = f'<code>{_e(node_id)}</code>'
    if anchor:
        node_label = f'<a href="#{_e(anchor)}">{node_label}</a>'
    heading = f"<h4>{_e(label)}：{_e(state['node_title'])} {node_label}</h4>"
    source = _source_refs_html(
        state.get('source_refs', ()), node_anchors, heading='状态源位置')
    snapshot = _pre(state['variables'])
    if full_snapshot:
        snapshot = (
            '<details class="snapshot"><summary>到达时完整变量快照</summary>'
            + snapshot + '</details>')
    return heading + source + snapshot


def _condition_node_html(explanation: Any) -> str:
    if not isinstance(explanation, dict):
        return f'<li>无法识别的解释节点 {_pre(explanation)}</li>'
    kind = explanation.get('kind')
    result = explanation.get('result')
    result_class = 'satisfied' if result is True else 'unsatisfied' if result is False else 'unknown'
    result_html = (
        f'<strong class="condition-result {result_class}">'
        f'{_e(_result_text(result))}</strong>')
    if kind == 'const':
        label = f"常量 <code>{_e(_bool_text(explanation.get('value')))}</code> → {result_html}"
    elif kind == 'var':
        label = (
            f"变量 <code>{_e(explanation.get('name', ''))}</code>：要求 "
            f"<code>{_e(_bool_text(explanation.get('expected')))}</code>，实际 "
            f"<code>{_e(_bool_text(explanation.get('actual')))}</code> → "
            f"{result_html}")
    else:
        labels = {'all': '全部满足', 'any': '任一满足', 'not': '取反'}
        label = f"{_e(labels.get(str(kind), str(kind)))} <code>{_e(kind)}</code> → {result_html}"
    children = explanation.get('children', ())
    nested = ''
    if children:
        nested = '<ul>' + ''.join(_condition_node_html(child) for child in children) + '</ul>'
    return f'<li><span class="condition-line">{label}</span>{nested}</li>'


def _condition_explanations_html(
        explanations: list[dict[str, Any]],
        node_anchors: Mapping[str, str]) -> str:
    if not explanations:
        return ''
    parts = ['<section class="condition-explanations"><h4>具体状态下的条件解释</h4>']
    for item in explanations:
        root = item.get('explanation', {})
        parts.append(
            '<details class="condition-explanation">'
            f'<summary>{_e(item.get("role", "相关条件"))}：'
            f'{_e(_result_text(root.get("result")))}</summary>')
        if item.get('text'):
            parts.append(f'<p>{_e(item["text"])}</p>')
        parts.append(_source_refs_html(
            item.get('source_refs', ()), node_anchors, heading='条件源位置'))
        parts.append('<ul class="condition-tree">')
        parts.append(_condition_node_html(root))
        parts.append('</ul>')
        if item.get('condition') is not None:
            parts.append(
                '<details class="raw-condition"><summary>原始条件结构</summary>'
                + _pre(item['condition']) + '</details>')
        parts.append('</details>')
    parts.append('</section>')
    return ''.join(parts)


def _path_html(
        path: dict[str, Any], number: int,
        node_anchors: Mapping[str, str]) -> str:
    parts = [
        f'<details class="path"><summary>代表路径 {number} · '
        f'{len(path["steps"])} 次选择</summary>',
        _state_html(path['initial_state'], '初始状态', node_anchors),
    ]
    if path['steps']:
        parts.append('<ol class="steps">')
        for step in path['steps']:
            source_anchor = node_anchors.get(step['source_node_id'])
            target_anchor = node_anchors.get(step['target_node_id'])
            source_id = f'<code>{_e(step["source_node_id"])}</code>'
            target_id = f'<code>{_e(step["target_node_id"])}</code>'
            if source_anchor:
                source_id = f'<a href="#{_e(source_anchor)}">{source_id}</a>'
            if target_anchor:
                target_id = f'<a href="#{_e(target_anchor)}">{target_id}</a>'
            parts.append(
                f'<li><b>{_e(step["source_title"])}</b> {source_id} → '
                f'<b>{_e(step["target_title"])}</b> {target_id}'
                f'<p>选择 <code>{_e(step["choice_id"])}</code>：'
                f'{_e(step["choice_text"])}</p>')
            parts.append(_source_refs_html(
                step.get('source_refs', ()), node_anchors,
                heading='实际触发选择的源位置'))
            if step['changes']:
                parts.append(
                    '<div class="table-wrap"><table><thead><tr>'
                    '<th>变化变量</th><th>之前</th><th>之后</th>'
                    '</tr></thead><tbody>')
                for name, change in step['changes'].items():
                    parts.append(
                        f'<tr><td><code>{_e(name)}</code></td>'
                        f'<td>{_e(_json(change["before"]))}</td>'
                        f'<td>{_e(_json(change["after"]))}</td></tr>')
                parts.append('</tbody></table></div>')
            else:
                parts.append('<p class="muted">变量变化：{}（无变化）</p>')
            parts.append('</li>')
        parts.append('</ol>')
    else:
        parts.append('<p>零步路径：问题出现在初始状态。</p>')
    parts.append(_state_html(
        path['final_state'], '最终状态', node_anchors, full_snapshot=True))
    parts.append(_condition_explanations_html(
        path.get('condition_explanations', []), node_anchors))
    parts.append('</details>')
    return ''.join(parts)


def _variable_sources_html(
        sources: list[dict[str, Any]],
        node_anchors: Mapping[str, str]) -> str:
    if not sources:
        return ''
    parts = [
        '<details class="variable-sources"><summary>变量赋值位置线索</summary>',
        '<p class="evidence-note">以下是静态声明线索，不证明选择可执行。'
        '“已触发”只来自实际搜索记录；分析未完成时未观察到的写入保持未知。</p>',
    ]
    for source in sources:
        if source.get('renpy_source'):
            parts.append(_source_refs_html([source], node_anchors, heading='default 源位置'))
        parts.append(
            '<section class="variable-source">'
            f'<h5><code>{_e(source.get("variable", ""))}</code></h5>'
            f'<p>初始值 <code>{_e(_bool_text(source.get("initial_value")))}</code> · '
            f'<code class="pointer" tabindex="0">'
            f'{_e(source.get("initial_pointer", ""))}</code></p>')
        writes = source.get('writes', ())
        if not writes:
            parts.append('<p class="muted">剧情中没有显式 effects 写入；初始值仍可能满足条件。</p>')
        else:
            parts.append('<ul class="write-list">')
            for write in writes:
                if write.get('renpy_source'):
                    parts.append(_source_refs_html([write], node_anchors, heading='赋值源位置'))
                reachability = REACHABILITY_LABELS.get(
                    write.get('source_reachability'),
                    write.get('source_reachability', '未知'))
                observation = OBSERVATION_LABELS.get(
                    write.get('observation_status'),
                    write.get('observation_status', '未知'))
                node_id = write.get('node_id', '')
                node_code = f'<code>{_e(node_id)}</code>'
                anchor = node_anchors.get(str(node_id))
                if anchor:
                    node_code = f'<a href="#{_e(anchor)}">{node_code}</a>'
                parts.append(
                    '<li>'
                    f'<code class="pointer" tabindex="0">{_e(write.get("pointer", ""))}</code>'
                    f'<p>{node_code} / <code>{_e(write.get("choice_id", ""))}</code> '
                    f'写为 <code>{_e(_bool_text(write.get("value")))}</code>，'
                    f'目标 <code>{_e(write.get("target_node_id", ""))}</code></p>'
                    f'<p><span class="fact-label">源节点：{_e(reachability)}</span> '
                    f'<span class="fact-label">观察状态：{_e(observation)}</span></p>'
                    '</li>')
            parts.append('</ul>')
        parts.append('</section>')
    parts.append('</details>')
    return ''.join(parts)


def _incoming_edges_html(
        diagnostic: dict[str, Any],
        node_anchors: Mapping[str, str]) -> str:
    if diagnostic['code'] not in ('UNREACHABLE_NODE', 'UNREACHABLE_ENDING'):
        return ''
    parts = [
        '<section class="incoming-edges">'
        '<p><strong>无可达路径</strong>。声明入边及条件仅为检查线索，不是执行路径。</p>',
    ]
    incoming = diagnostic.get('incoming_edges', ())
    if incoming:
        parts.append('<ul>')
        for edge in incoming:
            reachability = REACHABILITY_LABELS.get(
                edge.get('source_reachability'),
                edge.get('source_reachability', '未知'))
            parts.append(
                f'<li><code>{_e(edge["source_node_id"])} / '
                f'{_e(edge["choice_id"])}</code> · 源节点{_e(reachability)}'
                f'{_pre(edge["condition"])}')
            parts.append(_source_refs_html(
                edge.get('source_refs', ()), node_anchors,
                heading='声明入边源位置'))
            parts.append('</li>')
        parts.append('</ul>')
    else:
        parts.append('<p class="muted">无声明入边。</p>')
    parts.append('</section>')
    return ''.join(parts)


def _diagnostic_html(
        diagnostic: dict[str, Any], index: int,
        node_anchors: Mapping[str, str]) -> str:
    severity = diagnostic['severity']
    css_class = 'error' if severity == 'error' else 'warning'
    severity_label = '错误' if severity == 'error' else '警告'
    paths = list(diagnostic.get('paths', ()))[:3]
    parts = [
        f'<article id="diagnostic-{index}" class="diagnostic {css_class}">',
        f'<h3><span class="badge">{severity_label}</span> '
        f'<code>{_e(diagnostic["code"])}</code></h3>',
        f'<p class="diagnostic-message">{_e(diagnostic["message"])}</p>',
        f'<p><span class="fact-label">证据类型：'
        f'{_e(_evidence_label(diagnostic.get("evidence_kind")))}</span></p>',
    ]
    location = ' · '.join(
        f"{name}={diagnostic[name]}"
        for name in ('node_id', 'choice_id', 'assertion_id')
        if diagnostic.get(name))
    if location:
        parts.append(f'<p class="muted">{_e(location)}</p>')
    parts.append(_source_refs_html(
        diagnostic.get('source_refs', ()), node_anchors))
    parts.append(
        f'<p>受影响的不同状态：{_e(diagnostic.get("affected_state_count", 0))}；'
        f'展示代表路径：{len(paths)}（最多 3 条）。'
        '代表路径不等同于全部路径，仅用于重放证据。</p>')
    if diagnostic.get('condition') is not None:
        parts.extend([
            '<details><summary>相关条件结构</summary>',
            _pre(diagnostic['condition']),
            '</details>',
        ])
    if diagnostic.get('local_proof'):
        proof = diagnostic['local_proof']
        parts.append(
            '<details><summary>局部证明详情</summary>'
            '<p>该结论来自表达式自身的全部布尔赋值检查，不是一份状态快照。</p>'
            + _pre(proof) + '</details>')
    if diagnostic.get('related_conditions'):
        parts.append('<details><summary>本状态下未满足的选择条件</summary><ul>')
        for choice in diagnostic['related_conditions']:
            parts.append(
                f'<li><code>{_e(choice["choice_id"])}</code> '
                f'{_e(choice["text"])}{_pre(choice["condition"])}')
            parts.append(_source_refs_html(
                choice.get('source_refs', ()), node_anchors,
                heading='选择条件源位置'))
            parts.append('</li>')
        parts.append('</ul></details>')
    parts.append(_incoming_edges_html(diagnostic, node_anchors))
    for number, path in enumerate(paths, start=1):
        parts.append(_path_html(path, number, node_anchors))
    parts.append(_variable_sources_html(
        diagnostic.get('variable_sources', []), node_anchors))
    parts.append(
        '<p class="guidance"><strong>人工排查：</strong>'
        '先核对源 Pointer、路径快照和静态写入位置。静态线索不能自动确认应修改条件、断言或初始值。</p>')
    parts.append('</article>')
    return ''.join(parts)


def _diagnostic_toc(diagnostics: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    parts = [
        '<nav class="diagnostic-toc" aria-label="诊断目录">',
        '<h2>诊断目录</h2>',
        f'<p><strong>{_e(summary["error_count"])}</strong> 个错误 · '
        f'<strong>{_e(summary["warning_count"])}</strong> 个警告</p>',
    ]
    if diagnostics:
        parts.append('<ol>')
        for index, diagnostic in enumerate(diagnostics, start=1):
            severity_label = '错误' if diagnostic['severity'] == 'error' else '警告'
            parts.append(
                f'<li><a href="#diagnostic-{index}">'
                f'<span>{_e(severity_label)}</span> '
                f'<code>{_e(diagnostic["code"])}</code>'
                '</a></li>')
        parts.append('</ol>')
    else:
        parts.append('<p>未发现诊断问题。</p>')
    parts.append('</nav>')
    return ''.join(parts)


def render_html(report: dict[str, Any]) -> str:
    """Single offline HTML file; no input is interpreted as markup or script."""
    status = report['overall_status']
    status_class = status if status in STATUS_LABELS else 'invalid'
    diagnostics = _ordered_diagnostics(report)
    node_anchors = {
        node['node_id']: f'node-{index}'
        for index, node in enumerate(report.get('node_results', ()), start=1)
    }
    parts = [
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" '
        'content="default-src \'none\'; style-src \'unsafe-inline\'">',
        f"<title>BranchCheck · {_e(report['story_title'] or '未载入剧情')}</title>",
        '<style>' + _CSS + '</style></head><body><main>',
        '<header><p class="eyebrow">BRANCHCHECK · 布尔状态剧情分析</p>',
        f"<h1>{_e(report['story_title'] or '未载入剧情')}</h1>",
        f'<p class="status {status_class}">'
        f'{_e(STATUS_LABELS.get(status, status))} '
        f'<small>{_e(status)}</small></p>',
        f"<p>分析完整性：<strong>{'完整' if report['analysis_complete'] else '未完成'}</strong></p>",
    ]
    if report['stop_reason']:
        parts.append(f'<p class="stop">停止原因：{_e(report["stop_reason"])}</p>')
    parts.append('</header>')
    if report.get('import_context'):
        parts.append('<aside><strong>Ren’Py 导入边界</strong><p>' + _e(report['import_context']['boundary']) + '</p><p>'
                     + _e(f"作者视图抑制 {report['projection']['suppressed_count']} 条自动守卫警告；JSON raw_diagnostics 保留全部原始诊断。") + '</p></aside>')
    if not report['analysis_complete'] and status == 'incomplete':
        parts.append(
            '<aside class="incomplete-banner" role="alert">'
            '<strong>分析未完成</strong><span>搜索已达到上限。未访问节点和未观察到的选择保持未知；'
            '本报告不能呈现为通过，也不能据此认定它们不可达。</span></aside>')
    parts.append('<section aria-label="核心计数" class="metrics">')
    for key, label in SUMMARY_LABELS.items():
        parts.append(
            f'<div><strong>{_e(report["summary"][key])}</strong>'
            f'<span>{_e(label)}</span></div>')
    parts.append(
        '</section><p class="muted">搜索上限：'
        f'{_e(report["limits"]["max_states"])} 个唯一状态，'
        f'{_e(report["limits"]["max_transitions"])} 条有效转移。</p>')
    parts.append(_diagnostic_toc(diagnostics, report['summary']))
    parts.append('<section><h2>诊断问题</h2>')
    if not diagnostics:
        parts.append('<p>未发现诊断问题。</p>')
    for index, diagnostic in enumerate(diagnostics, start=1):
        parts.append(_diagnostic_html(diagnostic, index, node_anchors))
    parts.append(
        '</section><section><h2>节点可达性</h2>'
        '<p class="muted">“未知”表示搜索尚未完成，不能据此认定不可达。'
        '触发指已记录一次实际可行转移。</p>')
    parts.append(
        '<div class="table-wrap"><table><thead><tr>'
        '<th>节点</th><th>可达性</th><th>状态数</th>'
        '<th>声明选择</th><th>已触发选择</th></tr></thead><tbody>')
    for index, node in enumerate(report.get('node_results', ()), start=1):
        anchor = f'node-{index}'
        parts.append(
            f'<tr id="{anchor}"><td><b>{_e(node["title"])}</b><br>'
            f'<code>{_e(node["node_id"])}</code>'
            f'{" · 结局" if node["ending"] else ""}')
        refs = node.get('source_refs', ())
        if refs:
            parts.append(
                f'<br><code class="pointer" tabindex="0">'
                f'{_e(refs[0].get("pointer", ""))}</code>')
        parts.append(
            '</td>'
            f'<td>{_e(REACHABILITY_LABELS.get(node["reachability"], node["reachability"]))}</td>'
            f'<td>{_e(node["reachable_state_count"])}</td>'
            f'<td>{_e(node["declared_choice_count"])}</td>'
            f'<td>{_e(", ".join(node["triggered_choices"]) or "无")}</td></tr>')
        if node.get('choices'):
            parts.append(
                '<tr><td colspan="5"><details><summary>选择与条件</summary><ul>')
            for choice in node['choices']:
                parts.append(
                    f'<li><code>{_e(choice["choice_id"])}</code> '
                    f'{_e(choice["text"])} → <code>{_e(choice["target"])}</code>'
                    f' · {_e(REACHABILITY_LABELS.get(choice["status"], choice["status"]))}'
                    f'{_pre(choice["condition"])}')
                parts.append(_source_refs_html(
                    choice.get('source_refs', ()), node_anchors,
                    heading='选择源位置'))
                parts.append('</li>')
            parts.append('</ul></details></td></tr>')
    parts.append(
        '</tbody></table></div></section>'
        '<section><h2>局部条件矛盾检查</h2>'
        '<p class="muted">completed 表示已完成独立布尔赋值检查；'
        'skipped 表示超过 12 个不同变量，未判定。局部可满足不代表剧情中实际可触发。</p>')
    parts.append(
        '<div class="table-wrap"><table><thead><tr>'
        '<th>节点 / 选择</th><th>检查状态</th><th>变量数</th>'
        '<th>结果与原因</th></tr></thead><tbody>')
    for item in report.get('local_condition_checks', ()):
        result = ('未判定' if item['status'] == 'skipped'
                  else '可满足' if item['satisfiable'] else '条件矛盾')
        parts.append(
            f'<tr><td><code>{_e(item["node_id"])} / '
            f'{_e(item["choice_id"])}</code>')
        refs = item.get('source_refs', ())
        if refs:
            parts.append(
                f'<br><code class="pointer" tabindex="0">'
                f'{_e(refs[0].get("pointer", ""))}</code>')
        parts.append(
            f'</td><td>{_e(item["status"])}</td>'
            f'<td>{_e(item["variable_count"])}</td>'
            f'<td>{_e(result)}'
            f'{("：" + _e(item["reason"])) if item.get("reason") else ""}'
            '</td></tr>')
    parts.append('</tbody></table></div></section>')
    parts.append(
        f'<footer><p>{_e(MODEL_BOUNDARY)}</p>'
        f'<p>报告版本 {_e(report["report_version"])} · '
        '本文件可离线打开，无脚本、外部字体或远程资源。</p></footer>')
    parts.append('</main></body></html>\n')
    return ''.join(parts)


_CSS = '''
:root{color-scheme:light;font-family:system-ui,"Microsoft YaHei",sans-serif;color:#213343;background:#f3f5f7;line-height:1.65}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0}main{max-width:1100px;margin:auto;padding:36px 24px 64px}
header{padding:12px 0 20px}h1{font-size:2rem;line-height:1.3;margin:10px 0 20px;overflow-wrap:anywhere}
h2{font-size:1.4rem;margin-top:34px}h3{font-size:1.1rem}h4{font-size:1rem;margin:16px 0 8px}h5{font-size:.95rem;margin:14px 0 6px}
p{margin:8px 0}.eyebrow{font-size:.8rem;letter-spacing:0;color:#486479}small{font-weight:400;font-size:.8rem}
.muted,footer{color:#526678;font-size:.9rem}.status{display:inline-block;border-radius:7px;padding:7px 14px;font-weight:700}
.passed{color:#15603c;background:#dff2e7}.failed,.invalid{color:#912c2b;background:#ffe4e2}
.warning,.incomplete{color:#765000;background:#fff0c6}.stop{padding:12px;border-left:4px solid #ba850c;background:#fff6df}
.incomplete-banner{position:sticky;top:0;z-index:5;display:flex;gap:12px;align-items:flex-start;margin:0 0 18px;padding:13px 16px;border:2px solid #9a6400;background:#fff4cf;color:#573b00;box-shadow:0 2px 8px #0002}
.incomplete-banner strong{white-space:nowrap}.incomplete-banner span{display:block}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px}
.metrics div{padding:14px;background:white;border:1px solid #dce3e9;border-radius:8px}.metrics strong,.metrics span{display:block}.metrics strong{font-size:1.6rem}.metrics span{font-size:.85rem;color:#526678}
.diagnostic-toc{margin:26px 0;padding:14px 18px;border-left:4px solid #486479;background:#fff}.diagnostic-toc h2{margin-top:0}.diagnostic-toc ol{columns:2;column-gap:28px}.diagnostic-toc li{break-inside:avoid;margin:6px 0}
.diagnostic{scroll-margin-top:76px;background:white;border:1px solid #dce3e9;border-left:5px solid #b98318;border-radius:8px;margin:14px 0;padding:16px 20px}
.diagnostic.error{border-left-color:#bd4140}.diagnostic.warning{color:inherit;background:white}.diagnostic-message{font-size:1rem}
.badge{font-size:.8rem;padding:3px 7px;background:#fff0c6;color:#765000;border-radius:4px}.error .badge{background:#ffe4e2;color:#912c2b}
.fact-label{display:inline-block;padding:2px 7px;border:1px solid #c7d2dc;border-radius:4px;background:#f7f9fb;font-size:.88rem}
.source-refs{margin:10px 0}.source-refs h4{margin-bottom:4px}.source-refs ul{margin:0;padding-left:22px}.source-refs li{margin:5px 0}.source-refs .role{font-weight:600}.source-ids,.source-title{display:block;margin-top:2px;color:#526678;font-size:.88rem}
.pointer{user-select:all;background:#eef2f5;padding:2px 5px;border-radius:4px}.guidance,.evidence-note{padding:10px 12px;border-left:3px solid #698197;background:#f4f7f9}
details{padding:10px 0}summary{cursor:pointer;font-weight:600}details.path{border-top:1px solid #dce3e9}.steps{padding-left:24px}.steps>li{margin-bottom:18px;padding-left:4px}
.condition-explanations{margin:14px 0}.condition-tree,.condition-tree ul{list-style:none;padding-left:20px}.condition-tree{padding-left:0}.condition-line{display:inline-block;margin:3px 0}.condition-result.satisfied{color:#15603c}.condition-result.unsatisfied{color:#912c2b}.condition-result.unknown{color:#765000}
.variable-source{border-top:1px solid #dce3e9;padding:4px 0 10px}.write-list{padding-left:22px}.write-list li{margin:9px 0}.incoming-edges{margin:12px 0}
.snapshot pre{margin-bottom:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef2f5;padding:12px;border-radius:6px;font-size:.85rem}
code{font-family:Consolas,monospace;font-size:.9em;overflow-wrap:anywhere}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;background:white;font-size:.9rem}
th,td{padding:10px 12px;border:1px solid #dce3e9;text-align:left;vertical-align:top}th{background:#e9eff4;font-weight:600}tr[id]{scroll-margin-top:76px}li{overflow-wrap:anywhere}footer{margin-top:34px;padding-top:20px;border-top:1px solid #cbd6df}
a{color:#174f79;text-decoration-thickness:1px;text-underline-offset:2px}a:focus-visible,summary:focus-visible,.pointer:focus-visible{outline:3px solid #d17a00;outline-offset:3px}
@media(max-width:700px){main{padding:20px 14px 44px}h1{font-size:1.7rem}.diagnostic-toc ol{columns:1}.incomplete-banner{display:block}.incomplete-banner strong{display:block;margin-bottom:4px}}
@media print{body{background:white}main{max-width:none;padding:0}.diagnostic{break-inside:avoid}.incomplete-banner{position:static;box-shadow:none}details{display:block}}
'''
