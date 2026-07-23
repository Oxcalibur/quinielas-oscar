# Documento de Arquitectura de Software

## 1. Visión General
Este documento describe la arquitectura del sistema, delineada por los principios de alta cohesión, bajo acoplamiento y máxima resiliencia. Las recientes refactorizaciones han evolucionado el sistema hacia una clara separación de responsabilidades, aislamiento estricto de componentes de infraestructura, y el aseguramiento de la integridad de datos mediante el paradigma *Fail-Fast*.

## 2. Topología del Sistema
El repositorio está estructurado para distinguir claramente entre integración de datos, reglas de negocio del dominio y utilidades de automatización del ciclo de vida de desarrollo.

```text
/
├── src/
│   ├── data/                     # Capa de integración y limpieza de datos
│   │   ├── __init__.py
│   │   ├── cement_dictionary.py  # Patrón de normalización estricta de nombres
│   │   └── besoccer_client.py    # Cliente HTTP para BeSoccer
│   └── features/                 # Capa de reglas de negocio / Dominio
│       ├── __init__.py
│       └── fatigue_calculator.py # Lógica core de cálculos de descanso y fatiga
├── tests/
│   ├── data/
│   │   ├── __init__.py
│   │   ├── test_cement_dictionary.py
│   │   └── test_besoccer_client.py
│   └── features/
│       ├── __init__.py
│       └── test_fatigue_calculator.py
├── docs/
│   ├── ARCHITECTURE.md           # Este documento
│   └── reports/                  # Salidas de reportes y escaneos
├── .ruff_cache/                  # Cache local del linter estático
├── po_agent_old.py               # Módulo legacy/agente para escaneo y Backlog
└── vulture_whitelist.py          # Configuración del AST para falsos positivos de código muerto
```

## 3. Decisiones Arquitectónicas y Razonamiento Técnico

### 3.1. Aislamiento y Patrón "Diccionario de Cemento"
Se separa completamente la comunicación externa de la lógica de limpieza de datos:
*   **Cliente Aislado:** `BeSoccerClient` encapsula las peticiones HTTP, el manejo de base URLs y el parsing del esquema JSON de entrada, garantizando que los cambios en el proveedor externo impacten en un único lugar.
*   **Diccionario de Cemento:** `cement_dictionary.py` es responsable en exclusividad de normalizar nombres de equipos (`normalize_team_name`). Al aplicar el patrón de *Diccionario de Cemento*, se centralizan las reglas heurísticas y mapeos de strings bajo una exportación estricta (mediante `__all__`). Esto previene fugas de implementación y mutaciones de estado indeseadas en el runtime global.

### 3.2. Fail-Fast Estricto y Resiliencia de Datos
El flujo de datos impone barreras rígidas contra la corrupción silenciosa:
*   La capa de extracción de datos invoca la normalización en tiempo real durante el parseo de entidades.
*   Cualquier anomalía de *tipo* de dato en un campo objetivo genera un `TypeError` de inmediato.
*   Cualquier equipo *no mapeado* en el diccionario genera un `KeyError` de inmediato.
*   **Impacto:** El sistema prefiere colapsar y alertar explícitamente, abortando la operación, antes que permitir que un string no normalizado envenene el estado interno de calculadoras críticas como `FatigueCalculator`.

### 3.3. Testing Unitario Desacoplado
La suite de pruebas refleja la estructura y las fronteras de los componentes:
*   **Aislamiento de I/O:** Toda interacción de red (Llamadas HTTP en `BeSoccerClient`) o *side-effect* transversal (ej. Logs) es interceptada.
*   **Librería Nativa:** Se prescinde de librerías de terceros (como `pytest-mock`) para los *mocks*. Se utiliza única y exclusivamente `unittest.mock.patch`, forzando a los ingenieros a entender y manejar el ciclo de vida real del patcheo en Python, y reduciendo la deuda de dependencias de la pipeline de tests.
*   **Cobertura Orientada a Fallos:** Las pruebas como `test_fetch_matches_aborts_on_invalid_data_type` y `test_normalize_team_name_key_error` validan formalmente los contratos del diseño *Fail-Fast*.

### 3.4. Análisis Estático de Código (Vulture)
La estrategia para gestionar el código supuestamente no utilizado (Dead Code Analysis) se ha estandarizado usando el AST interno de Python:
*   Se erradica la vieja práctica de declarar *clases mock* falsas en el archivo de whitelist, ya que esto inducía ruido arquitectónico y ensuciaba el indexado del IDE.
*   En `vulture_whitelist.py`, el estándar vigente ahora es importar la clase real correspondiente y referenciar su método directamente (e.g., `_ = BeSoccerClient.fetch_matches`). Esta notación explícita es el estándar técnico validado por Vulture para silenciar alertas marcando la firma como consumida, preservando la integridad del árbol sintáctico del proyecto.