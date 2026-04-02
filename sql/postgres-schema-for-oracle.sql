-- ================================================================
-- Postgres tables for Oracle replication target
-- Source: Oracle 23ai Free, REPLTEST schema
-- Target: PostgreSQL enterprise_dw database, oracle_dw schema
--
-- Oracle → PostgreSQL type mappings:
--   NUMBER(p,0)          → BIGINT (PKs, FKs)
--   NUMBER(p,s)          → NUMERIC(p,s)
--   VARCHAR2(n)          → VARCHAR(n)
--   CHAR(n)              → CHAR(n)
--   CLOB                 → TEXT
--   BLOB / RAW           → BYTEA
--   DATE                 → TIMESTAMP (Oracle DATE includes time)
--   TIMESTAMP WITH TZ    → TIMESTAMPTZ
--   FLOAT / BINARY_DOUBLE→ DOUBLE PRECISION
--   BINARY_FLOAT         → REAL
--
-- Tables in FK dependency order
-- ================================================================

CREATE SCHEMA IF NOT EXISTS oracle_dw;

-- ============================================================
-- Table: CUSTOMERS
-- ============================================================
CREATE TABLE oracle_dw."CUSTOMERS" (
    "CUSTOMERID" BIGINT NOT NULL,
    "CUSTOMERCODE" VARCHAR(20) NOT NULL,
    "CUSTOMERNAME" VARCHAR(200) NOT NULL,
    "CUSTOMERTYPE" CHAR(1),
    "EMAIL" VARCHAR(200),
    "PHONE" VARCHAR(30),
    "BILLINGADDR" VARCHAR(500),
    "BILLINGCITY" VARCHAR(100),
    "BILLINGSTATE" VARCHAR(50),
    "BILLINGZIP" VARCHAR(10),
    "BILLINGCOUNTRY" CHAR(2),
    "CREDITLIMIT" NUMERIC(15,2),
    "ISACTIVE" INTEGER,
    "CUSTOMERSINCE" TIMESTAMP,
    "CREATEDAT" TIMESTAMP,
    "UPDATEDAT" TIMESTAMP,
    PRIMARY KEY ("CUSTOMERID")
);

-- ============================================================
-- Table: PRODUCTS
-- ============================================================
CREATE TABLE oracle_dw."PRODUCTS" (
    "PRODUCTID" BIGINT NOT NULL,
    "PRODUCTCODE" VARCHAR(30) NOT NULL,
    "PRODUCTNAME" VARCHAR(200) NOT NULL,
    "CATEGORYCODE" VARCHAR(20),
    "UOM" VARCHAR(10),
    "LISTPRICE" NUMERIC(12,4),
    "STANDARDCOST" NUMERIC(12,4),
    "WEIGHT" DOUBLE PRECISION,
    "ISACTIVE" INTEGER,
    "DESCRIPTION" TEXT,
    "PRODUCTGUID" BYTEA,
    "CREATEDAT" TIMESTAMP,
    PRIMARY KEY ("PRODUCTID")
);

-- ============================================================
-- Table: EMPLOYEES
-- ============================================================
CREATE TABLE oracle_dw."EMPLOYEES" (
    "EMPID" BIGINT NOT NULL,
    "EMPCODE" VARCHAR(20) NOT NULL,
    "FIRSTNAME" VARCHAR(100) NOT NULL,
    "LASTNAME" VARCHAR(100) NOT NULL,
    "DEPARTMENT" VARCHAR(50),
    "TITLE" VARCHAR(100),
    "SALARY" NUMERIC(12,2),
    "HIREDATE" TIMESTAMP,
    "BIRTHDATE" TIMESTAMP,
    "MANAGERID" BIGINT,
    "ISACTIVE" INTEGER,
    "CREATEDAT" TIMESTAMP,
    PRIMARY KEY ("EMPID")
);

-- ============================================================
-- Table: ORDERS (depends on CUSTOMERS)
-- ============================================================
CREATE TABLE oracle_dw."ORDERS" (
    "ORDERID" BIGINT NOT NULL,
    "CUSTOMERID" BIGINT NOT NULL,
    "ORDERDATE" TIMESTAMPTZ,
    "STATUS" VARCHAR(20),
    "TOTALAMOUNT" NUMERIC(15,2),
    "SHIPADDR" VARCHAR(500),
    "SHIPCITY" VARCHAR(100),
    "SHIPSTATE" VARCHAR(50),
    "SHIPZIP" VARCHAR(10),
    "NOTES" VARCHAR(1000),
    "CREATEDAT" TIMESTAMP,
    PRIMARY KEY ("ORDERID")
);

-- ============================================================
-- Table: ORDERLINES (depends on ORDERS, PRODUCTS)
-- ============================================================
CREATE TABLE oracle_dw."ORDERLINES" (
    "LINEID" BIGINT NOT NULL,
    "ORDERID" BIGINT NOT NULL,
    "PRODUCTID" BIGINT NOT NULL,
    "QUANTITY" NUMERIC(10,4),
    "UNITPRICE" NUMERIC(12,4),
    "DISCOUNT" NUMERIC(5,2),
    "LINEAMOUNT" NUMERIC(15,2),
    PRIMARY KEY ("LINEID")
);

-- ============================================================
-- Table: AUDITLOG
-- ============================================================
CREATE TABLE oracle_dw."AUDITLOG" (
    "LOGID" BIGINT NOT NULL,
    "TABLENAME" VARCHAR(50) NOT NULL,
    "RECORDID" BIGINT,
    "OPERATION" CHAR(1),
    "OLDVALUES" TEXT,
    "NEWVALUES" TEXT,
    "BINARYDATA" BYTEA,
    "TRACEID" BYTEA,
    "SCORE" REAL,
    "PRECISION" DOUBLE PRECISION,
    "LOGGEDAT" TIMESTAMPTZ,
    "LOGGEDBY" VARCHAR(100),
    PRIMARY KEY ("LOGID")
);
