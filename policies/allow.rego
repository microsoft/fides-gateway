package policy

import rego.v1

# Generic admission does not depend on a transport library's version.
# Operators may pin an actual upstream service compatibility contract here.
expected_version := ""

# Utility definitions

info := upstream.serverInfo()

allow(msg) := {"decision": "allow", "message": msg}
deny(msg)  := {"decision": "deny",  "message": msg}

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

decision := deny("The policy is incompatible with the server version.") if {
    not compatible_version
} else := allow("Calls to this tool are unconditionally allowed")
