import logging

from orchestrator_core.schemas import GateResult
from orchestrator_core.runtime import RuntimeClients
from orchestrator_core.prompt_budget import (
    PromptBudget,
    add_required_or_fail,
    fit_optional_text,
    ensure_prompt_fits,
)
from orchestrator_core.response_parsing import MD_FENCE
from orchestrator_core.model_config import MODEL_HEAVY

def agent_analyze_pipeline_failure(issue_id: int, title: str, description: str, design: dict, generated_files: dict[str, str], gate_results: list[GateResult], runtime: RuntimeClients, error_msg: str = "", pipeline_exc: Exception | None = None) -> str:
    logging.warning("El ciclo colapsó. Invocando Diagnóstico Clínico de IA...")
    budget = PromptBudget(max_input_tokens=100000, reserved_output_tokens=4000)

    # 5. CLASIFICACIÓN MANDATORY / OPTIONAL
    gobernanza = """
    Actúas como un Ingeniero Principal de DevOps y Experto en Diagnóstico de Agentes. El pipeline ha fallado durante su ejecución. Determina la fase real del fallo exclusivamente a partir de la excepción y los gates adjuntos. No asumas que se agotaron reintentos ni que se alcanzaron las fases de diseño o implementación.
    Realiza una autopsia técnica y emite un reporte Markdown detallado sobre qué causó el bloqueo.

    Se preservarán siempre las secciones:
    - FALLO OBSERVADO
    - RIESGO INFERIDO
    - RECOMENDACIÓN PREVENTIVA

    DISTINCIÓN DE FALLO CRÍTICO:
    - TECHNICAL/ORCHESTRATOR FAILURE: Si el pipeline colapsó por errores de Python, sintaxis, API, o herramientas (ej. "ValueError"). Esto NUNCA debe delegarse al PO. Recomienda acciones para el ingeniero.
    - PRODUCT/ISSUE AMBIGUITY: Si la implementación falló por ambigüedad funcional o diseño insalvable (después de haber generado código o diseño válido).

    🚨 INSTRUCCIÓN CRÍTICA DE DELEGACIÓN 🚨:
    - DEBE INCLUIR obligatoriamente la etiqueta exacta `[ACTION: DELEGATE_TO_PO]` en una línea independiente al final de tu reporte SOLO SI la evidencia demuestra que el Issue o los requisitos del producto contienen una ambigüedad material, contradicción, falta de decisión de negocio o defecto de requisitos que requiere juicio humano del Product Owner.
    - Los defectos, inconsistencias, reglas no soportadas o fallos de síntesis del AcceptanceContract generado son fallos de contexto u orquestación del Orchestrator y NO deben desencadenar la delegación al PO, a menos que la causa subyacente sea un defecto o decisión no resuelta demostrable en el propio Issue.
    - La simple necesidad de regenerar o corregir el AcceptanceContract NO DEBE activar la delegación al PO. Fallos puramente técnicos también deben omitir esta etiqueta.
    """

    issue_ctx = f"Issue #{issue_id}: '{title}' | Spec: {description}"

    failed_gates = [g for g in gate_results if not g.passed]
    failed_summaries = "\n".join([f"- Gate Fallido: {g.name}" for g in failed_gates])

    # 7. SINGLE SOURCE OF TRUTH DEL PROMPT
    def build_final_prompt(failed_outputs_text: str, related_files_text: str, other_files_text: str, passed_gates_text: str) -> str:
        return f"""
    {gobernanza}

    Contexto: {issue_ctx}

    EXCEPCIÓN CATASTRÓFICA (Si la hay):
    Mensaje: {error_msg}
    Tipo: {type(pipeline_exc).__name__ if pipeline_exc else "N/A"}


    GATES FALLIDOS (CAUSA DEL BLOQUEO):
    {failed_summaries}
    {failed_outputs_text}

    CÓDIGO GENERADO RELACIONADO:
    {related_files_text}

    RESTO DEL CÓDIGO GENERADO:
    {other_files_text}

    GATES EXITOSOS (CONTEXTO):
    {passed_gates_text}
    """

    # 8. RESERVA MANDATORY EXACTA
    mandatory_prompt = build_final_prompt(failed_outputs_text="", related_files_text="", other_files_text="", passed_gates_text="")
    add_required_or_fail(budget, mandatory_prompt, "Mandatory Post-Mortem prompt")

    # 5. RAW EVIDENCE ES LA ÚNICA FUENTE DE CLASIFICACIÓN
    raw_failed_outputs = ""
    for g in failed_gates:
        raw_failed_outputs += f"\n[Output de {g.name}]\n{g.output}\n"

    related_files = []
    other_files = []
    for path in generated_files:
        if path in raw_failed_outputs:
            related_files.append(path)
        else:
            other_files.append(path)

    # 6. PRESERVAR UN MANIFIESTO COMPACTO DE CLASIFICACIÓN
    related_paths_raw = "\n".join([f"- `{path}`" for path in related_files])
    other_paths_raw = "\n".join([f"- `{path}`" for path in other_files])

    related_paths_str = fit_optional_text(budget, related_paths_raw, "\n... [TRUNCADO PATHS RELACIONADOS]")
    other_paths_str = fit_optional_text(budget, other_paths_raw, "\n... [TRUNCADO PATHS ADICIONALES]")

    # 7. FAILED OUTPUT SIGUE SIENDO EVIDENCIA DE ALTA PRIORIDAD
    failed_outputs = fit_optional_text(budget, raw_failed_outputs, "\n... [TRUNCADO OUTPUT]")

    # 9. RELATED CODE SIGUE SIENDO OPTIONAL
    rel_code_str = ""
    for path in related_files:
        code = generated_files[path]
        frag = f"\n### Archivo Relacionado: `{path}`\n{MD_FENCE}python\n{code}\n{MD_FENCE}\n"
        bounded_frag = fit_optional_text(budget, frag, f"\n{MD_FENCE}\n... [TRUNCADO ARCHIVO]")
        if bounded_frag:
            rel_code_str += bounded_frag

    # 10. OTHER CODE SIGUE SIENDO OPTIONAL
    oth_code_str = ""
    for path in other_files:
        code = generated_files[path]
        frag = f"\n### Archivo Adicional: `{path}`\n{MD_FENCE}python\n{code}\n{MD_FENCE}\n"
        bounded_frag = fit_optional_text(budget, frag, f"\n{MD_FENCE}\n... [TRUNCADO ARCHIVO]")
        if bounded_frag:
            oth_code_str += bounded_frag

    # 14. PASSED GATES SON ÚLTIMA PRIORIDAD
    passed_gates = [g for g in gate_results if g.passed]
    passed_gates_raw = "\n".join([f"- Gate Exitoso: {g.name}" for g in passed_gates])
    passed_gates_str = fit_optional_text(budget, passed_gates_raw, "\n... [TRUNCADO]")

    # 11. COMPOSICIÓN DE LAS SECCIONES
    rel_files_str = related_paths_str + rel_code_str
    oth_files_str = other_paths_str + oth_code_str

    prompt = build_final_prompt(failed_outputs, rel_files_str, oth_files_str, passed_gates_str)

    # 12. ROUNDING LOOP
    limit = budget.max_input_tokens - budget.reserved_output_tokens
    excess_tokens = len(prompt) // 4 - limit
    while excess_tokens > 0:
        if len(passed_gates_str) > 0:
            trim_chars = max(1, excess_tokens * 4)
            passed_gates_str = passed_gates_str[:-trim_chars]
        elif len(oth_code_str) > 0:
            trim_chars = max(1, excess_tokens * 4)
            oth_code_str = oth_code_str[:-trim_chars]
        elif len(rel_code_str) > 0:
            trim_chars = max(1, excess_tokens * 4)
            rel_code_str = rel_code_str[:-trim_chars]
        elif len(failed_outputs) > 0:
            trim_chars = max(1, excess_tokens * 4)
            failed_outputs = failed_outputs[:-trim_chars]
        elif len(other_paths_str) > 0:
            trim_chars = max(1, excess_tokens * 4)
            other_paths_str = other_paths_str[:-trim_chars]
        elif len(related_paths_str) > 0:
            trim_chars = max(1, excess_tokens * 4)
            related_paths_str = related_paths_str[:-trim_chars]
        else:
            break

        rel_files_str = related_paths_str + rel_code_str
        oth_files_str = other_paths_str + oth_code_str
        prompt = build_final_prompt(failed_outputs, rel_files_str, oth_files_str, passed_gates_str)
        excess_tokens = len(prompt) // 4 - limit

    # 17. BARRERA FINAL
    try:
        ensure_prompt_fits(prompt, budget, "Post-Mortem")
        response = runtime.ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt)
        logging.error(f"REPORTE DE AUTODIAGNÓSTICO POST-MORTEM:\n{(response.text or "").strip()}")
        return (response.text or "").strip()
    except Exception as e: return f"Error de diagnostico: {e}"
