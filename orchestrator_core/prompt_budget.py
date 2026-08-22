from dataclasses import dataclass
from pydantic import BaseModel, Field

class PromptBudget(BaseModel):
    max_input_tokens: int
    reserved_output_tokens: int
    used_tokens: int = 0
    def can_add(self, tokens: int) -> bool:
        return (self.used_tokens + tokens) <= (self.max_input_tokens - self.reserved_output_tokens)
    def add(self, tokens: int):
        self.used_tokens += tokens
    @property
    def remaining(self) -> int:
        return max(0, self.max_input_tokens - self.reserved_output_tokens - self.used_tokens)

def ensure_prompt_fits(prompt: str, budget: PromptBudget, label: str) -> None:
    estimated_tokens = len(prompt) // 4
    maximum = budget.max_input_tokens - budget.reserved_output_tokens
    if estimated_tokens > maximum:
        raise PreflightError(f"{label} excede PromptBudget: {estimated_tokens} > {maximum}")

def add_required_or_fail(budget: PromptBudget, text: str, label: str) -> None:
    tokens = len(text) // 4
    if not budget.can_add(tokens):
        raise PreflightError(f"{label} no cabe en PromptBudget.")
    budget.add(tokens)

class PromptPayload(BaseModel):
    content: str
    estimated_tokens: int
    omitted_files: list[str] = Field(default_factory=list)

class PreflightError(Exception):
    """Custom exception for failures during environment preflight checks."""

def fit_optional_text(
    budget: PromptBudget,
    text: str,
    truncation_marker: str = "\n... [TRUNCADO]",
) -> str:
    if not text:
        return ""
        
    text_tokens = len(text) // 4
    if budget.can_add(text_tokens):
        budget.add(text_tokens)
        return text
        
    marker_tokens = len(truncation_marker) // 4
    if budget.remaining < marker_tokens:
        return ""
        
    avail_tokens = budget.remaining - marker_tokens
    
    if avail_tokens <= 0:
        truncated_result = truncation_marker
    else:
        truncated_result = text[:avail_tokens * 4] + truncation_marker
        
    final_tokens = len(truncated_result) // 4
    if budget.can_add(final_tokens):
        budget.add(final_tokens)
        return truncated_result
        
    return ""

