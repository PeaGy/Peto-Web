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
        var monHoc = _store.All().First(m => m.Id == id);
        return monHoc;
    }

    [HttpPost]
    public ActionResult<MonHoc> Create(MonHocDto dto)
    {
        var monHoc = _store.Add(dto.Ten ?? "", dto.SoTinChi);
        return CreatedAtAction(nameof(GetById), new { id = monHoc.Id }, monHoc);
    }
}
