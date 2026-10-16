# Agents

`InvestigationState` carries the user problem, relevant files, hypotheses, evidence, proposed fix, generated tests, test results, verification, and history. `DebuggingWorkflow` advances through small named nodes. Each transition adds an audit event. Deterministic tools are preferred; an LLM provider can augment synthesis but cannot override execution evidence. Provider output is schema-validated and retried once with a constrained correction prompt.

