import json
import logging
import os
from typing import Literal

from google.genai import types

from orchestrator_core.model_config import MODEL_LIGHT
from orchestrator_core.response_parsing import MD_FENCE, extract_code
from orchestrator_core.testing_policy import resolve_mocking_instruction
from orchestrator_core.runtime import RuntimeClients
from orchestrator_core.schemas import FileContract, RepositoryContext
from orchestrator_core.prompt_budget import (
    PromptBudget,
    add_required_or_fail,
    ensure_prompt_fits,
    fit_optional_text,
)
from orchestrator_core.prompt_context import PromptContextBuilder


def agent_implement_code(action: dict, file_contract: FileContract, design: dict, generated_so_far: dict[str, str], repo_context: RepositoryContext, runtime: RuntimeClients, context_manager: "RepositoryContextManager", feedback: str = "") -> str:
    logging.info(f"Procesando '{action['filepath']}' | Operacion: {action['operation']} con {MODEL_LIGHT}...")
    budget = PromptBudget(max_input_tokens=100000, reserved_output_tokens=8000)
    
    def build_final_prompt(fc, a, e, f, c, d):
        return f"""
    Actuas como un Software Engineer.
    
    Tus directrices y prioridades son claras:
    - El FileContract es OBLIGATORIO y prevalece frente a instrucciones inferiores.
    - Debes devolver el contenido COMPLETO final del archivo, sin explicaciones adicionales fuera del bloque de codigo.
    - Si la operacion es MODIFY, parte del codigo existente provisto y preserva todo el comportamiento no afectado por el cambio.
    
    FileContract: {fc}
    Action: {a}
    Codigo Actual: {e}
    Feedback: {f}
    Contexto Dinamico: {c}
    Dependencias y Generados: {d}
    """
    
    # Priority 1: Instrucciones fijas del agente / wrapper obligatorio
    wrapper_fixed_text = build_final_prompt("", "", "", "", "", "")
    add_required_or_fail(budget, wrapper_fixed_text, "Instrucciones fijas del Coder")
    
    # Priority 2: FileContract
    file_contract_json = file_contract.model_dump_json(indent=2)
    add_required_or_fail(budget, file_contract_json, "FileContract")
    
    # Priority 3: Action details
    action_str = f"filepath: {action.get('filepath')}\noperation: {action.get('operation')}\nsignatures: {action.get('signatures')}\ninstructions: {action.get('instructions')}"
    add_required_or_fail(budget, action_str, "Action details")
    
    # Priority 4: Existing code (if MODIFY)
    existing_code = ""
    filepath = action.get('filepath')
    if action.get('operation') == 'MODIFY':
        existing_code = context_manager.get_file_content(filepath)
        add_required_or_fail(budget, existing_code, "Existing code")
        
    # Priority 5: Feedback
    feedback = fit_optional_text(budget, feedback, "\n... [FEEDBACK TRUNCADO]")
    
    # Priority 6: Dynamic Context (from Architect)
    context_str = json.dumps(design.get('context', {}))
    context_str = fit_optional_text(budget, context_str, "\n... [CONTEXT TRUNCADO]")
        
    # Priority 7: Dependencies and Generated
    payload = PromptContextBuilder.build_for_coder(action, design, generated_so_far, repo_context, context_manager, budget)
    dep_gen_str = payload.content
    
    prompt = build_final_prompt(file_contract_json, action_str, existing_code, feedback, context_str, dep_gen_str)
    limit = budget.max_input_tokens - budget.reserved_output_tokens
    
    # Absorber redondeo de estimacion de manera determinista desde el prompt real
    while len(prompt) // 4 > limit:
        excess_tokens = (len(prompt) // 4) - limit
        trim_chars = excess_tokens * 4 + 4
        if len(dep_gen_str) > trim_chars:
            dep_gen_str = dep_gen_str[:-trim_chars]
        elif len(context_str) > trim_chars:
            context_str = context_str[:-trim_chars]
        elif len(feedback) > trim_chars:
            feedback = feedback[:-trim_chars]
        else:
            break
        prompt = build_final_prompt(file_contract_json, action_str, existing_code, feedback, context_str, dep_gen_str)
    
    ensure_prompt_fits(prompt, budget, "Coder")
    import os
    _, ext = os.path.splitext(action["filepath"])
    LANGUAGE_BY_EXTENSION = {
        ".py": "python", ".json": "json", ".ini": "ini",
        ".cfg": "ini", ".toml": "toml", ".yaml": "yaml",
        ".yml": "yaml", ".md": "markdown"
    }
    response = runtime.ai_client.models.generate_content(
        model=MODEL_LIGHT,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0,
        ),
    )
    
    return extract_code(response.text or "", LANGUAGE_BY_EXTENSION.get(ext))


def agent_generate_tests(action: dict, file_contract: FileContract, generated_so_far: dict[str, str], issue_desc: str, repo_context: RepositoryContext, framework: Literal["pytest", "unittest"], runtime: RuntimeClients, context_manager: "RepositoryContextManager", feedback: str = "") -> str:
    logging.info(f"Disenando suite de pruebas unitarias para '{action['filepath']}'...")

    budget = PromptBudget(max_input_tokens=128000, reserved_output_tokens=8192)

    # 6. PREPARAR DATOS MANDATORY
    file_contract_json = file_contract.model_dump_json(indent=2)
    mocking_instruction = resolve_mocking_instruction(framework, file_contract, repo_context)
    
    if repo_context.quality_policy.require_argument_annotations:
        typing_instruction = "2. TIPADO ESTRICTO OBLIGATORIO: Todas las funciones de test y los argumentos (incluyendo los mocks inyectados por `@patch`) deben tener type hints (ej. `def test_algo(mock_obj: Mock) -> None:`)."
    else:
        typing_instruction = "2. TIPADO FLEXIBLE: Respeta la convención de tipado existente en los tests (no exijas type hints si no son prevalentes)."

    if repo_context.quality_policy.require_explicit_exports or file_contract.required_exports:
        exports_instruction = "3. TESTEO EXHAUSTIVO DE INTERFACES PÚBLICAS: Es obligatorio importar, instanciar y usar explícitamente todas las clases o funciones declaradas en la variable '__all__' del archivo de producción objetivo para reducir la tasa de código muerto de Vulture a 0%."
    else:
        exports_instruction = "3. TESTEO ENFOCADO: Evalúa el contrato y los requerimientos sin obligatoriedad de referenciar __all__."

    # 7. MODIFY: EXISTING TEST CODE ES OBLIGATORIO
    existing_test_code = ""
    if action["operation"].upper() == "MODIFY":
        existing_test_code = context_manager.get_file_content(action["filepath"])

    # 5. SINGLE SOURCE OF TRUTH
    def build_final_prompt(context_text: str, feedback_section: str) -> str:
        return f"""
    Escribe una suite de pruebas unitarias exhaustiva con '{framework}' para validar el archivo: '{action['filepath']}'

    REQUISITOS ORIGINALES DEL ISSUE (FUENTE DE VERDAD SUPERIOR):
    {issue_desc}

    📜 CONTRATO DE ARCHIVO (REGLAS OBLIGATORIAS PARA ESTE ARCHIVO DE TEST):
    {file_contract_json}

    FIRMAS PROPUESTAS POR EL ARQUITECTO:
    {action.get("signatures", "")}

    INSTRUCCIONES ESPECÍFICAS DEL ARCHIVO:
    {action.get("instructions", "")}

    Las instrucciones del arquitecto están subordinadas al Issue original y al Contrato.
    Si existe una contradicción, prevalece el Contrato.

    CONTEXTO DINÁMICO RELEVANTE:
    {context_text}

    📜 ESTÁNDARES DE DISEÑO DE TESTING INDUSTRIAL:
    1. INDEPENDENCIA Y AISLAMIENTO: {mocking_instruction}
    {typing_instruction}
    {exports_instruction}

    {feedback_section}

    {f'''
    CÓDIGO DE TEST EXISTENTE (OPERACIÓN MODIFY):
    El siguiente código ya existe en el archivo. Debes preservarlo, corregirlo si el feedback lo indica, y añadir nuevas pruebas para los nuevos requisitos. No elimines pruebas existentes que no estén relacionadas con el feedback.
    ---
    {existing_test_code}
    ---
    ''' if existing_test_code else ''}

    Devuelve UNICAMENTE el codigo de '{framework}' en un bloque markdown usando {MD_FENCE}python.
    """

    # 8. RESERVA MANDATORY ÚNICA
    mandatory_prompt = build_final_prompt(context_text="", feedback_section="")
    add_required_or_fail(budget, mandatory_prompt, "Mandatory Test Generator prompt")

    # 9. FEEDBACK OPCIONAL
    raw_feedback_section = (
        "FEEDBACK DEL INTENTO ANTERIOR (DEBES CORREGIR ESTO):\n" + feedback
        if feedback else ""
    )
    feedback_section_final = fit_optional_text(budget, raw_feedback_section, "\n... [FEEDBACK TRUNCADO]")

    # 10. CONTEXTO DINÁMICO OPCIONAL
    payload = PromptContextBuilder.build_for_tests(action, generated_so_far, repo_context, context_manager, budget)
    contexto_dinamico = payload.content

    # 11. ORDEN EXACTO / 12. AJUSTE FINAL POR REDONDEO
    prompt = build_final_prompt(context_text=contexto_dinamico, feedback_section=feedback_section_final)
    limit = 119808
    
    excess_tokens = len(prompt) // 4 - limit
    while excess_tokens > 0:
        if len(contexto_dinamico) > 0:
            trim_chars = max(1, excess_tokens * 4)
            contexto_dinamico = contexto_dinamico[:-trim_chars]
        elif len(feedback_section_final) > 0:
            trim_chars = max(1, excess_tokens * 4)
            feedback_section_final = feedback_section_final[:-trim_chars]
        else:
            break
        
        prompt = build_final_prompt(context_text=contexto_dinamico, feedback_section=feedback_section_final)
        excess_tokens = len(prompt) // 4 - limit

    # 13. BARRERA FINAL
    ensure_prompt_fits(prompt, budget, "Test Generator")
    response = runtime.ai_client.models.generate_content(model=MODEL_LIGHT, contents=prompt, config=types.GenerateContentConfig(temperature=0.0))
    return extract_code(response.text, "python")

