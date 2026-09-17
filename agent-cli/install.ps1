# Bộ cài một dòng cho lệnh peto (Peto Agent) trên Windows:
#
#     irm https://<địa chỉ Peto>/install.ps1 | iex
#
# Máy chủ Peto phục vụ tệp này tại /install.ps1 và điền địa chỉ Peto, đường dẫn tải gói cùng mã băm của gói vào các
# biến ở đầu khối bên dưới. Bộ cài chỉ đụng tới tài khoản Windows đang dùng, không cần quyền quản trị:
#   1. Tìm Python 3.12 trở lên qua lệnh py hoặc python.
#   2. Tải gói peto từ chính máy chủ Peto và so mã băm SHA-256.
#   3. Cài gói vào môi trường Python riêng ở %LOCALAPPDATA%\PetoAgent\venv.
#   4. Chép peto.exe sang %LOCALAPPDATA%\PetoAgent\bin rồi thêm thư mục đó vào PATH của tài khoản.
# Tùy chọn qua biến môi trường: PETO_AGENT_INSTALL_DIR đổi nơi cài; PETO_AGENT_NO_MODIFY_PATH=1 để không sửa PATH.
#
# Mọi thứ nằm trong một khối & { } để biến và hàm không sót lại trong cửa sổ PowerShell của người dùng. Không dùng
# exit: chạy qua iex thì exit đóng luôn cửa sổ đó.

& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'

    $PetoServer = '__PETO_SERVER__'
    $WheelUrl = '__PETO_WHEEL_URL__'
    $WheelName = '__PETO_WHEEL_NAME__'
    $WheelSha256 = '__PETO_WHEEL_SHA256__'
    $MinPython = [version]'3.12'

    function Write-PetoStep([string]$Text) {
        Write-Host "  $Text" -ForegroundColor DarkGray
    }

    function Write-PetoError([string]$Text) {
        Write-Host "✗ $Text" -ForegroundColor Red
    }

    # Chạy chương trình ngoài, gom cả stdout lẫn stderr. PowerShell 5.1 coi mỗi dòng stderr là lỗi và dừng hẳn khi
    # ErrorActionPreference là Stop, nên trong hàm này hạ xuống Continue rồi tự xem mã thoát.
    function Invoke-PetoNative([string]$FilePath, [string[]]$Arguments) {
        $ErrorActionPreference = 'Continue'
        $lines = & $FilePath @Arguments 2>&1 | ForEach-Object { "$_" }
        [pscustomobject]@{ Code = $LASTEXITCODE; Output = (@($lines) -join "`n").Trim() }
    }

    # Python mới nhất gọi được qua py -3 hoặc python; $null nếu máy chưa có. Giữ lại lệnh gọi thay vì đường dẫn:
    # đường dẫn in qua ống dẫn có thể vỡ dấu khi tên tài khoản Windows có tiếng Việt.
    function Find-PetoPython {
        $probe = "import sys; print('%d.%d' % (sys.version_info[0], sys.version_info[1]))"
        $best = $null
        foreach ($candidate in @(@('py', '-3'), @('python'))) {
            if (-not (Get-Command $candidate[0] -CommandType Application -ErrorAction SilentlyContinue)) { continue }
            $prefix = @($candidate | Select-Object -Skip 1)
            $result = Invoke-PetoNative $candidate[0] ($prefix + @('-c', $probe))
            if ($result.Code -ne 0) { continue }
            $line = @($result.Output -split "`n" | Where-Object { $_.Trim() -match '^\d+\.\d+$' }) | Select-Object -Last 1
            if (-not $line) { continue }
            $found = [pscustomobject]@{ Version = [version]$line.Trim(); Command = $candidate[0]; Prefix = $prefix }
            if (-not $best -or $found.Version -gt $best.Version) { $best = $found }
        }
        return $best
    }

    function Test-PetoVenv([string]$Python) {
        if (-not (Test-Path -LiteralPath $Python)) { return $false }
        $check = 'import sys, pip; sys.exit(0 if sys.version_info >= (3, 12) else 1)'
        return (Invoke-PetoNative $Python @('-c', $check)).Code -eq 0
    }

    # peto.exe đang chạy thì không ghi đè được nhưng vẫn đổi tên được: dời bản cũ sang tên khác rồi xóa. Bản còn đang
    # chạy thì xóa không được, để lần cài sau dọn.
    function Copy-PetoLauncher([string]$Source, [string]$Bin) {
        New-Item -ItemType Directory -Force -Path $Bin | Out-Null
        $target = Join-Path $Bin 'peto.exe'
        if (Test-Path -LiteralPath $target) {
            $old = Join-Path $Bin ('peto-old-' + [guid]::NewGuid().ToString('N') + '.exe')
            Move-Item -LiteralPath $target -Destination $old
        }
        Copy-Item -LiteralPath $Source -Destination $target
        Get-ChildItem -LiteralPath $Bin -Filter 'peto-old-*.exe' | Remove-Item -Force -ErrorAction SilentlyContinue
    }

    # Nối thư mục vào chuỗi PATH nếu chưa có, so không phân biệt hoa thường và bỏ dấu \ cuối; $null nếu đã có.
    function Join-PetoPath([string]$Current, [string]$Directory) {
        $wanted = $Directory.TrimEnd('\')
        foreach ($entry in $Current -split ';') {
            if ($entry -and [Environment]::ExpandEnvironmentVariables($entry).TrimEnd('\') -ieq $wanted) { return $null }
        }
        if (-not $Current.Trim(';')) { return $Directory }
        return $Current.TrimEnd(';') + ';' + $Directory
    }

    function Add-PetoPath([string]$Directory) {
        $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Environment')
        try {
            # Đọc PATH chưa mở rộng để giữ nguyên các mục dạng %USERPROFILE%\..., rồi ghi lại đúng kiểu giá trị cũ.
            $options = [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames
            $current = [string]$key.GetValue('Path', '', $options)
            $updated = Join-PetoPath $current $Directory
            if ($null -eq $updated) { return $false }
            $kind = [Microsoft.Win32.RegistryValueKind]::ExpandString
            if ($current -and $key.GetValueKind('Path') -eq [Microsoft.Win32.RegistryValueKind]::String) {
                $kind = [Microsoft.Win32.RegistryValueKind]::String
            }
            $key.SetValue('Path', $updated, $kind)
        } finally {
            $key.Close()
        }
        # Đặt rồi xóa một biến tạm: Windows phát thông báo đổi biến môi trường, để cửa sổ mở sau nhận PATH mới.
        $notice = 'PETO_AGENT_PATH_NOTICE_' + [guid]::NewGuid().ToString('N')
        [Environment]::SetEnvironmentVariable($notice, '1', 'User')
        [Environment]::SetEnvironmentVariable($notice, [NullString]::Value, 'User')
        return $true
    }

    function Install-Peto {
        if ($env:OS -ne 'Windows_NT') {
            Write-PetoError 'Bộ cài này dành cho Windows. Máy khác thì cài từ mã nguồn theo agent-cli/README.md.'
            return
        }
        $source = [uri]$WheelUrl
        if ($source.Scheme -ne 'https' -and -not $source.IsLoopback) {
            Write-PetoError 'Chỉ cài peto qua HTTPS.'
            return
        }

        $python = Find-PetoPython
        if (-not $python -or $python.Version -lt $MinPython) {
            if ($python) {
                Write-PetoError "Python $($python.Version) đã cũ: Peto cần Python 3.12 trở lên."
            } else {
                Write-PetoError 'Chưa tìm thấy Python trên máy này: Peto cần Python 3.12 trở lên.'
            }
            Write-Host '  Cài Python bằng lệnh: winget install -e --id Python.Python.3.14'
            Write-Host '  (hoặc tải ở https://www.python.org/downloads/), rồi mở cửa sổ PowerShell mới và chạy lại lệnh cài Peto.'
            return
        }

        $root = $env:PETO_AGENT_INSTALL_DIR
        if (-not $root) { $root = Join-Path $env:LOCALAPPDATA 'PetoAgent' }
        $venv = Join-Path $root 'venv'
        $venvPython = Join-Path $venv 'Scripts\python.exe'
        $bin = Join-Path $root 'bin'
        $launcher = Join-Path $bin 'peto.exe'

        Write-Host "Cài peto từ $PetoServer"
        $temp = Join-Path ([IO.Path]::GetTempPath()) ('peto-install-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $temp | Out-Null
        try {
            Write-PetoStep "Tải $WheelName"
            # Windows PowerShell 5.1 trên máy cũ có thể chưa bật TLS 1.2.
            [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor
                [Net.SecurityProtocolType]::Tls12
            $wheel = Join-Path $temp $WheelName
            Invoke-WebRequest -Uri $WheelUrl -OutFile $wheel -UseBasicParsing
            if ((Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash -ne $WheelSha256) {
                Write-PetoError 'Gói tải về không khớp mã băm, có thể máy chủ vừa cập nhật. Chạy lại lệnh cài nhé.'
                return
            }

            if (-not (Test-PetoVenv $venvPython)) {
                Write-PetoStep "Tạo môi trường Python riêng (Python $($python.Version))"
                $result = Invoke-PetoNative $python.Command ($python.Prefix + @('-m', 'venv', '--clear', $venv))
                if ($result.Code -ne 0) {
                    Write-PetoError "Không tạo được môi trường Python ở $venv."
                    Write-Host $result.Output
                    return
                }
            }

            Write-PetoStep 'Cài peto vào môi trường đó'
            $pip = @('-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', '--no-index', '--no-deps',
                '--force-reinstall', $wheel)
            $result = Invoke-PetoNative $venvPython $pip
            if ($result.Code -ne 0) {
                Write-PetoError 'pip không cài được peto. Đóng các cửa sổ đang chạy peto rồi chạy lại lệnh cài.'
                Write-Host $result.Output
                return
            }
            Copy-PetoLauncher (Join-Path $venv 'Scripts\peto.exe') $bin
        } finally {
            Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
        }

        $version = Invoke-PetoNative $launcher @('--version')
        if ($version.Code -ne 0) {
            Write-PetoError 'Đã cài nhưng peto.exe không chạy được.'
            Write-Host $version.Output
            return
        }

        $pathNote = ''
        if ($env:PETO_AGENT_NO_MODIFY_PATH) {
            $pathNote = "Chưa thêm vào PATH vì có PETO_AGENT_NO_MODIFY_PATH; gọi bằng đường dẫn đầy đủ: $launcher"
        } else {
            if (Add-PetoPath $bin) {
                $pathNote = 'Đã thêm peto vào PATH. Các cửa sổ dòng lệnh đang mở khác cần mở lại mới gõ được peto.'
            }
            $session = @($env:Path -split ';' | ForEach-Object { $_.TrimEnd('\') })
            if ($session -notcontains $bin.TrimEnd('\')) { $env:Path = $env:Path.TrimEnd(';') + ';' + $bin }
        }

        Write-Host "✓ Đã cài $($version.Output) vào $root" -ForegroundColor Green
        if ($pathNote) { Write-Host "  $pathNote" }
        Write-Host ''
        Write-Host 'Bước tiếp theo:'
        Write-Host '  peto login   kết nối máy này với tài khoản Peto (Discord hoặc Google)'
        Write-Host '  cd <thư mục dự án>'
        Write-Host '  peto         bắt đầu nhờ Peto sửa code'
    }

    try {
        Install-Peto
    } catch {
        Write-PetoError "Cài không xong: $($_.Exception.Message)"
    }
}
