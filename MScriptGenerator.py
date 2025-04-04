import argparse
from converter import TFLToMConverter

def main():
    parser = argparse.ArgumentParser(
        description='Convert Tableau Prep (TFL/JSON) to Power Query M script'
    )
    parser.add_argument(
        'input_file',
        help='Path to Tableau Prep JSON/TFL file (required)'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output file path (default: output.pq)',
        default='output.pq'
    )
    parser.add_argument(
        '--excel',
        help='Optional: Override Excel file path (default: auto-detected from JSON or D:\\downloads\\AdventureWorks Sales.xlsx)',
        default=None
    )
    parser.add_argument(
        '--debug',
        help='Enable debug output',
        action='store_true'
    )
    
    args = parser.parse_args()
    
    try:
        converter = TFLToMConverter(args.input_file)
        if args.excel:
            converter.set_excel_path(args.excel)
        converter.enable_debug(args.debug)
        m_script = converter.convert()
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(m_script)
        print(f"Successfully converted to {args.output}")
        print(f"Using Excel file: {converter._excel_path}")
    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()
