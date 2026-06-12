# Day 12 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found
1. **Hardcoded Secrets:** API keys và Database credentials (`sk-hardcoded-fake-key-never-do-this`, `postgresql://admin:password123@localhost:5432/mydb`) bị ghi cứng trong code. Nếu đẩy code lên GitHub, các thông tin nhạy cảm này sẽ bị lộ ngay lập tức.
2. **Không có Config Management:** Biến môi trường (`DEBUG = True`, `MAX_TOKENS = 500`) không được tách biệt khỏi mã nguồn mà viết trực tiếp trong file logic.
3. **In log thô (print statement):** Sử dụng các hàm `print()` thô thay vì structured logging, có thể in ra cả các thông tin bảo mật (như in API Key) gây mất an toàn thông tin và khó phân tích log tập trung.
4. **Thiếu Health Check Endpoints:** Không có API endpoint `/health` hay `/ready` để giám sát trạng thái hoạt động của Agent, dẫn đến việc hạ tầng cloud không thể tự động phục hồi (auto-heal) khi ứng dụng gặp sự cố.
5. **Gán cứng Host và Port:** Host được gắn cố định là `localhost` (không thể truy cập ngoài container) và cổng `8000` được code cứng (không nhận từ biến môi trường `PORT` của cloud).

### Exercise 1.3: Comparison table
| Feature | Basic (❌) | Advanced (✅) | Tại sao quan trọng? |
|---------|-----------|--------------|---------------------|
| **Config** | Viết cứng trong file app.py | Đọc từ environment variables | Giúp triển khai ứng dụng linh hoạt trên nhiều môi trường (Dev, Staging, Prod) mà không cần chỉnh sửa mã nguồn. |
| **Health check** | Không có | Có `/health` (Liveness) & `/ready` (Readiness) | Giúp Container Orchestrator biết khi nào ứng dụng sẵn sàng nhận traffic hoặc cần phải restart khi gặp lỗi. |
| **Logging** | Dùng `print()` thô | Dùng Structured JSON logging | Dễ dàng parse và lọc logs tập trung ở môi trường production (như Datadog, ELK, Prometheus). |
| **Shutdown** | Đột ngột | Graceful shutdown (SIGTERM) | Đảm bảo các tiến trình (requests) đang chạy được hoàn tất trước khi tắt, tránh mất dữ liệu hoặc lỗi kết nối. |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions
1. **Base image:**
   - Develop: `python:3.11` (Full distribution, nặng ~1.66 GB).
   - Production: `python:3.11-slim` (Rút gọn, nhẹ hơn nhiều).
2. **Working directory:** `/app` (được cấu hình qua `WORKDIR /app`).
3. **Tại sao COPY requirements.txt trước?:** Để tận dụng cơ chế Docker layer cache. Nếu file code thay đổi nhưng packages không thay đổi, Docker sẽ tái sử dụng cache của layer cài đặt packages (`RUN pip install...`) thay vì cài lại từ đầu, giúp tăng tốc build đáng kể.
4. **CMD vs ENTRYPOINT khác nhau thế nào?:** 
   - `CMD` cung cấp lệnh mặc định để chạy container và có thể dễ dàng bị ghi đè hoàn toàn khi chạy container với đối số bổ sung.
   - `ENTRYPOINT` định nghĩa lệnh cơ sở cố định không thể bị override trực tiếp. Các tham số truyền vào từ `docker run` sẽ được append vào sau `ENTRYPOINT`.

### Exercise 2.3: Image size comparison
- **Develop (Single-stage):** 1.66 GB
- **Production (Multi-stage + Slim):** 236 MB
- **Difference:** Giảm khoảng **85.78%** dung lượng image.

### Exercise 2.4: Architecture and Load Balancer
- **Services được start:** `agent` (2 replicas chạy stateless), `redis` (session và rate limit storage), `qdrant` (vector database), và `nginx` (reverse proxy & load balancer).
- **Cách các service giao tiếp:** Nginx tiếp nhận các kết nối bên ngoài tại cổng 80/443 và phân phối traffic đến các instance `agent` chạy ngầm. Các agent giao tiếp nội bộ với `redis` và `qdrant` qua mạng Docker internal.
- **Vẽ sơ đồ luồng traffic:**
```
Client (Cổng 80/443)
       │
       ▼
 ┌───────────┐
 │   Nginx   │ (Reverse Proxy & Load Balancer)
 └─────┬─────┘
       ├───────────────────────┐
       ▼ (Round-Robin)         ▼ (Round-Robin)
 ┌───────────┐           ┌───────────┐
 │  Agent 1  │           │  Agent 2  │ (Stateless FastAPI)
 └─────┬─────┘           └─────┬─────┘
       │                       │
       └───────────┬───────────┘
                   ├───────────────────────┐
                   ▼                       ▼
             ┌───────────┐           ┌───────────┐
             │   Redis   │           │  Qdrant   │ (Vector Store)
             │  (Cache)  │           └───────────┘
             └───────────┘
```

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment
- **URL:** [Hãy điền URL Railway của bạn tại đây sau khi deploy thành công]
- **Screenshot:** [Screenshots dashboard sẽ được lưu tại: `screenshots/dashboard.png`]

---

## Part 4: API Security

### Exercise 4.1-4.3: Test results
- **API Key Auth:** Khi gọi API không có header `X-API-Key` hoặc sai key, hệ thống trả về mã lỗi `401 Unauthorized` kèm thông báo lỗi cụ thể. Khi truyền key chính xác, API hoạt động bình thường (`200 OK`).
- **JWT Auth:** Sinh token thành công qua endpoint `/auth/token` với username/password hợp lệ. Sau đó dùng token dạng `Authorization: Bearer <token>` để truy cập an toàn.
- **Rate Limiting:** Sử dụng thuật toán Sliding Window lưu trữ trong Redis/In-memory. Khi gửi request vượt quá tần suất cấu hình (ví dụ >20 requests/phút), hệ thống chặn lại và trả về mã lỗi `429 Too Many Requests`.

### Exercise 4.4: Cost guard implementation
- **Cách tiếp cận:** 
  - Tính toán số lượng tokens tiêu thụ (ước lượng dựa trên độ dài đầu vào và đầu ra của LLM).
  - Sử dụng Redis để lưu trữ và cộng dồn số tiền tiêu thụ hàng ngày/hàng tháng theo từng user bucket.
  - Trước mỗi lượt gọi LLM, kiểm tra xem tổng chi phí đã vượt ngưỡng cấu hình chưa (`daily_budget_usd`). Nếu vượt qua, chặn request và trả về lỗi `503 Service Unavailable` hoặc `402 Payment Required`.

---

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes
- **Liveness & Readiness Probes:** Endpoint `/health` kiểm tra xem container ứng dụng có đang sống không. Endpoint `/ready` kiểm tra kỹ hơn các kết nối backing services (Redis, database).
- **Graceful Shutdown:** Khi nhận tín hiệu SIGTERM (ví dụ khi platform restart hoặc scale down), ứng dụng sẽ chuyển `_is_ready` thành `False` để load balancer ngừng chuyển traffic mới vào, đồng thời chờ cho các in-flight requests hiện tại xử lý xong hoàn toàn trước khi dừng tiến trình chính.
- **Stateless Design:** Lưu trữ toàn bộ lịch sử trò chuyện (conversation history) và session data vào cụm Redis tập trung thay vì lưu ở bộ nhớ trong (in-memory) của từng container. Nhờ vậy, load balancer có thể phân phối request của cùng một user đến bất kỳ instance nào mà không làm mất hội thoại.
