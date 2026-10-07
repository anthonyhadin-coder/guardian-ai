from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from pydantic import BaseModel

class LLMResponse(BaseModel):
    content: str
    model: str
    tokens_used: int = 0
    raw: Optional[Dict[str, Any]] = None

class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.2) -> LLMResponse:
        """Synchronous text generation"""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        pass
