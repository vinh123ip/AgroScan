# AgroScan · Hướng dẫn chạy và kiểm thử thủ công

## Mở ứng dụng

Trên máy đã thiết lập, mở PowerShell trong thư mục mã chính và chạy:

```powershell
cd E:\AgroScan_Project\AgroScan
python run.py
```

Launcher tự chọn Python trong `.venv`. Với địa chỉ AI mặc định, launcher cũng mở dịch vụ VLM tại `127.0.0.1:8000` trong thời gian dùng ứng dụng. Nếu cổng đang có tiến trình sử dụng, desktop tiếp tục dùng địa chỉ đã cấu hình. Nếu có LM Studio chạy mô hình thị giác tại cổng `1234`, bridge có thể gửi ảnh đến mô hình. Khi chạy dự phòng, kết quả phân tích được tạo theo quy tắc. Các model ONNX baseline đi kèm bước thiết lập phục vụ kiểm tra luồng và dữ liệu mô phỏng.

**PostgreSQL v1.2.** Ứng dụng đọc cấu hình kết nối từ `.env`, có thể sao chép mẫu `.env.example`. Môi trường dev hiện dùng database `agroscan_dev` và tài khoản kết nối `agro_user`. Dùng `python run.py --demo` để mở chế độ mô phỏng dùng RAM.

**Máy mới của thành viên nhóm.** Từ thư mục repo trên Windows, chạy một lần:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/export_yolo_onnx.py
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

**Khởi tạo database lần đầu.** Trong pgAdmin, mở Query Tool vào database đích bằng tài khoản quản trị PostgreSQL. Chạy lần lượt [01_schema.sql](../scripts/db_v1_2/01_schema.sql), [02_seed.sql](../scripts/db_v1_2/02_seed.sql) và [03_grant_app.sql](../scripts/db_v1_2/03_grant_app.sql). Nếu schema đã có, bắt đầu từ script seed. Script cấp quyền dùng vai trò `agro_user`. Nếu máy dùng tên khác, sửa tên vai trò trong script cho khớp cấu hình.

Tạo tài khoản quản trị ứng dụng bằng PowerShell. Lệnh hỏi mật khẩu hai lần và lưu giá trị băm trong PostgreSQL.

```powershell
python run.py --create-admin TEN_DANG_NHAP
python run.py
```

## Kiểm thử PostgreSQL v1.2

- Đăng nhập bằng tài khoản vừa tạo. Trong **Box Intake**, tra `AGS:DEMO-V12-02-04/04` và đối chiếu mã thùng bằng token `00000000-0000-4000-8000-000000120024`.
- Trong **Data Import**, kiểm tra năm đơn `DEMO-V12-01` đến `DEMO-V12-05`. Trong **Inspection History**, kiểm tra phiên nháp của lô chuối, phiên chờ duyệt của lô tôm và lịch sử tái kiểm của lô mực. Lô mực có quyết định cấp lô `approve`.
- Tạo tài khoản Inspector và Reviewer trong **Users**. Lô tôm có thùng `AGS:DEMO-V12-04-02/03` được chọn và chưa kiểm trong seed. Luồng desktop hiện hỗ trợ một batch. Ảnh cuối cùng là ảnh đếm, ảnh trước đó là ảnh bổ sung. Dùng một ảnh bao quát toàn bộ thùng, có vật thể được detector phát hiện, rồi xác nhận độ bao phủ khi nộp. Reviewer độc lập xử lý phiên và nhập lý do.
- Tạo hoặc điều chỉnh kế hoạch lấy mẫu và ký quyết định cấp lô theo quy trình v1.2. Giao diện hiện đọc kế hoạch và quyết định đã lưu.

## Chức năng và tài khoản thử trong chế độ demo

| Vai trò | Tài khoản mẫu | Chức năng chính |
| --- | --- | --- |
| Inspector | `inspector` / `inspector123` | Tra đơn và mã thùng, nhận ảnh từ camera hoặc Simulation Feed, xem phát hiện và khuyến nghị, lưu ảnh bằng chứng, gửi duyệt. |
| Reviewer | `reviewer` / `reviewer123` | Mở hàng đợi, xem ảnh và hash, ghi chú, xác nhận đạt, không đạt hoặc yêu cầu kiểm lại. |
| Admin | `admin` / `admin123` | Quản lý danh mục và tiêu chí, người dùng, cấu hình trạm, nhập đơn, tra lịch sử và xuất báo cáo. |

Ba tài khoản trên dành cho `python run.py --demo`. Dùng tài khoản ứng dụng đã tạo trên PostgreSQL khi chạy chế độ v1.2. Mã thùng mẫu `AGS:DH00123-07/10` là thùng 7 trong đơn 10 thùng chuối. Khi thử các ca khác nhau, dùng số thùng khác trong cùng đơn để dễ tìm kết quả.

## Các ca kiểm thử thủ công

Mở `python run.py --demo` rồi chạy TC01–TC07 theo thứ tự cho một lượt kiểm định hoàn chỉnh. Ghi mã phiên hiển thị trên màn hình để tra lại đúng lượt. Khi báo lỗi, ghi mã ca, vai trò, mã thùng, chế độ PostgreSQL/RAM và kết quả thực tế.

| Mã | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| TC01 · Đăng nhập | Nhập sai mật khẩu Inspector rồi thử lại bằng tài khoản mẫu. | Lần đầu báo lỗi. Lần sau vào được màn hình của Inspector, có thông tin phiên đăng nhập. |
| TC02 · Tra mã | Trong **Box Intake**, thử `AGS:NOPE999-01/10`, sau đó nhập `AGS:DH00123-07/10`. | Mã đầu báo không tìm thấy đơn. Mã sau hiện đúng đơn, loại hàng BANANA, số thùng và tiêu chí. Có thể bắt đầu kiểm định. |
| TC03 · Chụp bằng chứng | Chọn **Start Inspection → Simulation Feed → Fresh Bananas → Capture Evidence**. | Có ảnh xem trước, số lượng phát hiện và ảnh thu nhỏ trong danh sách bằng chứng. Có thể kết thúc sau khi chụp. |
| TC04 · Đánh giá | Chọn **Finish Inspection**, xem lý do và chọn **Submit for Review**. Dùng thùng khác để thử lại với **Rotten Bananas** và bộ tiêu chí BANANA mặc định. | Ca tươi cho khuyến nghị đạt, ca có lỗi thối nghiêm trọng cho khuyến nghị không đạt. Phiên đã gửi xuất hiện ở **Review Queue**. |
| TC05 · Kiểm duyệt | Đăng xuất, vào bằng Reviewer. Chọn phiên vừa gửi, mở ảnh, xem SHA-256, nhập ghi chú và chọn **Pass** hoặc **Fail**. | Ảnh mở được và hiển thị kết quả kiểm tra toàn vẹn. Phiên đã xử lý rời hàng đợi và tra được trong lịch sử. Thử **Re-inspect** trên phiên riêng để xem quyết định kiểm lại. |
| TC06 · Lịch sử | Mở **Inspection History** trong cùng phiên chạy demo, tìm theo đơn hoặc ngày. | Tìm lại được phiên và quyết định vừa ghi. Phân biệt khuyến nghị của máy với quyết định của Reviewer. |
| TC07 · Xuất báo cáo | Từ lịch sử xuất PDF cho một phiên. Vào **Reports**, lọc đúng ngày và sản phẩm, chọn **Apply Filter**, xuất PDF và Excel. | PDF mở được, đúng phiên hoặc kỳ đã chọn. Excel có các trang **Order Summary**, **Inspection Sessions**, **Evidence Integrity**. Đối chiếu mã phiên và hash với ứng dụng. |
| TC08 · Nhập đơn | Admin mở **Data Import**, lưu mẫu CSV hoặc XLSX. Dùng mã đơn thử mới. Thêm một dòng có product code lạ và một dòng có `total_boxes=0`. Nạp tệp, xem preview, chọn **Import Valid Orders to DB**. | Preview chỉ đúng dòng lỗi và số dòng hợp lệ. Đơn hợp lệ xuất hiện trong danh sách. Các dòng lỗi được bỏ qua. Lặp lại với định dạng còn lại. |
| TC09 · Tiêu chí và phân quyền | Đăng nhập Admin, mở **Catalog**, tạo sản phẩm thử, nhập trùng loại lỗi rồi sửa thành bộ tiêu chí hợp lệ và lưu. Đăng nhập Inspector để so sánh menu. | Editor báo lỗi trùng. Bộ tiêu chí hợp lệ lưu được. Các chức năng quản trị chỉ xuất hiện với vai trò phù hợp. |
| TC10 · Quản lý tài khoản | Admin vào **Users**, tạo một tài khoản thử, đặt vai trò và mật khẩu. Thử đăng nhập rồi vô hiệu hóa chính tài khoản thử. | Tài khoản hoạt động đăng nhập được với vai trò đã chọn. Sau khi vô hiệu hóa, lần đăng nhập kế tiếp bị từ chối. |
| TC11 · Phân tích sâu | Sau khi chụp ảnh, chọn **Deep Analysis (Qwen-VL)**. Xem panel lỗi, OCR, độ bất định và cảnh báo. | UI hiển thị kết quả có cấu trúc hoặc lý do lỗi. Để xác minh suy luận thật, kiểm tra LM Studio đã nạp mô hình và nhận request ảnh của phiên đó. |
| TC12 · Camera và cấu hình | Admin chọn thiết bị trong **Settings**. Inspector mở một thùng mới, chọn camera thật và chụp. Thử **Simulation Feed** khi máy thiếu camera. | Với camera hoạt động, thấy khung hình và chụp được ảnh. Khi thiếu thiết bị, ứng dụng báo trạng thái camera và cho chuyển sang ảnh mô phỏng. |

## Kiểm tra tự động

`python tests/e2e_walkthrough.py` kiểm tra luồng giao diện với dữ liệu mock. `python run_tests.py` chạy bộ test đầy đủ, trong đó có ca đọc seed, nhập đơn, nộp và duyệt kiểm định trong giao dịch được rollback khi kết thúc. Khi chạy bộ đầy đủ, dùng database kiểm thử riêng đã nạp schema và seed, đồng thời trỏ cấu hình kết nối tới database đó. Kết quả cuối cần có `Failures: 0` và `Errors: 0`.

### Kiểm tra bản tích hợp Sprint 3.4 với PostgreSQL v1.2

- Chọn **Import original** để nạp ảnh vận hành. **Simulation Feed** gắn nhãn demo cho cả ảnh tự chọn. Đối chiếu SHA-256 với tệp nhập và thử hủy chọn ảnh. Các góc chụp hỗ trợ quan sát. Khi nộp, Inspector xác nhận ảnh đếm của batch bao quát toàn bộ thùng.
- Chuyển **EN / VI** giữa phiên, kiểm tra mã thùng, ảnh đã chụp và trạng thái. Xuất báo cáo trong giao diện tiếng Việt rồi kiểm tra cột kết quả trong tệp tiếng Anh.
- Trên Dashboard đối chiếu số thùng đã duyệt với số vị trí của kế hoạch mẫu hiện hành. Lô chưa khóa kế hoạch hiển thị dấu gạch ngang. Với lô mực mẫu, kiểm tra hai thùng đã duyệt, attempt tái kiểm cũ và quyết định chấp thuận ngoại lệ.
- Trong History, tìm thùng theo mã rồi mở từng attempt. Reviewer có thể thêm ghi chú. Admin có thể xem nhật ký. Manager có thể tra cứu kết quả. Khi thử trên lô đã ký, đối chiếu phiên bản, lý do ngoại lệ và danh sách attempt trong bản kê trước và sau khi ghi chú.
- Kiểm tra Qwen-VL vận hành bằng một ảnh gốc và một endpoint đã nạp mô hình. Test tự động chạy giao tiếp HTTP với đầu ra mô hình kiểm soát được. Kiểm tra SMB và suy luận trên máy chủ triển khai là hai phép thử riêng.
- Chạy `python tests/autorun.py --headless-check` để tự động thực hiện 18 bước demo. Kịch bản kiểm tra phiên có phân tích sâu, quyết định Pass của Reviewer và thay đổi tiêu chí do Admin lưu.
