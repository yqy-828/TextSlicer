[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [Alias("InputPsd")]
    [string]$InputPath,

    [string]$MappingJson,

    [string]$WorkDir,

    [string]$Python = "python",

    [switch]$AtlasToPsd,

    [string]$OutputPsd,

    [int]$CanvasWidth,

    [switch]$NoPack,

    [int]$AtlasMaxWidth = 2048,

    [int]$AtlasMaxHeight = 2048,

    [switch]$KeepWorkDir
)

Set-StrictMode -Version 3.0
$ErrorActionPreference = "Stop"

function ConvertTo-JsxString {
    param([Parameter(Mandatory = $true)][string]$Value)
    $escaped = $Value.Replace("\", "/").Replace("\", "\\").Replace('"', '\"')
    return '"' + $escaped + '"'
}

function Invoke-Python {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE."
    }
}

function Invoke-PythonJson {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $output = & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE."
    }
    return ($output | Out-String | ConvertFrom-Json)
}

function Get-PhotoshopProgIds {
    $progIds = New-Object System.Collections.Generic.List[string]
    try {
        $curVer = (Get-ItemProperty -LiteralPath "Registry::HKEY_CLASSES_ROOT\Photoshop.Application\CurVer" -ErrorAction Stop)."(default)"
        if (-not [string]::IsNullOrWhiteSpace($curVer)) {
            $progIds.Add($curVer)
        }
    } catch {
    }
    $progIds.Add("Photoshop.Application")
    return @($progIds | Select-Object -Unique)
}

function New-PhotoshopApplication {
    $errors = @()
    foreach ($progId in (Get-PhotoshopProgIds)) {
        try {
            Write-Host "Connecting to $progId..."
            return New-Object -ComObject $progId
        } catch {
            $errors += "${progId}: $($_.Exception.Message)"
        }
    }

    throw "Unable to create Photoshop COM application. Tried: $($errors -join '; ')"
}

function Get-PhotoshopExecutable {
    $appPath = Get-ItemProperty -LiteralPath "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Photoshop.exe" -ErrorAction SilentlyContinue
    if ($appPath -and $appPath."(default)" -and (Test-Path -LiteralPath $appPath."(default)")) {
        return $appPath."(default)"
    }

    $command = Get-Command Photoshop.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "Unable to find Photoshop.exe for JSX fallback execution."
}

function Wait-ForFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [datetime]$UpdatedAfter = [datetime]::MinValue,
        [int]$TimeoutSeconds = 300
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $Path) {
            $item = Get-Item -LiteralPath $Path
            if ($item.Length -gt 0 -and $item.LastWriteTime -ge $UpdatedAfter) {
                Start-Sleep -Milliseconds 500
                return
            }
        }
        Start-Sleep -Seconds 1
    }
    throw "Timed out waiting for Photoshop to create: $Path"
}

function Invoke-PhotoshopJsxFallback {
    param(
        [Parameter(Mandatory = $true)][string]$RunnerPath,
        [Parameter(Mandatory = $true)][string]$WaitPath,
        [datetime]$UpdatedAfter = [datetime]::MinValue
    )
    $photoshopExe = Get-PhotoshopExecutable
    Write-Host "Launching Photoshop.exe JSX fallback..."
    $argumentList = '"' + $RunnerPath + '"'
    Start-Process -FilePath $photoshopExe -ArgumentList $argumentList -WindowStyle Hidden | Out-Null
    Wait-ForFile -Path $WaitPath -UpdatedAfter $UpdatedAfter -TimeoutSeconds 300
}

function Invoke-PhotoshopJsxViaVbs {
    param(
        [Parameter(Mandatory = $true)][string]$RunnerPath,
        [Parameter(Mandatory = $true)][string]$WaitPath,
        [datetime]$UpdatedAfter = [datetime]::MinValue
    )

    $vbsPath = Join-Path (Split-Path -Parent $RunnerPath) "run_photoshop_jsx.vbs"
    $progIdArray = (Get-PhotoshopProgIds | ForEach-Object { '"' + $_.Replace('"', '""') + '"' }) -join ","
    $vbs = @"
On Error Resume Next
Dim progIds, app, i
progIds = Array($progIdArray)
For i = 0 To UBound(progIds)
  Err.Clear
  Set app = CreateObject(progIds(i))
  If Err.Number = 0 Then Exit For
Next
If app Is Nothing Then
  WScript.Echo "Unable to create Photoshop COM application: " & Err.Description
  WScript.Quit 1
End If
Err.Clear
app.DoJavaScriptFile WScript.Arguments(0)
If Err.Number <> 0 Then
  WScript.Echo "DoJavaScriptFile failed: " & Err.Description
  WScript.Quit 2
End If
"@
    Set-Content -LiteralPath $vbsPath -Value $vbs -Encoding ASCII
    Write-Host "Running Photoshop JSX through cscript late binding..."
    & cscript.exe //nologo $vbsPath $RunnerPath
    if ($LASTEXITCODE -ne 0) {
        throw "cscript Photoshop JSX execution failed with exit code $LASTEXITCODE."
    }
    Wait-ForFile -Path $WaitPath -UpdatedAfter $UpdatedAfter -TimeoutSeconds 300
}

function Invoke-PhotoshopRunner {
    param(
        [Parameter(Mandatory = $true)][string]$RunnerPath,
        [Parameter(Mandatory = $true)][string]$WaitPath
    )

    $startedAt = (Get-Date).AddSeconds(-2)

    try {
        $photoshop = New-PhotoshopApplication
        $result = $photoshop.DoJavaScriptFile($RunnerPath)
        if ($result) {
            Write-Host $result
        }
        Wait-ForFile -Path $WaitPath -UpdatedAfter $startedAt -TimeoutSeconds 300
    } catch {
        Write-Warning "Photoshop COM script execution failed: $($_.Exception.Message)"
        try {
            Invoke-PhotoshopJsxViaVbs -RunnerPath $RunnerPath -WaitPath $WaitPath -UpdatedAfter $startedAt
        } catch {
            Write-Warning "VBScript Photoshop execution failed: $($_.Exception.Message)"
            Invoke-PhotoshopJsxFallback -RunnerPath $RunnerPath -WaitPath $WaitPath -UpdatedAfter $startedAt
        }
    }
}

function Invoke-PackAtlas {
    param(
        [Parameter(Mandatory = $true)][string]$SlicesDir,
        [Parameter(Mandatory = $true)][string]$AtlasPath,
        [Parameter(Mandatory = $true)][string]$DataPath,
        [Parameter(Mandatory = $true)][string]$SourcePath
    )

    if ($NoPack) {
        return
    }

    Write-Host "Packing atlas and JSON..."
    Invoke-Python -Arguments @(
        $pythonScript,
        "pack-atlas",
        "--input-dir", $SlicesDir,
        "--atlas", $AtlasPath,
        "--data", $DataPath,
        "--source", $SourcePath,
        "--max-width", [string]$AtlasMaxWidth,
        "--max-height", [string]$AtlasMaxHeight
    )
}

$inputItem = Get-Item -LiteralPath $InputPath
$ext = $inputItem.Extension.ToLowerInvariant()
if ($ext -notin @(".png", ".psd", ".psb")) {
    throw "Input file must be .png, .psd, or .psb: $($inputItem.FullName)"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$exportJsx = Join-Path $scriptDir "export_layers.jsx"
$assembleJsx = Join-Path $scriptDir "assemble_layers.jsx"
$pythonScript = Join-Path $scriptDir "slice_text_psd.py"

foreach ($required in @($pythonScript)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing script: $required"
    }
}

$autoWorkDir = [string]::IsNullOrWhiteSpace($WorkDir)
if ($autoWorkDir) {
    $WorkDir = Join-Path ([System.IO.Path]::GetTempPath()) ("text-slicer-" + [guid]::NewGuid().ToString("N"))
}

$workItem = New-Item -ItemType Directory -Force -Path $WorkDir
$outputDir = Join-Path $inputItem.DirectoryName $inputItem.BaseName
$atlasOutputPath = Join-Path $inputItem.DirectoryName ($inputItem.BaseName + "_nub.png")
$dataOutputPath = Join-Path $inputItem.DirectoryName ($inputItem.BaseName + "_nub.json")
$inspect = Invoke-PythonJson -Arguments @($pythonScript, "inspect", "--input", $inputItem.FullName)

if ($AtlasToPsd) {
    if (-not (Test-Path -LiteralPath $assembleJsx)) {
        throw "Missing JSX script: $assembleJsx"
    }
    if ([string]::IsNullOrWhiteSpace($OutputPsd)) {
        throw "AtlasToPsd requires -OutputPsd."
    }

    $manifestPath = Join-Path $workItem.FullName "atlas_psd_manifest.json"
    $psdArgs = @(
        $pythonScript,
        "atlas-to-psd-assets",
        "--input", $inputItem.FullName,
        "--work-dir", $workItem.FullName,
        "--manifest", $manifestPath
    )
    if ($CanvasWidth -gt 0) {
        $psdArgs += @("--canvas-width", [string]$CanvasWidth)
    }
    Invoke-Python -Arguments $psdArgs

    $outputItemPath = [System.IO.Path]::GetFullPath($OutputPsd)
    $runnerPath = Join-Path $workItem.FullName "run_assemble.jsx"
    $runner = @"
var TEXT_SLICER_PSD_MANIFEST = $(ConvertTo-JsxString $manifestPath);
var TEXT_SLICER_PSD_OUTPUT = $(ConvertTo-JsxString $outputItemPath);
var TEXT_SLICER_PSD_SCRIPT = $(ConvertTo-JsxString $assembleJsx);
$.evalFile(File(TEXT_SLICER_PSD_SCRIPT));
"@
    Set-Content -LiteralPath $runnerPath -Value $runner -Encoding UTF8

    Write-Host "Building layered PSD from atlas..."
    Invoke-PhotoshopRunner -RunnerPath $runnerPath -WaitPath $outputItemPath
    Write-Host "Output PSD: $outputItemPath"

    if ($autoWorkDir -and -not $KeepWorkDir) {
        Remove-Item -LiteralPath $workItem.FullName -Recurse -Force
    } else {
        Write-Host "Kept work directory: $($workItem.FullName)"
    }
    exit 0
}

if ($inspect.kind -eq "atlas") {
    $null = New-Item -ItemType Directory -Force -Path $outputDir
    Write-Host "Detected wide atlas input. Exporting PNG slices..."
    Invoke-Python -Arguments @(
        $pythonScript,
        "atlas-finalize",
        "--input", $inputItem.FullName,
        "--output-dir", $outputDir
    )
    Invoke-PackAtlas -SlicesDir $outputDir -AtlasPath $atlasOutputPath -DataPath $dataOutputPath -SourcePath $inputItem.FullName
    Write-Host "Output folder: $outputDir"
    if (-not $NoPack) {
        Write-Host "Atlas: $atlasOutputPath"
        Write-Host "JSON: $dataOutputPath"
    }

    if ($autoWorkDir -and -not $KeepWorkDir) {
        Remove-Item -LiteralPath $workItem.FullName -Recurse -Force
    } else {
        Write-Host "Kept work directory: $($workItem.FullName)"
    }
    exit 0
}

if ($ext -notin @(".psd", ".psb")) {
    throw "Layered mode requires a .psd or .psb file: $($inputItem.FullName)"
}
if (-not (Test-Path -LiteralPath $exportJsx)) {
    throw "Missing JSX script: $exportJsx"
}

$previewDir = Join-Path $workItem.FullName "layers"
$null = New-Item -ItemType Directory -Force -Path $previewDir

$metadataPath = Join-Path $workItem.FullName "metadata.json"
$sheetPath = Join-Path $workItem.FullName "contact_sheet.png"
$templatePath = Join-Path $workItem.FullName "mapping_template.json"
$runnerPath = Join-Path $workItem.FullName "run_export.jsx"

foreach ($generatedPath in @($metadataPath, $sheetPath, $templatePath)) {
    if (Test-Path -LiteralPath $generatedPath) {
        Remove-Item -LiteralPath $generatedPath -Force
    }
}

$runner = @"
var TEXT_PSD_SLICER_INPUT = $(ConvertTo-JsxString $inputItem.FullName);
var TEXT_PSD_SLICER_EXPORT_DIR = $(ConvertTo-JsxString $previewDir);
var TEXT_PSD_SLICER_METADATA = $(ConvertTo-JsxString $metadataPath);
var TEXT_PSD_SLICER_SCRIPT = $(ConvertTo-JsxString $exportJsx);
$.evalFile(File(TEXT_PSD_SLICER_SCRIPT));
"@
Set-Content -LiteralPath $runnerPath -Value $runner -Encoding UTF8

Write-Host "Exporting full-canvas layer previews with Photoshop..."
Invoke-PhotoshopRunner -RunnerPath $runnerPath -WaitPath $metadataPath

Invoke-Python -Arguments @(
    $pythonScript,
    "make-contact-sheet",
    "--metadata", $metadataPath,
    "--preview-dir", $previewDir,
    "--sheet", $sheetPath,
    "--template", $templatePath
)

if ([string]::IsNullOrWhiteSpace($MappingJson)) {
    Write-Host ""
    Write-Host "Preview work directory: $($workItem.FullName)"
    Write-Host "Contact sheet: $sheetPath"
    Write-Host "Mapping template: $templatePath"
    Write-Host "Fill the char fields by visual inspection, then rerun with -MappingJson."
    exit 0
}

$mappingItem = Get-Item -LiteralPath $MappingJson
$null = New-Item -ItemType Directory -Force -Path $outputDir

Invoke-Python -Arguments @(
    $pythonScript,
    "finalize",
    "--metadata", $metadataPath,
    "--preview-dir", $previewDir,
    "--mapping", $mappingItem.FullName,
    "--output-dir", $outputDir
)

Invoke-PackAtlas -SlicesDir $outputDir -AtlasPath $atlasOutputPath -DataPath $dataOutputPath -SourcePath $inputItem.FullName
Write-Host "Output folder: $outputDir"
if (-not $NoPack) {
    Write-Host "Atlas: $atlasOutputPath"
    Write-Host "JSON: $dataOutputPath"
}

if ($autoWorkDir -and -not $KeepWorkDir) {
    Remove-Item -LiteralPath $workItem.FullName -Recurse -Force
} else {
    Write-Host "Kept work directory: $($workItem.FullName)"
}
