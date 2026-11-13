$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $root 'runtime\windows'
$python = Join-Path $runtime 'python.exe'
$sitePackages = Join-Path $runtime 'Lib\site-packages'
$pythonZipUrl = 'https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip'
$pythonZipSha256 = '90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159'
$wheels = @(
    @{
        Name = 'openpyxl-3.1.5-py2.py3-none-any.whl'
        Url = 'https://files.pythonhosted.org/packages/c0/da/977ded879c29cbd04de313843e76868e6e13408a94ed6b987245dc7c8506/openpyxl-3.1.5-py2.py3-none-any.whl'
        Sha256 = '5282c12b107bffeef825f4617dc029afaf41d0ea60823bbb665ef3079dc79de2'
    }
    @{
        Name = 'et_xmlfile-2.0.0-py3-none-any.whl'
        Url = 'https://files.pythonhosted.org/packages/c1/8b/5fe2cc11fee489817272089c4203e679c63b570a5aaeb18d852ae3cbba6a/et_xmlfile-2.0.0-py3-none-any.whl'
        Sha256 = '7a91720bc756843502c3b7504c77b8fe44217c85c537d85037f0f536151b2caa'
    }
)

$work = Join-Path $env:TEMP ('inspection-app-bootstrap-' + [guid]::NewGuid().ToString('N'))
$stage = Join-Path (Split-Path -Parent $runtime) ('.windows-runtime-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $work | Out-Null

try {
    $marker = Join-Path $runtime '.embedded-runtime'
    $openpyxlPath = Join-Path $sitePackages 'openpyxl'
    $etXmlfilePath = Join-Path $sitePackages 'et_xmlfile'
    if ((Test-Path -LiteralPath $marker) -and (Test-Path -LiteralPath $python) -and
        (Test-Path -LiteralPath $openpyxlPath) -and (Test-Path -LiteralPath $etXmlfilePath)) {
        & $python -I -c 'import openpyxl, et_xmlfile'
        if ($LASTEXITCODE -eq 0) {
            Write-Host 'The embedded Python runtime and dependencies are ready.'
            exit 0
        }
    }

    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if (-not $curl) {
        throw 'Windows curl.exe is unavailable. Connect this device to your organization-approved package source or use the prepared Windows ZIP.'
    }

    $pythonZip = Join-Path $work 'python-3.14.10-embed-amd64.zip'
    Write-Host 'Downloading the official Python 3.14.10 embeddable ZIP...'
    & $curl.Source --fail --location --silent --show-error --ssl-no-revoke --output $pythonZip $pythonZipUrl
    if ($LASTEXITCODE -ne 0) {
        throw 'Python download failed. Check network access to python.org and try again.'
    }
    $actualPythonSha256 = (Get-FileHash -LiteralPath $pythonZip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualPythonSha256 -ne $pythonZipSha256) {
        throw 'The Python ZIP checksum did not match. The downloaded file was rejected.'
    }

    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    Expand-Archive -LiteralPath $pythonZip -DestinationPath $stage -Force
    $pth = Get-ChildItem -LiteralPath $stage -Filter 'python*._pth' | Select-Object -First 1
    if (-not $pth) {
        throw 'The Python archive did not contain its expected embeddable path configuration.'
    }
    @(
        'python314.zip'
        '.'
        'Lib\site-packages'
        'import site'
    ) | Set-Content -LiteralPath $pth.FullName -Encoding ASCII

    $stageSitePackages = Join-Path $stage 'Lib\site-packages'
    New-Item -ItemType Directory -Force -Path $stageSitePackages | Out-Null
    foreach ($wheel in $wheels) {
        $wheelPath = Join-Path $work $wheel.Name
        Write-Host "Downloading $($wheel.Name)..."
        & $curl.Source --fail --location --silent --show-error --ssl-no-revoke --output $wheelPath $wheel.Url
        if ($LASTEXITCODE -ne 0) {
            throw "Dependency download failed for $($wheel.Name). Check network access to files.pythonhosted.org and try again."
        }
        $actualWheelSha256 = (Get-FileHash -LiteralPath $wheelPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualWheelSha256 -ne $wheel.Sha256) {
            throw "The checksum for $($wheel.Name) did not match. The downloaded file was rejected."
        }
        $wheelArchive = Join-Path $work ($wheel.Name + '.zip')
        Copy-Item -LiteralPath $wheelPath -Destination $wheelArchive
        Expand-Archive -LiteralPath $wheelArchive -DestinationPath $stageSitePackages -Force
    }

    & (Join-Path $stage 'python.exe') -I -c 'import openpyxl, et_xmlfile'
    if ($LASTEXITCODE -ne 0) {
        throw 'The embeddable runtime could not load the spreadsheet dependencies.'
    }
    Set-Content -LiteralPath (Join-Path $stage '.embedded-runtime') -Value 'Python 3.14.10 embeddable x64' -Encoding ASCII

    if (Test-Path -LiteralPath $runtime) {
        $oldRuntime = Join-Path (Split-Path -Parent $runtime) ('.windows-runtime-old-' + [guid]::NewGuid().ToString('N'))
        Move-Item -LiteralPath $runtime -Destination $oldRuntime
        try {
            Move-Item -LiteralPath $stage -Destination $runtime
        }
        catch {
            Move-Item -LiteralPath $oldRuntime -Destination $runtime
            throw
        }
        Remove-Item -LiteralPath $oldRuntime -Recurse -Force
    }
    else {
        Move-Item -LiteralPath $stage -Destination $runtime
    }

    Write-Host 'The portable Python runtime is ready. No Python installer or administrator access was used.'
}
catch {
    $location = if ($_.InvocationInfo.ScriptLineNumber) { " (line $($_.InvocationInfo.ScriptLineNumber))" } else { '' }
    Write-Host "First-run setup error$location`: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    if (Test-Path -LiteralPath $work) {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $stage) {
        Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
    }
}

exit 0
