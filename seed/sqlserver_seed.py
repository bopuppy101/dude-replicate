#!/usr/bin/env python3
"""
Enterprise ERP/Manufacturing seed script for SQL Server (Azure SQL Edge).
Creates realistic schema with tens of thousands of rows across multiple domains:
  - HR / Organization
  - Product Catalog & BOM
  - Customer & Vendor Master
  - Purchasing (PO)
  - Sales (SO)
  - Inventory & Warehousing
  - Manufacturing (Work Orders)
  - General Ledger / Finance
"""

import pymssql
import random
import uuid
import string
from datetime import datetime, timedelta
from decimal import Decimal
import time

import os
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

SERVER   = os.getenv('MSSQL_HOST', '127.0.0.1')
PORT     = int(os.getenv('MSSQL_PORT', '1433'))
USER     = os.getenv('MSSQL_USER', 'sa')
PASSWORD = os.getenv('MSSQL_PASS', '')
DB       = os.getenv('MSSQL_DB', 'EnterpriseDW')

random.seed(42)  # reproducible


# ── helpers ──────────────────────────────────────────────────────────────────

def rnd_date(start_year=2018, end_year=2025):
    start = datetime(start_year, 1, 1)
    end   = datetime(end_year, 12, 31)
    return start + timedelta(days=random.randint(0, (end - start).days))

def rnd_future(base_date, days=30, variance=30):
    return base_date + timedelta(days=days + random.randint(0, variance))

FIRST_NAMES = [
    "James","John","Robert","Michael","William","David","Richard","Joseph",
    "Thomas","Charles","Linda","Barbara","Patricia","Jennifer","Mary","Nancy",
    "Karen","Lisa","Betty","Dorothy","Sarah","Kevin","Brian","George","Edward",
    "Donna","Carol","Ruth","Sharon","Michelle","Laura","Sandra","Kimberly","Helen",
    "Deborah","Amy","Angela","Stephanie","Rebecca","Anna","Maria","Emma","Olivia"
]
LAST_NAMES = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis",
    "Rodriguez","Martinez","Hernandez","Lopez","Gonzalez","Wilson","Anderson",
    "Thomas","Taylor","Moore","Jackson","Martin","Lee","Perez","Thompson","White",
    "Harris","Sanchez","Clark","Ramirez","Lewis","Robinson","Walker","Young","Allen",
    "King","Wright","Scott","Torres","Nguyen","Hill","Flores","Green","Adams","Nelson"
]
STREET_NAMES = [
    "Main St","Oak Ave","Maple Dr","Cedar Ln","Elm St","Pine Rd","Lake Blvd",
    "Park Way","River Rd","Sunset Blvd","Commerce Dr","Industrial Pkwy","Tech Ct"
]
CITIES = [
    ("Chicago","IL","60601"),("Houston","TX","77001"),("Phoenix","AZ","85001"),
    ("Philadelphia","PA","19101"),("San Antonio","TX","78201"),("Dallas","TX","75201"),
    ("San Jose","CA","95101"),("Austin","TX","73301"),("Jacksonville","FL","32099"),
    ("Columbus","OH","43085"),("Charlotte","NC","28201"),("Indianapolis","IN","46201"),
    ("Fort Worth","TX","76101"),("Seattle","WA","98101"),("Denver","CO","80201"),
    ("Nashville","TN","37201"),("Louisville","KY","40201"),("Memphis","TN","38101"),
    ("Portland","OR","97201"),("Oklahoma City","OK","73101"),("Las Vegas","NV","89101"),
    ("Baltimore","MD","21201"),("Milwaukee","WI","53201"),("Albuquerque","NM","87101"),
    ("Tucson","AZ","85701"),("Fresno","CA","93701"),("Sacramento","CA","95814"),
    ("Kansas City","MO","64101"),("Atlanta","GA","30301"),("Omaha","NE","68101")
]

DEPARTMENTS = [
    "Engineering","Manufacturing","Quality Assurance","Supply Chain",
    "Sales","Marketing","Finance","Human Resources","Information Technology",
    "Research & Development","Operations","Legal","Customer Service",
    "Procurement","Logistics","Maintenance","Production Planning","EHS"
]

JOB_TITLES = [
    "Engineer I","Engineer II","Senior Engineer","Principal Engineer","Staff Engineer",
    "Manager","Senior Manager","Director","VP","Associate","Analyst","Senior Analyst",
    "Technician","Lead Technician","Supervisor","Coordinator","Specialist","Consultant",
    "Planner","Buyer","Controller","Accountant","HR Generalist","Recruiter"
]

PRODUCT_LINES = [
    ("MECH","Mechanical Components"),
    ("ELEC","Electrical Components"),
    ("HYDR","Hydraulic Systems"),
    ("PNEU","Pneumatic Systems"),
    ("CTRL","Control Systems"),
    ("SAFE","Safety Equipment"),
    ("TOOL","Tooling & Fixtures"),
    ("RAW","Raw Materials"),
    ("PACK","Packaging"),
    ("MRO","Maintenance Repair Operations")
]

PRODUCT_ADJECTIVES = [
    "Heavy-Duty","Precision","High-Performance","Industrial","Commercial",
    "Standard","Enhanced","Reinforced","Lightweight","Corrosion-Resistant",
    "High-Temp","Low-Friction","Sealed","Modular","Integrated"
]
PRODUCT_NOUNS = {
    "MECH": ["Bearing","Shaft","Coupling","Gear","Sprocket","Bushing","Seal Ring","Flange","Bracket","Housing"],
    "ELEC": ["Relay","Contactor","Circuit Breaker","Transformer","Motor","VFD Drive","Sensor","PLC Module","Cable Assembly","Switch"],
    "HYDR": ["Cylinder","Pump","Valve","Manifold","Accumulator","Filter","Hose Assembly","Fitting","Reservoir","Actuator"],
    "PNEU": ["Air Cylinder","Solenoid Valve","Regulator","Filter-Regulator","Muffler","Fitting","Tubing Assembly","Air Motor","Gripper","Actuator"],
    "CTRL": ["Controller","HMI Panel","I/O Module","Communication Gateway","Motion Controller","Safety PLC","Servo Drive","Encoder","Fieldbus Node","Cabinet"],
    "SAFE": ["Safety Barrier","Light Curtain","E-Stop Button","Safety Relay","Door Interlock","Guard Rail","PPE Kit","Lockout Kit","Warning Beacon","Safety Mat"],
    "TOOL": ["Cutting Insert","End Mill","Drill Bit","Tap","Reamer","Boring Bar","Fixture Plate","Collet","Tool Holder","Gauge Block"],
    "RAW":  ["Steel Plate","Aluminum Bar","Copper Rod","Stainless Sheet","Carbon Fiber Panel","Plastic Pellets","Rubber Sheet","Brass Rod","Cast Iron Blank","Titanium Bar"],
    "PACK": ["Corrugated Box","Foam Insert","Stretch Film","Pallet","Strapping Band","Bubble Wrap","Label Roll","Void Fill","Moisture Barrier","Crate"],
    "MRO":  ["Lubricant","Cleaner","Adhesive","Sealant","Fastener Kit","O-Ring Kit","Belt Set","Filter Set","Gasket Material","Wire Duct"]
}

UNITS_OF_MEASURE = ["EA","PC","KG","LB","FT","M","L","GAL","BOX","ROLL","SET","KIT","PKG","PR","CS"]

PAYMENT_TERMS = ["NET30","NET45","NET60","NET15","2/10NET30","DUE_ON_RECEIPT","NET90"]
SHIP_METHODS  = ["UPS_GROUND","FEDEX_EXPRESS","USPS_PRIORITY","FREIGHT_LTL","FREIGHT_FTL","CUSTOMER_PICKUP","DROP_SHIP"]

GL_ACCOUNTS = [
    (1000,"Cash and Cash Equivalents","ASSET"),
    (1100,"Accounts Receivable","ASSET"),
    (1200,"Inventory - Raw Materials","ASSET"),
    (1201,"Inventory - WIP","ASSET"),
    (1202,"Inventory - Finished Goods","ASSET"),
    (1300,"Prepaid Expenses","ASSET"),
    (1500,"Property, Plant & Equipment","ASSET"),
    (1600,"Accumulated Depreciation","ASSET"),
    (2000,"Accounts Payable","LIABILITY"),
    (2100,"Accrued Liabilities","LIABILITY"),
    (2200,"Deferred Revenue","LIABILITY"),
    (2300,"Notes Payable","LIABILITY"),
    (2400,"Income Taxes Payable","LIABILITY"),
    (3000,"Common Stock","EQUITY"),
    (3100,"Retained Earnings","EQUITY"),
    (3200,"Additional Paid-In Capital","EQUITY"),
    (4000,"Product Revenue","REVENUE"),
    (4100,"Service Revenue","REVENUE"),
    (4200,"Scrap & Rework Recovery","REVENUE"),
    (5000,"Cost of Goods Sold","COGS"),
    (5100,"Direct Labor","COGS"),
    (5200,"Manufacturing Overhead","COGS"),
    (6000,"Sales & Marketing Expense","OPEX"),
    (6100,"General & Administrative","OPEX"),
    (6200,"Research & Development","OPEX"),
    (6300,"Depreciation & Amortization","OPEX"),
    (6400,"Utilities","OPEX"),
    (6500,"Rent & Facilities","OPEX"),
    (7000,"Interest Expense","OTHER"),
    (7100,"Interest Income","OTHER"),
    (8000,"Income Tax Expense","OTHER"),
]

COST_CENTERS = [
    ("CC-100","Assembly Line A","Manufacturing"),
    ("CC-101","Assembly Line B","Manufacturing"),
    ("CC-102","Assembly Line C","Manufacturing"),
    ("CC-200","Machining Cell 1","Manufacturing"),
    ("CC-201","Machining Cell 2","Manufacturing"),
    ("CC-300","Quality Lab","Quality Assurance"),
    ("CC-400","Shipping & Receiving","Logistics"),
    ("CC-500","Engineering Services","Engineering"),
    ("CC-600","IT Operations","Information Technology"),
    ("CC-700","Corporate G&A","Finance"),
    ("CC-800","Sales Operations","Sales"),
    ("CC-900","R&D Lab","Research & Development"),
]

def rnd_address():
    city_info = random.choice(CITIES)
    return (
        f"{random.randint(100,9999)} {random.choice(STREET_NAMES)}",
        city_info[0], city_info[1], city_info[2], "US"
    )

def rnd_phone():
    return f"+1-{random.randint(200,999)}-{random.randint(200,999)}-{random.randint(1000,9999)}"

def rnd_name():
    return random.choice(FIRST_NAMES), random.choice(LAST_NAMES)

def rnd_email(first, last, domain="acmecorp.com"):
    return f"{first.lower()}.{last.lower()}{random.randint(1,99)}@{domain}"


# ── DDL ───────────────────────────────────────────────────────────────────────

DDL = """
-- ============================================================
-- ORGANIZATIONS
-- ============================================================
CREATE TABLE Organizations (
    OrgId           INT IDENTITY(1,1) PRIMARY KEY,
    OrgCode         VARCHAR(20)  NOT NULL UNIQUE,
    OrgName         NVARCHAR(200) NOT NULL,
    OrgType         VARCHAR(30)  NOT NULL,  -- COMPANY | DIVISION | PLANT | WAREHOUSE
    ParentOrgId     INT          REFERENCES Organizations(OrgId),
    TaxId           VARCHAR(20),
    IsActive        BIT          NOT NULL DEFAULT 1,
    IncorporatedDate DATE,
    CreatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE(),
    UpdatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE()
);

-- ============================================================
-- GL ACCOUNTS
-- ============================================================
CREATE TABLE GLAccounts (
    AccountId       INT IDENTITY(1,1) PRIMARY KEY,
    AccountNumber   INT          NOT NULL UNIQUE,
    AccountName     NVARCHAR(200) NOT NULL,
    AccountType     VARCHAR(20)  NOT NULL,  -- ASSET|LIABILITY|EQUITY|REVENUE|COGS|OPEX|OTHER
    IsActive        BIT          NOT NULL DEFAULT 1,
    CreatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE()
);

-- ============================================================
-- COST CENTERS
-- ============================================================
CREATE TABLE CostCenters (
    CostCenterId    INT IDENTITY(1,1) PRIMARY KEY,
    CostCenterCode  VARCHAR(20)  NOT NULL UNIQUE,
    CostCenterName  NVARCHAR(200) NOT NULL,
    Department      NVARCHAR(100) NOT NULL,
    OrgId           INT          REFERENCES Organizations(OrgId),
    BudgetAmount    DECIMAL(18,2),
    IsActive        BIT          NOT NULL DEFAULT 1,
    CreatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE()
);

-- ============================================================
-- EMPLOYEES
-- ============================================================
CREATE TABLE Employees (
    EmployeeId      INT IDENTITY(1,1) PRIMARY KEY,
    EmployeeCode    VARCHAR(20)  NOT NULL UNIQUE,
    FirstName       NVARCHAR(100) NOT NULL,
    LastName        NVARCHAR(100) NOT NULL,
    Email           NVARCHAR(200) NOT NULL UNIQUE,
    Phone           VARCHAR(30),
    HireDate        DATE         NOT NULL,
    TermDate        DATE,
    Department      NVARCHAR(100) NOT NULL,
    JobTitle        NVARCHAR(150) NOT NULL,
    ManagerId       INT          REFERENCES Employees(EmployeeId),
    CostCenterId    INT          REFERENCES CostCenters(CostCenterId),
    OrgId           INT          REFERENCES Organizations(OrgId),
    BaseSalary      DECIMAL(12,2) NOT NULL,
    Currency        CHAR(3)      NOT NULL DEFAULT 'USD',
    EmployeeStatus  VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE|TERMINATED|LOA
    SSNHash         VARBINARY(32),  -- stored as hash, not plaintext
    ExternalId      UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
    CreatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE(),
    UpdatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE()
);

CREATE INDEX IX_Employees_Dept ON Employees(Department);
CREATE INDEX IX_Employees_Manager ON Employees(ManagerId);
CREATE INDEX IX_Employees_CostCenter ON Employees(CostCenterId);

-- ============================================================
-- PRODUCT CATEGORIES
-- ============================================================
CREATE TABLE ProductCategories (
    CategoryId      INT IDENTITY(1,1) PRIMARY KEY,
    CategoryCode    VARCHAR(10)  NOT NULL UNIQUE,
    CategoryName    NVARCHAR(200) NOT NULL,
    ParentCategoryId INT         REFERENCES ProductCategories(CategoryId),
    Description     NVARCHAR(MAX),
    IsActive        BIT          NOT NULL DEFAULT 1,
    CreatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE()
);

-- ============================================================
-- PRODUCTS
-- ============================================================
CREATE TABLE Products (
    ProductId       INT IDENTITY(1,1) PRIMARY KEY,
    ProductCode     VARCHAR(30)  NOT NULL UNIQUE,
    ProductName     NVARCHAR(300) NOT NULL,
    CategoryId      INT          NOT NULL REFERENCES ProductCategories(CategoryId),
    UOM             VARCHAR(10)  NOT NULL DEFAULT 'EA',
    StandardCost    DECIMAL(14,4) NOT NULL,
    ListPrice       DECIMAL(14,4) NOT NULL,
    Weight          DECIMAL(10,4),         -- kg
    WeightUOM       VARCHAR(5),
    LeadTimeDays    INT          NOT NULL DEFAULT 14,
    MinOrderQty     DECIMAL(12,3) NOT NULL DEFAULT 1,
    ReorderPoint    DECIMAL(12,3),
    SafetyStock     DECIMAL(12,3),
    IsActive        BIT          NOT NULL DEFAULT 1,
    IsPurchased     BIT          NOT NULL DEFAULT 1,
    IsManufactured  BIT          NOT NULL DEFAULT 0,
    IsSold          BIT          NOT NULL DEFAULT 1,
    DrawingNumber   VARCHAR(50),
    Revision        VARCHAR(5),
    ProductGUID     UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
    CreatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE(),
    UpdatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE()
);

CREATE INDEX IX_Products_Category ON Products(CategoryId);
CREATE INDEX IX_Products_Active ON Products(IsActive) WHERE IsActive = 1;

-- ============================================================
-- BILL OF MATERIALS
-- ============================================================
CREATE TABLE BillOfMaterials (
    BOMId           INT IDENTITY(1,1) PRIMARY KEY,
    ParentProductId INT          NOT NULL REFERENCES Products(ProductId),
    ChildProductId  INT          NOT NULL REFERENCES Products(ProductId),
    Quantity        DECIMAL(14,4) NOT NULL DEFAULT 1,
    UOM             VARCHAR(10)  NOT NULL DEFAULT 'EA',
    BOMLevel        INT          NOT NULL DEFAULT 1,
    IsPhantom       BIT          NOT NULL DEFAULT 0,  -- phantom/intermediate assembly
    ScrapPercent    DECIMAL(6,4) NOT NULL DEFAULT 0,
    EffectiveFrom   DATE         NOT NULL,
    EffectiveTo     DATE,
    CreatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE(),
    CONSTRAINT UQ_BOM UNIQUE (ParentProductId, ChildProductId, EffectiveFrom)
);

CREATE INDEX IX_BOM_Parent ON BillOfMaterials(ParentProductId);
CREATE INDEX IX_BOM_Child  ON BillOfMaterials(ChildProductId);

-- ============================================================
-- WAREHOUSES / LOCATIONS
-- ============================================================
CREATE TABLE Warehouses (
    WarehouseId     INT IDENTITY(1,1) PRIMARY KEY,
    WarehouseCode   VARCHAR(20)  NOT NULL UNIQUE,
    WarehouseName   NVARCHAR(200) NOT NULL,
    OrgId           INT          REFERENCES Organizations(OrgId),
    AddressLine1    NVARCHAR(200),
    City            NVARCHAR(100),
    State           CHAR(2),
    PostalCode      VARCHAR(10),
    Country         CHAR(2)      NOT NULL DEFAULT 'US',
    IsActive        BIT          NOT NULL DEFAULT 1,
    CreatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE()
);

CREATE TABLE StorageLocations (
    LocationId      INT IDENTITY(1,1) PRIMARY KEY,
    WarehouseId     INT          NOT NULL REFERENCES Warehouses(WarehouseId),
    LocationCode    VARCHAR(30)  NOT NULL,
    Aisle           VARCHAR(5),
    Bay             VARCHAR(5),
    Level           VARCHAR(5),
    Bin             VARCHAR(5),
    MaxWeight       DECIMAL(10,2),         -- kg
    IsActive        BIT          NOT NULL DEFAULT 1,
    CONSTRAINT UQ_Location UNIQUE (WarehouseId, LocationCode)
);

CREATE INDEX IX_Location_Warehouse ON StorageLocations(WarehouseId);

-- ============================================================
-- INVENTORY
-- ============================================================
CREATE TABLE Inventory (
    InventoryId     INT IDENTITY(1,1) PRIMARY KEY,
    ProductId       INT          NOT NULL REFERENCES Products(ProductId),
    LocationId      INT          NOT NULL REFERENCES StorageLocations(LocationId),
    LotNumber       VARCHAR(50),
    SerialNumber    VARCHAR(100),
    QuantityOnHand  DECIMAL(14,4) NOT NULL DEFAULT 0,
    QuantityAllocated DECIMAL(14,4) NOT NULL DEFAULT 0,
    QuantityAvailable AS (QuantityOnHand - QuantityAllocated),
    UnitCost        DECIMAL(14,4) NOT NULL,
    ValuationMethod VARCHAR(10)  NOT NULL DEFAULT 'AVG',  -- AVG|FIFO|LIFO|STD
    LastCountDate   DATE,
    ExpirationDate  DATE,
    CreatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE(),
    UpdatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE(),
    CONSTRAINT UQ_Inventory UNIQUE (ProductId, LocationId, LotNumber)
);

CREATE INDEX IX_Inventory_Product  ON Inventory(ProductId);
CREATE INDEX IX_Inventory_Location ON Inventory(LocationId);

-- ============================================================
-- CUSTOMERS
-- ============================================================
CREATE TABLE Customers (
    CustomerId      INT IDENTITY(1,1) PRIMARY KEY,
    CustomerCode    VARCHAR(20)  NOT NULL UNIQUE,
    CustomerName    NVARCHAR(300) NOT NULL,
    CustomerType    VARCHAR(20)  NOT NULL DEFAULT 'COMMERCIAL',  -- COMMERCIAL|GOVERNMENT|DISTRIBUTOR|OEM
    IndustryCode    VARCHAR(10),
    TaxId           VARCHAR(30),
    BillingAddress  NVARCHAR(200),
    BillingCity     NVARCHAR(100),
    BillingState    CHAR(2),
    BillingPostal   VARCHAR(10),
    BillingCountry  CHAR(2)      NOT NULL DEFAULT 'US',
    ShipAddress     NVARCHAR(200),
    ShipCity        NVARCHAR(100),
    ShipState       CHAR(2),
    ShipPostal      VARCHAR(10),
    ShipCountry     CHAR(2)      NOT NULL DEFAULT 'US',
    Phone           VARCHAR(30),
    Email           NVARCHAR(200),
    WebSite         NVARCHAR(200),
    CreditLimit     DECIMAL(14,2) NOT NULL DEFAULT 50000.00,
    CreditBalance   DECIMAL(14,2) NOT NULL DEFAULT 0.00,
    PaymentTerms    VARCHAR(20)  NOT NULL DEFAULT 'NET30',
    PrimaryRepId    INT,                    -- FK to Employees added later
    TaxExempt       BIT          NOT NULL DEFAULT 0,
    IsActive        BIT          NOT NULL DEFAULT 1,
    CustomerSince   DATE,
    ExternalId      UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
    CreatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE(),
    UpdatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE()
);

CREATE INDEX IX_Customers_Type   ON Customers(CustomerType);
CREATE INDEX IX_Customers_Active ON Customers(IsActive) WHERE IsActive = 1;

-- ============================================================
-- VENDORS
-- ============================================================
CREATE TABLE Vendors (
    VendorId        INT IDENTITY(1,1) PRIMARY KEY,
    VendorCode      VARCHAR(20)  NOT NULL UNIQUE,
    VendorName      NVARCHAR(300) NOT NULL,
    VendorType      VARCHAR(20)  NOT NULL DEFAULT 'SUPPLIER',  -- SUPPLIER|CONTRACTOR|SERVICE
    TaxId           VARCHAR(30),
    BillingAddress  NVARCHAR(200),
    BillingCity     NVARCHAR(100),
    BillingState    CHAR(2),
    BillingPostal   VARCHAR(10),
    BillingCountry  CHAR(2)      NOT NULL DEFAULT 'US',
    Phone           VARCHAR(30),
    Email           NVARCHAR(200),
    WebSite         NVARCHAR(200),
    PaymentTerms    VARCHAR(20)  NOT NULL DEFAULT 'NET30',
    LeadTimeDays    INT          NOT NULL DEFAULT 14,
    QualificationStatus VARCHAR(20) NOT NULL DEFAULT 'APPROVED',
    IsActive        BIT          NOT NULL DEFAULT 1,
    ExternalId      UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
    CreatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE(),
    UpdatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE()
);

-- ============================================================
-- PURCHASE ORDERS
-- ============================================================
CREATE TABLE PurchaseOrders (
    POId            INT IDENTITY(1,1) PRIMARY KEY,
    PONumber        VARCHAR(20)  NOT NULL UNIQUE,
    VendorId        INT          NOT NULL REFERENCES Vendors(VendorId),
    OrgId           INT          REFERENCES Organizations(OrgId),
    PODate          DATE         NOT NULL,
    RequiredDate    DATE,
    ShipToWarehouseId INT        REFERENCES Warehouses(WarehouseId),
    BuyerId         INT          REFERENCES Employees(EmployeeId),
    POStatus        VARCHAR(20)  NOT NULL DEFAULT 'OPEN',  -- OPEN|PARTIAL|RECEIVED|INVOICED|CLOSED|CANCELLED
    PaymentTerms    VARCHAR(20)  NOT NULL DEFAULT 'NET30',
    ShipMethod      VARCHAR(30),
    TotalAmount     DECIMAL(18,2) NOT NULL DEFAULT 0,
    TaxAmount       DECIMAL(18,2) NOT NULL DEFAULT 0,
    FreightAmount   DECIMAL(18,2) NOT NULL DEFAULT 0,
    Currency        CHAR(3)      NOT NULL DEFAULT 'USD',
    ExchangeRate    DECIMAL(14,6) NOT NULL DEFAULT 1.000000,
    Notes           NVARCHAR(MAX),
    CreatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE(),
    UpdatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE()
);

CREATE INDEX IX_PO_Vendor  ON PurchaseOrders(VendorId);
CREATE INDEX IX_PO_Status  ON PurchaseOrders(POStatus);
CREATE INDEX IX_PO_Date    ON PurchaseOrders(PODate);

CREATE TABLE PurchaseOrderLines (
    POLineId        INT IDENTITY(1,1) PRIMARY KEY,
    POId            INT          NOT NULL REFERENCES PurchaseOrders(POId),
    LineNumber      SMALLINT     NOT NULL,
    ProductId       INT          NOT NULL REFERENCES Products(ProductId),
    Description     NVARCHAR(300),
    OrderedQty      DECIMAL(14,4) NOT NULL,
    ReceivedQty     DECIMAL(14,4) NOT NULL DEFAULT 0,
    InvoicedQty     DECIMAL(14,4) NOT NULL DEFAULT 0,
    UOM             VARCHAR(10)  NOT NULL DEFAULT 'EA',
    UnitCost        DECIMAL(14,4) NOT NULL,
    ExtendedCost    AS (OrderedQty * UnitCost),
    PromisedDate    DATE,
    ReceivedDate    DATE,
    CostCenterId    INT          REFERENCES CostCenters(CostCenterId),
    LineStatus      VARCHAR(20)  NOT NULL DEFAULT 'OPEN',
    CONSTRAINT UQ_POLine UNIQUE (POId, LineNumber)
);

CREATE INDEX IX_POLine_PO      ON PurchaseOrderLines(POId);
CREATE INDEX IX_POLine_Product ON PurchaseOrderLines(ProductId);

-- ============================================================
-- SALES ORDERS
-- ============================================================
CREATE TABLE SalesOrders (
    SOId            INT IDENTITY(1,1) PRIMARY KEY,
    SONumber        VARCHAR(20)  NOT NULL UNIQUE,
    CustomerId      INT          NOT NULL REFERENCES Customers(CustomerId),
    OrgId           INT          REFERENCES Organizations(OrgId),
    OrderDate       DATE         NOT NULL,
    RequestedDate   DATE,
    PromisedDate    DATE,
    ShipDate        DATE,
    SalesRepId      INT          REFERENCES Employees(EmployeeId),
    SOStatus        VARCHAR(20)  NOT NULL DEFAULT 'OPEN',  -- OPEN|PARTIAL|SHIPPED|INVOICED|CLOSED|CANCELLED
    PaymentTerms    VARCHAR(20)  NOT NULL DEFAULT 'NET30',
    ShipMethod      VARCHAR(30),
    ShipToAddress   NVARCHAR(200),
    ShipToCity      NVARCHAR(100),
    ShipToState     CHAR(2),
    ShipToPostal    VARCHAR(10),
    ShipToCountry   CHAR(2)      NOT NULL DEFAULT 'US',
    SubTotal        DECIMAL(18,2) NOT NULL DEFAULT 0,
    DiscountAmount  DECIMAL(18,2) NOT NULL DEFAULT 0,
    TaxAmount       DECIMAL(18,2) NOT NULL DEFAULT 0,
    FreightAmount   DECIMAL(18,2) NOT NULL DEFAULT 0,
    TotalAmount     DECIMAL(18,2) NOT NULL DEFAULT 0,
    Currency        CHAR(3)      NOT NULL DEFAULT 'USD',
    POReference     VARCHAR(50),          -- customer's PO number
    Notes           NVARCHAR(MAX),
    CreatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE(),
    UpdatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE()
);

CREATE INDEX IX_SO_Customer ON SalesOrders(CustomerId);
CREATE INDEX IX_SO_Status   ON SalesOrders(SOStatus);
CREATE INDEX IX_SO_Date     ON SalesOrders(OrderDate);
CREATE INDEX IX_SO_Rep      ON SalesOrders(SalesRepId);

CREATE TABLE SalesOrderLines (
    SOLineId        INT IDENTITY(1,1) PRIMARY KEY,
    SOId            INT          NOT NULL REFERENCES SalesOrders(SOId),
    LineNumber      SMALLINT     NOT NULL,
    ProductId       INT          NOT NULL REFERENCES Products(ProductId),
    Description     NVARCHAR(300),
    OrderedQty      DECIMAL(14,4) NOT NULL,
    ShippedQty      DECIMAL(14,4) NOT NULL DEFAULT 0,
    InvoicedQty     DECIMAL(14,4) NOT NULL DEFAULT 0,
    UOM             VARCHAR(10)  NOT NULL DEFAULT 'EA',
    UnitPrice       DECIMAL(14,4) NOT NULL,
    DiscountPct     DECIMAL(6,4) NOT NULL DEFAULT 0,
    ExtendedPrice   AS (OrderedQty * UnitPrice * (1 - DiscountPct)),
    WarehouseId     INT          REFERENCES Warehouses(WarehouseId),
    LineStatus      VARCHAR(20)  NOT NULL DEFAULT 'OPEN',
    CONSTRAINT UQ_SOLine UNIQUE (SOId, LineNumber)
);

CREATE INDEX IX_SOLine_SO      ON SalesOrderLines(SOId);
CREATE INDEX IX_SOLine_Product ON SalesOrderLines(ProductId);

-- ============================================================
-- WORK ORDERS (Manufacturing)
-- ============================================================
CREATE TABLE WorkOrders (
    WOId            INT IDENTITY(1,1) PRIMARY KEY,
    WONumber        VARCHAR(20)  NOT NULL UNIQUE,
    ProductId       INT          NOT NULL REFERENCES Products(ProductId),
    SOLineId        INT          REFERENCES SalesOrderLines(SOLineId),
    WarehouseId     INT          REFERENCES Warehouses(WarehouseId),
    PlannedQty      DECIMAL(14,4) NOT NULL,
    CompletedQty    DECIMAL(14,4) NOT NULL DEFAULT 0,
    ScrapQty        DECIMAL(14,4) NOT NULL DEFAULT 0,
    WOStatus        VARCHAR(20)  NOT NULL DEFAULT 'PLANNED',  -- PLANNED|RELEASED|IN_PROGRESS|COMPLETED|CLOSED|CANCELLED
    Priority        TINYINT      NOT NULL DEFAULT 5,          -- 1=highest, 10=lowest
    PlannedStartDate DATE        NOT NULL,
    PlannedEndDate   DATE        NOT NULL,
    ActualStartDate  DATE,
    ActualEndDate    DATE,
    PlannerEmployeeId INT        REFERENCES Employees(EmployeeId),
    LotNumber       VARCHAR(50),
    Notes           NVARCHAR(MAX),
    CreatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE(),
    UpdatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE()
);

CREATE INDEX IX_WO_Product ON WorkOrders(ProductId);
CREATE INDEX IX_WO_Status  ON WorkOrders(WOStatus);
CREATE INDEX IX_WO_Dates   ON WorkOrders(PlannedStartDate, PlannedEndDate);

CREATE TABLE WorkOrderOperations (
    WOOpId          INT IDENTITY(1,1) PRIMARY KEY,
    WOId            INT          NOT NULL REFERENCES WorkOrders(WOId),
    OperationSeq    SMALLINT     NOT NULL,
    OperationCode   VARCHAR(20)  NOT NULL,
    OperationName   NVARCHAR(200) NOT NULL,
    CostCenterId    INT          REFERENCES CostCenters(CostCenterId),
    SetupHours      DECIMAL(8,4) NOT NULL DEFAULT 0,
    RunHoursPerUnit DECIMAL(8,4) NOT NULL,
    PlannedHours    DECIMAL(10,4),
    ActualHours     DECIMAL(10,4),
    LaborRate       DECIMAL(10,4),
    MachineRate     DECIMAL(10,4),
    OpStatus        VARCHAR(20)  NOT NULL DEFAULT 'PENDING',  -- PENDING|ACTIVE|COMPLETED
    CONSTRAINT UQ_WOOp UNIQUE (WOId, OperationSeq)
);

CREATE INDEX IX_WOOp_WO ON WorkOrderOperations(WOId);

-- ============================================================
-- GL TRANSACTIONS
-- ============================================================
CREATE TABLE GLTransactions (
    TxId            BIGINT IDENTITY(1,1) PRIMARY KEY,
    TxDate          DATE         NOT NULL,
    PostedAt        DATETIME2    NOT NULL DEFAULT GETUTCDATE(),
    Period          CHAR(7)      NOT NULL,  -- YYYY-MM
    AccountId       INT          NOT NULL REFERENCES GLAccounts(AccountId),
    CostCenterId    INT          REFERENCES CostCenters(CostCenterId),
    OrgId           INT          REFERENCES Organizations(OrgId),
    DebitAmount     DECIMAL(18,2) NOT NULL DEFAULT 0,
    CreditAmount    DECIMAL(18,2) NOT NULL DEFAULT 0,
    Currency        CHAR(3)      NOT NULL DEFAULT 'USD',
    ExchangeRate    DECIMAL(14,6) NOT NULL DEFAULT 1.000000,
    Reference       VARCHAR(50),           -- PO/SO/WO number
    Description     NVARCHAR(300) NOT NULL,
    JournalBatch    VARCHAR(30),
    IsReversed      BIT          NOT NULL DEFAULT 0,
    PostedByEmployeeId INT       REFERENCES Employees(EmployeeId),
    CreatedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE()
);

CREATE INDEX IX_GLTx_Date    ON GLTransactions(TxDate);
CREATE INDEX IX_GLTx_Account ON GLTransactions(AccountId);
CREATE INDEX IX_GLTx_Period  ON GLTransactions(Period);
CREATE INDEX IX_GLTx_CostCenter ON GLTransactions(CostCenterId);

-- ============================================================
-- CHANGE LOG (audit / CDC simulation)
-- ============================================================
CREATE TABLE ChangeLog (
    ChangeId        BIGINT IDENTITY(1,1) PRIMARY KEY,
    TableName       VARCHAR(100) NOT NULL,
    RecordId        BIGINT       NOT NULL,
    ChangeType      CHAR(1)      NOT NULL,  -- I=insert, U=update, D=delete
    ChangedAt       DATETIME2    NOT NULL DEFAULT GETUTCDATE(),
    ChangedByUserId VARCHAR(100),
    OldValues       NVARCHAR(MAX),          -- JSON
    NewValues       NVARCHAR(MAX),          -- JSON
    ChangeSource    VARCHAR(50)
);

CREATE INDEX IX_ChangeLog_Table   ON ChangeLog(TableName, RecordId);
CREATE INDEX IX_ChangeLog_Changed ON ChangeLog(ChangedAt);
"""


# ── seed functions ────────────────────────────────────────────────────────────

def seed_orgs(cur):
    orgs = [
        ("ACME-HQ",  "ACME Industrial Corp — HQ",    "COMPANY",  None,  "82-1234567", "2001-03-15"),
        ("ACME-NA",  "ACME North America Division",   "DIVISION", 1,     None,         "2001-03-15"),
        ("ACME-EU",  "ACME Europe Division",          "DIVISION", 1,     None,         "2008-06-01"),
        ("PLT-CHI",  "Chicago Manufacturing Plant",   "PLANT",    2,     None,         "2001-03-15"),
        ("PLT-HOU",  "Houston Assembly Facility",     "PLANT",    2,     None,         "2005-09-12"),
        ("PLT-DEN",  "Denver Distribution Center",    "PLANT",    2,     None,         "2010-04-03"),
        ("PLT-FRA",  "Frankfurt Manufacturing Plant", "PLANT",    3,     None,         "2008-06-01"),
        ("WH-CHI-1", "Chicago Main Warehouse",        "WAREHOUSE",4,     None,         "2001-03-15"),
        ("WH-CHI-2", "Chicago Overflow Warehouse",    "WAREHOUSE",4,     None,         "2015-01-10"),
        ("WH-HOU-1", "Houston Distribution Warehouse","WAREHOUSE",5,     None,         "2005-09-12"),
        ("WH-DEN-1", "Denver 3PL Warehouse",          "WAREHOUSE",6,     None,         "2010-04-03"),
    ]
    cur.executemany(
        """INSERT INTO Organizations (OrgCode,OrgName,OrgType,ParentOrgId,TaxId,IncorporatedDate)
           VALUES (%s,%s,%s,%s,%s,%s)""", orgs)

def seed_gl_accounts(cur):
    rows = [(a[1], a[0], a[2]) for a in GL_ACCOUNTS]
    cur.executemany(
        "INSERT INTO GLAccounts (AccountName,AccountNumber,AccountType) VALUES (%s,%s,%s)", rows)

def seed_cost_centers(cur):
    rows = []
    for cc in COST_CENTERS:
        budget = round(random.uniform(200_000, 5_000_000), 2)
        rows.append((cc[0], cc[1], cc[2], 4, budget))  # OrgId=4 (Chicago plant)
    cur.executemany(
        "INSERT INTO CostCenters (CostCenterCode,CostCenterName,Department,OrgId,BudgetAmount) VALUES (%s,%s,%s,%s,%s)",
        rows)

def seed_employees(cur, count=500):
    rows = []
    # first 10 are managers (no manager themselves)
    for i in range(1, count + 1):
        fn, ln = rnd_name()
        hire = rnd_date(2005, 2024)
        dept = random.choice(DEPARTMENTS)
        title = random.choice(JOB_TITLES)
        mgr = None if i <= 10 else random.randint(1, max(1, i - 1))
        cc = random.randint(1, len(COST_CENTERS))
        org = random.choice([4, 5, 6, 7])  # plants / divisions
        salary = round(random.uniform(45_000, 210_000), 2)
        # use employee index to guarantee uniqueness
        email = f"{fn.lower()}.{ln.lower()}{i}@acmecorp.com"
        phone = rnd_phone()
        code = f"EMP{i:05d}"
        # SSN hash — store as binary sha256-like placeholder
        ssn_hash = bytes([random.randint(0, 255) for _ in range(32)])
        rows.append((code, fn, ln, email, phone, hire.date(), dept, title,
                     mgr, cc, org, salary, 'USD', 'ACTIVE', ssn_hash))
    cur.executemany(
        """INSERT INTO Employees
           (EmployeeCode,FirstName,LastName,Email,Phone,HireDate,Department,JobTitle,
            ManagerId,CostCenterId,OrgId,BaseSalary,Currency,EmployeeStatus,SSNHash)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows)

def seed_product_categories(cur):
    parent_rows = [(pl[0], pl[1], None) for pl in PRODUCT_LINES]
    cur.executemany(
        "INSERT INTO ProductCategories (CategoryCode,CategoryName,ParentCategoryId) VALUES (%s,%s,%s)",
        parent_rows)
    # sub-categories
    sub_rows = []
    for i, pl in enumerate(PRODUCT_LINES):
        parent_id = i + 1
        for j in range(3):
            code = f"{pl[0]}-{j+1:02d}"
            name = f"{pl[1]} — Sub {j+1}"
            sub_rows.append((code, name, parent_id))
    cur.executemany(
        "INSERT INTO ProductCategories (CategoryCode,CategoryName,ParentCategoryId) VALUES (%s,%s,%s)",
        sub_rows)

def seed_products(cur, count=800):
    rows = []
    for i in range(1, count + 1):
        pl_idx = (i - 1) % len(PRODUCT_LINES)
        pl = PRODUCT_LINES[pl_idx]
        cat_id = random.randint(pl_idx * 4 + 1, pl_idx * 4 + 4)  # parent + 3 subs
        noun = random.choice(PRODUCT_NOUNS[pl[0]])
        adj  = random.choice(PRODUCT_ADJECTIVES)
        name = f"{adj} {noun} {i:04d}"
        code = f"{pl[0]}-{i:05d}"
        uom  = random.choice(UNITS_OF_MEASURE[:6])
        std_cost = round(random.uniform(1.50, 4_500.00), 4)
        list_price = round(std_cost * random.uniform(1.15, 2.80), 4)
        weight = round(random.uniform(0.05, 500.0), 4)
        lead   = random.choice([7, 14, 21, 28, 42, 56])
        moq    = random.choice([1, 5, 10, 25, 50, 100])
        rop    = round(moq * random.uniform(1.5, 5), 1)
        ss     = round(moq * random.uniform(0.5, 2), 1)
        is_mfg = 1 if pl[0] not in ("RAW","PACK") else 0
        drawing = f"DWG-{pl[0]}-{i:05d}" if is_mfg else None
        rev    = random.choice(["A","B","C","D","E","F"])
        rows.append((code, name, cat_id, uom, std_cost, list_price, weight, "KG",
                     lead, moq, rop, ss, 1, 1, is_mfg, 1, drawing, rev))
    cur.executemany(
        """INSERT INTO Products
           (ProductCode,ProductName,CategoryId,UOM,StandardCost,ListPrice,
            Weight,WeightUOM,LeadTimeDays,MinOrderQty,ReorderPoint,SafetyStock,
            IsActive,IsPurchased,IsManufactured,IsSold,DrawingNumber,Revision)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows)

def seed_bom(cur, product_count=800):
    rows = []
    # Only manufactured products get BOMs
    mfg_ids = list(range(1, product_count + 1))
    raw_ids  = list(range(700, product_count + 1))  # "raw" products as components
    effective = datetime(2020, 1, 1).date()
    for parent_id in range(1, 400):  # 400 assemblies with BOMs
        n_components = random.randint(2, 12)
        children = random.sample([x for x in mfg_ids if x != parent_id], n_components)
        for child_id in children:
            qty   = round(random.choice([1, 1, 1, 2, 4, 8, 1.5, 0.5, 10]) * random.uniform(0.8, 1.2), 4)
            uom   = random.choice(["EA","KG","M","L","PC"])
            level = random.randint(1, 4)
            scrap = round(random.uniform(0, 0.05), 4)
            rows.append((parent_id, child_id, qty, uom, level, 0, scrap, effective))
    cur.executemany(
        """INSERT INTO BillOfMaterials
           (ParentProductId,ChildProductId,Quantity,UOM,BOMLevel,IsPhantom,ScrapPercent,EffectiveFrom)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows)

def seed_warehouses(cur):
    wh_data = [
        ("WH-001","Chicago Main Warehouse",       4,  "2700 S Racine Ave","Chicago","IL","60608","US"),
        ("WH-002","Chicago Overflow",             4,  "3400 W 47th St",   "Chicago","IL","60632","US"),
        ("WH-003","Houston Distribution",         5,  "4800 Navigation Blvd","Houston","TX","77011","US"),
        ("WH-004","Denver 3PL",                   6,  "6500 E 56th Ave",  "Denver", "CO","80022","US"),
        ("WH-005","Frankfurt Plant Stores",       7,  "Hanauer Landstraße 291","Frankfurt","HE","60314","DE"),
        ("WH-006","Dallas Regional DC",           2,  "9200 LBJ Fwy",     "Dallas", "TX","75243","US"),
    ]
    cur.executemany(
        """INSERT INTO Warehouses (WarehouseCode,WarehouseName,OrgId,AddressLine1,City,State,PostalCode,Country)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", wh_data)

def seed_storage_locations(cur, warehouses=6, locs_per_wh=60):
    rows = []
    for wh_id in range(1, warehouses + 1):
        aisles = ["A","B","C","D","E"]
        bays   = [f"{i:02d}" for i in range(1, 25)]
        levels = ["01","02","03","04","05"]
        seen_codes = set()
        count = 0
        for aisle in aisles:
            for bay in bays:
                for lvl in levels:
                    for bn_num in range(1, 9):
                        if count >= locs_per_wh:
                            break
                        bn   = f"{bn_num:02d}"
                        code = f"{aisle}-{bay}-{lvl}-{bn}"
                        if code in seen_codes:
                            continue
                        seen_codes.add(code)
                        max_wt = round(random.uniform(500, 5000), 2)
                        rows.append((wh_id, code, aisle, bay, lvl, bn, max_wt))
                        count += 1
                    if count >= locs_per_wh:
                        break
                if count >= locs_per_wh:
                    break
            if count >= locs_per_wh:
                break
    cur.executemany(
        """INSERT INTO StorageLocations (WarehouseId,LocationCode,Aisle,Bay,Level,Bin,MaxWeight)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        rows)

def seed_inventory(cur, product_count=800, location_count=360, rows_target=5000):
    rows = []
    seen = set()
    valuation_methods = ["AVG","AVG","AVG","FIFO","STD"]
    for _ in range(rows_target):
        prod_id = random.randint(1, product_count)
        loc_id  = random.randint(1, location_count)
        lot     = f"LOT-{random.randint(10000,99999)}"
        key     = (prod_id, loc_id, lot)
        if key in seen:
            continue
        seen.add(key)
        qty    = round(random.uniform(0, 5000), 4)
        alloc  = round(min(qty * random.uniform(0, 0.5), qty), 4)
        cost   = round(random.uniform(1.0, 3000.0), 4)
        vm     = random.choice(valuation_methods)
        cnt_dt = rnd_date(2023, 2025).date()
        exp_dt = rnd_future(datetime(2025,1,1), 365, 365).date() if random.random() < 0.3 else None
        rows.append((prod_id, loc_id, lot, qty, alloc, cost, vm, cnt_dt, exp_dt))
    cur.executemany(
        """INSERT INTO Inventory
           (ProductId,LocationId,LotNumber,QuantityOnHand,QuantityAllocated,
            UnitCost,ValuationMethod,LastCountDate,ExpirationDate)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows)

def seed_customers(cur, count=300):
    rows = []
    types  = ["COMMERCIAL","COMMERCIAL","COMMERCIAL","DISTRIBUTOR","OEM","GOVERNMENT"]
    terms  = PAYMENT_TERMS
    industries = ["MFG","CONST","ENERGY","AUTO","AERO","FOOD","PHARMA","GOVT","UTIL","TECH"]
    for i in range(1, count + 1):
        code   = f"CUST-{i:05d}"
        fn, ln = rnd_name()
        name   = f"{ln} {random.choice(['Industries','Manufacturing','Corp','LLC','Inc','Group','Solutions'])} {i}"
        ctype  = random.choice(types)
        ind    = random.choice(industries)
        addr   = rnd_address()
        ship   = rnd_address()
        phone  = rnd_phone()
        email  = rnd_email(fn, ln, "client.com")
        credit = round(random.uniform(10_000, 500_000), 2)
        pt     = random.choice(terms)
        since  = rnd_date(2010, 2024).date()
        rows.append((code, name, ctype, ind, addr[0], addr[1], addr[2], addr[3], addr[4],
                     ship[0], ship[1], ship[2], ship[3], ship[4],
                     phone, email, credit, pt, since))
    cur.executemany(
        """INSERT INTO Customers
           (CustomerCode,CustomerName,CustomerType,IndustryCode,
            BillingAddress,BillingCity,BillingState,BillingPostal,BillingCountry,
            ShipAddress,ShipCity,ShipState,ShipPostal,ShipCountry,
            Phone,Email,CreditLimit,PaymentTerms,CustomerSince)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows)

def seed_vendors(cur, count=150):
    rows = []
    types = ["SUPPLIER","SUPPLIER","SUPPLIER","CONTRACTOR","SERVICE"]
    for i in range(1, count + 1):
        code  = f"VND-{i:04d}"
        fn, ln = rnd_name()
        name  = f"{ln} {random.choice(['Supply','Components','Materials','Industrial','Tech','Logistics'])} {i}"
        vtype = random.choice(types)
        addr  = rnd_address()
        phone = rnd_phone()
        email = rnd_email(fn, ln, "vendor.com")
        pt    = random.choice(PAYMENT_TERMS)
        lead  = random.choice([7, 10, 14, 21, 28, 45, 60])
        rows.append((code, name, vtype, addr[0], addr[1], addr[2], addr[3], addr[4],
                     phone, email, pt, lead, "APPROVED"))
    cur.executemany(
        """INSERT INTO Vendors
           (VendorCode,VendorName,VendorType,BillingAddress,BillingCity,BillingState,
            BillingPostal,BillingCountry,Phone,Email,PaymentTerms,LeadTimeDays,QualificationStatus)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows)

def seed_purchase_orders(cur, count=1200):
    rows = []
    statuses = ["OPEN","OPEN","PARTIAL","RECEIVED","INVOICED","CLOSED","CLOSED","CANCELLED"]
    for i in range(1, count + 1):
        po_num  = f"PO-{2020 + i // 400}-{i:06d}"
        vnd     = random.randint(1, 150)
        org     = random.choice([4, 5, 6])
        po_date = rnd_date(2020, 2025).date()
        req_dt  = rnd_future(datetime.combine(po_date, datetime.min.time()), 21, 14).date()
        wh      = random.randint(1, 6)
        buyer   = random.randint(1, 500)
        status  = random.choice(statuses)
        pt      = random.choice(PAYMENT_TERMS)
        ship    = random.choice(SHIP_METHODS)
        total   = round(random.uniform(500, 250_000), 2)
        tax     = round(total * random.uniform(0, 0.08), 2)
        freight = round(random.uniform(0, 2500), 2)
        rows.append((po_num, vnd, org, po_date, req_dt, wh, buyer,
                     status, pt, ship, total, tax, freight))
    cur.executemany(
        """INSERT INTO PurchaseOrders
           (PONumber,VendorId,OrgId,PODate,RequiredDate,ShipToWarehouseId,BuyerId,
            POStatus,PaymentTerms,ShipMethod,TotalAmount,TaxAmount,FreightAmount)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows)

def seed_po_lines(cur, po_count=1200, product_count=800):
    rows = []
    statuses = ["OPEN","PARTIAL","RECEIVED","INVOICED","CLOSED"]
    for po_id in range(1, po_count + 1):
        n_lines = random.randint(1, 10)
        for ln in range(1, n_lines + 1):
            prod = random.randint(1, product_count)
            desc = f"PO line {ln} product {prod}"
            qty  = round(random.uniform(1, 500), 3)
            rqty = round(qty * random.uniform(0, 1), 3) if random.random() < 0.6 else 0
            iqty = round(min(rqty, qty), 3)
            uom  = random.choice(["EA","KG","PC","SET"])
            cost = round(random.uniform(1, 2000), 4)
            prm  = rnd_date(2020, 2025).date()
            st   = random.choice(statuses)
            cc   = random.randint(1, len(COST_CENTERS))
            rows.append((po_id, ln, prod, desc, qty, rqty, iqty, uom, cost, prm, st, cc))
    cur.executemany(
        """INSERT INTO PurchaseOrderLines
           (POId,LineNumber,ProductId,Description,OrderedQty,ReceivedQty,InvoicedQty,
            UOM,UnitCost,PromisedDate,LineStatus,CostCenterId)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows)

def seed_sales_orders(cur, count=2000):
    rows = []
    statuses = ["OPEN","OPEN","PARTIAL","SHIPPED","INVOICED","CLOSED","CLOSED","CANCELLED"]
    for i in range(1, count + 1):
        so_num  = f"SO-{2020 + i // 500}-{i:07d}"
        cust    = random.randint(1, 300)
        org     = random.choice([2, 4, 5])
        o_date  = rnd_date(2020, 2025).date()
        req_dt  = rnd_future(datetime.combine(o_date, datetime.min.time()), 14, 21).date()
        prm_dt  = rnd_future(datetime.combine(o_date, datetime.min.time()), 21, 14).date()
        shp_dt  = prm_dt if random.random() < 0.7 else None
        rep     = random.randint(1, 500)
        status  = random.choice(statuses)
        pt      = random.choice(PAYMENT_TERMS)
        ship_m  = random.choice(SHIP_METHODS)
        addr    = rnd_address()
        sub     = round(random.uniform(1_000, 500_000), 2)
        disc    = round(sub * random.uniform(0, 0.15), 2)
        tax     = round((sub - disc) * random.uniform(0, 0.09), 2)
        freight = round(random.uniform(0, 3000), 2)
        total   = round(sub - disc + tax + freight, 2)
        po_ref  = f"CUST-PO-{random.randint(10000,99999)}" if random.random() < 0.8 else None
        rows.append((so_num, cust, org, o_date, req_dt, prm_dt, shp_dt, rep,
                     status, pt, ship_m,
                     addr[0], addr[1], addr[2], addr[3], addr[4],
                     sub, disc, tax, freight, total, po_ref))
    cur.executemany(
        """INSERT INTO SalesOrders
           (SONumber,CustomerId,OrgId,OrderDate,RequestedDate,PromisedDate,ShipDate,SalesRepId,
            SOStatus,PaymentTerms,ShipMethod,
            ShipToAddress,ShipToCity,ShipToState,ShipToPostal,ShipToCountry,
            SubTotal,DiscountAmount,TaxAmount,FreightAmount,TotalAmount,POReference)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows)

def seed_so_lines(cur, so_count=2000, product_count=800):
    rows = []
    statuses = ["OPEN","PARTIAL","SHIPPED","INVOICED","CLOSED"]
    for so_id in range(1, so_count + 1):
        n_lines = random.randint(1, 8)
        for ln in range(1, n_lines + 1):
            prod  = random.randint(1, product_count)
            qty   = round(random.uniform(1, 200), 3)
            shpd  = round(qty * random.uniform(0, 1), 3) if random.random() < 0.7 else 0
            invd  = round(min(shpd, qty), 3)
            uom   = "EA"
            price = round(random.uniform(5, 5000), 4)
            disc  = round(random.uniform(0, 0.20), 4)
            wh    = random.randint(1, 6)
            st    = random.choice(statuses)
            rows.append((so_id, ln, prod, qty, shpd, invd, uom, price, disc, wh, st))
    cur.executemany(
        """INSERT INTO SalesOrderLines
           (SOId,LineNumber,ProductId,OrderedQty,ShippedQty,InvoicedQty,
            UOM,UnitPrice,DiscountPct,WarehouseId,LineStatus)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows)

def seed_work_orders(cur, count=1500):
    rows = []
    statuses = ["PLANNED","PLANNED","RELEASED","IN_PROGRESS","COMPLETED","COMPLETED","CLOSED","CANCELLED"]
    for i in range(1, count + 1):
        wo_num  = f"WO-{i:07d}"
        prod    = random.randint(1, 400)  # manufactured products
        wh      = random.randint(1, 6)
        planned_qty = round(random.uniform(10, 2000), 3)
        comp_qty    = round(planned_qty * random.uniform(0, 1), 3) if random.random() < 0.6 else 0
        scrap_qty   = round(comp_qty * random.uniform(0, 0.03), 3)
        status  = random.choice(statuses)
        priority= random.randint(1, 10)
        psd     = rnd_date(2022, 2025).date()
        ped     = rnd_future(datetime.combine(psd, datetime.min.time()), 5, 20).date()
        asd     = psd if status not in ("PLANNED","CANCELLED") else None
        aed     = ped if status in ("COMPLETED","CLOSED") else None
        planner = random.randint(1, 500)
        lot     = f"WO-LOT-{i:06d}"
        rows.append((wo_num, prod, wh, planned_qty, comp_qty, scrap_qty, status,
                     priority, psd, ped, asd, aed, planner, lot))
    cur.executemany(
        """INSERT INTO WorkOrders
           (WONumber,ProductId,WarehouseId,PlannedQty,CompletedQty,ScrapQty,WOStatus,
            Priority,PlannedStartDate,PlannedEndDate,ActualStartDate,ActualEndDate,
            PlannerEmployeeId,LotNumber)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows)

def seed_wo_operations(cur, wo_count=1500):
    op_templates = [
        ("OP-010","Material Issue",        1, 0.5,  0.02),
        ("OP-020","CNC Machining",         2, 2.0,  0.25),
        ("OP-030","Welding",               2, 1.5,  0.30),
        ("OP-040","Assembly",              1, 0.0,  0.15),
        ("OP-050","Hydraulic Test",        3, 1.0,  0.10),
        ("OP-060","Quality Inspection",    3, 0.5,  0.05),
        ("OP-070","Surface Treatment",     2, 2.0,  0.12),
        ("OP-080","Final Assembly",        1, 0.5,  0.20),
        ("OP-090","Functional Test",       3, 0.5,  0.08),
        ("OP-100","Packing & Shipping",    4, 0.5,  0.05),
    ]
    rows = []
    statuses = ["PENDING","ACTIVE","COMPLETED"]
    for wo_id in range(1, wo_count + 1):
        n_ops = random.randint(3, 7)
        ops   = sorted(random.sample(op_templates, n_ops), key=lambda x: x[0])
        for seq, op in enumerate(ops, start=10):
            setup_h   = round(op[3] * random.uniform(0.8, 1.2), 4)
            run_h     = round(op[4] * random.uniform(0.7, 1.5), 4)
            plan_h    = round(setup_h + run_h * random.uniform(50, 500), 4)
            act_h     = round(plan_h * random.uniform(0.9, 1.3), 4) if random.random() < 0.6 else None
            labor_r   = round(random.uniform(25, 95), 4)
            machine_r = round(random.uniform(10, 200), 4)
            st        = random.choice(statuses)
            cc        = random.randint(1, len(COST_CENTERS))
            rows.append((wo_id, seq, op[0], op[1], cc, setup_h, run_h, plan_h, act_h, labor_r, machine_r, st))
    cur.executemany(
        """INSERT INTO WorkOrderOperations
           (WOId,OperationSeq,OperationCode,OperationName,CostCenterId,
            SetupHours,RunHoursPerUnit,PlannedHours,ActualHours,LaborRate,MachineRate,OpStatus)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows)

def seed_gl_transactions(cur, count=30000):
    rows = []
    journals = ["AP_ACCRUAL","AR_INVOICE","PAYROLL","INVENTORY_ADJ","DEPRECIATION",
                "REVENUE_REC","COST_XFER","MANUAL_JE","PERIOD_CLOSE","CONSOLIDATION"]
    for i in range(1, count + 1):
        tx_date = rnd_date(2022, 2025)
        period  = tx_date.strftime("%Y-%m")
        acct_id = random.randint(1, len(GL_ACCOUNTS))
        cc_id   = random.randint(1, len(COST_CENTERS))
        org_id  = random.choice([1, 2, 4, 5, 6])
        amt     = round(random.uniform(100, 500_000), 2)
        is_debit= random.random() < 0.5
        debit   = amt if is_debit else 0
        credit  = 0 if is_debit else amt
        ref_types = ["PO", "SO", "WO", "JE", "ADJ"]
        ref_type  = random.choice(ref_types)
        ref_num   = f"{ref_type}-{random.randint(1000, 99999)}"
        desc    = f"{'Debit' if is_debit else 'Credit'} for {random.choice(['vendor invoice','customer payment','payroll','inventory adj','depreciation','expense accrual','revenue recognition'])}"
        journal = random.choice(journals)
        emp_id  = random.randint(1, 500)
        rows.append((tx_date.date(), period, acct_id, cc_id, org_id, debit, credit,
                     'USD', 1.0, ref_num, desc, journal, 0, emp_id))
    # batch insert
    batch = 1000
    for start in range(0, len(rows), batch):
        cur.executemany(
            """INSERT INTO GLTransactions
               (TxDate,Period,AccountId,CostCenterId,OrgId,DebitAmount,CreditAmount,
                Currency,ExchangeRate,Reference,Description,JournalBatch,IsReversed,PostedByEmployeeId)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            rows[start:start + batch])

def seed_changelog(cur, count=10000):
    tables = ["Products","Customers","Vendors","PurchaseOrders","SalesOrders",
              "WorkOrders","Inventory","Employees"]
    change_types = ["I", "U", "U", "U", "D"]
    rows = []
    for _ in range(count):
        tbl  = random.choice(tables)
        rid  = random.randint(1, 2000)
        ct   = random.choice(change_types)
        at   = rnd_date(2022, 2025)
        user = f"usr_{random.randint(1,50):03d}"
        old  = '{"status":"OPEN"}' if ct != "I" else None
        new  = '{"status":"CLOSED"}' if ct != "D" else None
        src  = random.choice(["API","ETL","TRIGGER","MANUAL","SYNC"])
        rows.append((tbl, rid, ct, at, user, old, new, src))
    cur.executemany(
        """INSERT INTO ChangeLog (TableName,RecordId,ChangeType,ChangedAt,ChangedByUserId,OldValues,NewValues,ChangeSource)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows)


# ── main ─────────────────────────────────────────────────────────────────────

def run():
    print("Connecting to SQL Server...")
    # wait for SQL Server to be fully ready
    for attempt in range(12):
        try:
            conn = pymssql.connect(server=SERVER, port=PORT, user=USER, password=PASSWORD)
            break
        except Exception as e:
            print(f"  attempt {attempt+1}: {e}")
            time.sleep(5)
    else:
        raise RuntimeError("Could not connect to SQL Server after 60s")

    print("Connected. Creating database...")
    conn.autocommit(True)
    cur = conn.cursor()
    cur.execute(f"IF DB_ID('{DB}') IS NULL CREATE DATABASE [{DB}]")
    cur.execute(f"USE [{DB}]")

    print("Creating schema (DDL)...")
    # split on GO-like boundaries and run each statement
    statements = [s.strip() for s in DDL.split(';') if s.strip()]
    for stmt in statements:
        try:
            cur.execute(stmt)
        except Exception as e:
            if "already exists" not in str(e) and "There is already" not in str(e):
                print(f"  DDL warning: {e}")

    print("Seeding Organizations...")
    seed_orgs(cur)
    print("Seeding GL Accounts...")
    seed_gl_accounts(cur)
    print("Seeding Cost Centers...")
    seed_cost_centers(cur)
    print("Seeding Employees (500)...")
    seed_employees(cur, 500)
    print("Seeding Product Categories...")
    seed_product_categories(cur)
    print("Seeding Products (800)...")
    seed_products(cur, 800)
    print("Seeding Bill of Materials...")
    seed_bom(cur, 800)
    print("Seeding Warehouses...")
    seed_warehouses(cur)
    print("Seeding Storage Locations...")
    seed_storage_locations(cur)
    print("Seeding Inventory (5,000 rows)...")
    seed_inventory(cur, 800, 360, 5000)
    print("Seeding Customers (300)...")
    seed_customers(cur, 300)
    print("Seeding Vendors (150)...")
    seed_vendors(cur, 150)
    print("Seeding Purchase Orders (1,200)...")
    seed_purchase_orders(cur, 1200)
    print("Seeding PO Lines (~6,000 rows)...")
    seed_po_lines(cur, 1200, 800)
    print("Seeding Sales Orders (2,000)...")
    seed_sales_orders(cur, 2000)
    print("Seeding SO Lines (~10,000 rows)...")
    seed_so_lines(cur, 2000, 800)
    print("Seeding Work Orders (1,500)...")
    seed_work_orders(cur, 1500)
    print("Seeding Work Order Operations (~7,500 rows)...")
    seed_wo_operations(cur, 1500)
    print("Seeding GL Transactions (30,000 rows)...")
    seed_gl_transactions(cur, 30000)
    print("Seeding Change Log (10,000 rows)...")
    seed_changelog(cur, 10000)

    # summary counts
    print("\n=== ROW COUNTS ===")
    tables = [
        "Organizations","GLAccounts","CostCenters","Employees",
        "ProductCategories","Products","BillOfMaterials",
        "Warehouses","StorageLocations","Inventory",
        "Customers","Vendors",
        "PurchaseOrders","PurchaseOrderLines",
        "SalesOrders","SalesOrderLines",
        "WorkOrders","WorkOrderOperations",
        "GLTransactions","ChangeLog"
    ]
    total = 0
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        n = cur.fetchone()[0]
        total += n
        print(f"  {t:<30} {n:>8,}")
    print(f"  {'TOTAL':<30} {total:>8,}")

    conn.commit()
    conn.close()
    print("\nDone! SQL Server is ready.")

if __name__ == "__main__":
    run()
