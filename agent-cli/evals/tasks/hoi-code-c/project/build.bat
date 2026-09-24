@echo off
rem Build bằng MSVC: mở "Developer Command Prompt" rồi chạy build.bat
cl /nologo /O2 /W3 /Iinclude src\main.c src\http.c src\net.c src\sync.c ws2_32.lib /Fe:sas-net.exe
