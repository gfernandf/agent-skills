package orca.policy.pre

# Baseline policy bundle for pre-execution decisions.
# Runtime safety remains authoritative during staged rollout.

default result := {"status": "allow"}

result := {"status": "block", "reason": "same_tenant_context_missing"} if {
  input.safety.allowed_targets[_] == "same_tenant"
  not input.context_tenant_id
}

result := {
  "status": "block",
  "reason": sprintf("same_tenant_mismatch:%v!=%v", [input.target_tenant_id, input.context_tenant_id]),
} if {
  input.safety.allowed_targets[_] == "same_tenant"
  input.context_tenant_id
  input.target_tenant_id
  input.target_tenant_id != input.context_tenant_id
}
