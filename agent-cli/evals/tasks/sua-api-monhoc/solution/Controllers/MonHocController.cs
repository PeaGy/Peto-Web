using Microsoft.AspNetCore.Mvc;
using MonHocApi.Dto;
using MonHocApi.Models;
using MonHocApi.Services;

namespace MonHocApi.Controllers;

[ApiController]
[Route("api/monhoc")]
public class MonHocController : ControllerBase
{
    private readonly MonHocStore _store;

    public MonHocController(MonHocStore store)
    {
        _store = store;
    }

    [HttpGet]
    public List<MonHoc> GetAll() => _store.All();

    [HttpGet("{id:int}")]
    public ActionResult<MonHoc> GetById(int id)
    {
        var monHoc = _store.All().FirstOrDefault(m => m.Id == id);
        if (monHoc is null)
        {
            return NotFound();
        }
        return monHoc;
    }

    [HttpPost]
    public ActionResult<MonHoc> Create(MonHocDto dto)
    {
        if (string.IsNullOrWhiteSpace(dto.Ten))
        {
            return BadRequest("Tên môn học không được trống");
        }
        var monHoc = _store.Add(dto.Ten.Trim(), dto.SoTinChi);
        return CreatedAtAction(nameof(GetById), new { id = monHoc.Id }, monHoc);
    }
}
