"""Tests for the ``ifc.label()`` Rego extension exposed by :func:`_eval_policy`.

Exercises the four-rule effective-label resolution implemented by
:func:`policy_engine._make_label_extension`:

    1. explicit label at the queried canonical path,
    2. implicit label from the join (lub) of descendants' effective labels,
    3. nearest ancestor with an effective label,
    4. call-level fallback at ``"$"``.

Label keys in ``_meta[IFC_LABELS_META_PREFIX]`` are RFC 9535 JSONPath
singular-query strings (``"$['arguments']['foo']"`` canonical,
``"$.arguments.foo"`` etc. also accepted). The Rego-side
``ifc.label("...")`` argument uses the same JSONPath syntax rooted at
``input`` (``$``).
"""

from __future__ import annotations

from typing import Any

import pytest

from policy_engine import (
    IFC_LABELS_META_PREFIX,
    eval_policy,
    _make_label_extension,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _label(integrity: str, confidentiality: list[str]) -> dict[str, Any]:
    return {"integrity": integrity, "confidentiality": confidentiality}


T_EMPTY = _label("trusted", [])
T_ALICE = _label("trusted", ["alice"])
T_BOB = _label("trusted", ["bob"])
U_ALICE = _label("untrusted", ["alice"])
U_BOB = _label("untrusted", ["bob"])
U_EMPTY = _label("untrusted", [])


def _set_conf(label: dict[str, Any]) -> set[str]:
    return set(label.get("confidentiality") or [])


def _labels_equiv(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Lattice-aware equality on label dicts (set semantics on readers)."""
    return a["integrity"] == b["integrity"] and _set_conf(a) == _set_conf(b)


# ---------------------------------------------------------------------------
# Rule 1: explicit label at queried path
# ---------------------------------------------------------------------------


def test_explicit_label_at_canonical_path_resolves():
    call = {"name": "T", "arguments": {"x": "v"}}
    labels = {"$['name']": T_EMPTY, "$['arguments']['x']": U_ALICE}
    label = _make_label_extension(call, labels)
    assert _labels_equiv(label("$['arguments']['x']"), U_ALICE)
    assert _labels_equiv(label("$.arguments.x"), U_ALICE)
    assert _labels_equiv(label("$['arguments'].x"), U_ALICE)


@pytest.mark.parametrize(
    "raw_key",
    [
        "$.arguments.x",
        "$['arguments']['x']",
        "$.arguments['x']",
        "$['arguments'].x",
    ],
)
def test_explicit_label_attached_under_any_path_form(raw_key: str):
    """Label keys may use any singular JSONPath form; the resolver
    normalizes them to a single Normalized Path spelling."""
    call = {"name": "T", "arguments": {"x": "v"}}
    labels = {"$['name']": T_EMPTY, raw_key: U_ALICE}
    label = _make_label_extension(call, labels)
    assert _labels_equiv(label("$['arguments']['x']"), U_ALICE)
    assert _labels_equiv(label("$.arguments.x"), U_ALICE)


def test_mixed_dot_and_bracket_path_forms_resolve_consistently():
    call = {"name": "T", "arguments": {"x": {"y": {"z": "v"}}}}
    labels = {"$['name']": T_EMPTY, "$.arguments.x['y'].z": U_BOB}
    label = _make_label_extension(call, labels)
    # All spellings refer to the same node.
    spellings = [
        "$['arguments']['x']['y']['z']",
        "$.arguments.x.y.z",
        "$.arguments.x['y'].z",
        "$['arguments'].x.y['z']",
    ]
    for s in spellings:
        assert _labels_equiv(label(s), U_BOB), s


# ---------------------------------------------------------------------------
# Rule 2: implicit label from descendants
# ---------------------------------------------------------------------------


def test_implicit_label_from_dict_descendants():
    """An unlabelled container takes the lub of its labelled children."""
    call = {
        "name": "T",
        "arguments": {"body": {"to": "alice", "tag": "internal"}},
    }
    labels = {
        "$['name']": T_EMPTY,
        "$['arguments']['body']['to']": T_ALICE,
        "$['arguments']['body']['tag']": U_BOB,
    }
    label = _make_label_extension(call, labels)
    # body's effective label is the lub: integrity=untrusted (min), confidentiality
    # = {alice} ∩ {bob} = ∅.
    body = label("$.arguments.body")
    assert body["integrity"] == "untrusted"
    assert _set_conf(body) == set()


def test_implicit_label_from_list_elements():
    """Arrays take the lub over their elements."""
    call = {"name": "T", "arguments": {"items": ["a", "b", "c"]}}
    labels = {
        "$['name']": T_EMPTY,
        "$['arguments']['items'][0]": T_ALICE,
        "$['arguments']['items'][2]": U_BOB,
    }
    label = _make_label_extension(call, labels)
    items = label("$.arguments.items[0]")
    assert _labels_equiv(items, T_ALICE)
    # Element 1 has no explicit label and no labelled descendants;
    # its enclosing list has implicit label = lub({alice}, {bob}) at
    # integrity=untrusted → integrity=untrusted, confidentiality=∅.
    arr = label("$['arguments']['items']")
    assert arr["integrity"] == "untrusted"
    assert _set_conf(arr) == set()


def test_implicit_label_propagates_up_to_arguments():
    """``arguments`` itself becomes labelled when only descendants carry labels."""
    call = {"name": "T", "arguments": {"x": "v", "y": "w"}}
    labels = {
        "$['name']": T_EMPTY,
        "$.arguments.x": T_ALICE,
        "$['arguments']['y']": U_BOB,
    }
    label = _make_label_extension(call, labels)
    args = label("$.arguments")
    assert args["integrity"] == "untrusted"
    assert _set_conf(args) == set()


# ---------------------------------------------------------------------------
# Rule 3: nearest labelled ancestor
# ---------------------------------------------------------------------------


def test_unlabeled_descendant_inherits_nearest_ancestor():
    call = {"name": "T", "arguments": {"x": {"nested": {"deep": "v"}}}}
    labels = {"$['name']": T_EMPTY, "$['arguments']['x']": U_ALICE}
    label = _make_label_extension(call, labels)
    assert _labels_equiv(label("$['arguments']['x']['nested']['deep']"), U_ALICE)
    assert _labels_equiv(label("$.arguments.x.nested.deep"), U_ALICE)
    # Sibling-less ancestors also resolve via rule 3.
    assert _labels_equiv(label("$.arguments.x.nested"), U_ALICE)


def test_unlabeled_sibling_inherits_container_implicit_label():
    """An unlabelled sibling of a labelled subtree picks up the *implicit*
    container label (rule 3 returns the ancestor's effective label, which
    may itself be a descendants-lub)."""
    call = {
        "name": "T",
        "arguments": {"to": "alice", "body": {"text": "hi"}, "subject": "test"},
    }
    labels = {
        "$['name']": T_EMPTY,
        "$['arguments']['to']": T_ALICE,
        "$['arguments']['body']": U_BOB,
    }
    label = _make_label_extension(call, labels)
    # subject inherits the implicit ``arguments`` label:
    # lub(T_ALICE, U_BOB) = integrity=untrusted, confidentiality = {alice} ∩ {bob} = ∅.
    subject = label("$.arguments.subject")
    assert subject["integrity"] == "untrusted"
    assert _set_conf(subject) == set()


# ---------------------------------------------------------------------------
# Rule 4: call-level fallback at "$"
# ---------------------------------------------------------------------------


def test_call_level_fallback_used_when_no_ancestor_label():
    call = {"name": "T", "arguments": {"unlabeled": {"nested": "v"}}}
    labels = {"$": T_ALICE}
    label = _make_label_extension(call, labels)
    assert _labels_equiv(label("$.arguments.unlabeled.nested"), T_ALICE)
    assert _labels_equiv(label("$.arguments"), T_ALICE)
    assert _labels_equiv(label("$.name"), T_ALICE)
    assert _labels_equiv(label("$"), T_ALICE)


def test_explicit_label_wins_over_call_level_fallback():
    """When both an explicit/implicit label and a ``"$"`` fallback exist,
    the closer one wins."""
    call = {"name": "T", "arguments": {"x": "v"}}
    labels = {
        "$": T_EMPTY,
        "$['arguments']['x']": U_ALICE,
        "$['name']": T_BOB,
    }
    label = _make_label_extension(call, labels)
    assert _labels_equiv(label("$['arguments']['x']"), U_ALICE)
    assert _labels_equiv(label("$.name"), T_BOB)
    # No node-level coverage for arguments → fall through to the
    # call-level fallback (arguments has no descendants-derived label
    # because its only child has an explicit one matching it; the
    # implicit label for arguments is the lub of its children, i.e.
    # U_ALICE, which still wins over the fallback).
    assert _labels_equiv(label("$.arguments"), U_ALICE)


# ---------------------------------------------------------------------------
# Path normalization edge cases
# ---------------------------------------------------------------------------


def test_label_resolves_paths_with_integer_indices():
    call = {"name": "T", "arguments": {"items": [{"v": "1"}, {"v": "2"}]}}
    labels = {
        "$['name']": T_EMPTY,
        "$['arguments']['items'][0]['v']": T_ALICE,
        "$.arguments.items[1].v": U_BOB,
    }
    label = _make_label_extension(call, labels)
    assert _labels_equiv(label("$.arguments.items[0].v"), T_ALICE)
    assert _labels_equiv(label("$['arguments']['items'][1]['v']"), U_BOB)


def test_orphan_explicit_label_at_nonexistent_path_is_still_resolvable():
    """Explicit labels attached to paths that don't exist in the call
    tree are still returned by ``ifc.label()`` when queried directly."""
    call = {"name": "T", "arguments": {"x": "v"}}
    labels = {
        "$['name']": T_EMPTY,
        # Coverage for ``arguments`` is needed because the orphan-ghost
        # path below is *not* part of the call tree and so doesn't
        # contribute a descendants-lub for ``arguments``.
        "$['arguments']": T_EMPTY,
        # ``arguments.ghost`` doesn't exist in the call but the label
        # is still queryable.
        "$.arguments.ghost": U_ALICE,
    }
    label = _make_label_extension(call, labels)
    assert _labels_equiv(label("$.arguments.ghost"), U_ALICE)
    assert _labels_equiv(label("$['arguments']['ghost']"), U_ALICE)


def test_explicit_label_on_existing_path_covers_arguments_implicitly():
    """When the labelled path *exists* in the call tree, the
    descendants-lub propagates up and an explicit ``arguments`` label is
    not required for total coverage."""
    call = {"name": "T", "arguments": {"ghost": "v"}}
    labels = {
        "$['name']": T_EMPTY,
        # No explicit ``arguments`` label — coverage flows up from the
        # labelled child.
        "$.arguments.ghost": U_ALICE,
    }
    label = _make_label_extension(call, labels)
    assert _labels_equiv(label("$.arguments.ghost"), U_ALICE)
    # ``arguments`` itself resolves to the implicit lub of its children,
    # which is just ``U_ALICE`` (only one labelled child).
    assert _labels_equiv(label("$.arguments"), U_ALICE)


def test_query_for_empty_path_returns_fallback():
    call = {"name": "T", "arguments": {"x": "v"}}
    labels = {"$['name']": T_EMPTY, "$": U_BOB, "$['arguments']['x']": T_ALICE}
    label = _make_label_extension(call, labels)
    assert _labels_equiv(label("$"), U_BOB)


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_inconsistent_explicit_label_raises():
    """An explicit label that doesn't dominate the lub of its descendants
    is rejected at construction time."""
    call = {"name": "T", "arguments": {"body": {"x": "v"}}}
    labels = {
        "$['name']": T_EMPTY,
        # body claims trusted but contains an untrusted child.
        "$['arguments']['body']": T_ALICE,
        "$['arguments']['body']['x']": U_ALICE,
    }
    with pytest.raises(ValueError, match="Inconsistent label"):
        _make_label_extension(call, labels)


def test_duplicate_noncanonical_keys_with_conflicting_values_raise():
    call = {"name": "T", "arguments": {"x": "v"}}
    labels = {
        "$['name']": T_EMPTY,
        "$.arguments.x": T_ALICE,
        "$['arguments']['x']": U_BOB,
    }
    with pytest.raises(ValueError, match="duplicate label entries"):
        _make_label_extension(call, labels)


def test_duplicate_noncanonical_keys_with_equal_values_are_accepted():
    """Two non-canonical keys mapping to the same canonical path with
    equal values are fine — confidentiality-list ordering must not
    spuriously trigger the duplicate-detection error."""
    call = {"name": "T", "arguments": {"x": "v"}}
    labels = {
        "$['name']": T_EMPTY,
        "$.arguments.x": {
            "integrity": "untrusted",
            "confidentiality": ["alice", "bob"],
        },
        "$['arguments']['x']": {
            "integrity": "untrusted",
            "confidentiality": ["bob", "alice"],
        },
    }
    label = _make_label_extension(call, labels)
    resolved = label("$.arguments.x")
    assert resolved["integrity"] == "untrusted"
    assert _set_conf(resolved) == {"alice", "bob"}


def test_missing_total_coverage_raises():
    """Without an explicit/implicit label on ``name`` *and* no ``"$"``
    fallback, construction fails."""
    call = {"name": "T", "arguments": {"x": "v"}}
    labels = {"$['arguments']['x']": U_ALICE}  # name uncovered, no fallback
    with pytest.raises(ValueError, match="no effective label"):
        _make_label_extension(call, labels)


def test_label_extension_rejects_non_string_path():
    call = {"name": "T", "arguments": {"x": "v"}}
    label = _make_label_extension(call, {"$['name']": T_EMPTY, "$": T_EMPTY})
    with pytest.raises(ValueError, match="expects a JSONPath string"):
        label(123)


# ---------------------------------------------------------------------------
# End-to-end: Rego policies invoking label() see consistent results
# ---------------------------------------------------------------------------


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_eval_policy_label_calls_match_direct_extension():
    """Effective labels resolved by a Rego policy via ``ifc.label("…")``
    match the values returned by the in-process extension callable."""
    call = {
        "name": "SendMessage",
        "arguments": {
            "to": "alice",
            "body": {"text": "hi", "tag": "internal"},
            "subject": "test",
            "items": [{"v": "1"}, {"v": "2"}],
        },
        "_meta": {
            IFC_LABELS_META_PREFIX: {
                "$['name']": T_EMPTY,
                # Mix of canonical and non-canonical JSONPath keys.
                "$['arguments']['to']": T_ALICE,
                "$.arguments.body": U_BOB,
                "$['arguments']['items'][0]['v']": T_ALICE,
                "$.arguments.items[1].v": U_BOB,
                "$": T_EMPTY,  # call-level fallback
            }
        },
    }
    queries = [
        ("name", "$.name"),
        ("to_explicit", "$.arguments.to"),
        ("body_explicit", "$.arguments.body"),
        ("body_text_via_ancestor", "$.arguments.body.text"),
        ("subject_via_implicit_arguments", "$.arguments.subject"),
        ("items_elem0_explicit", "$.arguments.items[0].v"),
        ("items_elem1_explicit", "$.arguments.items[1].v"),
        ("items_array_implicit", "$.arguments.items"),
        ("call_level_fallback", "$"),
    ]
    policy_lines = ["package policy"]
    for var, path in queries:
        # Rego string escapes are minimal here because none of the paths
        # contain quotes.
        policy_lines.append(f'{var} := ifc.label("{path}")')
    policy = "\n".join(policy_lines)

    result = await eval_policy(call, policy)

    # Cross-check each policy value against the direct extension.
    direct = _make_label_extension(call, call["_meta"][IFC_LABELS_META_PREFIX])
    for var, path in queries:
        expected = direct(path)
        got = result[var]
        assert _labels_equiv(got, expected), (var, path, got, expected)


@pytest.mark.anyio
async def test_eval_policy_label_jsonpath_query_forms():
    """Policies may query with any equivalent JSONPath spelling; the
    resolver normalizes them and returns the same effective label."""
    call = {
        "name": "T",
        "arguments": {"x": {"y": "v"}},
        "_meta": {
            IFC_LABELS_META_PREFIX: {
                "$['name']": T_EMPTY,
                "$['arguments']['x']": U_ALICE,
            }
        },
    }
    policy = """
package policy

bracketed := ifc.label("$['arguments']['x']['y']")
dotted := ifc.label("$.arguments.x.y")
"""
    result = await eval_policy(call, policy)
    assert _labels_equiv(result["bracketed"], U_ALICE)
    assert _labels_equiv(result["dotted"], U_ALICE)
    assert _labels_equiv(result["bracketed"], result["dotted"])


@pytest.mark.anyio
async def test_eval_policy_label_uses_fallback_for_uncovered_paths():
    """``ifc.label("$")`` (and any path with no ancestor coverage) returns
    the call-level fallback when one is configured."""
    call = {
        "name": "T",
        "arguments": {"unlabeled": {"nested": "v"}},
        "_meta": {IFC_LABELS_META_PREFIX: {"$": T_ALICE}},
    }
    policy = """
package policy

deep := ifc.label("$.arguments.unlabeled.nested")
root := ifc.label("$")
name_label := ifc.label("$.name")
"""
    result = await eval_policy(call, policy)
    assert _labels_equiv(result["deep"], T_ALICE)
    assert _labels_equiv(result["root"], T_ALICE)
    assert _labels_equiv(result["name_label"], T_ALICE)


# ---------------------------------------------------------------------------
# Dynamic JSONPath queries via sprintf: a policy can render the path
# string from values computed at evaluation time and hand the result
# to ``ifc.label(...)``.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_eval_policy_label_dynamic_segment_via_sprintf():
    """A path segment can be a variable computed at evaluation time:
    ``sprintf`` renders the JSONPath and ``label`` resolves it."""
    call = {
        "name": "T",
        "arguments": {"value": "secret", "other": "public"},
        "_meta": {
            IFC_LABELS_META_PREFIX: {
                "$['name']": T_EMPTY,
                "$['arguments']['value']": U_ALICE,
                "$['arguments']['other']": T_BOB,
            }
        },
    }
    policy = """
package policy

foo := "value"
bar := "other"

dynamic_value := ifc.label(sprintf("$.arguments.%s", [foo]))
dynamic_other := ifc.label(sprintf("$.arguments.%s", [bar]))
"""
    result = await eval_policy(call, policy)
    assert _labels_equiv(result["dynamic_value"], U_ALICE)
    assert _labels_equiv(result["dynamic_other"], T_BOB)


@pytest.mark.anyio
async def test_eval_policy_label_dynamic_segment_iterated():
    """A more realistic dynamic use: iterate over a set of argument names
    and resolve each one's effective label via ``ifc.label(sprintf(...))``."""
    call = {
        "name": "T",
        "arguments": {"a": "1", "b": "2"},
        "_meta": {
            IFC_LABELS_META_PREFIX: {
                "$['name']": T_EMPTY,
                "$['arguments']['a']": T_ALICE,
                "$['arguments']['b']": U_BOB,
            }
        },
    }
    policy = """
package policy

arg_names := {"a", "b"}

labels_by_arg[k] := ifc.label(sprintf("$.arguments.%s", [k])) if {
    some k in arg_names
}
"""
    result = await eval_policy(call, policy)
    by_arg = result["labels_by_arg"]
    assert _labels_equiv(by_arg["a"], T_ALICE)
    assert _labels_equiv(by_arg["b"], U_BOB)
