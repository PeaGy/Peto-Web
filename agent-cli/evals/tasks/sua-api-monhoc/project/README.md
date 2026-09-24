# MonHocApi

API quản lý môn học (bài tập ASP.NET Core, lưu trong bộ nhớ).

## Chạy

    dotnet run

API nghe ở http://localhost:5080.

| Phương thức | Đường dẫn | Việc |
|---|---|---|
| GET | /api/monhoc | danh sách môn học |
| GET | /api/monhoc/{id} | một môn học |
| POST | /api/monhoc | thêm môn học, body `{"ten": "...", "soTinChi": 3}` |
