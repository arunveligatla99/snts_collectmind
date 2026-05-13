# Diagnostic finding

Tenant: {{ tenant_id }}
Finding: {{ finding_id }}
Anomaly type: {{ anomaly_type }}
Hypothesis class: {{ hypothesis_class }}
Hypothesis: {{ hypothesis_statement }}
Vehicle scope: {{ vehicle_scope_json }}
Upstream confidence: {{ upstream_confidence }}
Candidate signals (optional hints): {{ candidate_signals_json }}

# Task

Produce a `CollectionPolicySpec` JSON object that:

1. Selects the minimum set of VSS v6.0 signals needed to confirm or rule out the hypothesis above.
2. Sets sampling rates per the system-prompt guidance.
3. Sets `policy_id` to `"policy-{{ finding_id }}"` and `version` to `"1.0.0"`.
4. Sets `generated_from_session_id` to `"{{ session_id }}"`.
5. Sets `originating_finding` to `{"tenant_id": "{{ tenant_id }}", "finding_id": "{{ finding_id }}"}`.
6. Sets `vehicle_scope` to the list above verbatim.
7. Selects a window that fits the hypothesis: brake-wear early-stage usually wants 24-72 hours.
8. Sets `data_governance_flags` correctly per the PII rules.
9. Sets `confidence_threshold` per the system-prompt guidance.
{% if retry_context %}

# Retry context

The previous generation failed validation. Address the errors below and try again.

{{ retry_context_json }}
{% endif %}
