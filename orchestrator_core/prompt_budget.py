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

def build_budget_safe_authoritative_evidence(auth_docs: dict[str, str], issue_desc: str, budget: PromptBudget, label: str = "Contexto", resolved_refs: list[str] = None) -> str:
    if not auth_docs:
        return ""

    if resolved_refs is None:
        resolved_refs = []

    total_tokens = sum(len(content) // 4 for content in auth_docs.values())
    headers = [f"=== INICIO AUTORITATIVO {df} ===\n" for df in auth_docs.keys()]
    footers = [f"\n=== FIN AUTORITATIVO {df} ===" for df in auth_docs.keys()]
    overhead_tokens = sum(len(h) // 4 + len(f) // 4 for h, f in zip(headers, footers))

    if budget.can_add(total_tokens + overhead_tokens):
        budget.add(total_tokens + overhead_tokens)
        result = []
        for df, content in auth_docs.items():
            result.append(f"=== INICIO AUTORITATIVO {df} ===\n{content}\n=== FIN AUTORITATIVO {df} ===")
        return "\n\n".join(result)

    result = []
    for df, content in auth_docs.items():
        header = f"=== EXTRACTO {df} ==="
        footer = f"=== FIN EXTRACTO {df} ==="

        doc_refs = [ref for ref in resolved_refs if ref.lower() in content.lower()]

        extracted = []
        lines = content.splitlines()
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if any(ref.lower() in line_lower for ref in doc_refs):
                start = max(0, i - 15)
                end = min(len(lines), i + 15)
                extracted.append("\n".join(lines[start:end]))

        extracted_content = "\n...\n".join(extracted)

        result.append(f"{header}\n{extracted_content}\n{footer}")

    final_str = "\n\n".join(result)
    final_tokens = len(final_str) // 4
    if not budget.can_add(final_tokens):
        raise PreflightError(f"{label} evidencias exceden PromptBudget incluso en modo extracto.")

    final_str_lower = final_str.lower()
    for ref in resolved_refs:
        if ref.lower() not in final_str_lower:
            raise PreflightError(f"No se pudo preservar la referencia requerida '{ref}' en el modo extracto para {label}.")

    budget.add(final_tokens)
    return final_str

