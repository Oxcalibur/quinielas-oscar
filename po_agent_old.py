"""
Product Owner Agent (Compuerta 1 - Olivia's Legacy 2026)
Convierte requisitos funcionales puros en un backlog de Épicas y sub-issues en GitHub.
Usa gobernanza asíncrona nativa mediante etiquetas de aprobación en GitHub.
"""

# Parche de seguridad SSL
import truststore

try:
    truststore.inject_into_ssl()
except AttributeError:
    import urllib3
    truststore.inject_into_urllib3()

import argparse
import ast
import json
import os
import re
import sys

from dotenv import load_dotenv
from github import Auth, Github
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# Cargar variables de entorno
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

# Inicializar clientes
auth = Auth.Token(os.getenv("GITHUB_TOKEN"))
github_client = Github(auth=auth)
repo_path = f"{os.getenv('REPO_OWNER')}/{os.getenv('REPO_NAME')}"
repo = github_client.get_repo(repo_path)

ai_client = genai.Client()
MODEL_HEAVY = "gemini-3.1-pro-preview"

# =====================================================================
# ESQUEMAS PYDANTIC PARA ESTRUCTURACIÓN DE ISSUES
# =====================================================================
class ProposedSubIssue(BaseModel):
    title: str = Field(description="Título claro y descriptivo del Issue (ej. 'Implementar clase base Entity en core/entities/base.py').")
    body: str = Field(description="Cuerpo detallado del Issue en Markdown. Debe incluir especificación funcional, requisitos técnicos y pruebas sugeridas.")
    priority: str = Field(description="Prioridad de desarrollo: 'high', 'medium' o 'low'.")
    estimated_files: list[str] = Field(description="Lista de archivos que se estiman crear o modificar para esta tarea específica.")

class BacklogProposal(BaseModel):
    epic_title: str = Field(description="Título de la Épica que agrupa el backlog (ej. 'Epic: Cimientos del Motor de Olivia\\'s Legacy').")
    epic_justification: str = Field(description="Justificación detallada de por qué se divide el proyecto en estas tareas y cómo escala el acoplamiento.")
    proposed_issues: list[ProposedSubIssue] = Field(description="Colección ordenada secuencialmente de sub-issues técnicos de desarrollo.")

class CodebaseScanner:
    """Escanea el repositorio real para que el PO conozca la jerga técnica ya implementada."""
    def __init__(self, root_path="."):
        self.root_path = root_path
        self.ignored_dirs = {".git", "venv", "__pycache__", ".pytest_cache", "docs", ".env"}

    def get_existing_vocabulary(self) -> str:
        repo_map = []
        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs]
            for file in files:
                if file.endswith(".py") and file not in ["orchestrator.py", "po_agent.py", "user_manual_generator.py"]:
                    full_path = os.path.join(root, file)
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            node = ast.parse(f.read())
                        for child in node.body:
                            if isinstance(child, ast.ClassDef):
                                repo_map.append(f"Clase existente: {child.name} (en {file})")
                    except Exception:
                        pass
        return "\n".join(repo_map) if repo_map else "[Repositorio limpio sin clases aún]"

# =====================================================================
# ACCIONES DE GOBERNANZA
# =====================================================================

def create_labels_if_not_exist():
    """Asegura que las etiquetas de gobernanza estén disponibles en GitHub."""
    labels = {
        "gate:backlog-proposal": "f29513",  # Naranja
        "gate:approved": "0e8a16",          # Verde
        "ai:ready-to-code": "1d76db"        # Azul
    }
    for name, color in labels.items():
        try:
            repo.get_label(name)
        except Exception:
            repo.create_label(name, color)
            print(f"🏷️  [Labels] Creada etiqueta de gobernanza: '{name}'")

def propose_backlog(requirements_file):
    """Fase A: Lee requisitos en markdown, llama a Gemini PO y crea la Épica en GitHub."""
    if not os.path.exists(requirements_file):
        print(f"❌ Error: El archivo de requisitos '{requirements_file}' no existe.")
        sys.exit(1)
        
    with open(requirements_file, "r", encoding="utf-8") as f:
        req_text = f.read()
        
    # --- NUEVO: Captura del estado real del código ---
    scanner = CodebaseScanner()
    existing_vocab = scanner.get_existing_vocabulary()
        
    print("\n🧠 [PO Agent] Analizando requisitos funcionales y diseñando descomposición técnica...")
    
    prompt = f"""
    Actúas como un Product Owner y Arquitecto de Soluciones Senior bajo metodologías ágiles. Tu objetivo es tomar una especificación de requerimientos funcionales y estructurar un plan de desarrollo incremental (Product Backlog).
    
    📜 DIRECTIVAS DE GOBERNANZA Y BUENAS PRÁCTICAS DE REQUISITOS:
    1. RECONCILIACIÓN ESTRICTA DE DOMINIO: Es obligatorio revisar el vocabulario y las clases que ya existen en el repositorio. Redacta los sub-issues usando EXCLUSIVAMENTE los nombres de componentes, paquetes y entidades reales en producción. Queda prohibido usar nombres genéricos de la industria si ya existe un equivalente físico implementado.
    2. DISEÑO INCREMENTAL (INVEST-READY): Cada sub-issue debe cumplir con los criterios INVEST (Independiente, Negociable, Valioso, Estimable, Pequeño, Testeable). No mezcles responsabilidades en una sola tarea (ej. separa la lógica de captura de entrada de la lógica de renderizado visual).
    3. TRAZABILIDAD VISUAL: Estructura los cuerpos de las tareas delimitando con total claridad el PROPÓSITO de negocio y los CRITERIOS DE ACEPTACIÓN TÉCNICOS legibles tanto para humanos como para otros agentes de IA.

    MÓDULOS Y CLASES EXISTENTES EN EL REPOSITORIO (CONTRATO DE JUEGO ACTUAL):
    {existing_vocab}
    
    ESPECIFICACIÓN DE NEGOCIO A DESCOMPONER:
    ---
    {req_text}
    ---
    """
    
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=BacklogProposal,
        temperature=0.2
    )
    
    response = ai_client.models.generate_content(
        model=MODEL_HEAVY,
        contents=prompt,
        config=config
    )
    
    proposal = json.loads(response.text or "{}")
    
    # Asegurar etiquetas
    create_labels_if_not_exist()
    
    # Construir el cuerpo de la Épica con metadatos estructurados
    epic_body = f"""## 🎯 Justificación Arquitectónica del Backlog
{proposal['epic_justification']}

---

## 📋 Propuesta de Sub-Tareas (Sub-Issues)
A continuación se detallan las tareas lógicas propuestas para el desarrollo de esta funcionalidad. Revísalas minuciosamente en esta Épica de Planificación.

"""
    # Guardamos los metadatos de los issues propuestos dentro del cuerpo como un JSON oculto para recuperarlos al aprobar
    metadata = []
    for idx, sub in enumerate(proposal['proposed_issues'], 1):
        epic_body += f"### {idx}. {sub['title']} (Prioridad: `{sub['priority'].upper()}`)\n"
        epic_body += f"{sub['body']}\n\n"
        epic_body += f"**Archivos Estimados:** `{', '.join(sub['estimated_files'])}`\n\n---\n\n"
        
        metadata.append({
            "title": sub['title'],
            "body": f"Pertenece a la Épica de Planificación de esta funcionalidad.\n\n### 📝 Especificación Técnica:\n{sub['body']}\n\n**Archivos implicados:** `{', '.join(sub['estimated_files'])}`",
            "priority": sub['priority']
        })
        
    # EVITAR DEGRADACIÓN DE MARKDOWN: Protegemos la inyección de la etiqueta de comentarios
    comment_open = "<" + "!--"
    comment_close = "--" + ">"
    epic_body += f"\n\n{comment_open} BACKLOG_METADATA_START\n{json.dumps(metadata, indent=2)}\nBACKLOG_METADATA_END {comment_close}"
    
    print("\n📤 [GitHub] Creando Épica de Planificación en el repositorio...")
    epic_issue = repo.create_issue(
        title=f"[ÉPICA] {proposal['epic_title']}",
        body=epic_body,
        labels=["gate:backlog-proposal"]
    )
    
    print("\n🎉 ¡Propuesta de Backlog publicada con éxito en GitHub!")
    print(f"🔗 URL de la Épica: {epic_issue.html_url}")
    print("\n🚦 COMPUERTA 1 - ACCIÓN REQUERIDA:")
    print(f"1. Accede al Issue #{epic_issue.number} in tu navegador.")
    print("2. Revisa el plan técnico, las firmas lógicas y los módulos estimados.")
    print("3. Si estás de acuerdo, añade de forma manual la etiqueta 'gate:approved' en GitHub.")
    print(f"4. Una vez etiquetado, ejecuta: python po_agent.py --approve-epic {epic_issue.number}")

def approve_and_deploy_backlog(epic_id):
    """Fase B: Verifica la etiqueta en la Épica, deserializa las tareas lógicas y las despliega."""
    print(f"\n🔍 [Gobernanza] Buscando Épica de Planificación #{epic_id} en GitHub...")
    try:
        epic_issue = repo.get_issue(number=epic_id)
    except Exception as e:
        print(f"❌ Error: No se pudo obtener el Issue #{epic_id}: {e}")
        sys.exit(1)
        
    # Verificar etiqueta de aprobación
    labels = [label.name for label in epic_issue.labels]
    if "gate:approved" not in labels:
        print(f"🛑 [Compuerta 1] Bloqueado: El Issue #{epic_id} no cuenta con la etiqueta 'gate:approved'.")
        print("Añádela en la interfaz web de GitHub antes de confirmar la aprobación.")
        sys.exit(1)
        
    print("🟢 [Compuerta 1] ¡Firma verificada! Deserializando especificaciones del backlog...")
    
    body = epic_issue.body
    
    # EVITAR DEGRADACIÓN DE MARKDOWN: Protegemos la expresión regular para que el chat no la limpie
    regex_pattern = "<" + r"!-- BACKLOG_METADATA_START\s*(.*?)\s*BACKLOG_METADATA_END --" + ">"
    match = re.search(regex_pattern, body, re.DOTALL)
    
    if not match:
        print("❌ Error crítico: No se encontraron metadatos de backlog estructurados en la Épica.")
        sys.exit(1)
        
    metadata_json = match.group(1)
    proposed_issues = json.loads(metadata_json)
    
    print(f"📌 Se han detectado {len(proposed_issues)} sub-tareas validadas por el humano. Desplegando...")
    
    for idx, sub in enumerate(proposed_issues, 1):
        # --- NUEVA MEJORA DE TRAZABILIDAD: INYECCIÓN DE ÉPICA PADRE EN EL TÍTULO ---
        title = f"[Épica #{epic_id}] Task {idx}: {sub['title']}"
        body_with_epic = f"Este sub-issue ha sido creado y aprobado bajo la Épica #{epic_id}.\n\n{sub['body']}"
        
        # Crear los sub-issues individuales listos para codificar
        created_issue = repo.create_issue(
            title=title,
            body=body_with_epic,
            labels=["ai:ready-to-code", f"priority:{sub['priority']}"]
        )
        print(f"  ↳ ✅ Creado Issue #{created_issue.number}: '{title}' | Listo para codificar.")
        
    # Retirar la etiqueta de propuesta y marcar la Épica como procesada
    try:
        epic_issue.remove_from_labels("gate:backlog-proposal")
    except Exception:
        pass
    print(f"\n🎉 ¡Proceso de Gobernanza completado! La Épica #{epic_id} está formalmente aprobada y su backlog desplegado.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestión de Backlog y Gobernanza Asíncrona")
    parser.add_argument("--requirements", type=str, help="Ruta al archivo Markdown de especificación funcional")
    parser.add_argument("--approve-epic", type=int, dest="approve_epic", help="Número de Issue de la Épica a verificar y desplegar")
    args = parser.parse_args()
    
    if args.requirements:
        propose_backlog(args.requirements)
    elif args.approve_epic:
        approve_and_deploy_backlog(args.approve_epic)
    else:
        parser.print_help()