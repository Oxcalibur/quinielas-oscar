# -*- coding: utf-8 -*-
"""
Orquestador SDLC de Agentes Autónomos con Refactorización Dinámica y Calidad Estática (Versión 2026)
Optimizado para decisiones dinámicas de arquitectura modular libre, Docs-as-Code,
análisis estático contra código muerto (Vulture) y linter (Ruff),
y Git flow con Run ID y registro transaccional JSON de alta trazabilidad.
Incluye un Agente Clínico Post-Mortem y Reflexión Multinivel Integral para auto-corrección estructural.
"""

# 1. PARCHE DE SEGURIDAD SSL INICIAL
import truststore
try:
    truststore.inject_into_ssl()
except AttributeError:
    import urllib3
    truststore.inject_into_urllib3()

import os
import re
import sys
import json
import ast
import datetime
import subprocess
from dotenv import load_dotenv

# Constante para evitar cortes en el renderizado de la UI del chat y formatear Prompts
MD_FENCE = "`" * 3

# =====================================================================
# MONKEY PATCH: CARGA DEL .ENV Y COMPATIBILIDAD SSL (BYPASS)
# =====================================================================
load_dotenv()

if os.getenv("BYPASS_SSL_VERIFY", "false").lower() == "true":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    import requests
    original_request = requests.Session.request
    
    def patched_request(self, method, url, *args, **kwargs):
        kwargs['verify'] = False
        return original_request(self, method, url, *args, **kwargs)
        
    requests.Session.request = patched_request
    print("[INFO] [Seguridad] Modo de compatibilidad activo: Verificacion SSL de GitHub omitida.")
# =====================================================================

from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from github import Github, Auth

# Validar variables críticas
required_env = ["GITHUB_TOKEN", "REPO_OWNER", "REPO_NAME", "GEMINI_API_KEY"]
for var in required_env:
    if not os.getenv(var):
        print(f"[ERROR] La variable de entorno {var} no esta configurada en el .env")
        sys.exit(1)

# 2. Inicializar clientes de API
ai_client = genai.Client()
auth = Auth.Token(os.getenv("GITHUB_TOKEN"))
github_client = Github(auth=auth)
repo_path = f"{os.getenv('REPO_OWNER')}/{os.getenv('REPO_NAME')}"
repo = github_client.get_repo(repo_path)

# --- CONFIGURACION DE MODELOS GEMINI 3 (VIGENCIA 2026) ---
MODEL_HEAVY = "gemini-3.1-pro-preview"   # Razonamiento complejo, refactorizacion estructural y auditorias
MODEL_LIGHT = "gemini-3.5-flash"          # Velocidad extrema para codificacion de piezas, tests y reportes

# =====================================================================
# GESTOR DE CONTEXTO HIBRIDO (ANALISIS ESTATICO DE ARCHIVOS CON AST)
# =====================================================================
class RepositoryContextManager:
    def __init__(self, root_path="."):
        self.root_path = root_path
        self.ignored_dirs = {
            ".git", "venv", "__pycache__", ".pytest_cache", 
            ".env", "node_modules", "dist", "build"
        }

    def generate_repository_map(self) -> str:
        """Genera un mapa textual de la estructura fisica y logica del proyecto."""
        repo_map = []
        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs]
            
            relative_path = os.path.relpath(root, self.root_path)
            level = 0 if relative_path == "." else relative_path.count(os.sep) + 1
            indent = "  " * level
            
            if relative_path != ".":
                repo_map.append(f"{indent}[DIR] {os.path.basename(root)}/")
            
            for file in files:
                if file.endswith(".py") and file not in ["orchestrator.py", "po_agent.py", "test_github.py", "test_ssl.py", "user_manual_generator.py"]:
                    file_indent = "  " * (level + 1)
                    repo_map.append(f"{file_indent}[FILE] {file}")
                    
                    full_path = os.path.join(root, file)
                    signatures = self._extract_signatures(full_path)
                    for sig in signatures:
                        repo_map.append(f"{file_indent}  ↳ {sig}")
                        
        return "\n".join(repo_map)

    def _extract_signatures(self, filepath) -> list:
        """Extrae firmas de clases y métodos de inicialización usando AST de Python."""
        signatures = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                node = ast.parse(f.read(), filename=filepath)
                
            for child in node.body:
                if isinstance(child, ast.FunctionDef):
                    args = [arg.arg for arg in child.args.args]
                    signatures.append(f"def {child.name}({', '.join(args)})")
                elif isinstance(child, ast.ClassDef):
                    init_args = []
                    methods = []
                    for subchild in child.body:
                        if isinstance(subchild, ast.FunctionDef):
                            sub_args = [arg.arg for arg in subchild.args.args if arg.arg != 'self']
                            if subchild.name == "__init__":
                                init_args = sub_args
                            else:
                                methods.append(f"    - def {subchild.name}({', '.join(sub_args)})")
                    
                    class_def_str = f"class {child.name}"
                    if init_args:
                        class_def_str += f"({', '.join(init_args)})"
                    
                    signatures.append(class_def_str)
                    signatures.extend(methods)
        except Exception:
            pass
        return signatures

    def get_file_content(self, relative_filepath) -> str:
        """Carga el contenido real de un archivo especifico del repositorio."""
        full_path = os.path.join(self.root_path, relative_filepath)
        if not os.path.exists(full_path):
            return f"# El archivo '{relative_filepath}' no existe todavia o se creará nuevo."
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"# Error al leer {relative_filepath}: {str(e)}"

# Instancia global de contexto
context_manager = RepositoryContextManager()

# =====================================================================
# ESQUEMAS PYDANTIC PARA REFACTORIZACION Y DISENO DINAMICO LIBRE
# =====================================================================
class FileAction(BaseModel):
    filepath: str = Field(description="Ruta relativa completa del archivo (ej. 'core/billing.py', 'utils/helpers.py').")
    operation: str = Field(description="Operacion de ciclo de vida: 'CREATE' (crear nuevo), 'MODIFY' (modificar), 'DELETE' (eliminar).")
    file_type: str = Field(description="Categoria: 'production' (logica), 'test' (pytest), 'config', o 'none'.")
    signatures: str = Field(description="Firma de las funciones, metodos o clases que deben residir en este archivo.")
    instructions: str = Field(description="Logica detallada de implementacion o requerimientos de refactorizacion.")

class ProjectDesign(BaseModel):
    architecture_justification: str = Field(description="Razonamiento tecnico completo de por que se adopta esta topologia.")
    actions: list[FileAction] = Field(description="Secuencia ordenada de acciones de archivos a ejecutar fisicamente.")
    dependencies: list[str] = Field(default=[], description="Archivos existentes que se deben leer de forma micro como contexto.")

def extract_code(text, language="python"):
    pattern = rf"{MD_FENCE}{language}\s*(.*?)\s*{MD_FENCE}"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    return text.strip()

# =====================================================================
# FUNCION DE LOGS LOCALES Y METADATOS TRANSACCIONALES
# =====================================================================
def write_local_log(issue_id, title, success, details=""):
    log_file = "pipeline.log"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCCESS" if success else "FAILED"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] Issue #{issue_id} - '{title}' | Estado: {status}\n")
        if details: f.write(f"Detalle: {details}\n")
        f.write("-" * 80 + "\n")
    print(f"[LOG] Historial guardado localmente en '{log_file}'")

def write_transactional_metadata(run_id, issue_id, title, success, design, commit_hash="N/A"):
    registry_file = "docs/metadata/runs_registry.json"
    os.makedirs("docs/metadata", exist_ok=True)
    registry = {}
    if os.path.exists(registry_file):
        try:
            with open(registry_file, "r", encoding="utf-8") as f: registry = json.load(f)
        except Exception: registry = {}
    created_files, modified_files, deleted_files = [], [], []
    for action in design.get("actions", []):
        filepath = action.get("filepath")
        op = action.get("operation", "").upper()
        if op == "CREATE": created_files.append(filepath)
        elif op == "MODIFY": modified_files.append(filepath)
        elif op == "DELETE": deleted_files.append(filepath)
            
    registry[run_id] = {
        "issue_id": issue_id, "title": title,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "SUCCESS" if success else "FAILED",
        "commit_hash": commit_hash,
        "impact": {"created": created_files, "modified": modified_files, "deleted": deleted_files}
    }
    try:
        with open(registry_file, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=4, ensure_ascii=False)
        print(f"[AUDIT] Registro transaccional guardado en '{registry_file}'")
    except Exception as e:
        print(f"[WARN] No se pudo actualizar el JSON de trazabilidad: {e}")

# =====================================================================
# FUNCION DE ANALISIS ESTATICO DE CALIDAD (RUFF AUTO-FIX Y VULTURE BLINDADO)
# =====================================================================
def run_static_analysis(generated_filepaths):
    """
    Ejecuta Ruff (Auto-fix + Linter) y Vulture (detector de código muerto)
    de forma nativa sobre los archivos generados en disco.
    Filtra los archivos de pruebas unitarias de Vulture para mitigar falsos positivos.
    """
    success = True
    report = ""
    
    py_files = [f for f in generated_filepaths if f.endswith(".py") and os.path.exists(f)]
    if not py_files: return True, "No hay archivos Python para validacion estatica."
        
    print(f"[LINTER] Ejecutando Auto-Fixer y analizando {len(py_files)} archivos con Ruff y Vulture...")
    
    # 1 y 2. Ejecutar Ruff Check con auto-fix nativo para estilo en todo el ecosistema
    for filepath in py_files:
        subprocess.run([sys.executable, "-m", "ruff", "check", "--fix", filepath], capture_output=True, text=True)
    for filepath in py_files:
        result = subprocess.run([sys.executable, "-m", "ruff", "check", filepath], capture_output=True, text=True)
        if result.returncode != 0:
            success = False
            report += f"\n[Ruff Check] Errores de estilo criticos en '{filepath}':\n{result.stdout or result.stderr}"
            
    # 3. Ejecutar Vulture (Detector de codigo muerto) EXCLUSIVAMENTE en archivos de produccion lógicos
    prod_files = [f for f in py_files if "test_" not in f and "tests/" not in f]
    if prod_files:
        result_v = subprocess.run([sys.executable, "-m", "vulture"] + prod_files, capture_output=True, text=True)
        if result_v.returncode != 0:
            success = False
            report += f"\n[Vulture Detector] Codigo muerto detectado:\n{result_v.stdout or result_v.stderr}"
        
    return success, report

# =====================================================================
# CAPA DE VALIDACIÓN DE CALIDAD DE CÓDIGO (NUEVO)
# =====================================================================
def validate_code_quality(code: str, filepath: str) -> tuple[bool, str]:
    """
    Valida la sintaxis y el cumplimiento de políticas de tipado estricto usando AST.
    Retorna (es_valido: bool, mensaje_error: str).
    """
    # 1. Verificación de sintaxis básica
    try:
        tree = ast.parse(code, filename=filepath)
    except SyntaxError as se:
        return False, f"ERROR DE SINTAXIS: El código no es Python válido. Detalle: {se}"

    # 2. Verificación de Type Hints en todas las funciones y métodos
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Validar argumentos
            for arg in node.args.args:
                if arg.arg not in ('self', 'cls') and arg.annotation is None:
                    errors.append(f"Argumento '{arg.arg}' en la función '{node.name}' (línea {arg.lineno}) no tiene type hint.")
            # Validar retorno (excepto en constructores)
            if node.returns is None and node.name != '__init__':
                errors.append(f"La función '{node.name}' (línea {node.lineno}) no tiene un type hint de retorno (ej: -> str).")

    if errors:
        return False, "ERROR DE CALIDAD DE CÓDIGO (FALTA DE TIPADO ESTRICTO):\n" + "\n".join(errors)

    return True, ""

# =====================================================================
# FASES DEL PIPELINE DE ARQUITECTURA EVOLUTIVA
# =====================================================================
def fetch_issue(issue_id):
    print(f"\n[GITHUB] Leyendo requisitos en el Issue #{issue_id}...")
    issue = repo.get_issue(number=issue_id)
    return issue.title, issue.body

def agent_analyze_and_design(title, description):
    repo_map = context_manager.generate_repository_map()
    
    prompt = f"""
    Actúas como el Arquitecto de Software Principal. Tu objetivo es diseñar una solución técnica estructurada, elegante, testable y lista para producción que cumpla con la especificación del Issue.

    🛠️ 1. REGLAS DE RECONCILIACIÓN Y TOPOLOGÍA (TU CONTRATO PRINCIPAL):
    - ALINEACIÓN ESTRICTA: Reconcilia los requerimientos funcionales con la 'TOPOLOGÍA EN DISCO ACTUAL'. Utiliza obligatoriamente las clases y métodos existentes.
    - INSPECCIÓN DE FIRMAS OBLIGATORIA: Examina meticulosamente el mapa (AST) adjunto para ver si el método '__init__' de las clases objetivo declara parámetros. Queda terminantemente PROHIBIDO pasar parámetros con nombre (kwargs) si la estructura no coincide con la firma real dictada por el mapa.

    🏗️ 2. PRINCIPIOS DE ARQUITECTURA Y DISEÑO (CLEAN CODE):
    - PROTECCIÓN ESTÁTICA EXTREMA (VULTURE): Para todo archivo de producción nuevo, exige obligatoriamente la declaración explícita de '__all__ = ["NombreClase", "nombre_funcion"]' al inicio del archivo. Esto certifica al linter que son interfaces públicas blindadas.

    ESPECIFICACIÓN FUNCIONAL DEL ISSUE:
    - Título: {title}
    - Requisitos: {description}

    TOPOLOGÍA EN DISCO ACTUAL Y FIRMAS AST:
    --- INICIO MAPA ---
    {repo_map if repo_map else "[Repositorio limpio]"}
    --- FIN MAPA ---
    """
    
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ProjectDesign,
        temperature=0.1
    )
    response = ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt, config=config)
    return json.loads(response.text)

def agent_implement_code(action, design, generated_so_far, feedback=""):
    print(f"[CODER] Procesando '{action['filepath']}' | Operacion: {action['operation']} con {MODEL_HEAVY}...")
    contexto_acumulado = "".join([f"\n\n# Archivo: '{path}'\n{code}\n" for path, code in generated_so_far.items()])
    contexto_dependencias = "".join([f"\n\n# Codigo de referencia ('{dep}'):\n{context_manager.get_file_content(dep)}\n" for dep in design.get("dependencies", [])])
    feedback_prompt = f"\n\n[ALERT] REPORTE DE FALLOS O RECHAZOS DE LINTER EN ESTE ARCHIVO:\n{feedback}" if feedback else ""

    # --- INYECCIÓN DE CÓDIGO EXISTENTE PARA OPERACIONES DE MODIFICACIÓN ---
    existing_code_context = ""
    if action['operation'].upper() == 'MODIFY':
        existing_code = context_manager.get_file_content(action['filepath'])
        existing_code_context = f"\n\nCÓDIGO ACTUAL DEL ARCHIVO (PARA MODIFICAR):\n{MD_FENCE}python\n{existing_code}\n{MD_FENCE}\n"

    prompt = f"""
    Implementa o refactoriza el contenido del archivo: '{action['filepath']}'
    Tipo de archivo: {action['file_type']}
    Operacion requerida: {action['operation']}
    
    {existing_code_context}
    ESPECIFICACIONES TECNICAS DEL ARQUITECTO:
    - Firmas y estructuras esperadas: {action['signatures']}
    - Instrucciones precisas de codificacion: {action['instructions']}
    {contexto_acumulado}{contexto_dependencias}{feedback_prompt}

    📜 ESTÁNDARES OBLIGATORIOS:
    1. EXPORTACIÓN EXPLÍCITA (__all__): Todo archivo lógico de producción debe incluir '__all__ = [...]' al inicio con los nombres de las clases o métodos principales para evitar el bloqueo del linter Vulture.
    2. TIPADO ESTRICTO (Type Hints): Todas las funciones y métodos deben tener type hints para sus argumentos y valores de retorno (ej. `def func(arg: str) -> bool:`).
    3. CERO CAPTURAS GENÉRICAS (PEP 8): Prohibido usar 'except Exception:' o silenciamientos ciegos ('except: pass').

    Devuelve UNICAMENTE el codigo limpio dentro de un bloque markdown usando {MD_FENCE}. No añadas texto explicativo fuera del bloque.
    """
    response = ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt, config=types.GenerateContentConfig(temperature=0.0))
    ext = action['filepath'].split('.')[-1]
    return extract_code(response.text, ext if ext in ["python", "json", "ini", "yaml"] else "python")

def agent_generate_tests(action, production_code_context):
    print(f"[QA] Disenando suite de pruebas unitarias para '{action['filepath']}'...")
    prompt = f"""
    Escribe una suite de pruebas unitarias exhaustiva con 'pytest' para validar el archivo: '{action['filepath']}'
    Instrucciones del arquitecto: {action['instructions']}

    CONTEXTO DEL CODIGO DE PRODUCCION SISTEMICO:
    {production_code_context}

    📜 ESTÁNDARES DE DISEÑO DE TESTING INDUSTRIAL:
    1. INDEPENDENCIA Y AISLAMIENTO: Usa 'unittest.mock.patch' para aislar dependencias externas o de I/O.
    2. TIPADO ESTRICTO OBLIGATORIO: Todas las funciones de test y los argumentos (incluyendo los mocks inyectados por `@patch`) deben tener type hints (ej. `def test_algo(mock_obj: Mock) -> None:`).
    3. TESTEO EXHAUSTIVO DE INTERFACES PÚBLICAS: Es obligatorio importar, instanciar y usar explícitamente todas las clases o funciones declaradas en la variable '__all__' del archivo de producción objetivo para reducir la tasa de código muerto de Vulture a 0%.

    Devuelve UNICAMENTE el codigo de pytest en un bloque markdown usando {MD_FENCE}python.
    """
    response = ai_client.models.generate_content(model=MODEL_LIGHT, contents=prompt)
    return extract_code(response.text, "python")

def run_local_tests(test_filename):
    print(f"[RUNNER] Ejecutando pytest nativo para {test_filename}...")
    result = subprocess.run([sys.executable, "-m", "pytest", "-v", test_filename], capture_output=True, text=True)
    return result.returncode == 0, result.stdout + "\n" + result.stderr

def agent_security_audit(generated_files):
    print(f"\n[SEC] Realizando auditoria de robustez del ecosistema modular con {MODEL_HEAVY}...")
    contexto_auditoria = "".join([f"\n\nArchivo: '{path}'\n{MD_FENCE}python\n{code}\n{MD_FENCE}\n" for path, code in generated_files.items()])
        
    prompt = f"""
    Analiza la calidad de diseno, desacoplamiento, programacion defensiva y control de excepciones del siguiente lote transaccional de archivos:
    {contexto_auditoria}

    Escribe un dictamen de robustez industrial.
    Al final de tu reporte, concluye de forma obligatoria con:
    - 'ESTADO: APROBADO' si el codigo es seguro para produccion.
    - 'ESTADO: RECHAZADO' si la modularidad presenta fallos criticos o imports circulares.
    """
    config = types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=2048), temperature=0.2)
    try:
        response = ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt, config=config)
        print("-" * 60 + f"\n{response.text}\n" + "-" * 60)
        return "ESTADO: APROBADO" in response.text, response.text
    except Exception as e: return False, f"Fallo en la ejecucion de la API de auditoria: {e}"

# =====================================================================
# AGENTES DE DOCUMENTACION DINAMICA (DOCS-AS-CODE)
# =====================================================================
def agent_generate_execution_report(design, generated_files, pytest_log, sast_report, issue_id, title):
    print(f"\n[DOCS] Compilando reporte de ejecucion para Issue #{issue_id}...")
    contexto_archivos = "".join([f"\n\n### Archivo: `{path}`\n{MD_FENCE}python\n{code}\n{MD_FENCE}\n" for path, code in generated_files.items()])
    prompt = f"""
    Eres un documentador tecnico senior. Escribe un reporte de ingenieria de software en Markdown detallando los resultados de la tarea:
    Issue #{issue_id}: '{title}'

    DATOS DE LA EJECUCION:
    - Justificacion de Arquitectura: {design['architecture_justification']}
    - Cambios realizados: {contexto_archivos}
    - Pruebas locales: {MD_FENCE}\n{pytest_log}\n{MD_FENCE}
    - Auditoria de robustez: {MD_FENCE}\n{sast_report}\n{MD_FENCE}

    Devuelve UNICAMENTE el codigo Markdown.
    """
    response = ai_client.models.generate_content(model=MODEL_LIGHT, contents=prompt)
    os.makedirs("docs/reports", exist_ok=True)
    report_path = f"docs/reports/run_issue_{issue_id}.md"
    with open(report_path, "w", encoding="utf-8") as f: f.write(response.text.strip())
    print(f"[DOCS] Reporte guardado en '{report_path}'")
    return report_path

def agent_update_architecture_doc(design, repo_map):
    print(f"\n[ARCHITECT] Sincronizando evolucion del manual de arquitectura...")
    arch_file = "docs/ARCHITECTURE.md"
    existing_content = open(arch_file, "r", encoding="utf-8").read() if os.path.exists(arch_file) else "[Crear desde cero]"
    prompt = f"""
    Eres el Arquitecto de Soluciones de Olivia. Actualiza 'docs/ARCHITECTURE.md'.
    Refactorizaciones: {design['architecture_justification']}
    NUEVA TOPOLOGIA EN DISCO: {MD_FENCE}\n{repo_map}\n{MD_FENCE}
    PREVIO: {existing_content}
    
    Devuelve UNICAMENTE el Markdown definitivo.
    """
    response = ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt)
    os.makedirs("docs", exist_ok=True)
    with open(arch_file, "w", encoding="utf-8") as f: f.write(response.text.strip())
    return arch_file

def agent_update_user_manual(issue_id, title, description, design, generated_files):
    print(f"\n[TECHNICAL-WRITER] Evaluando impacto operativo del Issue #{issue_id} en el Manual de Usuario...")
    manual_path = "docs/USER_MANUAL.md"
    existing_content = open(manual_path, "r", encoding="utf-8").read() if os.path.exists(manual_path) else "[Vacio]"
    contexto_cambios = "".join([f"\nArchivo modificado: {p}\n" for p in generated_files.keys()])

    prompt = f"""
    Actúas como un Redactor Técnico Senior. Actualiza el manual de usuario ('docs/USER_MANUAL.md') de forma incremental.
    - Tarea: Issue #{issue_id} - '{title}' | Descripción: {description} | Archivos: {contexto_cambios}
    ESTADO ACTUAL: {existing_content}

    Evalúa si afecta la UX. Si es técnico interno, devuelve el manual intacto. Si impacta, traduce la mejora a operativas sin usar jerga de código.
    Devuelve UNICAMENTE el Markdown definitivo.
    """
    response = ai_client.models.generate_content(
        model=MODEL_HEAVY, contents=prompt,
        config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=1024), temperature=0.2)
    )
    clean_text = response.text.strip()
    if clean_text.startswith(f"{MD_FENCE}markdown"): clean_text = clean_text[11:]
    if clean_text.endswith(MD_FENCE): clean_text = clean_text[:-3]
    os.makedirs("docs", exist_ok=True)
    with open(manual_path, "w", encoding="utf-8") as f: f.write(clean_text.strip())
    return manual_path

# =====================================================================
# AGENTE CLÍNICO DE DIAGNÓSTICO DE FALLOS CON GOBERNANZA AUTOMATIZADA
# =====================================================================
def agent_analyze_pipeline_failure(issue_id, title, description, design, generated_files, pytest_log, static_log, sast_report):
    print(f"\n[POST-MORTEM] 🧠 El ciclo colapsó. Invocando Diagnóstico Clínico de IA...")
    contexto_archivos = "".join([f"\n### Archivo: `{path}`\n{MD_FENCE}python\n{code}\n{MD_FENCE}\n" for path, code in generated_files.items()])

    prompt = f"""
    Actúas como un Ingeniero Principal de DevOps y Experto en Diagnóstico de Agentes. El pipeline falló tras agotar los reintentos de calidad.
    Realiza una autopsia técnica y emite un reporte Markdown detallado sobre qué causó el bloqueo.
    
    Contexto: Issue #{issue_id}: '{title}' | Spec: {description}
    CÓDIGO GENERADO: {contexto_archivos}
    ERRORES: Pytest: {MD_FENCE}\n{pytest_log}\n{MD_FENCE} | Linter: {MD_FENCE}\n{static_log}\n{MD_FENCE} | SAST: {MD_FENCE}\n{sast_report}\n{MD_FENCE}

    Escribe el Reporte Clínico en Markdown con Análisis de Causa Raíz y Recomendación Inmediata al humano.

    🚨 INSTRUCCIÓN CRÍTICA DE GOBERNANZA AUTOMATIZADA 🚨:
    Si determinas que la causa raíz del fallo NO es un mero despiste tipográfico de sintaxis, sino que el Agente Coder necesita directrices explícitas en los Criterios de Aceptación Técnicos para superar una barrera estricta o trampa de herramientas (ej. inyectar comentarios de bypass como '# vulture: ignore', modificar firmas específicas o mitigar asimetrías de testing), DEBES incluir obligatoriamente la siguiente etiqueta exacta en una línea independiente al final de tu reporte:
    [ACTION: DELEGATE_TO_PO]
    
    Si el error es puramente técnico subsanable sin alterar las especificaciones, omite la etiqueta.
    """
    try:
        response = ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt)
        print("\n" + "="*80 + "\n🚨 REPORTE DE AUTODIAGNÓSTICO POST-MORTEM GENERADO POR LA IA 🚨\n" + "="*80)
        print(response.text.strip() + "\n" + "="*80 + "\n")
        return response.text.strip()
    except Exception as e: return f"Error de diagnostico: {e}"

# =====================================================================
# AGENTE DE REVISIÓN DE CÓDIGO (NUEVO)
# =====================================================================
def agent_code_reviewer(design, generated_files, issue_desc) -> tuple[bool, str]:
    """
    Un agente que actúa como un revisor de código senior.
    Valida que el código generado se adhiere semánticamente a las instrucciones.
    """
    print(f"[CODE-REVIEW] 🧐 Realizando revisión de código semántica con {MODEL_HEAVY}...")
    contexto_codigo = "".join([f"\n\n### Archivo: `{path}`\n{MD_FENCE}python\n{code}\n{MD_FENCE}\n" for path, code in generated_files.items()])
    
    prompt = f"""
    Actúas como un Ingeniero de Software Principal realizando una revisión de código. Tu tarea es verificar que el código generado cumple ESTRICTAMENTE con las instrucciones del arquitecto Y con los requisitos originales del Issue.

    **Requisitos Originales del Issue:**
    {issue_desc}

    **Plan del Arquitecto:**
    {json.dumps(design, indent=2)}

    **Código Generado para Revisión:**
    {contexto_codigo}

    Busca discrepancias lógicas, como manejo incorrecto de excepciones, violación de principios (ej. Fail-Fast), o pruebas que no validan el requisito real. Si todo es correcto, responde únicamente con "APROBADO". Si encuentras un problema, describe el fallo de forma clara y concisa para que el Coder pueda corregirlo.
    """
    response = ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt, config=types.GenerateContentConfig(temperature=0.0))
    report = response.text.strip()
    return "APROBADO" in report.upper(), report

# =====================================================================
# GIT FLOW DE ALTA TRAZABILIDAD CON RUN ID
# =====================================================================
def deploy_to_github(design, generated_files, report_path, arch_path, user_manual_path, issue_id):
    print("\n[DEVOPS] Inicializando PR de alta trazabilidad...")
    branch_name = f"agent-refactor-issue-{issue_id}"
    run_id = f"RUN-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    commit_title = f"feat(issue-{issue_id}): [{run_id}] refactorizacion y solucion modular evolutiva"
    commit_body = f"Trazabilidad: {run_id}\nJustificacion: {design['architecture_justification']}"
    
    try:
        subprocess.run(["git", "checkout", "-b", branch_name], check=True, capture_output=True)
        for action in design['actions']:
            if action['operation'].upper() == "DELETE" and os.path.exists(action['filepath']):
                subprocess.run(["git", "rm", action['filepath']], capture_output=True)
                
        for path in generated_files.keys(): subprocess.run(["git", "add", path], capture_output=True)
        subprocess.run(["git", "add", report_path, arch_path, user_manual_path], check=True)
        subprocess.run(["git", "commit", "-m", commit_title, "-m", commit_body], check=True)
        
        commit_hash = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        write_transactional_metadata(run_id, issue_id, design.get("architecture_justification", "Refactor"), True, design, commit_hash)
        
        print("[DEVOPS] Empujando rama de refactorizacion a GitHub...")
        subprocess.run(["git", "push", "origin", branch_name, "--force"], check=True)
        
        fresh_repo = Github(auth=Auth.Token(os.getenv("GITHUB_TOKEN"))).get_repo(repo_path)
        pr = fresh_repo.create_pull(title=f"[Agente SDLC] [{run_id}] Issue #{issue_id}", body=f"Cambio autónomo (Run {run_id}).\nCloses #{issue_id}", head=branch_name, base="main")
        
        print("\n" + "=" * 80 + f"\n[SUCCESS] Pull Request creado: {pr.html_url}\n" + "=" * 80)
        print(f"🚀 ATENCIÓN HUMANO: Para probar localmente AHORA MISMO, ejecuta:\ngit fetch origin && git checkout {branch_name}\n" + "=" * 80 + "\n")
        
        try:
            issue = fresh_repo.get_issue(number=issue_id)
            for lbl in ["status:in-progress", "ai:ready-to-code"]:
                if lbl in [l.name for l in issue.labels]: issue.remove_from_labels(lbl)
            try: fresh_repo.get_label("status:pending-review")
            except: fresh_repo.create_label("status:pending-review", "d4c5f9")
            issue.add_to_labels("status:pending-review")
        except: pass
    except Exception as e: print(f"[ERROR] Critico en despliegue: {e}")
    finally:
        print("[DEVOPS] Limpiando entorno y volviendo a la rama principal...")
        subprocess.run(["git", "fetch", "origin"], capture_output=True)
        subprocess.run(["git", "checkout", "main"], capture_output=True)

def ensure_git_setup():
    print("[DEVOPS] Verificando Git local...")
    if not os.path.exists(".git"):
        subprocess.run(["git", "init"], check=True, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], check=True, capture_output=True)
    remotes = subprocess.run(["git", "remote"], capture_output=True, text=True)
    if "origin" not in remotes.stdout:
        remote_url = f"https://{os.getenv('GITHUB_TOKEN')}@github.com/{os.getenv('REPO_OWNER')}/{os.getenv('REPO_NAME')}.git"
        subprocess.run(["git", "remote", "add", "origin", remote_url], check=True, capture_output=True)
    if subprocess.run(["git", "log", "-1"], capture_output=True).returncode != 0:
        subprocess.run(["git", "fetch", "origin"], capture_output=True)
        subprocess.run(["git", "pull", "origin", "main", "--allow-unrelated-histories", "--no-rebase"], capture_output=True)
    else:
        subprocess.run(["git", "checkout", "main"], capture_output=True)
        subprocess.run(["git", "pull", "origin", "main"], capture_output=True)

# =====================================================================
# COORDINADOR DEL WORKFLOW CENTRAL UNIFICADO
# =====================================================================
# =====================================================================
# COORDINADOR DEL WORKFLOW CENTRAL UNIFICADO
# =====================================================================
def run_pipeline(issue_id):
    ensure_git_setup()
    try:
        issue_to_update = repo.get_issue(number=issue_id)
        if "ai:ready-to-code" in [l.name for l in issue_to_update.labels]: 
            issue_to_update.remove_from_labels("ai:ready-to-code")
        try: 
            repo.get_label("status:in-progress")
        except: 
            repo.create_label("status:in-progress", "fef2c0")
        issue_to_update.add_to_labels("status:in-progress")
    except: 
        pass

    title, desc = fetch_issue(issue_id)
    print(f"\n[INFO] Pipeline iniciado - Issue #{issue_id}: '{title}'")
    
    attempt, max_attempts, pipeline_passed = 1, 3, False
    generated_files, feedback_dict = {}, {}
    sast_report, pytest_log_acumulado, last_static_log, combined_feedback = "", "", "", ""
    design = None

    while attempt <= max_attempts and not pipeline_passed:
        print(f"\n[INFO] Ejecutando ciclo de desarrollo (Intento {attempt}/{max_attempts})...")
        generated_files.clear()

        if attempt == 1:
            print("[ARCHITECT] Diseñando plan estructural base...")
            design = agent_analyze_and_design(title, desc)
        elif combined_feedback:
            print("[ARCHITECT] 🧠 Re-planificando diseño basado en fallos acumulados...")
            design = agent_analyze_and_design(title, f"{desc}\n\n⚠️ REPORTE DEL INTENTO ANTERIOR:\n{combined_feedback}")
            
        print(f"[INFO] Justificacion del Arquitecto:\n{design.get('architecture_justification', 'N/A')}\n")
        
        code_actions = [a for a in design.get('actions', []) if a['operation'].upper() in ["CREATE", "MODIFY"] and a['file_type'] != 'test']
        test_actions = [a for a in design.get('actions', []) if a['operation'].upper() in ["CREATE", "MODIFY"] and a['file_type'] == 'test' and not a['filepath'].endswith("__init__.py")]
        
        for act in [a for a in design.get('actions', []) if a['operation'].upper() == "DELETE"]:
            if os.path.exists(act['filepath']): 
                os.remove(act['filepath'])
        
        # --- BUCLE DE IMPLEMENTACIÓN CON BLINDAJE AST (PYTHON PURO) ---
        syntax_passed = True
        for act in code_actions + test_actions:
            path = act['filepath']
            if act in code_actions: 
                code = agent_implement_code(act, design, generated_files, feedback_dict.get(path, ""))
            else: 
                code = agent_generate_tests(act, "\n\n".join([f"# Archivo: {p}\n{c}" for p, c in generated_files.items()]))
            
            # --- CAPA DE SEGURIDAD: VERIFICACIÓN AST DE PYTHON PURO ---
            is_valid, quality_report = validate_code_quality(code, path)
            if not is_valid:
                print(f"[ERROR DE CALIDAD] El código para '{path}' fue rechazado: {quality_report}")
                feedback_dict[path] = quality_report
                syntax_passed = False
                break
            # ---------------------------------------------------------
            
            generated_files[path] = code
            dir_name = os.path.dirname(path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
                init_f = os.path.join(dir_name, "__init__.py")
                if not os.path.exists(init_f): 
                    open(init_f, "w", encoding="utf-8").write("# Package\n")
            open(path, "w", encoding="utf-8").write(code)

        if not syntax_passed:
            print("[WARN] Error de calidad de código detectado por AST antes de testing. Reintentando...")
            combined_feedback = f"FALLO DE CALIDAD DE CÓDIGO (AST):\n" + "\n".join([f"{k}: {v}" for k, v in feedback_dict.items()])
            attempt += 1
            continue
        # -------------------------------------------------------------

        # --- NUEVO QUALITY GATE: REVISIÓN DE CÓDIGO POR IA ---
        review_passed, review_report = agent_code_reviewer(design, generated_files, desc)
        if not review_passed:
            print(f"[WARN] Rechazo del Code Reviewer: {review_report}")
            combined_feedback = f"FALLO DE REVISIÓN DE CÓDIGO:\n{review_report}"
            # Asignar el feedback a todos los archivos para que el arquitecto lo vea
            for path in generated_files: feedback_dict[path] = review_report
            attempt += 1
            continue
                
        success_qa, pytest_log_acumulado, feedback_dict = True, "", {}
        for act in test_actions:
            path = act['filepath']
            success, log = run_local_tests(path)
            pytest_log_acumulado += f"\n--- {path} ---\n{log}"
            if not success:
                success_qa = False
                feedback_dict[path] = log
                
        if not success_qa:
            print("[WARN] Pruebas unitarias fallaron. Realimentando sistema...")
            combined_feedback = f"FALLO DE QA (PYTEST):\n{pytest_log_acumulado}"
            attempt += 1
            continue
            
        success_static, log_static = run_static_analysis(list(generated_files.keys()))
        if not success_static:
            print("[WARN] Rechazo estatico tras intento de auto-fix. Linter/Vulture bloquea subida.")
            last_static_log, combined_feedback = log_static, f"FALLO ESTÁTICO (LINTER/VULTURE):\n{log_static}"
            for act in code_actions: 
                feedback_dict[act['filepath']] = f"CODIGO RECHAZADO:\n{log_static}"
            attempt += 1
            continue
            
        is_secure, sast_report = agent_security_audit(generated_files)
        if not is_secure:
            print("[WARN] Rechazo de Robustez Estructural (SAST).")
            combined_feedback = f"FALLO SAST:\n{sast_report}"
            for act in code_actions: 
                feedback_dict[act['filepath']] = sast_report
            attempt += 1
            continue
            
        print("[INFO] Todos los Quality Gates pasados.")
        pipeline_passed = True
        
    if not pipeline_passed:
        error_msg = f"El pipeline colapsó tras {max_attempts} reintentos."
        print(f"\n[ERROR] {error_msg}")
        pm_report = agent_analyze_pipeline_failure(issue_id, title, desc, design or {}, generated_files, pytest_log_acumulado, last_static_log, sast_report)
        
        # --- LOGICA DE DELEGACION AUTOMATIZADA AL PO AGENT ---
        if "[ACTION: DELEGATE_TO_PO]" in pm_report:
            print("\n[ORCHESTRATOR] 🚨 Problema funcional/estructural detectado. Delegando de forma autonoma al PO Agent...")
            try:
                subprocess.run([sys.executable, "po_agent.py", "--refine-issue", str(issue_id), "--pm-report", pm_report], check=True)
                
                # Modificar etiquetas a validacion requerida
                issue = repo.get_issue(number=issue_id)
                if "status:in-progress" in [l.name for l in issue.labels]: 
                    issue.remove_from_labels("status:in-progress")
                try: 
                    repo.get_label("po:human-validation-required")
                except: 
                    repo.create_label("po:human-validation-required", "fbca04")
                issue.add_to_labels("po:human-validation-required")
                print(f"[ORCHESTRATOR] ⏸️ El PO Agent ha renegociado el Issue #{issue_id}. A la espera de tu firma en GitHub.")
            except Exception as e: 
                print(f"[ERROR] Fallo al delegar al PO Agent: {e}")
        else:
            write_local_log(issue_id, title, False, f"{error_msg}\n\n### REPORTE POST-MORTEM:\n{pm_report}")
        return
        
    report = agent_generate_execution_report(design, generated_files, pytest_log_acumulado, sast_report, issue_id, title)
    arch = agent_update_architecture_doc(design, context_manager.generate_repository_map())
    man = agent_update_user_manual(issue_id, title, desc, design, generated_files)
    
    try:
        deploy_to_github(design, generated_files, report, arch, man, issue_id)
        write_local_log(issue_id, title, True, "Despliegue y PR completado.")
    except Exception as e: 
        write_local_log(issue_id, title, False, f"Fallo Git: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Framework de Agentes Autonomos SDLC")
    parser.add_argument("--issue", type=int, required=True, help="Numero del Issue a procesar")
    args = parser.parse_args()
    run_pipeline(args.issue)