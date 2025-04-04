let
    GetSheetData = (SelectedSheetName as text) => let
        // Load the Excel file
        Source = Excel.Workbook(File.Contents("D:\\MScript Testing\\MScript Testing\\AdventureWorks Sales.xlsx"), null, true),

        // Filter sheets of interest
        SelectedSheets = {"Customer_data", "Date_data", "Sales Territory_data", "Sales_data", "Sales Order_data"},
        FilteredSheets = Table.SelectRows(Source, each List.Contains(SelectedSheets, [Name])),

        // Validate selected sheet exists
        TargetSheet = Table.SelectRows(FilteredSheets, each [Name] = SelectedSheetName),
        CheckSheet = if Table.IsEmpty(TargetSheet) then
            error Error.Record(
                "Sheet not found",
                "Available sheets: " & Text.Combine(FilteredSheets[Name], ", "),
                [RequestedSheet = SelectedSheetName]
            )
        else TargetSheet,

        // Extract sheet data
        SheetData = try CheckSheet{0}[Data] otherwise error Error.Record(
            "Data extraction failed",
            "Verify sheet structure",
            [SheetName = SelectedSheetName, AvailableColumns = Table.ColumnNames(CheckSheet)]
        ),

        // Promote headers and clean data
        PromotedHeaders = Table.PromoteHeaders(SheetData, [PromoteAllScalars=true]),
        ColumnsToTransform = Table.ColumnNames(PromotedHeaders),
        ChangedTypes = Table.TransformColumnTypes(
            PromotedHeaders,
            List.Transform(
                ColumnsToTransform,
                each {_, 
                    let
                        SampleValue = List.First(Table.Column(PromotedHeaders, _), null),
                        TypeDetect = if SampleValue = null then type text
                            else if Value.Is(SampleValue, Number.Type) then
                                if Number.Round(SampleValue) = SampleValue then Int64.Type else type number
                            else if Value.Is(SampleValue, Date.Type) then type date
                            else if Value.Is(SampleValue, DateTime.Type) then type datetime
                            else type text
                    in
                        TypeDetect}
            )
        ),
        CleanedData = Table.SelectRows(ChangedTypes, each not List.Contains(Record.FieldValues(_), null)),
        FinalTable = Table.Distinct(CleanedData)
    in
        FinalTable,

    // Load base tables
    Customer_data = GetSheetData("Customer_data"),
    Date_data = GetSheetData("Date_data"),
    Sales_Territory_data = GetSheetData("Sales Territory_data"),
    Sales_data = GetSheetData("Sales_data"),
    Sales_Order_data = GetSheetData("Sales Order_data"),

    // Transformations
// Container: Clean_4
Clean_4 = Sales_Territory_data,
// Container: Clean_1
Clean_1 = Sales_data,
// Container: Clean_3
Clean_3 = Customer_data,
// Container: Clean_5
Clean_5 = Sales_Order_data,
// Container: Clean_2
Clean_2 = Date_data,
Join_1 = Table.Join(
    Clean_4,
    {"SalesTerritoryKey"},
    Clean_1,
    {"SalesTerritoryKey"},
    JoinKind.Inner
),
Join_3 = Table.Join(
    Clean_5,
    {"SalesOrderLineKey"},
    Join_1,
    {"SalesOrderLineKey"},
    JoinKind.Inner
),
// Container: Clean_6
Add_Revenue = Table.AddColumn(
    Join_3,
    "Revenue",
    each [Sales Amount]*[Order Quantity],
    type any
),
Clean_6 = Add_Revenue,

    // Create combined table set
    CombinedTables = [
        Customer_data = Customer_data,
        Date_data = Date_data,
        Sales_Territory_data = Sales_Territory_data,
        Sales_data = Sales_data,
        Sales_Order_data = Sales_Order_data,
        Clean_4 = Clean_4,
        Clean_1 = Clean_1,
        Clean_3 = Clean_3,
        Clean_5 = Clean_5,
        Clean_2 = Clean_2,
        Join_1 = Join_1,
        Join_3 = Join_3,
        Clean_6 = Clean_6
    ],

    // Parameter handling
    SelectedSheetName = "",
    SelectedSheets = Record.FieldNames(CombinedTables),

    GetSelectedTable = if SelectedSheetName = "" then
        error "No sheet selected" 
    else 
        try Record.Field(CombinedTables, SelectedSheetName) 
        otherwise error Error.Record(
            "Sheet not found", 
            "Available tables: " & Text.Combine(SelectedSheets, ", "), 
            [RequestedTable = SelectedSheetName]
        )
in
    GetSelectedTable