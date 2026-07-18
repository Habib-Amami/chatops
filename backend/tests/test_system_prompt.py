from app.agent.prompts import CHATOPS_SYSTEM_PROMPT


def test_system_prompt_is_environment_agnostic() -> None:
    environment_specific_values = (
        "demo-app",
        "chatops-demo",
        "OpsTasks",
        "opstasks-logs",
        "opstasks-assets",
    )

    for value in environment_specific_values:
        assert value not in CHATOPS_SYSTEM_PROMPT


def test_system_prompt_matches_the_users_language() -> None:
    assert "same language as the user's most recent message" in CHATOPS_SYSTEM_PROMPT
    assert "respond in English" in CHATOPS_SYSTEM_PROMPT
    assert "Answer in French" not in CHATOPS_SYSTEM_PROMPT


def test_system_prompt_requires_explicit_resource_scope() -> None:
    assert "Never assume a Kubernetes namespace" in CHATOPS_SYSTEM_PROMPT
    assert "ask one concise clarification question" in CHATOPS_SYSTEM_PROMPT
    assert "configured allowlists" in CHATOPS_SYSTEM_PROMPT
