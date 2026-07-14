"""Provider-neutral LangChain chat model factory."""

from typing import Any, cast

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.core import Settings


class ModelConfigurationError(ValueError):
    """Raised when a chat model has not been fully configured."""


class ChatModelFactory:
    """Initialize and reuse the configured LangChain chat model."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model: BaseChatModel | None = None

    def get_model(self) -> BaseChatModel:
        """Return one provider-neutral chat model instance."""
        if self._model is not None:
            return self._model

        if not self._settings.model_provider or not self._settings.model_name:
            raise ModelConfigurationError(
                "MODEL_PROVIDER and MODEL_NAME must be configured"
            )

        model_options: dict[str, Any] = {}
        model_options["timeout"] = self._settings.model_timeout_seconds
        model_options["max_retries"] = self._settings.model_max_retries

        if self._settings.model_api_key is not None:
            model_options["api_key"] = (
                self._settings.model_api_key.get_secret_value()
            )

        self._model = cast(
            BaseChatModel,
            init_chat_model(
                model=self._settings.model_name,
                model_provider=self._settings.model_provider,
                **model_options,
            ),
        )
        return self._model
