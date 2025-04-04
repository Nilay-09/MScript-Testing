import re

def sanitize_name(name: str) -> str:
    """Convert table names to valid M identifiers."""
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    if sanitized and sanitized[0].isdigit():
        sanitized = f"tbl_{sanitized}"
    return sanitized

def translate_expression(expr: str) -> str:
    """Convert Tableau Prep expressions to M syntax."""
    return (expr.replace('==', '=')
                .replace('&&', ' and ')
                .replace('||', ' or ')
                .replace('!', 'not ')
                .replace('[', '[') 
                .replace(']', ']'))

def detect_column_type(node: dict) -> str:
    """Determine appropriate M type for calculated columns."""
    col_name = node.get('columnName', '').lower()
    if any(kw in col_name for kw in ['amount', 'price', 'cost', 'value', 'total']):
        return "type number"
    elif any(kw in col_name for kw in ['date', 'time', 'year', 'month', 'day']):
        return "type datetime"
    elif any(kw in col_name for kw in ['flag', 'is_', 'has_']):
        return "type logical"
    return "type any"
