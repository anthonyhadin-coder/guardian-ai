from __future__ import annotations
import re
from typing import List, Tuple

# Patterns identifying sensitive tokens and keys
SECRET_PATTERNS = [
    (r"sk-[a-zA-Z0-9]{20,}", "[REDACTED_OPENAI_KEY]"),
    (r"AIza[0-9A-Za-z-_]{35}", "[REDACTED_GEMINI_KEY]"),
    (r"gh[pous]_[a-zA-Z0-9]{36,}", "[REDACTED_GITHUB_TOKEN]"),
    (r"-----BEGIN (?:RSA )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA )?PRIVATE KEY-----", "[REDACTED_PRIVATE_KEY]"),
    (r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key)\s*[:=]\s*['\"][a-zA-Z0-9_\-\.\/]{8,}['\"]", "[REDACTED_CREDENTIAL]"),
    (r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{4,}['\"]", "password=\"[REDACTED_PASSWORD]\"")
]

PROMPT_INJECTION_PATTERNS = [
    r"(?i)ignore\s+(?:all\s+)?previous\s+instructions",
    r"(?i)disregard\s+(?:all\s+)?prior\s+instructions",
    r"(?i)system\s*:\s*override",
    r"(?i)you\s+are\s+now\s+in\s+developer\s+mode",
    r"(?i)print\s+(?:all\s+)?(?:env|environment)\s+variables",
    r"(?i)delete\s+(?:all\s+)?files",
    r"(?i)reveal\s+(?:your\s+)?system\s+prompt"
]

DESTRUCTIVE_COMMAND_PATTERNS = [
    r"rm\s+-rf\s+(?:/|~|\.\.)",
    r"mkfs",
    r">\s*/dev/sd[a-z]",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",  # fork bomb
    r"chmod\s+-R\s+777\s+/",
    r"wget\s+.*\|\s*sh",
    r"curl\s+.*\|\s*sh",
    r"curl\s+.*\|\s*bash"
]

class SecurityGuard:
    @staticmethod
    def redact_secrets(text: str) -> str:
        """Redacts sensitive credentials, tokens, and keys from any text."""
        if not text:
            return ""
        sanitized = text
        for pattern, replacement in SECRET_PATTERNS:
            sanitized = re.sub(pattern, replacement, sanitized)
        return sanitized

    @staticmethod
    def sanitize_untrusted_context(text: str) -> Tuple[str, List[str]]:
        """Neutralizes prompt injection attempts found inside repository code, READMEs, or comments."""
        if not text:
            return "", []

        warnings = []
        sanitized = text

        for pattern in PROMPT_INJECTION_PATTERNS:
            matches = re.findall(pattern, sanitized)
            if matches:
                warnings.append(f"Prompt injection pattern detected and defused: '{matches[0]}'")
                sanitized = re.sub(pattern, "[DEFUSED_PROMPT_INJECTION_ATTEMPT]", sanitized)

        # Redact secrets from repo context as well
        sanitized = SecurityGuard.redact_secrets(sanitized)
        return sanitized, warnings

    @staticmethod
    def is_safe_command(command: str) -> Tuple[bool, str]:
        """Checks if shell command contains destructive or unauthorized operations."""
        for pattern in DESTRUCTIVE_COMMAND_PATTERNS:
            if re.search(pattern, command):
                return False, f"Destructive command pattern detected: {pattern}"
        return True, "Command is safe"
