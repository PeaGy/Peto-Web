$ErrorActionPreference = 'Stop'
$runner = Join-Path $PSScriptRoot '..\local-tts\.runtime\venv-fast\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $runner)) { throw 'Chưa cài bộ chạy giọng nói venv-fast.' }
if (-not $env:PETO_VOICE_SERVER_URL) {
    $env:PETO_VOICE_SERVER_URL = Read-Host 'Địa chỉ HTTPS của web Peto'
}
if (-not $env:PETO_VOICE_WORKER_TOKEN) {
    $secret = Read-Host 'Khóa PETO_VOICE_WORKER_TOKEN đã đặt trên VPS (nội dung được ẩn)' -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try { $env:PETO_VOICE_WORKER_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}
& $runner -u (Join-Path $PSScriptRoot 'relay.py')
