import re

def sanitize_name(name: str) -> str:
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    if sanitized and sanitized[0].isdigit():
        sanitized = f"tbl_{sanitized}"
    return sanitized

def translate_expression(expr: str) -> str:
    return (expr.replace('==', '=')
                .replace('&&', ' and ')
                .replace('||', ' or ')
                .replace('!', 'not ')
                .replace('[', '[') 
                .replace(']', ']'))

def detect_column_type(node: dict) -> str:
    col_name = node.get('columnName', '').lower()
    expression = node.get('expression', '').lower()
    if expression:
        if '*' in expression and all('[' in part and ']' in part for part in expression.split('*')):
            if any(kw in col_name for kw in ['quantity', 'count', 'order', 'num', 'revenue']):
                return "Int64.Type"
            return "type number"
        if any(op in expression for op in ['+', '-', '*', '/']) or '[' in expression:
            return "type number"
        if '"' in expression or "'" in expression or '+' in expression:
            return "type text"
    if any(kw in col_name for kw in ['amount', 'price', 'cost', 'value', 'total']):
        return "type number"
    elif any(kw in col_name for kw in ['date', 'time', 'year', 'month', 'day']):
        return "type datetime"
    elif any(kw in col_name for kw in ['flag', 'is_', 'has_']):
        return "type logical"
    return "type any"