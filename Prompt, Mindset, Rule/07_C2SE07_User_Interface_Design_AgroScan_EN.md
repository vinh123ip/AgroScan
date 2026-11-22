# C2SE.07 — USER INTERFACE DESIGN SPECIFICATION
## PROJECT: AI-POWERED SEMI-AUTOMATED MULTI-CATEGORY GOODS INSPECTION SYSTEM (AGROSCAN)

---

## PROJECT INFORMATION

| Attribute | Details |
|---|---|
| **Project Acronym** | **AgroScan** |
| **Project Title** | AI-Powered Semi-Automated Multi-Category Goods Inspection System |
| **Start Date** | 21 Aug 2026 |
| **End Date** | 12 Dec 2026 *(or actual project defense/handover date - [NOTE: FILL IN OR ADJUST PROJECT END DATE])* |
| **Lead Institution** | International School, Duy Tan University |
| **Project Mentor** | M.Sc. Huynh Ba Dieu |
| **Scrum Master / Project Leader** | Pham Le Vinh<br>Email: phamlevinh2011@gmail.com<br>Tel: 0901299871 |
| **Partner Organization** | Duy Tan University |
| **Project Repository / Web URL** | *[NOTE: INSERT GITHUB REPO URL OR INTERNAL URL IF AVAILABLE]* |

### Development Team Members

| Student ID | Full Name | Email | Phone Number | Primary Project Role |
|---|---|---|---|---|
| 28211102597 | Pham Le Vinh | phamlevinh2011@gmail.com | 0901299871 | Scrum Master, Core Backend & AI Architecture |
| 28211105939 | Vu Ha Ninh | vuhaninh20102004@gmail.com | 0352637790 | Team Member, Desktop UI/UX & PySide6 Developer |
| 28219006221 | Dao Tien Dung | dungdao150@gmail.com | 0559751466 | Team Member, Computer Vision & YOLO Integration |
| 28211141406 | Nguyen Dinh Vinh Khang | khanglucky@gmail.com | 0704667333 | Team Member, Data Engineering, Reports & Storage |
| 28211138343 | Le Huy Hoang | hoangdepzai462004@gmail.com | 0938490563 | Team Member, System QA, Testing & Validation |

---

## DOCUMENT APPROVALS

The following signatures are required for formal approval and acceptance of this User Interface Design specification before UI verification.

| Name & Role | Signature | Date |
|---|---|---|
| **M.Sc. Huynh Ba Dieu**<br>Project Mentor / Academic Advisor | *[NOTE: SIGN UPON PRINTING]* | *[NOTE: FILL IN APPROVAL DATE]* |
| **Pham Le Vinh** (ID: 28211102597)<br>Scrum Master / Project Leader | *[NOTE: SIGN UPON PRINTING]* | *[NOTE: FILL IN DATE]* |
| **Vu Ha Ninh** (ID: 28211105939)<br>Team Member / UI Lead | *[NOTE: SIGN UPON PRINTING]* | *[NOTE: FILL IN DATE]* |
| **Dao Tien Dung** (ID: 28219006221)<br>Team Member | *[NOTE: SIGN UPON PRINTING]* | *[NOTE: FILL IN DATE]* |
| **Nguyen Dinh Vinh Khang** (ID: 28211141406)<br>Team Member | *[NOTE: SIGN UPON PRINTING]* | *[NOTE: FILL IN DATE]* |
| **Le Huy Hoang** (ID: 28211138343)<br>Team Member | *[NOTE: SIGN UPON PRINTING]* | *[NOTE: FILL IN DATE]* |

---

## DOCUMENT METADATA & REVISION HISTORY

| Document Information | Details |
|---|---|
| **Document Title** | User Interface Design Document (UIDD) |
| **Document Identifier** | C2SE.07_User_Interface_Design_AgroScan_ver1.2 |
| **Target System** | AgroScan Industrial Workstation (Desktop Client on Windows 10/11) |
| **UI Framework** | PySide6 (Qt for Python 6.x) with Custom Modular QSS (Dark/Light Mode) |

### Revision History

| Version | Date | Author(s) | Summary of Changes |
|---|---|---|---|
| **1.0** | 15/09/2026 | AgroScan Development Team | Initial document structure created based on C2SE.07 template. Drafted initial wireframes for Login and Live Camera Inspection screens. |
| **1.1** | 10/10/2026 | AgroScan Development Team | Updated screen structure aligned with the industrial 12-step intake workflow. Added detailed technical specifications for Box Intake (Barcode/QR scanning) and Catalog & Criteria Editor. |
| **1.2** | 06/11/2026 | AgroScan Development Team | Completed full UI specifications matching actual codebase: Synchronized `PageKey` navigation registry and 3-tier Role-Based Access Control (`Admin`, `Inspector`, `Reviewer`); specified VLM JSON Schema 1.0 result panel (Qwen-VL); integrated SHA-256 evidence preservation rules; added ISO/IEC 18004 standard QR label dialog specification. |

---

## 1. Introduction

### 1.1. Purpose
This User Interface Design Document (UIDD) is compiled to:
1. **Provide a detailed and visual description of all screens, interaction flows, control widgets, and system feedback** for the **AgroScan** industrial workstation client (Desktop application built with PySide6/Qt).
2. **Establish a cohesive Design System and QSS Styling Architecture:** Explicitly define buttons, input fields, data tables, status badges, warning banners, and inline error-handling mechanisms tailored for factory/warehouse inspection environments.
3. **Serve as a unified technical reference across development tracks:** Ensure that desktop UI developers (Qt/Frontend), computer vision engineers (YOLO/ByteTrack), backend engineers (PostgreSQL/LAN REST APIs), and QA engineers share an identical understanding of view states, widget mappings, validation constraints, and error boundaries.
4. **Provide an Acceptance Testing Baseline:** Ensure that the implemented application satisfies all agreed architecture decisions (`DECISIONS.md`), business rules (`PROJECT.md`), and delivery milestones (`PROGRESS.md`).

### 1.2. Scope
This document covers the local desktop workstation client of AgroScan connected to the LAN server, supporting three distinct user roles with specific operational privileges:
- **Inspector (Workstation Operator):** Rapid intake with USB 2D QR/barcode scanners, real-time camera inspection monitoring, official still evidence capture (with SHA-256 hashing), and submitting preliminary evaluation results to the review queue.
- **Reviewer:** Signs in from any PC across the local area network (LAN) to audit `PENDING_REVIEW` inspection sessions, inspect high-resolution evidence images, examine deep analysis insights from Vision-Language Models (Qwen-VL), and issue binding final decisions (`PASS`, `FAIL`, or `RE_INSPECT`).
- **Administrator:** Manages goods categories, binds dedicated YOLO models per commodity fruit type, configures defect thresholds and immediate-rejection criteria; manages user accounts and roles; executes batch data imports from Excel/CSV/PDF; and configures LAN infrastructure endpoints (PostgreSQL IP, Qwen-VL service URL, SMB evidence share).

All user interface labels, action buttons, notifications, status badges, and report headers are standardized in **International English** according to Architecture Decision `D-013`.

---

## 2. Interface Design

The AgroScan interface is organized into 5 functional modules reflecting the end-to-end industrial quality control lifecycle:
- **2.1. Common Layout & Application Shell:** Main window shell, role-based dynamic navigation sidebar, header bar, and asynchronous loading transitions.
- **2.2. Authentication & Pre-login Configuration:** User sign-in dialog, quick demo role switcher, and pre-login LAN connection settings dialog.
- **2.3. Operations Module:** Operational shift dashboard, box intake & QR scanning, ISO/IEC 18004 QR label dialog, real-time live inspection camera, Qwen-VL deep analysis panel, deterministic rule-engine assessment result, and reviewer decision queue.
- **2.4. Records Module:** Comprehensive inspection history lookup, complete record audit detail widget, and aggregated quality reports & PDF/Excel exports.
- **2.5. Administration Module:** Goods catalog & criteria editor, batch data import & AI PDF extraction, user management, and workstation system settings.

---

### 2.1. Common Layout & Application Shell

#### 2.1.1. Main Window Shell & Navigation Sidebar

> **Functional Description:** The primary desktop application shell (`MainWindow`) wrapping all views after successful authentication. The left navigation sidebar employs Dynamic Role-Based UI (`D-032`): unauthorized pages are completely omitted from memory and sidebar rendering based on the active role (`Admin`, `Inspector`, or `Reviewer`) configured in `navigation.py`.

```
+----------------------------------------------------------------------------------------------------+
| AgroScan [WORKSTATION - STATION-01]               AgroScan / Operations / Box Intake               |
|                                                     [Pham Le Vinh]  [ROLE: INSPECTOR]   [ Logout ] |
+------------------------------------+---------------------------------------------------------------+
| OPERATIONS                         |                                                               |
|   [x] Dashboard                    |                                                               |
|   [ ] Box Intake                   |                                                               |
|   [ ] Review Queue (Reviewer/Admin)|                   <ACTIVE VIEWPORT CONTENT>                   |
|                                    |                                                               |
| RECORDS                            |                    (Dynamic QStackedWidget)                   |
|   [ ] Inspection History           |                                                               |
|   [ ] Reports                      |                                                               |
|                                    |                                                               |
| ADMINISTRATION (Admin only)        |                                                               |
|   [ ] Data Import                  |                                                               |
|   [ ] Catalog & Criteria           |                                                               |
|   [ ] Users                        |                                                               |
|   [ ] Settings                     |                                                               |
+------------------------------------+---------------------------------------------------------------+
```

> **[NOTE FOR YOU TO FILL IN / INSERT WIREFRAME OR ACTUAL SCREENSHOT HERE]:**
> *Capture a screenshot of the running application or insert a design mockup showing the MainWindow shell and sidebar navigation here. Suggested filename: `fig_2_1_1_main_window_shell.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **App Branding & Logo** | `QLabel` (`#AppTitle`, `#StationBadge`) | Fixed (Read-only) | Displays "AgroScan" brand identity and the active workstation ID (e.g., `STATION-01`) for clear physical plant identification. |
| **Nav Section: OPERATIONS** | `QLabel` (`#NavSectionLabel`) | Fixed (Read-only) | Section label grouping daily workstation inspection tasks (Dashboard, Box Intake, Review Queue). |
| **Nav Button: Dashboard** | `QPushButton` (`.NavButton`) | Mandatory (All roles) | Quick navigation to the daily inspection shift dashboard. |
| **Nav Button: Box Intake** | `QPushButton` (`.NavButton`) | Mandatory (Admin, Inspector) | Opens the box intake screen to scan QR/barcodes via USB scanner. |
| **Nav Button: Review Queue** | `QPushButton` (`.NavButton`) | Conditional (Admin, Reviewer) | Opens the list of sessions currently awaiting review in `PENDING_REVIEW` state. |
| **Nav Section: RECORDS** | `QLabel` (`#NavSectionLabel`) | Fixed (Read-only) | Section label grouping historical audit and reporting features. |
| **Nav Button: History** | `QPushButton` (`.NavButton`) | Mandatory (All roles) | Opens the search and audit log page for past inspection sessions. |
| **Nav Button: Reports** | `QPushButton` (`.NavButton`) | Mandatory (All roles) | Opens quality analytics charts and PDF/Excel report export features. |
| **Nav Section: ADMINISTRATION** | `QLabel` (`#NavSectionLabel`) | Conditional (Admin only) | Management section; automatically hidden for Inspector and Reviewer accounts (`D-032`). |
| **Nav Button: Data Import** | `QPushButton` (`.NavButton`) | Conditional (Admin only) | Opens batch import of orders, products, and criteria from Excel/CSV/PDF files. |
| **Nav Button: Catalog & Criteria** | `QPushButton` (`.NavButton`) | Conditional (Admin only) | Opens the product catalog editor, YOLO model binder, and defect criteria threshold manager. |
| **Nav Button: Users** | `QPushButton` (`.NavButton`) | Conditional (Admin only) | Opens operator account management, role assignment, and password reset. |
| **Nav Button: Settings** | `QPushButton` (`.NavButton`) | Conditional (Admin only) | Opens system parameters, LAN database connection, AI endpoint, and SMB storage paths. |

---

#### 2.1.2. Top Header & User Status Bar

> **Functional Description:** Located at the top right of the main window shell, displaying the active view breadcrumb path, authenticated operator details, role indicator badge, and a secure session logout trigger.

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Breadcrumbs Path** | `QLabel` (`#BreadcrumbLabel`) | Fixed (Dynamic text) | Displays hierarchical location path (e.g., `AgroScan / Operations / Live Inspection`). |
| **User Full Name** | `QLabel` (`#UserLabel`) | Fixed (Dynamic text) | Shows the display name of the currently signed-in operator (e.g., `Pham Le Vinh`). |
| **Role Badge** | `StatusBadge` (`role="admin\|inspector\|reviewer"`) | Fixed (Dynamic styling) | Color-coded status badge identifying active privileges: Purple/Blue for Admin, Blue for Inspector, Orange/Amber for Reviewer. |
| **Logout Button** | `QPushButton` (`#LogoutButton`) | Mandatory (Interactive) | Initiates session termination. If an unsubmitted inspection session is in progress, prompts confirmation (`_confirm_discard_active_session`) before releasing the camera and returning to the sign-in dialog. |

---

#### 2.1.3. Loading & Transition Screen

> **Functional Description:** Smooth translucent overlay (`LoadingScreen`) with a custom vector spinner (`QProgressIndicator`) and informative progress caption, displayed when navigating to data-heavy or network-bound modules (`is_heavy=True` such as Review Queue, History, and Reports).

> **[NOTE FOR YOU TO FILL IN / INSERT WIREFRAME OR ACTUAL SCREENSHOT HERE]:**
> *Capture a screenshot or insert a mockup of the LoadingScreen overlay here. Suggested filename: `fig_2_1_3_loading_screen.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Overlay Background** | `QWidget` (`#LoadingOverlay`) | Semi-transparent | Dimmed backdrop preventing duplicate user clicks or conflicting inputs during data queries. |
| **Animated Spinner** | `LoadingSpinnerWidget` | Auto-rotating | Hardware-accelerated vector spinner rendered with the primary brand emerald accent. |
| **Loading Title** | `QLabel` (`#LoadingTitle`) | Fixed (Dynamic text) | Caption indicating the ongoing background operation (e.g., `"Loading Review Queue..."`). |
| **Loading Subtitle / Progress Note** | `QLabel` (`#LoadingSubtitle`) | Optional (Dynamic text) | Secondary detail string (e.g., `"Fetching pending records from LAN server..."`). |

---

### 2.2. Authentication & Pre-login Configuration

#### 2.2.1. User Login Dialog

> **Functional Description:** The entry authentication dialog (`src/agroscan/ui/pages/login_dialog.py`). Supports secure HMAC-SHA256 bearer token authentication (`D-027`), inline error feedback, quick demo sign-in shortcuts (Admin, Inspector, Reviewer) for evaluation, and a direct link to configure network endpoints before logging in.

```
+-------------------------------------------------------------------+
|                             AgroScan                              |
|                      INSPECTION WORKSTATION                       |
|                                                                   |
|   +-----------------------------------------------------------+   |
|   | Sign In                                       [DEMO MODE] |   |
|   |                                                           |   |
|   | Username   [ admin                                    ]   |   |
|   | Password   [ ••••••••                                 ]   |   |
|   |                                                           |   |
|   | [⚠ Invalid username or password.]  (hidden when valid)    |   |
|   |                                                           |   |
|   | [                    Sign In  →                       ]   |   |
|   |                                                           |   |
|   | QUICK DEMO SIGN-IN                                        |   |
|   | [   Admin   ]  [  Inspector  ]  [   Reviewer   ]          |   |
|   +-----------------------------------------------------------+   |
|                                                                   |
|                    [ Connection Settings… ]                       |
+-------------------------------------------------------------------+
```

> **[NOTE FOR YOU TO FILL IN / INSERT WIREFRAME OR ACTUAL SCREENSHOT HERE]:**
> *Capture a screenshot of the actual AgroScan login dialog here. Suggested filename: `fig_2_2_1_login_dialog.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Workstation Header** | `QLabel` (`#DialogTitle`, `#DialogSubtitle`) | Fixed (Read-only) | Displays application branding "AgroScan" and workstation operational mode. |
| **Demo Mode Badge** | `QLabel` (`#MockBadge`) | Fixed (Visual tag) | Amber tag indicating the workstation supports pre-configured evaluation accounts. |
| **Username Field** | `QLineEdit` (`#UsernameField`) | Mandatory (User input) | Input field for operator account name (e.g., `admin`, `inspector`, `reviewer`). Includes helper placeholder text. |
| **Password Field** | `QLineEdit` (`#PasswordField`) | Mandatory (User input) | Masked password entry field (`EchoMode.Password`). |
| **Inline Error Message** | `QLabel` (`#InlineErrorLabel`) | Automatic (Show/Hide) | Red text displayed on invalid credentials, locked accounts, or database connection dropouts. Automatically resets when typing resumes. |
| **Sign In Button** | `QPushButton` (`#PrimaryButton`) | Mandatory (Interactive) | Dispatches authentication request. Triggered on `Enter` key. |
| **Quick Demo: Admin** | `QPushButton` (`.QuickLoginButton`) | Optional (One-click) | Autofills Admin credentials (`admin`/`admin123`) and signs in directly with administrative privileges. |
| **Quick Demo: Inspector** | `QPushButton` (`.QuickLoginButton`) | Optional (One-click) | Autofills Inspector credentials (`inspector`/`insp123`) and opens workstation camera intake workflows. |
| **Quick Demo: Reviewer** | `QPushButton` (`.QuickLoginButton`) | Optional (One-click) | Autofills Reviewer credentials (`reviewer`/`rev123`) and navigates to the pending audit queue. |
| **Connection Settings Link** | `QPushButton` (`#LinkButton`) | Optional (Interactive) | Opens `ConnectionSettingsDialog` to adjust LAN server addresses prior to login (`D-028`). |

---

#### 2.2.2. Pre-login Connection Settings Dialog

> **Functional Description:** Allows plant technicians to configure LAN server parameters (PostgreSQL, Qwen-VL, SMB storage share) directly from the login interface without requiring prior authentication, enabling portable workstation mobility across warehouses (`D-028`).

> **[NOTE FOR YOU TO FILL IN / INSERT WIREFRAME OR ACTUAL SCREENSHOT HERE]:**
> *Capture a screenshot of the Connection Settings Dialog here. Suggested filename: `fig_2_2_2_connection_settings_dialog.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **PostgreSQL Host IP** | `QLineEdit` (`#FormField`) | Mandatory (IP/Hostname) | LAN IP address or hostname of the PostgreSQL database host (e.g., `192.168.1.10`). |
| **PostgreSQL Port** | `QSpinBox` (`#FormSpin`) | Mandatory (1–65535) | Database service port (default: `5432`). |
| **Test DB Connection Button** | `QPushButton` (`#SecondaryButton`) | Optional (Interactive) | Probes TCP socket connectivity to the database host and reports reachability instantly. |
| **Qwen-VL Service URL** | `QLineEdit` (`#FormField`) | Mandatory (URL format) | HTTP REST API base endpoint of the VLM service running on the server (e.g., `http://192.168.1.10:8000`). |
| **AI Timeout (seconds)** | `QSpinBox` (`#FormSpin`) | Mandatory (1–120 sec) | Maximum allowable duration to wait for deep image inference (default: 30 seconds). |
| **Test AI Service Button** | `QPushButton` (`#SecondaryButton`) | Optional (Interactive) | Dispatches an HTTP GET health-check to verify VLM service responsiveness. |
| **SMB Image Folder Path** | `QLineEdit` (`#FormField`) | Mandatory (UNC Path) | Windows Shared folder path (SMB) for storing original evidence images (e.g., `\\192.168.1.10\AgroScan_Data`). |
| **Save & Apply Button** | `QPushButton` (`#PrimaryButton`) | Mandatory (Interactive) | Persists settings into `app_settings.json` and closes the configuration dialog. |

---

### 2.3. Operations Module

#### 2.3.1. Dashboard Page

> **Functional Description:** The initial landing view upon login (`src/agroscan/ui/pages/dashboard_page.py`), featuring 4 summary KPI metric cards for the current shift and an auto-refreshing table of recent inspection sessions.

```
+----------------------------------------------------------------------------------------------------+
| Dashboard                                                                                          |
| Overview of goods inspection activities                                                            |
+----------------------------------------------------------------------------------------------------+
| [ BOXES INSPECTED TODAY ]  [ PENDING REVIEW ]        [ PASSED ]             [ FAILED ]             |
|          24                       3                      18                      3                 |
|   Total 142 records         Awaiting reviewer       Confirmed reviewer     Confirmed reviewer      |
+----------------------------------------------------------------------------------------------------+
| RECENT ACTIVITY                                                                                    |
| +---------------------+--------------------+------------+------------------+-----------+---------+ |
| | Session ID          | Box Code           | Product    | Status           | Result    | Started | |
| +---------------------+--------------------+------------+------------------+-----------+---------+ |
| | INS-20261106-0004   | AGS:DH00123-04/10  | Cavendish  | PENDING_REVIEW   | —         | 04:12   | |
| | INS-20261106-0003   | AGS:DH00123-03/10  | Cavendish  | COMPLETED        | PASS      | 04:05   | |
| | INS-20261106-0002   | AGS:DH00121-01/05  | Fuji Apple | COMPLETED        | FAIL      | 03:48   | |
| +---------------------+--------------------+------------+------------------+-----------+---------+ |
+----------------------------------------------------------------------------------------------------+
```

> **[NOTE FOR YOU TO FILL IN / INSERT WIREFRAME OR ACTUAL SCREENSHOT HERE]:**
> *Capture a screenshot of the Dashboard page in the running app here. Suggested filename: `fig_2_3_1_dashboard_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Page Header** | `PageHeader` | Fixed (Read-only) | Page title "Dashboard" and operational subtitle. |
| **Stat Card 1: Today Boxes** | `StatCardWidget` | Automatic (Read-only) | Total count of boxes submitted for inspection during the current calendar day. |
| **Stat Card 2: Pending Review** | `StatCardWidget` | Automatic (Read-only, Highlight) | Number of boxes currently queued in `PENDING_REVIEW` awaiting a reviewer's confirmation. |
| **Stat Card 3: Passed Boxes** | `StatCardWidget` | Automatic (Read-only, Green) | Number of boxes officially confirmed as `PASS` by the reviewer. |
| **Stat Card 4: Failed Boxes** | `StatCardWidget` | Automatic (Read-only, Red) | Number of boxes confirmed as `FAIL` due to defect ratio breaches or critical flaws. |
| **Recent Activity Table** | `DataTable` (`QTableWidget`) | Automatic (Read-only) | Lists the last 8 inspection sessions: Session ID, Box Code, Product, Session Status, Final Result, and Start Timestamp. |

---

#### 2.3.2. Box Intake Page

> **Functional Description:** Entry point of the physical inspection workflow (`src/agroscan/ui/pages/box_intake_page.py`). Captures QR/barcode data from 2D USB scanners (acting as keyboard input with auto-Enter) or manual selection (`D-019`, `D-020`, `D-021`). Canonical QR structure: `AGS:<Order>-<Box>/<Total>`. Incorporates 7 scan validation error codes (including retail EAN-13 mismatch protection), 350ms scanner trigger debouncing, order metadata preview, and auto-binding of the specialized YOLO model.

```
+----------------------------------------------------------------------------------------------------+
| Box Intake                                                                                         |
| Scan the QR label on the box to open an inspection session.                                        |
+----------------------------------------------------------------------------------------------------+
| [ Session INS-20261106-0004 for box AGS:DH00123-04/10 is in progress.                 [Resume →] ] |
|                                                                                                    |
| +------------------------------------------------------------------------------------------------+ |
| | SCAN BOX CODE                                                                                  | |
| | [ AGS:DH00123-04/10                                                                          ] | |
| | The barcode scanner types the code into this field automatically (Enter).                      | |
| +------------------------------------------------------------------------------------------------+ |
| +------------------------------------------------------------------------------------------------+ |
| | OR FIND BY ORDER                                                                               | |
| | [ DH00123 · Cavendish Banana · Mekong Fresh Supply       v ]   [ Box  4 / 10 ]  [Load Box]       | |
| +------------------------------------------------------------------------------------------------+ |
| +------------------------------------------------------------------------------------------------+ |
| | BOX INFORMATION                                                                                | |
| | ORDER: DH00123               BOX: 4 of 10                   PRODUCT: Cavendish Banana          | |
| | SUPPLIER: Mekong Fresh       EXPECTED QTY: 200 units        YOLO MODEL: banana_defect.onnx     | |
| | [▲ This box already has 1 session(s). Starting creates a re-inspection.] (Hidden if fresh)     | |
| | [ Optional notes regarding physical box appearance...                                        ] | |
| +------------------------------------------------------------------------------------------------+ |
|                                                    [ Generate / Print QR ]   [Start Inspection →]  |
+----------------------------------------------------------------------------------------------------+
```

> **[NOTE FOR YOU TO FILL IN / INSERT WIREFRAME OR ACTUAL SCREENSHOT HERE]:**
> *Capture a screenshot of the Box Intake page here. Suggested filename: `fig_2_3_2_box_intake_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Active Session Banner** | `QFrame` (`#WarningBanner`) | Automatic (Show/Hide) | Warns when another session is currently in progress, providing a `Resume` shortcut button. |
| **Scan Box Code Field** | `QLineEdit` (`#ScanField`) | Mandatory (Auto-focus) | Receives raw barcode strings from the USB scanner. Submits automatically on `returnPressed`. |
| **Scan Error Notice** | `QLabel` (`#InlineErrorLabel`) | Automatic (Show/Hide) | Displays exact error message for 7 scanning failure modes: `INVALID_FORMAT`, `EAN13_RETAIL_BARCODE`, `UNKNOWN_ORDER`, `BOX_INDEX_OUT_OF_RANGE`, `BOX_TOTAL_MISMATCH`, etc. |
| **Manual Order Combo** | `QComboBox` (`#FormCombo`) | Optional (Dropdown) | Allows manual order selection if the physical scanner is unavailable or barcode is damaged. |
| **Manual Box SpinBox** | `QSpinBox` (`#FormSpin`) | Optional (1..Total) | Numeric selector for the box sequence index within the chosen order. |
| **Load Box Button** | `QPushButton` (`#SecondaryButton`) | Optional (Interactive) | Loads order and box metadata into the view from the manual selection controls. |
| **Box Info Grid** | `KeyValueGrid` | Fixed (Read-only) | Displays 6 key attributes: Order Code, Box Index, Commodity Name, Supplier, Expected Unit Count, and the dedicated YOLO Model File to be loaded (`D-024`). |
| **Re-inspection Warning** | `QLabel` (`#WarningNote`) | Automatic (Show/Hide) | Amber warning shown when previous inspection sessions exist for this box; confirms a new session is being created without deleting past history (`D-021`). |
| **Session Notes Input** | `QLineEdit` (`#FormField`) | Optional (User input) | Captures visual observations regarding packaging damage prior to conveyor inspection. |
| **Print QR Button** | `QPushButton` (`#SecondaryButton`) | Optional (Interactive) | Opens `QrLabelDialog` to inspect and print ISO/IEC 18004 box QR labels. |
| **Start Inspection Button** | `QPushButton` (`#PrimaryButton`) | Mandatory (Interactive) | Initializes a new inspection session, loads the fruit-specific AI model, and switches to Live Inspection. |

---

#### 2.3.3. QR Label Preview & Print Dialog

> **Functional Description:** Modal dialog (`src/agroscan/ui/components/qr_label_dialog.py`) generating standard ISO/IEC 18004 2D QR matrix labels via pure Python (`qr_encoder.py`), supporting thermal barcode printing or PNG export.

> **[NOTE FOR YOU TO FILL IN / INSERT WIREFRAME OR ACTUAL SCREENSHOT HERE]:**
> *Capture a screenshot of the QrLabelDialog component here. Suggested filename: `fig_2_3_3_qr_label_dialog.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **QR Code Canvas** | `QLabel` (Pixmap Display) | Automatic (High-DPI) | Renders standard QR matrix encoding `AGS:<Order>-<Box>/<Total>` with error correction level L/M. |
| **Label Text Info** | `QVBoxLayout` (`QLabel`) | Automatic (Read-only) | Clear human-readable text below the matrix: Order Code, Box Index, Commodity, Pack Date, Supplier. |
| **Export PNG Button** | `QPushButton` (`#SecondaryButton`) | Optional (Interactive) | Exports the generated label as a high-resolution PNG file. |
| **Print Label Button** | `QPushButton` (`#PrimaryButton`) | Optional (Interactive) | Sends raw print instructions directly to the connected USB industrial thermal label printer. |
| **Close Button** | `QPushButton` (`#SecondaryButton`) | Mandatory (Interactive) | Dismisses the label dialog. |

---

#### 2.3.4. Live Inspection Page

> **Functional Description:** Core inspection workspace for workstation operators (`src/agroscan/ui/pages/live_inspection_page.py`). Feeds real-time video via `QCamera`/`QVideoWidget` or simulated test stream (`D-031`). Renders bounding boxes from the active specialized YOLO model, tracks fruits via ByteTrack to prevent duplicate counts (`D-025`), smooths live metrics over 5 frames (Moving Average), and provides one-click still image capture hashed with SHA-256 (`D-026`).

```
+----------------------------------------------------------------------------------------------------+
| Live Inspection                                                        [ IN PROGRESS ] [DEMO MODE] |
| Box AGS:DH00123-04/10 · Cavendish Banana · Order DH00123                                           |
+-----------------------------------------------------+----------------------------------------------+
| +-------------------------------------------------+ | REALTIME (Simulated / YOLO)                  |
| |                                                 | | Objects in frame:  22                        |
| |         LIVE CAMERA FEED / PREVIEW              | | Fresh: 18  ·  Bruised: 3  ·  Rotten: 1       |
| |                                                 | | Model: banana_defect.onnx                    |
| |   [Bounding Boxes: fresh(95%), bruised(88%)]    | +----------------------------------------------+
| |                                                 | | DEEP ANALYSIS (Qwen-VL)                      |
| +-------------------------------------------------+ | [▲ Low confidence — deep analysis suggested] |
| Camera: USB Industrial HD Camera 01                 | | [ VlmResultPanel Component ]               |
| [ Deep Analysis (Qwen-VL) ] [ ● Capture Evidence ]  | +----------------------------------------------+
|                                                     | | NEXT BOX (Continuous Scan)                 |
| EVIDENCE IMAGES (Still Captures for Legal Audit)    | | [ Scan next box to submit this one       ] |
| [Thumb 1 (SHA-256)] [Thumb 2]  (Double-click view)  | +----------------------------------------------+
| • Official results computed from still images only. | [ Finish Inspection → ]  [ Discard Session ] |
+-----------------------------------------------------+----------------------------------------------+
```

> **[NOTE FOR YOU TO FILL IN / INSERT WIREFRAME OR ACTUAL SCREENSHOT HERE]:**
> *Capture a screenshot of Live Inspection with active camera preview and defect counts here. Suggested filename: `fig_2_3_4_live_inspection_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Session Info Header** | `QLabel` (`#PageTitleSmall`, `#PageSubtitle`) | Fixed (Read-only) | Displays active box code, inspected commodity, and parent order code. |
| **Session Status Badge** | `StatusBadge` (`status="in_progress"`) | Fixed (Visual tag) | Blue badge indicating an active inspection session. |
| **Live Camera Viewport** | `QStackedWidget` (`#CameraFrame`) | Mandatory (Live Feed) | Renders 30fps camera feed. Falls back to "No camera detected" with a "Retry" button if disconnected. |
| **Deep Analysis Button** | `QPushButton` (`#SecondaryButton`) | Optional (Interactive) | Dispatches the latest capture to the server-hosted Qwen-VL endpoint for deep reasoning (`D-017`). |
| **Capture Evidence Button** | `QPushButton` (`#PrimaryButton`) | Mandatory (Interactive) | Captures high-resolution still image as official legal evidence, hashes content with SHA-256, and stores to SMB (`D-026`). |
| **Evidence Strip** | `EvidenceStrip` (`QScrollArea`) | Automatic (Thumbnails) | Displays horizontal thumbnail reel of captured evidence photos. Double-click opens full-screen zoom. |
| **Realtime Objects Count** | `QLabel` (`#RealtimeValue`) | Automatic (Moving Average) | Displays stable object count in camera view smoothed across 5 consecutive frames. |
| **Realtime Defect Breakdown** | `QGridLayout` | Automatic (Dynamic stats) | Itemized counts by defect class (e.g., Fresh, Bruised, Rotten) from the specialized YOLO model. |
| **Next Box Continuous Field** | `QLineEdit` (`#FormField`) | Optional (Scanner input) | Continuous scanning (`D-020`): Scanning the next box automatically moves current session to `PENDING_REVIEW` and initializes the new box session. |
| **Finish Inspection Button** | `QPushButton` (`#PrimaryButton`) | Mandatory (Interactive) | Concludes camera observation and navigates to the automated assessment review view (`AssessmentResultPage`). |
| **Discard Session Button** | `QPushButton` (`#DangerButton`) | Optional (Warning red) | Discards all captures and data for this session and returns to intake (requires confirmation). |

---

#### 2.3.5. VLM Deep Analysis Panel (Qwen-VL)

> **Functional Description:** Embedded inspection widget (`src/agroscan/ui/components/vlm_result_panel.py`) presenting multi-modal reasoning from Qwen-VL on the LAN server (`D-017`), strictly complying with `JSON Schema 1.0` (`docs/api/vlm_analysis.schema.json`). Renders 4 distinct states: Idle, Loading (with progress bar), Result (defects breakdown and OCR order-matching), and Error (5 typed failure codes with retry support).

```
+-------------------------------------------------------------------+
| DEEP ANALYSIS                                       [✔ OK] [MOCK] |
| qwen2.5-vl-7b · 1.4 s · 04:10:12                                  |
+-------------------------------------------------------------------+
| DEFECTS DETECTED                                                  |
| Class       Count    Severity       Confidence                    |
| Bruised     3        Minor          84%                           |
| Rotten      1        ▲ Critical     91%                           |
+-------------------------------------------------------------------+
| LABEL OCR (Box Label Cross-Verification)                          |
| Box Code:     AGS:DH00123-04/10                 (97% - Match)     |
| Supplier:     Unknown Packer                    (88% - [≠ Mismatch])|
|               [≠ Declared Order: Mekong Fresh]                    |
| Packed Date:  2026-11-04                        (81%)             |
+-------------------------------------------------------------------+
| UNCERTAINTY LEVEL                                                 |
| [▲ MEDIUM · 0.42] - Partial occlusion at the bottom corner        |
+-------------------------------------------------------------------+
| AI OBSERVATIONS & SUGGESTION                                      |
| • Observations: Severe stem decay and bruising detected.          |
| • Suggestion: Rotate bottom layer and capture a second image.     |
| (Advisory only — never overrides deterministic Python rules)       |
+-------------------------------------------------------------------+
```

> **[NOTE FOR YOU TO FILL IN / INSERT WIREFRAME OR ACTUAL SCREENSHOT HERE]:**
> *Capture a screenshot of VlmResultPanel showing defects and label OCR verification here. Suggested filename: `fig_2_3_5_vlm_result_panel.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **VLM Status Badge** | `StatusBadge` | Automatic (Read-only) | Reflects inference execution outcome: `OK` (green), `PARTIAL` (amber), `ERROR` (red). |
| **Execution Metadata** | `QLabel` (`#HintLabel`) | Automatic (Read-only) | Displays model identifier (`qwen2.5-vl-7b`), inference latency (`latency_ms`), and analysis timestamp. |
| **Defects Analysis Table** | `QGridLayout` (`#VlmValue`) | Automatic (Dynamic) | Lists detected defects: Class name, Count, Severity (Minor, Major, Critical in bold red), and Confidence (%). Hovering reveals detailed descriptions. |
| **Label OCR Verification** | `QGridLayout` (`#VlmValue`) | Automatic (Comparison) | OCR-extracted text from box packaging (Box Code, Supplier, Pack Date). Mismatches against order data highlight an amber badge `≠ Differs from order`. |
| **Uncertainty Indicator** | `StatusBadge` + `QLabel` | Automatic (Read-only) | Expresses AI uncertainty rating (Low / Medium / High with 0.0–1.0 score) and root cause notes (e.g., poor lighting or fruit occlusion). |
| **AI Assessment & Suggestion** | `QLabel` (`#VlmValue`) | Automatic (WordWrap) | Natural language summary from Qwen-VL providing actionable inspection advice for the operator. |
| **API Error & Retry Block** | `QFrame` (`#VlmErrorPanel`) | Automatic (On error) | Displays typed failure reason (`TIMEOUT`, `SERVICE_UNAVAILABLE`, `INVALID_RESPONSE`, `IMAGE_UNUSABLE`) with a `Retry` action if recoverable. |

---

#### 2.3.6. Assessment Result Page

> **Functional Description:** Workstation technical evaluation view (`src/agroscan/ui/pages/assessment_result_page.py`). Applies the deterministic Python Rule Engine (`D-007`, `D-023`) against captured still evidence and database quality thresholds. Formulates an automated recommendation (`AiRecommendation`: `PASS`, `FAIL`, or `NEEDS_REVIEW`). Workstation operators do not unilaterally approve batches here; submitting forwards the session to the review queue (`D-020`).

> **[NOTE FOR YOU TO FILL IN / INSERT WIREFRAME OR ACTUAL SCREENSHOT HERE]:**
> *Capture a screenshot of the Assessment Result page here. Suggested filename: `fig_2_3_6_assessment_result_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Page Header** | `PageHeader` | Fixed (Read-only) | Page banner clarifying that the evaluation is calculated via deterministic Python criteria. |
| **Record Detail Component** | `RecordDetailWidget` | Fixed (Integrated) | Full session audit view: Box metadata, still evidence images, defect ratio table vs limits, and VLM analysis results. |
| **Rule Recommendation Badge** | `StatusBadge` | Automatic (Highlight) | Rule-engine proposed outcome: `PASS` (Accept), `FAIL` (Reject), or `NEEDS_REVIEW` (Flagged for scrutiny). |
| **Rule Evaluation Reasons** | `QLabel` (`#ValueLabel`) | Automatic (Bullet points) | Itemized logic triggers (e.g., `"Bruised ratio 12.5% exceeds limit 10.0%"`, `"Detected 1 rotten fruit marked as immediate critical failure"`). |
| **Next Box Scan Field** | `QLineEdit` (`#FormField`) | Optional (Scanner input) | Scanning the next box automatically submits this session to review and opens the next intake. |
| **Back Button** | `QPushButton` (`#SecondaryButton`) | Optional (Interactive) | Returns to Live Inspection to capture additional evidence or re-evaluate. |
| **Submit for Review Button** | `QPushButton` (`#PrimaryButton`) | Mandatory (Interactive) | Submits the entire session package into the server's `PENDING_REVIEW` queue (`D-020`). |

---

#### 2.3.7. Review Queue Page

> **Functional Description:** Dedicated workstation environment for Reviewers and Administrators (`src/agroscan/ui/pages/review_queue_page.py`). Split-view layout: Left panel lists queued `PENDING_REVIEW` boxes submitted from all workstations across the LAN; right panel presents full audit evidence and 3 binding decision actions (`D-027`, `D-030`).

```
+----------------------------------------------------------------------------------------------------+
| Review Queue                                                                                       |
| Sessions waiting for a reviewer decision. Oldest first.                                            |
+-----------------------------------+----------------------------------------------------------------+
| 3 PENDING SESSIONS                | RECORD DETAIL: INS-20261106-0004                               |
| +-------------------------------+ | Box: AGS:DH00123-04/10 · Product: Cavendish Banana             |
| |Box Code |Product |AI Rec|Time | | Inspector: Vu Ha Ninh · Station: STATION-01                    |
| |---------|--------|------|-----| |                                                                |
| |DH00123-4|Banana  |NEEDS |04:12| | [ Evidence Image Thumbnail Strip with SHA-256 Hash ]           |
| |DH00122-1|Apple   |FAIL  |04:08| | [ Detection Breakdown vs Quality Criteria Table ]              |
| |DH00121-5|Mango   |PASS  |03:55| | [ Qwen-VL Deep Analysis Observations & Label OCR ]             |
| +-------------------------------+ |                                                                |
|                                   | YOUR OFFICIAL DECISION                                         |
|                                   | [ Optional audit remarks or re-inspection directives...      ] |
|                                   | [  PASS (Accept)  ]  [  FAIL (Reject)  ]  [  RE-INSPECT  ]     |
+-----------------------------------+----------------------------------------------------------------+
```

> **[NOTE FOR YOU TO FILL IN / INSERT WIREFRAME OR ACTUAL SCREENSHOT HERE]:**
> *Capture a screenshot of Review Queue with pending sessions and reviewer actions here. Suggested filename: `fig_2_3_7_review_queue_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Pending Count Header** | `QLabel` (`#FormSectionTitle`) | Automatic (Read-only) | Count of unreviewed sessions currently awaiting adjudication (ordered oldest first). |
| **Queue Table List** | `DataTable` (`QTableWidget`) | Mandatory (Single selection) | Interactive table of queued boxes: Box Code, Product, AI Recommendation, Inspector, Start Time. |
| **Record Detail Panel** | `RecordDetailWidget` | Fixed (Scrollable) | Full evidence review view: Order details, still captures, SHA-256 hashes, defect metrics, and VLM findings. |
| **Reviewer Decision Notes** | `QPlainTextEdit` (`#NotesField`) | Optional (User input) | Input field for reviewer remarks or corrective directives stored permanently in the audit trail. |
| **Decision Button: PASS** | `QPushButton` (`#PassButton`) | Mandatory (Emerald green) | Confirms the box satisfies quality requirements, transitioning session to `COMPLETED`. |
| **Decision Button: FAIL** | `QPushButton` (`#DangerButton`) | Mandatory (Bright red) | Rejects the box due to non-conformance. |
| **Decision Button: RE-INSPECT** | `QPushButton` (`#SecondaryButton`) | Mandatory (Slate/Amber) | Directs the workstation operator to re-sample or re-scan the box (`D-030`). |

---

### 2.4. Records Module

#### 2.4.1. Inspection History Page

> **Functional Description:** Historical repository and audit query interface (`PageKey.INSPECTION_HISTORY`). Supports multi-dimensional filtering (date range, box/order code, commodity type, session status, inspector/reviewer) and immutable read-only evidence inspection.

> **[NOTE FOR YOU TO FILL IN / INSERT WIREFRAME OR ACTUAL SCREENSHOT HERE]:**
> *Capture a screenshot of the Inspection History page here. Suggested filename: `fig_2_4_1_inspection_history_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Search Filter Field** | `QLineEdit` (`#FormField`) | Optional (Search query) | Real-time text search by order code, box code, or supplier name. |
| **Product Category Filter** | `QComboBox` (`#FormCombo`) | Optional (Dropdown) | Filters records by specific commodity category (Banana, Apple, Mango, etc.). |
| **Status Filter** | `QComboBox` (`#FormCombo`) | Optional (Dropdown) | Filters by workflow state (`ALL`, `IN_PROGRESS`, `PENDING_REVIEW`, `COMPLETED`). |
| **Date Range Pickers** | `QDateEdit` (From / To) | Optional (Date filter) | Constrains inspection records within a specified operational date window. |
| **History Data Table** | `DataTable` (`QTableWidget`) | Fixed (Multi-column) | Primary audit table: Session ID, Box Code, Product, Official Decision, Inspector, Reviewer, Timestamp. |
| **View Details Action** | `QPushButton` (`#SecondaryButton`) | Mandatory (Interactive) | Opens `RecordDetailWidget` displaying the complete sealed inspection record with original evidence photos. |

---

#### 2.4.2. Inspection Record Detail View

> **Functional Description:** Reusable component (`src/agroscan/ui/components/record_detail.py`) embedded across Assessment Result, Review Queue, and History pages, preserving the complete legal integrity of inspection sessions (`PROJECT.md` §5).

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Session Metadata Section** | `KeyValueGrid` | Fixed (Read-only) | 3-column grid displaying Session ID, Box Code, Status, Product, Supplier, Workstation, Start Time, and Physical Notes. |
| **AI Recommendation Card** | `SectionCard` | Automatic (Read-only) | Rule-engine outcome badge (`PASS`/`FAIL`/`NEEDS_REVIEW`) and underlying logical justifications. |
| **Evidence Image Preview Strip** | `EvidenceStrip` | Mandatory (High-res strip) | Displays thumbnails of captured still images with SHA-256 hashes calculated before AI inference (`D-026`). Click to enlarge. |
| **Defect vs Criteria Table** | `DataTable` | Automatic (Read-only) | 5-column comparison table: Defect Class, Detected Count, Percentage Ratio, Permitted Limit, and Critical Immediate-Rejection Flag. |
| **VLM Analysis Details** | `VlmResultPanel` | Optional (Show/Hide) | Deep reasoning insights from Qwen-VL (rendered only if deep analysis was executed for this session). |
| **Reviewer Decision Card** | `SectionCard` | Automatic (Read-only) | Binding human determination: Final Decision (`PASS`/`FAIL`/`RE_INSPECT`), Reviewer Username, Timestamp, and Remarks. |

---

#### 2.4.3. Reports & Analytics Page

> **Functional Description:** Analytical dashboard for quality assurance supervisors and plant management (`PageKey.REPORTS`). Aggregates outcomes at the order level ("8/10 boxes passed, 1 pending, 1 failed" - `D-022`), plots quality defect trends, and exports synchronized datasets to PDF and Excel formats (`D-010`).

> **[NOTE FOR YOU TO FILL IN / INSERT WIREFRAME OR ACTUAL SCREENSHOT HERE]:**
> *Capture a screenshot of the Reports & Analytics view here. Suggested filename: `fig_2_4_3_reports_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Report Scope Filter** | `QComboBox` / `QDateEdit` | Mandatory (Filter settings) | Selects reporting boundaries: By inbound shipment lot, supplier, or date range. |
| **Order-Level Summary Cards** | `QHBoxLayout` (`StatCard`) | Automatic (Calculated) | Displays aggregated order conformance: Count and percentage of passed boxes out of total order lot size (`D-022`). |
| **Quality Breakdown Chart** | `QWidget` (Matplotlib Canvas) | Automatic (Pie/Bar chart) | Visualizes relative distribution of defect types (Bruising, Rot, Scratches, Pest damage) per commodity fruit. |
| **Daily Throughput Chart** | `QWidget` (Line Chart) | Automatic (Line chart) | Trends daily inspection volume and pass/fail ratios across all active workstations. |
| **AI Summary Commentary Box** | `QPlainTextEdit` (Read-only) | Optional (Qwen generated) | Natural language synthesis summarizing supplier quality trends generated on demand by the AI model (`PROJECT.md` §3 step 10). |
| **Export Excel Button** | `QPushButton` (`#SecondaryButton`) | Mandatory (Interactive) | Exports tabular inspection metrics and raw defect numbers into a structured Microsoft Excel (.xlsx) workbook. |
| **Export PDF Report Button** | `QPushButton` (`#PrimaryButton`) | Mandatory (Interactive) | Generates a publication-grade PDF quality inspection certificate featuring charts, criteria tables, and SHA-256 evidence links. |

---

### 2.5. Administration Module

#### 2.5.1. Catalog & Inspection Criteria Editor

> **Functional Description:** Core configuration console for system administrators (`src/agroscan/ui/pages/catalog_page.py`). Enables creating/modifying commodities, binding dedicated specialized YOLO models (`banana_defect.onnx`, `apple_defect.onnx` - `D-024`), and setting allowable defect thresholds and immediate rejection flags (`Fail immediately` - `D-023`). Enforces rigorous validation constraints (`catalog_validation.py`) and protects unsaved changes.

```
+----------------------------------------------------------------------------------------------------+
| Catalog & Criteria                                                                     [MOCK DATA] |
| Goods categories, products, their dedicated YOLO model and defect criteria.                         |
+-----------------------------------+----------------------------------------------------------------+
| Category: [ All categories    v ] | Banana · BANANA                                                |
| 3 PRODUCTS                        | [▲ Used by 2 order(s): DH00121, DH00123. Code is read-only]    |
| +-------------------------------+ |                                                                |
| |Code  |Name    |Category|Model | | PRODUCT PROFILE                                                |
| |------|--------|--------|------| | Code:            [ BANANA             ] (Locked when in use)   |
| |BANANA|Cavendis|Fruit   |ban...| | Name:            [ Cavendish Banana   ]                           |
| |APPLE |Fuji App|Fruit   |app...| | Category:        [ Fruit            v ]                           |
| |MANGO |Aust. Ma|Fruit   |man...| | YOLO Model File: [ banana_defect.onnx ]                           |
| +-------------------------------+ | Detect Classes:  [ fresh, bruised, rotten ]                      |
| [+ New Product] [Delete Product]  +----------------------------------------------------------------+
|                                   | QUALITY & DEFECT CRITERIA                                      |
|                                   | Min Objects in Frame: [ 5  ]     Min Confidence: [ 60 % ]      |
|                                   | +------------------------------------------------------------+ |
|                                   | | Defect Class    | Max Ratio (%)      | Critical (Fail Imm.)| |
|                                   | |-----------------|--------------------|---------------------| |
|                                   | | [bruised      v]| [ 10.0 %         ] | [ ]                 | |
|                                   | | [rotten       v]| [  0.0 %         ] | [x] Fail imm.       | |
|                                   | +------------------------------------------------------------+ |
|                                   | [+ Add Criterion]  [Remove Selected]                           |
|                                   | ● Unsaved changes                    [Revert]  [Save Changes]  |
+-----------------------------------+----------------------------------------------------------------+
```

> **[NOTE FOR YOU TO FILL IN / INSERT WIREFRAME OR ACTUAL SCREENSHOT HERE]:**
> *Capture a screenshot of Catalog & Criteria Editor in the running app here. Suggested filename: `fig_2_5_1_catalog_criteria_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Category Filter** | `QComboBox` (`#FormCombo`) | Optional (Dropdown) | Filters the product table by commodity category (Fruit, Vegetable, etc.). |
| **Product List Table** | `DataTable` (`QTableWidget`) | Mandatory (Single selection) | Displays registered products: Product Code, Commercial Name, Category, Model File, Criteria Count. |
| **Add Product Button** | `QPushButton` (`#SecondaryButton`) | Optional (Interactive) | Adds a new agricultural commodity to the inspection catalog. |
| **Product Code Field** | `QLineEdit` (`#FormField`) | Mandatory (Regex: `^[A-Z0-9_]+$`) | Unique identifier for the product (e.g., `BANANA`). Automatically locked to read-only if orders reference it. |
| **Product Name Field** | `QLineEdit` (`#FormField`) | Mandatory (1–60 chars) | Commercial display name of the fruit (e.g., `Cavendish Banana`). |
| **YOLO Model File Field** | `QLineEdit` (`#FormField`) | Mandatory (ONNX/PT filename) | Specialized model filename loaded dynamically during inspection (`D-024` e.g., `banana_defect.onnx`). |
| **Detect Classes Field** | `QLineEdit` (`#FormField`) | Mandatory (Comma-separated) | Supported detection classes; index 0 is strictly reserved for the sound/healthy class (`fresh`). |
| **Min Objects SpinBox** | `QSpinBox` (`#FormSpin`) | Mandatory (1–500 items) | Minimum object count in frame; lower counts automatically trigger `NEEDS_REVIEW`. |
| **Min Confidence SpinBox** | `QSpinBox` (`#FormSpin`) | Mandatory (0–100%) | Minimum mean detector confidence; lower values trigger deep analysis recommendations. |
| **Criteria Defect Class** | `QComboBox` (In table) | Mandatory (Select defect) | Target defect class to apply a quality tolerance rule (e.g., `bruised`, `rotten`). |
| **Max Defect Ratio (%)** | `QDoubleSpinBox` (In table) | Mandatory (0.0–100.0%) | Maximum allowable proportion of defective units; exceeding triggers an automated rejection proposal. |
| **Critical Checkbox** | `QCheckBox` (`Fail immediately`) | Optional (Boolean toggle) | Critical defect flag: If any fruit exhibits this defect (e.g., decay/rot), immediately proposes `FAIL` (`D-023`). |
| **Save Changes Button** | `QPushButton` (`#PrimaryButton`) | Mandatory (Interactive) | Persists all product specifications and defect rules into PostgreSQL. |

---

#### 2.5.2. Data Import Page

> **Functional Description:** Batch onboarding interface (`PageKey.DATA_IMPORT` - `D-029`) enabling bulk loading of inbound orders, product catalogs, and quality specifications from Excel/CSV templates, or parsing supplier PDF delivery bills via Qwen-VL. Includes row-level dry-run validation prior to database commit.

> **[NOTE FOR YOU TO FILL IN / INSERT WIREFRAME OR ACTUAL SCREENSHOT HERE]:**
> *Capture a screenshot of the Data Import page here. Suggested filename: `fig_2_5_2_data_import_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Import Channel Selector** | `QRadioButton` / `Tabs` | Mandatory (Toggle) | Selects data channel: Excel/CSV (primary channel) or PDF (AI-assisted extraction). |
| **Template Download Link** | `QPushButton` (`#LinkButton`) | Optional (File download) | Downloads standardized AgroScan Excel (.xlsx) template with predefined schemas and examples. |
| **File Drag & Drop Area** | `QFrame` (`#UploadDropZone`) | Mandatory (File selector) | Drag-and-drop zone or file browser button to upload `.xlsx`, `.csv`, or `.pdf` documents. |
| **Validation Report Table** | `DataTable` (`QTableWidget`) | Automatic (Row verification) | Pre-commit validation ledger: Shows row number, parsed record, Valid/Error status, and failure causes. |
| **AI Extraction Status** | `QLabel` (`#HintLabel`) | Automatic (PDF import) | Feedback indicator displaying the count of fields successfully extracted by Qwen-VL from unstructured PDFs. |
| **Commit to Database Button** | `QPushButton` (`#PrimaryButton`) | Mandatory (DB Transaction) | Executes an atomic database transaction importing all validated records; rolls back automatically on conflict. |

---

#### 2.5.3. User Management Page

> **Functional Description:** Administrative security console (`PageKey.USERS`) for managing staff accounts, enforcing 3-tier Role-Based Access Control (`ADMIN`, `INSPECTOR`, `REVIEWER` per `D-027`), credentials resets, and account activation flags.

> **[NOTE FOR YOU TO FILL IN / INSERT WIREFRAME OR ACTUAL SCREENSHOT HERE]:**
> *Capture a screenshot of the User Management console here. Suggested filename: `fig_2_5_3_users_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Users List Table** | `DataTable` (`QTableWidget`) | Mandatory (Single selection) | Displays registered accounts: Username, Display Name, Role, Active Status, and Last Login. |
| **Create User Button** | `QPushButton` (`#PrimaryButton`) | Optional (Interactive) | Opens dialog to provision a new workstation user account. |
| **Full Name Field** | `QLineEdit` (`#FormField`) | Mandatory (User info) | Real name of the staff member (e.g., `Vu Ha Ninh`). |
| **Username Field** | `QLineEdit` (`#FormField`) | Mandatory (Unique username) | Unique alphanumeric username for signing in. |
| **Password & Confirm** | `QLineEdit` (Password Mode) | Mandatory (Password input) | Secure password input fields. |
| **Role Selection Combo** | `QComboBox` (`#FormCombo`) | Mandatory (Role dropdown) | Assigns one of 3 roles: `Administrator` (Full access), `Inspector` (Workstation), `Reviewer` (Adjudication). |
| **Active Status Toggle** | `QCheckBox` (`Account Active`) | Mandatory (Boolean toggle) | Toggles active status; allows instant revocation of permissions when an employee departs. |
| **Save User Button** | `QPushButton` (`#PrimaryButton`) | Mandatory (Interactive) | Commits user account attributes to the `users` database table. |

---

#### 2.5.4. System & LAN Connection Settings Page

> **Functional Description:** Infrastructure setup console (`src/agroscan/ui/pages/settings_page.py` - `D-016`, `D-028`). Configures distributed 2-tier LAN architecture parameters: PostgreSQL host IP, Qwen-VL REST URL, SMB shared folder path, workstation identifier, and physical video capture device. Includes non-blocking background connection tests (`_CheckTask` on `QThreadPool`) to keep the UI fully responsive.

```
+----------------------------------------------------------------------------------------------------+
| Settings                                                                                           |
| Configure workstation hardware, server connections, and storage.                                   |
+----------------------------------------------------------------------------------------------------+
| DATABASE SERVER (PostgreSQL on LAN Server)                                                         |
| Server IP / Host:  [ 192.168.1.10             ]   Port:     [ 5432       ]                         |
| Database Name:     [ agroscan                 ]   User:     [ agroscan   ]                         |
| [ Test Connection ]   ✔ Port 5432 is open and reachable on 192.168.1.10.                           |
+----------------------------------------------------------------------------------------------------+
| AI SERVICE (Qwen-VL REST on LAN Server)                                                            |
| Service URL:       [ http://192.168.1.10:8000 ]   Timeout:  [ 30 s       ]                         |
| [ Test Connection ]   ✔ AI service responded in 120 ms (qwen2.5-vl-7b ready).                      |
+----------------------------------------------------------------------------------------------------+
| IMAGE STORAGE (Windows SMB Share on Server)                                                        |
| Folder UNC Path:   [ \\192.168.1.10\AgroScan_Data                 ]  [ Browse… ]                   |
| [ Test Access ]       ✔ Wrote and verified canary file successfully.                               |
+----------------------------------------------------------------------------------------------------+
| WORKSTATION HARDWARE                                                                               |
| Station Identifier:[ STATION-01               ]                                                    |
| Camera Device:     [ USB Industrial HD Camera 01 (1920x1080)   v ]                                 |
+----------------------------------------------------------------------------------------------------+
|                                                                    [ Revert ]  [ Save Settings ]   |
+----------------------------------------------------------------------------------------------------+
```

> **[NOTE FOR YOU TO FILL IN / INSERT WIREFRAME OR ACTUAL SCREENSHOT HERE]:**
> *Capture a screenshot of the Settings page in the running app here. Suggested filename: `fig_2_5_4_settings_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **DB Host / IP** | `QLineEdit` (`#FormField`) | Mandatory (IP address) | Network IP of the central PostgreSQL host in the LAN (`D-014`). |
| **DB Port** | `QSpinBox` (`#FormSpin`) | Mandatory (1..65535) | Database service port (default: `5432`). |
| **DB Name & User** | `QLineEdit` (`#FormField`) | Mandatory (Credentials) | Target database name and authorized database username. |
| **Test DB Connection** | `QPushButton` (`#SecondaryButton`) | Optional (Background task) | Probes TCP connectivity to PostgreSQL on a background worker thread (`_CheckTask`). |
| **AI Service URL** | `QLineEdit` (`#FormField`) | Mandatory (HTTP Endpoint) | HTTP base URL of the Qwen-VL Vision-Language model on the LAN server (`D-017`). |
| **AI Timeout Field** | `QSpinBox` (`#FormSpin`) | Mandatory (1..120 sec) | Maximum allowable duration to wait for deep image inference before timeout. |
| **Test AI Connection** | `QPushButton` (`#SecondaryButton`) | Optional (Background task) | Queries the AI service health endpoint and measures latency without freezing the UI. |
| **SMB Storage Path** | `QLineEdit` (`#FormField`) | Mandatory (UNC Path) | Windows Shared folder path for storing official raw evidence images (`D-018` e.g., `\\192.168.1.10\AgroScan_Data`). |
| **Browse Folder Button** | `QPushButton` (`#SecondaryButton`) | Optional (File dialog) | Opens a native folder selection dialog to browse network directories. |
| **Test Storage Access** | `QPushButton` (`#SecondaryButton`) | Optional (Background task) | Writes, verifies, and removes a temporary canary file to validate read/write permissions. |
| **Station Identifier** | `QLineEdit` (`#FormField`) | Mandatory (Unique Station ID) | Workstation name stored in session metadata (e.g., `STATION-01`). |
| **Camera Device Selector**| `QComboBox` (`#FormCombo`) | Mandatory (Hardware list) | Dropdown listing active physical cameras enumerated via `QMediaDevices`. |
| **Save Settings Button** | `QPushButton` (`#PrimaryButton`) | Mandatory (Interactive) | Saves configuration to `app_settings.json` and updates active runtime parameters immediately. |

---

## 3. Design System & Styling Conventions

The AgroScan desktop application strictly adheres to a modular Qt Style Sheets (QSS) design system (`src/agroscan/ui/styles/dark_theme.qss` and `light_theme.qss`), engineered for high readability and reduced eye strain during extended warehouse shifts:
- **Core Color Palette:**
  - Main Background (`Background`): `#0F172A` (Slate 900 - Industrial Dark Mode) / `#F8FAFC` (Slate 50 - Light Mode).
  - Surface Cards (`Surface / Cards`): `#1E293B` (Slate 800) with subtle borders `#334155`.
  - Primary Brand Accent (`Primary Accent`): `#10B981` (Emerald 500 - Fresh Produce Green) for primary triggers: capture, start inspection, and confirm.
  - Warning Accent (`Warning`): `#F59E0B` (Amber 500) for pending reviews and elevated uncertainty warnings.
  - Critical / Rejection Accent (`Danger / Critical`): `#EF4444` (Red 500) for severe defects, rejection decisions, and discard triggers.
- **Typography Standards:** Utilizes the variable geometric typeface **Inter Variable** (`src/agroscan/ui/resources/fonts/Inter-Variable.ttf`), optimized for rapid legibility of numerical metrics, barcodes, and status indicators on high-resolution workstation monitors.
- **Input & Keyboard Workflow Standards:** All barcode-centric intake screens (Box Intake, Live Inspection, Assessment Result) automatically focus their barcode input fields (`Auto-focus`), allowing warehouse operators to point and pull the trigger on handheld USB 2D scanners without having to touch the workstation mouse or keyboard.

---

> **END OF USER INTERFACE DESIGN SPECIFICATION (C2SE.07 - AGROSCAN)**
> *This document is stored at: `Prompt, Mindset, Rule/07_C2SE07_User_Interface_Design_AgroScan_EN.md`.*

