# Secure Video Streamer

Đây là một dự án Python sử dụng Flask để tạo ra một hệ thống máy chủ web cho phép mã hóa, quản lý và phát các tệp video một cách an toàn. Hệ thống hỗ trợ tua video, có cơ chế cache thông minh và cung cấp giao diện web cho cả quản trị viên và người dùng cuối.

## Tính năng chính

- **Mã hóa An toàn:** Sử dụng `AES-CTR` để mã hóa/giải mã các tệp video, cho phép streaming hiệu quả.
- **Tên tệp Ngẫu nhiên:** Các tệp sau khi mã hóa sẽ có tên ngẫu nhiên để tăng tính khó đoán.
- **Streaming Hỗ trợ Tua (Seeking):** Máy chủ hỗ trợ `HTTP Range Requests`, cho phép người dùng tua đến bất kỳ vị trí nào trong video.
- **Hệ thống Cache Thông minh:** Các tệp được yêu cầu từ URL sẽ được tải về và lưu vào bộ đệm (`cache`) để tăng tốc độ cho các lần xem lại.
- **Giao diện Quản lý Toàn diện (`/manage`):**
    - Hiển thị danh sách hợp nhất các tệp từ cache và thư mục cục bộ.
    - Hiển thị tên gốc, dung lượng, nguồn, và các thông tin khác.
    - Chức năng tìm kiếm mạnh mẽ.
    - Chức năng quét để cập nhật danh sách tệp cục bộ.
    - Cho phép phát hoặc xóa tệp trực tiếp từ giao diện.
- **Trang Viewer cho Người dùng (`/viewer`):**
    - Cho phép người dùng bất kỳ xem video bằng cách cung cấp URL của tệp `.vcc` và mật khẩu tương ứng.
    - Mật khẩu của người dùng được xử lý tạm thời cho phiên xem, không được lưu trữ lâu dài.

## Yêu cầu

- Python 3.x
- pip

## Cài đặt

1.  Sao chép hoặc tải về toàn bộ mã nguồn dự án.
2.  Mở terminal trong thư mục gốc của dự án.
3.  Cài đặt các thư viện cần thiết bằng lệnh sau:
    ```bash
    pip install Flask pycryptodome requests
    ```

## Hướng dẫn Sử dụng

### 1. Mã hóa Video

- Để mã hóa các video của bạn, hãy đặt chúng vào một thư mục (ví dụ: `input`).
- Chạy lệnh sau từ terminal:
    ```bash
    python video.py encrypt input output
    ```
- Lệnh này sẽ mã hóa tất cả các tệp trong `input` và lưu kết quả vào thư mục `output` với các tên tệp ngẫu nhiên.

### 2. Chạy Máy chủ API

- Chạy lệnh sau:
    ```bash
    python api.py
    ```
- Lần đầu tiên chạy, hệ thống sẽ tự động tạo các thư mục `output` và `cache`.
- Bạn sẽ được yêu cầu nhập một **mật khẩu ADMIN**. Mật khẩu này được dùng để quản lý và quét các tệp cục bộ trong thư mục `output` vui lòng đảm bảo mật khẩu đúng mới mật khẩu mã hóa.

### 3. Sử dụng Giao diện Web

Sau khi máy chủ khởi động, bạn có thể truy cập các trang sau từ trình duyệt:

#### Trang Quản lý (Dành cho Admin)

- **Địa chỉ:** `http://127.0.0.1:5000/manage`
- **Chức năng:**
    - **Xem tất cả tệp:** Xem danh sách các tệp trong `cache` và `output`.
    - **Quét Tệp Cục bộ:** Nhấn nút này để hệ thống quét thư mục `output`, giải mã tên gốc và cập nhật vào danh sách quản lý. **Bạn cần thực hiện thao tác này mỗi khi thêm tệp mới vào `output`**.
    - **Tìm kiếm:** Gõ vào ô tìm kiếm để lọc danh sách.
    - **Hành động:** Nhấn nút "Phát" để xem video hoặc "Xóa" để loại bỏ tệp.

#### Trang Viewer (Dành cho Người dùng cuối)

- **Địa chỉ:** `http://127.0.0.1:5000/viewer`
- **Chức năng:**
    - Dán URL của một tệp `.vcc` vào ô URL.
    - Nhập mật khẩu tương ứng của tệp đó.
    - Nhấn "Xem Video". Hệ thống sẽ tải tệp vào cache (nếu cần) và phát video.

## Cấu trúc Thư mục

- `api.py`: Tệp máy chủ Flask chính.
- `video.py`: Kịch bản để mã hóa/giải mã.
- `info_manifest.json`: Tệp "sổ ghi chép" trung tâm, lưu trữ thông tin về tất cả các tệp.
- `output/`: Thư mục mặc định chứa các tệp `.vcc` cục bộ của bạn.
- `cache/`: Thư mục chứa các tệp `.vcc` được tải về từ URL.
- `templates/`: Chứa các tệp HTML (`index.html`, `viewer.html`).
- `static/`: Chứa các tệp CSS (`style.css`).
