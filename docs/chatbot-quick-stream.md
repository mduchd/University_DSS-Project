# Chatbot: câu hỏi nhanh, trả lời theo luồng và Markdown

## Người dùng nhìn thấy gì

Trong panel trợ lý có bốn câu hỏi mẫu. Bấm một chip sẽ gửi đúng câu hỏi đó như khi người dùng tự gõ; hồ sơ tổ hợp, ba điểm và sở thích đang nhập được gửi kèm. Người dùng có thể bấm **Dừng** trong lúc AI trả lời.

Trả lời hiện dần theo từng đoạn nhỏ. Danh sách, chữ đậm, tiêu đề, mã, liên kết và bảng Markdown được định dạng ngay trong bong bóng chat. Bảng làm khung chat rộng hơn trên laptop; trên màn hình hẹp, người dùng cuộn ngang để xem đủ cột. Nếu thư viện Markdown không tải được, nội dung vẫn hiện dưới dạng văn bản thuần.

## Luồng xử lý

1. Browser gửi `POST /api/assistant/chat/stream` với Bearer token, câu hỏi, hồ sơ hiện tại và tối đa sáu lượt hội thoại gần nhất.
2. Flask xác minh JWT. Dịch vụ trợ lý kiểm tra câu hỏi và `DEEPSEEK_API_KEY`, rồi lấy tối đa tám bản ghi tuyển sinh phù hợp và bối cảnh việc làm từ dữ liệu DSS. Điểm/tổ hợp nêu trong câu hỏi được ưu tiên hơn hồ sơ đang nhập; câu hỏi IT/CNTT chỉ nhận các ngành máy tính liên quan và nhóm việc làm CNTT.
3. Backend gọi DeepSeek Chat Completions với `stream: true`. DeepSeek trả các sự kiện SSE `data: ...` chứa `choices[0].delta.content` và kết thúc bằng `data: [DONE]`.
4. Backend chỉ chuyển phần `content` thành các sự kiện `ready`, `delta`, `done` hoặc `error` của riêng ứng dụng. API key luôn ở server; `reasoning_content` không được đưa ra giao diện.
5. Browser dùng `fetch()` và `ReadableStream` để đọc POST theo từng chunk. Bộ giải mã UTF-8 ghép chunk, tách frame SSE tại `\n\n`, ghép `delta.text` thành một câu trả lời và cập nhật giao diện theo nhịp khung hình.
6. Marked chuyển Markdown thành HTML; DOMPurify làm sạch HTML và chỉ cho phép các thẻ/thuộc tính cần thiết trước khi chèn vào DOM. Nội dung người dùng luôn dùng `textContent`.

Route JSON cũ `/api/assistant/chat` vẫn hoạt động cho client chưa chuyển sang streaming. Nếu route streaming chưa có trên backend (404/405), giao diện tự dùng route JSON. Nếu lỗi xảy ra trước khi stream bắt đầu, API trả JSON với mã lỗi phù hợp. Nếu kết nối bị ngắt giữa chừng, stream phát sự kiện `error` và giao diện giữ phần trả lời đã nhận kèm thông báo. Nút **Dừng** dùng `AbortController` để hủy yêu cầu.

## Tại sao chọn cách này

- Chip giúp người mới biết chatbot có thể hỏi gì, và dùng đúng hồ sơ đang nhập thay vì yêu cầu gõ lại.
- `fetch()` đọc stream phù hợp với route POST cần JSON và Bearer token; `EventSource` chuẩn chỉ mở GET.
- Proxy SSE giảm thời gian chờ cảm nhận được và giữ key LLM ở backend.
- Render lại Markdown từ **toàn bộ văn bản đã nhận** thay vì định dạng từng token riêng lẻ, vì cú pháp như `**chữ đậm**` hoặc danh sách có thể bị chia giữa hai chunk.
- Làm sạch HTML bảo vệ giao diện trước HTML hoặc liên kết không an toàn do model sinh ra.

Streaming chỉ làm thay đổi cách hiển thị câu trả lời. Nó không đổi mô hình dự báo điểm chuẩn hay biến kết quả thành xác suất trúng tuyển. Khả năng hiện từng đoạn trên bản Vercel/Render cần được kiểm tra sau deploy vì proxy trung gian có thể gom các chunk.
