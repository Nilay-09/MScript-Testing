import json
import os
from typing import Dict, List, Optional, Set
from helpers import sanitize_name
import node_handlers as nh

def is_json_file(filepath):
    """Check if a file contains valid JSON content."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            json.load(f)
        return True
    except (json.JSONDecodeError, UnicodeDecodeError, FileNotFoundError):
        return False

class TFLToMConverter:
    def __init__(self, json_file_path: str):
        self.prep_flow = self._validate_and_load_json(json_file_path)
        self.generated_tables: Dict[str, str] = {}
        self.custom_functions: List[str] = []
        self._excel_path = self._extract_excel_path()
        if not self._excel_path:
            raise ValueError("No Excel file path found in flow file connections. Please specify via set_excel_path().")
        self._debug_mode = False

    def _extract_excel_path(self) -> Optional[str]:
        """Extract Excel path from connection information if available."""
        for conn_id, conn in self.prep_flow.get('connections', {}).items():
            if conn.get('connectionType') == '.v1.SqlConnection':
                if 'filename' in conn.get('connectionAttributes', {}):
                    path = conn['connectionAttributes']['filename']
                    return path.replace("\\", "\\\\")
        return None

    def _validate_and_load_json(self, path: str) -> dict:
        """Validate and load the JSON file with proper error handling."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Input file not found: {path}")
        if not (path.lower().endswith(('.json', '.tfl')) or is_json_file(path)):
            print(f"Warning: Expected .json or .tfl file, got {os.path.splitext(path)[1]}")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format in {os.path.basename(path)}: {str(e)}")

    def set_excel_path(self, path: str):
        """Update the source Excel file path."""
        self._excel_path = path.replace("\\", "\\\\")

    def enable_debug(self, enabled: bool = True):
        """Enable debug output."""
        self._debug_mode = enabled

    def convert(self) -> str:
        """Main conversion entry point."""
        try:
            m_script = ["let"]
            m_script += self._process_data_sources()
            m_script += self._process_transformations()
            m_script += self._build_output_section()
            return "\n".join(m_script)
        except Exception as e:
            raise RuntimeError(f"Conversion failed: {str(e)}")

    def _process_data_sources(self) -> List[str]:
        """Process all input data sources with specified M script syntax."""
        section = []
        sheet_nodes = [
            n for n in self.prep_flow.get('initialNodes', [])
            if self.prep_flow['nodes'][n]['nodeType'] == '.v1.LoadExcel'
        ]
        section += [
            "    GetSheetData = (SelectedSheetName as text) => let",
            "        // Load the Excel file",
            f"        Source = Excel.Workbook(File.Contents(\"{self._excel_path}\"), null, true),",
            "",
            "        // Filter sheets of interest",
            f"        SelectedSheets = {self._get_sheet_list(sheet_nodes)},",
            "        FilteredSheets = Table.SelectRows(Source, each List.Contains(SelectedSheets, [Name])),",
            "",
            "        // Validate selected sheet exists",
            "        TargetSheet = Table.SelectRows(FilteredSheets, each [Name] = SelectedSheetName),",
            "        CheckSheet = if Table.IsEmpty(TargetSheet) then",
            "            error Error.Record(",
            "                \"Sheet not found\",",
            "                \"Available sheets: \" & Text.Combine(FilteredSheets[Name], \", \"),",
            "                [RequestedSheet = SelectedSheetName]",
            "            )",
            "        else TargetSheet,",
            "",
            "        // Extract sheet data",
            "        SheetData = try CheckSheet{0}[Data] otherwise error Error.Record(",
            "            \"Data extraction failed\",",
            "            \"Verify sheet structure\",",
            "            [SheetName = SelectedSheetName, AvailableColumns = Table.ColumnNames(CheckSheet)]",
            "        ),",
            "",
            "        // Promote headers and clean data",
            "        PromotedHeaders = Table.PromoteHeaders(SheetData, [PromoteAllScalars=true]),",
            "        ColumnsToTransform = Table.ColumnNames(PromotedHeaders),",
            "        ChangedTypes = Table.TransformColumnTypes(",
            "            PromotedHeaders,",
            "            List.Transform(",
            "                ColumnsToTransform,",
            "                each {_, ",
            "                    let",
            "                        SampleValue = List.First(Table.Column(PromotedHeaders, _), null),",
            "                        TypeDetect = if SampleValue = null then type text",
            "                            else if Value.Is(SampleValue, Number.Type) then",
            "                                if Number.Round(SampleValue) = SampleValue then Int64.Type else type number",
            "                            else if Value.Is(SampleValue, Date.Type) then type date",
            "                            else if Value.Is(SampleValue, DateTime.Type) then type datetime",
            "                            else type text",
            "                    in",
            "                        TypeDetect}",
            "            )",
            "        ),",
            "        CleanedData = Table.SelectRows(ChangedTypes, each not List.Contains(Record.FieldValues(_), null)),",
            "        FinalTable = Table.Distinct(CleanedData)",
            "    in",
            "        FinalTable,"
        ]
        section.append("")
        section.append("    // Load base tables")
        for node_id in sheet_nodes:
            node = self.prep_flow['nodes'][node_id]
            safe_name = sanitize_name(node['name'])
            section.append(f"    {safe_name} = GetSheetData(\"{node['name']}\"),")
            self.generated_tables[node_id] = safe_name
        return section

    def _get_node_dependencies(self, node: dict) -> List[str]:
        """Get all upstream dependencies for a node, ensuring container sub-nodes are linked."""
        dependencies = []
        node_id = node.get('id', 'Unknown')
        node_type = node.get('nodeType', 'Unknown')

        if node_type in ['.v1.LoadExcel', '.v1.WriteToHyper']:
            return []

        # Find nodes that feed into this one (reverse dependency)
        for nid, n in self.prep_flow['nodes'].items():
            if 'nextNodes' in n and any(nn.get('nextNodeId') == node_id for nn in n.get('nextNodes', [])):
                dependencies.append(nid)

        # Special handling for containers
        if node_type == '.v1.Container':
            # Check loomContainer for initialNodes and sub-node dependencies
            container_data = node.get('loomContainer', {})
            if 'initialNodes' in container_data and container_data['initialNodes']:
                dependencies.extend(container_data['initialNodes'])
            # For containers, also consider the node feeding into it as the primary dependency
            for nid, n in self.prep_flow['nodes'].items():
                if 'nextNodes' in n and any(nn.get('nextNodeId') == node_id for nn in n.get('nextNodes', [])):
                    dependencies.append(nid)
            # Remove sub-node IDs from dependencies if present, as they are processed within the container
            sub_nodes = container_data.get('nodes', {})
            sub_node_ids = set(sub_nodes.keys())
            dependencies = [dep for dep in dependencies if dep not in sub_node_ids]

        # Special handling for sub-nodes like AddColumn
        if node_type == '.v1.AddColumn':
            # If this is a sub-node, its dependency is the container’s input or previous node
            for nid, n in self.prep_flow['nodes'].items():
                if 'nextNodes' in n and any(nn.get('nextNodeId') == node_id for nn in n.get('nextNodes', [])):
                    dependencies.append(nid)
                # Check if this AddColumn is inside a container
                container_data = n.get('loomContainer', {})
                if container_data and node_id in container_data.get('nodes', {}):
                    # Dependency is the container’s input
                    for parent_nid, parent_n in self.prep_flow['nodes'].items():
                        if 'nextNodes' in parent_n and any(nn.get('nextNodeId') == nid for nn in parent_n.get('nextNodes', [])):
                            dependencies.append(parent_nid)

        # Special handling for SuperJoin
        if node_type == '.v2018_2_3.SuperJoin':
            action_node = node.get('actionNode', {})
            if action_node and 'nodeType' in action_node and action_node['nodeType'] == '.v1.SimpleJoin':
                for nid, n in self.prep_flow['nodes'].items():
                    if 'nextNodes' in n and any(nn.get('nextNodeId') == node_id for nn in n.get('nextNodes', [])):
                        dependencies.append(nid)

        unique_deps = list(set(dependencies))
        if not unique_deps and self._debug_mode and node_type != '.v1.AddColumn':  # AddColumn may have no direct deps if in container
            print(f"Warning: No dependencies found for node {node_id} ({node_type})")
        return unique_deps

    def _process_transformations(self) -> List[str]:
        """Process all transformation nodes in dependency order."""
        section = ["", "    // Transformations"]
        processed_nodes: Set[str] = set(self.generated_tables.keys())
        all_nodes = {nid: node for nid, node in self.prep_flow['nodes'].items()}
        remaining_nodes = {
            nid: node for nid, node in all_nodes.items()
            if nid not in processed_nodes and node['nodeType'] not in ['.v1.WriteToHyper', '.v1.LoadExcel']
        }

        visited = set()
        node_order = []

        while remaining_nodes:
            current_batch = []
            for nid, node in remaining_nodes.items():
                if nid in visited:
                    continue

                deps = self._get_node_dependencies(node)
                if all(dep in processed_nodes for dep in deps):
                    current_batch.append((nid, node))
                else:
                    if self._debug_mode:
                        missing_deps = [d for d in deps if d not in processed_nodes]
                        print(f"Node {nid} ({node['nodeType']}): Waiting for dependencies {missing_deps}")

            if not current_batch:
                unprocessed = ", ".join(remaining_nodes.keys())
                warning = f"    // Warning: Circular or unresolvable dependencies detected in nodes: {unprocessed}"
                if self._debug_mode:
                    print(warning)
                    for nid, node in remaining_nodes.items():
                        print(f"Node {nid} ({node['nodeType']}): {node.get('name', 'Unnamed')}, Dependencies: {self._get_node_dependencies(node)}")
                section.append(warning)
                break

            for node_id, node in current_batch:
                visited.add(node_id)
                node_order.append(node_id)
                m_code = self._generate_node_code(node, node_id)
                if m_code:
                    section.append(m_code)
                    processed_nodes.add(node_id)
                    if self._debug_mode:
                        print(f"Processed node {node_id} ({node['nodeType']}): {node.get('name', 'Unnamed')}")
                del remaining_nodes[node_id]

        if self._debug_mode:
            print(f"Processing order: {node_order}")
        return section

    def _generate_node_code(self, node: dict, node_id: str) -> Optional[str]:
        """Generate M code for a specific node type."""
        handlers = {
            '.v1.SimpleJoin': nh.handle_join,
            '.v1.AddColumn': nh.handle_add_column,
            '.v1.Aggregate': nh.handle_aggregate,
            '.v1.Union': nh.handle_union,
            '.v1.Pivot': nh.handle_pivot,
            '.v1.Filter': nh.handle_filter,
            '.v1.Container': nh.handle_container,
            '.v2018_2_3.SuperJoin': nh.handle_super_join
        }

        node_type = node.get('nodeType', 'Unknown')
        handler = handlers.get(node_type)

        if not handler:
            warning = f"    // Warning: No handler for node type {node_type}"
            if self._debug_mode:
                print(warning)
            return warning

        dependencies = self._get_node_dependencies(node)
        if not dependencies and node_type != '.v1.Container':
            error_msg = f"    // Error: No dependencies found for node {node_id} ({node_type})"
            if self._debug_mode:
                print(error_msg)
            return error_msg

        upstream_tables = [self.generated_tables.get(dep, f"MissingTable_{dep}") for dep in dependencies]
        if any(table.startswith("MissingTable_") for table in upstream_tables):
            error_msg = f"    // Error: Missing upstream tables for node {node_id} ({node_type}): {upstream_tables}"
            if self._debug_mode:
                print(error_msg)
                for dep in dependencies:
                    if dep not in self.generated_tables:
                        print(f"Potential missing node: {dep}, Type: {self.prep_flow['nodes'].get(dep, {}).get('nodeType', 'Unknown')}")
            return error_msg

        try:
            m_code = handler(node, upstream_tables)
            self.generated_tables[node_id] = sanitize_name(node.get('name', f"Transform_{node_id}"))
            if self._debug_mode:
                print(f"Generated code for {node_id} ({node_type}): {m_code.splitlines()[0]}...")
            return m_code
        except Exception as e:
            error_msg = f"    // Error processing node {node_id} ({node_type}): {str(e)}"
            if self._debug_mode:
                print(error_msg)
            return error_msg

    def _build_output_section(self) -> List[str]:
        """Build the final output structure with specified syntax."""
        all_tables = list(self.generated_tables.values())
        default_output = all_tables[-1] if all_tables else ""
        return [
            "",
            "    // Create combined table set",
            "    CombinedTables = [",
            "        " + ",\n        ".join(f"{name} = {name}" for name in all_tables),
            "    ],",
            "",
            "    // Parameter handling",
            f"    SelectedSheetName = \"\",",
            "    SelectedSheets = Record.FieldNames(CombinedTables),",
            "",
            "    GetSelectedTable = if SelectedSheetName = \"\" then",
            "        error \"No sheet selected\" ",
            "    else ",
            "        try Record.Field(CombinedTables, SelectedSheetName) ",
            "        otherwise error Error.Record(",
            "            \"Sheet not found\", ",
            "            \"Available tables: \" & Text.Combine(SelectedSheets, \", \"), ",
            "            [RequestedTable = SelectedSheetName]",
            "        )",
            "in",
            "    GetSelectedTable"
        ]

    def _get_sheet_list(self, sheet_nodes: List[str]) -> str:
        """Generate the list of sheets for the Excel loader function."""
        names = [self.prep_flow['nodes'][n]['name'] for n in sheet_nodes]
        return "{\"" + "\", \"".join(names) + "\"}"