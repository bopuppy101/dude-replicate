#!/usr/bin/env python3
"""
Oracle REPLTEST schema seed script.
Creates 6 tables with varied Oracle types and inserts realistic data:
  - Customers   (500 rows)
  - Products    (500 rows)
  - Employees   (500 rows)
  - Orders      (1,000 rows)
  - OrderLines  (3,000 rows)
  - AuditLog    (500 rows)

Idempotent: drops and recreates tables on each run.
"""

import oracledb
import random
import os
import struct
from datetime import datetime, timedelta, timezone

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

ORACLE_USER = os.getenv('ORACLE_USER', 'repltest')
ORACLE_PASS = os.getenv('ORACLE_PASS', '')
ORACLE_DSN  = os.getenv('ORACLE_PDB_DSN', '127.0.0.1:1521/FREEPDB1')

random.seed(42)  # reproducible

BATCH_SIZE = 500

# ── helpers ───────────────────────────────────────────────────────────────────

def rnd_date(start_year=2015, end_year=2025):
    start = datetime(start_year, 1, 1)
    end   = datetime(end_year, 12, 31)
    return start + timedelta(days=random.randint(0, (end - start).days))

def rnd_ts(start_year=2020, end_year=2025):
    """Return a timezone-aware datetime for TIMESTAMP WITH TIME ZONE columns."""
    base = rnd_date(start_year, end_year)
    return base.replace(tzinfo=timezone.utc) + timedelta(
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59),
    )

def rnd_bytes(n):
    """Return n random bytes for RAW / BLOB columns."""
    return bytes([random.randint(0, 255) for _ in range(n)])

FIRST_NAMES = [
    "James","John","Robert","Michael","William","David","Richard","Joseph",
    "Thomas","Charles","Linda","Barbara","Patricia","Jennifer","Mary","Nancy",
    "Karen","Lisa","Betty","Dorothy","Sarah","Kevin","Brian","George","Edward",
    "Donna","Carol","Ruth","Sharon","Michelle","Laura","Sandra","Kimberly","Helen",
    "Deborah","Amy","Angela","Stephanie","Rebecca","Anna","Maria","Emma","Olivia",
]
LAST_NAMES = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis",
    "Rodriguez","Martinez","Hernandez","Lopez","Gonzalez","Wilson","Anderson",
    "Thomas","Taylor","Moore","Jackson","Martin","Lee","Perez","Thompson","White",
    "Harris","Sanchez","Clark","Ramirez","Lewis","Robinson","Walker","Young","Allen",
    "King","Wright","Scott","Torres","Nguyen","Hill","Flores","Green","Adams","Nelson",
]
CITIES = [
    ("Chicago","IL","60601"),("Houston","TX","77001"),("Phoenix","AZ","85001"),
    ("Philadelphia","PA","19101"),("San Antonio","TX","78201"),("Dallas","TX","75201"),
    ("San Jose","CA","95101"),("Austin","TX","73301"),("Jacksonville","FL","32099"),
    ("Columbus","OH","43085"),("Charlotte","NC","28201"),("Indianapolis","IN","46201"),
    ("Seattle","WA","98101"),("Denver","CO","80201"),("Nashville","TN","37201"),
    ("Portland","OR","97201"),("Atlanta","GA","30301"),("Las Vegas","NV","89101"),
]
STREET_NAMES = [
    "Main St","Oak Ave","Maple Dr","Cedar Ln","Elm St","Pine Rd","Lake Blvd",
    "Park Way","River Rd","Sunset Blvd","Commerce Dr","Industrial Pkwy","Tech Ct",
]
DEPARTMENTS = [
    "Engineering","Manufacturing","Quality Assurance","Supply Chain",
    "Sales","Marketing","Finance","Human Resources","Information Technology",
    "Research & Development","Operations","Legal","Customer Service","Procurement",
]
JOB_TITLES = [
    "Engineer I","Engineer II","Senior Engineer","Principal Engineer",
    "Manager","Senior Manager","Director","VP","Analyst","Senior Analyst",
    "Technician","Lead Technician","Supervisor","Coordinator","Specialist",
]
PRODUCT_CATEGORIES = [
    "Mechanical Components","Electrical Components","Hydraulic Systems",
    "Pneumatic Systems","Control Systems","Safety Equipment",
    "Tooling & Fixtures","Raw Materials","Packaging","MRO Supplies",
]
ORDER_STATUSES = ["OPEN","PROCESSING","SHIPPED","DELIVERED","CANCELLED","RETURNED"]
CHANGE_TYPES   = ["I","U","D"]
CHANGE_SOURCES = ["API","ETL","TRIGGER","MANUAL","SYNC"]
AUDIT_TABLES   = ["Customers","Products","Orders","OrderLines","Employees"]


def rnd_name():
    return random.choice(FIRST_NAMES), random.choice(LAST_NAMES)

def rnd_phone():
    return f"({random.randint(200,999)}) {random.randint(200,999)}-{random.randint(1000,9999)}"

def rnd_address():
    city, state, zipcode = random.choice(CITIES)
    street = f"{random.randint(100,9999)} {random.choice(STREET_NAMES)}"
    return street, city, state, zipcode


# ── DDL ───────────────────────────────────────────────────────────────────────

# Tables to drop in reverse FK order
DROP_ORDER = ["OrderLines", "Orders", "AuditLog", "Employees", "Products", "Customers"]

# DDL statements — executed individually
DDL = [
    """CREATE TABLE Customers (
        CustomerId      NUMBER(10)    NOT NULL,
        CustomerCode    VARCHAR2(20)  NOT NULL,
        CustomerName    VARCHAR2(200) NOT NULL,
        CustomerType    CHAR(1)       NOT NULL,
        Email           VARCHAR2(200),
        Phone           VARCHAR2(20),
        BillingAddr     VARCHAR2(200),
        BillingCity     VARCHAR2(100),
        BillingState    VARCHAR2(50),
        BillingZip      VARCHAR2(10),
        BillingCountry  VARCHAR2(50)  DEFAULT 'US',
        CreditLimit     NUMBER(15,2),
        IsActive        NUMBER(1)     DEFAULT 1,
        CustomerSince   DATE,
        CreatedAt       TIMESTAMP     DEFAULT SYSTIMESTAMP,
        UpdatedAt       TIMESTAMP     DEFAULT SYSTIMESTAMP,
        CONSTRAINT pk_customers PRIMARY KEY (CustomerId),
        CONSTRAINT uq_custcode  UNIQUE (CustomerCode)
    )""",

    """CREATE TABLE Products (
        ProductId       NUMBER(10)    NOT NULL,
        ProductCode     VARCHAR2(50)  NOT NULL,
        ProductName     VARCHAR2(200) NOT NULL,
        Category        VARCHAR2(100),
        Description     CLOB,
        UnitPrice       NUMBER(12,4),
        StdCost         NUMBER(12,4),
        Weight          FLOAT,
        PartNoRaw       RAW(16),
        IsActive        NUMBER(1)     DEFAULT 1,
        CreatedAt       TIMESTAMP     DEFAULT SYSTIMESTAMP,
        UpdatedAt       TIMESTAMP     DEFAULT SYSTIMESTAMP,
        CONSTRAINT pk_products PRIMARY KEY (ProductId),
        CONSTRAINT uq_prodcode UNIQUE (ProductCode)
    )""",

    """CREATE TABLE Employees (
        EmployeeId      NUMBER(10)    NOT NULL,
        EmployeeCode    VARCHAR2(20)  NOT NULL,
        FirstName       VARCHAR2(100) NOT NULL,
        LastName        VARCHAR2(100) NOT NULL,
        Email           VARCHAR2(200),
        Phone           VARCHAR2(20),
        Department      VARCHAR2(100),
        JobTitle        VARCHAR2(100),
        HireDate        DATE,
        Salary          NUMBER(12,2),
        ManagerId       NUMBER(10),
        IsActive        NUMBER(1)     DEFAULT 1,
        CreatedAt       TIMESTAMP     DEFAULT SYSTIMESTAMP,
        UpdatedAt       TIMESTAMP     DEFAULT SYSTIMESTAMP,
        CONSTRAINT pk_employees PRIMARY KEY (EmployeeId),
        CONSTRAINT uq_empcode   UNIQUE (EmployeeCode),
        CONSTRAINT fk_emp_mgr   FOREIGN KEY (ManagerId) REFERENCES Employees(EmployeeId)
    )""",

    """CREATE TABLE Orders (
        OrderId         NUMBER(10)    NOT NULL,
        OrderNum        VARCHAR2(30)  NOT NULL,
        CustomerId      NUMBER(10)    NOT NULL,
        OrderStatus     VARCHAR2(20)  NOT NULL,
        OrderDate       DATE          NOT NULL,
        RequiredDate    DATE,
        TotalAmount     NUMBER(15,2),
        ShippingAddr    VARCHAR2(400),
        CreatedAt       TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP,
        UpdatedAt       TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP,
        CONSTRAINT pk_orders   PRIMARY KEY (OrderId),
        CONSTRAINT uq_ordernum UNIQUE (OrderNum),
        CONSTRAINT fk_ord_cust FOREIGN KEY (CustomerId) REFERENCES Customers(CustomerId)
    )""",

    """CREATE TABLE OrderLines (
        OrderLineId     NUMBER(10)    NOT NULL,
        OrderId         NUMBER(10)    NOT NULL,
        ProductId       NUMBER(10)    NOT NULL,
        LineNumber      NUMBER(5)     NOT NULL,
        Qty             NUMBER(10,4)  NOT NULL,
        UnitPrice       NUMBER(12,4)  NOT NULL,
        DiscountPct     NUMBER(5,4)   DEFAULT 0,
        LineAmount      NUMBER(15,2),
        CONSTRAINT pk_orderlines  PRIMARY KEY (OrderLineId),
        CONSTRAINT fk_ol_order    FOREIGN KEY (OrderId)    REFERENCES Orders(OrderId),
        CONSTRAINT fk_ol_product  FOREIGN KEY (ProductId)  REFERENCES Products(ProductId)
    )""",

    """CREATE TABLE AuditLog (
        AuditId         NUMBER(10)    NOT NULL,
        TableName       VARCHAR2(100) NOT NULL,
        RecordId        NUMBER(10),
        ChangeType      CHAR(1)       NOT NULL,
        ChangedAt       TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP,
        ChangedBy       VARCHAR2(100),
        OldValues       CLOB,
        NewValues       CLOB,
        BinaryPayload   BLOB,
        RecordHash      RAW(16),
        Measurement     BINARY_FLOAT,
        Score           BINARY_DOUBLE,
        CONSTRAINT pk_auditlog PRIMARY KEY (AuditId)
    )""",
]

INDEX_DDL = [
    "CREATE INDEX ix_cust_type    ON Customers(CustomerType)",
    "CREATE INDEX ix_cust_active  ON Customers(IsActive)",
    "CREATE INDEX ix_prod_cat     ON Products(Category)",
    "CREATE INDEX ix_emp_dept     ON Employees(Department)",
    "CREATE INDEX ix_emp_mgr      ON Employees(ManagerId)",
    "CREATE INDEX ix_ord_cust     ON Orders(CustomerId)",
    "CREATE INDEX ix_ord_status   ON Orders(OrderStatus)",
    "CREATE INDEX ix_ord_date     ON Orders(OrderDate)",
    "CREATE INDEX ix_ol_order     ON OrderLines(OrderId)",
    "CREATE INDEX ix_ol_product   ON OrderLines(ProductId)",
    "CREATE INDEX ix_audit_table  ON AuditLog(TableName)",
    "CREATE INDEX ix_audit_ts     ON AuditLog(ChangedAt)",
]


# ── seed functions ─────────────────────────────────────────────────────────────

def seed_customers(cur, count=500):
    rows = []
    types = ['R', 'R', 'W', 'W', 'D']  # retail-heavy
    for i in range(1, count + 1):
        fn, ln = rnd_name()
        street, city, state, zipcode = rnd_address()
        rows.append((
            i,                                           # CustomerId
            f"CUST{i:05d}",                              # CustomerCode
            f"{fn} {ln} {random.choice(['Inc','LLC','Corp','Ltd','Co'])}",  # CustomerName
            random.choice(types),                        # CustomerType
            f"{fn.lower()}.{ln.lower()}{i}@example.com",# Email
            rnd_phone(),                                 # Phone
            street,                                      # BillingAddr
            city,                                        # BillingCity
            state,                                       # BillingState
            zipcode,                                     # BillingZip
            'US',                                        # BillingCountry
            round(random.uniform(5_000, 500_000), 2),   # CreditLimit
            1,                                           # IsActive
            rnd_date(2010, 2024),                        # CustomerSince
            rnd_date(2020, 2025),                        # CreatedAt
            rnd_date(2020, 2025),                        # UpdatedAt
        ))
    _executemany(cur,
        """INSERT INTO Customers
           (CustomerId,CustomerCode,CustomerName,CustomerType,Email,Phone,
            BillingAddr,BillingCity,BillingState,BillingZip,BillingCountry,
            CreditLimit,IsActive,CustomerSince,CreatedAt,UpdatedAt)
           VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,:13,:14,:15,:16)""",
        rows)


def seed_products(cur, count=500):
    rows = []
    adjectives = ["Heavy-Duty","Precision","High-Performance","Industrial",
                  "Standard","Enhanced","Reinforced","Lightweight","Modular","Integrated"]
    for i in range(1, count + 1):
        cat = random.choice(PRODUCT_CATEGORIES)
        adj = random.choice(adjectives)
        std_cost   = round(random.uniform(1.50, 4_500.00), 4)
        unit_price = round(std_cost * random.uniform(1.15, 2.80), 4)
        weight     = round(random.uniform(0.05, 500.0), None)
        desc       = (f"{adj} {cat} component — part {i:05d}. "
                      f"Meets ISO-{random.randint(1000,9999)} specification. "
                      f"Rated for {random.randint(1,50)} year service life.")
        rows.append((
            i,                                           # ProductId
            f"PROD{i:05d}",                              # ProductCode
            f"{adj} {cat} {i:04d}",                      # ProductName
            cat,                                         # Category
            desc,                                        # Description (CLOB)
            unit_price,                                  # UnitPrice
            std_cost,                                    # StdCost
            weight,                                      # Weight (FLOAT)
            rnd_bytes(16),                               # PartNoRaw (RAW(16))
            1,                                           # IsActive
            rnd_date(2018, 2025),                        # CreatedAt
            rnd_date(2020, 2025),                        # UpdatedAt
        ))
    _executemany(cur,
        """INSERT INTO Products
           (ProductId,ProductCode,ProductName,Category,Description,
            UnitPrice,StdCost,Weight,PartNoRaw,IsActive,CreatedAt,UpdatedAt)
           VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12)""",
        rows)


def seed_employees(cur, count=500):
    rows = []
    for i in range(1, count + 1):
        fn, ln = rnd_name()
        # first 10 have no manager (top-level)
        mgr = None if i <= 10 else random.randint(1, max(1, i - 1))
        rows.append((
            i,                                           # EmployeeId
            f"EMP{i:05d}",                               # EmployeeCode
            fn,                                          # FirstName
            ln,                                          # LastName
            f"{fn.lower()}.{ln.lower()}{i}@corp.com",   # Email
            rnd_phone(),                                 # Phone
            random.choice(DEPARTMENTS),                  # Department
            random.choice(JOB_TITLES),                   # JobTitle
            rnd_date(2000, 2024),                        # HireDate (Oracle DATE includes time)
            round(random.uniform(40_000, 220_000), 2),  # Salary
            mgr,                                         # ManagerId (self-ref FK)
            1,                                           # IsActive
            rnd_date(2020, 2025),                        # CreatedAt
            rnd_date(2020, 2025),                        # UpdatedAt
        ))
    _executemany(cur,
        """INSERT INTO Employees
           (EmployeeId,EmployeeCode,FirstName,LastName,Email,Phone,
            Department,JobTitle,HireDate,Salary,ManagerId,IsActive,CreatedAt,UpdatedAt)
           VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,:13,:14)""",
        rows)


def seed_orders(cur, count=1000, customer_count=500):
    rows = []
    for i in range(1, count + 1):
        order_date = rnd_date(2021, 2025)
        req_date   = order_date + timedelta(days=random.randint(7, 60))
        street, city, state, zipcode = rnd_address()
        rows.append((
            i,                                           # OrderId
            f"ORD{i:07d}",                               # OrderNum
            random.randint(1, customer_count),           # CustomerId
            random.choice(ORDER_STATUSES),               # OrderStatus
            order_date,                                  # OrderDate (DATE)
            req_date,                                    # RequiredDate (DATE)
            round(random.uniform(50, 250_000), 2),       # TotalAmount
            f"{street}, {city}, {state} {zipcode}",     # ShippingAddr
            rnd_ts(2021, 2025),                          # CreatedAt (TIMESTAMP WITH TIME ZONE)
            rnd_ts(2021, 2025),                          # UpdatedAt (TIMESTAMP WITH TIME ZONE)
        ))
    _executemany(cur,
        """INSERT INTO Orders
           (OrderId,OrderNum,CustomerId,OrderStatus,OrderDate,RequiredDate,
            TotalAmount,ShippingAddr,CreatedAt,UpdatedAt)
           VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10)""",
        rows)


def seed_orderlines(cur, count=3000, order_count=1000, product_count=500):
    rows = []
    # distribute ~3 lines per order, varied
    line_map = {}   # order_id -> next line number
    for i in range(1, count + 1):
        oid = ((i - 1) % order_count) + 1
        lnum = line_map.get(oid, 0) + 1
        line_map[oid] = lnum
        qty   = round(random.uniform(1, 200), 4)
        price = round(random.uniform(5, 5_000), 4)
        disc  = round(random.uniform(0, 0.25), 4)
        amt   = round(qty * price * (1 - disc), 2)
        rows.append((
            i,                                           # OrderLineId
            oid,                                         # OrderId
            random.randint(1, product_count),            # ProductId
            lnum,                                        # LineNumber
            qty,                                         # Qty (NUMBER(10,4))
            price,                                       # UnitPrice (NUMBER(12,4))
            disc,                                        # DiscountPct (NUMBER(5,4))
            amt,                                         # LineAmount
        ))
    _executemany(cur,
        """INSERT INTO OrderLines
           (OrderLineId,OrderId,ProductId,LineNumber,Qty,UnitPrice,DiscountPct,LineAmount)
           VALUES (:1,:2,:3,:4,:5,:6,:7,:8)""",
        rows)


def seed_auditlog(cur, count=500):
    rows = []
    for i in range(1, count + 1):
        tbl  = random.choice(AUDIT_TABLES)
        rid  = random.randint(1, 500)
        ct   = random.choice(CHANGE_TYPES)
        old  = '{"status":"OPEN","amount":1234.56}' if ct != 'I' else None
        new  = '{"status":"CLOSED","amount":9876.54}' if ct != 'D' else None
        rows.append((
            i,                                           # AuditId
            tbl,                                         # TableName
            rid,                                         # RecordId
            ct,                                          # ChangeType (CHAR(1))
            rnd_ts(2020, 2025),                          # ChangedAt (TIMESTAMP WITH TIME ZONE)
            random.choice(FIRST_NAMES),                  # ChangedBy
            old,                                         # OldValues (CLOB)
            new,                                         # NewValues (CLOB)
            rnd_bytes(random.randint(32, 256)),          # BinaryPayload (BLOB)
            rnd_bytes(16),                               # RecordHash (RAW(16))
            random.uniform(0.0, 1.0),                   # Measurement (BINARY_FLOAT)
            random.uniform(0.0, 100.0),                 # Score (BINARY_DOUBLE)
        ))
    _executemany(cur,
        """INSERT INTO AuditLog
           (AuditId,TableName,RecordId,ChangeType,ChangedAt,ChangedBy,
            OldValues,NewValues,BinaryPayload,RecordHash,Measurement,Score)
           VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12)""",
        rows)


def _executemany(cur, sql, rows):
    """Insert rows in batches."""
    for start in range(0, len(rows), BATCH_SIZE):
        cur.executemany(sql, rows[start:start + BATCH_SIZE])


# ── main ──────────────────────────────────────────────────────────────────────

def run():
    print(f"Connecting to Oracle at {ORACLE_DSN} as {ORACLE_USER}...")
    conn = oracledb.connect(user=ORACLE_USER, password=ORACLE_PASS, dsn=ORACLE_DSN)
    cur  = conn.cursor()

    print("Dropping existing tables (idempotent)...")
    for tbl in DROP_ORDER:
        try:
            cur.execute(f"DROP TABLE {tbl} CASCADE CONSTRAINTS")
            print(f"  dropped {tbl}")
        except oracledb.DatabaseError:
            pass  # table did not exist

    print("Creating tables...")
    for stmt in DDL:
        cur.execute(stmt)

    print("Creating indexes...")
    for stmt in INDEX_DDL:
        try:
            cur.execute(stmt)
        except oracledb.DatabaseError as e:
            print(f"  index warning: {e}")

    print("Seeding Customers (500)...")
    seed_customers(cur, 500)
    conn.commit()

    print("Seeding Products (500)...")
    seed_products(cur, 500)
    conn.commit()

    print("Seeding Employees (500)...")
    seed_employees(cur, 500)
    conn.commit()

    print("Seeding Orders (1,000)...")
    seed_orders(cur, 1000, customer_count=500)
    conn.commit()

    print("Seeding OrderLines (3,000)...")
    seed_orderlines(cur, 3000, order_count=1000, product_count=500)
    conn.commit()

    print("Seeding AuditLog (500)...")
    seed_auditlog(cur, 500)
    conn.commit()

    # verify
    print("\nRow counts:")
    totals = 0
    for tbl in ["Customers", "Products", "Employees", "Orders", "OrderLines", "AuditLog"]:
        cur.execute(f"SELECT COUNT(*) FROM {tbl}")
        n = cur.fetchone()[0]
        print(f"  {tbl:<15} {n:>5}")
        totals += n
    print(f"  {'TOTAL':<15} {totals:>5}")

    cur.close()
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    run()
