-- ================================================================
-- Postgres tables for SQL Server replication target
-- Source: SQL Server EnterpriseDW (dbo schema)
-- Target: PostgreSQL enterprise_dw database, sqlserver_dw schema
--
-- SQL Server → PostgreSQL type mappings:
--   int IDENTITY(1,1)    → SERIAL (INTEGER auto-increment)
--   bigint IDENTITY(1,1) → BIGSERIAL
--   bit                  → BOOLEAN
--   varchar(n)           → VARCHAR(n) | TEXT (-1/MAX)
--   nvarchar(n)          → VARCHAR(n) | TEXT (-1/MAX)
--   nchar(n)             → CHAR(n)
--   datetime             → TIMESTAMP(3)
--   datetime2(n)         → TIMESTAMP(n)
--   uniqueidentifier     → UUID
--   money                → NUMERIC(19,4)
--   varbinary/binary     → BYTEA
--   computed (virtual)   → GENERATED ALWAYS AS (...) STORED
--
-- Tables in topological FK dependency order
-- ================================================================

CREATE SCHEMA IF NOT EXISTS sqlserver_dw;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Enable pgcrypto for gen_random_uuid() if needed
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- Table: ProductCategories
-- ============================================================
CREATE TABLE sqlserver_dw."ProductCategories" (
    "CategoryId" SERIAL,
    "CategoryCode" VARCHAR(10) NOT NULL,
    "CategoryName" VARCHAR(200) NOT NULL,
    "ParentCategoryId" INTEGER,
    "Description" TEXT,
    "IsActive" BOOLEAN DEFAULT TRUE NOT NULL,
    "CreatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    PRIMARY KEY ("CategoryId"),
    CONSTRAINT "FK__ProductCa__Paren__5535A963" FOREIGN KEY ("ParentCategoryId") REFERENCES sqlserver_dw."ProductCategories" ("CategoryId")
);

-- ============================================================
-- Table: Products
-- ============================================================
CREATE TABLE sqlserver_dw."Products" (
    "ProductId" SERIAL,
    "ProductCode" VARCHAR(30) NOT NULL,
    "ProductName" VARCHAR(300) NOT NULL,
    "CategoryId" INTEGER NOT NULL,
    "UOM" VARCHAR(10) DEFAULT 'EA' NOT NULL,
    "StandardCost" NUMERIC(14,4) NOT NULL,
    "ListPrice" NUMERIC(14,4) NOT NULL,
    "Weight" NUMERIC(10,4),
    "WeightUOM" VARCHAR(5),
    "LeadTimeDays" INTEGER DEFAULT 14 NOT NULL,
    "MinOrderQty" NUMERIC(12,3) DEFAULT 1 NOT NULL,
    "ReorderPoint" NUMERIC(12,3),
    "SafetyStock" NUMERIC(12,3),
    "IsActive" BOOLEAN DEFAULT TRUE NOT NULL,
    "IsPurchased" BOOLEAN DEFAULT TRUE NOT NULL,
    "IsManufactured" BOOLEAN DEFAULT FALSE NOT NULL,
    "IsSold" BOOLEAN DEFAULT TRUE NOT NULL,
    "DrawingNumber" VARCHAR(50),
    "Revision" VARCHAR(5),
    "ProductGUID" UUID DEFAULT gen_random_uuid() NOT NULL,
    "CreatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    "UpdatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    PRIMARY KEY ("ProductId"),
    CONSTRAINT "FK__Products__Catego__5AEE82B9" FOREIGN KEY ("CategoryId") REFERENCES sqlserver_dw."ProductCategories" ("CategoryId")
);

-- ============================================================
-- Table: BillOfMaterials
-- ============================================================
CREATE TABLE sqlserver_dw."BillOfMaterials" (
    "BOMId" SERIAL,
    "ParentProductId" INTEGER NOT NULL,
    "ChildProductId" INTEGER NOT NULL,
    "Quantity" NUMERIC(14,4) DEFAULT 1 NOT NULL,
    "UOM" VARCHAR(10) DEFAULT 'EA' NOT NULL,
    "BOMLevel" INTEGER DEFAULT 1 NOT NULL,
    "IsPhantom" BOOLEAN DEFAULT FALSE NOT NULL,
    "ScrapPercent" NUMERIC(6,4) DEFAULT 0 NOT NULL,
    "EffectiveFrom" DATE NOT NULL,
    "EffectiveTo" DATE,
    "CreatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    PRIMARY KEY ("BOMId"),
    CONSTRAINT "FK__BillOfMat__Child__693CA210" FOREIGN KEY ("ChildProductId") REFERENCES sqlserver_dw."Products" ("ProductId"),
    CONSTRAINT "FK__BillOfMat__Paren__68487DD7" FOREIGN KEY ("ParentProductId") REFERENCES sqlserver_dw."Products" ("ProductId")
);

-- ============================================================
-- Table: ChangeLog
-- ============================================================
CREATE TABLE sqlserver_dw."ChangeLog" (
    "ChangeId" BIGSERIAL,
    "TableName" VARCHAR(100) NOT NULL,
    "RecordId" BIGINT NOT NULL,
    "ChangeType" CHAR(1) NOT NULL,
    "ChangedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    "ChangedByUserId" VARCHAR(100),
    "OldValues" TEXT,
    "NewValues" TEXT,
    "ChangeSource" VARCHAR(50),
    PRIMARY KEY ("ChangeId")
);

-- ============================================================
-- Table: Organizations
-- ============================================================
CREATE TABLE sqlserver_dw."Organizations" (
    "OrgId" SERIAL,
    "OrgCode" VARCHAR(20) NOT NULL,
    "OrgName" VARCHAR(200) NOT NULL,
    "OrgType" VARCHAR(30) NOT NULL,
    "ParentOrgId" INTEGER,
    "TaxId" VARCHAR(20),
    "IsActive" BOOLEAN DEFAULT TRUE NOT NULL,
    "IncorporatedDate" DATE,
    "CreatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    "UpdatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    PRIMARY KEY ("OrgId"),
    CONSTRAINT "FK__Organizat__Paren__38996AB5" FOREIGN KEY ("ParentOrgId") REFERENCES sqlserver_dw."Organizations" ("OrgId")
);

-- ============================================================
-- Table: CostCenters
-- ============================================================
CREATE TABLE sqlserver_dw."CostCenters" (
    "CostCenterId" SERIAL,
    "CostCenterCode" VARCHAR(20) NOT NULL,
    "CostCenterName" VARCHAR(200) NOT NULL,
    "Department" VARCHAR(100) NOT NULL,
    "OrgId" INTEGER,
    "BudgetAmount" NUMERIC(18,2),
    "IsActive" BOOLEAN DEFAULT TRUE NOT NULL,
    "CreatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    PRIMARY KEY ("CostCenterId"),
    CONSTRAINT "FK__CostCente__OrgId__440B1D61" FOREIGN KEY ("OrgId") REFERENCES sqlserver_dw."Organizations" ("OrgId")
);

-- ============================================================
-- Table: Customers
-- ============================================================
CREATE TABLE sqlserver_dw."Customers" (
    "CustomerId" SERIAL,
    "CustomerCode" VARCHAR(20) NOT NULL,
    "CustomerName" VARCHAR(300) NOT NULL,
    "CustomerType" VARCHAR(20) DEFAULT 'COMMERCIAL' NOT NULL,
    "IndustryCode" VARCHAR(10),
    "TaxId" VARCHAR(30),
    "BillingAddress" VARCHAR(200),
    "BillingCity" VARCHAR(100),
    "BillingState" CHAR(2),
    "BillingPostal" VARCHAR(10),
    "BillingCountry" CHAR(2) DEFAULT 'US' NOT NULL,
    "ShipAddress" VARCHAR(200),
    "ShipCity" VARCHAR(100),
    "ShipState" CHAR(2),
    "ShipPostal" VARCHAR(10),
    "ShipCountry" CHAR(2) DEFAULT 'US' NOT NULL,
    "Phone" VARCHAR(30),
    "Email" VARCHAR(200),
    "WebSite" VARCHAR(200),
    "CreditLimit" NUMERIC(14,2) DEFAULT 50000.00 NOT NULL,
    "CreditBalance" NUMERIC(14,2) DEFAULT 0.00 NOT NULL,
    "PaymentTerms" VARCHAR(20) DEFAULT 'NET30' NOT NULL,
    "PrimaryRepId" INTEGER,
    "TaxExempt" BOOLEAN DEFAULT FALSE NOT NULL,
    "IsActive" BOOLEAN DEFAULT TRUE NOT NULL,
    "CustomerSince" DATE,
    "ExternalId" UUID DEFAULT gen_random_uuid() NOT NULL,
    "CreatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    "UpdatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    PRIMARY KEY ("CustomerId")
);

-- ============================================================
-- Table: Employees
-- ============================================================
CREATE TABLE sqlserver_dw."Employees" (
    "EmployeeId" SERIAL,
    "EmployeeCode" VARCHAR(20) NOT NULL,
    "FirstName" VARCHAR(100) NOT NULL,
    "LastName" VARCHAR(100) NOT NULL,
    "Email" VARCHAR(200) NOT NULL,
    "Phone" VARCHAR(30),
    "HireDate" DATE NOT NULL,
    "TermDate" DATE,
    "Department" VARCHAR(100) NOT NULL,
    "JobTitle" VARCHAR(150) NOT NULL,
    "ManagerId" INTEGER,
    "CostCenterId" INTEGER,
    "OrgId" INTEGER,
    "BaseSalary" NUMERIC(12,2) NOT NULL,
    "Currency" CHAR(3) DEFAULT 'USD' NOT NULL,
    "EmployeeStatus" VARCHAR(20) DEFAULT 'ACTIVE' NOT NULL,
    "SSNHash" BYTEA,
    "ExternalId" UUID DEFAULT gen_random_uuid() NOT NULL,
    "CreatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    "UpdatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    PRIMARY KEY ("EmployeeId"),
    CONSTRAINT "FK__Employees__CostC__4BAC3F29" FOREIGN KEY ("CostCenterId") REFERENCES sqlserver_dw."CostCenters" ("CostCenterId"),
    CONSTRAINT "FK__Employees__Manag__4AB81AF0" FOREIGN KEY ("ManagerId") REFERENCES sqlserver_dw."Employees" ("EmployeeId"),
    CONSTRAINT "FK__Employees__OrgId__4CA06362" FOREIGN KEY ("OrgId") REFERENCES sqlserver_dw."Organizations" ("OrgId")
);

-- ============================================================
-- Table: GLAccounts
-- ============================================================
CREATE TABLE sqlserver_dw."GLAccounts" (
    "AccountId" SERIAL,
    "AccountNumber" INTEGER NOT NULL,
    "AccountName" VARCHAR(200) NOT NULL,
    "AccountType" VARCHAR(20) NOT NULL,
    "IsActive" BOOLEAN DEFAULT TRUE NOT NULL,
    "CreatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    PRIMARY KEY ("AccountId")
);

-- ============================================================
-- Table: GLTransactions
-- ============================================================
CREATE TABLE sqlserver_dw."GLTransactions" (
    "TxId" BIGSERIAL,
    "TxDate" DATE NOT NULL,
    "PostedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    "Period" CHAR(7) NOT NULL,
    "AccountId" INTEGER NOT NULL,
    "CostCenterId" INTEGER,
    "OrgId" INTEGER,
    "DebitAmount" NUMERIC(18,2) DEFAULT 0 NOT NULL,
    "CreditAmount" NUMERIC(18,2) DEFAULT 0 NOT NULL,
    "Currency" CHAR(3) DEFAULT 'USD' NOT NULL,
    "ExchangeRate" NUMERIC(14,6) DEFAULT 1.000000 NOT NULL,
    "Reference" VARCHAR(50),
    "Description" VARCHAR(300) NOT NULL,
    "JournalBatch" VARCHAR(30),
    "IsReversed" BOOLEAN DEFAULT FALSE NOT NULL,
    "PostedByEmployeeId" INTEGER,
    "CreatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    PRIMARY KEY ("TxId"),
    CONSTRAINT "FK__GLTransac__Accou__671F4F74" FOREIGN KEY ("AccountId") REFERENCES sqlserver_dw."GLAccounts" ("AccountId"),
    CONSTRAINT "FK__GLTransac__CostC__681373AD" FOREIGN KEY ("CostCenterId") REFERENCES sqlserver_dw."CostCenters" ("CostCenterId"),
    CONSTRAINT "FK__GLTransac__OrgId__690797E6" FOREIGN KEY ("OrgId") REFERENCES sqlserver_dw."Organizations" ("OrgId"),
    CONSTRAINT "FK__GLTransac__Poste__6EC0713C" FOREIGN KEY ("PostedByEmployeeId") REFERENCES sqlserver_dw."Employees" ("EmployeeId")
);

-- ============================================================
-- Table: Warehouses
-- ============================================================
CREATE TABLE sqlserver_dw."Warehouses" (
    "WarehouseId" SERIAL,
    "WarehouseCode" VARCHAR(20) NOT NULL,
    "WarehouseName" VARCHAR(200) NOT NULL,
    "OrgId" INTEGER,
    "AddressLine1" VARCHAR(200),
    "City" VARCHAR(100),
    "State" CHAR(2),
    "PostalCode" VARCHAR(10),
    "Country" CHAR(2) DEFAULT 'US' NOT NULL,
    "IsActive" BOOLEAN DEFAULT TRUE NOT NULL,
    "CreatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    PRIMARY KEY ("WarehouseId"),
    CONSTRAINT "FK__Warehouse__OrgId__72C60C4A" FOREIGN KEY ("OrgId") REFERENCES sqlserver_dw."Organizations" ("OrgId")
);

-- ============================================================
-- Table: StorageLocations
-- ============================================================
CREATE TABLE sqlserver_dw."StorageLocations" (
    "LocationId" SERIAL,
    "WarehouseId" INTEGER NOT NULL,
    "LocationCode" VARCHAR(30) NOT NULL,
    "Aisle" VARCHAR(5),
    "Bay" VARCHAR(5),
    "Level" VARCHAR(5),
    "Bin" VARCHAR(5),
    "MaxWeight" NUMERIC(10,2),
    "IsActive" BOOLEAN DEFAULT TRUE NOT NULL,
    PRIMARY KEY ("LocationId"),
    CONSTRAINT "FK__StorageLo__Wareh__797309D9" FOREIGN KEY ("WarehouseId") REFERENCES sqlserver_dw."Warehouses" ("WarehouseId")
);

-- ============================================================
-- Table: Inventory
-- ============================================================
CREATE TABLE sqlserver_dw."Inventory" (
    "InventoryId" SERIAL,
    "ProductId" INTEGER NOT NULL,
    "LocationId" INTEGER NOT NULL,
    "LotNumber" VARCHAR(50),
    "SerialNumber" VARCHAR(100),
    "QuantityOnHand" NUMERIC(14,4) DEFAULT 0 NOT NULL,
    "QuantityAllocated" NUMERIC(14,4) DEFAULT 0 NOT NULL,
    "QuantityAvailable" NUMERIC(15,4) GENERATED ALWAYS AS (("QuantityOnHand"-"QuantityAllocated")) STORED,
    "UnitCost" NUMERIC(14,4) NOT NULL,
    "ValuationMethod" VARCHAR(10) DEFAULT 'AVG' NOT NULL,
    "LastCountDate" DATE,
    "ExpirationDate" DATE,
    "CreatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    "UpdatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    PRIMARY KEY ("InventoryId"),
    CONSTRAINT "FK__Inventory__Locat__7F2BE32F" FOREIGN KEY ("LocationId") REFERENCES sqlserver_dw."StorageLocations" ("LocationId"),
    CONSTRAINT "FK__Inventory__Produ__7E37BEF6" FOREIGN KEY ("ProductId") REFERENCES sqlserver_dw."Products" ("ProductId")
);

-- ============================================================
-- Table: Vendors
-- ============================================================
CREATE TABLE sqlserver_dw."Vendors" (
    "VendorId" SERIAL,
    "VendorCode" VARCHAR(20) NOT NULL,
    "VendorName" VARCHAR(300) NOT NULL,
    "VendorType" VARCHAR(20) DEFAULT 'SUPPLIER' NOT NULL,
    "TaxId" VARCHAR(30),
    "BillingAddress" VARCHAR(200),
    "BillingCity" VARCHAR(100),
    "BillingState" CHAR(2),
    "BillingPostal" VARCHAR(10),
    "BillingCountry" CHAR(2) DEFAULT 'US' NOT NULL,
    "Phone" VARCHAR(30),
    "Email" VARCHAR(200),
    "WebSite" VARCHAR(200),
    "PaymentTerms" VARCHAR(20) DEFAULT 'NET30' NOT NULL,
    "LeadTimeDays" INTEGER DEFAULT 14 NOT NULL,
    "QualificationStatus" VARCHAR(20) DEFAULT 'APPROVED' NOT NULL,
    "IsActive" BOOLEAN DEFAULT TRUE NOT NULL,
    "ExternalId" UUID DEFAULT gen_random_uuid() NOT NULL,
    "CreatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    "UpdatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    PRIMARY KEY ("VendorId")
);

-- ============================================================
-- Table: PurchaseOrders
-- ============================================================
CREATE TABLE sqlserver_dw."PurchaseOrders" (
    "POId" SERIAL,
    "PONumber" VARCHAR(20) NOT NULL,
    "VendorId" INTEGER NOT NULL,
    "OrgId" INTEGER,
    "PODate" DATE NOT NULL,
    "RequiredDate" DATE,
    "ShipToWarehouseId" INTEGER,
    "BuyerId" INTEGER,
    "POStatus" VARCHAR(20) DEFAULT 'OPEN' NOT NULL,
    "PaymentTerms" VARCHAR(20) DEFAULT 'NET30' NOT NULL,
    "ShipMethod" VARCHAR(30),
    "TotalAmount" NUMERIC(18,2) DEFAULT 0 NOT NULL,
    "TaxAmount" NUMERIC(18,2) DEFAULT 0 NOT NULL,
    "FreightAmount" NUMERIC(18,2) DEFAULT 0 NOT NULL,
    "Currency" CHAR(3) DEFAULT 'USD' NOT NULL,
    "ExchangeRate" NUMERIC(14,6) DEFAULT 1.000000 NOT NULL,
    "Notes" TEXT,
    "CreatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    "UpdatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    PRIMARY KEY ("POId"),
    CONSTRAINT "FK__PurchaseO__Buyer__236943A5" FOREIGN KEY ("BuyerId") REFERENCES sqlserver_dw."Employees" ("EmployeeId"),
    CONSTRAINT "FK__PurchaseO__OrgId__2180FB33" FOREIGN KEY ("OrgId") REFERENCES sqlserver_dw."Organizations" ("OrgId"),
    CONSTRAINT "FK__PurchaseO__ShipT__22751F6C" FOREIGN KEY ("ShipToWarehouseId") REFERENCES sqlserver_dw."Warehouses" ("WarehouseId"),
    CONSTRAINT "FK__PurchaseO__Vendo__208CD6FA" FOREIGN KEY ("VendorId") REFERENCES sqlserver_dw."Vendors" ("VendorId")
);

-- ============================================================
-- Table: PurchaseOrderLines
-- ============================================================
CREATE TABLE sqlserver_dw."PurchaseOrderLines" (
    "POLineId" SERIAL,
    "POId" INTEGER NOT NULL,
    "LineNumber" SMALLINT NOT NULL,
    "ProductId" INTEGER NOT NULL,
    "Description" VARCHAR(300),
    "OrderedQty" NUMERIC(14,4) NOT NULL,
    "ReceivedQty" NUMERIC(14,4) DEFAULT 0 NOT NULL,
    "InvoicedQty" NUMERIC(14,4) DEFAULT 0 NOT NULL,
    "UOM" VARCHAR(10) DEFAULT 'EA' NOT NULL,
    "UnitCost" NUMERIC(14,4) NOT NULL,
    "ExtendedCost" NUMERIC(29,8) GENERATED ALWAYS AS (("OrderedQty"*"UnitCost")) STORED,
    "PromisedDate" DATE,
    "ReceivedDate" DATE,
    "CostCenterId" INTEGER,
    "LineStatus" VARCHAR(20) DEFAULT 'OPEN' NOT NULL,
    PRIMARY KEY ("POLineId"),
    CONSTRAINT "FK__PurchaseO__CostC__3493CFA7" FOREIGN KEY ("CostCenterId") REFERENCES sqlserver_dw."CostCenters" ("CostCenterId"),
    CONSTRAINT "FK__PurchaseOr__POId__2FCF1A8A" FOREIGN KEY ("POId") REFERENCES sqlserver_dw."PurchaseOrders" ("POId"),
    CONSTRAINT "FK__PurchaseO__Produ__30C33EC3" FOREIGN KEY ("ProductId") REFERENCES sqlserver_dw."Products" ("ProductId")
);

-- ============================================================
-- Table: SalesOrders
-- ============================================================
CREATE TABLE sqlserver_dw."SalesOrders" (
    "SOId" SERIAL,
    "SONumber" VARCHAR(20) NOT NULL,
    "CustomerId" INTEGER NOT NULL,
    "OrgId" INTEGER,
    "OrderDate" DATE NOT NULL,
    "RequestedDate" DATE,
    "PromisedDate" DATE,
    "ShipDate" DATE,
    "SalesRepId" INTEGER,
    "SOStatus" VARCHAR(20) DEFAULT 'OPEN' NOT NULL,
    "PaymentTerms" VARCHAR(20) DEFAULT 'NET30' NOT NULL,
    "ShipMethod" VARCHAR(30),
    "ShipToAddress" VARCHAR(200),
    "ShipToCity" VARCHAR(100),
    "ShipToState" CHAR(2),
    "ShipToPostal" VARCHAR(10),
    "ShipToCountry" CHAR(2) DEFAULT 'US' NOT NULL,
    "SubTotal" NUMERIC(18,2) DEFAULT 0 NOT NULL,
    "DiscountAmount" NUMERIC(18,2) DEFAULT 0 NOT NULL,
    "TaxAmount" NUMERIC(18,2) DEFAULT 0 NOT NULL,
    "FreightAmount" NUMERIC(18,2) DEFAULT 0 NOT NULL,
    "TotalAmount" NUMERIC(18,2) DEFAULT 0 NOT NULL,
    "Currency" CHAR(3) DEFAULT 'USD' NOT NULL,
    "POReference" VARCHAR(50),
    "Notes" TEXT,
    "CreatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    "UpdatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    PRIMARY KEY ("SOId"),
    CONSTRAINT "FK__SalesOrde__Custo__395884C4" FOREIGN KEY ("CustomerId") REFERENCES sqlserver_dw."Customers" ("CustomerId"),
    CONSTRAINT "FK__SalesOrde__OrgId__3A4CA8FD" FOREIGN KEY ("OrgId") REFERENCES sqlserver_dw."Organizations" ("OrgId"),
    CONSTRAINT "FK__SalesOrde__Sales__3B40CD36" FOREIGN KEY ("SalesRepId") REFERENCES sqlserver_dw."Employees" ("EmployeeId")
);

-- ============================================================
-- Table: SalesOrderLines
-- ============================================================
CREATE TABLE sqlserver_dw."SalesOrderLines" (
    "SOLineId" SERIAL,
    "SOId" INTEGER NOT NULL,
    "LineNumber" SMALLINT NOT NULL,
    "ProductId" INTEGER NOT NULL,
    "Description" VARCHAR(300),
    "OrderedQty" NUMERIC(14,4) NOT NULL,
    "ShippedQty" NUMERIC(14,4) DEFAULT 0 NOT NULL,
    "InvoicedQty" NUMERIC(14,4) DEFAULT 0 NOT NULL,
    "UOM" VARCHAR(10) DEFAULT 'EA' NOT NULL,
    "UnitPrice" NUMERIC(14,4) NOT NULL,
    "DiscountPct" NUMERIC(6,4) DEFAULT 0 NOT NULL,
    "ExtendedPrice" NUMERIC(37,12) GENERATED ALWAYS AS ((("OrderedQty"*"UnitPrice")*((1)-"DiscountPct"))) STORED,
    "WarehouseId" INTEGER,
    "LineStatus" VARCHAR(20) DEFAULT 'OPEN' NOT NULL,
    PRIMARY KEY ("SOLineId"),
    CONSTRAINT "FK__SalesOrde__Produ__4A8310C6" FOREIGN KEY ("ProductId") REFERENCES sqlserver_dw."Products" ("ProductId"),
    CONSTRAINT "FK__SalesOrder__SOId__498EEC8D" FOREIGN KEY ("SOId") REFERENCES sqlserver_dw."SalesOrders" ("SOId"),
    CONSTRAINT "FK__SalesOrde__Wareh__4F47C5E3" FOREIGN KEY ("WarehouseId") REFERENCES sqlserver_dw."Warehouses" ("WarehouseId")
);

-- ============================================================
-- Table: WorkOrders
-- ============================================================
CREATE TABLE sqlserver_dw."WorkOrders" (
    "WOId" SERIAL,
    "WONumber" VARCHAR(20) NOT NULL,
    "ProductId" INTEGER NOT NULL,
    "SOLineId" INTEGER,
    "WarehouseId" INTEGER,
    "PlannedQty" NUMERIC(14,4) NOT NULL,
    "CompletedQty" NUMERIC(14,4) DEFAULT 0 NOT NULL,
    "ScrapQty" NUMERIC(14,4) DEFAULT 0 NOT NULL,
    "WOStatus" VARCHAR(20) DEFAULT 'PLANNED' NOT NULL,
    "Priority" SMALLINT DEFAULT 5 NOT NULL,
    "PlannedStartDate" DATE NOT NULL,
    "PlannedEndDate" DATE NOT NULL,
    "ActualStartDate" DATE,
    "ActualEndDate" DATE,
    "PlannerEmployeeId" INTEGER,
    "LotNumber" VARCHAR(50),
    "Notes" TEXT,
    "CreatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    "UpdatedAt" TIMESTAMP(7) DEFAULT NOW() NOT NULL,
    PRIMARY KEY ("WOId"),
    CONSTRAINT "FK__WorkOrder__Plann__5AB9788F" FOREIGN KEY ("PlannerEmployeeId") REFERENCES sqlserver_dw."Employees" ("EmployeeId"),
    CONSTRAINT "FK__WorkOrder__Produ__540C7B00" FOREIGN KEY ("ProductId") REFERENCES sqlserver_dw."Products" ("ProductId"),
    CONSTRAINT "FK__WorkOrder__SOLin__55009F39" FOREIGN KEY ("SOLineId") REFERENCES sqlserver_dw."SalesOrderLines" ("SOLineId"),
    CONSTRAINT "FK__WorkOrder__Wareh__55F4C372" FOREIGN KEY ("WarehouseId") REFERENCES sqlserver_dw."Warehouses" ("WarehouseId")
);

-- ============================================================
-- Table: WorkOrderOperations
-- ============================================================
CREATE TABLE sqlserver_dw."WorkOrderOperations" (
    "WOOpId" SERIAL,
    "WOId" INTEGER NOT NULL,
    "OperationSeq" SMALLINT NOT NULL,
    "OperationCode" VARCHAR(20) NOT NULL,
    "OperationName" VARCHAR(200) NOT NULL,
    "CostCenterId" INTEGER,
    "SetupHours" NUMERIC(8,4) DEFAULT 0 NOT NULL,
    "RunHoursPerUnit" NUMERIC(8,4) NOT NULL,
    "PlannedHours" NUMERIC(10,4),
    "ActualHours" NUMERIC(10,4),
    "LaborRate" NUMERIC(10,4),
    "MachineRate" NUMERIC(10,4),
    "OpStatus" VARCHAR(20) DEFAULT 'PENDING' NOT NULL,
    PRIMARY KEY ("WOOpId"),
    CONSTRAINT "FK__WorkOrder__CostC__6166761E" FOREIGN KEY ("CostCenterId") REFERENCES sqlserver_dw."CostCenters" ("CostCenterId"),
    CONSTRAINT "FK__WorkOrderO__WOId__607251E5" FOREIGN KEY ("WOId") REFERENCES sqlserver_dw."WorkOrders" ("WOId")
);
