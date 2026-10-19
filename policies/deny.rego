package policy

import rego.v1

expected_version := ""

# Utility definitions

info := upstream.serverInfo()

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
} else := deny("Calls to this tool are unconditionally denied")
