"""Command-line entry point; analysis and rendering stay independently usable."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import json
import os
import tempfile

from .analyzer import analyze, invalid_report
from .loader import InputError, load_story
from .models import Limits
from .reports import STATUS_LABELS, render_html, render_json, render_text


def _positive_integer(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError('必须为正整数') from None
    if value <= 0:
        raise argparse.ArgumentTypeError('必须为正整数')
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='branchcheck', description='检查布尔状态分支剧情，生成可重放路径证据。')
    subparsers = parser.add_subparsers(dest='command', required=True)
    check = subparsers.add_parser('check', help='分析一个 JSON 剧情文件')
    check.add_argument('story', type=Path, help='UTF-8 JSON 剧情文件')
    check.add_argument('--format', choices=('text', 'json', 'html'), default='text', help='报告格式（默认 text）')
    check.add_argument('--output', type=Path, help='报告文件；省略则写入 stdout')
    check.add_argument('--max-states', type=_positive_integer, default=50000, help='唯一发现状态上限（默认 50000）')
    check.add_argument('--max-transitions', type=_positive_integer, default=200000, help='有效状态转移上限（默认 200000）')
    renpy = subparsers.add_parser('check-renpy', help='只读检查单文件 Ren’Py 受限子集')
    renpy.add_argument('story', type=Path)
    renpy.add_argument('--format', choices=('text', 'json', 'html'), default='text')
    renpy.add_argument('--output', type=Path)
    renpy.add_argument('--max-states', type=_positive_integer, default=50000)
    renpy.add_argument('--max-transitions', type=_positive_integer, default=200000)
    export = subparsers.add_parser('import-renpy', help='导出严格剧情 JSON 与来源 sidecar')
    export.add_argument('story', type=Path)
    export.add_argument('--output', type=Path, required=True)
    return parser


def _export_renpy(args):
    from .renpy import load_renpy
    sidecar = args.output.with_name(args.output.stem + '.sources.json')
    temporary = []
    replaced = []
    originals = {}
    try:
        if args.story.resolve() in (args.output.resolve(), sidecar.resolve()) or args.output.resolve() == sidecar.resolve():
            raise ValueError('输出模型和 sidecar 必须互异，且不能覆盖输入脚本')
        imported = load_renpy(args.story)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        for path, data in ((args.output, imported.model), (sidecar, imported.sources)):
            originals[path] = path.read_bytes() if path.exists() else None
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                             prefix='.branchcheck-', delete=False) as stream:
                temporary.append((Path(stream.name), path))
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
        for temp, path in temporary:
            os.replace(temp, path)
            replaced.append(path)
    except (InputError, OSError, ValueError) as exc:
        for path in reversed(replaced):
            # Restore the prior pair on ordinary replace/write failure. A process
            # crash cannot make a two-file update transactional across the OS.
            if originals[path] is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(originals[path])
        print(f'导入失败：{exc}；本次未更新导出产物，未运行状态分析。', file=sys.stderr)
        return 2
    finally:
        for temp, _path in temporary:
            temp.unlink(missing_ok=True)
    print(f'转换完成：{args.output}；来源：{sidecar}（尚未分析剧情）', file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    # Windows pipes can otherwise fall back to a legacy encoding. Reports,
    # including redirected JSON and arbitrary story titles, are always UTF-8.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    args = build_parser().parse_args(argv)
    if args.command == 'import-renpy':
        return _export_renpy(args)
    limits = Limits(max_states=args.max_states, max_transitions=args.max_transitions)
    try:
        if args.command == 'check-renpy':
            from .renpy import load_renpy, project_report
            if args.output and args.output.resolve() == args.story.resolve():
                print('错误：报告不能覆盖输入脚本。', file=sys.stderr)
                return 2
            imported = load_renpy(args.story)
            story = imported.story
        else:
            story = load_story(args.story)
    except (InputError, OSError, UnicodeError, ValueError) as exc:
        report = invalid_report(f'无法读取或解析剧情：{exc}', limits)
        if args.command == 'check-renpy':
            report.update(import_complete=False, analysis_started=False)
            report['diagnostics'][0]['importer'] = dict(
                subtype=getattr(exc, 'subtype', 'input_io'), source=getattr(exc, 'source', None))
    else:
        report = analyze(story, limits)
        if args.command == 'check-renpy':
            report = project_report(report, imported)
    renderer = {'text': render_text, 'json': render_json, 'html': render_html}[args.format]
    content = renderer(report)
    try:
        if args.output is None:
            sys.stdout.write(content)
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding='utf-8', newline='\n')
    except (OSError, UnicodeError, ValueError) as exc:
        print(f'错误：无法写入报告：{exc}', file=sys.stderr)
        return 2
    if args.output is not None:
        summary = report['summary']
        print(f"{STATUS_LABELS[report['overall_status']]}：{summary['error_count']} error，{summary['warning_count']} warning；报告已写入 {args.output}", file=sys.stderr)
    return {'passed': 0, 'warning': 0, 'failed': 1, 'invalid': 2, 'incomplete': 3}[report['overall_status']]
