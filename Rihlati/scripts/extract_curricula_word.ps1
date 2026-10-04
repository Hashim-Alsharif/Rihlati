param([switch]$FirstOnly)
# Extract original Word text using physical page boundaries of its PDF export.
# Macro execution, link updates, file saves and recent-document entries disabled.
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$intake = Join-Path $project 'data/intake/curricula-2026-10'
$books = Get-Content -LiteralPath (Join-Path $intake 'manifest.json') -Raw -Encoding utf8 | ConvertFrom-Json
$word = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $oldLinks = $word.Options.UpdateLinksAtOpen
    $word.Options.UpdateLinksAtOpen = $false
    foreach ($book in $books) {
        if ([IO.Path]::GetExtension($book.original) -notin '.doc','.docx') { continue }
        $target = Join-Path $intake ($book.id+'.native-word.json')
        if (Test-Path -LiteralPath $target) {
            $cached = Get-Content -LiteralPath $target -Raw -Encoding utf8 | ConvertFrom-Json
            if ($cached.extraction_version -eq 2) { continue }
        }
        $source = Join-Path $project $book.original
        if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLower() -ne $book.original_sha256) { throw 'Original changed' }
        $doc = $null
        try {
            $doc = $word.Documents.Open($source,$false,$true,$false)
            $doc.Repaginate()
            $count = $doc.ComputeStatistics(2)
            if ($count -ne $book.page_count) { throw 'Physical page count differs from PDF export' }
            $notesByPage = @{}
            foreach ($note in $doc.Footnotes) {
                $notePage = [int]$note.Reference.Information(3)
                if (-not $notesByPage.ContainsKey($notePage)) { $notesByPage[$notePage] = @() }
                $notesByPage[$notePage] += ($note.Range.Text -replace '[\r\v\f]',"`n" -replace '[\x00-\x08\x0E-\x1F]',' ')
            }
            $pages = @()
            for ($number=1; $number -le $count; $number++) {
                $startRange = $doc.GoTo(1,1,$number)
                $pageStart = $startRange.Start
                [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($startRange)
                $pageEnd = $doc.Content.End
                if ($number -lt $count) {
                    $nextRange = $doc.GoTo(1,1,($number+1))
                    $pageEnd = $nextRange.Start
                    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($nextRange)
                }
                $range = $doc.Range($pageStart,$pageEnd)
                $pageText = $range.Text -replace '[\r\v\f]',"`n" -replace '[\x00-\x08\x0E-\x1F]',' '
                if ($notesByPage.ContainsKey($number)) { $pageText += "`n" + ($notesByPage[$number] -join "`n") }
                $pages += @{page=$number; text=$pageText; confidence=$null; method='word-native'; footnotes=@($notesByPage[$number]).Count}
                [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($range)
            }
            @{sha256=$book.sha256; original_sha256=$book.original_sha256; extraction_version=2; pages=$pages} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $target -Encoding utf8
            Write-Output "EXTRACTED $($book.id) pages=$count"
        } finally {
            if ($null -ne $doc) { $doc.Close(0); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($doc) }
        }
        if ($FirstOnly) { break }
    }
} finally {
    if ($null -ne $word) {
        if ($null -ne $oldLinks) { $word.Options.UpdateLinksAtOpen = $oldLinks }
        $word.Quit(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word)
    }
}
