import json
import logging
from google.genai import types

from orchestrator_core.schemas import AcceptanceContract, ProjectDesign, RepositoryContext
from orchestrator_core.prompt_budget import PreflightError, PromptBudget, ensure_prompt_fits
from orchestrator_core.runtime import RuntimeClients
from orchestrator_core.model_config import MODEL_HEAVY
from orchestrator_core.exceptions import (
    ContractGenerationError,
    CandidateSchemaError,
    InfrastructureGenerationError,
)

def _build_gemini_json_schema(raw_schema: dict) -> dict:
    import copy
    schema = copy.deepcopy(raw_schema)

    gemini_allowlist = {
        "$id", "$defs", "$ref", "$anchor", "type", "format", "title",
        "description", "enum", "items", "prefixItems", "minItems",
        "maxItems", "minimum", "maximum", "anyOf", "oneOf", "properties",
        "additionalProperties", "required", "propertyOrdering"
    }

    strip_keys = {"default", "uniqueItems"}

    def adapt_schema_node(node: dict, path: list) -> None:
        if not isinstance(node, dict):
            return

        for k in strip_keys:
            if k in node:
                del node[k]

        for k in node:
            if k not in gemini_allowlist:
                dot_path = ".".join(path + [k])
                from orchestrator_core.exceptions import ContractGenerationError
                raise ContractGenerationError(f"Unsupported schema keyword found: '{k}' at '{dot_path}'")

        if "properties" in node and isinstance(node["properties"], dict):
            for prop_name, prop_node in node["properties"].items():
                if isinstance(prop_node, dict):
                    adapt_schema_node(prop_node, path + ["properties", prop_name])

        if "$defs" in node and isinstance(node["$defs"], dict):
            for def_name, def_node in node["$defs"].items():
                if isinstance(def_node, dict):
                    adapt_schema_node(def_node, path + ["$defs", def_name])

        if "additionalProperties" in node and isinstance(node["additionalProperties"], dict):
            adapt_schema_node(node["additionalProperties"], path + ["additionalProperties"])

        if "items" in node and isinstance(node["items"], dict):
            adapt_schema_node(node["items"], path + ["items"])

        for list_key in ["prefixItems", "anyOf", "oneOf"]:
            if list_key in node and isinstance(node[list_key], list):
                for i, item_node in enumerate(node[list_key]):
                    if isinstance(item_node, dict):
                        adapt_schema_node(item_node, path + [list_key, str(i)])

    adapt_schema_node(schema, ["$root"])
    return schema

def agent_generate_acceptance_contract(title: str, description: str, repository_context: RepositoryContext, runtime: RuntimeClients, prior_feedback: str = "") -> AcceptanceContract:
    """
    Generates a structured acceptance contract from the issue description, repository context, and architecture.
    """
    logging.info("Generando Contrato de Aceptación a partir del Issue y contexto del repositorio...")

    budget_contract = PromptBudget(max_input_tokens=100000, reserved_output_tokens=8000)

    project_config_json = repository_context.structured_config.model_dump_json(indent=2)
    policy_summary = json.dumps(repository_context.quality_policy.model_dump(), indent=2)

    # Reservar contexto obligatorio
    base_instructions_len = 2000 # estimación conservadora
    mandatory_tokens = base_instructions_len + (len(title) + len(description) + len(project_config_json) + len(policy_summary)) // 4
    if not budget_contract.can_add(mandatory_tokens):
        raise PreflightError("El contexto obligatorio excede el presupuesto del Contrato.")
    budget_contract.add(mandatory_tokens)

    # Priority 1: architecture doc
    arch_text = repository_context.architecture_document or "[No se encontro documento de arquitectura.]"
    arch_tokens = len(arch_text) // 4
    if not budget_contract.can_add(arch_tokens):
        max_chars = budget_contract.remaining * 4
        arch_text = arch_text[:max_chars]
        logging.warning("architecture_document truncado.")
        arch_tokens = len(arch_text) // 4
    budget_contract.add(arch_tokens)

    # Priority 2: compact global index
    all_summaries = {**repository_context.source_index, **repository_context.test_index}
    global_index_summary = {
        fp: {"classes": summary.classes, "functions": summary.functions}
        for fp, summary in all_summaries.items()
    }
    global_index_json = json.dumps(global_index_summary, indent=2)
    idx_tokens = len(global_index_json) // 4
    if budget_contract.can_add(idx_tokens):
        budget_contract.add(idx_tokens)
    else:
        max_chars = budget_contract.remaining * 4
        global_index_json = global_index_json[:max_chars]
        budget_contract.add(len(global_index_json) // 4)

    # Priority 3: relevant file metadata
    relevant_files_metadata = {}
    for fp in list(repository_context.relevant_source_files.keys()) + list(repository_context.relevant_test_files.keys()):
        summary = all_summaries.get(fp)
        if summary:
            relevant_files_metadata[fp] = summary.model_dump(exclude={'file_hash', 'estimated_tokens', 'referenced_symbols', 'docstring_summary'})
    relevant_metadata_json = json.dumps(relevant_files_metadata, indent=2)
    meta_tokens = len(relevant_metadata_json) // 4
    if budget_contract.can_add(meta_tokens):
        budget_contract.add(meta_tokens)
    else:
        relevant_metadata_json = relevant_metadata_json[:budget_contract.remaining * 4]
        budget_contract.add(len(relevant_metadata_json) // 4)

    # Priority 4: full file contents (only what fits)
    relevant_files_context = ""
    if repository_context.relevant_source_files or repository_context.relevant_test_files:
        relevant_files_context += "\n\nCONTENIDO DE ARCHIVOS RELEVANTES (PRE-SELECCIONADOS POR RELEVANCIA):\n"
        for path, file_content in {**repository_context.relevant_source_files, **repository_context.relevant_test_files}.items():
            frag = f"--- INICIO {path} ---\n{file_content}\n--- FIN {path} ---\n"
            tok = len(frag) // 4
            if budget_contract.can_add(tok):
                relevant_files_context += frag
                budget_contract.add(tok)

    prompt = f"""
    Actúas como un Quality Assurance Lead y Arquitecto de Pruebas. Tu tarea es leer una especificación de requisitos de un Issue y traducirla a un contrato de aceptación técnico y estricto en formato JSON.

    Este contrato define las reglas inmutables que el código generado debe cumplir.

    FUENTES DE INFORMACIÓN:
    1.  REQUISITOS DEL ISSUE (El 'qué' se debe cambiar):
       - Título: {title}
       - Requisitos: {description}

    2.  DOCUMENTO DE ARQUITECTURA (El 'porqué' de las decisiones de diseño):
       --- INICIO DOCUMENTO ---
       {arch_text}
       --- FIN DOCUMENTO ---

    3.  RESUMEN GLOBAL DEL CÓDIGO (Todas las clases y funciones del repo):
       --- INICIO RESUMEN ÍNDICE ---
       {global_index_json}
       --- FIN RESUMEN ÍNDICE ---

    4.  METADATOS DE ARCHIVOS RELEVANTES (Relaciones, tests e imports detectados):
       --- INICIO METADATOS RELEVANTES ---
       {relevant_metadata_json}
       --- FIN METADATOS RELEVANTES ---

    5.  CONFIGURACIÓN DEL PROYECTO (Reglas de linters, dependencias base):
       --- INICIO CONFIGURACIÓN ---
       {project_config_json}
       --- FIN CONFIGURACIÓN ---

    6.  POLÍTICA DE CALIDAD DERIVADA (Reglas de alto nivel inferidas del repositorio):
        {policy_summary}

    {relevant_files_context}

    REGLAS DE FIDELIDAD DE FUENTES (SOURCE FIDELITY):
    1. PRECEDENCIA VINCULANTE: "Scope", "Expected Behavior", "Acceptance Criteria", "Constraints", "Preservation Requirements", "authoritative repository evidence", y "Purpose when it contains normative requirements" son ESTRICTAMENTE VINCULANTES.
    2. RECOMENDACIONES NO VINCULANTES: "Implementation Open Choices", "recommendations", "suggested technologies", "optional choices", "examples", y "estimated_files / Estimated Files" son fuentes NO VINCULANTES. Estas NO DEBEN convertirse en una regla contractual obligatoria a menos que estén respaldadas independientemente por una restricción vinculante. Explicitly: An estimated file list is a planning hint and MUST NOT automatically become required_final_files, required_new_files or required_modified_files without independent binding evidence from requirements or repository state.
    3. EXHAUSTIVIDAD DE REQUISITOS ENUMERADOS: Si el Issue enumera dimensiones obligatorias, debes preservar TODAS. No omitas ninguna, no las reemplaces por conceptos adyacentes, no cambies su significado semántico y no inventes requisitos de negocio adicionales.
    4. PRESERVACIÓN SEMÁNTICA: Preserva el significado exacto de la terminología de origen. Si la fuente exige una restauración o equivalencia exacta tras la persistencia, el contrato debe preservar esa exigencia semántica exacta en lugar de debilitarla a un simple "load" o "resume".

    Analiza TODAS las fuentes de información para derivar el contrato. Por ejemplo:
    - Si el Issue pide modificar un archivo, el contrato debe incluirlo en `required_modified_files`.
    - Si la `POLÍTICA DE CALIDAD` indica `require_explicit_exports: true`, el contrato debe generar reglas en `required_exports` para los archivos de producción relevantes.
    - Si la `POLÍTICA DE CALIDAD` indica `require_argument_annotations: true`, el contrato debe reflejarlo en sus reglas, aunque el validador `validate_code_quality` ya lo compruebe.
    - Si la arquitectura o la política prohíben `pytest-mock`, el contrato debe reflejarlo en `forbidden_testing_techniques` y `forbidden_imports`.
    - Si el Issue menciona una funcionalidad que ya tiene tests (visible en el ÍNDICE DE TESTS), el contrato debe listarlos en `protected_tests` para asegurar que no se rompan.
    - Si el código existente (visible en ARCHIVOS RELEVANTES) usa un patrón (ej. `logger.warning` antes de `raise`), el contrato debe exigirlo en `required_patterns`.
    - Si `pyproject.toml` define una regla de Ruff, el contrato puede reforzarla en `required_quality_tools`.

    Extrae las siguientes reglas:
    - `required_final_files`: Archivos que deben existir al finalizar la tarea.
    - `required_new_files`: Archivos que deben ser creados.
    - `required_modified_files`: Archivos que deben ser modificados.
    - `required_deleted_files`: Archivos que deben ser eliminados.
    - `preserved_files`: Archivos existentes que son relevantes pero no deben ser modificados. Si un archivo tiene tests protegidos, debería estar aquí.
    - `relevant_context_files`: Archivos de contexto relevantes.
    - `required_tests`: Pruebas obligatorias para la **nueva** funcionalidad.
    - `protected_tests`: Tests existentes que no deben romperse ni eliminarse. Extrae esto del índice del repositorio, especialmente los tests que cubren los módulos a modificar.
    - `forbidden_test_names`: Nombres de pruebas que están explícitamente prohibidos.
    - `preserved_signatures`: Firmas de símbolos que deben preservarse porque otros módulos dependen de ellas. Extrae las firmas completas del índice. Formato: `{{"module.py": {{"PublicClass": "class PublicClass(arg1: int)", "public_function": "def public_function()"}}}}`.
    - `preserved_behaviors`: Comportamientos de alto nivel que no pueden ser expresados con reglas AST o tests. **Usa este campo como último recurso.** Prioriza siempre convertir un comportamiento en una regla concreta en `protected_tests`, `required_tests`, `required_patterns`, etc. Si usas este campo, el Code Reviewer lo validará semánticamente.
    - `forbidden_constructs`: Un diccionario donde la clave es un glob de ruta de archivo (ej. `src/services/example_service*.py`) y el valor es una lista de constructos prohibidos ('continue', 'pass').
    - `required_exports`: Símbolos que deben estar en `__all__`.
    - `required_calls`: Especifica que una función debe llamar a otra. Ej: `{{ "src/utils/data_normalization.py": {{ "normalize_data_item": [{{ "name": "dependency_function", "count": 1 }}] }} }}`.
    - `required_patterns`: Patrones de código obligatorios. Ej: `{{ "src/services/example_service.py": ["log_before_raise"] }}`.
    - `required_structures`: Validaciones sobre estructuras de datos. Ej: `{{ "src/utils/data_normalization.py": {{ "PUBLIC_MAPPING": "has_aliases" }} }}`.
    - `required_imports` / `forbidden_imports`: Reglas sobre importaciones. Ej: `{{ "tests/*": ["from unittest.mock import patch"] }}` y `{{ "tests/*": ["pytest_mock"] }}`.
    - `required_decorators`: Decoradores requeridos en un archivo. Ej: `{{ "src/api/endpoints.py": ["@app.route"] }}`.
    - `required_quality_tools`: Herramientas de calidad (linters/checkers) que deben usarse (ej. "mypy", "ruff").
    - `forbidden_quality_tools`: Herramientas de calidad prohibidas (ej. "flake8").
    - `required_testing_techniques`: Técnicas específicas de pruebas obligatorias (ej. "unittest.mock.patch").
    - `forbidden_testing_techniques`: Técnicas de pruebas explícitamente prohibidas (ej. "pytest-mock").

    Si un campo no es aplicable, déjalo como una lista o diccionario vacío.
    Responde únicamente con el JSON que se ajuste al esquema `AcceptanceContract`.
    """
    transport_schema = _build_gemini_json_schema(AcceptanceContract.model_json_schema())

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=transport_schema,
        temperature=0.1
    )

    # Append prior validation feedback for retry correction
    if prior_feedback:
        prompt = prompt + f"\n\n    FEEDBACK DE INTENTO ANTERIOR (CORRIGE ESTOS ERRORES):\n    {prior_feedback}"

    try:
        ensure_prompt_fits(prompt, budget_contract, "Acceptance Contract")
        try:
            response = runtime.ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt, config=config)
        except Exception as api_exc:
            # API/transport/auth/network failure: non-retryable
            logging.error(f"Error de infraestructura al llamar al modelo: {api_exc}")
            raise InfrastructureGenerationError(
                f"Fallo de infraestructura al generar el Contrato de Aceptación: {api_exc}"
            ) from api_exc
        try:
            contract = AcceptanceContract.model_validate_json(response.text)
        except Exception as val_exc:
            # JSON/schema validation failure: retryable
            logging.error(f"Error de validación de esquema del candidato: {val_exc}")
            raise CandidateSchemaError(
                f"Fallo de validación del esquema del candidato: {val_exc}"
            ) from val_exc
        logging.info("Contrato de Aceptación generado con éxito.")
        return contract
    except (InfrastructureGenerationError, CandidateSchemaError):
        raise
    except PreflightError:
        raise
    except Exception as e:
        # Unexpected Python/runtime failure: non-retryable
        logging.error(f"Error inesperado al generar el Contrato de Aceptación: {e}")
        raise InfrastructureGenerationError(
            f"Error inesperado al generar el Contrato de Aceptación: {e}"
        ) from e


def agent_analyze_and_design(title: str, description: str, contract: AcceptanceContract, repo_context: RepositoryContext, runtime: RuntimeClients, context_manager: "RepositoryContextManager", design_feedback: str = "") -> dict:
    """Diseña la solucion tecnica usando un PromptBudget con prioridades fail-closed/warn-and-truncate."""
    MAX_INPUT = 130000
    RESERVED_OUTPUT = 8192
    budget = PromptBudget(max_input_tokens=MAX_INPUT, reserved_output_tokens=RESERVED_OUTPUT)

    # ----- FUENTES OBLIGATORIAS (fail-closed si no caben) -----
    # 1. AcceptanceContract
    contract_json = contract.model_dump_json(indent=2)
    contract_tokens = len(contract_json) // 4
    if not budget.can_add(contract_tokens):
        raise PreflightError(
            f"El AcceptanceContract ({contract_tokens} tokens) supera el presupuesto disponible "
            f"({budget.remaining} tokens). No se puede proceder."
        )
    budget.add(contract_tokens)

    # 2. Issue (title + description)
    issue_text = f"Titulo: {title}\nRequisitos: {description}"
    issue_tokens = len(issue_text) // 4
    if not budget.can_add(issue_tokens):
        raise PreflightError(
            f"El Issue ({issue_tokens} tokens) supera el presupuesto disponible tras el contrato. "
            "No se puede proceder."
        )
    budget.add(issue_tokens)

    # 3. Instrucciones fijas minimas del prompt
    FIXED_PROMPT_TOKENS = 1200
    if not budget.can_add(FIXED_PROMPT_TOKENS):
        raise PreflightError(
            "Las instrucciones fijas del arquitecto no caben en el presupuesto. "
            "El prompt esta sobrecargado con contrato + issue."
        )
    budget.add(FIXED_PROMPT_TOKENS)

    # ----- FUENTES OPCIONALES (warn-and-truncate) -----
    # 4. architecture_document
    arch_doc_raw = repo_context.architecture_document or "[No se encontro documento de arquitectura.]"
    ARCH_MAX = 8000
    arch_tok = len(arch_doc_raw) // 4
    if arch_tok > ARCH_MAX:
        arch_doc_display = arch_doc_raw[:ARCH_MAX * 4] + "\n... [ARQUITECTURA TRUNCADA]"
        logging.warning(f"agent_analyze_and_design: architecture_document truncado a {ARCH_MAX} tokens.")
        arch_tok = ARCH_MAX
    else:
        arch_doc_display = arch_doc_raw
    if budget.can_add(arch_tok):
        budget.add(arch_tok)
    else:
        arch_doc_display = "[arquitectura omitida por presupuesto]"
        logging.warning("agent_analyze_and_design: architecture_document omitido por presupuesto.")

    # 5. structured_config
    project_config_json = repo_context.structured_config.model_dump_json(indent=2)
    pcfg_tok = len(project_config_json) // 4
    if not budget.can_add(pcfg_tok):
        project_config_json = "[config omitida por presupuesto]"
        logging.warning("agent_analyze_and_design: project_config omitida por presupuesto.")
    else:
        budget.add(pcfg_tok)

    # 6. architecture_conflicts
    arch_conflicts_json = json.dumps([c.model_dump() for c in repo_context.architecture_conflicts], indent=2)
    aconf_tok = len(arch_conflicts_json) // 4
    if not budget.can_add(aconf_tok):
        arch_conflicts_display = "[conflictos omitidos por presupuesto]"
        logging.warning("agent_analyze_and_design: architecture_conflicts omitidos por presupuesto.")
    else:
        budget.add(aconf_tok)
        arch_conflicts_display = arch_conflicts_json if repo_context.architecture_conflicts else "[No se detectaron conflictos.]"

    # 7. repository_map
    repo_map = repo_context.repository_map or "[Repositorio limpio]"
    map_tok = len(repo_map) // 4
    REPO_MAP_MAX = 12000
    if map_tok > REPO_MAP_MAX:
        repo_map = repo_map[:REPO_MAP_MAX * 4] + "\n... [MAPA TRUNCADO]"
        map_tok = REPO_MAP_MAX
        logging.warning(f"agent_analyze_and_design: repository_map truncado a {REPO_MAP_MAX} tokens.")
    if budget.can_add(map_tok):
        budget.add(map_tok)
    else:
        repo_map = "[mapa omitido por presupuesto]"
        logging.warning("agent_analyze_and_design: repository_map omitido por presupuesto.")

    # 8. relevant files
    omitted_files = []
    relevant_files_context = ""
    if repo_context.relevant_source_files or repo_context.relevant_test_files:
        relevant_files_context += "\n\nCONTENIDO DE ARCHIVOS RELEVANTES (PRE-SELECCIONADOS POR RELEVANCIA):\n"
        for path, file_content in {**repo_context.relevant_source_files, **repo_context.relevant_test_files}.items():
            frag = f"--- INICIO {path} ---\n{file_content}\n--- FIN {path} ---\n"
            tok = len(frag) // 4
            if budget.can_add(tok):
                relevant_files_context += frag
                budget.add(tok)
            else:
                relevant_files_context += f"[{path}: omitido por presupuesto]\n"
                omitted_files.append(path)
                logging.warning(f"agent_analyze_and_design: archivo relevante '{path}' omitido por presupuesto.")

    # 9. design_feedback
    feedback_section = ""
    if design_feedback:
        fb_tok = len(design_feedback) // 4
        if budget.can_add(fb_tok):
            feedback_section = f"FEEDBACK DEL DISENO ANTERIOR (DEBES CORREGIR ESTO):\n{design_feedback}"
            budget.add(fb_tok)
        else:
            logging.warning("agent_analyze_and_design: design_feedback omitido por presupuesto.")

    if omitted_files:
        logging.warning(f"agent_analyze_and_design: {len(omitted_files)} archivos relevantes omitidos: {omitted_files}")

    prompt = f"""
    Actuas como el Arquitecto de Software Principal. Tu objetivo es disenar una solucion tecnica estructurada, elegante, testable y lista para produccion que cumpla con la especificacion del Issue.

    Para entender el sistema, tienes varias fuentes de informacion clave:
    1. CONTRATO DE ACEPTACION: Las reglas estrictas y deterministas que tu diseno DEBE cumplir. Es tu principal restriccion.
    2. DOCUMENTO DE ARQUITECTURA: Describe la vision y restricciones del sistema. CUIDADO: puede estar desactualizado.
    3. CONFLICTOS DE ARQUITECTURA: Analisis automatico de posibles desactualizaciones.
    4. INDICES AST: Fuente de verdad sobre el estado actual del codigo (el mapa del repositorio).
    5. CONTENIDO DE ARCHIVOS RELEVANTES: El contenido completo de los archivos mas importantes.

    CONTRATO DE ACEPTACION (REGLAS OBLIGATORIAS PARA TU DISENO):
    --- INICIO CONTRATO ---
    {contract_json}
    --- FIN CONTRATO ---

    CONFLICTOS DETECTADOS ENTRE ARQUITECTURA Y CODIGO REAL:
    --- INICIO CONFLICTOS ---
    {arch_conflicts_display}
    --- FIN CONFLICTOS ---

    DOCUMENTO DE ARQUITECTURA:
    --- INICIO DOCUMENTO ---
    {arch_doc_display}
    --- FIN DOCUMENTO ---

    CONFIGURACION DEL PROYECTO (Reglas de linters, dependencias base):
    --- INICIO CONFIGURACION ---
    {project_config_json}
    --- FIN CONFIGURACION ---

    {relevant_files_context}

    ESPECIFICACION FUNCIONAL DEL ISSUE:
    - {issue_text}

    {feedback_section}

    TOPOLOGIA EN DISCO ACTUAL Y FIRMAS AST:
    --- INICIO MAPA ---
    {repo_map}
    --- FIN MAPA ---

    REGLAS DE RECONCILIACION Y TOPOLOGIA:
    - ALINEACION ESTRICTA: Reconcilia los requerimientos funcionales con la TOPOLOGIA EN DISCO ACTUAL. Utiliza obligatoriamente las clases y metodos existentes.
    - INSPECCION DE FIRMAS OBLIGATORIA: Examina meticulosamente el mapa (AST) adjunto para ver si el metodo '__init__' de las clases objetivo declara parametros. Queda terminantemente PROHIBIDO pasar parametros con nombre (kwargs) si la estructura no coincide con la firma real dictada por el mapa.
    - EXPORTACION EXPLICITA (__all__): Si el AcceptanceContract especifica required_exports para un archivo, tu diseno debe instruir su creacion.

    EXPANSION DE CONTEXTO BAJO DEMANDA:
    - Si necesitas examinar el codigo de OTRO archivo, devuelve is_context_request: true y rellena context_request. NO generes el diseno en ese paso.
    """

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ProjectDesign,
        temperature=0.1
    )
    ensure_prompt_fits(prompt, budget, "Technical Design")
    response = runtime.ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt, config=config)
    return json.loads(response.text or "{}")
