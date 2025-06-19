"""Lightning LLM module - Model registry and completions API."""

from .api import CompletionsAPI, get_completions_api
from ..abstractions.llm import Message, MessageRole, CompletionResponse, StreamResponse
from ..vextir_os.registries import ModelSpec, get_model_registry

__all__ = [
    "CompletionsAPI",
    "get_completions_api", 
    "Message",
    "MessageRole",
    "CompletionResponse",
    "StreamResponse",
    "ModelSpec",
    "get_model_registry",
]