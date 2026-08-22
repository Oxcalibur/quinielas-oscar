import json
import re

MD_FENCE = "`" * 3

def extract_code(text, language=None):
    """
    Extrae el contenido de un bloque de código Markdown.
    Si no encuentra un bloque, devuelve el texto limpio.
    """
    # Intenta extraer JSON si el texto parece un objeto o array JSON
    stripped_text = text.strip()
    if (stripped_text.startswith('{') and stripped_text.endswith('}')) or \
       (stripped_text.startswith('[') and stripped_text.endswith(']')):
        try:
            json.loads(stripped_text)
            return stripped_text
        except json.JSONDecodeError:
            pass # No es JSON válido, seguir con la lógica de markdown
    pattern = rf"{MD_FENCE}{language}\s*(.*?)\s*{MD_FENCE}" if language else rf"{MD_FENCE}(?:[a-zA-Z0-9_\-\.]+)?\s*(.*?)\s*{MD_FENCE}"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
        
    pattern_any = rf"{MD_FENCE}(?:[a-zA-Z0-9_\-\.]+)?\s*(.*?)\s*{MD_FENCE}"
    match_any = re.search(pattern_any, text, re.DOTALL)
    if match_any:
        return match_any.group(1).strip()

    return text.strip()

