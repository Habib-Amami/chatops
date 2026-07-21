from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models import BaseChatModel

from app.agent.models import ChatModelFactory, ModelConfigurationError
from app.core import Settings


def test_model_factory_requires_provider_and_model_name() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    factory = ChatModelFactory(settings)

    with pytest.raises(ModelConfigurationError, match="MODEL_PROVIDER"):
        factory.get_model()


@pytest.mark.parametrize(
    "model_name",
    [
        "meta-llama/llama-prompt-guard-2-22m",
        "meta-llama/llama-prompt-guard-2-86m",
    ],
)
def test_model_factory_rejects_groq_prompt_guard_models(
    model_name: str,
) -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        model_provider="groq",
        model_name=model_name,
    )
    factory = ChatModelFactory(settings)

    with pytest.raises(ModelConfigurationError, match="Tool Use"):
        factory.get_model()


@patch("app.agent.models.factory.init_chat_model")
def test_model_factory_initializes_and_reuses_configured_model(
    init_chat_model: MagicMock,
) -> None:
    expected_model = MagicMock(spec=BaseChatModel)
    init_chat_model.return_value = expected_model
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        model_provider="example-provider",
        model_name=" example-model ",
        model_api_key="secret-key",
    )
    factory = ChatModelFactory(settings)

    first_model = factory.get_model()
    second_model = factory.get_model()

    assert first_model is expected_model
    assert second_model is expected_model
    init_chat_model.assert_called_once_with(
        model="example-model",
        model_provider="example-provider",
        timeout=30.0,
        max_retries=0,
        api_key="secret-key",
    )


@patch("app.agent.models.factory.init_chat_model")
def test_model_factory_hides_groq_qwen_reasoning(
    init_chat_model: MagicMock,
) -> None:
    init_chat_model.return_value = MagicMock(spec=BaseChatModel)
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        model_provider="groq",
        model_name="qwen/qwen3.6-27b",
        model_api_key="secret-key",
    )

    ChatModelFactory(settings).get_model()

    init_chat_model.assert_called_once_with(
        model="qwen/qwen3.6-27b",
        model_provider="groq",
        timeout=30.0,
        max_retries=0,
        api_key="secret-key",
        reasoning_effort="none",
        reasoning_format="hidden",
    )
