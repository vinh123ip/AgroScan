# Đối chiếu Branch Git & Trạng thái Trello của AgroScan (Cập nhật 26/11/2026)

**Ngày kiểm tra & đồng bộ:** 26/11/2026 (UTC+7) · **Nhánh tích hợp cuối:** `main` & `develop`

---

## 1. Kết quả hợp nhất & dọn dẹp Branch Git

Toàn bộ các nhánh tính năng từ `origin` (`vinh123ip/AgroScan`) và bản tích hợp trước đó đã được hợp nhất đầy đủ vào `main`, xử lý triệt để xung đột theo đặc tả **Database Design v1.2** (15 bảng, 19 khóa ngoại, 3 views, 5 seed mẫu) và kiểm chứng tự động (51/51 unit tests + E2E 7 bước + Autorun 18 bước đạt 0 lỗi):

| Branch cũ | Commit đầu nhánh | Trạng thái hợp nhất & xử lý |
|---|---|---|
| `3.2.4.2-–-Design-Login/Criteria/QR-Screens-and-VLM-JSON-Schema` | `fc216b0` | Đã hợp nhất hoàn toàn vào `main` & `develop` → **Đã xóa nhánh phụ**. |
| `3.2.5.7-–-Build-PySide6-Login,-Criteria-Editor-and-QR/Barcode-UI` | `d131064` | Đã hợp nhất hoàn toàn vào `main` & `develop` → **Đã xóa nhánh phụ**. |
| `feat/core-yolo-onnx-and-review-flow` | `178f2e9` | Đã hợp nhất hoàn toàn (`yolo_engine.py`, `rule_engine.py`, `evidence_service.py`) → **Đã xóa nhánh phụ**. |
| `feat/postgres-and-simulation-feed` | `2699f0a` | Đã hợp nhất và nâng cấp lên **PostgreSQL v1.2 (15 bảng + 5 seed mẫu)** → **Đã xóa nhánh phụ**. |
| `3.4.4.2---3.4.5.9` | `a261775` | Đã hợp nhất hoàn toàn (song ngữ EN/VI, whole-box coverage, history/audit/notes) → **Đã xóa nhánh phụ**. |
| `integration/local-uat` | `5073ecb` | Đã hợp nhất hoàn toàn vào `main` → **Đã xóa nhánh phụ**. |
| `main` & `develop` (`origin`) | Đồng bộ cùng commit mới nhất | **Giữ lại song song trên local & `origin`** để các thành viên tiếp tục phát triển. *(Không tác động tới `upstream`)*. |

---

## 2. Kết quả đồng bộ Board Trello (`AgroScan`)

Đã liên kết trực tiếp Trello board [AgroScan](https://trello.com/b/yD6OZfa8/agroscan) và đối chiếu 100 thẻ với mã nguồn hiện tại:

- **Chuyển sang cột `Done` (55 thẻ kỹ thuật/QA/tài liệu đã hoàn thiện & kiểm chứng trong repo):**
  - **Sprint 1:** `3.1.3`, `3.1.4.1`, `3.1.4.2`, `3.1.4.3`, `3.1.5.2`, `3.1.5.6`, `3.1.5.7`, `3.1.6.2`.
  - **Sprint 2:** `3.2.3`, `3.2.4.1`, `3.2.4.2`, `3.2.5.2`, `3.2.5.4`, `3.2.5.5`, `3.2.5.6`, `3.2.5.7`, `3.2.5.8`, `3.2.6.1`, `3.2.6.2`.
  - **Sprint 3:** `3.3.3`, `3.3.4.1`, `3.3.5.1`, `3.3.5.2`, `3.3.5.4`, `3.3.5.6`, `3.3.5.7`, `3.3.6.1`.
  - **Sprint 4:** `3.4.3`, `3.4.4.1`, `3.4.4.2`, `3.4.5.1`, `3.4.5.2`, `3.4.5.3`, `3.4.5.4`, `3.4.5.5`, `3.4.5.6`, `3.4.5.7`, `3.4.5.8`, `3.4.5.9`, `3.4.6.1`, `3.4.6.2`.
  - **Sprint 5:** `3.5.3`, `3.5.4.1`, `3.5.4.2`, `3.5.5.1`, `3.5.5.2`, `3.5.5.4`, `3.5.5.5`, `3.5.5.6`, `3.5.6.1`, `3.5.6.2`.
  - **Sprint 6:** `3.6.4.2`, `3.6.5.2`, `3.6.5.3`, `3.6.6.2`.
- **Giữ ở `In Progress` / Backlog theo dõi mở rộng:**
  - `3.1.5.3`, `3.1.5.4`, `3.1.5.5` (thu thập dataset thật, fine-tune & đo mAP@0.5 / Top-1 độc lập), `3.1.5.1` / `3.2.5.1` (FastAPI/Docker/MinIO nếu tách client-server ngoài kiến trúc Desktop hiện tại), `3.2.5.3` (cài đặt Ollama Qwen2-VL-2B riêng nếu thay LM Studio).
