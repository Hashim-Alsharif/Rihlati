param([switch]$Convert)
# Preserve originals. Export with a separate hidden Word instance, read-only
# documents, disabled macros/links, and no recent-file entries. Never overwrite.
$ErrorActionPreference = 'Stop'
$curriculaRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'data\library\مناهج المسلمين الجدد'
$curriculaOutput = Join-Path (Split-Path -Parent $PSScriptRoot) 'data\library\curricula-pdf'
$curriculaFiles = @(Get-ChildItem -LiteralPath $curriculaRoot -File -Recurse | Where-Object { $_.Extension -in '.doc','.docx' })
if (-not $Convert) { $curriculaFiles | Select-Object FullName,Length; exit 0 }
$word = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $oldUpdateLinks = $word.Options.UpdateLinksAtOpen
    $word.Options.UpdateLinksAtOpen = $false
    foreach ($file in $curriculaFiles) {
        $relative = $file.FullName.Substring($curriculaRoot.Length).TrimStart('\')
        $target = Join-Path $curriculaOutput ([IO.Path]::ChangeExtension($relative,'.pdf'))
        if (Test-Path -LiteralPath $target) { Write-Output "PRESERVED $relative"; continue }
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        $document = $null
        try {
            $document = $word.Documents.Open($file.FullName,$false,$true,$false)
            $document.ExportAsFixedFormat($target,17)
            Write-Output "CONVERTED $relative pages=$($document.ComputeStatistics(2))"
        } finally {
            if ($null -ne $document) { $document.Close(0); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document) }
        }
    }
} finally {
    if ($null -ne $word) {
        if ($null -ne $oldUpdateLinks) { $word.Options.UpdateLinksAtOpen = $oldUpdateLinks }
        $word.Quit(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word)
    }
}
