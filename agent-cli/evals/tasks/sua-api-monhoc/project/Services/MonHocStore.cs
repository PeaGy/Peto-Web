using MonHocApi.Models;

namespace MonHocApi.Services;

/// <summary>Lưu môn học trong bộ nhớ (bài tập chưa cần database).</summary>
public class MonHocStore
{
    private readonly List<MonHoc> _items = new()
    {
        new MonHoc { Id = 1, Ten = "Lập trình C#", SoTinChi = 3 },
        new MonHoc { Id = 2, Ten = "Cơ sở dữ liệu", SoTinChi = 3 },
        new MonHoc { Id = 3, Ten = "Toán rời rạc", SoTinChi = 2 },
    };

    private readonly object _lock = new();

    public List<MonHoc> All()
    {
        lock (_lock)
        {
            return _items.ToList();
        }
    }

    public MonHoc Add(string ten, int soTinChi)
    {
        lock (_lock)
        {
            var monHoc = new MonHoc { Id = _items.Max(m => m.Id) + 1, Ten = ten, SoTinChi = soTinChi };
            _items.Add(monHoc);
            return monHoc;
        }
    }
}
