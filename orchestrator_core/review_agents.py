import re
import json
import logging
from orchestrator_core.prompt_budget import ensure_prompt_fits, PromptBudget, PreflightError, add_required_or_fail
from orchestrator_core.response_parsing import extract_code, MD_FENCE
from orchestrator_core.prompt_context import PromptContextBuilder
from orchestrator_core.runtime import RuntimeClients
from orchestrator_core.model_config import MODEL_LIGHT, MODEL_HEAVY
from orchestrator_core.schemas import AcceptanceContract, CodeReviewResult, ReviewFinding, RepositoryContext, SecurityAuditResult
from orchestrator_core.import_graph import extract_imported_modules, resolve_imported_files
from orchestrator_core.ast_utils import extract_ast_signatures
from google.genai import types

def summarize_dependency_file(filename: str, content: str) -> dict:
    import re
    if "poetry.lock" in filename or "Pipfile.lock" in filename:
        # Extract basic package names without all details to save tokens
        packages = re.findall(r'\[\[package\]\]\s+name\s*=\s*"([^"]+)"\s+version\s*=\s*"([^"]+)"', content)
        if not packages:
            packages = re.findall(r'name\s*=\s*"([^"]+)"', content) # fallback
        return {"type": "lockfile", "packages": packages[:100]} # limit to 100
    elif "requirements" in filename and filename.endswith(".txt"):
        lines = [l.strip() for l in content.split('\n') if l.strip() and not l.strip().startswith('#')]
        return {"type": "requirements", "lines": lines[:100]}
    else:
        return {"type": "unknown", "content": content if len(content) // 4 < 1000 else content[:4000] + "\n...[TRUNCATED]"}

def agent_security_audit(
    design: dict, generated_files: dict[str, str], contract: AcceptanceContract, runtime: RuntimeClients, repo_context: RepositoryContext
) -> SecurityAuditResult:
    logging.info(f"Realizando auditoria de robustez del ecosistema modular con {MODEL_HEAVY}...")
    all_findings = []

    budget = PromptBudget(max_input_tokens=100000, reserved_output_tokens=8000)
    
    # 1. Base mandatory tokens (policy + contract)
    policy_str = repo_context.quality_policy.model_dump_json(indent=2)
    contract_str = contract.model_dump_json(indent=2)
    
    # 2. Config & Dependencies (new additions to context)
    config_str = repo_context.structured_config.model_dump_json(indent=2)
    deps_str = json.dumps(repo_context.structured_config.dependencies + repo_context.structured_config.dev_dependencies, indent=2)
    
    # 3. Coherence Graph (summary of existing state + generated files)
    coherence_graph = build_coherence_summary(generated_files, repo_context)
    graph_str = json.dumps(coherence_graph, indent=2)

    design_compact = json.dumps(design, separators=(',', ':')) if design else "{}"
    dependency_evidence = {}
    for filename, content in repo_context.dependency_files.items():
        dependency_evidence[filename] = summarize_dependency_file(filename, content)
    dep_json = json.dumps(dependency_evidence, indent=2)
    
    # Calculate required base budget
    req_base_str = f"""
        - Politica de calidad activa: {policy_str}
        - Contrato Canonico (Reglas de Arquitectura): {contract_str}
        - Configuracion Estructurada Completa: {config_str}
        - Dependencias (Prod/Dev): {deps_str}
        - Diseño Arquitectónico:
        {design_compact}

        Evidencia de Dependencias:
        {dep_json}

        Grafo de Coherencia: {graph_str}
    """
    req_base_tokens = len(req_base_str) // 4
    
    if not budget.can_add(req_base_tokens):
        logging.warning("El contexto base excede el presupuesto. Fallando rapido.")
        return SecurityAuditResult(
            approved=False, 
            findings=["El contexto base del Security Audit excede el limite de tokens."]
        )
    budget.add(req_base_tokens)

    # 4. Optional context (Architecture and Conflicts)
    arch_doc = repo_context.architecture_document or "[No hay documento de arquitectura]"
    arch_tok = len(arch_doc) // 4
    if arch_tok > 8000:
        arch_doc = arch_doc[:8000 * 4] + "\n... [TRUNCADO]"
        arch_tok = len(arch_doc) // 4
        
    if budget.can_add(arch_tok):
        budget.add(arch_tok)
    else:
        arch_doc = "[Omitido por presupuesto]"

    conflicts = json.dumps([c.model_dump() for c in repo_context.architecture_conflicts], indent=2)
    conf_tok = len(conflicts) // 4
    if budget.can_add(conf_tok):
        budget.add(conf_tok)
    else:
        conflicts = "[Omitido por presupuesto]"

    base_prompt = f"""
        Contexto Adicional para Auditoria:
        - Politica de calidad activa: {policy_str}
        - Contrato Canonico (Reglas de Arquitectura): {contract_str}
        - Configuracion Estructurada Completa: {config_str}
        - Dependencias (Prod/Dev): {deps_str}
        - Diseño Arquitectónico:
        {design_compact}
        - Evidencia de Dependencias:
        {dep_json}
        - Documento de Arquitectura Base: {arch_doc}
        - Conflictos de Arquitectura Detectados Previos: {conflicts}
        - Grafo de Coherencia de Imports: {graph_str}
    """

    available_chunk_tokens = budget.remaining - 2000 # leave buffer for fixed prompt wrapper
    if available_chunk_tokens <= 0:
        return SecurityAuditResult(approved=False, findings=["Sin presupuesto para procesar lotes de auditoria."])

    try:
        payloads = PromptContextBuilder.build_for_audit(generated_files, max_tokens=available_chunk_tokens)
    except PreflightError as e:
        return SecurityAuditResult(approved=False, findings=[str(e)])
    except Exception as e:
        return SecurityAuditResult(approved=False, findings=[f"Fallo al construir chunks de auditoria: {e}"])
        
    for i, payload in enumerate(payloads):
        prompt = base_prompt + f"""
        Archivos Generados (Lote {i+1} de {len(payloads)}):
        {payload.content}

        Actuas como un experto auditor de seguridad y arquitectura. Identifica SI O SI cualquier:
        1. Regresion de Robustez (ej: inyecciones de codigo, rutas inseguras, variables globales mutables).
        2. Dependencias externas o APIs sin envoltorios seguros ni validacion.
        3. Excepciones capturadas de manera generica ('except Exception:') sin logging contextual o relanzamiento.
        4. Falta de validacion de aserciones en los tests (tests que pasan solo con assert True).
        
        Responde exclusivamente con el JSON esperado.
        """
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SecurityAuditResult,
            temperature=0.0
        )
        try:
            ensure_prompt_fits(prompt, budget, "Security Audit Chunk")
            response = runtime.ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt, config=config)
            cleaned_json = extract_code(response.text, "json")
            result = SecurityAuditResult.model_validate_json(cleaned_json)
            if not result.approved:
                all_findings.extend(result.findings)
        except Exception as e:
            logging.error(f"Error parseando resultado de auditoria de seguridad: {e}")
            all_findings.append(f"Error parseando resultado de auditoria: {e}")

    return SecurityAuditResult(approved=len(all_findings)==0, findings=all_findings)

def build_coherence_summary(
    generated_files: dict[str, str],
    repo_context,
) -> dict:
    import ast as _ast
    
    # 1. Build virtual index (baseline + generated)
    virtual_index = {}
    for path, summary in {**repo_context.source_index, **repo_context.test_index}.items():
        virtual_index[path] = summary.model_copy()
        
    for path, code in generated_files.items():
        entry = {"signatures": {}, "imports": [], "imported_files": [], "imported_by": [], "_extracted_modules": []}
        try:
            tree = _ast.parse(code, filename=path)
            # simulate extract_ast_signatures
            entry["signatures"] = extract_ast_signatures(tree)
            mod_name = path.replace("\\", "/").replace(".py", "").replace("/", ".")
            entry["_extracted_modules"] = extract_imported_modules(tree, mod_name)
            for node in _ast.walk(tree):
                if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                    try:
                        entry["imports"].append(_ast.unparse(node))
                    except Exception:
                        pass
        except SyntaxError:
            entry["signatures"] = {"__parse_error__": "SyntaxError en contenido final"}
        
        from pydantic import BaseModel
        class MockSummary:
            def __init__(self, **kwargs):
                for k,v in kwargs.items(): setattr(self, k, v)
        virtual_index[path] = MockSummary(signatures=entry["signatures"], imports=entry["imports"], imported_files=[], imported_by=[], _extracted_modules=entry["_extracted_modules"], model_copy=lambda: None)

    # 2. Re-calculate imported_files and imported_by for the WHOLE virtual index
    all_py_files = list(virtual_index.keys())
    
    # Update imported_files for generated files
    for p in generated_files:
        idx = virtual_index[p]
        idx.imported_files = resolve_imported_files(getattr(idx, "_extracted_modules", []), "", all_py_files)
        
    # Reconstruct imported_by for the WHOLE virtual index
    for p, idx in virtual_index.items():
        idx.imported_by = []
        
    for p, idx in virtual_index.items():
        for imp_file in idx.imported_files:
            if imp_file in virtual_index:
                if p not in virtual_index[imp_file].imported_by:
                    virtual_index[imp_file].imported_by.append(p)
                
    # 3. Build summary for generated and affected
    summary = {}
    for p in generated_files:
        idx = virtual_index[p]
        summary[p] = {
            "signatures": idx.signatures,
            "imports": idx.imports,
            "imported_files": list(set(idx.imported_files)),
            "imported_by": list(set(idx.imported_by))
        }
        
    affected_consumers = set()
    for p in generated_files:
        affected_consumers.update(virtual_index[p].imported_by)
        
    for consumer_path in affected_consumers:
        if consumer_path in summary: continue
        if consumer_path not in virtual_index: continue
        idx = virtual_index[consumer_path]
        summary[consumer_path] = {
            "signatures": getattr(idx, "signatures", {}),
            "imports": getattr(idx, "imports", []),
            "imported_files": list(set(getattr(idx, "imported_files", []))),
            "imported_by": list(set(getattr(idx, "imported_by", []))),
            "_source": "existing_consumer",
        }
    return summary

def agent_code_reviewer(design: dict, generated_files: dict[str, str], issue_desc: str, contract: AcceptanceContract, repo_context: RepositoryContext, runtime: RuntimeClients) -> CodeReviewResult:
    """
    Un agente que actua como un revisor de codigo senior.
    Valida que el codigo generado se adhiere semanticamente a las instrucciones.
    """
    logging.info(f"Realizando revision de codigo semantica con {MODEL_HEAVY}...")
    
    all_findings = []
    design_conflict = False

    budget = PromptBudget(max_input_tokens=100000, reserved_output_tokens=8000)

    # 1. Base mandatory tokens (Contract + Issue)
    contract_json = contract.model_dump_json(indent=2)
    contract_tok = len(contract_json) // 4
    if not budget.can_add(contract_tok):
        return CodeReviewResult(
            approved=False, 
            findings=[ReviewFinding(filepath="unknown", message="Contrato demasiado largo para el reviewer")]
        )
    budget.add(contract_tok)

    issue_tok = len(issue_desc) // 4
    if not budget.can_add(issue_tok):
        return CodeReviewResult(
            approved=False, 
            findings=[ReviewFinding(filepath="unknown", message="Issue demasiado largo para el reviewer")]
        )
    budget.add(issue_tok)

    # 2. Optional context (Architecture, Design, Dependencies)
    arch_doc = repo_context.architecture_document or "[No hay documento de arquitectura]"
    arch_tok = len(arch_doc) // 4
    if arch_tok > 8000:
        arch_doc = arch_doc[:8000 * 4] + "\n... [TRUNCADO]"
        arch_tok = len(arch_doc) // 4
    if budget.can_add(arch_tok):
        budget.add(arch_tok)
    else:
        arch_doc = "[Arquitectura omitida por presupuesto]"

    design_json = json.dumps(design, indent=2)
    des_tok = len(design_json) // 4
    if budget.can_add(des_tok):
        budget.add(des_tok)
    else:
        design_json = "[Diseno omitido por presupuesto]"

    deps_json = json.dumps(repo_context.structured_config.dependencies, indent=2)
    deps_tok = len(deps_json) // 4
    if budget.can_add(deps_tok):
        budget.add(deps_tok)
    else:
        deps_json = "[Dependencias omitidas por presupuesto]"

    base_prompt = f"""
        Actuas como un Ingeniero de Software Principal realizando una revision de codigo. Tu tarea es verificar que el codigo generado cumple ESTRICTAMENTE con todas las fuentes de verdad.

        **FUENTES DE VERDAD (EN ORDEN DE PRIORIDAD):**
        1.  **Requisitos Originales del Issue:**
            {issue_desc}

        2.  **Contrato de Aceptacion (Reglas Estrictas):**
            {contract_json}

        3.  **Documento de Arquitectura (Vision y Restricciones):**
            {arch_doc}

        4.  **Plan del Arquitecto (Intencion de Implementacion):**
            {design_json}

        5.  **Dependencias del Proyecto (Bibliotecas Externas):**
            {deps_json}
    """
    
    # 2000 reserved for the wrapper prompt text below
    available_chunk_tokens = budget.remaining - 2000
    if available_chunk_tokens <= 0:
        return CodeReviewResult(approved=False, findings=[ReviewFinding(filepath="unknown", message="Sin presupuesto para revision.")])

    try:
        payloads = PromptContextBuilder.build_for_reviewer(generated_files, max_tokens=available_chunk_tokens)
    except PreflightError as e:
        return CodeReviewResult(approved=False, findings=[ReviewFinding(filepath="unknown", message=str(e))])
    except Exception as e:
        return CodeReviewResult(approved=False, findings=[ReviewFinding(filepath="unknown", message=f"Fallo al construir chunks: {e}")])
        
    for i, payload in enumerate(payloads):
        prompt = base_prompt + f"""
        **Codigo Generado para Revision (Lote {i+1} de {len(payloads)}):**
        {payload.content}

        IMPORTANTE - ALCANCE DE ESTE LOTE:
        Evalua unicamente el cumplimiento aplicable a los archivos contenidos en este lote ({i+1} de {len(payloads)}).
        No rechaces este lote por la ausencia de archivos que pertenezcan a otros lotes.
        Las reglas del contrato que apunten a archivos no incluidos en este lote se evaluaran en la revision de coherencia transversal final.
        Tu mision es encontrar discrepancias entre el **Codigo Generado** y las **Fuentes de Verdad** para los archivos presentes.
        -   Valida que el codigo cumple con la logica del `issue_desc`.
        -   Valida que el codigo cumple con TODAS las reglas del `AcceptanceContract`, prestando especial atencion a `preserved_behaviors`.
        -   Valida que el codigo no contradice los principios del `architecture_document`.
        -   El `Plan del Arquitecto` es la guia de mas bajo nivel. Si contradice una fuente de verdad superior (Issue, Contrato, Arquitectura), debes rechazar el diseno.

        Si el plan del arquitecto contradice una fuente de verdad superior:
        1. No exijas al codigo cumplir la instruccion contradictoria.
        2. Rechaza el diseno.
        3. Identifica la contradiccion como DESIGN_CONFLICT en tu mensaje.
        
        Responde con un JSON que se ajuste al esquema `CodeReviewResult`. Si todo es correcto, `approved` sera `true`. Si hay fallos, `approved` sera `false` y `findings` contendra una lista de objetos con `filepath` y `message`.
        """
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=CodeReviewResult,
            temperature=0.0,
        )
        try:
            ensure_prompt_fits(prompt, budget, "Reviewer Chunk")
            response = runtime.ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt, config=config)
            cleaned_json = extract_code(response.text, "json")
            result = CodeReviewResult.model_validate_json(cleaned_json)
            if not result.approved:
                all_findings.extend(result.findings)
                if result.design_conflict:
                    design_conflict = True
        except Exception as e:
            logging.error(f"Error parseando resultado de code_reviewer: {e}")
            all_findings.append(ReviewFinding(filepath="unknown", message=f"Error en la revision: {e}"))

    # Revision de coherencia transversal
    if generated_files and not all_findings and not design_conflict:
        logging.info("Realizando revision de coherencia transversal del sistema...")

        coherence_budget = PromptBudget(max_input_tokens=100000, reserved_output_tokens=4000)
        coherence_graph = build_coherence_summary(generated_files, repo_context)
        coherence_graph_json = json.dumps(coherence_graph, indent=2)
        
        try:
            add_required_or_fail(coherence_budget, contract_json, "Contrato en Coherence")
            add_required_or_fail(coherence_budget, coherence_graph_json, "Grafo en Coherence")
        except PreflightError as e:
            all_findings.append(ReviewFinding(filepath="unknown", message=f"Fallo de presupuesto transversal: {e}"))
            return CodeReviewResult(approved=False, findings=all_findings, design_conflict=design_conflict)

        coherence_prompt = f"""
        Eres un arquitecto de software revisando la coherencia global de un sistema.

        GRAFO DE DEPENDENCIAS Y FIRMAS DEL ESTADO FINAL:
        {coherence_graph_json}

        Contrato de Aceptacion: {contract_json}

        Verifica EXCLUSIVAMENTE:
        1. Imports rotos (un archivo importa simbolos que no existen en sus dependencias).
        2. Interfaces incompatibles (firma esperada por consumidores vs firma real generada).
        3. Archivos contractualmente requeridos ausentes en el manifiesto.
        4. Dependencias circulares evidentes entre los modulos generados.
        5. Consumidores existentes que reciben interfaces incompatibles.

        NO revises el contenido completo de los archivos individuales (ya fue revisado por lotes).
        Responde en JSON bajo el esquema CodeReviewResult.
        """
        
        ensure_prompt_fits(coherence_prompt, coherence_budget, "Coherence Pass")
        try:
            coherence_config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CodeReviewResult,
                temperature=0.0,
            )
            coherence_resp = runtime.ai_client.models.generate_content(model=MODEL_LIGHT, contents=coherence_prompt, config=coherence_config)
            coherence_result = CodeReviewResult.model_validate_json(extract_code(coherence_resp.text, "json"))
            if not coherence_result.approved:
                all_findings.extend(coherence_result.findings)
            if coherence_result.design_conflict:
                design_conflict = True
        except Exception as e:
            logging.error(f"Error en revision de coherencia transversal: {e}")
            all_findings.append(ReviewFinding(
                filepath="__coherence__",
                message=f"La revision de coherencia transversal fallo con un error tecnico: {e}. El pipeline no puede garantizar la integridad del sistema sin esta revision."
            ))

    return CodeReviewResult(approved=len(all_findings)==0, findings=all_findings, design_conflict=design_conflict)
