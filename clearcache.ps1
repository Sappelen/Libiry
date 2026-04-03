# Libiry Cache Cleaner - PowerShell (Windows/Linux/macOS)
# Verwijdert de Libiry cache folder (~/.libiry/cache)

$CacheDir = Join-Path $HOME ".libiry" "cache"

if (Test-Path $CacheDir) {
    Write-Host "Clearing Libiry cache: $CacheDir"
    Remove-Item -Recurse -Force $CacheDir
    Write-Host "Cache cleared."
} else {
    Write-Host "No cache found at $CacheDir"
}
