import os
import logging
from orchestrator_core.prompt_budget import ensure_prompt_fits, PromptBudget, PreflightError, add_required_or_fail, fit_optional_text
from orchestrator_core.response_parsing import extract_code, MD_FENCE
from orchestrator_core.prompt_context import PromptContextBuilder
from orchestrator_core.runtime import RuntimeClients
from orchestrator_core.model_config import MODEL_LIGHT, MODEL_HEAVY
from orchestrator_core.schemas import GateResult
from google.genai import types

def agent_update_architecture_doc(
    issue_id: int,
    title: str,
    description: str,
    design: dict,
    generated_files: dict[str, str],
    current_arch_doc: str,
    gate_results: list[GateResult],
    git_diff: str,
    runtime: RuntimeClients,
) -> str:
    """Actualiza ARCHITECTURE.md con evidencia real: diff, gates, manifiesto."""
    logging.info("Sincronizando evolucion del manual de arquitectura con evidencia real...")
    arch_file = "docs/ARCHITECTURE.md"

    # ---- PromptBudget con prioridades explicitas ----
    MAX_INPUT = 80000
    RESERVED_OUTPUT = 8192
    budget = PromptBudget(max_input_tokens=MAX_INPUT, reserved_output_tokens=RESERVED_OUTPUT)
    
    # Priority 1: Fixed Instructions
    fixed_instructions = """
    Actuas como un Arquitecto de Soluciones que mantiene el documento 'docs/ARCHITECTURE.md' actualizado.
    Tu tarea es actualizar el documento basandote en la evidencia real de los cambios, no solo en la intencion del diseno.
    INSTRUCCIONES:
    1.  **Actualiza con Evidencia**: Tu principal fuente de verdad es el 'DIFF REAL'. Usalo para entender que interfaces, dependencias y logicas cambiaron realmente.
    2.  **Manten la Estructura**: El documento DEBE seguir esta estructura de 9 secciones.
        1.  `# 1. Vision General del Sistema`
        2.  `# 2. Catalogo de Componentes`
        3.  `# 3. Interfaces Publicas y Contratos`
        4.  `# 4. Flujos de Datos`
        5.  `# 5. Dependencias Externas`
        6.  `# 6. Convenciones de Calidad y Pruebas`
        7.  `# 7. Restricciones Actuales`
        8.  `# 8. Registro de Decisiones de Arquitectura (ADR)`: Crea un nuevo ADR para esta ejecucion.
        9.  `# 9. Historial de Cambios por Issue`: Anade una entrada concisa.
    Devuelve UNICAMENTE el Markdown definitivo.
    """
    try:
        add_required_or_fail(budget, fixed_instructions, "Instrucciones fijas en Architecture Updater")
    except PreflightError as e:
        logging.error(f"Fallo en agente arquitectura: {e}")
        raise

    # Priority 2: Issue metadata obligatorio
    meta = f"Issue: #{issue_id} - {title}\nDescripcion: {description}"
    try:
        add_required_or_fail(budget, meta, "Issue en Architecture Updater")
    except PreflightError as e:
        logging.error(f"Fallo en agente arquitectura: {e}")
        raise

    # Priority 3: Git Diff
    git_diff_text = git_diff or "[Sin diff disponible]"
    diff_toks = len(git_diff_text) // 4
    if not budget.can_add(diff_toks):
        trunc_msg = "\n... [DIFF TRUNCADO]"
        avail = max(0, budget.remaining * 4 - len(trunc_msg) * 4)
        git_diff_text = git_diff_text[:avail] + trunc_msg
        logging.warning("git_diff truncado en Architecture Updater")
        if git_diff_text: budget.add(len(git_diff_text) // 4)
    else:
        budget.add(diff_toks)

    # Priority 4: Manifest
    manifest_text = repr(list(generated_files.keys()))
    if not budget.can_add(len(manifest_text) // 4):
        manifest_text = "[Manifiesto omitido]"
    else:
        budget.add(len(manifest_text) // 4)
        
    # Priority 5: Gate Summary
    gate_summary = repr([{"name": g.name, "passed": g.passed, "executed": g.executed} for g in gate_results])
    if not budget.can_add(len(gate_summary) // 4):
        gate_summary = "[Gate summary omitido]"
    else:
        budget.add(len(gate_summary) // 4)

    # Priority 6: Current Architecture
    arch_display = current_arch_doc or "[El documento esta vacio. Debes crearlo desde cero.]"
    arch_toks = len(arch_display) // 4
    if not budget.can_add(arch_toks):
        trunc_msg = "\n... [ARQUITECTURA TRUNCADA]"
        avail = max(0, budget.remaining * 4 - len(trunc_msg) * 4)
        arch_display = arch_display[:avail] + trunc_msg
        if arch_display: budget.add(len(arch_display) // 4)
    else:
        budget.add(arch_toks)

    # Priority 7: Architecture Justification
    arch_just = design.get("architecture_justification", "[no disponible]")
    if not budget.can_add(len(arch_just) // 4):
        arch_just = "[Justificacion omitida]"
    else:
        budget.add(len(arch_just) // 4)

    prompt = f"""
    {fixed_instructions}

    EVIDENCIA DE CAMBIOS REALIZADOS EN ESTA EJECUCION:
    - {meta}
    - Justificacion de Arquitectura (Intencion Original): {arch_just}
    - Manifiesto Final de Archivos (Creados/Modificados): {manifest_text}
    - Resumen de Quality Gates (solo paso/fallo):
    {gate_summary}

    DIFF REAL DE LOS CAMBIOS (fuente de verdad principal):
    ---
    {git_diff_text}
    ---

    DOCUMENTO DE ARQUITECTURA ACTUAL:
    ---
    {arch_display}
    ---
    """
    
    try:
        ensure_prompt_fits(prompt, budget, "Architecture Updater")
        response = runtime.ai_client.models.generate_content(
            model=MODEL_HEAVY,
            contents=prompt,
        )
        updated_doc = extract_code(response.text or "", "markdown")
        if not updated_doc:
            updated_doc = (response.text or "").strip()
        
        # Write to file
        full_path = arch_file
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(updated_doc)
            
        logging.info(f"Documento de arquitectura actualizado y guardado en {arch_file}.")
        return arch_file
    except Exception as e:
        logging.error(f"Fallo al invocar agente de arquitectura: {e}")
        raise PreflightError(f"Error generando documento de arquitectura: {e}")

def agent_update_user_manual(issue_id: int, title: str, description: str, design: dict, generated_files: dict[str, str], runtime: RuntimeClients) -> str:
    logging.info(f"Evaluando impacto operativo del Issue #{issue_id} en el Manual de Usuario...")
    manual_path = "docs/USER_MANUAL.md"
    existing_content = open(manual_path, "r", encoding="utf-8").read() if os.path.exists(manual_path) else "[Vacio]"
    budget = PromptBudget(max_input_tokens=100000, reserved_output_tokens=8000)
    
    try:
        # Priority 1: Issue
        add_required_or_fail(budget, title, "Issue title en User Manual")
        
        # Priority 2: description
        add_required_or_fail(budget, description, "Issue desc en User Manual")
        
        # Priority 3: fixed instructions
        fixed_instructions = "Actúas como Technical Writer. Tu tarea es analizar los cambios generados y decidir si impactan la operatividad del usuario final. Si no hay impacto (ej. refactor interno, test), devuelve exactamente el mismo contenido original. Si hay impacto, actualiza el manual de forma incremental, explicando las nuevas funciones sin jerga de implementación. Devuelve el Markdown final completo."
        add_required_or_fail(budget, fixed_instructions, "Instrucciones fijas en User Manual")
        
        # Priority 4: existing manual
        add_required_or_fail(budget, existing_content, "Existing manual")
        
        # Priority 5: cambios generados
        payload = PromptContextBuilder.build_for_docs(design, generated_files, budget)
        cambios_str = payload.content
        
        prompt = f"""
        {fixed_instructions}
        
        ISSUE:
        {title}
        {description}
        
        MANUAL ACTUAL:
        {existing_content}
        
        CAMBIOS GENERADOS:
        {cambios_str}
        
        Devuelve UNICAMENTE el contenido actualizado en Markdown.
        """
        
        ensure_prompt_fits(prompt, budget, "User Manual")
    except PreflightError as e:
        logging.warning(f"User manual omitido por presupuesto: {e}")
        return manual_path
    response = runtime.ai_client.models.generate_content(
        model=MODEL_HEAVY, contents=prompt,
        config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=1024), temperature=0.2)
    )
    clean_text = (response.text or "").strip()
    if clean_text.startswith(f"{MD_FENCE}markdown"): clean_text = clean_text[11:]
    if clean_text.endswith(MD_FENCE): clean_text = clean_text[:-3]
    os.makedirs("docs", exist_ok=True)
    with open(manual_path, "w", encoding="utf-8") as f: f.write(clean_text.strip())
    return manual_path

def agent_generate_execution_report(design: dict, generated_files: dict[str, str], pytest_log: str, sast_report: str, issue_id: int, title: str, runtime: RuntimeClients) -> str:
    logging.info(f"Compilando reporte de ejecucion para Issue #{issue_id}...")
    budget = PromptBudget(max_input_tokens=100000, reserved_output_tokens=4000)

    # 4. MANDATORY
    architecture_justification = design.get("architecture_justification", "[no disponible]")
    manifest_str = str(list(generated_files.keys()))
    fixed_instructions = "Actúas como un ingeniero de release. Genera un reporte Markdown detallado del ciclo de ejecución. Incluye el título, la justificación de la arquitectura, resumen de dependencias/archivos modificados, resumen de calidad estática, y análisis de fallos en tests si los hay."

    # 6. SINGLE SOURCE OF TRUTH
    def build_final_prompt(content_text: str, failures_text: str, traceback_text: str, sast_text: str, tail_text: str) -> str:
        return f"""
    {fixed_instructions}
    
    Title/Issue: {title}
    Architecture Justification: {architecture_justification}
    Generated Files Manifest: {manifest_str}
    
    Content of generated files:
    {content_text}
    
    Test Failures/Errors:
    {failures_text}
    
    Relevant Tracebacks:
    {traceback_text}
    
    SAST:
    {sast_text}
    
    Test Tail Logs:
    {tail_text}
    """

    # 7. RESERVAR MANDATORY PRIMERO
    mandatory_prompt = build_final_prompt(content_text="", failures_text="", traceback_text="", sast_text="", tail_text="")
    add_required_or_fail(budget, mandatory_prompt, "Mandatory Execution Report prompt")

    # 9. GENERATED FILE EVIDENCE
    payload = PromptContextBuilder.build_for_report(generated_files, budget)
    content_str = payload.content

    # 10. FAILED / ERROR
    lines = pytest_log.split('\n')
    important_failures = [l for l in lines if 'FAILED' in l or 'ERROR' in l]
    failures_str = "\n".join(important_failures) if important_failures else ""
    failures_str = fit_optional_text(budget, failures_str, "\n... [TRUNCADO FALLOS]")

    # 11. TRACEBACKS
    important_tracebacks = [l for l in lines if 'Traceback' in l]
    tb_str = "\n".join(important_tracebacks) if important_tracebacks else ""
    tb_str = fit_optional_text(budget, tb_str, "\n... [TRUNCADO TRACEBACKS]")

    # 12. SAST ES OPTIONAL Y BOUNDED
    sast_text = fit_optional_text(budget, sast_report, "\n... [SAST TRUNCADO]")

    # 13. PYTEST TAIL ES ÚLTIMA PRIORIDAD
    resto_logs = "\n".join(lines[-50:]) if lines else ""
    tail_text = fit_optional_text(budget, resto_logs, "\n... [TAIL TRUNCADO]")

    # 14. ENSAMBLAJE FINAL
    prompt = build_final_prompt(content_str, failures_str, tb_str, sast_text, tail_text)

    # 15. AJUSTE DE REDONDEO
    limit = 96000
    excess_tokens = len(prompt) // 4 - limit
    while excess_tokens > 0:
        if len(tail_text) > 0:
            trim_chars = max(1, excess_tokens * 4)
            tail_text = tail_text[:-trim_chars]
        elif len(sast_text) > 0:
            trim_chars = max(1, excess_tokens * 4)
            sast_text = sast_text[:-trim_chars]
        elif len(tb_str) > 0:
            trim_chars = max(1, excess_tokens * 4)
            tb_str = tb_str[:-trim_chars]
        elif len(failures_str) > 0:
            trim_chars = max(1, excess_tokens * 4)
            failures_str = failures_str[:-trim_chars]
        elif len(content_str) > 0:
            trim_chars = max(1, excess_tokens * 4)
            content_str = content_str[:-trim_chars]
        else:
            break
        prompt = build_final_prompt(content_str, failures_str, tb_str, sast_text, tail_text)
        excess_tokens = len(prompt) // 4 - limit

    # 16. BARRERA FINAL
    ensure_prompt_fits(prompt, budget, "Execution Report")
    
    # 17. OUTPUT Y FILESYSTEM
    response = runtime.ai_client.models.generate_content(model=MODEL_LIGHT, contents=prompt)
    os.makedirs("docs/reports", exist_ok=True)
    report_path = f"docs/reports/run_issue_{issue_id}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write((response.text or "").strip())
    logging.info(f"Reporte guardado en '{report_path}'")
    return report_path
