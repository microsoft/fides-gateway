from __future__ import annotations

import json
import re
from typing import Any

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import ToolResult
from mcp.types import CallToolRequestParams, TextContent

from lattice import IFCLabels
from policy_engine import IFC_LABELS_META_PREFIX

_TRUSTED_METADATA_FIELDS = {
    "additions",
    "ahead_by",
    "author_association",
    "behind_by",
    "changed_files",
    "closed",
    "comments",
    "commits",
    "created",
    "databaseid",
    "deletions",
    "forks",
    "id",
    "incomplete_results",
    "locked",
    "maintainer_can_modify",
    "mergeable",
    "merged",
    "number",
    "open_issues",
    "private",
    "public",
    "score",
    "size",
    "state",
    "status",
    "total",
    "total_count",
    "updated",
    "watchers",
}

_TRUSTED_METADATA_CONTAINERS = {
    "permissions",
    "reactions",
}

_TRUSTED_METADATA_SUFFIXES = (
    "_at",
    "_count",
    "_id",
    "_url",
)

_TRUSTED_METADATA_NAMES = {
    "etag",
    "git_url",
    "html_url",
    "node_id",
    "sha",
    "ssh_url",
    "svn_url",
    "url",
}


def _labels(integrity: str, readers: tuple[str, ...] = ()) -> IFCLabels:
    # Repository visibility and membership are not available in every tool
    # result, so confidentiality remains fail-closed until an audience-aware
    # GitHub policy widens it.
    return IFCLabels(integrity=integrity, confidentiality=list(readers))


def _path(parent: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]"
    escaped = key.replace("\\", "\\\\").replace("'", "\\'")
    return f"{parent}['{escaped}']"


def _is_trusted_metadata(
    field: str | None, value: Any, trusted_container: bool
) -> bool:
    if trusted_container:
        return True
    if field is None:
        return False
    normalized = field.lower()
    return (
        normalized in _TRUSTED_METADATA_FIELDS
        or normalized in _TRUSTED_METADATA_NAMES
        or normalized.endswith(_TRUSTED_METADATA_SUFFIXES)
        or normalized.startswith(("has_", "is_"))
        or normalized.endswith("_sha")
        or isinstance(value, bool)
    )


def _label_payload(
    value: Any,
    path: str,
    labels: dict[str, IFCLabels],
    field: str | None = None,
    trusted_container: bool = False,
    readers: tuple[str, ...] = (),
) -> None:
    current_trusted = _is_trusted_metadata(field, value, trusted_container)
    if isinstance(value, dict):
        if not value:
            labels[path] = _labels(
                "trusted" if current_trusted else "untrusted", readers
            )
            return
        child_trusted = current_trusted or (
            field is not None and field.lower() in _TRUSTED_METADATA_CONTAINERS
        )
        for key, child in value.items():
            _label_payload(
                child,
                _path(path, key),
                labels,
                key,
                child_trusted,
                readers,
            )
        return
    if isinstance(value, list):
        if not value:
            labels[path] = _labels(
                "trusted" if current_trusted else "untrusted", readers
            )
            return
        for index, child in enumerate(value):
            _label_payload(
                child,
                _path(path, index),
                labels,
                field,
                current_trusted,
                readers,
            )
        return
    labels[path] = _labels("trusted" if current_trusted else "untrusted", readers)


def _github_payload(result: ToolResult) -> dict[str, Any] | None:
    if result.structured_content is not None:
        return result.structured_content
    if not result.content or not isinstance(result.content[0], TextContent):
        return None
    try:
        parsed = json.loads(result.content[0].text)
    except json.JSONDecodeError:
        return None
    payload = parsed if isinstance(parsed, dict) else {"result": parsed}
    result.structured_content = payload
    return payload


class GitHubLabellingMiddleware(Middleware):
    """Label GitHub-controlled metadata as trusted and all other data as untrusted."""

    def __init__(self, repository_readers: dict[str, list[str]] | None = None) -> None:
        self.repository_readers: dict[str, tuple[str, ...]] = {}
        if repository_readers is not None and not isinstance(repository_readers, dict):
            raise ValueError("repositoryReaders must map repositories to reader lists")
        for repository, readers in (repository_readers or {}).items():
            if not isinstance(repository, str) or not re.fullmatch(
                r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository
            ):
                raise ValueError("repositoryReaders keys must be owner/repo names")
            if (
                not isinstance(readers, list)
                or not all(
                    isinstance(reader, str) and reader.strip() for reader in readers
                )
                or ("public" in readers and len(readers) != 1)
            ):
                raise ValueError(
                    "repositoryReaders values must be reader lists; public must stand alone"
                )
            key = repository.casefold()
            if key in self.repository_readers:
                raise ValueError(f"duplicate repositoryReaders entry: {repository}")
            self.repository_readers[key] = tuple(sorted(set(readers)))

    def _readers(self, call: CallToolRequestParams) -> tuple[str, ...]:
        arguments = call.arguments or {}
        if call.name != "issue_read" or arguments.get("method") not in {
            "get",
            "get_comments",
        }:
            return ()
        owner, repository = arguments.get("owner"), arguments.get("repo")
        if not isinstance(owner, str) or not isinstance(repository, str):
            return ()
        return self.repository_readers.get(f"{owner}/{repository}".casefold(), ())

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        result = await call_next(context)
        readers = self._readers(context.message)
        labels: dict[str, IFCLabels] = {"$": _labels("untrusted", readers)}
        payload = _github_payload(result)
        if payload is not None:
            _label_payload(payload, "$['structuredContent']", labels, readers=readers)

        meta = dict(result.meta) if result.meta else {}
        meta[IFC_LABELS_META_PREFIX] = {
            path: label.model_dump() for path, label in labels.items()
        }
        result.meta = meta
        return result
