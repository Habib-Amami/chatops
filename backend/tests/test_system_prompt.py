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


def test_system_prompt_does_not_delegate_conversation_persistence() -> None:
    assert "persist the conversation" not in CHATOPS_SYSTEM_PROMPT


def test_system_prompt_stops_after_rejected_or_missing_mutation() -> None:
    assert "If the user rejects a mutation" in CHATOPS_SYSTEM_PROMPT
    assert "do not\n  retry it" in CHATOPS_SYSTEM_PROMPT
    assert "target was not found" in CHATOPS_SYSTEM_PROMPT


def test_system_prompt_explains_standalone_pod_lifecycle() -> None:
    assert "Before creating a standalone Pod" in CHATOPS_SYSTEM_PROMPT
    assert "Docker Hub is the default" in CHATOPS_SYSTEM_PROMPT
    assert "image will be checked before creation" in CHATOPS_SYSTEM_PROMPT
    assert "will not be recreated after deletion" in CHATOPS_SYSTEM_PROMPT
