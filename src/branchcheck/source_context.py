"""Static source locations and variable-write clues for validated stories."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from .models import Story


def escape_pointer_token(token: str | int) -> str:
    """Escape one RFC 6901 JSON Pointer reference token."""
    return str(token).replace('~', '~0').replace('/', '~1')


def json_pointer(*tokens: str | int) -> str:
    """Build an RFC 6901 JSON Pointer; no tokens denotes the document root."""
    if not tokens:
        return ''
    return '/' + '/'.join(escape_pointer_token(token) for token in tokens)


def _field_pointer(base: str, field: str | None, allowed: frozenset[str]) -> str:
    if field is None:
        return base
    if field not in allowed:
        expected = ', '.join(sorted(allowed))
        raise ValueError(f'unsupported source field {field!r}; expected one of: {expected}')
    return f'{base}/{escape_pointer_token(field)}'


@dataclass(frozen=True)
class SourceRef:
    """One structural location, before a diagnostic assigns its role."""

    pointer: str
    node_id: str
    node_title: str
    choice_id: str | None = None
    choice_text: str | None = None
    target_node_id: str | None = None
    assertion_id: str | None = None
    assertion_message: str | None = None

    def as_dict(self, *, pointer: str | None = None,
                role: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            'pointer': self.pointer if pointer is None else pointer,
            'node_id': self.node_id,
            'node_title': self.node_title,
        }
        if self.choice_id is not None:
            result.update(
                choice_id=self.choice_id,
                choice_text=self.choice_text,
                target_node_id=self.target_node_id,
            )
        if self.assertion_id is not None:
            result.update(
                assertion_id=self.assertion_id,
                assertion_message=self.assertion_message,
            )
        if role is not None:
            result['role'] = role
        return result


@dataclass(frozen=True)
class VariableWriteRef:
    """A declared effect assignment, without reachability implications."""

    pointer: str
    value: bool
    node_id: str
    node_title: str
    choice_id: str
    choice_text: str
    target_node_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            'pointer': self.pointer,
            'value': self.value,
            'node_id': self.node_id,
            'node_title': self.node_title,
            'choice_id': self.choice_id,
            'choice_text': self.choice_text,
            'target_node_id': self.target_node_id,
        }


@dataclass(frozen=True)
class VariableSource:
    """Initial declaration plus every static effect that writes one variable."""

    name: str
    initial_value: bool
    initial_pointer: str
    writes: tuple[VariableWriteRef, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            'variable': self.name,
            'initial_value': self.initial_value,
            'initial_pointer': self.initial_pointer,
            'writes': [write.as_dict() for write in self.writes],
        }


@dataclass(frozen=True)
class SourceContext:
    """Lookup API for report-ready source references and static write clues."""

    _nodes: Mapping[str, SourceRef]
    _choices: Mapping[tuple[str, str], SourceRef]
    _assertions: Mapping[tuple[str, str], SourceRef]
    _variables: Mapping[str, VariableSource]

    def node_ref(self, node_id: str, *, role: str | None = None) -> dict[str, Any]:
        return self._nodes[node_id].as_dict(role=role)

    def choice_ref(self, node_id: str, choice_id: str, *,
                   field: str | None = None,
                   role: str | None = None) -> dict[str, Any]:
        ref = self._choices[(node_id, choice_id)]
        pointer = _field_pointer(
            ref.pointer, field, frozenset({'condition', 'target', 'effects'}))
        return ref.as_dict(pointer=pointer, role=role)

    def assertion_ref(self, node_id: str, assertion_id: str, *,
                      field: str | None = None,
                      role: str | None = None) -> dict[str, Any]:
        ref = self._assertions[(node_id, assertion_id)]
        pointer = _field_pointer(ref.pointer, field, frozenset({'condition'}))
        return ref.as_dict(pointer=pointer, role=role)

    def variable_source(self, name: str) -> dict[str, Any]:
        return self._variables[name].as_dict()

    def all_variable_sources(self) -> list[dict[str, Any]]:
        """Return sources in the variable declaration order retained by Story."""
        return [source.as_dict() for source in self._variables.values()]


def build_source_context(story: Story) -> SourceContext:
    """Index validated story structure without inferring execution facts."""
    nodes: dict[str, SourceRef] = {}
    choices: dict[tuple[str, str], SourceRef] = {}
    assertions: dict[tuple[str, str], SourceRef] = {}
    writes: dict[str, list[VariableWriteRef]] = {
        name: [] for name in story.variables
    }

    for node_index, node in enumerate(story.nodes):
        node_pointer = json_pointer('nodes', node_index)
        nodes[node.id] = SourceRef(node_pointer, node.id, node.title)

        for assertion_index, assertion in enumerate(node.assertions):
            assertion_pointer = json_pointer(
                'nodes', node_index, 'assertions', assertion_index)
            assertions[(node.id, assertion.id)] = SourceRef(
                pointer=assertion_pointer,
                node_id=node.id,
                node_title=node.title,
                assertion_id=assertion.id,
                assertion_message=assertion.message,
            )

        for choice_index, choice in enumerate(node.choices):
            choice_pointer = json_pointer(
                'nodes', node_index, 'choices', choice_index)
            choices[(node.id, choice.id)] = SourceRef(
                pointer=choice_pointer,
                node_id=node.id,
                node_title=node.title,
                choice_id=choice.id,
                choice_text=choice.text,
                target_node_id=choice.target,
            )
            for variable, value in choice.effects.items():
                writes[variable].append(VariableWriteRef(
                    pointer=json_pointer(
                        'nodes', node_index, 'choices', choice_index,
                        'effects', variable),
                    value=value,
                    node_id=node.id,
                    node_title=node.title,
                    choice_id=choice.id,
                    choice_text=choice.text,
                    target_node_id=choice.target,
                ))

    variables = {
        name: VariableSource(
            name=name,
            initial_value=initial_value,
            initial_pointer=json_pointer('variables', name),
            writes=tuple(writes[name]),
        )
        for name, initial_value in story.variables.items()
    }
    return SourceContext(
        MappingProxyType(nodes),
        MappingProxyType(choices),
        MappingProxyType(assertions),
        MappingProxyType(variables),
    )
