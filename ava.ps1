param(
    [Parameter(Position = 0)]
    [string]$Channel = "etv"
)

$ErrorActionPreference = "Stop"

$key = $Channel.ToLowerInvariant() -replace "\+", "pluss"
if ($key -notin @("etv", "etv2", "etvpluss")) {
    Write-Error "Tundmatu kanal '$Channel'. Kasuta: etv, etv2, etvpluss"
}

$proxy = Join-Path $PSScriptRoot "err_proxy.py"
$portOpen = $false
try {
    $client = New-Object System.Net.Sockets.TcpClient
    $client.Connect("127.0.0.1", 8765)
    $client.Close()
    $portOpen = $true
} catch {
    $portOpen = $false
}

if (-not $portOpen) {
    $python = Get-Command py -ErrorAction SilentlyContinue
    if ($python) {
        Start-Process -FilePath $python.Source -ArgumentList @("-3", $proxy) -WindowStyle Hidden -WorkingDirectory $PSScriptRoot
    } else {
        Start-Process -FilePath "python" -ArgumentList @($proxy) -WindowStyle Hidden -WorkingDirectory $PSScriptRoot
    }
    $ready = $false
    foreach ($try in 1..20) {
        Start-Sleep -Milliseconds 250
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $client.Connect("127.0.0.1", 8765)
            $client.Close()
            $ready = $true
            break
        } catch {
            $ready = $false
        }
    }
    if (-not $ready) {
        Write-Error "Kohalik voog ei käivitunud."
    }
}

$vlc = Join-Path ${env:ProgramFiles} "VideoLAN\VLC\vlc.exe"
if (-not (Test-Path $vlc)) {
    Write-Error "VLC ei ole kaustas $vlc"
}

$url = "http://127.0.0.1:8765/$key.m3u8"
Start-Process -FilePath $vlc -ArgumentList @("--no-one-instance", "--no-qt-privacy-ask", $url)
Write-Output $url
