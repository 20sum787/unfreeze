param(
    [Parameter(Mandatory = $true)] [string] $VideoPath,
    [string] $OutputDirectory,
    [double] $Step = 0,
    [double] $Offset = 0.15,
    [double] $Limit = 0,
    [string] $TimestampFile,
    [int] $Width = 432
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$storageFileType = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$mediaClipType = [Windows.Media.Editing.MediaClip,Windows.Media.Editing,ContentType=WindowsRuntime]
$compositionType = [Windows.Media.Editing.MediaComposition,Windows.Media.Editing,ContentType=WindowsRuntime]
$imageStreamType = [Windows.Media.Editing.ImageStream,Windows.Media.Editing,ContentType=WindowsRuntime]
$precision = [Windows.Media.Editing.VideoFramePrecision,Windows.Media.Editing,ContentType=WindowsRuntime]::NearestFrame
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1

function Get-WinRtResult($Operation, $ResultType) {
    $task = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    return $task.GetAwaiter().GetResult()
}

$video = Get-WinRtResult ($storageFileType::GetFileFromPathAsync($VideoPath)) $storageFileType
$clip = Get-WinRtResult ($mediaClipType::CreateFromFileAsync($video)) $mediaClipType
$props = $clip.GetVideoEncodingProperties()
$duration = $clip.OriginalDuration.TotalSeconds
[pscustomobject]@{
    duration_s = $duration
    width = $props.Width
    height = $props.Height
    fps_numerator = $props.FrameRate.Numerator
    fps_denominator = $props.FrameRate.Denominator
} | ConvertTo-Json -Compress

if (-not $OutputDirectory) { exit 0 }
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$composition = New-Object -TypeName $compositionType.FullName
$composition.Clips.Add($clip)
$invariant = [System.Globalization.CultureInfo]::InvariantCulture
if ($TimestampFile) {
    $timestamps = Get-Content -LiteralPath $TimestampFile | Where-Object { $_.Trim() } | ForEach-Object { [double]::Parse($_, $invariant) }
} else {
    if ($Step -le 0) { throw 'Step must be positive.' }
    $end = $duration - 0.05
    if ($Limit -gt 0) { $end = [math]::Min($end, $Limit) }
    $timestamps = for ($seconds = $Offset; $seconds -lt $end; $seconds += $Step) { $seconds }
}

foreach ($seconds in $timestamps) {
    $name = 't{0:0000000}.jpg' -f [int][math]::Round($seconds * 1000)
    $outputPath = Join-Path $OutputDirectory $name
    $timeCode = [TimeSpan]::FromSeconds($seconds)
    $thumbnail = Get-WinRtResult ($composition.GetThumbnailAsync($timeCode, $Width, 0, $precision)) $imageStreamType
    $buffer = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($thumbnail.GetInputStreamAt(0))
    $target = [System.IO.File]::Create($outputPath)
    try { $buffer.CopyTo($target) }
    finally {
        $target.Dispose()
        $buffer.Dispose()
        $thumbnail.Dispose()
    }
}
