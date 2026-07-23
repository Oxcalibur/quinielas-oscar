# Manual de Usuario

Bienvenido al Manual de Usuario del sistema de análisis y extracción de datos deportivos.

## 1. Extracción de Datos de Partidos
El sistema cuenta con una integración automatizada para consultar el histórico de partidos directamente desde la plataforma BeSoccer. Esta funcionalidad permite obtener información actualizada de las ligas de Primera y Segunda división, así como de competiciones europeas y copas.

## 2. Estandarización de Nombres de Equipos
Para asegurar que los datos extraídos sean perfectamente compatibles con nuestra base de datos principal, el sistema aplica una regla de validación estricta conocida como "Diccionario de Cemento". 

* **Reconocimiento Inteligente:** El sistema es capaz de identificar múltiples variaciones o alias de un mismo equipo (por ejemplo, "real madrid", "real madrid cf" o "rmadrid") y los transforma automáticamente a su nombre oficial y estandarizado.
* **Parada de Seguridad:** Si durante la extracción de datos el sistema detecta un nombre de equipo que no está registrado en el diccionario oficial, o si hay un problema de conexión con el proveedor de datos, la operación se detendrá de forma inmediata. Esta es una medida de seguridad estricta diseñada para evitar la entrada de datos corruptos o inconsistentes en el sistema. En estos casos, el sistema emitirá una alerta para que el usuario o administrador pueda revisar la información o actualizar los registros permitidos.