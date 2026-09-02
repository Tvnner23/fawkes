param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryPath,
    [string]$EntriesOutput
)

$ErrorActionPreference = "Stop"
$PolicyVersion = "phoenix-portable-snapshot-identity-v2"
$ExcludedNames = [System.Collections.Generic.HashSet[string]]::new(
    [string[]]@(".git", ".venv", "database", "node_modules", "__pycache__",
               ".pytest_cache", ".mypy_cache", ".ruff_cache", ".coverage", "htmlcov"),
    [System.StringComparer]::Ordinal)
$ExcludedRoots = [System.Collections.Generic.HashSet[string]]::new(
    [string[]]@(".agents", ".codex", "archive", "backups", "conversations", "database",
               "instances", "library", "logs", "memory", "node_modules"),
    [System.StringComparer]::Ordinal)
$SecretNames = [System.Collections.Generic.HashSet[string]]::new(
    [string[]]@(".env", ".env.local", ".env.production", "credentials.json", "secrets.json"),
    [System.StringComparer]::Ordinal)

function Write-U64BigEndian([System.IO.Stream]$Stream, [UInt64]$Value) {
    $bytes = [BitConverter]::GetBytes($Value)
    if ([BitConverter]::IsLittleEndian) { [Array]::Reverse($bytes) }
    $Stream.Write($bytes, 0, $bytes.Length)
}

$root = [IO.Path]::GetFullPath($RepositoryPath).TrimEnd([char]92, [char]47)
$entries = [System.Collections.Generic.Dictionary[string,object]]::new(
    [System.StringComparer]::Ordinal)
$casePaths = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase)

foreach ($file in Get-ChildItem -LiteralPath $root -Force -Recurse -File) {
    if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
    $relative = $file.FullName.Substring($root.Length).TrimStart([char]92, [char]47)
    $portable = $relative.Replace("\", "/").Normalize([Text.NormalizationForm]::FormC)
    $parts = $portable.Split('/')
    if ($ExcludedRoots.Contains($parts[0])) { continue }
    $excluded = $false
    foreach ($part in $parts) {
        if ($ExcludedNames.Contains($part)) { $excluded = $true; break }
    }
    if ($excluded -or $SecretNames.Contains($parts[-1]) -or
        $portable.EndsWith(".pyc", [StringComparison]::Ordinal) -or
        $portable.EndsWith(".pyo", [StringComparison]::Ordinal) -or
        $portable.EndsWith(":Zone.Identifier", [StringComparison]::Ordinal) -or
        $portable.EndsWith(([string][char]0xF03A + "Zone.Identifier"),
                           [StringComparison]::Ordinal)) { continue }
    if (-not $casePaths.Add($portable) -or $entries.ContainsKey($portable)) {
        throw "snapshot contains a portable path identity collision: $portable"
    }
    $bytes = [IO.File]::ReadAllBytes($file.FullName)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $contentHash = $sha.ComputeHash($bytes) } finally { $sha.Dispose() }
    $entries.Add($portable, [pscustomobject]@{
        Path = $portable
        Hash = $contentHash
        Length = [UInt64]$bytes.LongLength
    })
}

$paths = [string[]]$entries.Keys
[Array]::Sort($paths, [StringComparer]::Ordinal)
if ($EntriesOutput) {
    $diagnosticEntries = foreach ($path in $paths) {
        $entry = $entries[$path]
        [ordered]@{
            path = $entry.Path
            sha256 = (-join ($entry.Hash | ForEach-Object { $_.ToString("x2") }))
            byte_length = $entry.Length
        }
    }
    [IO.File]::WriteAllText($EntriesOutput,
        ($diagnosticEntries | ConvertTo-Json -Compress),
        [Text.UTF8Encoding]::new($false))
}
$stream = [IO.MemoryStream]::new()
try {
    $prefix = [Text.Encoding]::UTF8.GetBytes($PolicyVersion + "`n")
    $stream.Write($prefix, 0, $prefix.Length)
    [UInt64]$totalBytes = 0
    foreach ($path in $paths) {
        $entry = $entries[$path]
        $pathBytes = [Text.Encoding]::UTF8.GetBytes($entry.Path)
        Write-U64BigEndian $stream ([UInt64]$pathBytes.Length)
        $stream.Write($pathBytes, 0, $pathBytes.Length)
        $stream.Write($entry.Hash, 0, $entry.Hash.Length)
        Write-U64BigEndian $stream $entry.Length
        $totalBytes += $entry.Length
    }
    $identitySha = [Security.Cryptography.SHA256]::Create()
    try { $identityHash = $identitySha.ComputeHash($stream.ToArray()) }
    finally { $identitySha.Dispose() }
    $identityStreamLength = $stream.Length
} finally {
    $stream.Dispose()
}

$hex = -join ($identityHash | ForEach-Object { $_.ToString("x2") })
[ordered]@{
    policy_version = $PolicyVersion
    candidate_snapshot_id = "candidate-snapshot-$hex"
    file_count = $paths.Length
    total_byte_length = $totalBytes
    identity_stream_byte_length = $identityStreamLength
    repository_path = $root
} | ConvertTo-Json -Compress
