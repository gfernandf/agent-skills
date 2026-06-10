---
name: Governance Validation Failure
about: Automated report of continuous governance validation failure
title: "❌ Governance Validation Failed - [Check Name]"
labels: ["governance", "validation", "automated"]
assignees: []
---

## Continuous Governance Validation Failure

**Automated Report**: This issue was created by the `governance_continuous_validation` workflow.

### Failure Summary

| Field | Value |
|-------|-------|
| **Workflow Run** | [Run Link] |
| **Check Failed** | [Check Name] |
| **Failure Status** | [Status from Report] |
| **Timestamp** | [When failure occurred] |
| **Report Artifact** | [Link to governance_continuous_validation_report.json] |

### Failing Check Details

**Check Name**: [Name of specific governance check]

**Expected State**: [What should be true]

**Actual State**: [What is currently true]

**Error/Issue**:
```
[Error details from report]
```

### Impact

This failure indicates potential **governance drift** that may affect:
- Branch protection enforcement
- CI/CD pipeline stability
- Release gate decision logic
- Policy profile consistency

### Remediation Steps

**Immediate Actions**:
1. Review the failing check details above
2. Consult `docs/CONTINUOUS_GOVERNANCE_VALIDATION.md` for remediation guidance
3. Follow the remediation steps for your specific failing check

**Common Remediation**:
- **Branch Protection**: Verify GitHub ruleset is active and contains all required checks
- **Trend SLO**: Check if recent CI runs have high failure rates or insufficient samples
- **Status Checks Consistency**: Ensure `docs/required_status_checks.json` matches workflow definitions
- **Release Gate Policy**: Validate `.github/release_gate_policy.json` JSON syntax and profile structure

### Next Steps

- [ ] Investigate root cause
- [ ] Apply remediation from `CONTINUOUS_GOVERNANCE_VALIDATION.md`
- [ ] Manual re-run validation: `gh workflow run governance_continuous_validation.yml`
- [ ] Confirm fix resolves issue
- [ ] Close issue once validation passes

### Documentation References

- [Continuous Governance Validation Runbook](../docs/CONTINUOUS_GOVERNANCE_VALIDATION.md)
- [GitHub Ruleset Configuration](../docs/GITHUB_RULESET_RUNBOOK.md)
- [Required Status Checks](../docs/required_status_checks.json)
- [Release Gate Policy](../.github/release_gate_policy.json)

---

*This issue template is automatically populated by the continuous governance validation workflow.*
*For questions about the validation system, see the runbook or contact the maintainers.*
