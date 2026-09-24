# inventory

Quản lý kho hàng nhỏ của cửa hàng: xem tồn kho, báo hàng sắp hết, tìm theo mã hàng.

## Dữ liệu

Kho lưu trong một file JSON (mặc định `data/kho.json`):

```json
{
  "items": [
    {"sku": "A-100", "name": "Bút bi xanh", "qty": 120, "price": 5000}
  ]
}
```

| Khóa | Nghĩa |
|---|---|
| `sku` | mã hàng, không phân biệt hoa thường khi tìm |
| `name` | tên hàng |
| `qty` | số lượng tồn |
| `price` | giá bán (đồng) |

## Dùng

    python -m inventory list                   # cả kho và tổng giá trị
    python -m inventory low --threshold 10     # hàng còn từ 10 trở xuống
    python -m inventory find --sku a-100       # tìm theo mã hàng

## Chạy test

    python -m unittest
