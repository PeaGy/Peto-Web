using MonHocApi.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddSingleton<MonHocStore>();

var app = builder.Build();

app.MapControllers();

app.Run();
