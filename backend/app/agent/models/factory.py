"""Provider-neutral LangChain chat model factory."""

from typing import Any, cast

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.core import Settings


class ModelConfigurationError(ValueError):
    """Raised when a chat model has not been fully configured."""


_GROQ_NON_TOOL_CALLING_MODELS = frozenset(
    {
        "meta-llama/llama-prompt-guard-2-22m",
        "meta-llama/llama-prompt-guard-2-86m",
    }
)


class ChatModelFactory:
    """Initialize and reuse the configured LangChain chat model."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model: BaseChatModel | None = None

    def get_model(self) -> BaseChatModel:
        """Return one provider-neutral chat model instance."""
        if self._model is not None:
            return self._model

        provider = (self._settings.model_provider or "").strip()
        model_name = (self._settings.model_name or "").strip()
        if not provider or not model_name:
            raise ModelConfigurationError(
                "MODEL_PROVIDER and MODEL_NAME must be configured"
            )

        if (
            provider.casefold() == "groq"
            and model_name.casefold() in _GROQ_NON_TOOL_CALLING_MODELS
        ):
            raise ModelConfigurationError(
                f"Groq model {model_name!r} is a content-moderation model and "
                "does not support the local tool calling required by ChatOps. "
                "Configure a Groq model with the Tool Use capability."
            )

        model_options: dict[str, Any] = {}
        model_options["timeout"] = self._settings.model_timeout_seconds
        model_options["max_retries"] = self._settings.model_max_retries

        if self._settings.model_api_key is not None:
            model_options["api_key"] = self._settings.model_api_key.get_secret_value()

        if provider.casefold() == "groq" and model_name.casefold().startswith("qwen/"):
            model_options["reasoning_effort"] = "none"
            model_options["reasoning_format"] = "hidden"

        self._model = cast(
            BaseChatModel,
            init_chat_model(
                model=model_name,
                model_provider=provider,
                **model_options,
            ),
        )
        return self._model
