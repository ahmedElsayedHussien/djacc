# Django Accounting System (DJACC) 🚀

A professional-grade ERP and Accounting system built with Django, focusing on robust double-entry bookkeeping, hierarchical Chart of Accounts, and automated financial workflows.

---

## 🏗️ Project Architecture

The project follows a **Service Layer Architecture** to ensure data integrity and clean separation of concerns. All financial operations (Journal Entries, Entity Creation) are handled through dedicated Service classes rather than directly in Views or Models.

### Core Technologies
- **Backend**: Python / Django
- **Database**: SQLite (Development) / PostgreSQL (Production ready)
- **Background Tasks**: Celery (for reports and heavy processing)
- **Frontend**: Django Templates + Bootstrap 5

---

## 📂 App Structure

The system is modular, with each app handling a specific domain:

### 🛠️ `core`
The heart of the system.
- **Models**: `Account` (COA), `JournalEntry`, `JournalLine`, `FiscalYear`, `CostCenter`, `TaxType`.
- **Services**: `JournalService` (Handles all double-entry logic), `AccountService`, `AuditService`.
- **Key Feature**: Automatic balancing validation for all journal entries.

### 💰 `sales`
- **Models**: `Customer`, `SalesInvoice`, `SalesRepresentative`, `CustomerReceipt`, `SalesReturn`.
- **Logic**: Automated revenue recognition and receivable tracking. Linking customers to the COA.

### 🛒 `purchases`
- **Models**: `Supplier`, `PurchaseInvoice`, `SupplierPayment`.
- **Logic**: Automated expense/asset recognition and payable tracking.

### 📦 `inventory`
- **Models**: `Item`, `Warehouse`, `StockMovement`, `UnitOfMeasure`.
- **Logic**: Real-time stock tracking, costing methods, and warehouse management.

### 🏦 `treasury`
- **Models**: `CashBox`, `BankAccount`.
- **Logic**: Managing liquid assets and multi-currency support.

### 📊 `reports`
- **Logic**: Generates Balance Sheets, Profit & Loss statements, and Ledger reports using background tasks.

---

## ⚙️ Core Principles & Rules

### 1. The Golden Rule of Journal Entries
**NEVER** create a `JournalEntry` or `JournalLine` manually in a view. Always use `JournalService.create_entry()`. This ensures:
- Sum(Debit) == Sum(Credit).
- The entry is linked to an active `FiscalYear`.
- Audit logs are created.
- Auto-generation of unique entry numbers.

### 2. Automatic COA Linking
Entities like **Customers**, **Suppliers**, **Cash Boxes**, and **Banks** are 1:1 linked to an `Account`. When a new Customer is created via `CustomerService`, a corresponding sub-account is created under the "Receivables" parent account automatically.

### 3. Generic Source Documents
`JournalEntry` uses Django's `ContentType` framework to link back to the source document (Invoice, Payment, etc.), allowing for easy drill-down from the General Ledger to the original transaction.

---

## 🚀 Getting Started

1. **Setup Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```

2. **Initialize Database**:
   ```bash
   python manage.py migrate
   python manage.py create_default_chart  # Seeds the Chart of Accounts
   ```

3. **Run Server**:
   ```bash
   python manage.py run dev
   ```

---

## 📝 Arabic Summary (ملخص المشروع)

هذا المشروع هو نظام محاسبي متكامل (ERP) مبني باستخدام Django. يتميز بالنظام المحاسبي المزدوج (Double-entry bookkeeping) وشجرة حسابات مرنة.
- **المبدأ الأساسي**: يتم إنشاء حسابات تلقائية لكل (عميل، مورد، خزينة) في شجرة الحسابات.
- **محرك القيود**: يوجد `JournalService` مركزي لضمان توازن القيود وصحة البيانات المالية.
- **التدقيق**: النظام يسجل كافة العمليات في `AuditLog`.

---

## 🔗 Account Auto-Linking Map

To maintain a consistent General Ledger, the system automatically links entities to specific COA branches:

| Entity | Account Type | Parent Code | Example Generated Code |
| :--- | :--- | :--- | :--- |
| **Customer** | Asset | `1121` | `1121001`, `1121002` |
| **Supplier** | Liability | `2111` | `2111001`, `2111002` |
| **Cash Box** | Asset | `1111` | `11111`, `11112` |
| **Bank Account** | Asset | `1112` | `111201`, `111202` |
| **Employee Custody**| Asset | `1141` | `1141001` |

---

## 🛠️ Execution & Setup Flow

Follow this order to initialize a new system:

1. **Seed COA**: `python manage.py create_default_chart`.
2. **Fiscal Year**: Create the first fiscal year via `/core/fiscal-years/create/`.
3. **Master Data**:
   - Create Cash Boxes and Banks.
   - Create Suppliers and Customers.
   - Setup Warehouses, Units, and Categories.
4. **Inventory**: Create Items and link them to Inventory/COGS accounts.
5. **Transactions**: Start recording daily invoices and payments.

---

## 🤖 AI Context
When working with this repo:
- Business logic MUST reside in **Services** (`apps/*/services.py`).
- **Models** should be kept lean (mostly fields and property methods).
- **Views** should delegate to Services for any data mutation.
- Always ensure the `FiscalYear` is open before attempting to create journal entries.
