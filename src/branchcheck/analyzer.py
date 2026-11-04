"""Breadth-first exploration of the *state* graph, with bounded evidence.

Only fully scanned states count as expanded. Negative global conclusions are
made exclusively after exhaustive exploration; a budget is tested when a real
transition would exceed it, not merely when its counter equals the budget.
"""
from collections import defaultdict, deque
from typing import Any

from .conditions import (
    condition_to_json, contradiction_check, evaluate, explain_condition,
    referenced_variables,
)
from .models import Choice, Condition, Limits, State, Story, TRUE
from .source_context import build_source_context


def _base_report(title: str, limits: Limits) -> dict[str, Any]:
    return {
        'report_version': 2, 'story_title': title,
        'analysis_complete': True, 'stop_reason': None,
        'overall_status': 'passed',
        'limits': {'max_states': limits.max_states,
                   'max_transitions': limits.max_transitions},
        'summary': dict.fromkeys((
            'node_count', 'variable_count', 'declared_ending_count',
            'reached_ending_count', 'discovered_states', 'expanded_states',
            'transition_count', 'error_count', 'warning_count'), 0),
        'diagnostics': [], 'node_results': [], 'local_condition_checks': [],
        'variable_sources': [],
    }


def invalid_report(message: str, limits: Limits = Limits()) -> dict[str, Any]:
    report = _base_report('', limits)
    report.update(analysis_complete=False, stop_reason='输入无效，未执行状态分析。',
                  overall_status='invalid')
    report['summary']['error_count'] = 1
    report['diagnostics'] = [{
        'code': 'INVALID_INPUT', 'severity': 'error', 'message': message,
        'node_id': None, 'choice_id': None, 'assertion_id': None,
        'condition': None, 'affected_state_count': 0, 'paths': [],
        'representative_path_count': 0, 'source_refs': [],
        'evidence_kind': 'input_error', 'variable_sources': [],
    }]
    return report


def analyze(story: Story, limits: Limits = Limits()) -> dict[str, Any]:
    """Analyze a validated Story without file access or rendering side effects."""
    nodes = {node.id: node for node in story.nodes}
    source_context = build_source_context(story)
    variable_names = tuple(sorted(story.variables))
    variable_index = {name: i for i, name in enumerate(variable_names)}
    initial_mask = sum(1 << variable_index[name]
                       for name, value in story.variables.items() if value)
    initial: State = (story.start, initial_mask)
    report = _base_report(story.title, limits)
    # Insertion order here is BFS discovery order, including its input-order ties.
    parents: dict[State, tuple[State, Choice] | None] = {initial: None}
    distance = {initial: 0}
    queue = deque([initial])
    reverse: dict[State, list[tuple[State, Choice]]] = defaultdict(list)
    transitions: list[tuple[State, Choice, State]] = []
    reached: dict[str, list[State]] = defaultdict(list)
    reached[initial[0]].append(initial)
    triggered: set[tuple[str, str]] = set()
    dead_states: set[State] = set()
    expanded: set[State] = set()
    findings: dict[tuple, dict[str, Any]] = {}
    contradiction_keys: set[tuple[str, str]] = set()

    def snapshot(state: State) -> dict[str, Any]:
        return {'node_id': state[0], 'node_title': nodes[state[0]].title,
                'variables': {name: bool(state[1] & (1 << i))
                              for name, i in variable_index.items()},
                'source_refs': [source_context.node_ref(
                    state[0], role='状态所在节点')]}

    def evidence(state: State) -> dict[str, Any]:
        chain: list[tuple[State, Choice, State]] = []
        cursor = state
        while parents[cursor] is not None:
            source, choice = parents[cursor]  # type: ignore[misc]
            chain.append((source, choice, cursor))
            cursor = source
        steps = []
        for source, choice, target in reversed(chain):
            changes = {}
            for name, i in variable_index.items():
                before = bool(source[1] & (1 << i))
                after = bool(target[1] & (1 << i))
                if before != after:
                    changes[name] = {'before': before, 'after': after}
            steps.append({
                'source_node_id': source[0], 'source_title': nodes[source[0]].title,
                'choice_id': choice.id, 'choice_text': choice.text,
                'target_node_id': target[0], 'target_title': nodes[target[0]].title,
                'changes': changes,
                'source_refs': [source_context.choice_ref(
                    source[0], choice.id, role='路径中实际触发的选择')],
            })
        return {'initial_state': snapshot(initial), 'steps': steps,
                'final_state': snapshot(state)}

    def explanation_spec(role: str, condition: Condition, **labels: Any) -> dict[str, Any]:
        return {'role': role, 'condition_ast': condition, **labels}

    def choice_condition_ref(node_id: str, choice: Choice,
                             role: str) -> dict[str, Any]:
        field = None if choice.condition is TRUE else 'condition'
        return source_context.choice_ref(
            node_id, choice.id, field=field, role=role)

    def add(code: str, severity: str, message: str, node_id: str | None = None,
            choice_id: str | None = None, assertion_id: str | None = None,
            state: State | None = None, condition: Any = None,
            source_refs: list[dict[str, Any]] | None = None,
            evidence_kind: str = 'global_conclusion',
            explanation_specs: list[dict[str, Any]] | None = None,
            variable_names_used: tuple[str, ...] | set[str] = (),
            **extra: Any) -> None:
        key = (code, node_id, choice_id, assertion_id)
        if key not in findings:
            findings[key] = {
                'code': code, 'severity': severity, 'message': message,
                'node_id': node_id, 'choice_id': choice_id,
                'assertion_id': assertion_id, 'condition': condition,
                'source_refs': list(source_refs or ()),
                'evidence_kind': evidence_kind,
                '_states': set(), '_representatives': [],
                '_explanation_specs': list(explanation_specs or ()),
                '_variable_names': set(variable_names_used),
                **extra,
            }
        entry = findings[key]
        entry['_variable_names'].update(variable_names_used)
        if state is not None and state not in entry['_states']:
            entry['_states'].add(state)
            # Normally calls arrive in BFS order. Sorting also protects future
            # analysis passes that may supply already discovered states.
            candidates = entry['_representatives'] + [state]
            candidates.sort(key=lambda s: distance[s])
            entry['_representatives'] = candidates[:3]

    def assertions(state: State) -> None:
        for assertion in nodes[state[0]].assertions:
            if not evaluate(assertion.condition, state[1], variable_index):
                add('ASSERTION_FAILED', 'error', assertion.message,
                    node_id=state[0], assertion_id=assertion.id, state=state,
                    condition=condition_to_json(assertion.condition),
                    source_refs=[source_context.assertion_ref(
                        state[0], assertion.id, field='condition',
                        role='失败断言')],
                    evidence_kind='specific_state',
                    explanation_specs=[explanation_spec(
                        '失败断言', assertion.condition,
                        assertion_id=assertion.id,
                        text=assertion.message,
                        source_refs=[source_context.assertion_ref(
                            state[0], assertion.id, field='condition',
                            role='失败断言')])],
                    variable_names_used=referenced_variables(
                        assertion.condition))

    # These are local proofs, independent of whether BFS can finish.
    for node in story.nodes:
        for choice in node.choices:
            result = contradiction_check(choice.condition)
            proof = {
                'proof_kind': ('all_assignments' if result['status'] == 'completed'
                               else 'skipped'),
                'assignment_count': (1 << result['variable_count']
                                     if result['status'] == 'completed' else None),
                **result,
            }
            report['local_condition_checks'].append({
                'node_id': node.id, 'choice_id': choice.id,
                'condition': condition_to_json(choice.condition),
                'source_refs': [choice_condition_ref(
                    node.id, choice, '局部检查的选择条件')],
                **proof,
            })
            if result['status'] == 'completed' and result['satisfiable'] is False:
                contradiction_keys.add((node.id, choice.id))
                add('CONTRADICTORY_CONDITION', 'warning',
                    '该选择的条件在所有布尔赋值下均为假。',
                    node_id=node.id, choice_id=choice.id,
                    condition=condition_to_json(choice.condition),
                    source_refs=[choice_condition_ref(
                        node.id, choice, '矛盾选择条件')],
                    evidence_kind='local_proof', local_proof=proof,
                    variable_names_used=referenced_variables(
                        choice.condition))

    assertions(initial)
    stop_reason = None
    while queue and stop_reason is None:
        state = queue.popleft()
        node = nodes[state[0]]
        if node.ending:
            expanded.add(state)
            continue
        enabled = False
        for choice in node.choices:
            if not evaluate(choice.condition, state[1], variable_index):
                continue
            enabled = True
            target_mask = state[1]
            for name, value in choice.effects.items():
                bit = 1 << variable_index[name]
                target_mask = target_mask | bit if value else target_mask & ~bit
            target = (choice.target, target_mask)
            is_new = target not in parents
            if len(transitions) >= limits.max_transitions:
                stop_reason = ('下一条有效状态转移将超过 max_transitions='
                               f'{limits.max_transitions}。')
                break
            if is_new and len(parents) >= limits.max_states:
                stop_reason = ('发现下一个新状态将超过 max_states='
                               f'{limits.max_states}。')
                break
            # Preserve even parallel edges or edges back to visited states:
            # they are real transitions needed for reverse reachability.
            transitions.append((state, choice, target))
            reverse[target].append((state, choice))
            triggered.add((node.id, choice.id))
            if is_new:
                parents[target] = (state, choice)
                distance[target] = distance[state] + 1
                reached[target[0]].append(target)
                queue.append(target)
                assertions(target)
        if stop_reason is None:
            expanded.add(state)
            if not enabled:
                dead_states.add(state)
                blocked_specs = [explanation_spec(
                    '不可执行选择', choice.condition,
                    choice_id=choice.id, text=choice.text,
                    source_refs=[choice_condition_ref(
                        node.id, choice, '不可执行选择条件')])
                    for choice in node.choices]
                blocked_variables = {
                    name for choice in node.choices
                    for name in referenced_variables(choice.condition)
                }
                add('DEAD_END', 'error',
                    '可达的非结局状态没有可执行选择。', node_id=node.id,
                    state=state,
                    related_conditions=[{
                        'choice_id': c.id, 'text': c.text,
                        'condition': condition_to_json(c.condition),
                        'source_refs': [choice_condition_ref(
                            node.id, c, '不可执行选择条件')],
                    } for c in node.choices],
                    source_refs=[source_context.node_ref(
                        node.id, role='可达死路节点')] + [
                            choice_condition_ref(
                                node.id, c, '不可执行选择条件')
                            for c in node.choices],
                    evidence_kind='specific_state',
                    explanation_specs=blocked_specs,
                    variable_names_used=blocked_variables)

    complete = stop_reason is None
    ending_states = [state for state in parents if nodes[state[0]].ending]
    if complete:
        for node in story.nodes:
            if node.id not in reached:
                incoming = [{
                    'source_node_id': source.id, 'choice_id': choice.id,
                    'condition': condition_to_json(choice.condition),
                    'source_reachability': (
                        'reachable' if source.id in reached else 'unreachable'),
                    'source_refs': [source_context.choice_ref(
                        source.id, choice.id, field='target',
                        role='指向不可达节点的声明入边')],
                } for source in story.nodes for choice in source.choices
                    if choice.target == node.id]
                code = 'UNREACHABLE_ENDING' if node.ending else 'UNREACHABLE_NODE'
                add(code, 'warning', '该节点从初始状态无可达路径。',
                    node_id=node.id, incoming_edges=incoming,
                    source_refs=[source_context.node_ref(
                        node.id, role='不可达目标节点')],
                    evidence_kind='global_conclusion')
            else:
                for choice in node.choices:
                    key = (node.id, choice.id)
                    if key not in triggered and key not in contradiction_keys:
                        for state in reached[node.id]:
                            add('NEVER_ENABLED_CHOICE', 'warning',
                                '源节点可达，但该选择在所有可达源状态中均不可执行。',
                                node_id=node.id, choice_id=choice.id, state=state,
                                condition=condition_to_json(choice.condition),
                                source_refs=[choice_condition_ref(
                                    node.id, choice,
                                    '从未可用的选择条件')],
                                evidence_kind=(
                                    'global_conclusion_with_state_samples'),
                                explanation_specs=[explanation_spec(
                                    '代表源状态中的选择条件',
                                    choice.condition, choice_id=choice.id,
                                    text=choice.text,
                                    source_refs=[choice_condition_ref(
                                        node.id, choice,
                                        '从未可用的选择条件')])],
                                variable_names_used=referenced_variables(
                                    choice.condition))
        if not ending_states:
            add('NO_REACHABLE_ENDING', 'error',
                '从初始状态无法到达任何声明的结局（也可能未声明结局）。',
                state=initial, evidence_kind='global_conclusion')
        can_finish = set(ending_states)
        reverse_queue = deque(ending_states)
        while reverse_queue:
            target = reverse_queue.popleft()
            for source, _choice in reverse.get(target, ()):
                if source not in can_finish:
                    can_finish.add(source)
                    reverse_queue.append(source)
        for state in parents:
            if state not in can_finish and state not in dead_states:
                if not nodes[state[0]].ending:
                    add('NO_ENDING_PATH', 'warning',
                        '从这个可达状态已无法再到达任何结局。',
                        node_id=state[0], state=state,
                        source_refs=[source_context.node_ref(
                            state[0], role='无法通往结局的可达状态节点')],
                        evidence_kind='specific_state')
    else:
        add('ANALYSIS_LIMIT_REACHED', 'warning',
            '分析未完成：' + stop_reason,
            evidence_kind='analysis_status')

    def annotated_variable_source(name: str) -> dict[str, Any]:
        source = source_context.variable_source(name)
        source['evidence_kind'] = 'static_variable_index'
        for write in source['writes']:
            source_was_reached = write['node_id'] in reached
            write['evidence_kind'] = 'static_write_location'
            write['source_reachability'] = (
                'reachable' if source_was_reached
                else 'unreachable' if complete else 'unknown')
            write['observation_status'] = (
                'triggered'
                if (write['node_id'], write['choice_id']) in triggered
                else 'not_triggered' if complete else 'unknown')
            write['target_title'] = nodes[write['target_node_id']].title
        return source

    variable_source_index = {
        name: annotated_variable_source(name) for name in story.variables
    }
    report['variable_sources'] = list(variable_source_index.values())

    for node in story.nodes:
        reachability = ('reachable' if node.id in reached
                        else 'unreachable' if complete else 'unknown')
        choices = []
        for choice in node.choices:
            was_triggered = (node.id, choice.id) in triggered
            status = ('enabled' if was_triggered else 'unknown' if not complete
                      else 'never_enabled' if node.id in reached
                      else 'source_unreachable')
            choices.append({
                'choice_id': choice.id, 'text': choice.text,
                'target': choice.target,
                'condition': condition_to_json(choice.condition),
                'triggered': was_triggered, 'status': status,
                'source_refs': [choice_condition_ref(
                    node.id, choice, '选择及其条件')],
            })
        report['node_results'].append({
            'node_id': node.id, 'title': node.title, 'ending': node.ending,
            'declared_choice_count': len(node.choices),
            'triggered_choices': [c.id for c in node.choices
                                  if (node.id, c.id) in triggered],
            'reachable_state_count': len(reached.get(node.id, ())),
            'reachability': reachability, 'choices': choices,
            'source_refs': [source_context.node_ref(
                node.id, role='声明节点')],
        })

    # Explicit order makes comparison independent of hash randomization.
    codes = ('INVALID_INPUT', 'ASSERTION_FAILED', 'DEAD_END',
             'NO_REACHABLE_ENDING', 'UNREACHABLE_NODE', 'UNREACHABLE_ENDING',
             'CONTRADICTORY_CONDITION', 'NEVER_ENABLED_CHOICE',
             'NO_ENDING_PATH', 'ANALYSIS_LIMIT_REACHED')
    node_order = {node.id: i for i, node in enumerate(story.nodes)}
    diagnostics = list(findings.values())
    diagnostics.sort(key=lambda d: (
        d['severity'] != 'error', codes.index(d['code']),
        node_order.get(d['node_id'], -1), d['choice_id'] or '',
        d['assertion_id'] or ''))
    for finding in diagnostics:
        finding['affected_state_count'] = len(finding.pop('_states'))
        representatives = finding.pop('_representatives')
        specs = finding.pop('_explanation_specs')
        names = finding.pop('_variable_names')
        paths = []
        for state in representatives:
            path = evidence(state)
            path['condition_explanations'] = []
            for spec in specs:
                condition_ast = spec['condition_ast']
                explanation = {
                    key: value for key, value in spec.items()
                    if key != 'condition_ast'
                }
                explanation['condition'] = condition_to_json(condition_ast)
                explanation['explanation'] = explain_condition(
                    condition_ast, state[1], variable_index)
                path['condition_explanations'].append(explanation)
            paths.append(path)
        finding['paths'] = paths
        finding['representative_path_count'] = len(finding['paths'])
        finding['variable_sources'] = [
            annotated_variable_source(name) for name in sorted(names)
        ]
    error_count = sum(d['severity'] == 'error' for d in diagnostics)
    warning_count = sum(d['severity'] == 'warning' for d in diagnostics)
    report.update(
        analysis_complete=complete, stop_reason=stop_reason,
        overall_status=('incomplete' if not complete else 'failed' if error_count
                        else 'warning' if warning_count else 'passed'),
        diagnostics=diagnostics,
    )
    report['summary'].update(
        node_count=len(nodes), variable_count=len(variable_names),
        declared_ending_count=sum(node.ending for node in story.nodes),
        reached_ending_count=len({s[0] for s in ending_states}),
        discovered_states=len(parents), expanded_states=len(expanded),
        transition_count=len(transitions), error_count=error_count,
        warning_count=warning_count,
    )
    return report
