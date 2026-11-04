"""Read-only, bounded Ren'Py subset parser and continuation-based CFG compiler.

No input is executed. The generated JSON passes the ordinary strict loader;
source metadata and author-view projection remain outside the search core.
"""
from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
import keyword
from pathlib import Path
import re

from .loader import InputError, validate_story

ID = r'[A-Za-z_][A-Za-z0-9_]*'
BOUNDARY = ('单文件受限子集；新游戏 default 初始状态；不模拟引擎外部逻辑、'
            '存档与显示系统。叙述按无布尔状态变化抽象。最短路径为编译图转移数，非最少玩家操作。')


class ImportError(InputError):
    def __init__(self, file, line, reason, subtype='unsupported_syntax'):
        self.source = dict(file=Path(file).name, start_line=line, end_line=line)
        self.subtype = subtype
        super().__init__(f'{Path(file).name}:{line}: {reason}')


@dataclass
class Statement:
    uid: str
    kind: str
    line: int
    end: int
    text: str
    label: str
    value: object = None
    branches: list = field(default_factory=list)


@dataclass
class ImportedStory:
    model: dict
    sources: dict

    @property
    def story(self):
        return validate_story(self.model)


class Parser:
    def __init__(self, text, file):
        self.file = Path(file).name
        self.lines = []
        self.count = 0
        self.variables = {}
        self.defaults = {}
        self.labels = []
        if len(text.encode('utf-8')) > 1_048_576:
            self.fail(1, '文件超过 1 MiB 资源上限')
        raw = text.removeprefix('\ufeff').splitlines()
        if len(raw) > 10000:
            self.fail(1, '超过 10000 行资源上限')
        for number, line in enumerate(raw, 1):
            if len(line) > 4096 or '\t' in line:
                self.fail(number, '禁止 Tab；单行最多 4096 字符')
            quote = None
            escape = False
            end = len(line)
            for i, char in enumerate(line):
                if escape:
                    escape = False
                elif char == '\\' and quote:
                    escape = True
                elif quote:
                    if char == quote:
                        quote = None
                elif char in ('"', "'"):
                    quote = char
                elif char == '#':
                    end = i
                    break
            clean = line[:end].rstrip()
            if not clean.strip():
                continue
            if quote:
                self.fail(number, '字符串未闭合，不支持跨行字符串')
            indent = len(clean) - len(clean.lstrip(' '))
            if indent % 4:
                self.fail(number, '缩进必须是四个空格的整数倍')
            self.lines.append((indent, clean.strip(), number))
        for indent, code, number in self.lines:
            if indent == 0 and code.startswith('default '):
                match = re.fullmatch(rf'default ({ID}) = (True|False)', code)
                if not match:
                    self.fail(number, 'default 只支持已命名布尔字面量')
                name, value = match.groups()
                if keyword.iskeyword(name):
                    self.fail(number, '变量名不能是保留关键字: ' + name)
                if name in self.variables:
                    self.fail(number, '重复 default: ' + name)
                self.variables[name] = value == 'True'
                self.defaults[name] = number
        self.pos = 0

    def fail(self, line, message):
        raise ImportError(self.file, line, message)

    def stmt(self, kind, line, text, label, value=None):
        self.count += 1
        if self.count > 5000:
            self.fail(line, '语句数超过 5000 上限')
        return Statement(f'r{self.count:05d}', kind, line, line, text[:240], label, value)

    def expression(self, text, line):
        try:
            tree = ast.parse(text.strip(), mode='eval')
        except (SyntaxError, RecursionError, ValueError):
            self.fail(line, '非法或过深的条件表达式')
        if len(text) > 2048 or sum(1 for _ in ast.walk(tree)) > 256:
            self.fail(line, '表达式超过 2048 字符或 256 AST 节点上限')

        def convert(node, depth=1):
            if depth > 24:
                self.fail(line, '表达式深度超过 24')
            if isinstance(node, ast.Constant) and type(node.value) is bool:
                return node.value
            if isinstance(node, ast.Name):
                if node.id not in self.variables:
                    self.fail(line, '未知变量: ' + node.id)
                return {'var': node.id, 'eq': True}
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                return {'not': convert(node.operand, depth + 1)}
            if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
                return {'all' if isinstance(node.op, ast.And) else 'any':
                        [convert(n, depth + 1) for n in node.values]}
            if (isinstance(node, ast.Compare) and len(node.ops) == 1
                    and isinstance(node.ops[0], (ast.Eq, ast.NotEq))
                    and isinstance(node.left, ast.Name)
                    and isinstance(node.comparators[0], ast.Constant)
                    and type(node.comparators[0].value) is bool):
                leaf = convert(node.left, depth + 1)
                leaf['eq'] = node.comparators[0].value ^ isinstance(node.ops[0], ast.NotEq)
                return leaf
            self.fail(line, '条件包含不支持的表达式；仅允许布尔变量、and/or/not 与布尔字面量比较')
        return convert(tree.body)

    def string(self, text, line):
        if not text or text[0] not in ('"', "'") or text.startswith(('"""', "'''")):
            self.fail(line, '只支持普通单行无前缀字符串')
        quote = text[0]
        result = ''
        i = 1
        escapes = {'n': '\n', 'r': '\r', 't': '\t', '\\': '\\', '"': '"', "'": "'"}
        while i < len(text):
            char = text[i]
            if char == quote:
                if '[' in result or '{' in result:
                    self.fail(line, '不支持字符串插值 [ 或文本标签 {')
                return result, text[i+1:].strip()
            if char == '\\':
                i += 1
                if i >= len(text) or text[i] not in escapes:
                    self.fail(line, '不支持该字符串转义（仅 n/r/t/引号/反斜线）')
                char = escapes[text[i]]
            result += char
            i += 1
        self.fail(line, '字符串未闭合')

    def block(self, indent, label, depth=1):
        if depth > 16:
            self.fail(self.lines[self.pos][2], '块嵌套超过 16')
        body = []
        while self.pos < len(self.lines):
            level, code, line = self.lines[self.pos]
            if level < indent:
                break
            if level != indent:
                self.fail(line, '非法缩进跳级')
            self.pos += 1
            if code.startswith(('elif ', 'else:')):
                self.fail(line, '孤立 elif/else')
            if code.startswith('if ') and code.endswith(':'):
                s = self.stmt('if', line, code, label)
                header = self.stmt('branch', line, code, label)
                cond = self.expression(code[3:-1], line)
                s.branches.append((header, cond, self.child(indent, label, depth)))
                seen_else = False
                while self.pos < len(self.lines):
                    lev, c, ln = self.lines[self.pos]
                    if lev != indent or not (c.startswith('elif ') or c == 'else:'):
                        break
                    if seen_else or not c.endswith(':'):
                        self.fail(ln, '非法 elif/else 顺序')
                    self.pos += 1
                    seen_else = c == 'else:'
                    h = self.stmt('branch', ln, c, label)
                    condition = None if seen_else else self.expression(c[5:-1], ln)
                    s.branches.append((h, condition, self.child(indent, label, depth)))
                s.end = self.lines[self.pos-1][2]
            elif code == 'menu:':
                s = self.stmt('menu', line, code, label)
                while self.pos < len(self.lines) and self.lines[self.pos][0] > indent:
                    lev, c, ln = self.lines[self.pos]
                    if lev != indent + 4:
                        self.fail(ln, '菜单选项缩进错误')
                    self.pos += 1
                    caption, rest = self.string(c, ln)
                    if rest == ':':
                        condition = True
                    elif rest.startswith('if ') and rest.endswith(':'):
                        condition = self.expression(rest[3:-1], ln)
                    else:
                        self.fail(ln, '菜单必须是字符串选项，可附 if 条件，末尾冒号')
                    h = self.stmt('menu_choice', ln, c, label, caption)
                    s.branches.append((h, condition, self.child(indent+4, label, depth)))
                if not s.branches:
                    self.fail(line, '菜单不能为空')
                s.end = self.lines[self.pos-1][2]
            elif re.fullmatch(rf'\$ ({ID}) = (True|False)', code):
                name, value = re.fullmatch(rf'\$ ({ID}) = (True|False)', code).groups()
                if name not in self.variables:
                    self.fail(line, '未声明赋值变量: ' + name)
                s = self.stmt('assign', line, code, label, (name, value == 'True'))
            elif re.fullmatch(rf'jump ({ID})', code):
                s = self.stmt('jump', line, code, label, code[5:])
            elif code in ('return', 'pass'):
                s = self.stmt(code, line, code, label)
            elif code.startswith(('"', "'")):
                caption, rest = self.string(code, line)
                if rest:
                    self.fail(line, '叙述不支持拼接、前缀或附加语句')
                s = self.stmt('narration', line, code, label, caption)
            else:
                self.fail(line, '子集不支持的语句: ' + code[:120])
            body.append(s)
        return body

    def child(self, indent, label, depth):
        if self.pos >= len(self.lines) or self.lines[self.pos][0] != indent+4:
            self.fail(self.lines[self.pos-1][2], '空块或非法缩进（每级四空格）')
        return self.block(indent+4, label, depth+1)

    def parse(self):
        seen = set()
        while self.pos < len(self.lines):
            indent, code, line = self.lines[self.pos]
            self.pos += 1
            if indent:
                self.fail(line, '顶层只允许 default 与 label')
            if code.startswith('default '):
                continue
            match = re.fullmatch(rf'label ({ID}):', code)
            if not match:
                self.fail(line, '顶层只支持无参数 ASCII 全局 label 与布尔 default')
            name = match[1]
            if keyword.iskeyword(name) or name == 'expression':
                self.fail(line, 'label 名不能是保留关键字: ' + name)
            if name in seen:
                self.fail(line, '重复 label: ' + name)
            seen.add(name)
            s = self.stmt('label', line, code, name)
            body = self.child(0, name, 0)
            s.end = self.lines[self.pos-1][2]
            self.labels.append((s, body))
        if 'start' not in seen:
            self.fail(1, '缺少 label start')
        if self.labels[-1][1][-1].kind not in ('jump', 'return'):
            self.fail(self.labels[-1][1][-1].line, '最后 label 最后一条顶层语句必须是静态 jump 或无参 return')
        return self.labels


def loads_renpy(text: str, filename='story.rpy') -> ImportedStory:
    parser = Parser(text, filename)
    labels = parser.parse()
    entries = {s.label: s.uid for s, _ in labels}
    nodes = {}
    refs = {}
    guard_size = 0

    def ref(s, synthetic=False, **extra):
        return dict(file=parser.file, start_line=s.line, end_line=s.end,
                    label=s.label, statement_type=s.kind, snippet=s.text,
                    synthetic=synthetic, **extra)

    def compile_block(body, continuation):
        for s in reversed(body):
            n = dict(id=s.uid, title=f'{s.label}:{s.line} {s.text}', choices=[])
            nodes[s.uid] = n
            refs[s.uid] = ref(s)

            def edge(target, condition=True, effects=None, source=s,
                     synthetic=True, original=None, guard_role='automatic'):
                nonlocal guard_size
                pending = [condition]
                while pending:
                    item = pending.pop()
                    guard_size += 1
                    if guard_size > 100000:
                        parser.fail(source.line, '编译守卫累计超过 100000 项资源上限')
                    if isinstance(item, dict):
                        pending.extend(item.values())
                    elif isinstance(item, list):
                        pending.extend(item)
                cid = f'c{len(n["choices"]):04d}'
                n['choices'].append(dict(id=cid,
                    text=('自动执行：' if synthetic else '玩家选择：') + str(source.value if source.kind == 'menu_choice' else source.text),
                    target=target, condition=condition, effects=effects or {}))
                refs[(s.uid, cid)] = ref(source, synthetic, original_condition=original,
                                          effective_guard=condition, guard_role=guard_role)
            if s.kind == 'return':
                n['ending'] = True
            elif s.kind == 'jump':
                if s.value not in entries:
                    parser.fail(s.line, 'jump 目标不存在: ' + s.value)
                edge(entries[s.value])
            elif s.kind in ('if', 'menu'):
                prior = []
                for h, cond, block in s.branches:
                    dest = compile_block(block, continuation)
                    if s.kind == 'menu':
                        guard = cond
                    else:
                        parts = [{'not': p} for p in prior] + ([] if cond is None else [cond])
                        guard = parts[0] if len(parts) == 1 else {'all': parts} if parts else True
                    edge(dest, guard, source=h, synthetic=s.kind != 'menu',
                         original=cond, guard_role='ordered_branch' if s.kind == 'if' else 'menu_option')
                    if cond is not None:
                        prior.append(cond)
                if s.kind == 'menu' or s.branches[-1][1] is not None:
                    guard = {'not': {'any': prior}}
                    edge(continuation, guard, guard_role='menu_fallback' if s.kind == 'menu' else 'if_fallback')
            else:
                edge(continuation, effects=dict([s.value]) if s.kind == 'assign' else {})
            continuation = s.uid
        return continuation

    continuation = None
    for label, body in reversed(labels):
        target = compile_block(body, continuation)
        nodes[label.uid] = dict(id=label.uid, title=f'label {label.label}', choices=[
            dict(id='enter', text='自动执行：进入 label ' + label.label, target=target)])
        refs[label.uid] = ref(label)
        refs[(label.uid, 'enter')] = ref(label, True, guard_role='label_entry')
        continuation = label.uid
    model = dict(schema_version=1, title=parser.file, start=entries['start'],
                 variables=parser.variables, nodes=[nodes[k] for k in sorted(nodes)])
    try:
        validate_story(model)
    except InputError as exc:
        raise ImportError(parser.file, 1, '编译模型超出格式限制: ' + str(exc), 'model_limit') from None
    mappings = []
    for i, node in enumerate(model['nodes']):
        mappings.append(dict(refs[node['id']], node_id=node['id'], choice_id=None, pointer=f'/nodes/{i}'))
        for j, c in enumerate(node['choices']):
            mappings.append(dict(refs[(node['id'], c['id'])], node_id=node['id'], choice_id=c['id'], pointer=f'/nodes/{i}/choices/{j}'))
    for name, line in parser.defaults.items():
        mappings.append(dict(file=parser.file, start_line=line, end_line=line, label=None,
            statement_type='default', snippet=f'default {name} = {parser.variables[name]}',
            synthetic=False, node_id=None, choice_id=None, pointer=f'/variables/{name}'))
    return ImportedStory(model, dict(mapping_version=1, file=parser.file,
        source_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
        line_count=len(text.splitlines()), mappings=mappings))


def load_renpy(path):
    path = Path(path)
    if path.stat().st_size > 1_048_576:
        raise ImportError(path.name, 1, '文件超过 1 MiB 资源上限', 'resource_limit')
    try:
        return loads_renpy(path.read_bytes().decode('utf-8'), path.name)
    except UnicodeError:
        raise ImportError(path.name, 1, '文件不是有效 UTF-8', 'encoding') from None


def project_report(report, imported):
    """Attach fresh provenance, retain raw findings and narrowly suppress noise."""
    result = deepcopy(report)
    mapping = imported.sources['mappings']
    index = {r['pointer']: r for r in mapping}
    def visit(value):
        if isinstance(value, list):
            for v in value:
                visit(v)
        elif isinstance(value, dict):
            pointer = value.get('pointer', value.get('initial_pointer'))
            if isinstance(pointer, str):
                p = pointer
                while p and p not in index:
                    p = p.rsplit('/', 1)[0]
                if p in index:
                    value['renpy_source'] = deepcopy(index[p])
            for k, v in list(value.items()):
                if k != 'renpy_source':
                    visit(v)
    visit(result)
    result['raw_diagnostics'] = deepcopy(result['diagnostics'])
    suppressed = []
    visible = []
    by_node = {r['node_id']: r for r in mapping if r['choice_id'] is None and r['node_id']}
    by_choice = {(r['node_id'], r['choice_id']): r for r in mapping if r['choice_id']}
    for d in result['diagnostics']:
        src = by_choice.get((d['node_id'], d['choice_id'])) if d['choice_id'] else by_node.get(d['node_id'])
        hide = False
        if d['severity'] == 'warning' and src:
            if d['code'] in ('UNREACHABLE_NODE', 'UNREACHABLE_ENDING'):
                # Every compiled node currently corresponds to an actual source
                # statement, so keep its reachability rather than hiding it.
                hide = False
            elif d['code'] in ('NEVER_ENABLED_CHOICE', 'CONTRADICTORY_CONDITION'):
                hide = src.get('guard_role') != 'menu_option'
                if src.get('guard_role') == 'ordered_branch':
                    # The proof concerns the *effective* ordered guard, not the
                    # original expression. Keep a source-level execution fact.
                    hide = False
                    d['message'] = '该分支的有效守卫无法执行；包含未选中前序分支的约束，不是原表达式的独立矛盾证明。'
                    d['condition_scope'] = 'effective_guard'
        if hide:
            suppressed.append(dict(code=d['code'], node_id=d['node_id'], choice_id=d['choice_id'],
                                   reason='编译内部连接或自动守卫；原始诊断保留于 raw_diagnostics'))
        else:
            visible.append(d)
    result['diagnostics'] = visible
    result['projection'] = dict(suppressed_count=len(suppressed), suppressed=suppressed)
    result['import_complete'] = True
    result['import_context'] = dict(boundary=BOUNDARY, **imported.sources)
    result['analysis_started'] = True
    result['summary']['warning_count'] = sum(d['severity'] == 'warning' for d in visible)
    if result['overall_status'] in ('passed', 'warning'):
        result['overall_status'] = 'warning' if result['summary']['warning_count'] else 'passed'
    return result
