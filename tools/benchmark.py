"""Reproducible small benchmark; standard library only, no timing promises."""
import json
import platform
import sys
from pathlib import Path
from time import perf_counter

from branchcheck.analyzer import analyze
from branchcheck.loader import validate_story


def main():
    variables = {f'flag_{i}': False for i in range(10)}
    choices = []
    for name in variables:
        for before in (False, True):
            choices.append({
                'id': f'{name}_{int(before)}', 'text': f'切换 {name}',
                'target': 'hub', 'condition': {'var': name, 'eq': before},
                'effects': {name: not before},
            })
    choices.append({'id': 'finish', 'text': '结束调查', 'target': 'end'})
    model = validate_story({
        'schema_version': 1, 'title': '十变量可控状态空间', 'start': 'hub',
        'variables': variables,
        'nodes': [{'id': 'hub', 'title': '调查中心', 'choices': choices},
                  {'id': 'end', 'title': '完成', 'ending': True}],
    })
    begin = perf_counter()
    report = analyze(model)
    elapsed = perf_counter() - begin
    result = {
        'python': sys.version.split()[0], 'platform': platform.platform(),
        'processor': platform.processor(), 'node_count': 2, 'variable_count': 10,
        'overall_status': report['overall_status'], **report['summary'],
        'elapsed_seconds': round(elapsed, 6),
        'scope': '仅 analyze 调用；不含加载、报告渲染及进程启动；单次实测。',
    }
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output + '\n', encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
