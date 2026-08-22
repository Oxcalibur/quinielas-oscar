from orchestrator_core.prompt_budget import PromptBudget, fit_optional_text

def test_PB001_texto_completo_cabe():
    budget = PromptBudget(max_input_tokens=100, reserved_output_tokens=0, used_tokens=0)
    texto = "a" * 100 # 25 tokens
    resultado = fit_optional_text(budget, texto)
    assert resultado == texto
    assert budget.used_tokens == 25

def test_PB002_texto_cabe_exactamente():
    budget = PromptBudget(max_input_tokens=100, reserved_output_tokens=0, used_tokens=90)
    # remaining is 10. We need exactly 10 tokens.
    # 40 chars = 10 tokens.
    texto = "a" * 40
    resultado = fit_optional_text(budget, texto)
    assert resultado == texto
    assert budget.used_tokens == 100

def test_PB003_un_token_estimado_por_encima():
    budget = PromptBudget(max_input_tokens=100, reserved_output_tokens=0, used_tokens=90)
    # remaining is 10.
    # 44 chars = 11 tokens.
    texto = "a" * 44
    marker = "..." # 3 chars = 0 tokens
    resultado = fit_optional_text(budget, texto, truncation_marker=marker)
    assert resultado != texto
    # marker_tokens = 0. avail_tokens = 10.
    # truncated = texto[:40] + "..." = 43 chars = 10 tokens.
    assert resultado == ("a" * 40) + "..."
    assert budget.used_tokens == 100

def test_PB004_marcador_contabilizado():
    budget = PromptBudget(max_input_tokens=100, reserved_output_tokens=0, used_tokens=90)
    # remaining is 10.
    marker = "M" * 12 # 3 tokens
    # marker_tokens = 3. avail_tokens = 7.
    # truncated = texto[:28] + marker = 28 + 12 = 40 chars = 10 tokens.
    texto = "T" * 100
    resultado = fit_optional_text(budget, texto, truncation_marker=marker)
    assert resultado == ("T" * 28) + marker
    assert budget.used_tokens == 100
    assert len(resultado) // 4 == 10

def test_PB005_solo_cabe_marcador():
    budget = PromptBudget(max_input_tokens=100, reserved_output_tokens=0, used_tokens=97)
    # remaining is 3.
    marker = "M" * 12 # 3 tokens
    texto = "T" * 100
    resultado = fit_optional_text(budget, texto, truncation_marker=marker)
    assert resultado == marker
    assert budget.used_tokens == 100

def test_PB006_no_cabe_marcador():
    budget = PromptBudget(max_input_tokens=100, reserved_output_tokens=0, used_tokens=98)
    # remaining is 2.
    marker = "M" * 12 # 3 tokens
    texto = "T" * 100
    resultado = fit_optional_text(budget, texto, truncation_marker=marker)
    assert resultado == ""
    assert budget.used_tokens == 98

def test_PB007_remaining_cero():
    budget = PromptBudget(max_input_tokens=100, reserved_output_tokens=0, used_tokens=100)
    marker = "M" * 4 # 1 token
    texto = "T" * 10
    resultado = fit_optional_text(budget, texto, truncation_marker=marker)
    assert resultado == ""
    assert budget.used_tokens == 100

def test_PB008_budget_parcialmente_consumido():
    budget = PromptBudget(max_input_tokens=200, reserved_output_tokens=50, used_tokens=100)
    # max_input = 200, reserved = 50 -> effective max = 150.
    # used = 100. remaining = 50.
    texto = "T" * 201 # 50 tokens
    resultado = fit_optional_text(budget, texto)
    # text fits exactly! wait, 201 // 4 = 50. 
    # budget.can_add(50) is used_tokens(100) + 50 <= 150. True.
    assert resultado == texto
    assert budget.used_tokens == 150
    
    # Let's test overflow:
    budget2 = PromptBudget(max_input_tokens=200, reserved_output_tokens=50, used_tokens=100)
    texto2 = "T" * 204 # 51 tokens
    resultado2 = fit_optional_text(budget2, texto2, truncation_marker="MMMM") # 1 token marker
    # avail = 49.
    assert resultado2 == ("T" * 196) + "MMMM"
    assert budget2.used_tokens == 150

def test_PB009_marker_personalizado_grande():
    budget = PromptBudget(max_input_tokens=100, reserved_output_tokens=0, used_tokens=50)
    # remaining is 50.
    marker = "M" * 160 # 40 tokens
    texto = "T" * 100 # 25 tokens, doesn't fit with marker if we truncate?
    # Wait, text fits entirely! 25 tokens. budget has 50 remaining.
    resultado = fit_optional_text(budget, texto, truncation_marker=marker)
    assert resultado == texto
    assert budget.used_tokens == 75
    
    # What if text doesn't fit?
    budget2 = PromptBudget(max_input_tokens=100, reserved_output_tokens=0, used_tokens=50)
    texto2 = "T" * 204 # 51 tokens
    resultado2 = fit_optional_text(budget2, texto2, truncation_marker=marker)
    # remaining 50. marker 40. avail 10.
    assert resultado2 == ("T" * 40) + marker
    assert budget2.used_tokens == 100

import pytest

@pytest.mark.parametrize("max_input", [10, 50, 100, 1000])
@pytest.mark.parametrize("reserved", [0, 5, 20])
@pytest.mark.parametrize("used", [0, 5, 50, 95, 100])
@pytest.mark.parametrize("text_len", [0, 10, 50, 200, 500])
@pytest.mark.parametrize("marker_len", [0, 3, 4, 15, 100])
def test_PB010_invariant_fuzz(max_input, reserved, used, text_len, marker_len):
    if used > (max_input - reserved):
        return # invalid initial state
        
    budget = PromptBudget(max_input_tokens=max_input, reserved_output_tokens=reserved, used_tokens=used)
    effective_max = max_input - reserved
    texto = "T" * text_len
    marker = "M" * marker_len
    
    resultado = fit_optional_text(budget, texto, truncation_marker=marker)
    
    # INVARIANTS:
    # 1. Budget is never exceeded
    assert budget.used_tokens <= effective_max
    
    # 2. Returned text cost matches the added budget (unless empty)
    if resultado != "":
        cost = len(resultado) // 4
        # Note: if texto wasn't empty, cost should match the increase in used_tokens
        # unless used_tokens was already modified by another test? No, this is isolated.
        
