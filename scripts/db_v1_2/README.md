# AgroScan | Phân tích ERD và triển khai Database Design v1.2

Bộ SQL triển khai 15 bảng, 121 thuộc tính và 19 khóa ngoại theo mục 2.1–2.4 của Database Design v1.2. Mục 3.1 quyết định cách khóa kế hoạch, lưu bằng chứng, tái kiểm và ký kết luận. Hai hình ở mục 2.2–2.3 thể hiện quan hệ chính. Từ điển ở mục 2.4 bổ sung các trường như `plan_version`, `coverage`, `checkpoint`, `machine_box_result`, `source_kind`, `usage_context` và `received_at`.

## Cách nạp bằng pgAdmin 4

1. Mở **Query Tool** tại database dev mà AgroScan đang kết nối, ví dụ `agroscan_dev`. Có thể kiểm tra bằng `SELECT current_database(), current_user;`.
2. Mở `01_schema.sql` và chạy toàn bộ file một lần. Tài khoản chạy cần quyền tạo schema trong database. Script tạo namespace `agroscan` trong một transaction. Nếu namespace này đã tồn tại, script dừng ngay để giữ dữ liệu. Nếu Query Tool báo transaction đã hủy, chạy `ROLLBACK;` trước câu lệnh kế tiếp.
3. Mở `02_seed.sql` và chạy toàn bộ file. Năm kịch bản và sự kiện hoàn tất được commit cùng nhau. Chạy lại sau khi nạp thành công sẽ bỏ qua bộ mẫu. Các ID âm cố định dùng riêng cho fixture để cùng một chữ ký mẫu kiểm chứng được trên nhiều máy. Nếu khóa mẫu đã bị dữ liệu khác chiếm, transaction báo lỗi.
4. Refresh **Schemas → agroscan → Tables**. Các truy vấn bên dưới ghi rõ namespace nên dùng được ngay trong Query Tool.

5. Chạy `03_grant_app.sql` bằng chủ sở hữu schema để cấp quyền cho tài khoản PostgreSQL trong `.env`. Thay `agro_user` trong script nếu môi trường dùng vai trò khác.
6. Từ thư mục AgroScan, chạy `python run.py --create-admin TEN_DANG_NHAP` để tạo tài khoản đăng nhập desktop, sau đó chạy `python run.py`. Các tài khoản lịch sử trong seed dùng để đối chiếu dữ liệu.

## Các quan hệ trong ERD

Ký hiệu ở cột phải mô tả số cha trên **một bản ghi con**. Mỗi cha có thể có nhiều con, trừ liên kết thay thế và tái kiểm, mỗi tiền nhiệm chỉ có tối đa một kế nhiệm trực tiếp trong schema.

| Bảng con | Khóa ngoại → bảng cha | Ý nghĩa và lực lượng |
|---|---|---|
| `inspection_profiles` | `product_id → products` | Mỗi phiên bản tiêu chí thuộc đúng 1 sản phẩm. Cặp sản phẩm và số phiên bản là duy nhất. |
| `quality_rules` | `profile_id → inspection_profiles` | Mỗi quy tắc thuộc 1 phiên bản. Mã quy tắc duy nhất trong phiên bản đó. |
| `lots` | `order_id → orders`, `profile_id → inspection_profiles`, `sampling_rule_id → sampling_rules` | Lô thuộc 1 đơn, dùng 1 profile. Có thể chưa có ô tra khi nhập lô. Khóa kế hoạch yêu cầu đúng 1 ô tra. |
| `boxes` | `lot_id → lots` | Thùng thuộc 1 lô. Mã thùng duy nhất trong lô, token quét duy nhất toàn schema. |
| `sample_selections` | `box_id → boxes`, `replaces_id → sample_selections` | Mỗi lượt chọn gắn với 1 thùng. Lượt thay thế có 1 tiền nhiệm trong cùng lô, revision và vị trí mẫu. Lượt chọn gốc có 0 tiền nhiệm. |
| `inspections` | `selection_id → sample_selections`, `previous_id → inspections`, `inspector_id / reviewer_id → users` | Mỗi attempt thuộc 1 lượt chọn, do 1 inspector tạo. Reviewer xuất hiện khi xử lý kết quả. Tái kiểm mở attempt kế tiếp trên cùng lượt chọn. |
| `inspection_batches` | `inspection_id → inspections` | Mỗi batch là 1 nhóm vật thể riêng thuộc đúng 1 attempt. |
| `inspection_images` | `batch_id → inspection_batches` | Một batch có nhiều ảnh và tối đa 1 ảnh đếm. Khi nộp, mỗi batch phải có ảnh đếm cùng quan sát sử dụng được. |
| `observed_products` | `batch_id → inspection_batches`, `count_image_id → inspection_images` | Một dòng cho 1 vật thể trên ảnh đếm của chính batch. Hộp tọa độ phải nằm trong ảnh. Ảnh bổ sung không tạo thêm vật thể. |
| `lot_decisions` | `lot_id → lots`, `reviewer_id → users` | Mỗi quyết định có 1 lô, 1 người ký và 1 số phiên bản. Kết luận sửa đổi được lưu bằng phiên bản mới. |
| `audit_logs` | `actor_id → users` | Tác vụ con người có người thực hiện. Sự kiện hệ thống có thể để trống actor. Cặp `target_type/target_key` xác định đối tượng thuộc nhiều loại. |

**Phân biệt thay thùng và tái kiểm.** Thùng chưa kiểm nhưng không tiếp cận được có thể được thay bằng thùng dự phòng khi Reviewer cho phép. Lịch sử thay nằm ở `sample_selections.replaces_id`. Nếu bằng chứng của thùng đã kiểm chưa đủ, Reviewer yêu cầu tái kiểm chính thùng đó. Lịch sử attempt nằm ở `inspections.previous_id`. Khi chốt lô, mỗi vị trí lấy mẫu chỉ đóng góp một kết quả có thẩm quyền.

## Quy tắc từ mục 3.1–3.4

| Giai đoạn | Ràng buộc và dữ liệu được lưu |
|---|---|
| Nhập hàng | Đơn giữ mã ngoài và file nguồn. Lô giữ số thùng khai báo. Khối lượng và đơn vị nếu có thuộc sự kiện nhập. Service gửi đơn, lô, danh sách thùng và sự kiện Admin trong cùng transaction, như seed minh họa. |
| Tiêu chí | Chốt profile sau khi khai báo quy tắc và nguồn. Sửa tiêu chí đã duyệt bằng phiên bản mới. Profile nghỉ áp dụng vẫn truy được qua các lô cũ. Quy tắc tỷ lệ hỗ trợ `gt/ge`. Quy tắc loại trừ xác định lỗi từ một vật thể bị ảnh hưởng. |
| Lấy mẫu | Đối chiếu số thùng thực tế, digest danh sách và ô tra khi khóa. Mỗi revision lưu N, n, Ac/Re, AQL, mức kiểm, nguồn tra, seed, thuật toán và thứ tự ID thùng. Revision mới ghi lý do, tiền nhiệm và cách xử lý attempt đang mở. View `current_selections` trả về các vị trí đang có hiệu lực. |
| Chụp và suy luận | PostgreSQL giữ khóa MinIO, SHA-256, kích thước và nguồn gốc ảnh. Nguồn camera/ảnh nhập độc lập với chế độ demo/vận hành. Mỗi lần suy luận có execution ID và sự kiện bất biến. API ghi thêm phản hồi VLM gốc hoặc tham chiếu được bảo vệ cùng digest khi chạy VLM. |
| Nộp và phục hồi | `checkpoint` lưu giai đoạn và thao tác gần nhất. Nộp yêu cầu xác nhận toàn bộ thùng, tập batch khớp thực tế, quan sát trên ảnh đếm, mẫu số và kết quả máy đã chốt. Thời điểm nộp gắn với sự kiện của người nộp. Ứng dụng dùng operation ID để xử lý retry. |
| Review | Reviewer là inspector đang hoạt động có `can_review = true`. Kiểm tra độc lập xét người tạo và người nộp trên thùng. Sửa nhận định ghi `review_findings` cùng sự kiện có lý do, thời điểm và giá trị trước/sau. View `box_rule_counts` đếm vật thể phân biệt theo từng quy tắc và giữ riêng số liệu AI và review. |
| Chốt lô | Sự kiện `attempt_selected` chỉ định attempt có thẩm quyền cho từng vị trí. Hàm `decision_payload` đối chiếu revision đang hoạt động, toàn bộ mẫu đã review và người ký. Bản kê chứa phiên bản tiêu chí, attempt, hash ảnh gốc, kết quả máy và người duyệt, d, Ac/Re, khuyến nghị, quyết định và lý do ngoại lệ. |
| Chữ ký và audit | Service dùng khóa cá nhân và kiểm tra RSA-PSS/SHA-256 trên đúng `manifest_bytes`. Database kiểm tra nội dung với dữ kiện lô, liên kết đăng ký chứng thư, digest chứng thư/bản kê/chữ ký và sự kiện xác minh thành công trong cùng transaction. Chữ ký lỗi cần được service ghi thành sự kiện thất bại sau khi rollback quyết định. View `latest_lot_decisions` lấy phiên bản quyết định mới nhất. |
| Xuất và khôi phục | Dùng `audit_logs` cho người xuất, bộ lọc, phiên bản quyết định, digest file xuất, lỗi và khôi phục. Service thực hiện xuất file, backup/restore phối hợp PostgreSQL–MinIO, đối chiếu hash ảnh và xác minh lại chữ ký sau khôi phục. |

DB kiểm tra quan hệ và nội dung được ghi. Service vẫn chịu trách nhiệm xác thực actor, giới hạn quyền ghi sự kiện, xác minh nguồn tiêu chuẩn trước khi kích hoạt, xác nhận lý do đổi mẫu, chạy thuật toán lấy mẫu, kiểm chứng chữ ký thực tế và quản lý MinIO. Các thao tác ký trong vận hành phải đi qua verifier tin cậy. Sự kiện SQL tự khai thành công không thay thế được phép kiểm tra chữ ký. Hai file SQL không cấp quyền ghi rộng cho các tài khoản khác.

## Năm lô mẫu

| Đơn | Hàng hóa | Điểm cần kiểm tra |
|---|---|---|
| `DEMO-V12-01` | Táo | Nhập 3 thùng. Profile đã gắn, kế hoạch chưa khóa. |
| `DEMO-V12-02` | Cam | Bổ sung thùng thứ 4, chuyển từ revision 1 sang 2. Vị trí 1 ở revision 2 thay thùng không tiếp cận được, giữ lịch sử và lý do. |
| `DEMO-V12-03` | Chuối | Attempt ở `draft`, có batch, ảnh đếm và quan sát. Có thể kiểm tra tiếp luồng nộp. |
| `DEMO-V12-04` | Tôm | Một attempt đã nộp, chờ Reviewer. Hai batch, hai ảnh đếm, một ảnh bổ sung và bốn vật thể được đếm. |
| `DEMO-V12-05` | Mực | Một thùng tái kiểm, thùng còn lại không phù hợp. Với d = 1, Ac = 0 và Re = 1, khuyến nghị là `reject`. Reviewer ký `approve` theo ngoại lệ có lý do. |

Các ngưỡng và ô tra gắn nhãn **DEMO** dùng để chạy thử logic. Tài liệu không cung cấp giá trị TCVN đã xác minh. Năm tài khoản mẫu là danh tính lịch sử, không có mật khẩu đăng nhập. Seed chứa chứng thư thử nghiệm, chữ ký có thể xác minh và đúng các byte bản kê đã ký. Khóa ký riêng không đi kèm. Ảnh PNG mô phỏng có thể dựng lại từ base64 ở đầu seed. Script nạp tham chiếu ảnh vào PostgreSQL. Các `object_key` chưa được tải lên MinIO.

## Truy vấn đối chiếu

Xem số thùng, revision, số vị trí đang hoạt động và tình trạng quyết định theo năm lô.

```sql
SELECT o.order_code, p.name AS product, l.declared_boxes,
       (l.plan_snapshot->>'active_version')::int AS active_revision,
       (SELECT count(*) FROM agroscan.current_selections s
        JOIN agroscan.boxes b ON b.id = s.box_id WHERE b.lot_id = l.id) AS active_slots,
       d.version AS decision_version, d.outcome
FROM agroscan.orders o
JOIN agroscan.lots l ON l.order_id = o.id
JOIN agroscan.inspection_profiles ip ON ip.id = l.profile_id
JOIN agroscan.products p ON p.id = ip.product_id
LEFT JOIN agroscan.latest_lot_decisions d ON d.lot_id = l.id
WHERE o.order_code LIKE 'DEMO-V12-%'
ORDER BY o.order_code;
```

Đọc nội dung đã ký của lô mực và so sánh khuyến nghị với quyết định cuối.

```sql
SELECT manifest->>'d' AS nonconforming_boxes, manifest->>'Ac' AS ac,
       manifest->>'Re' AS re, manifest->>'recommendation' AS recommendation,
       manifest->>'outcome' AS signed_outcome, manifest->>'override_reason' AS reason
FROM (
    SELECT convert_from(d.manifest_bytes,'UTF8')::jsonb AS manifest
    FROM agroscan.latest_lot_decisions d
    JOIN agroscan.lots l ON l.id = d.lot_id
    JOIN agroscan.orders o ON o.id = l.order_id
    WHERE o.order_code = 'DEMO-V12-05'
) signed;
```

## Kết nối desktop

Repository truy vấn đối tượng với namespace `agroscan`. Màn hình tra cứu đọc đơn và lô từ profile đã gắn, hỗ trợ mã nội bộ `AGS:DEMO-V12-02-04/04` và UUID `scan_token`. **Data Import** tạo lô và danh sách thùng trong cùng transaction. **Catalog & Criteria** lưu thay đổi tiêu chí thành profile nháp mới. Khi nhập lô, repository chọn phiên bản profile đã duyệt mới nhất còn hiệu lực.

Luồng kiểm định desktop mở một thùng trong kế hoạch đang hiệu lực, lưu một batch khi người kiểm xác nhận ảnh đếm bao quát toàn thùng, rồi đưa vào hàng đợi Reviewer độc lập. Ảnh từ ứng dụng desktop dùng kho ảnh SMB hoặc thư mục cục bộ đã cấu hình. Đóng lô bằng chữ ký, tạo hoặc sửa kế hoạch lấy mẫu và thu nhiều batch vẫn cần quy trình v1.2 tương ứng. Seed chỉ lưu metadata ảnh. Có thể khôi phục ảnh demo từ PNG base64 ở phần đầu `02_seed.sql`, với mỗi đường dẫn tương ứng `inspection_images.object_key` trong kho ảnh desktop.

Xem thêm [hướng dẫn kiểm thử desktop](../../docs/HUONG_DAN_KIEM_THU.md).
