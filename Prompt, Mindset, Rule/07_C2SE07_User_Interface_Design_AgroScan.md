# C2SE.07 — USER INTERFACE DESIGN SPECIFICATION
## DỰ ÁN: HỆ THỐNG KIỂM TRA CHẤT LƯỢNG NÔNG SẢN BÁN TỰ ĐỘNG BẰNG TRÍ TUỆ NHÂN TẠO (AGROSCAN)
### AI-Powered Semi-Automated Multi-Category Goods Inspection System

---

## PROJECT INFORMATION

| Thuộc tính | Chi tiết |
|---|---|
| **Project Acronym** | **AgroScan** |
| **Project Title** | AI-Powered Semi-Automated Multi-Category Goods Inspection System |
| **Start Date** | 21 Aug 2026 |
| **End Date** | 12 Dec 2026 *(hoặc ngày nghiệm thu thực tế - [CHÚ THÍCH: ĐIỀN HOẶC ĐIỀU CHỈNH NGÀY KẾT THÚC DỰ ÁN])* |
| **Lead Institution** | Trường Đào tạo Quốc tế (International School), Đại học Duy Tân |
| **Project Mentor** | ThS. Huỳnh Bá Diệu |
| **Scrum Master / Project Leader** | Phạm Lê Vinh<br>Email: phamlevinh2011@gmail.com<br>Tel: 0901299871 |
| **Partner Organization** | Đại học Duy Tân (Duy Tan University) |
| **Project Repository / Web URL** | *[CHÚ THÍCH: ĐIỀN ĐƯỜNG DẪN REPO GITHUB HOẶC URL NỘI BỘ NẾU CÓ]* |

### Danh sách thành viên nhóm phát triển (Development Team)

| MSSV (Student ID) | Họ và Tên (Full Name) | Email | Số điện thoại | Vai trò chính trong dự án |
|---|---|---|---|---|
| 28211102597 | Phạm Lê Vinh | phamlevinh2011@gmail.com | 0901299871 | Scrum Master, Core Backend & AI Architecture |
| 28211105939 | Vũ Hà Ninh | vuhaninh20102004@gmail.com | 0352637790 | Team Member, Desktop UI/UX & PySide6 Developer |
| 28219006221 | Đào Tiến Dũng | dungdao150@gmail.com | 0559751466 | Team Member, Computer Vision & YOLO Integration |
| 28211141406 | Nguyễn Đình Vinh Khang | khanglucky@gmail.com | 0704667333 | Team Member, Data Engineering, Reports & Storage |
| 28211138343 | Lê Huy Hoàng | hoangdepzai462004@gmail.com | 0938490563 | Team Member, System QA, Testing & Validation |

---

## DOCUMENT APPROVALS

Tài liệu này yêu cầu chữ ký phê duyệt từ các thành viên chủ chốt và Giảng viên hướng dẫn trước khi tiến hành nghiệm thu giao diện phần mềm.

| Họ và tên & Vai trò | Chữ ký (Signature) | Ngày ký (Date) |
|---|---|---|
| **ThS. Huỳnh Bá Diệu**<br>Project Mentor / Giảng viên hướng dẫn | *[CHÚ THÍCH: KÝ TÊN KHI IN RA]* | *[CHÚ THÍCH: ĐIỀN NGÀY DUYỆT]* |
| **Phạm Lê Vinh** (MSSV: 28211102597)<br>Scrum Master / Project Leader | *[CHÚ THÍCH: KÝ TÊN KHI IN RA]* | *[CHÚ THÍCH: ĐIỀN NGÀY]* |
| **Vũ Hà Ninh** (MSSV: 28211105939)<br>Team Member / UI Lead | *[CHÚ THÍCH: KÝ TÊN KHI IN RA]* | *[CHÚ THÍCH: ĐIỀN NGÀY]* |
| **Đào Tiến Dũng** (MSSV: 28219006221)<br>Team Member | *[CHÚ THÍCH: KÝ TÊN KHI IN RA]* | *[CHÚ THÍCH: ĐIỀN NGÀY]* |
| **Nguyễn Đình Vinh Khang** (MSSV: 28211141406)<br>Team Member | *[CHÚ THÍCH: KÝ TÊN KHI IN RA]* | *[CHÚ THÍCH: ĐIỀN NGÀY]* |
| **Lê Huy Hoàng** (MSSV: 28211138343)<br>Team Member | *[CHÚ THÍCH: KÝ TÊN KHI IN RA]* | *[CHÚ THÍCH: ĐIỀN NGÀY]* |

---

## DOCUMENT METADATA & REVISION HISTORY

| Thông tin tài liệu | Chi tiết |
|---|---|
| **Document Title** | User Interface Design Document (Tài liệu Thiết kế Giao diện Người dùng) |
| **Document Identifier** | C2SE.07_User_Interface_Design_AgroScan_ver1.2 |
| **Target System** | AgroScan Industrial Workstation (Desktop Client on Windows 10/11) |
| **UI Framework** | PySide6 (Qt for Python 6.x) with Custom Modular QSS (Dark/Light Mode) |

### Lịch sử sửa đổi (Revision History)

| Version | Ngày (Date) | Tác giả (Author) | Mô tả nội dung thay đổi (Summary of Changes) |
|---|---|---|---|
| **1.0** | 15/09/2026 | Nhóm phát triển AgroScan | Khởi tạo cấu trúc tài liệu UI Design theo mẫu đặc tả C2SE.07. Phác thảo wireframe cơ bản của màn hình Đăng nhập và Màn hình Kiểm định Camera. |
| **1.1** | 10/10/2026 | Nhóm phát triển AgroScan | Cập nhật cấu trúc màn hình theo quy trình 12 bước nghiệp vụ thu mua công nghiệp. Thêm thông số kỹ thuật chi tiết cho trang Box Intake (quét Barcode/QR) và Catalog & Criteria Editor. |
| **1.2** | 06/11/2026 | Nhóm phát triển AgroScan | Hoàn thiện toàn bộ đặc tả chi tiết giao diện theo mã nguồn thực tế: Đồng bộ kiến trúc điều hướng theo `PageKey` và phân quyền 3 vai trò (Admin, Inspector, Reviewer); đặc tả bảng kết quả VLM JSON Schema 1.0 (Qwen-VL); tích hợp quy tắc bảo toàn bằng chứng ảnh tĩnh (SHA-256); bổ sung hộp thoại in tem QR chuẩn ISO/IEC 18004. |

---

## 1. Introduction (Giới thiệu)

### 1.1. Purpose (Mục đích)
Tài liệu Đặc tả Thiết kế Giao diện Người dùng (User Interface Design Document - UIDD) này được biên soạn nhằm:
1. **Mô tả chi tiết và trực quan toàn bộ các màn hình, luồng tương tác, thành phần điều khiển (widgets) và phản hồi hệ thống** của ứng dụng máy trạm **AgroScan** (Desktop Application trên nền tảng PySide6/Qt).
2. **Thiết lập chuẩn mực giao diện nhất quán (Design System & QSS Architecture):** Định nghĩa rõ các kiểu nút bấm, trường nhập liệu, bảng dữ liệu, nhãn trạng thái (Status Badges), biểu tượng cảnh báo và cơ chế xử lý lỗi tức thời (Inline Error Handling) phù hợp môi trường vận hành trạm kiểm định thực tế tại kho hàng.
3. **Làm tài liệu tham chiếu kỹ thuật thống nhất giữa các nhóm phát triển:** Giúp lập trình viên giao diện (Frontend/Qt), kỹ sư xử lý ảnh/AI (Computer Vision), kỹ sư Backend (Database/API) và đội ngũ Kiểm thử (QA/QC) hiểu rõ trạng thái hiển thị, dữ liệu đầu vào/đầu ra và các quy tắc kiểm tra tính hợp lệ trên từng màn hình.
4. **Cung cấp bằng chứng nghiệm thu (Acceptance Baseline):** Đảm bảo hệ thống khi triển khai đáp ứng đầy đủ các quyết định kiến trúc đã thống nhất (`DECISIONS.md`), ràng buộc nghiệp vụ (`PROJECT.md`) và tiến độ triển khai thực tế (`PROGRESS.md`).

### 1.2. Scope (Phạm vi)
Tài liệu bao trùm giao diện ứng dụng máy trạm cục bộ của AgroScan kết nối máy chủ LAN, phục vụ đầy đủ 3 nhóm đối tượng người dùng với quyền hạn riêng biệt:
- **Nhân viên kiểm định tại trạm (Inspector):** Thao tác nhanh với máy quét mã vạch 2D USB/QR, theo dõi camera kiểm định thời gian thực, chụp ảnh bằng chứng gốc (SHA-256), gửi kết quả đề xuất sang hàng đợi chờ duyệt.
- **Kiểm duyệt viên (Reviewer):** Đăng nhập từ bất kỳ máy tính nào trong mạng nội bộ (LAN) để rà soát danh sách kiện hàng "Pending Review", kiểm tra ảnh tĩnh bằng chứng độ phân giải cao, xem nhận xét chuyên sâu từ mô hình thị giác lớn (Qwen-VL) và đưa ra quyết định cuối cùng (PASS, FAIL hoặc RE-INSPECT).
- **Quản trị viên hệ thống (Administrator):** Quản lý danh mục hàng hóa, gắn file mô hình YOLO chuyên hóa theo từng loại quả, cấu hình ngưỡng lỗi và điều kiện từ chối lập tức; quản lý tài khoản người dùng; nhập dữ liệu từ tệp Excel/CSV; và thiết lập kết nối mạng (PostgreSQL IP, Qwen-VL REST URL, thư mục chia sẻ ảnh SMB).

Ngôn ngữ hiển thị trên giao diện hệ thống (menu, nhãn, nút bấm, thông báo trạng thái và tiêu đề báo cáo) được chuẩn hóa bằng **Tiếng Anh chuyên ngành Logistics/QC** theo Quyết định `D-013`, đảm bảo tính chuyên nghiệp và tiêu chuẩn hóa quốc tế.

---

## 2. Interface Design (Chi tiết thiết kế giao diện)

Hệ thống giao diện AgroScan được tổ chức thành 5 phân hệ chức năng tương ứng với vòng đời vận hành của hệ thống:
- **2.1. Common Layout & Application Shell:** Khung giao diện dùng chung, thanh điều hướng phân quyền, thanh trạng thái và màn hình chờ chuyển trạng thái.
- **2.2. Authentication & Pre-login Configuration:** Đăng nhập, chuyển vai trò demo nhanh và hộp thoại cấu hình mạng LAN trước khi vào hệ thống.
- **2.3. Operations Module (Phân hệ Tác nghiệp & Kiểm định):** Tổng quan ca làm việc (Dashboard), tiếp nhận kiện hàng (Box Intake), in tem QR (QrLabelDialog), camera kiểm định trực tiếp (Live Inspection), phân tích sâu qua AI (VLM Result Panel), kết quả đánh giá tự động (Assessment Result), và hàng đợi phê duyệt (Review Queue).
- **2.4. Records Module (Phân hệ Tra cứu & Báo cáo):** Tra cứu lịch sử kiểm tra (Inspection History), xem chi tiết biên bản kiểm tra (Record Detail Widget) và thống kê báo cáo (Reports & Analytics).
- **2.5. Administration Module (Phân hệ Quản trị hệ thống):** Thiết lập danh mục & tiêu chí chất lượng (Catalog & Criteria), nhập dữ liệu hàng loạt (Data Import), quản trị người dùng (Users Management) và cấu hình hệ thống (Settings).

---

### 2.1. Common Layout & Application Shell

#### 2.1.1. Main Window Shell & Navigation Sidebar (Khung cửa sổ chính & Thanh điều hướng phân quyền)

> **Mô tả chức năng:** Khung vỏ chính (`MainWindow`) bao bọc toàn bộ ứng dụng sau khi người dùng xác thực thành công. Thanh điều hướng bên trái (`Sidebar`) áp dụng cơ chế phân quyền động (`Dynamic Role-Based UI` - `D-032`): tự động lọc và chỉ hiển thị các mục chức năng mà vai trò hiện tại có quyền truy cập theo cấu hình `PAGE_SPECS` trong `navigation.py`. Các trang ngoài quyền hạn bị ẩn hoàn toàn để tối ưu bảo mật.

```
+----------------------------------------------------------------------------------------------------+
| AgroScan [WORKSTATION - STATION-01]               AgroScan / Operations / Box Intake               |
|                                                     [Pham Le Vinh]  [ROLE: INSPECTOR]   [ Logout ] |
+------------------------------------+---------------------------------------------------------------+
| OPERATIONS                         |                                                               |
|   [x] Dashboard                    |                                                               |
|   [ ] Box Intake                   |                                                               |
|   [ ] Review Queue (Reviewer/Admin)|                 <NỘI DUNG TRANG ĐANG CHỌN>                    |
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

> **[CHÚ THÍCH CHO BẠN ĐIỀN VÀO / CHÈN ẢNH WIREFRAME HOẶC SCREENSHOT THỰC TẾ]:**
> *Hãy chụp ảnh màn hình ứng dụng thực tế hoặc chèn ảnh thiết kế giao diện thanh Sidebar và Header của MainWindow tại đây. Đặt tên ảnh: `fig_2_1_1_main_window_shell.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **App Branding & Logo** | `QLabel` (`#AppTitle`, `#StationBadge`) | Cố định (Read-only) | Hiển thị thương hiệu "AgroScan" và tên mã trạm làm việc hiện tại (ví dụ: `STATION-01`) giúp nhận diện điểm kiểm định trong kho. |
| **Nav Section: OPERATIONS** | `QLabel` (`#NavSectionLabel`) | Cố định (Read-only) | Tiêu đề nhóm chức năng tác nghiệp hàng ngày (Dashboard, Box Intake, Review Queue). |
| **Nav Button: Dashboard** | `QPushButton` (`.NavButton`) | Bắt buộc (Tất cả vai trò) | Chuyển nhanh về màn hình tổng quan thống kê kiểm định trong ngày. |
| **Nav Button: Box Intake** | `QPushButton` (`.NavButton`) | Bắt buộc (Admin, Inspector) | Mở màn hình tiếp nhận kiện hàng và quét mã QR barcode bằng máy đọc. |
| **Nav Button: Review Queue** | `QPushButton` (`.NavButton`) | Điều kiện (Admin, Reviewer) | Mở danh sách các phiên kiểm định đang ở trạng thái `PENDING_REVIEW` chờ duyệt. |
| **Nav Section: RECORDS** | `QLabel` (`#NavSectionLabel`) | Cố định (Read-only) | Tiêu đề nhóm chức năng hồ sơ dữ liệu (Inspection History, Reports). |
| **Nav Button: History** | `QPushButton` (`.NavButton`) | Bắt buộc (Tất cả vai trò) | Mở trang tra cứu và lọc toàn bộ lịch sử các phiên kiểm định đã thực hiện. |
| **Nav Button: Reports** | `QPushButton` (`.NavButton`) | Bắt buộc (Tất cả vai trò) | Mở màn hình biểu đồ phân tích tỷ lệ đạt/hỏng và xuất báo cáo PDF/Excel. |
| **Nav Section: ADMINISTRATION** | `QLabel` (`#NavSectionLabel`) | Điều kiện (Chỉ Admin) | Nhóm chức năng quản trị hệ thống, tự động ẩn hoàn toàn nếu đăng nhập vai trò Inspector hoặc Reviewer (`D-032`). |
| **Nav Button: Data Import** | `QPushButton` (`.NavButton`) | Điều kiện (Chỉ Admin) | Mở chức năng nhập danh sách đơn hàng, sản phẩm và tiêu chuẩn từ Excel/CSV/PDF. |
| **Nav Button: Catalog & Criteria** | `QPushButton` (`.NavButton`) | Điều kiện (Chỉ Admin) | Mở trang biên tập danh mục sản phẩm, gán tệp model YOLO và thiết lập ngưỡng kiểm định lỗi. |
| **Nav Button: Users** | `QPushButton` (`.NavButton`) | Điều kiện (Chỉ Admin) | Mở trang quản trị tài khoản nhân viên, đặt mật khẩu và phân quyền vai trò. |
| **Nav Button: Settings** | `QPushButton` (`.NavButton`) | Điều kiện (Chỉ Admin) | Mở trang cấu hình tham số hệ thống, kết nối cơ sở dữ liệu LAN và dịch vụ AI. |

---

#### 2.1.2. Top Header & User Status Bar (Thanh trạng thái đầu trang, thông tin tài khoản & Đăng xuất)

> **Mô tả chức năng:** Nằm ở góc trên cùng bên phải của giao diện làm việc, hiển thị đường dẫn phân cấp trang hiện tại (Breadcrumbs), thông tin định danh người dùng đang đăng nhập, nhãn huy hiệu vai trò phân màu đặc trưng và nút Đăng xuất an toàn.

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Breadcrumbs Path** | `QLabel` (`#BreadcrumbLabel`) | Cố định (Dynamic text) | Hiển thị ngữ cảnh vị trí trang hiện tại (ví dụ: `AgroScan / Operations / Live Inspection`). |
| **User Full Name** | `QLabel` (`#UserLabel`) | Cố định (Dynamic text) | Tên hiển thị của nhân viên đang đăng nhập phiên làm việc (ví dụ: `Pham Le Vinh`). |
| **Role Badge** | `StatusBadge` (`role="admin\|inspector\|reviewer"`) | Cố định (Dynamic text & QSS color) | Huy hiệu hiển thị vai trò với màu sắc tương ứng: Tím/Xanh cho Admin, Xanh lam cho Inspector, Vàng cam cho Reviewer. |
| **Logout Button** | `QPushButton` (`#LogoutButton`) | Bắt buộc (Interactive) | Thực hiện đăng xuất khỏi hệ thống. Nếu phiên kiểm định chưa hoàn tất đang mở, hiển thị hộp thoại xác nhận cảnh báo trước khi hủy bỏ phiên (`_confirm_discard_active_session`). |

---

#### 2.1.3. Loading & Transition Screen (Màn hình chuyển trạng thái nạp dữ liệu nặng)

> **Mô tả chức năng:** Hiển thị lớp phủ làm mờ mượt mà (Fade Overlay) kèm vòng quay vô cực (`QProgressIndicator`) và thông điệp tiến trình khi người dùng chuyển sang các trang xử lý dữ liệu nặng hoặc truy vấn mạng LAN (`is_heavy=True` trong `navigation.py` như Review Queue, History, Reports).

> **[CHÚ THÍCH CHO BẠN ĐIỀN VÀO / CHÈN ẢNH WIREFRAME HOẶC SCREENSHOT THỰC TẾ]:**
> *Hãy chụp ảnh màn hình hoặc chèn mockup lớp phủ LoadingScreen tại đây. Đặt tên ảnh: `fig_2_1_3_loading_screen.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Overlay Background** | `QWidget` (`#LoadingOverlay`) | Bán trong suốt | Lớp nền mờ ngăn chặn người dùng bấm đúp hoặc thao tác chồng chéo trong lúc nạp dữ liệu. |
| **Animated Spinner** | `LoadingSpinnerWidget` | Tự động quay | Vòng xoay tiến trình đồ họa vector mượt mà với tông màu xanh chủ đạo của hệ thống. |
| **Loading Title** | `QLabel` (`#LoadingTitle`) | Cố định (Dynamic text) | Tiêu đề tác vụ đang nạp (ví dụ: `"Loading Review Queue..."`). |
| **Loading Subtitle / Progress Note** | `QLabel` (`#LoadingSubtitle`) | Tùy chọn (Dynamic text) | Thông báo chi tiết trạng thái (ví dụ: `"Fetching pending records from LAN server..."`). |

---

### 2.2. Authentication & Pre-login Configuration

#### 2.2.1. User Login Dialog (Cửa sổ đăng nhập & Chuyển vai trò nhanh Demo)

> **Mô tả chức năng:** Hộp thoại xác thực người dùng đầu vào (`src/agroscan/ui/pages/login_dialog.py`). Hỗ trợ nhập Tên người dùng và Mật khẩu chuẩn xác thực Bearer Token HMAC-SHA256 (`D-027`). Đồng thời cung cấp 3 nút bấm chuyển nhanh vai trò (Admin, Inspector, Reviewer) để phục vụ chấm điểm và trình diễn đồ án thuận tiện nhất. Cung cấp liên kết mở nhanh cài đặt mạng trước khi đăng nhập.

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
|   | [⚠ Invalid username or password.]  (ẩn khi hợp lệ)        |   |
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

> **[CHÚ THÍCH CHO BẠN ĐIỀN VÀO / CHÈN ẢNH WIREFRAME HOẶC SCREENSHOT THỰC TẾ]:**
> *Hãy chụp ảnh màn hình hộp thoại đăng nhập thực tế của AgroScan tại đây. Đặt tên ảnh: `fig_2_2_1_login_dialog.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Workstation Header** | `QLabel` (`#DialogTitle`, `#DialogSubtitle`) | Cố định (Read-only) | Hiển thị tiêu đề ứng dụng "AgroScan" và phân định chế độ hoạt động máy trạm. |
| **Demo Mode Badge** | `QLabel` (`#MockBadge`) | Cố định (Visual tag) | Huy hiệu màu vàng nhạt báo hiệu hệ thống hỗ trợ tài khoản demo phục vụ kiểm thử. |
| **Username Field** | `QLineEdit` (`#UsernameField`) | Bắt buộc (User input) | Ô nhập tài khoản người dùng (ví dụ: `admin`, `inspector`, `reviewer`). Có placeholder hướng dẫn. |
| **Password Field** | `QLineEdit` (`#PasswordField`) | Bắt buộc (User input) | Ô nhập mật khẩu với chế độ ẩn ký tự (`EchoMode.Password`). |
| **Inline Error Message** | `QLabel` (`#InlineErrorLabel`) | Tự động (Ẩn/Hiện) | Cảnh báo chữ đỏ khi sai thông tin xác thực, tài khoản bị khóa hoặc mất kết nối DB. Tự ẩn khi người dùng gõ lại phím. |
| **Sign In Button** | `QPushButton` (`#PrimaryButton`) | Bắt buộc (Interactive) | Nút bấm gửi yêu cầu xác thực. Kích hoạt phím tắt `Enter`. |
| **Quick Demo: Admin** | `QPushButton` (`.QuickLoginButton`) | Tùy chọn (One-click) | Điền sẵn tài khoản Admin (`admin`/`admin123`) và đăng nhập thẳng vào hệ thống với toàn quyền quản trị. |
| **Quick Demo: Inspector** | `QPushButton` (`.QuickLoginButton`) | Tùy chọn (One-click) | Điền sẵn tài khoản Kiểm định viên (`inspector`/`insp123`) để mở luồng tác nghiệp camera tại trạm. |
| **Quick Demo: Reviewer** | `QPushButton` (`.QuickLoginButton`) | Tùy chọn (One-click) | Điền sẵn tài khoản Kiểm duyệt viên (`reviewer`/`rev123`) để mở luồng phê duyệt hàng chờ. |
| **Connection Settings Link** | `QPushButton` (`#LinkButton`) | Tùy chọn (Interactive) | Mở hộp thoại `ConnectionSettingsDialog` để cấu hình địa chỉ IP máy chủ trước khi đăng nhập (`D-028`). |

---

#### 2.2.2. Pre-login Connection Settings Dialog (Cửa sổ cấu hình mạng LAN trước khi đăng nhập)

> **Mô tả chức năng:** Cho phép kỹ thuật viên thiết lập thông số kết nối tới máy chủ trung tâm trong mạng LAN ngay từ màn hình đăng nhập (không yêu cầu phải có tài khoản trước) để thuận tiện di chuyển laptop giữa các kho hàng khác nhau (`D-028`).

> **[CHÚ THÍCH CHO BẠN ĐIỀN VÀO / CHÈN ẢNH WIREFRAME HOẶC SCREENSHOT THỰC TẾ]:**
> *Hãy chụp ảnh màn hình hộp thoại Connection Settings Dialog tại đây. Đặt tên ảnh: `fig_2_2_2_connection_settings_dialog.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **PostgreSQL Host IP** | `QLineEdit` (`#FormField`) | Bắt buộc (IP/Hostname) | Địa chỉ IP của máy chủ cơ sở dữ liệu PostgreSQL trong mạng LAN (ví dụ: `192.168.1.10`). |
| **PostgreSQL Port** | `QSpinBox` (`#FormSpin`) | Bắt buộc (1–65535) | Cổng kết nối PostgreSQL (mặc định: `5432`). |
| **Test DB Connection Button** | `QPushButton` (`#SecondaryButton`) | Tùy chọn (Interactive) | Thực hiện kiểm tra ping mở cổng TCP socket tới máy chủ DB và hiển thị trạng thái Ok/Lỗi ngay lập tức. |
| **Qwen-VL Service URL** | `QLineEdit` (`#FormField`) | Bắt buộc (URL format) | Đường dẫn API HTTP REST của dịch vụ mô hình thị giác ngôn ngữ trên máy chủ (ví dụ: `http://192.168.1.10:8000`). |
| **AI Timeout (seconds)** | `QSpinBox` (`#FormSpin`) | Bắt buộc (1–120 giây) | Thời gian chờ tối đa khi gửi ảnh yêu cầu phân tích sâu (mặc định: 30 giây). |
| **Test AI Service Button** | `QPushButton` (`#SecondaryButton`) | Tùy chọn (Interactive) | Gửi gói tin HTTP GET health-check tới dịch vụ AI để kiểm tra mức độ sẵn sàng. |
| **SMB Image Folder Path** | `QLineEdit` (`#FormField`) | Bắt buộc (UNC Path) | Đường dẫn thư mục mạng chia sẻ Windows Share (SMB) để lưu trữ ảnh bằng chứng gốc (ví dụ: `\\192.168.1.10\AgroScan_Data`). |
| **Save & Apply Button** | `QPushButton` (`#PrimaryButton`) | Bắt buộc (Interactive) | Lưu toàn bộ thiết lập vào tệp cấu hình máy trạm `app_settings.json` và đóng hộp thoại. |

---

### 2.3. Operations Module (Phân hệ Tác nghiệp & Kiểm định)

#### 2.3.1. Dashboard Page (Trang tổng quan hoạt động kiểm định)

> **Mô tả chức năng:** Trang chủ hiển thị ngay sau khi đăng nhập (`src/agroscan/ui/pages/dashboard_page.py`). Cung cấp 4 thẻ chỉ số KPI tổng hợp nhanh trong ngày làm việc và bảng danh sách các phiên kiểm tra gần nhất với trạng thái cập nhật tự động.

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
| | INS-20261106-0004   | AGS:DH00123-04/10  | Chuối tiêu | PENDING_REVIEW   | —         | 04:12   | |
| | INS-20261106-0003   | AGS:DH00123-03/10  | Chuối tiêu | COMPLETED        | PASS      | 04:05   | |
| | INS-20261106-0002   | AGS:DH00121-01/05  | Táo Fuji   | COMPLETED        | FAIL      | 03:48   | |
| +---------------------+--------------------+------------+------------------+-----------+---------+ |
+----------------------------------------------------------------------------------------------------+
```

> **[CHÚ THÍCH CHO BẠN ĐIỀN VÀO / CHÈN ẢNH WIREFRAME HOẶC SCREENSHOT THỰC TẾ]:**
> *Hãy chụp ảnh màn hình Dashboard thực tế của AgroScan tại đây. Đặt tên ảnh: `fig_2_3_1_dashboard_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Page Header** | `PageHeader` | Cố định (Read-only) | Tiêu đề trang "Dashboard" và phụ đề giải thích hoạt động tổng quan. |
| **Stat Card 1: Today Boxes** | `StatCardWidget` | Tự động (Read-only) | Đếm tổng số kiện/hộp hàng đã được đưa vào quét kiểm tra trong ngày hôm nay. |
| **Stat Card 2: Pending Review** | `StatCardWidget` | Tự động (Read-only, Highlight) | Hiển thị số lượng kiện hàng đang chờ kiểm duyệt viên rà soát và xác nhận quyết định cuối cùng. |
| **Stat Card 3: Passed Boxes** | `StatCardWidget` | Tự động (Read-only, Green) | Tổng số kiện hàng đã được người kiểm duyệt phê duyệt "Đạt" (PASS) chính thức. |
| **Stat Card 4: Failed Boxes** | `StatCardWidget` | Tự động (Read-only, Red) | Tổng số kiện hàng bị kết luận "Không đạt" (FAIL) do vi phạm ngưỡng chất lượng hoặc lỗi nghiêm trọng. |
| **Recent Activity Table** | `DataTable` (`QTableWidget`) | Tự động (Read-only) | Bảng liệt kê 8 phiên kiểm tra gần nhất, gồm các cột: Mã phiên (Session), Mã kiện (Box), Tên sản phẩm, Trạng thái phiên, Kết quả chính thức và Thời gian bắt đầu. |

---

#### 2.3.2. Box Intake Page (Trang tiếp nhận kiện hàng & Quét mã QR Barcode)

> **Mô tả chức năng:** Điểm bắt đầu của quy trình kiểm định hàng hóa (`src/agroscan/ui/pages/box_intake_page.py`). Hỗ trợ tiếp nhận mã kiện hàng từ máy quét mã vạch 2D USB (hoạt động như bàn phím tự gõ mã kèm phím Enter) hoặc tra cứu thủ công theo đơn hàng (`D-019`, `D-020`, `D-021`). Định dạng chuẩn mã QR do AgroScan phát hành: `AGS:<Mã_Đơn>-<Số_Hộp>/<Tổng>`. Tích hợp bộ lọc phân loại 7 mã lỗi quét (kể cả quét nhầm mã vạch bán lẻ EAN-13), cơ chế khử nảy cò quét (debounce 350ms) và nạp sẵn thông số đơn hàng cùng bộ model YOLO tương ứng.

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
| | [ DH00123 · Chuối tiêu · Hợp tác xã Nông nghiệp Sông Hồng   v ]   [ Box  4 / 10 ]  [Load Box]   | |
| +------------------------------------------------------------------------------------------------+ |
| +------------------------------------------------------------------------------------------------+ |
| | BOX INFORMATION                                                                                | |
| | ORDER: DH00123               BOX: 4 of 10                   PRODUCT: Chuối tiêu                | |
| | SUPPLIER: HTX Sông Hồng      EXPECTED QTY: 200 units        YOLO MODEL: banana_defect.onnx     | |
| | [▲ This box already has 1 session(s). Starting creates a re-inspection.] (Ẩn khi quét mới)      | |
| | [ Ghi chú thêm về tình trạng ngoại quan kiện hàng...                                         ] | |
| +------------------------------------------------------------------------------------------------+ |
|                                                    [ Generate / Print QR ]   [Start Inspection →]  |
+----------------------------------------------------------------------------------------------------+
```

> **[CHÚ THÍCH CHO BẠN ĐIỀN VÀO / CHÈN ẢNH WIREFRAME HOẶC SCREENSHOT THỰC TẾ]:**
> *Hãy chụp ảnh màn hình trang Box Intake thực tế của AgroScan tại đây. Đặt tên ảnh: `fig_2_3_2_box_intake_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Active Session Banner** | `QFrame` (`#WarningBanner`) | Tự động (Ẩn/Hiện) | Thông báo khi hệ thống đang có một phiên kiểm định khác dở dang, kèm nút `Resume` để quay lại ngay. |
| **Scan Box Code Field** | `QLineEdit` (`#ScanField`) | Bắt buộc (Auto-focus) | Ô nhập mã QR kiện hàng tự động nhận chuỗi từ máy quét laser 2D. Tích hợp cơ chế tự động gửi khi nhấn Enter. |
| **Scan Error Notice** | `QLabel` (`#InlineErrorLabel`) | Tự động (Ẩn/Hiện) | Báo lỗi chi tiết đối với 7 tình huống sai mã: `INVALID_FORMAT`, `EAN13_RETAIL_BARCODE` (quét nhầm mã bán lẻ), `UNKNOWN_ORDER`, `BOX_INDEX_OUT_OF_RANGE`, `BOX_TOTAL_MISMATCH`, v.v. |
| **Manual Order Combo** | `QComboBox` (`#FormCombo`) | Tùy chọn (Dropdown) | Danh sách chọn thủ công đơn hàng đang chờ tiếp nhận khi máy quét gặp sự cố phần cứng. |
| **Manual Box SpinBox** | `QSpinBox` (`#FormSpin`) | Tùy chọn (1..Total) | Chọn số thứ tự hộp cần kiểm tra trong tổng số hộp của đơn hàng đã chọn. |
| **Load Box Button** | `QPushButton` (`#SecondaryButton`) | Tùy chọn (Interactive) | Nạp thông tin kiện hàng lên giao diện từ lựa chọn thủ công. |
| **Box Info Grid** | `KeyValueGrid` | Cố định (Read-only) | Hiển thị bảng tổng hợp 6 thông số: Mã đơn, Thứ tự hộp, Tên nông sản, Nhà cung cấp, Số lượng dự kiến, và File Model YOLO chuyên biệt sẽ được tự động kích hoạt (`D-024`). |
| **Re-inspection Warning** | `QLabel` (`#WarningNote`) | Tự động (Ẩn/Hiện) | Cảnh báo màu vàng cam khi kiện hàng này đã từng được kiểm tra trước đó; thông báo việc tiếp tục sẽ tạo phiên kiểm tra lại (`Re-inspection`) mà không ghi đè lịch sử cũ (`D-021`). |
| **Session Notes Input** | `QLineEdit` (`#FormField`) | Tùy chọn (User input) | Ghi chú nhanh các đặc điểm vật lý bất thường trước khi đưa lên bàn cân/băng chuyền camera. |
| **Print QR Button** | `QPushButton` (`#SecondaryButton`) | Tùy chọn (Interactive) | Mở hộp thoại `QrLabelDialog` để tạo và in tem mã vạch dán lên thùng hàng. |
| **Start Inspection Button** | `QPushButton` (`#PrimaryButton`) | Bắt buộc (Interactive) | Khởi tạo phiên kiểm định mới, nạp model AI và chuyển thẳng sang màn hình Live Inspection. |

---

#### 2.3.3. QR Label Preview & Print Dialog (Hộp thoại in tem QR chuẩn ISO/IEC 18004)

> **Mô tả chức năng:** Hộp thoại tạo tem nhãn mã vạch kiện hàng (`src/agroscan/ui/components/qr_label_dialog.py`). Sinh đồ họa mã QR thuần Python (`qr_encoder.py`) theo chuẩn quốc tế ISO/IEC 18004, hiển thị thông tin kiện hàng sắc nét và hỗ trợ kết nối máy in tem công nghiệp hoặc xuất tệp hình ảnh/PDF tem nhãn.

> **[CHÚ THÍCH CHO BẠN ĐIỀN VÀO / CHÈN ẢNH WIREFRAME HOẶC SCREENSHOT THỰC TẾ]:**
> *Hãy chụp ảnh màn hình hộp thoại QrLabelDialog tại đây. Đặt tên ảnh: `fig_2_3_3_qr_label_dialog.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **QR Code Canvas** | `QLabel` (Pixmap Display) | Tự động (High-DPI) | Hiển thị ma trận điểm ảnh mã QR chuẩn với mức sửa lỗi L/M, chứa chuỗi ký tự nhận diện `AGS:<Mã_Đơn>-<Hộp>/<Tổng>`. |
| **Label Text Info** | `QVBoxLayout` (`QLabel`) | Tự động (Read-only) | Chứa các dòng chữ in rõ ràng dưới mã QR: Mã đơn hàng, Thứ tự kiện, Tên loại quả, Ngày đóng gói và Nhà cung cấp. |
| **Export PNG Button** | `QPushButton` (`#SecondaryButton`) | Tùy chọn (Interactive) | Lưu tem nhãn ra tệp ảnh PNG chất lượng cao để dán tài liệu hoặc chia sẻ. |
| **Print Label Button** | `QPushButton` (`#PrimaryButton`) | Tùy chọn (Interactive) | Gửi trực tiếp lệnh in tới máy in mã vạch nhiệt tiêu chuẩn kết nối qua cổng USB máy trạm. |
| **Close Button** | `QPushButton` (`#SecondaryButton`) | Bắt buộc (Interactive) | Đóng hộp thoại xem trước tem. |

---

#### 2.3.4. Live Inspection Page (Trang kiểm định trực tiếp qua Camera & YOLO/ByteTrack)

> **Mô tả chức năng:** Màn hình trung tâm của nhân viên kiểm định tại trạm (`src/agroscan/ui/pages/live_inspection_page.py`). Kết nối luồng video trực tiếp từ camera công nghiệp (`QCamera`/`QVideoWidget`) hoặc chế độ giả lập nguồn phát phục vụ demo (`Simulation Feed` - `D-031`). Hiển thị bounding box phát hiện lỗi tức thời từ mô hình YOLO chuyên hóa; ứng dụng thuật toán ByteTrack theo dõi vật thể chống đếm trùng (`D-025`). Tự động tính chỉ số làm mượt (Moving Average) và cung cấp nút chụp ảnh bằng chứng tĩnh có mã băm SHA-256 (`D-026`).

```
+----------------------------------------------------------------------------------------------------+
| Live Inspection                                                        [ IN PROGRESS ] [DEMO MODE] |
| Box AGS:DH00123-04/10 · Chuối tiêu · Order DH00123                                                 |
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
| [Thumb 1 (SHA-256)] [Thumb 2]  (Bấm xem phóng to)   | +----------------------------------------------+
| • Official results computed from still images only. | [ Finish Inspection → ]  [ Discard Session ] |
+-----------------------------------------------------+----------------------------------------------+
```

> **[CHÚ THÍCH CHO BẠN ĐIỀN VÀO / CHÈN ẢNH WIREFRAME HOẶC SCREENSHOT THỰC TẾ]:**
> *Hãy chụp ảnh màn hình trang Live Inspection với khung camera thực tế và bảng kết quả tại đây. Đặt tên ảnh: `fig_2_3_4_live_inspection_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Session Info Header** | `QLabel` (`#PageTitleSmall`, `#PageSubtitle`) | Cố định (Read-only) | Hiển thị thông tin phiên hiện tại: Mã hộp, Tên loại quả đang kiểm tra và Mã đơn hàng cha. |
| **Session Status Badge** | `StatusBadge` (`status="in_progress"`) | Cố định (Visual tag) | Huy hiệu màu xanh biển báo hiệu phiên kiểm định camera đang mở. |
| **Live Camera Viewport** | `QStackedWidget` (`#CameraFrame`) | Bắt buộc (Live Feed) | Hiển thị luồng video 30fps từ camera kết nối trạm. Nếu mất camera, tự động chuyển sang panel cảnh báo "No camera detected" kèm nút "Retry". |
| **Deep Analysis Button** | `QPushButton` (`#SecondaryButton`) | Tùy chọn (Interactive) | Gửi ảnh chụp hiện tại tới máy chủ LAN gọi mô hình đa phương thức Qwen-VL phân tích chuyên sâu (`D-017`). |
| **Capture Evidence Button** | `QPushButton` (`#PrimaryButton`) | Bắt buộc (Interactive) | Nút bấm chụp ảnh tĩnh làm bằng chứng kiểm định chính thức. Tệp ảnh được tính mã băm toàn vẹn SHA-256 và lưu vào thư mục mạng SMB (`D-026`). |
| **Evidence Strip** | `EvidenceStrip` (`QScrollArea`) | Tự động (Thumbnail list) | Dải hiển thị danh sách các ảnh tĩnh đã chụp trong phiên. Nhấp đúp vào ảnh để mở cửa sổ xem chi tiết kích thước đầy đủ. |
| **Realtime Objects Count** | `QLabel` (`#RealtimeValue`) | Tự động (Moving Average) | Hiển thị số lượng quả đang hiện diện ổn định trước ống kính camera theo thuật toán làm mượt 5 khung hình. |
| **Realtime Defect Breakdown** | `QGridLayout` | Tự động (Dynamic stats) | Thống kê số lượng quả theo từng phân lớp nhận diện (ví dụ: Fresh, Bruised, Rotten) dựa trên model YOLO đang nạp. |
| **Next Box Continuous Field** | `QLineEdit` (`#FormField`) | Tùy chọn (Scanner input) | Hỗ trợ luồng quét liên tục (`D-020`): Quét mã kiện tiếp theo sẽ tự động hoàn tất kiện hiện tại chuyển sang "Pending Review" và mở ngay phiên cho kiện mới. |
| **Finish Inspection Button** | `QPushButton` (`#PrimaryButton`) | Bắt buộc (Interactive) | Kết thúc bước quan sát trực tiếp, chuyển sang màn hình đối chiếu kết quả tự động (`AssessmentResultPage`). |
| **Discard Session Button** | `QPushButton` (`#DangerButton`) | Tùy chọn (Cảnh báo đỏ) | Hủy bỏ toàn bộ dữ liệu phiên kiểm tra dở dang này và quay về trang tiếp nhận (có hộp thoại xác nhận). |

---

#### 2.3.5. VLM Deep Analysis Panel - Qwen-VL (Bảng kết quả phân tích thị giác chuyên sâu VLM & OCR nhãn)

> **Mô tả chức năng:** Thành phần giao diện nhúng (`src/agroscan/ui/components/vlm_result_panel.py`) hiển thị kết quả phân tích đa phương thức từ Qwen-VL chạy trên máy chủ LAN (`D-017`), tuân thủ chuẩn hợp đồng dữ liệu `JSON Schema 1.0` (`docs/api/vlm_analysis.schema.json`). Bảng có 4 trạng thái hiển thị rõ rệt: Chờ (Idle), Đang gọi API (Loading với thanh tiến trình), Kết quả hợp lệ (Result với bảng chi tiết khuyết tật và OCR đối chiếu đơn hàng) và Xử lý lỗi (Error với 5 mã lỗi chuyên biệt kèm nút Thử lại).

```
+-------------------------------------------------------------------+
| DEEP ANALYSIS                                       [✔ OK] [MOCK] |
| qwen2.5-vl-7b · 1.4 s · 04:10:12                                  |
+-------------------------------------------------------------------+
| DEFECTS DETECTED (Mô tả khuyết tật)                               |
| Class       Count    Severity       Confidence                    |
| Bruised     3        Minor          84%                           |
| Rotten      1        ▲ Critical     91%                           |
+-------------------------------------------------------------------+
| LABEL OCR (Đọc & đối chiếu nhãn thùng)                            |
| Box Code:     AGS:DH00123-04/10                 (97% - Khớp)      |
| Supplier:     Unknown Packer                    (88% - [≠ Sai lệch])|
|               [≠ Khác khai báo: HTX Sông Hồng]                    |
| Packed Date:  2026-11-04                        (81%)             |
+-------------------------------------------------------------------+
| UNCERTAINTY (Độ bất định đánh giá)                                |
| [▲ MEDIUM · 0.42] - Bị che khuất một phần ở góc thùng             |
+-------------------------------------------------------------------+
| AI OBSERVATIONS & SUGGESTION                                      |
| • Nhận định: Phát hiện vết dập và dấu hiệu úng cuống nghiêm trọng.|
| • Đề xuất: Lật lớp quả phía dưới và kiểm tra thêm 1 ảnh chụp.    |
| (Chỉ mang tính chất tư vấn — không ghi đè quyết định con người)   |
+-------------------------------------------------------------------+
```

> **[CHÚ THÍCH CHO BẠN ĐIỀN VÀO / CHÈN ẢNH WIREFRAME HOẶC SCREENSHOT THỰC TẾ]:**
> *Hãy chụp ảnh màn hình thành phần VlmResultPanel trong ứng dụng tại đây. Đặt tên ảnh: `fig_2_3_5_vlm_result_panel.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **VLM Status Badge** | `StatusBadge` | Tự động (Read-only) | Hiển thị trạng thái phân tích: `OK` (xanh lục), `PARTIAL` (vàng cam), `ERROR` (đỏ). |
| **Execution Metadata** | `QLabel` (`#HintLabel`) | Tự động (Read-only) | Tên model AI (`qwen2.5-vl-7b`), thời gian phản hồi API (`latency_ms`) và thời điểm phân tích. |
| **Defects Analysis Table** | `QGridLayout` (`#VlmValue`) | Tự động (Dynamic) | Danh sách lỗi nhận diện: Tên phân lớp lỗi, Số lượng, Mức độ nghiêm trọng (Minor, Major, Critical màu đỏ đậm) và Độ tin cậy (%). Di chuột vào dòng để xem giải thích chi tiết. |
| **Label OCR Verification** | `QGridLayout` (`#VlmValue`) | Tự động (Comparison) | Trích xuất ký tự trên nhãn dán thùng (Mã kiện, Nhà cung cấp, Ngày đóng gói). Nếu nhà cung cấp đọc được khác với thông tin trên đơn hàng, tự động gắn cờ cảnh báo màu cam `≠ Differs from order`. |
| **Uncertainty Indicator** | `StatusBadge` + `QLabel` | Tự động (Read-only) | Mức độ nghi ngờ của AI (Thấp / Trung bình / Cao kèm điểm số 0.0–1.0) và lý do bất định (ví dụ: do góc chụp tối hoặc quả bị che khuất). |
| **AI Assessment & Suggestion** | `QLabel` (`#VlmValue`) | Tự động (WordWrap) | Nhận xét ngôn ngữ tự nhiên từ Qwen-VL và gợi ý hành động tiếp theo cho nhân viên kiểm tra. |
| **API Error & Retry Block** | `QFrame` (`#VlmErrorPanel`) | Tự động (Khi có lỗi) | Hiển thị mã lỗi cụ thể (`TIMEOUT`, `SERVICE_UNAVAILABLE`, `INVALID_RESPONSE`, `IMAGE_UNUSABLE`) kèm nút `Retry` (Thử lại) nếu lỗi có thể phục hồi. |

---

#### 2.3.6. Assessment Result Page (Trang kết quả đánh giá tự động từ Python Rule Engine)

> **Mô tả chức năng:** Màn hình kết luận kỹ thuật của máy trạm (`src/agroscan/ui/pages/assessment_result_page.py`). Áp dụng công cụ quy tắc logic Python độc lập (`Deterministic Rule Engine` - `D-007`, `D-023`) dựa trên ảnh tĩnh bằng chứng và tiêu chuẩn chất lượng trong DB. Đề xuất kết quả sơ bộ (`AiRecommendation`: PASS, FAIL, hoặc NEEDS_REVIEW). Nhân viên không ra quyết định chủ quan tại đây mà bấm gửi để đẩy hồ sơ vào hàng đợi phê duyệt (`D-020`).

> **[CHÚ THÍCH CHO BẠN ĐIỀN VÀO / CHÈN ẢNH WIREFRAME HOẶC SCREENSHOT THỰC TẾ]:**
> *Hãy chụp ảnh màn hình Assessment Result Page tại đây. Đặt tên ảnh: `fig_2_3_6_assessment_result_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Page Header** | `PageHeader` | Cố định (Read-only) | Tiêu đề trang giải thích rõ kết quả do Rule Engine tính toán tự động. |
| **Record Detail Component** | `RecordDetailWidget` | Cố định (Tích hợp) | Khung xem đầy đủ thông tin phiên: Thông số kiện, ảnh bằng chứng tĩnh, bảng tỷ lệ lỗi so với ngưỡng quy định và kết quả Qwen-VL (nếu có). |
| **Rule Recommendation Badge** | `StatusBadge` | Tự động (Highlight) | Kết quả thuật toán đề xuất: `PASS` (Đạt), `FAIL` (Không đạt - nếu vi phạm tỷ lệ hoặc có lỗi thối hỏng), `NEEDS_REVIEW` (Cần thẩm định kỹ). |
| **Rule Evaluation Reasons** | `QLabel` (`#ValueLabel`) | Tự động (Bullet points) | Danh sách lý do dẫn đến kết luận (ví dụ: `"Tỷ lệ dập 12.5% vượt ngưỡng cho phép 10.0%"`, `"Phát hiện 1 quả thối thuộc danh mục lỗi nghiêm trọng loại bỏ ngay"`). |
| **Next Box Scan Field** | `QLineEdit` (`#FormField`) | Tùy chọn (Scanner input) | Quét kiện tiếp theo để tự động gửi duyệt kiện này và bắt đầu phiên mới ngay lập tức. |
| **Back Button** | `QPushButton` (`#SecondaryButton`) | Tùy chọn (Interactive) | Quay lại màn hình Live Inspection để chụp thêm ảnh hoặc phân tích lại. |
| **Submit for Review Button** | `QPushButton` (`#PrimaryButton`) | Bắt buộc (Interactive) | Gửi toàn bộ hồ sơ dữ liệu phiên kiểm tra vào hàng đợi `PENDING_REVIEW` trên máy chủ LAN (`D-020`). |

---

#### 2.3.7. Review Queue Page (Trang hàng đợi phê duyệt dành cho Kiểm duyệt viên - Reviewer)

> **Mô tả chức năng:** Không gian làm việc chuyên biệt của Kiểm duyệt viên (`Reviewer`) hoặc Quản trị viên (`Admin`) (`src/agroscan/ui/pages/review_queue_page.py`). Màn hình chia đôi (Splitter layout): Bên trái là danh sách các kiện hàng đang chờ duyệt (`PENDING_REVIEW`) từ tất cả các máy trạm gửi về qua mạng LAN; bên phải là khung hồ sơ chi tiết và cụm 3 nút đưa ra quyết định thẩm định cuối cùng (`D-027`, `D-030`).

```
+----------------------------------------------------------------------------------------------------+
| Review Queue                                                                                       |
| Sessions waiting for a reviewer decision. Oldest first.                                            |
+-----------------------------------+----------------------------------------------------------------+
| 3 PENDING SESSIONS                | RECORD DETAIL: INS-20261106-0004                               |
| +-------------------------------+ | Box: AGS:DH00123-04/10 · Product: Chuối tiêu                   |
| |Box Code |Product |AI Rec|Time | | Inspector: Vu Ha Ninh · Station: STATION-01                    |
| |---------|--------|------|-----| |                                                                |
| |DH00123-4|Chuối   |NEEDS |04:12| | [ Evidence Image Thumbnail Strip with SHA-256 Hash ]           |
| |DH00122-1|Táo     |FAIL  |04:08| | [ Detection Breakdown vs Quality Criteria Table ]              |
| |DH00121-5|Xoài    |PASS  |03:55| | [ Qwen-VL Deep Analysis Observations & Label OCR ]             |
| +-------------------------------+ |                                                                |
|                                   | YOUR OFFICIAL DECISION                                         |
|                                   | [ Ghi chú lý do phê duyệt hoặc chỉ đạo kiểm tra lại...       ] |
|                                   | [  PASS (Đạt)  ]  [  FAIL (Hủy bỏ)  ]  [  RE-INSPECT (Khám lại)]|
+-----------------------------------+----------------------------------------------------------------+
```

> **[CHÚ THÍCH CHO BẠN ĐIỀN VÀO / CHÈN ẢNH WIREFRAME HOẶC SCREENSHOT THỰC TẾ]:**
> *Hãy chụp ảnh màn hình trang Review Queue với danh sách hàng chờ và bảng duyệt quyết định tại đây. Đặt tên ảnh: `fig_2_3_7_review_queue_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Pending Count Header** | `QLabel` (`#FormSectionTitle`) | Tự động (Read-only) | Đếm tổng số kiện hàng đang tồn đọng trong hàng đợi cần thẩm định (sắp xếp cũ nhất lên trước). |
| **Queue Table List** | `DataTable` (`QTableWidget`) | Bắt buộc (Single selection) | Bảng chọn danh sách các phiên chờ duyệt, hiển thị: Mã hộp, Tên quả, Đề xuất của AI, Nhân viên kiểm tra và Thời gian. |
| **Record Detail Panel** | `RecordDetailWidget` | Cố định (Scrollable) | Hiển thị toàn bộ bằng chứng pháp lý của phiên đang chọn: Thông tin đơn, ảnh chụp tĩnh bằng chứng, mã băm SHA-256, bảng chi tiết khuyết tật và nhận định từ Qwen-VL. |
| **Reviewer Decision Notes** | `QPlainTextEdit` (`#NotesField`) | Tùy chọn (User input) | Ô nhập lời phê duyệt hoặc chỉ đạo cụ thể của kiểm duyệt viên lưu vĩnh viễn vào nhật ký kiểm toán. |
| **Decision Button: PASS** | `QPushButton` (`#PassButton`) | Bắt buộc (Màu xanh lá) | Xác nhận kiện hàng đạt chuẩn thu mua chất lượng, chuyển trạng thái phiên thành `COMPLETED`. |
| **Decision Button: FAIL** | `QPushButton` (`#DangerButton`) | Bắt buộc (Màu đỏ tươi) | Xác nhận từ chối kiện hàng do không đạt tiêu chuẩn kỹ thuật. |
| **Decision Button: RE-INSPECT** | `QPushButton` (`#SecondaryButton`) | Bắt buộc (Màu xám/cam) | Yêu cầu trạm kiểm định lấy mẫu hoặc quét lại kiện hàng này (`D-030`). |

---

### 2.4. Records Module (Phân hệ Tra cứu & Báo cáo thống kê)

#### 2.4.1. Inspection History Page (Trang tra cứu & Lịch sử kiểm định toàn diện)

> **Mô tả chức năng:** Nơi lưu trữ và tra cứu toàn bộ hồ sơ kiểm định trong quá khứ (`PageKey.INSPECTION_HISTORY`). Cung cấp bộ lọc đa tiêu chí (khoảng thời gian, mã đơn/kiện, sản phẩm, trạng thái, người thực hiện) và hỗ trợ mở xem lại nguyên trạng hồ sơ bằng chứng mà không thể sửa đổi (Read-only audit).

> **[CHÚ THÍCH CHO BẠN ĐIỀN VÀO / CHÈN ẢNH WIREFRAME HOẶC SCREENSHOT THỰC TẾ]:**
> *Hãy chụp ảnh màn hình hoặc thiết kế giao diện trang Inspection History tại đây. Đặt tên ảnh: `fig_2_4_1_inspection_history_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Search Filter Field** | `QLineEdit` (`#FormField`) | Tùy chọn (Search input) | Tìm kiếm tức thời theo mã đơn hàng, mã vạch hộp hoặc tên nhà cung cấp. |
| **Product Category Filter** | `QComboBox` (`#FormCombo`) | Tùy chọn (Dropdown) | Lọc danh sách theo loại nông sản cụ thể (Chuối, Táo, Xoài, v.v.). |
| **Status Filter** | `QComboBox` (`#FormCombo`) | Tùy chọn (Dropdown) | Lọc theo trạng thái xử lý (`ALL`, `IN_PROGRESS`, `PENDING_REVIEW`, `COMPLETED`). |
| **Date Range Pickers** | `QDateEdit` (From / To) | Tùy chọn (Date range) | Lọc các phiên kiểm tra phát sinh trong khoảng thời gian xác định. |
| **History Data Table** | `DataTable` (`QTableWidget`) | Cố định (Multi-column) | Bảng dữ liệu chính hiển thị: Mã phiên, Mã kiện, Sản phẩm, Quyết định kiểm duyệt, Kiểm tra viên, Kiểm duyệt viên và Ngày thực hiện. |
| **View Details Action** | `QPushButton` (`#SecondaryButton`) | Bắt buộc (Interactive) | Mở hộp thoại `RecordDetailWidget` hiển thị toàn vẹn biên bản kiểm tra kèm ảnh bằng chứng gốc. |

---

#### 2.4.2. Inspection Record Detail View (Khung hiển thị chi tiết biên bản kiểm tra & Bằng chứng ảnh SHA-256)

> **Mô tả chức năng:** Khung thành phần độc lập (`src/agroscan/ui/components/record_detail.py`) dùng chung cho cả trang Kết quả đánh giá, Hàng đợi phê duyệt và Lịch sử. Bảo toàn tính toàn vẹn của hồ sơ pháp lý kiểm định hàng hóa theo `PROJECT.md` §5.

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Session Metadata Section** | `KeyValueGrid` | Cố định (Read-only) | Lưới 3 cột thể hiện thông tin: Session ID, Mã hộp, Trạng thái, Sản phẩm, Nhà cung cấp, Trạm kiểm tra, Ngày bắt đầu và Ghi chú ngoại quan. |
| **AI Recommendation Card** | `SectionCard` | Tự động (Read-only) | Huy hiệu đề xuất của thuật toán (PASS/FAIL/NEEDS_REVIEW) kèm danh sách căn cứ logic. |
| **Evidence Image Preview Strip** | `EvidenceStrip` | Bắt buộc (High-res thumbnails) | Danh sách ảnh tĩnh chụp kiện hàng kèm mã băm SHA-256 được tính toán trước khi đưa vào mô hình AI (`D-026`). Cho phép click phóng to ảnh gốc. |
| **Defect vs Criteria Table** | `DataTable` | Tự động (Read-only) | Bảng so sánh 5 cột: Phân lớp lỗi, Số lượng đếm được, Tỷ lệ %, Ngưỡng tối đa cho phép và Đánh dấu lỗi nghiêm trọng loại bỏ ngay (`Critical`). |
| **VLM Analysis Details** | `VlmResultPanel` | Tùy chọn (Ẩn/Hiện) | Khối hiển thị kết quả phân tích sâu từ Qwen-VL (chỉ xuất hiện nếu phiên có gọi phân tích sâu). |
| **Reviewer Decision Card** | `SectionCard` | Tự động (Read-only) | Kết luận chính thức từ người kiểm duyệt: Quyết định (PASS/FAIL/RE-INSPECT), Tên kiểm duyệt viên, Ngày giờ phê duyệt và Lời phê. |

---

#### 2.4.3. Reports & Analytics Page (Trang báo cáo thống kê, biểu đồ chất lượng & Xuất dữ liệu PDF/Excel)

> **Mô tả chức năng:** Cung cấp thông tin phân tích chất lượng nông sản phục vụ cấp quản lý (`PageKey.REPORTS`). Tổng hợp kết quả theo cấp đơn hàng ("8/10 hộp đạt, 1 chờ, 1 không đạt" theo `D-022`), vẽ biểu đồ xu hướng chất lượng và xuất báo cáo đồng nhất sang định dạng PDF và Excel (`D-010`).

> **[CHÚ THÍCH CHO BẠN ĐIỀN VÀO / CHÈN ẢNH WIREFRAME HOẶC SCREENSHOT THỰC TẾ]:**
> *Hãy chụp ảnh màn hình hoặc mockup giao diện Reports & Analytics tại đây. Đặt tên ảnh: `fig_2_4_3_reports_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Report Scope Filter** | `QComboBox` / `QDateEdit` | Bắt buộc (Filter settings) | Chọn phạm vi báo cáo: Theo đợt giao hàng, theo nhà cung cấp hoặc theo khoảng thời gian nhập kho. |
| **Order-Level Summary Cards** | `QHBoxLayout` (`StatCard`) | Tự động (Calculated) | Thể hiện kết quả tổng hợp cấp đơn hàng: Tỷ lệ kiện đạt chuẩn trên tổng kiện đã kiểm tra của đơn hàng (`D-022`). |
| **Quality Breakdown Chart** | `QWidget` (Matplotlib Canvas) | Tự động (Biểu đồ tròn/cột) | Trực quan hóa tỷ lệ các nhóm khuyết tật phổ biến (Dập, Thối, Sâu bệnh, Trầy xước) theo từng loại quả. |
| **Daily Throughput Chart** | `QWidget` (Line Chart) | Tự động (Biểu đồ đường) | Xu hướng năng lực kiểm định của các trạm qua các ngày trong tuần/tháng. |
| **AI Summary Commentary Box** | `QPlainTextEdit` (Read-only) | Tùy chọn (Qwen generated) | Phần văn bản nhận xét tổng quan tình hình chất lượng lô hàng do mô hình AI tổng hợp theo yêu cầu người dùng (`PROJECT.md` §3 bước 10). |
| **Export Excel Button** | `QPushButton` (`#SecondaryButton`) | Bắt buộc (Interactive) | Xuất toàn bộ bảng số liệu chi tiết và chỉ số KPI ra tệp Microsoft Excel (.xlsx) chuẩn mẫu. |
| **Export PDF Report Button** | `QPushButton` (`#PrimaryButton`) | Bắt buộc (Interactive) | Xuất ấn phẩm báo cáo chất lượng chuyên nghiệp định dạng PDF có kèm biểu đồ, bảng kiểm định và mã băm bằng chứng ảnh. |

---

### 2.5. Administration Module (Phân hệ Quản trị hệ thống)

#### 2.5.1. Catalog & Inspection Criteria Editor (Trang quản lý danh mục sản phẩm, Model YOLO & Tiêu chí lỗi)

> **Mô tả chức năng:** Màn hình quản trị cấu hình cốt lõi của AgroScan (`src/agroscan/ui/pages/catalog_page.py`). Cho phép Quản trị viên thêm/sửa sản phẩm, gắn từng loại quả với tệp mô hình YOLO chuyên hóa tương ứng (`D-024` như `banana_defect.onnx`, `apple_defect.onnx`), và thiết lập bảng ngưỡng lỗi cùng cờ vi phạm loại bỏ ngay (`Fail immediately` - `D-023`). Có cơ chế kiểm tra tính hợp lệ dữ liệu chặt chẽ (`catalog_validation.py`) và cảnh báo khi có thay đổi chưa lưu.

```
+----------------------------------------------------------------------------------------------------+
| Catalog & Criteria                                                                     [MOCK DATA] |
| Goods categories, products, their dedicated YOLO model and defect criteria.                         |
+-----------------------------------+----------------------------------------------------------------+
| Category: [ All categories    v ] | Banana · BANANA                                                |
| 3 PRODUCTS                        | [▲ Used by 2 order(s): DH00121, DH00123. Code is read-only]    |
| +-------------------------------+ |                                                                |
| |Code  |Name    |Category|Model | | PRODUCT PROFILE                                                |
| |------|--------|--------|------| | Code:            [ BANANA             ] (Khóa sửa khi đã dùng)  |
| |BANANA|Chuối   |Fruit   |ban...| | Name:            [ Chuối tiêu         ]                           |
| |APPLE |Táo Fuji|Fruit   |app...| | Category:        [ Fruit            v ]                           |
| |MANGO |Xoài Úc |Fruit   |man...| | YOLO Model File: [ banana_defect.onnx ]                           |
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

> **[CHÚ THÍCH CHO BẠN ĐIỀN VÀO / CHÈN ẢNH WIREFRAME HOẶC SCREENSHOT THỰC TẾ]:**
> *Hãy chụp ảnh màn hình trang Catalog & Criteria Editor thực tế của AgroScan tại đây. Đặt tên ảnh: `fig_2_5_1_catalog_criteria_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Category Filter** | `QComboBox` (`#FormCombo`) | Tùy chọn (Dropdown) | Lọc danh sách sản phẩm theo nhóm ngành hàng (Fruit, Vegetable, v.v.). |
| **Product List Table** | `DataTable` (`QTableWidget`) | Bắt buộc (Single selection) | Danh sách sản phẩm: Mã sản phẩm, Tên gọi, Phân loại, Tệp Model AI và Số lượng tiêu chí đang áp dụng. |
| **Add Product Button** | `QPushButton` (`#SecondaryButton`) | Tùy chọn (Interactive) | Tạo mới một mặt hàng nông sản vào danh mục kiểm định. |
| **Product Code Field** | `QLineEdit` (`#FormField`) | Bắt buộc (Regex: `^[A-Z0-9_]+$`) | Mã định danh duy nhất của sản phẩm (ví dụ: `BANANA`). Tự động khóa chế độ chỉ đọc nếu mã này đã có đơn hàng sử dụng. |
| **Product Name Field** | `QLineEdit` (`#FormField`) | Bắt buộc (1–60 ký tự) | Tên thương mại hiển thị của nông sản (ví dụ: `Chuối tiêu Laba`). |
| **YOLO Model File Field** | `QLineEdit` (`#FormField`) | Bắt buộc (Tên tệp ONNX/PT) | Tên file mô hình chuyên hóa nạp khi kiểm định loại quả này (`D-024` ví dụ: `banana_defect.onnx`). |
| **Detect Classes Field** | `QLineEdit` (`#FormField`) | Bắt buộc (Phẩy ngăn cách) | Danh sách các nhãn khuyết tật mà mô hình nhận diện được; phần tử đầu tiên luôn là nhãn quả lành lặn (`fresh`). |
| **Min Objects SpinBox** | `QSpinBox` (`#FormSpin`) | Bắt buộc (1–500 quả) | Ngưỡng số lượng quả tối thiểu trong khung hình; nếu ít hơn hệ thống tự động đề xuất `NEEDS_REVIEW`. |
| **Min Confidence SpinBox** | `QSpinBox` (`#FormSpin`) | Bắt buộc (0–100%) | Ngưỡng độ tin cậy trung bình của detector; nếu thấp hơn hệ thống sẽ gợi ý gọi phân tích sâu Qwen-VL. |
| **Criteria Defect Class** | `QComboBox` (Trong bảng) | Bắt buộc (Chọn nhãn lỗi) | Phân lớp lỗi áp dụng tiêu chuẩn (ví dụ: `bruised`, `rotten`). |
| **Max Defect Ratio (%)** | `QDoubleSpinBox` (Trong bảng) | Bắt buộc (0.0–100.0%) | Tỷ lệ phần trăm quả lỗi tối đa cho phép trong một kiện hàng; vượt quá sẽ bị kết luận Không đạt. |
| **Critical Checkbox** | `QCheckBox` (`Fail immediately`) | Tùy chọn (Boolean toggle) | Đánh dấu lỗi nghiêm trọng: Nếu phát hiện dù chỉ 1 quả bị lỗi này (như thối nhũn, mốc), hệ thống đề xuất Loại bỏ/Hủy đơn ngay lập tức (`D-023`). |
| **Save Changes Button** | `QPushButton` (`#PrimaryButton`) | Bắt buộc (Interactive) | Lưu toàn bộ cấu hình sản phẩm và tiêu chuẩn chất lượng vào cơ sở dữ liệu PostgreSQL. |

---

#### 2.5.2. Data Import Page (Trang nhập dữ liệu hàng loạt từ Excel/CSV & Trích xuất PDF qua AI)

> **Mô tả chức năng:** Hỗ trợ nhập danh sách đơn hàng, danh mục sản phẩm, tiêu chí và tài khoản từ tệp Excel/CSV mẫu hoặc tải lên hóa đơn/phiếu kiểm nghiệm PDF để Qwen-VL tự động trích xuất dữ liệu (`PageKey.DATA_IMPORT` - `D-029`). Có bảng báo cáo kiểm tra tính hợp lệ từng dòng trước khi xác nhận ghi vào cơ sở dữ liệu.

> **[CHÚ THÍCH CHO BẠN ĐIỀN VÀO / CHÈN ẢNH WIREFRAME HOẶC SCREENSHOT THỰC TẾ]:**
> *Hãy chụp ảnh màn hình hoặc mockup giao diện Data Import tại đây. Đặt tên ảnh: `fig_2_5_2_data_import_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Import Channel Selector** | `QRadioButton` / `Tabs` | Bắt buộc (Toggle) | Chọn nguồn dữ liệu nhập: Excel/CSV (kênh chính) hoặc PDF (giao AI trích xuất). |
| **Template Download Link** | `QPushButton` (`#LinkButton`) | Tùy chọn (File download) | Tải tệp biểu mẫu Excel (.xlsx) chuẩn của AgroScan có sẵn cấu trúc cột và dữ liệu mẫu. |
| **File Drag & Drop Area** | `QFrame` (`#UploadDropZone`) | Bắt buộc (File selector) | Vùng kéo thả hoặc bấm nút duyệt chọn tệp từ máy tính (`.xlsx`, `.csv`, `.pdf`). |
| **Validation Report Table** | `DataTable` (`QTableWidget`) | Tự động (Row verification) | Bảng rà soát dữ liệu trước khi nạp: Hiển thị số dòng, dữ liệu nhận dạng, trạng thái Hợp lệ/Lỗi và nguyên nhân chi tiết (ví dụ: dòng 4 trùng mã đơn, dòng 8 sai định dạng ngày). |
| **AI Extraction Status** | `QLabel` (`#HintLabel`) | Tự động (Khi tải PDF) | Trạng thái trích xuất của Qwen-VL: Số trường dữ liệu đọc được từ biểu mẫu PDF. |
| **Commit to Database Button** | `QPushButton` (`#PrimaryButton`) | Bắt buộc (Database Transaction) | Xác nhận ghi dữ liệu toàn vẹn vào cơ sở dữ liệu PostgreSQL; tự động hủy bỏ giao dịch (Rollback) nếu xảy ra lỗi xung đột. |

---

#### 2.5.3. User Management Page (Trang quản trị người dùng & Phân quyền 3 vai trò)

> **Mô tả chức năng:** Màn hình quản lý danh sách tài khoản nhân viên của hệ thống (`PageKey.USERS`). Quản trị viên có quyền tạo mới tài khoản, phân chia 1 trong 3 vai trò chuẩn (`ADMIN`, `INSPECTOR`, `REVIEWER` theo `D-027`), đặt lại mật khẩu và kích hoạt/khóa tài khoản.

> **[CHÚ THÍCH CHO BẠN ĐIỀN VÀO / CHÈN ẢNH WIREFRAME HOẶC SCREENSHOT THỰC TẾ]:**
> *Hãy chụp ảnh màn hình hoặc mockup giao diện Users Management tại đây. Đặt tên ảnh: `fig_2_5_3_users_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **Users List Table** | `DataTable` (`QTableWidget`) | Bắt buộc (Single selection) | Danh sách người dùng: Tên đăng nhập, Tên đầy đủ, Vai trò, Trạng thái (Hoạt động / Đã khóa) và Thời điểm đăng nhập gần nhất. |
| **Create User Button** | `QPushButton` (`#PrimaryButton`) | Tùy chọn (Interactive) | Mở form thêm mới nhân viên vận hành trạm. |
| **Full Name Field** | `QLineEdit` (`#FormField`) | Bắt buộc (User info) | Họ và tên đầy đủ của nhân viên (ví dụ: `Vũ Hà Ninh`). |
| **Username Field** | `QLineEdit` (`#FormField`) | Bắt buộc (Unique username) | Tên tài khoản định danh không dấu dùng để đăng nhập. |
| **Password & Confirm** | `QLineEdit` (Password Mode) | Bắt buộc (Password input) | Mật khẩu truy cập hệ thống của nhân viên. |
| **Role Selection Combo** | `QComboBox` (`#FormCombo`) | Bắt buộc (Role dropdown) | Phân quyền 1 trong 3 vai trò: `Administrator` (Toàn quyền), `Inspector` (Trạm kiểm định camera), `Reviewer` (Duyệt kết quả). |
| **Active Status Toggle** | `QCheckBox` (`Account Active`) | Bắt buộc (Boolean toggle) | Bật/tắt trạng thái hoạt động; cho phép vô hiệu hóa tài khoản ngay lập tức khi nhân viên nghỉ việc. |
| **Save User Button** | `QPushButton` (`#PrimaryButton`) | Bắt buộc (Interactive) | Lưu thông tin người dùng vào bảng `users` trong cơ sở dữ liệu. |

---

#### 2.5.4. System & LAN Connection Settings Page (Trang cấu hình hệ thống máy trạm & Kiểm tra dịch vụ)

> **Mô tả chức năng:** Màn hình cấu hình toàn bộ hạ tầng mạng phân tán 2 máy tính qua mạng nội bộ (`src/agroscan/ui/pages/settings_page.py` - `D-016`, `D-028`). Cho phép kỹ thuật viên khai báo IP máy chủ DB, URL máy chủ AI, thư mục chia sẻ ảnh SMB, tên định danh máy trạm và camera vật lý kết nối. Tích hợp các nút bấm kiểm tra kết nối chạy trên tiến trình nền (`QThreadPool`) để đảm bảo không gây treo đóng băng giao diện.

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

> **[CHÚ THÍCH CHO BẠN ĐIỀN VÀO / CHÈN ẢNH WIREFRAME HOẶC SCREENSHOT THỰC TẾ]:**
> *Hãy chụp ảnh màn hình trang Settings thực tế của AgroScan tại đây. Đặt tên ảnh: `fig_2_5_4_settings_page.png`.*

| Field name | Type | Require | Target / Purpose |
|---|---|---|---|
| **DB Host / IP** | `QLineEdit` (`#FormField`) | Bắt buộc (IP address) | Địa chỉ mạng của máy chủ cơ sở dữ liệu PostgreSQL trong LAN (`D-014`). |
| **DB Port** | `QSpinBox` (`#FormSpin`) | Bắt buộc (1..65535) | Cổng dịch vụ cơ sở dữ liệu (mặc định: `5432`). |
| **DB Name & User** | `QLineEdit` (`#FormField`) | Bắt buộc (Credentials) | Tên cơ sở dữ liệu và người dùng phân quyền truy cập. |
| **Test DB Connection** | `QPushButton` (`#SecondaryButton`) | Tùy chọn (Background task) | Kiểm tra kết nối TCP socket tới PostgreSQL mà không làm giật lag giao diện (`_CheckTask`). |
| **AI Service URL** | `QLineEdit` (`#FormField`) | Bắt buộc (HTTP Endpoint) | Địa chỉ HTTP REST của dịch vụ mô hình ngôn ngữ - thị giác Qwen-VL trên máy chủ LAN (`D-017`). |
| **AI Timeout Field** | `QSpinBox` (`#FormSpin`) | Bắt buộc (1..120 giây) | Giới hạn thời gian chờ phản hồi tối đa khi gọi phân tích ảnh. |
| **Test AI Connection** | `QPushButton` (`#SecondaryButton`) | Tùy chọn (Background task) | Gửi truy vấn kiểm tra tới Qwen-VL endpoint và đo lường độ trễ mạng thực tế. |
| **SMB Storage Path** | `QLineEdit` (`#FormField`) | Bắt buộc (UNC Path) | Đường dẫn thư mục mạng chia sẻ Windows Share để lưu ảnh bằng chứng gốc (`D-018` ví dụ: `\\192.168.1.10\AgroScan_Data`). |
| **Browse Folder Button** | `QPushButton` (`#SecondaryButton`) | Tùy chọn (File dialog) | Mở hộp thoại chọn thư mục mạng trực quan. |
| **Test Storage Access** | `QPushButton` (`#SecondaryButton`) | Tùy chọn (Background task) | Thử nghiệm ghi và xóa tệp thử nghiệm (canary test) để kiểm tra quyền đọc/ghi trên thư mục mạng. |
| **Station Identifier** | `QLineEdit` (`#FormField`) | Bắt buộc (Unique Station ID) | Mã định danh trạm kiểm định lưu vào metadata của từng phiên (ví dụ: `STATION-01`). |
| **Camera Device Selector**| `QComboBox` (`#FormCombo`) | Bắt buộc (Hardware list) | Danh sách các thiết bị camera vật lý kết nối với máy tính do hệ điều hành nhận dạng qua `QMediaDevices`. |
| **Save Settings Button** | `QPushButton` (`#PrimaryButton`) | Bắt buộc (Interactive) | Lưu toàn bộ thiết lập vào tệp cấu hình máy trạm `app_settings.json` và áp dụng tức thời. |

---

## 3. Design System & Styling Conventions (Quy chuẩn phong cách & Hệ thống thiết kế)

Ứng dụng AgroScan tuân thủ chặt chẽ hệ thống định kiểu bằng Qt Style Sheets (QSS) module hóa (`src/agroscan/ui/styles/dark_theme.qss` và `light_theme.qss`), đảm bảo độ tương phản cao, chống mỏi mắt cho công nhân kho vận làm việc liên tục:
- **Bảng màu chủ đạo (Color Palette):**
  - Nền giao diện chính (`Background`): `#0F172A` (Slate 900 - Dark mode công nghiệp) / `#F8FAFC` (Slate 50 - Light mode).
  - Khung nội dung (`Surface / Cards`): `#1E293B` (Slate 800) với viền nhẹ `#334155`.
  - Màu nhấn hành động chính (`Primary Brand Accent`): `#10B981` (Emerald 500 - Xanh nông sản tươi sáng) cho nút chụp ảnh, bắt đầu kiểm tra và xác nhận.
  - Màu cảnh báo (`Warning`): `#F59E0B` (Amber 500) dành cho trạng thái chờ duyệt hoặc nghi vấn bất định.
  - Màu nguy hiểm / Từ chối (`Danger / Critical`): `#EF4444` (Red 500) dành cho lỗi nghiêm trọng, kiện hàng không đạt hoặc nút hủy phiên.
- **Phông chữ hiển thị (Typography):** Sử dụng họ phông chữ hình học biến thiên **Inter Variable** (`src/agroscan/ui/resources/fonts/Inter-Variable.ttf`), tối ưu hóa khả năng đọc nhanh các chỉ số số học, mã vạch và trạng thái kiểm định trên màn hình máy trạm độ phân giải cao.
- **Tiêu chuẩn thiết kế trường nhập liệu & Bàn phím:** Tất cả các màn hình tác nghiệp quét mã (Box Intake, Live Inspection, Assessment Result) đều tự động bắt tiêu điểm (Auto-focus) vào ô nhập mã kiện để người thao tác chỉ cần cầm máy quét bóp cò là hệ thống tự tiếp nhận chuỗi ký tự mà không cần chạm tay vào chuột hay bàn phím máy tính.

---

> **HẾT TÀI LIỆU ĐẶC TẢ GIAO DIỆN NGƯỜI DÙNG (C2SE.07 - AGROSCAN)**
> *File tài liệu này được lưu trữ tại: `Prompt, Mindset, Rule/07_C2SE07_User_Interface_Design_AgroScan.md`.*

