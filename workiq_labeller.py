from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable, Mapping

from fastmcp import Client
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import ToolResult
from fastmcp.client.transports.base import ClientTransportT

from mcp.types import CallToolRequestParams

from lattice import IFCLabels, SecurityLattice
from mcp_result import extract_structured_content
from middleware import PathRule, PathRules, match_path, resolve_path_rules
from policy_engine import IFC_LABELS_META_PREFIX, LabeledMeta

CallUpstream = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
"""Async helper passed to labelers that need to call upstream tools.

Signature: ``await call_upstream(tool_name, arguments) -> structured_payload``.
The returned dict is the upstream tool's structured payload, extracted via
:func:`mcp_result.extract_structured_content` (i.e. ``structured_content``
if present, otherwise ``content[0].text`` parsed as JSON).
"""


def _fallback_meta(labels: IFCLabels) -> LabeledMeta:
    """Wrap *labels* as a :class:`LabeledMeta` carrying it as the ``"$"``
    payload-level fallback.

    All current WorkIQ labelers produce a single ``IFCLabels`` for the
    whole result and have no sub-object granularity to express, so they
    attach it at ``"$"`` — the payload-level fallback consulted whenever
    no node-level or ancestor label is available.
    """
    return LabeledMeta(**{IFC_LABELS_META_PREFIX: {"$": labels}})


def _label_from_members(
    members_payload: dict[str, Any] | None, integrity: str
) -> LabeledMeta:
    """Build a :class:`LabeledMeta` whose confidentiality is the
    ``userId`` set of a WorkIQ ``ListChannelMembers``/``ListChatMembers``
    response.

    *members_payload* is expected to be the structured payload of such a
    response (i.e. a dict with a ``"members"`` list of dicts carrying
    ``"userId"``). Missing/non-dict members and missing ``userId`` keys
    are dropped silently. *integrity* is the integrity component of the
    resulting :class:`IFCLabels` — ``"trusted"`` when the roster is the
    payload being labelled, ``"untrusted"`` when the roster is just used
    to scope the audience of an unrelated payload (e.g. chat or channel
    messages). The label is attached at the ``"$"`` payload-level
    fallback.
    """
    members = (members_payload or {}).get("members") or []
    user_ids = [m["userId"] for m in members if isinstance(m, dict) and m.get("userId")]
    return _fallback_meta(IFCLabels(integrity=integrity, confidentiality=user_ids))


# --- Work IQ server (resource-oriented tool surface) ----------------------
#
# Work IQ uses dynamic tool discovery
# with generic tools (``fetch``, ``create_entity``, ``do_action``, ...)
# whose concrete target is a Microsoft Graph resource path in the
# arguments. Labeling therefore dispatches on the resource path rather
# than on the tool name, the same way ``policies/workiq/*.rego`` do.

# ``userId``/``email`` live on the aadUserConversationMember subtype and
# can only be selected through a type cast.
CONVERSATION_MEMBER_SELECT = (
    "$select=id,displayName,roles,"
    "microsoft.graph.aadUserConversationMember/userId,"
    "microsoft.graph.aadUserConversationMember/email"
)


def _path_segments(url: str) -> list[str]:
    """Split a Work IQ resource path into its non-empty segments, dropping
    any query string (``/me/messages?$top=5`` → ``["me", "messages"]``)."""
    if not isinstance(url, str):
        return []
    return [segment for segment in url.split("?")[0].split("/") if segment]


def _members_url_for(segments: list[str]) -> str | None:
    """Return the roster path whose members bound the audience of the
    message collection at *segments*, or ``None`` if *segments* does not
    address Teams chat or channel messages.

    Mirrors the dispatch in ``policies/workiq/teams/messages.rego``.
    """
    keywords = [segment.lower() for segment in segments]
    chat_id: str | None = None
    conversation: str | None = None

    if keywords[:1] == ["chats"] and "messages" in keywords:
        chat_id = segments[1] if len(segments) > 1 else None
    elif keywords[:2] == ["me", "chats"] and "messages" in keywords:
        chat_id = segments[2] if len(segments) > 2 else None
    elif (
        len(keywords) > 3
        and keywords[0] == "users"
        and keywords[2] == "chats"
        and "messages" in keywords
    ):
        chat_id = segments[3]
    elif (
        len(keywords) > 4
        and keywords[0] == "teams"
        and keywords[2] == "channels"
        and keywords[4] == "messages"
    ):
        conversation = f"/teams/{segments[1]}/channels/{segments[3]}/members"

    if chat_id:
        conversation = f"/chats/{chat_id}/members"
    if conversation is None:
        return None
    return f"{conversation}?{CONVERSATION_MEMBER_SELECT}"


def _principals_from_members(members: Any) -> set[str]:
    """Collect the ``userId`` and ``email`` aliases of a Graph member
    collection.

    Both aliases are kept so a policy can match a principal named either
    way in a confidentiality set (see ``member_aliases`` in
    ``policies/workiq/teams/messages.rego``).
    """
    principals: set[str] = set()
    if not isinstance(members, list):
        return principals
    for member in members:
        if not isinstance(member, dict):
            continue
        for key in ("userId", "email"):
            value = member.get(key)
            if isinstance(value, str) and value.strip():
                principals.add(value.strip().lower())
    return principals


def _collection_items(data: Any) -> list[dict[str, Any]]:
    """Normalize a Graph payload to a list of entities: a collection
    response carries them under ``value``, a single-entity response *is*
    the entity."""
    if isinstance(data, dict):
        value = data.get("value")
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return [data]
    return []


def _default_labels() -> IFCLabels:
    return IFCLabels.from_security_lattice(SecurityLattice.default())


def _fail_closed_labels() -> IFCLabels:
    """The label given to content whose audience could not be
    established: readable by nobody until someone approves widening it."""
    return IFCLabels(integrity="untrusted", confidentiality=[])


def _private_labels(integrity: str) -> IFCLabels:
    """Return a private label with the requested integrity level."""
    return IFCLabels(integrity=integrity, confidentiality=[])


def _response_meta(tool_output: dict[str, Any]) -> LabeledMeta:
    """Keep returned entity data fail-closed while trusting the MCP envelope."""
    labels: dict[str, IFCLabels] = {"$": _fail_closed_labels()}
    trusted = _default_labels()
    for field in ("statusCode", "error", "requestId"):
        if field in tool_output:
            labels[f"$['structuredContent']['{field}']"] = trusted
    return LabeledMeta(**{IFC_LABELS_META_PREFIX: labels})


# --- Named per-path labelers for ``fetch`` --------------------------------
#
# ``fetch`` returns one result per resource path, and what bounds the
# audience of that result depends on the path. Each function below
# handles one kind of path; ``labellers`` in the server configuration
# maps path patterns to their names, the same way ``policies`` maps
# path patterns to Rego files. Keeping the mapping in configuration
# rather than in an if-chain here means a new domain is added by writing
# a labeler and naming it in config, and that the routing can be read
# without reading the code.


PathLabels = dict[str, IFCLabels]


def _message_labels(data: Any, audience: list[str]) -> PathLabels:
    """Label message content as untrusted while retaining trusted Graph metadata."""
    content_labels = IFCLabels(integrity="untrusted", confidentiality=audience)
    metadata_labels = IFCLabels(integrity="trusted", confidentiality=audience)
    labels = {"$": content_labels}
    metadata_fields = (
        "id",
        "replyToId",
        "etag",
        "messageType",
        "createdDateTime",
        "lastModifiedDateTime",
        "lastEditedDateTime",
        "deletedDateTime",
        "chatId",
        "webUrl",
        "channelIdentity",
        "from",
    )
    items = _collection_items(data)
    collection = isinstance(data, dict) and isinstance(data.get("value"), list)
    for index, item in enumerate(items):
        item_path = f"$['value'][{index}]" if collection else "$"
        for field in metadata_fields:
            if field in item:
                labels[f"{item_path}['{field}']"] = metadata_labels
    return labels


def _email_address(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    email = value.get("emailAddress")
    if not isinstance(email, dict):
        return None
    address = email.get("address")
    if not isinstance(address, str) or not address.strip():
        return None
    return address.strip().lower()


def _mail_audience(message: dict[str, Any]) -> list[str]:
    readers: set[str] = set()
    for field in ("from", "sender"):
        address = _email_address(message.get(field))
        if address:
            readers.add(address)
    for field in ("toRecipients", "ccRecipients", "bccRecipients", "replyTo"):
        recipients = message.get(field)
        if not isinstance(recipients, list):
            continue
        for recipient in recipients:
            address = _email_address(recipient)
            if address:
                readers.add(address)
    return sorted(readers)


def _calendar_audience(event: dict[str, Any]) -> list[str]:
    readers: set[str] = set()
    organizer = _email_address(event.get("organizer"))
    if organizer:
        readers.add(organizer)
    attendees = event.get("attendees")
    if isinstance(attendees, list):
        for attendee in attendees:
            address = _email_address(attendee)
            if address:
                readers.add(address)
    return sorted(readers)


def _entity_labels(
    data: Any,
    audience_for: Callable[[dict[str, Any]], list[str]],
    trusted_fields: tuple[str, ...],
) -> PathLabels:
    items = _collection_items(data)
    if not items:
        return {"$": _fail_closed_labels()}

    collection = isinstance(data, dict) and isinstance(data.get("value"), list)
    item_labels: list[IFCLabels] = []
    labels: PathLabels = {}
    for index, item in enumerate(items):
        audience = audience_for(item)
        content_label = IFCLabels(integrity="untrusted", confidentiality=audience)
        metadata_label = IFCLabels(integrity="trusted", confidentiality=audience)
        item_path = f"$['value'][{index}]" if collection else "$"
        labels[item_path] = content_label
        item_labels.append(content_label)
        for field in trusted_fields:
            if field in item:
                labels[f"{item_path}['{field}']"] = metadata_label

    aggregate = item_labels[0]
    for item_label in item_labels[1:]:
        aggregate = aggregate.join(item_label)
    labels["$"] = aggregate
    return labels


async def _label_teams_messages(
    url: str, data: Any, call_upstream: CallUpstream
) -> PathLabels:
    """Label Teams chat or channel messages with the roster of the
    conversation they belong to.

    The roster is read back from the upstream because a message payload
    does not enumerate the conversation's participants, only the author
    of each message.
    """
    members_url = _members_url_for(_path_segments(url))
    if members_url is None:
        return {"$": _fail_closed_labels()}
    roster = await call_upstream("fetch", {"entityUrls": [members_url]})
    results = (roster or {}).get("results") or []
    roster_data = results[0].get("data") if results else None
    principals = _principals_from_members(
        (roster_data or {}).get("value") if isinstance(roster_data, dict) else None
    )
    audience = sorted(principals)
    return _message_labels(data, audience)


async def _label_outlook_mail(
    url: str, data: Any, call_upstream: CallUpstream
) -> PathLabels:
    del url, call_upstream
    return _entity_labels(
        data,
        _mail_audience,
        (
            "id",
            "createdDateTime",
            "lastModifiedDateTime",
            "receivedDateTime",
            "sentDateTime",
            "conversationId",
            "internetMessageId",
            "parentFolderId",
            "from",
            "sender",
            "toRecipients",
            "ccRecipients",
            "bccRecipients",
            "replyTo",
            "isDraft",
            "isRead",
            "hasAttachments",
        ),
    )


async def _label_calendar_events(
    url: str, data: Any, call_upstream: CallUpstream
) -> PathLabels:
    del url, call_upstream
    return _entity_labels(
        data,
        _calendar_audience,
        (
            "id",
            "createdDateTime",
            "lastModifiedDateTime",
            "start",
            "end",
            "organizer",
            "attendees",
            "isOrganizer",
            "isCancelled",
            "responseStatus",
            "type",
            "seriesMasterId",
            "iCalUId",
            "uid",
        ),
    )


async def _label_teams_members(
    url: str, data: Any, call_upstream: CallUpstream
) -> PathLabels:
    """Label a member roster with its own members."""
    del url, call_upstream
    principals = _principals_from_members(
        data.get("value") if isinstance(data, dict) else None
    )
    label = IFCLabels(integrity="trusted", confidentiality=sorted(principals))
    labels = {"$": label}
    collection = isinstance(data, dict) and isinstance(data.get("value"), list)
    for index, member in enumerate(_collection_items(data)):
        item_path = f"$['value'][{index}]" if collection else "$"
        for field in member:
            labels[f"{item_path}['{field}']"] = label
    return labels


PathLabeller = Callable[[str, Any, CallUpstream], Awaitable[PathLabels]]

FETCH_LABELLERS: dict[str, PathLabeller] = {
    "calendarEvents": _label_calendar_events,
    "outlookMail": _label_outlook_mail,
    "teamsMessages": _label_teams_messages,
    "teamsMembers": _label_teams_members,
}


def _resolve_labeller_leaf(spec: Mapping[str, Any]) -> str:
    """Resolve the non-``path`` part of a ``labellers`` rule to a
    labeler name, rejecting names with no implementation so a typo fails
    at startup rather than silently labeling everything fail-closed."""
    name = spec.get("labeller")
    if not isinstance(name, str) or not name:
        raise TypeError(
            "WorkIQLabellingMiddleware: each rule must carry a non-empty "
            f"'labeller' name, got {name!r}"
        )
    extra = set(spec.keys()) - {"labeller"}
    if extra:
        raise ValueError(
            "WorkIQLabellingMiddleware: unsupported keys in rule: "
            f"{sorted(extra)}; expected 'path' and 'labeller'"
        )
    if name not in FETCH_LABELLERS:
        raise ValueError(
            f"WorkIQLabellingMiddleware: unknown labeller {name!r}; "
            f"known labellers are {sorted(FETCH_LABELLERS)}"
        )
    return name


def resolve_labellers(
    labellers: Mapping[str, Any] | None,
) -> dict[str, PathRules]:
    """Resolve a ``labellers`` config block to ``{tool_name: PathRules}``.

    Each entry has the same shape as a path-rule policy entry, with
    ``labeller`` in place of ``file`` / ``literal``::

        {"fetch": {"pathArg": "entityUrls",
                   "rules": [{"path": "/chats/*/messages/**",
                              "labeller": "teamsMessages"}]}}
    """
    if not labellers:
        return {}
    return {
        name: resolve_path_rules(
            spec,
            _resolve_labeller_leaf,
            origin="WorkIQLabellingMiddleware",
        )
        for name, spec in labellers.items()
    }


class WorkIQLabeling:
    """Labeling functions for WorkIQ MCP tool calls.

    Each ``label<ToolName>`` method takes the tool's input arguments and
    output payload, derives the IFC labels describing the confidentiality
    of the result, and returns a :class:`LabeledMeta` carrying them.

    Current labelers all yield a single :class:`IFCLabels` covering the
    whole result; that label is attached at the ``"$"`` payload-level
    fallback so it applies to every sub-object that doesn't carry a more
    specific label.
    """

    @staticmethod
    def labelListTeams(
        tool_input: dict[str, Any], tool_output: dict[str, Any]
    ) -> LabeledMeta:
        """Label a ``ListTeams`` result.

        Team rosters are treated as non-confidential, so the label is the
        baseline ``integrity=trusted`` with ``confidentiality=public``,
        attached at the ``"$"`` payload-level fallback.
        """
        del tool_input, tool_output
        return _fallback_meta(
            IFCLabels.from_security_lattice(SecurityLattice.default())
        )

    @staticmethod
    def labelListChannels(
        tool_input: dict[str, Any], tool_output: dict[str, Any]
    ) -> LabeledMeta:
        """Label a ``ListChannels`` result.

        Channel listings are treated as non-confidential, so the label is
        the baseline ``integrity=trusted`` with ``confidentiality=public``,
        attached at the ``"$"`` payload-level fallback.
        """
        del tool_input, tool_output
        return _fallback_meta(
            IFCLabels.from_security_lattice(SecurityLattice.default())
        )

    @staticmethod
    def labelListChats(
        tool_input: dict[str, Any], tool_output: dict[str, Any]
    ) -> LabeledMeta:
        """Label a ``ListChats`` result.

        Chat listings are treated as non-confidential, so the label is
        the baseline ``integrity=trusted`` with ``confidentiality=public``,
        attached at the ``"$"`` payload-level fallback.
        """
        del tool_input, tool_output
        # TODO: this returns message previews that may contain confidential info
        # Should be labelled more restrictively.
        return _fallback_meta(
            IFCLabels.from_security_lattice(SecurityLattice.default())
        )

    @staticmethod
    def labelListChannelMembers(
        tool_input: dict[str, Any], tool_output: dict[str, Any]
    ) -> LabeledMeta:
        """Label a ``ListChannelMembers`` result by its members' ``userId``s.

        The resulting :class:`IFCLabels` is attached at the ``"$"``
        payload-level fallback so it applies to the whole result.
        """
        del tool_input  # unused; confidentiality is derived from the output
        return _label_from_members(tool_output, integrity="trusted")

    @staticmethod
    def labelListChatMembers(
        tool_input: dict[str, Any], tool_output: dict[str, Any]
    ) -> LabeledMeta:
        """Label a ``ListChatMembers`` result by its members' ``userId``s.

        The resulting :class:`IFCLabels` is attached at the ``"$"``
        payload-level fallback so it applies to the whole result.
        """
        del tool_input  # unused; confidentiality is derived from the output
        return _label_from_members(tool_output, integrity="trusted")

    @staticmethod
    async def labelListChatMessages(
        tool_input: dict[str, Any],
        tool_output: dict[str, Any],
        call_upstream: CallUpstream,
    ) -> LabeledMeta:
        """Label a ``ListChatMessages`` result by the chat's full member roster.

        The ``ListChatMessages`` response itself does not enumerate
        participants, so we call the upstream ``ListChatMembers`` tool to
        retrieve the roster and use the resulting ``userId``s as the
        confidentiality set. The resulting :class:`IFCLabels` is
        attached at the ``"$"`` payload-level fallback.
        """
        del tool_output  # confidentiality comes from the upstream roster
        chat_id = tool_input.get("chatId")
        if not chat_id:
            raise ValueError("tool_input for ListChatMessages missing required chatId")
        members_payload = await call_upstream("ListChatMembers", {"chatId": chat_id})
        return _label_from_members(members_payload, integrity="untrusted")

    @staticmethod
    async def labelListChannelMessages(
        tool_input: dict[str, Any],
        tool_output: dict[str, Any],
        call_upstream: CallUpstream,
    ) -> LabeledMeta:
        """Label a ``ListChannelMessages`` result by the channel's full member roster.

        The ``ListChannelMessages`` response itself does not enumerate
        participants, so we call the upstream ``ListChannelMembers`` tool to
        retrieve the roster and use the resulting ``userId``s as the
        confidentiality set. The resulting :class:`IFCLabels` is
        attached at the ``"$"`` payload-level fallback.
        """
        del tool_output  # confidentiality comes from the upstream roster
        channel_id = tool_input.get("channelId")
        if not channel_id:
            raise ValueError(
                "tool_input for ListChannelMessages missing required channelId"
            )
        team_id = tool_input.get("teamId")
        if not team_id:
            raise ValueError(
                "tool_input for ListChannelMessages missing required teamId"
            )
        members_payload = await call_upstream(
            "ListChannelMembers", {"teamId": team_id, "channelId": channel_id}
        )
        return _label_from_members(members_payload, integrity="untrusted")

    # -- Work IQ server --------------------------------------------------

    @staticmethod
    async def labelfetch(
        tool_input: dict[str, Any],
        tool_output: dict[str, Any],
        call_upstream: CallUpstream,
        path_rules: PathRules | None = None,
    ) -> LabeledMeta:
        """Label a Work IQ ``fetch`` result by the audience of the
        entities it returned.

        ``fetch`` takes a list of resource paths and returns one result
        per path, so the label of the whole payload is the *join* of the
        per-path labels (i.e. the intersection of their reader sets: the
        result is only readable by principals cleared for every part of
        it).

        Which labeler handles a path is decided by *path_rules*, the
        ``labellers`` block of the server configuration. If no rules are
        configured, or a path matches none of them, the result is labelled
        with an empty reader set: an unrecognized path is not evidence that
        its contents are public. The result stays usable, but sending it on
        requires explicit approval.
        """
        urls = tool_input.get("entityUrls") or []
        results = (tool_output or {}).get("results") or []
        labels: list[IFCLabels] = []
        field_labels: dict[str, IFCLabels] = {}
        for index, url in enumerate(urls):
            result = results[index] if index < len(results) else {}
            data = (result or {}).get("data") if isinstance(result, dict) else None
            name = (
                match_path(path_rules, url)
                if path_rules is not None and isinstance(url, str)
                else None
            )
            labeller = FETCH_LABELLERS.get(name) if name is not None else None
            if labeller is None:
                path_labels = {"$": _fail_closed_labels()}
            else:
                path_labels = await labeller(url, data, call_upstream)

            result_path = f"$['structuredContent']['results'][{index}]['data']"
            envelope_path = f"$['structuredContent']['results'][{index}]"
            if isinstance(result, dict):
                for field in ("statusCode", "error", "requestId"):
                    if field in result:
                        field_labels[f"{envelope_path}['{field}']"] = _default_labels()
            for relative_path, path_label in path_labels.items():
                absolute_path = (
                    result_path
                    if relative_path == "$"
                    else f"{result_path}{relative_path[1:]}"
                )
                field_labels[absolute_path] = path_label
            labels.append(path_labels["$"])

        if not labels:
            return _fallback_meta(_default_labels())

        label = labels[0]
        for other in labels[1:]:
            label = label.join(other)
        return LabeledMeta(
            **{
                IFC_LABELS_META_PREFIX: {
                    "$": label,
                    **field_labels,
                }
            }
        )

    # TODO: Support Rego-based label computation as an alternative to these
    # Python labeler wrappers.
    # TODO: Use fixed or dynamically retrieved output schemas to address
    # individual response fields, then assign field-level IFC labels based on
    # each field's semantics. Keep these tool-level labels as conservative
    # fallbacks for fields without a more specific label.

    @staticmethod
    def labelask(tool_input: dict[str, Any]) -> LabeledMeta:
        """Label a Work IQ ``ask`` result as maximally confidential.

        ``ask`` answers a natural-language question by searching across
        the user's entire M365 estate, so its provenance (and therefore
        its audience) cannot be recovered from the response. Labeling it
        with an empty reader set is the fail-closed choice: the answer can
        still be used, but forwarding it anywhere requires an explicit
        approval from the ``ask`` decision of the send policies.
        """
        del tool_input
        return _fallback_meta(_fail_closed_labels())

    @staticmethod
    def labelsearch_paths(tool_input: dict[str, Any]) -> LabeledMeta:
        """Label server-owned path metadata as trusted and public."""
        del tool_input
        return _fallback_meta(_default_labels())

    @staticmethod
    def labelget_schema(tool_input: dict[str, Any]) -> LabeledMeta:
        """Label server-owned schema metadata as trusted and public."""
        del tool_input
        return _fallback_meta(_default_labels())

    @staticmethod
    def labellist_agents(tool_input: dict[str, Any]) -> LabeledMeta:
        """Label the tenant-specific agent list as trusted and private."""
        del tool_input
        return _fallback_meta(_private_labels("trusted"))

    @staticmethod
    def labelfetch_blob(
        tool_input: dict[str, Any], tool_output: dict[str, Any]
    ) -> LabeledMeta:
        """Keep binary content private while trusting response metadata."""
        del tool_input
        return _response_meta(tool_output)

    @staticmethod
    def labelcall_function(
        tool_input: dict[str, Any], tool_output: dict[str, Any]
    ) -> LabeledMeta:
        """Fail closed for function data while trusting response metadata."""
        del tool_input
        return _response_meta(tool_output)

    @staticmethod
    def labelcreate_entity(
        tool_input: dict[str, Any], tool_output: dict[str, Any]
    ) -> LabeledMeta:
        """Fail closed for echoed entity data while trusting write metadata."""
        del tool_input
        return _response_meta(tool_output)

    @staticmethod
    def labelupdate_entity(
        tool_input: dict[str, Any], tool_output: dict[str, Any]
    ) -> LabeledMeta:
        """Fail closed for updated entity data while trusting write metadata."""
        del tool_input
        return _response_meta(tool_output)

    @staticmethod
    def labeldelete_entity(
        tool_input: dict[str, Any], tool_output: dict[str, Any]
    ) -> LabeledMeta:
        """Fail closed for deletion data while trusting write metadata."""
        del tool_input
        return _response_meta(tool_output)

    @staticmethod
    def labeldo_action(
        tool_input: dict[str, Any], tool_output: dict[str, Any]
    ) -> LabeledMeta:
        """Fail closed for action data while trusting response metadata."""
        del tool_input
        return _response_meta(tool_output)


class WorkIQLabellingMiddleware(Middleware):
    """FastMCP middleware that labels tool results from selected WorkIQ
    MCP servers.

    - ``on_call_tool`` stamps every tool result with an ``ifc`` label in
    ``_meta``.

    Labelers may be either sync (``label<Tool>(tool_input, tool_output)``)
    or async (``label<Tool>(tool_input, tool_output, call_upstream)``) and
    return a :class:`LabeledMeta`. Async labelers receive a
    :data:`CallUpstream` helper that issues calls against the same
    upstream MCP server through the configured *upstream_client_factory*.
    This lets a labeler enrich its decision with data that isn't in the
    tool's own response — e.g. ``labelListChatMessages`` calling
    ``ListChatMembers`` to recover the chat's full participant roster.
    """

    def __init__(
        self,
        upstream_client_factory: Callable[[], Client[ClientTransportT]] | None = None,
        labellers: Mapping[str, Any] | None = None,
    ) -> None:
        self._upstream_client_factory = upstream_client_factory
        self._labellers: dict[str, PathRules] = resolve_labellers(labellers)

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        result = await call_next(context)
        meta = dict(result.meta) if result.meta else {}

        tool_name = getattr(getattr(context, "message", None), "name", None)
        labeler: Callable[..., LabeledMeta] | None = (
            getattr(WorkIQLabeling, f"label{tool_name}", None) if tool_name else None
        )
        labeled_meta: LabeledMeta | None = None
        if callable(labeler):
            tool_input: dict[str, Any] = (
                getattr(getattr(context, "message", None), "arguments", None) or {}
            )
            parameters = inspect.signature(labeler).parameters
            needs_output = "tool_output" in parameters
            tool_output: dict[str, Any] | None = None
            if needs_output:
                try:
                    tool_output = extract_structured_content(result)
                except ValueError as e:
                    # A labeler that inspects the output cannot safely label
                    # a response whose structured payload is unavailable.
                    raise ValueError(
                        f"WorkIQLabellingMiddleware: cannot extract structured "
                        f"content from upstream response for tool {tool_name!r}; "
                        f"refusing to label to avoid mislabeling ({e})"
                    ) from e
            try:
                path_rules = self._path_rules_for(labeler, tool_name)
                if inspect.iscoroutinefunction(labeler):
                    assert tool_output is not None
                    labeled_meta = await self._run_async_labeler(
                        labeler, tool_input, tool_output, path_rules
                    )
                elif needs_output:
                    assert tool_output is not None
                    labeled_meta = labeler(tool_input, tool_output)
                else:
                    labeled_meta = labeler(tool_input)
            except Exception:
                labeled_meta = None
            if needs_output and result.structured_content is None:
                result.structured_content = tool_output
        if labeled_meta is None:
            # No tool-specific labeler (or it failed) — fall back to the
            # fail-closed IFC labels so an unknown result is never treated as
            # trusted or public merely because no precise labeler exists.
            labeled_meta = _fallback_meta(_fail_closed_labels())

        meta[IFC_LABELS_META_PREFIX] = {
            path: labels.model_dump()
            for path, labels in labeled_meta.ifc_labels.items()
        }
        result.meta = meta
        return result

    def _path_rules_for(
        self, labeler: Callable[..., Any], tool_name: str | None
    ) -> PathRules | None:
        """Return the configured path rules to hand to *labeler*, if it
        takes any.

        A labeler declares that its dispatch is resource-path based by accepting a
        ``path_rules`` parameter. Labelers bound to a tool that names a
        single kind of entity do not, and are left alone.
        """
        if "path_rules" not in inspect.signature(labeler).parameters:
            return None
        return self._labellers.get(tool_name) if tool_name else None

    async def _run_async_labeler(
        self,
        labeler: Callable[..., Awaitable[LabeledMeta]],
        tool_input: dict[str, Any],
        tool_output: dict[str, Any],
        path_rules: PathRules | None = None,
    ) -> LabeledMeta:
        """Invoke an async labeler with a :data:`CallUpstream` helper.

        Opens a fresh upstream session from the configured factory and
        exposes a ``call_upstream(name, arguments)`` coroutine that
        forwards to ``session.call_tool`` and returns its structured
        payload via :func:`mcp_result.extract_structured_content`
        (which transparently handles upstreams that ship the payload as
        ``content[0].text`` rather than ``structured_content``). Raises
        ``RuntimeError`` if no factory is configured — async labelers are
        useless without one.

        *path_rules* is forwarded only to labelers that accept it (see
        :meth:`_path_rules_for`).
        """
        extra = {} if path_rules is None else {"path_rules": path_rules}
        if self._upstream_client_factory is None:

            async def unavailable_upstream(
                name: str, arguments: dict[str, Any]
            ) -> dict[str, Any]:
                del name, arguments
                raise RuntimeError(
                    f"Async labeler {labeler.__qualname__!r} requires an "
                    "auxiliary upstream call that is unavailable for this transport"
                )

            return await labeler(
                tool_input,
                tool_output,
                unavailable_upstream,
                **extra,
            )
        async with self._upstream_client_factory() as session:

            async def call_upstream(
                name: str, arguments: dict[str, Any]
            ) -> dict[str, Any]:
                result = await session.call_tool(name, arguments)
                return extract_structured_content(result)

            return await labeler(tool_input, tool_output, call_upstream, **extra)
