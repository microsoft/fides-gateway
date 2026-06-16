package policy

import rego.v1

version := "3.3.1"

# Utility definitions

info := upstream.serverInfo()

deny(msg)  := {"decision": "deny",  "message": msg}

default decision := {}

decision := deny("The policy is incompatible with the server version.") if {
    info != null
    semver.is_valid(info.version)
    not (semver.compare(info.version, version) == 0)
} else := deny("Calls to this tool are unconditionally denied")
