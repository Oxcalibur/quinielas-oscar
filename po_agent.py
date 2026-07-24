# -*- coding: utf-8 -*-
"""
Product Owner Agent (Compuerta 1 - Olivia's Legacy 2026)
Convierte requisitos funcionales puros en un backlog de Épicas y sub-issues en GitHub.
Usa gobernanza asíncrona nativa mediante etiquetas de aprobación en GitHub.
INCLUYE: Feedback Loop autónomo para refinamiento guiado por Post-Mortem.
"""

# Parche de seguridad SSL
import truststore
try:
    truststore.inject_into_ssl()
except AttributeError:
    import urllib3
    truststore.inject_into_urllib3()

import os
import sys
import json
import re
import argparse
import ast
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from github import Github, Auth

# Constante para evitar cortes en la UI del chat
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

# =====================================================================
# INICIALIZAR CLIENTES (GITHUB Y GEMINI)
# =====================================================================
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
        "ai:ready-to-code": "1d76db",       # Azul
        "po:human-validation-required": "fbca04" # Nuevo: Feedback loop
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
        
    scanner = CodebaseScanner()
    existing_vocab = scanner.get_existing_vocabulary()
        
    print("\n🧠 [PO Agent] Analizando requisitos funcionales y diseñando descomposición técnica...")
    
    prompt = f"""
    Actúas como un Product Owner y Arquitecto de Soluciones Senior bajo metodologías ágiles. Tu objetivo es tomar una especificación de requerimientos funcionales y estructurar un plan de desarrollo incremental (Product Backlog).
    
    📜 DIRECTIVAS DE GOBERNANZA Y BUENAS PRÁCTICAS DE REQUISITOS:
    1. RECONCILIACIÓN ESTRICTA DE DOMINIO: Es obligatorio revisar el vocabulario y las clases que ya existen en el repositorio. Redacta los sub-issues usando EXCLUSIVAMENTE los nombres de componentes, paquetes y entidades reales en producción. Queda prohibido usar nombres genéricos de la industria si ya existe un equivalente físico implementado.
    2. DISEÑO INCREMENTAL (INVEST-READY): Cada sub-issue debe cumplir con los criterios INVEST (Independiente, Negociable, Valioso, Estimable, Pequeño, Testeable). No mezcles responsabilidades en una sola tarea.
    3. TRAZABILIDAD VISUAL: Estructura los cuerpos de las tareas delimitando con total claridad el PROPÓSITO de negocio y los CRITERIOS DE ACEPTACIÓN TÉCNICOS.

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
    
    proposal = json.loads(response.text)
    
    create_labels_if_not_exist()
    
    epic_body = f"""## 🎯 Justificación Arquitectónica del Backlog
{proposal['epic_justification']}

---

## 📋 Propuesta de Sub-Tareas (Sub-Issues)
A continuación se detallan las tareas lógicas propuestas para el desarrollo de esta funcionalidad. Revísalas minuciosamente en esta Épica de Planificación.

"""
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
        
    comment_open = "<" + "!--"
    comment_close = "--" + ">"
    epic_body += f"\n\n{comment_open} BACKLOG_METADATA_START\n{json.dumps(metadata, indent=2)}\nBACKLOG_METADATA_END {comment_close}"
    
    print("\n📤 [GitHub] Creando Épica de Planificación en el repositorio...")
    epic_issue = repo.create_issue(
        title=f"[ÉPICA] {proposal['epic_title']}",
        body=epic_body,
        labels=["gate:backlog-proposal"]
    )
    
    print(f"\n🎉 ¡Propuesta de Backlog publicada con éxito en GitHub!")
    print(f"🔗 URL de la Épica: {epic_issue.html_url}")
    print("\n🚦 COMPUERTA 1 - ACCIÓN REQUERIDA:")
    print(f"1. Accede al Issue #{epic_issue.number} en tu navegador.")
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
        
    labels = [label.name for label in epic_issue.labels]
    if "gate:approved" not in labels:
        print(f"🛑 [Compuerta 1] Bloqueado: El Issue #{epic_id} no cuenta con la etiqueta 'gate:approved'.")
        print("Añádela en la interfaz web de GitHub antes de confirmar la aprobación.")
        sys.exit(1)
        
    print("🟢 [Compuerta 1] ¡Firma verificada! Deserializando especificaciones del backlog...")
    
    body = epic_issue.body
    regex_pattern = "<" + r"!-- BACKLOG_METADATA_START\s*(.*?)\s*BACKLOG_METADATA_END --" + ">"
    match = re.search(regex_pattern, body, re.DOTALL)
    
    if not match:
        print("❌ Error crítico: No se encontraron metadatos de backlog estructurados en la Épica.")
        sys.exit(1)
        
    metadata_json = match.group(1)
    proposed_issues = json.loads(metadata_json)
    
    print(f"📌 Se han detectado {len(proposed_issues)} sub-tareas validadas por el humano. Desplegando...")
    
    for idx, sub in enumerate(proposed_issues, 1):
        title = f"[Épica #{epic_id}] Task {idx}: {sub['title']}"
        body_with_epic = f"Este sub-issue ha sido creado y aprobado bajo la Épica #{epic_id}.\n\n{sub['body']}"
        
        created_issue = repo.create_issue(
            title=title,
            body=body_with_epic,
            labels=["ai:ready-to-code", f"priority:{sub['priority']}"]
        )
        print(f"  ↳ ✅ Creado Issue #{created_issue.number}: '{title}' | Listo para codificar.")
        
    try:
        epic_issue.remove_from_labels("gate:backlog-proposal")
    except Exception:
        pass
    print(f"\n🎉 ¡Proceso de Gobernanza completado! La Épica #{epic_id} está formalmente aprobada y su backlog desplegado.")

def refine_issue(issue_id: int, pm_report: str):
    """
    NUEVA FASE DE GOBERNANZA ASÍNCRONA: Feedback Loop.
    Activada por el Orquestador cuando el código falla debido a contradicciones o fallos recurrentes.
    """
    print(f"\n[PO-AGENT] 🚨 Iniciando refinamiento autónomo del Issue #{issue_id} a petición del Orquestador...")
    try:
        issue = repo.get_issue(number=issue_id)
    except Exception as e:
        print(f"❌ Error al obtener el Issue #{issue_id}: {e}")
        return
    
    prompt = f"""
    Actúas como el Product Owner Principal del proyecto.
    El equipo técnico (Pipeline de CI/CD del Orquestador) ha devuelto el Issue #{issue_id} ('{issue.title}') porque los requerimientos del contrato original chocan con la realidad técnica, la arquitectura actual o las reglas de seguridad.

    REPORTE POST-MORTEM (Diagnóstico del equipo técnico):
    ---
    {pm_report}
    ---

    CUERPO ACTUAL DEL ISSUE (El Contrato Original que provocó el fallo):
    ---
    {issue.body}
    ---

    Tu tarea es REESCRIBIR la sección de "Criterios de Aceptación Técnicos" del Issue original para resolver EXACTAMENTE las discrepancias detalladas en el Post-Mortem (asegurando el uso exclusivo de Python, manejo de linters, etc.).
    
    Además, DEBES ASEGURARTE de que los "Criterios de Aceptación Técnicos" siempre incluyan una directriz explícita sobre el uso de type hints en todas las funciones y métodos, tanto para argumentos como para valores de retorno, para cumplir con los estándares de calidad de código y análisis estático.

    Devuelve ÚNICAMENTE el nuevo contenido Markdown completo y limpio con el que debo sobreescribir el Issue actual en GitHub. No incluyas notas explicativas fuera del bloque.
    """
    
    print("[PO-AGENT] 🧠 Evaluando diagnóstico clínico y renegociando el contrato (ACs)...")
    response = ai_client.models.generate_content(
        model=MODEL_HEAVY,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2)
    )
    
    new_body = response.text.strip()
    if new_body.startswith(f"{MD_FENCE}markdown"): new_body = new_body[11:]
    elif new_body.startswith(MD_FENCE): new_body = new_body[3:]
    if new_body.endswith(MD_FENCE): new_body = new_body[:-3]
    
    print(f"[PO-AGENT] 📝 Sobrescribiendo el Issue en GitHub con los Criterios Técnicos actualizados...")
    issue.edit(body=new_body.strip())
    
    create_labels_if_not_exist()
    
    comment = (
        "⚠️ **Atención Óscar (Validación Humana Requerida):**\n\n"
        "El Orquestador me ha devuelto este ticket debido a un conflicto técnico o de arquitectura estricta detectado en el pipeline de validación.\n\n"
        "He **reescrito los Criterios de Aceptación** de este Issue para integrar las exigencias obligatorias del Post-Mortem técnico (como restricciones estrictas de sintaxis Python, linters, o mocks).\n"
        "Por favor, revisa el contrato actualizado en la descripción superior.\n\n"
        "👉 **Si apruebas esta renegociación técnica:** Cambia manualmente la etiqueta de este Issue a `ai:ready-to-code` y vuelve a lanzar el orquestador en tu consola."
    )
    issue.create_comment(comment)
    print(f"[PO-AGENT] ✅ Issue #{issue_id} refinado con éxito. Notificación de validación humana enviada a GitHub.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Product Owner Agent: Gestión de Backlog y Gobernanza Asíncrona")
    parser.add_argument("--requirements", type=str, help="Ruta al archivo Markdown de especificación funcional")
    parser.add_argument("--approve-epic", type=int, dest="approve_epic", help="Número de Issue de la Épica a verificar y desplegar")
    
    # Nuevos argumentos para el Feedback Loop
    parser.add_argument("--refine-issue", type=int, help="Número de Issue a refinar basado en feedback técnico")
    parser.add_argument("--pm-report", type=str, help="Texto del reporte Post-Mortem para justificar el refinamiento")
    
    args = parser.parse_args()
    
    if args.requirements:
        propose_backlog(args.requirements)
    elif args.approve_epic:
        approve_and_deploy_backlog(args.approve_epic)
    elif args.refine_issue and args.pm_report:
        refine_issue(args.refine_issue, args.pm_report)
    else:
        parser.print_help()