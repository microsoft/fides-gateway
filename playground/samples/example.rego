package example

import rego.v1

version := "3.3.1"

info := upstream.serverInfo()

allow(msg) := {"decision": "allow", "message": msg}
deny(msg)  := {"decision": "deny",  "message": msg}
ask(msg)   := {"decision": "ask",   "message": msg}

context_trusted := ifc.label("$.name").integrity == "trusted"

content_readers := ifc.label("$.arguments.content").confidentiality

members := upstream.ListChannelMembers({
    "teamId": input.arguments.teamId,
    "channelId": input.arguments.channelId
})

target_user_ids := { m.userId | some m in members.members }

allowed_user_ids := { m | some m in content_readers }

missing := target_user_ids - allowed_user_ids

msg := sprintf("Sending the message would declassify it to users with IDs %s. Are you sure you want to continue?",
               [concat(", ", sort(missing))])


decision := deny("The policy is incompatible with the server version.") if {
    info != null
    semver.is_valid(info.version)
    not (semver.compare(info.version, version) == 0)
} else := allow("The tool call was generated in a trusted context.") if {
  context_trusted == true
} else := allow("All channel members are authorized to read the content.") if {
  count(missing) == 0
} else := ask(msg) if {
  count(missing) >= 0
} else := deny("Denied")
