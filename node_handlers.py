from typing import List
from helpers import sanitize_name, translate_expression, detect_column_type

def handle_join(node: dict, upstream_tables: List[str]) -> str:
    if len(upstream_tables) != 2:
        raise ValueError(f"Join operation requires exactly 2 inputs, got {len(upstream_tables)}")
    left, right = upstream_tables
    conditions = [(c['leftExpression'].strip('[]'), c['rightExpression'].strip('[]'))
                  for c in node.get('conditions', [])]
    if not conditions:
        raise ValueError("Join operation requires at least one condition")
    return (
        f"{sanitize_name(node['name'])} = Table.Join(\n"
        f"    {left},\n"
        f"    {{{', '.join([f'\"{c[0]}\"' for c in conditions])}}},\n"
        f"    {right},\n"
        f"    {{{', '.join([f'\"{c[1]}\"' for c in conditions])}}},\n"
        f"    JoinKind.{node.get('joinType', 'inner').capitalize()}\n"
        "),"
    )

def handle_add_column(node: dict, upstream_tables: List[str]) -> str:
    if len(upstream_tables) != 1:
        raise ValueError(f"AddColumn requires exactly 1 input, got {len(upstream_tables)}")
    if 'columnName' not in node or 'expression' not in node:
        raise ValueError("AddColumn node missing required properties")
    return (
        f"{sanitize_name(node['name'])} = Table.AddColumn(\n"
        f"    {upstream_tables[0]},\n"
        f"    \"{node['columnName']}\",\n"
        f"    each {translate_expression(node['expression'])},\n"
        f"    {detect_column_type(node)}\n"
        "),"
    )

def handle_aggregate(node: dict, upstream_tables: List[str]) -> str:
    if len(upstream_tables) != 1:
        raise ValueError(f"Aggregate requires exactly 1 input, got {len(upstream_tables)}")
    groups = [f.strip('[]') for f in node.get('groupByFields', [])]
    aggregations = []
    for agg in node.get('aggregations', []):
        agg_type = agg.get('aggregationType', 'Sum').capitalize()
        column = agg.get('column', '').strip('[]')
        new_name = agg.get('newName', f"{column}_{agg_type.lower()}")
        aggregations.append(f"{{ \"{column}\", List.{agg_type}, \"{new_name}\" }}")
    if not groups and not aggregations:
        raise ValueError("Aggregate operation requires groupByFields or aggregations")
    return (
        f"{sanitize_name(node['name'])} = Table.Group(\n"
        f"    {upstream_tables[0]},\n"
        f"    {{{', '.join([f'\"{g}\"' for g in groups])}}},\n"
        f"    {{{', '.join(aggregations)}}}\n"
        "),"
    )

def handle_union(node: dict, upstream_tables: List[str]) -> str:
    if len(upstream_tables) < 2:
        raise ValueError(f"Union requires at least 2 inputs, got {len(upstream_tables)}")
    return (
        f"{sanitize_name(node['name'])} = Table.Combine(\n"
        f"    {{{', '.join(upstream_tables)}}}\n"
        "),"
    )

def handle_pivot(node: dict, upstream_tables: List[str]) -> str:
    if len(upstream_tables) != 1:
        raise ValueError(f"Pivot requires exactly 1 input, got {len(upstream_tables)}")
    pivot_col = node.get('pivotColumn', '').strip('[]')
    value_col = node.get('valueColumn', '').strip('[]')
    pivot_type = node.get('pivotType', 'columns')
    if not pivot_col or not value_col:
        raise ValueError("Pivot operation requires pivotColumn and valueColumn")
    if pivot_type == 'columns':
        return (
            f"{sanitize_name(node['name'])} = Table.Pivot(\n"
            f"    Table.Distinct(Table.SelectColumns({upstream_tables[0]}, \"{pivot_col}\")),\n"
            f"    {upstream_tables[0]}[[{pivot_col}]],\n"
            f"    \"{pivot_col}\",\n"
            f"    \"{value_col}\",\n"
            "    List.Sum\n"
            "),"
        )
    else:
        return (
            f"{sanitize_name(node['name'])} = Table.Unpivot(\n"
            f"    {upstream_tables[0]},\n"
            f"    {node.get('valueColumns', {})},\n"
            f"    \"{pivot_col}\",\n"
            f"    \"{value_col}\"\n"
            "),"
        )

def handle_filter(node: dict, upstream_tables: List[str]) -> str:
    if len(upstream_tables) != 1:
        raise ValueError(f"Filter requires exactly 1 input, got {len(upstream_tables)}")
    condition = node.get('filterExpression', '')
    if not condition:
        raise ValueError("Filter operation requires filterExpression")
    return (
        f"{sanitize_name(node['name'])} = Table.SelectRows(\n"
        f"    {upstream_tables[0]},\n"
        f"    each {translate_expression(condition)}\n"
        "),"
    )

def handle_container(node: dict, upstream_tables: List[str]) -> str:
    """Handle container nodes by processing sub-nodes in loomContainer."""
    if len(upstream_tables) != 1:
        raise ValueError(f"Container requires exactly 1 input, got {len(upstream_tables)}")
    container_name = sanitize_name(node['name'])
    upstream_table = upstream_tables[0]

    # Check for sub-nodes in loomContainer
    container_data = node.get('loomContainer', {})
    sub_nodes = container_data.get('nodes', {})
    
    if not sub_nodes:
        # No sub-nodes, just pass through the upstream table
        return (
            f"// Container: {container_name}\n"
            f"{container_name} = {upstream_table},"
        )

    # Process sub-nodes (e.g., AddColumn in Clean 6)
    handlers = {
        '.v1.SimpleJoin': handle_join,
        '.v1.AddColumn': handle_add_column,
        '.v1.Aggregate': handle_aggregate,
        '.v1.Union': handle_union,
        '.v1.Pivot': handle_pivot,
        '.v1.Filter': handle_filter,
        '.v2018_2_3.SuperJoin': handle_super_join
    }
    
    transformations = []
    current_table = upstream_table
    
    for sub_node_id, sub_node in sub_nodes.items():
        sub_node_type = sub_node.get('nodeType', 'Unknown')
        handler = handlers.get(sub_node_type)
        if not handler:
            transformations.append(f"// Warning: No handler for sub-node type {sub_node_type} in {container_name}")
            continue
        
        # Generate M code for the sub-node
        sub_node_code = handler(sub_node, [current_table])
        transformations.append(sub_node_code)
        # Update current_table to the result of this transformation
        current_table = sanitize_name(sub_node['name'])
    
    # Combine transformations into the container output
    return (
        f"// Container: {container_name}\n"
        + "\n".join(transformations) + f"\n{container_name} = {current_table},"
    )

def handle_super_join(node: dict, upstream_tables: List[str]) -> str:
    if 'actionNode' not in node:
        raise ValueError("SuperJoin node missing actionNode")
    # Process the internal join node
    return handle_join(node['actionNode'], upstream_tables)
