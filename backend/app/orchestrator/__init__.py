"""QUASAR Research Orchestrator: one controlled LangGraph workflow over allowlisted deterministic tools.

REQUEST -> PLAN -> ELIGIBILITY -> APPROVAL -> EXECUTE -> VALIDATE -> CRITIC -> REPORT

The language model (optional, via LangChain) only proposes a typed plan. Every step is checked against
the tool allowlist, scientific eligibility is enforced before execution, permission tier T2 waits for
explicit human approval, and all scientific numbers come from existing deterministic services (docs/23).
"""
