package policy

import rego.v1

# Policy for posting a Teams message using ``create_entity``
# server.
#
# This policies applies to calls to ``create_entity`` against a collection of Graph paths, e.g.
#
#   parentUrl = /teams/{team-id}/channels/{channel-id}/messages
#   parentUrl = /teams/{team-id}/channels/{channel-id}/messages/{id}/replies
#   parentUrl = /chats/{chat-id}/messages
#
# A single tool covers every creation, so the configuration routes calls
# to this file by the ``parentUrl`` they name (see the ``pathArg`` /
# ``rules`` block of ``config.workiq.example.json``). This file owns
# Teams messaging only; other creation paths are routed elsewhere or, by
# default, to ``deny.rego``. The path is re-derived here regardless, both
# to locate the conversation whose membership forms the audience and so the
# policy stays fail-closed if it is ever bound to a wider set of paths
# than it covers.
#
# See ``../allow.rego`` for why ``expected_version`` is
# unpinned by default.

expected_version := ""

info := upstream.serverInfo()

default decision := {}

allow(msg) := {"decision": "allow", "message": msg}

deny(msg) := {"decision": "deny", "message": msg}

ask(msg) := {"decision": "ask", "message": msg}

incompatible_version if {
	info != null
	semver.is_valid(expected_version)
	semver.is_valid(info.version)
	not semver.compare(info.version, expected_version) == 0
}

# Request shape

path := split(input.arguments.parentUrl, "?")[0]

segments := [segment |
	some segment in split(path, "/")
	segment != ""
]

# Path *keywords* are matched case-insensitively; identifiers are taken
# from ``segments`` so their original casing is preserved.
keywords := [lower(segment) | some segment in segments]

# ``userId`` and ``email`` live on the aadUserConversationMember subtype,
# so they have to be selected through a type cast.
member_select := "$select=id,displayName,roles,microsoft.graph.aadUserConversationMember/userId,microsoft.graph.aadUserConversationMember/email"

# Audience of a message post: the membership of the target chat or channel.

members_url := sprintf("/chats/%s/members?%s", [segments[1], member_select]) if {
	keywords[0] == "chats"
	count(segments) == 3
	keywords[2] == "messages"
}

members_url := sprintf("/chats/%s/members?%s", [segments[2], member_select]) if {
	keywords[0] == "me"
	keywords[1] == "chats"
	count(segments) == 4
	keywords[3] == "messages"
}

members_url := sprintf("/chats/%s/members?%s", [segments[3], member_select]) if {
	keywords[0] == "users"
	keywords[2] == "chats"
	count(segments) == 5
	keywords[4] == "messages"
}

members_url := sprintf("/teams/%s/channels/%s/members?%s", [segments[1], segments[3], member_select]) if {
	keywords[0] == "teams"
	keywords[2] == "channels"
	keywords[4] == "messages"
	count(segments) == 5
}

members_url := sprintf("/teams/%s/channels/%s/members?%s", [segments[1], segments[3], member_select]) if {
	keywords[0] == "teams"
	keywords[2] == "channels"
	keywords[4] == "messages"
	count(segments) == 7
	keywords[6] == "replies"
}

members_response := upstream.fetch({"entityUrls": [members_url]}) if {
	members_url
}

members_result := members_response.results[0]

membership_available if {
	members_result.statusCode == 200
}

# A paginated membership list is an incomplete audience: fail closed rather than
# clearing a message against a partial member list.
# TODO: Follow @odata.nextLink until the complete membership is collected or a threshold
# audience size is exceeded.
membership_complete if {
	not members_result.data["@odata.nextLink"]
}

members := [member |
	some member in members_result.data.value
	is_object(member)
]

# Policy logic

context_trusted := ifc.label("$.name").integrity == "trusted"

content_readers := {lower(reader) |
	some reader in ifc.label("$.arguments.jsonBody").confidentiality
}

content_public if {
	"public" in content_readers
}

# A member may be named in the confidentiality set either by their AAD
# object ID or by their mail address, so any alias grants access.
member_aliases(member) := {lower(alias) |
	some alias in [object.get(member, "userId", ""), object.get(member, "email", "")]
	is_string(alias)
	alias != ""
}

member_name(member) := object.get(member, "email", "") if {
	object.get(member, "email", "") != ""
} else := object.get(member, "userId", "") if {
	object.get(member, "userId", "") != ""
} else := object.get(member, "displayName", "an unidentified member")

unauthorized contains name if {
	some member in members
	count(member_aliases(member) & content_readers) == 0
	name := member_name(member)
}

msg := sprintf(
	"Posting the message would declassify it to %s.",
	[concat(", ", sort(unauthorized))],
)

# Decision

decision := deny("The policy is incompatible with the server version.") if {
	incompatible_version
} else := allow("The tool call was generated in a trusted context.") if {
	context_trusted
} else := deny("Creating entities at this path is not covered by a policy.") if {
	not members_url
} else := allow("The message content is public.") if {
	content_public
} else := ask("The membership of the target conversation could not be verified.") if {
	not membership_available
} else := ask("The complete membership of the target conversation could not be verified.") if {
	not membership_complete
} else := allow("All conversation members are authorized to read the content.") if {
	count(unauthorized) == 0
} else := ask(msg) if {
	count(unauthorized) > 0
} else := deny("Denied")
