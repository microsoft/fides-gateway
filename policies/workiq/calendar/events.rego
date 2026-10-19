package policy

import rego.v1

expected_version := ""
info := upstream.serverInfo()

allow(msg) := {"decision": "allow", "message": msg}
deny(msg) := {"decision": "deny", "message": msg}
ask(msg) := {"decision": "ask", "message": msg}

compatible_version if {
	expected_version == ""
}

compatible_version if {
	info != null
	semver.is_valid(expected_version)
	is_string(info.version)
	semver.is_valid(info.version)
	semver.compare(info.version, expected_version) == 0
}

target := input.arguments.parentUrl if {
	input.name == "create_entity"
} else := input.arguments.entityUrl if {
	input.name == "update_entity"
}

path := split(target, "?")[0]

covered_path if {
	input.name == "create_entity"
	regex.match(`(?i)^/me/(calendar/)?events/?$`, path)
}

covered_path if {
	input.name == "update_entity"
	regex.match(`(?i)^/me/(calendar/)?events/[^/]+/?$`, path)
	segments := split(trim(path, "/"), "/")
	identifier := lower(urlquery.decode(segments[count(segments) - 1]))
	not identifier in {".", ".."}
	not contains(identifier, "/")
	not contains(identifier, "\\")
}

body := input.arguments.jsonBody if {
	is_object(input.arguments.jsonBody)
} else := json.unmarshal(input.arguments.jsonBody) if {
	is_string(input.arguments.jsonBody)
	json.is_valid(input.arguments.jsonBody)
}

valid_body if {
	is_object(body)
	is_array(object.get(body, "attendees", []))
}

context_trusted := ifc.label("$.name").integrity == "trusted"

content_readers := {lower(reader) |
	some reader in ifc.label("$.arguments.jsonBody").confidentiality
}

content_public if {
	"public" in content_readers
}

needs_audience if {
	covered_path
	valid_body
	not context_trusted
	not content_public
}

owner_response := upstream.fetch({"entityUrls": ["/me?$select=id,mail,userPrincipalName"]}) if {
	needs_audience
}

owner_result := owner_response.results[0]
owner := owner_result.data

owner_aliases := {lower(value) |
	some field in ["id", "mail", "userPrincipalName"]
	value := owner[field]
	is_string(value)
	value != ""
}

owner_known if {
	owner_result.statusCode == 200
	is_object(owner)
	count(owner_aliases) > 0
}

event_response := upstream.fetch({"entityUrls": [sprintf("%s?$select=id,organizer,attendees", [path])]}) if {
	needs_audience
	input.name == "update_entity"
}

event_result := event_response.results[0]
event := event_result.data

recipient_aliases(recipient) := {lower(address) |
	address := recipient.emailAddress.address
	is_string(address)
	address != ""
}

event_known if {
	event_result.statusCode == 200
	is_object(event)
	is_array(object.get(event, "attendees", []))
	count(recipient_aliases(event.organizer)) > 0
}

proposed_recipients := array.concat(object.get(body, "attendees", []), [body.organizer]) if {
	valid_body
	"organizer" in object.keys(body)
} else := object.get(body, "attendees", []) if {
	valid_body
}

recipients := proposed_recipients if {
	input.name == "create_entity"
} else := array.concat(
	array.concat([event.organizer], object.get(event, "attendees", [])),
	proposed_recipients,
) if {
	valid_body
	input.name == "update_entity"
	event_known
}

audience_known if {
	owner_known
	input.name == "create_entity"
}

audience_known if {
	owner_known
	input.name == "update_entity"
	event_known
}

unidentified_recipient if {
	some recipient in recipients
	count(recipient_aliases(recipient)) == 0
}

unauthorized_owner if {
	count(owner_aliases & content_readers) == 0
}

unauthorized contains address if {
	some recipient in recipients
	aliases := recipient_aliases(recipient)
	count(aliases & content_readers) == 0
	some address in aliases
}

decision := deny("The policy is incompatible with the server version.") if {
	not compatible_version
} else := deny("This Calendar operation or resource path is not covered by a policy.") if {
	not covered_path
} else := deny("The event body must be a JSON object with an optional attendees array.") if {
	not valid_body
} else := allow("The tool call was generated in a trusted context.") if {
	context_trusted
} else := allow("The event content is public.") if {
	content_public
} else := ask("The Calendar owner or existing event audience could not be verified.") if {
	not audience_known
} else := ask("An event recipient could not be identified.") if {
	unidentified_recipient
} else := ask("The Calendar owner is not authorized to read the event content.") if {
	unauthorized_owner
} else := ask(sprintf("Updating the Calendar would disclose content to %s.", [concat(", ", sort(unauthorized))])) if {
	count(unauthorized) > 0
} else := allow("The Calendar owner and all event recipients are authorized to read the content.")
