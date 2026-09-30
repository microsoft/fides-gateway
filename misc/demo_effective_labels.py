"""Visual sanity-check for ``_build_effective_labels`` + ``ifc.label()`` resolution.

Each example renders the entire call tree with every node annotated by its
resolved IFC label. Labels are colour-coded by their *source*, matching
the three categories in the resolution semantics:

- [bold bright_cyan]explicit[/]: the input directly attached a label at this
  node's canonical path.
- [bold magenta]computed[/]: the node has no explicit label, but
  ``_build_effective_labels`` produced one as the join (lub) of its
  descendants' effective labels.
- [bold yellow]implicit[/]: neither the node nor any descendant carries an
  explicit label. The label is resolved at *query time* by walking up
  through the ``effective`` map (rule 3) or falling back to the
  call-level label at ``"$"`` (rule 4).

After rendering, the script verifies that the ``ifc.label()`` function — the
Rego extension exposed to policies — returns the same value for every
node, computed by an independent reference resolver. Any mismatch is
reported in red so a regression in the resolver is immediately visible.

Run with::

    uv run python misc/demo_effective_labels.py
"""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.tree import Tree

from policy_engine import (
    _build_effective_labels,
    _jsonpath_normalize,
    _make_label_extension,
)

# ---------------------------------------------------------------------------
# Colour scheme per label-source category
# ---------------------------------------------------------------------------

EXPLICIT_COLOUR = "bright_cyan"
COMPUTED_COLOUR = "magenta"
IMPLICIT_COLOUR = "yellow"


# ---------------------------------------------------------------------------
# Pretty-printing helpers
# ---------------------------------------------------------------------------


def _fmt_label(label: dict[str, Any] | None) -> str:
    """Render an IFC label as compact ``⟨I=H|L, C={…}⟩`` notation."""
    if label is None:
        return "—"
    integrity = "T" if label.get("integrity") == "trusted" else "U"
    conf = sorted(label.get("confidentiality") or [])
    conf_str = "∅" if not conf else "{" + ",".join(conf) + "}"
    return f"⟨{integrity}, {conf_str}⟩"


def _fmt_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return ""
    return json.dumps(value, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Independent reference resolver — exists solely so the consistency check
# tests the engine's ``ifc.label()`` against a separate implementation of the
# same spec, rather than testing the engine against itself.
# ---------------------------------------------------------------------------


def _reference_resolve(
    segments: list[str | int],
    labels: dict[str, dict[str, Any]],
    effective: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    """Resolve the effective label for *segments* and return ``(label, category)``.

    Category is one of ``"explicit"``, ``"computed"``, ``"implicit"``.
    Returns ``(None, "implicit")`` only when no fallback exists and the
    path is unresolvable — in practice forbidden by the construction-time
    coverage check, but guarded against here defensively.
    """
    canonical = _jsonpath_normalize(segments)
    if canonical in labels:
        return labels[canonical], "explicit"
    if canonical in effective:
        return effective[canonical], "computed"
    # Rule 3: nearest ancestor with an effective label.
    for end in range(len(segments) - 1, 0, -1):
        ancestor = _jsonpath_normalize(segments[:end])
        if ancestor in effective:
            return effective[ancestor], "implicit"
    # Rule 4: call-level fallback at ``"$"``.
    if "$" in labels:
        return labels["$"], "implicit"
    return None, "implicit"


_COLOUR_FOR_CATEGORY = {
    "explicit": EXPLICIT_COLOUR,
    "computed": COMPUTED_COLOUR,
    "implicit": IMPLICIT_COLOUR,
}


# ---------------------------------------------------------------------------
# Tree rendering
# ---------------------------------------------------------------------------


def _add_node(
    parent: Tree,
    display_key: str,
    value: Any,
    segments: list[str | int],
    labels: dict[str, dict[str, Any]],
    effective: dict[str, dict[str, Any]],
    label_fn,
    mismatches: list[tuple[str, Any, Any]],
) -> None:
    canonical = _jsonpath_normalize(segments)
    expected, category = _reference_resolve(segments, labels, effective)
    actual = label_fn(canonical)
    if expected != actual:
        mismatches.append((canonical, expected, actual))

    colour = _COLOUR_FOR_CATEGORY[category]
    label_str = _fmt_label(expected)
    inline_value = _fmt_value(value)
    if isinstance(value, dict):
        head = f"[bold]{display_key}[/bold]"
    elif isinstance(value, list):
        head = f"[bold]{display_key}[/bold]  [dim]\\[{len(value)} items][/dim]"
    else:
        head = f"[bold]{display_key}[/bold]: [green]{inline_value}[/green]"
    head = f"{head}   [{colour}]{label_str}[/{colour}]" f"  [dim]({category})[/dim]"
    node = parent.add(head)

    if isinstance(value, dict):
        for k, v in value.items():
            _add_node(
                node, k, v, segments + [k], labels, effective, label_fn, mismatches
            )
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _add_node(
                node,
                f"[{i}]",
                v,
                segments + [i],
                labels,
                effective,
                label_fn,
                mismatches,
            )


def _render_example(
    console: Console,
    title: str,
    description: str,
    call: dict[str, Any],
    labels: dict[str, dict[str, Any]],
) -> bool:
    effective = _build_effective_labels(call, labels)
    label_fn = _make_label_extension(call, labels)

    # Header: include the call-level fallback ('$') annotation when present,
    # since it is not attached to any rendered child node.
    fallback = labels.get("$")
    header = "[bold]CALL[/bold]"
    if fallback is not None:
        # The fallback is itself an "explicit" labelling (of the call as a
        # whole), so it gets the explicit colour.
        header = (
            f"{header}   [dim]call-level fallback ('$') :[/dim] "
            f"[{EXPLICIT_COLOUR}]{_fmt_label(fallback)}[/{EXPLICIT_COLOUR}]"
            f"  [dim](explicit)[/dim]"
        )
    root = Tree(header)

    mismatches: list[tuple[str, Any, Any]] = []
    _add_node(
        root, "name", call["name"], ["name"], labels, effective, label_fn, mismatches
    )
    _add_node(
        root,
        "arguments",
        call.get("arguments") or {},
        ["arguments"],
        labels,
        effective,
        label_fn,
        mismatches,
    )

    # Also exercise the call-level path itself: ifc.label("$").
    if fallback is not None:
        actual = label_fn("$")
        if actual != fallback:
            mismatches.append(("$", fallback, actual))

    console.print(Rule(title=f"[bold]{title}[/bold]", style="bold yellow"))
    console.print(f"[italic dim]{description}[/italic dim]")
    console.print(Panel(root, border_style="white"))

    if mismatches:
        for canonical, expected, actual in mismatches:
            console.print(
                f"  [bold red]✗ mismatch at[/bold red] [yellow]{canonical!r}[/yellow]:"
                f" reference={_fmt_label(expected)}, ifc.label()={_fmt_label(actual)}"
            )
        return False
    console.print(
        "  [bold green]✓[/bold green] [green]ifc.label() agrees with the displayed"
        " labels for every queryable path[/green]"
    )
    return True


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------


EXAMPLES: list[tuple[str, str, dict[str, Any], dict[str, dict[str, Any]]]] = [
    (
        "1. Single labelled leaf lifts into its parent",
        "arguments['to'] carries an explicit label. arguments has no explicit"
        " label, so its effective label is computed as the lub of its only"
        " labelled child — exactly arguments['to'] itself. name has no"
        " explicit label and no descendants, so it resolves implicitly via"
        " the call-level fallback at '$'.",
        {"name": "Send", "arguments": {"to": "alice"}},
        {
            "$": {"integrity": "trusted", "confidentiality": []},
            "$['arguments']['to']": {
                "integrity": "trusted",
                "confidentiality": ["alice"],
            },
        },
    ),
    (
        "2. Lub propagates through several nesting levels",
        "Only the deepest leaf is labelled. Every dict on the path back up"
        " is computed as the lub of a single labelled subtree (so each"
        " gets the same label). Siblings without descendant labels"
        " resolve implicitly to the call-level fallback.",
        {
            "name": "Send",
            "arguments": {"body": {"recipient": {"id": "alice"}}},
        },
        {
            "$": {"integrity": "untrusted", "confidentiality": []},
            "$['arguments']['body']['recipient']['id']": {
                "integrity": "trusted",
                "confidentiality": ["alice"],
            },
        },
    ),
    (
        "3. Sibling labels join: integrity to min, confidentiality to"
        " set-intersection",
        "Two arguments carry incompatible labels. Their parent (arguments)"
        " is computed: integrity = min(high, low) = low; confidentiality"
        " = {alice,bob,carol} ∩ {alice,bob} = {alice,bob}. The nested 'y'"
        " dict is also computed (lub over its single labelled child).",
        {"name": "Op", "arguments": {"x": 1, "y": {"z": 2}}},
        {
            "$": {"integrity": "trusted", "confidentiality": []},
            "$['arguments']['x']": {
                "integrity": "trusted",
                "confidentiality": ["alice", "bob", "carol"],
            },
            "$['arguments']['y']['z']": {
                "integrity": "untrusted",
                "confidentiality": ["alice", "bob"],
            },
        },
    ),
    (
        "4. Explicit label on a container overrides the lub of its children",
        "arguments['body'] is explicitly labelled. Its child 'text' carries"
        " a stricter label (higher in the lattice); the well-formedness"
        " check verifies join(body, text) == body. body's display colour is"
        " 'explicit' even though it also dominates its descendants —"
        " explicit wins over computed when both are present.",
        {
            "name": "Send",
            "arguments": {
                "to": "alice",
                "body": {"text": "hi", "priority": "untrusted"},
            },
        },
        {
            "$": {"integrity": "trusted", "confidentiality": []},
            "$['arguments']['to']": {
                "integrity": "trusted",
                "confidentiality": ["alice", "bob"],
            },
            "$['arguments']['body']": {
                "integrity": "untrusted",
                "confidentiality": ["alice"],
            },
            "$['arguments']['body']['text']": {
                "integrity": "trusted",
                "confidentiality": ["alice", "bob"],
            },
        },
    ),
    (
        "5. Array elements carry their own labels and join into the array",
        "items[0] and items[1] are individually labelled; items[2] is not."
        " The array's effective label is the lub of its labelled elements:"
        " integrity = 'low' (items[1] is low); confidentiality = {alice} ∩"
        " {alice,bob} = {alice}. items[2] resolves implicitly via the"
        " ancestor walk to the array's computed label.",
        {
            "name": "Add",
            "arguments": {
                "items": [{"v": 1}, {"v": 2}, {"v": 3}],
                "note": "n",
            },
        },
        {
            "$": {"integrity": "trusted", "confidentiality": []},
            "$['arguments']['items'][0]": {
                "integrity": "trusted",
                "confidentiality": ["alice"],
            },
            "$['arguments']['items'][1]": {
                "integrity": "untrusted",
                "confidentiality": ["alice", "bob"],
            },
        },
    ),
    (
        "6. Independent labels on name and the call-level fallback",
        "name has its own explicit label, incomparable with the call-level"
        " fallback (the fallback is NOT required to upper-bound name or"
        " arguments). arguments has no explicit label, no labelled"
        " descendants — it resolves implicitly via the '$' fallback.",
        {"name": "Send", "arguments": {"to": "alice", "body": {"text": "hi"}}},
        {
            "$": {"integrity": "trusted", "confidentiality": []},
            "$['name']": {"integrity": "untrusted", "confidentiality": ["bob"]},
        },
    ),
    (
        "7. Pure fallback labelling — only '$' is configured",
        "No node-level labels at all. Every node resolves implicitly via"
        " rule 4 to the call-level fallback. The effective map remains"
        " empty (no subtree-derived labels), but every queryable path"
        " still receives a label.",
        {"name": "Send", "arguments": {"to": "alice", "body": {"text": "hi"}}},
        {"$": {"integrity": "untrusted", "confidentiality": ["alice"]}},
    ),
]


def main() -> None:
    console = Console()
    console.print()
    console.print(
        Panel(
            "[bold]_build_effective_labels & ifc.label() — visual sanity check[/bold]\n\n"
            "Every node in each example shows its resolved IFC label,"
            " colour-coded by source:\n"
            f"  • [{EXPLICIT_COLOUR}]explicit[/{EXPLICIT_COLOUR}] — directly"
            " attached at this path in the input\n"
            f"  • [{COMPUTED_COLOUR}]computed[/{COMPUTED_COLOUR}] — lub of"
            " descendants, recorded in the effective map\n"
            f"  • [{IMPLICIT_COLOUR}]implicit[/{IMPLICIT_COLOUR}] — not"
            " stored anywhere; resolved at query time by walking up the"
            " effective map (rule 3) or falling back to the call-level"
            " label at '$' (rule 4)\n\n"
            "After rendering, each example asserts that ifc.label() — the Rego"
            " extension — returns the same value an independent reference"
            " resolver does for every node.",
            border_style="yellow",
        )
    )
    console.print()
    all_passed = True
    for title, description, call, labels in EXAMPLES:
        passed = _render_example(console, title, description, call, labels)
        all_passed = all_passed and passed
        console.print()

    if all_passed:
        console.print(
            "[bold green]All examples passed the ifc.label() consistency check."
            "[/bold green]"
        )
    else:
        console.print(
            "[bold red]One or more examples reported mismatches between"
            " ifc.label() and the reference resolver — see above.[/bold red]"
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
