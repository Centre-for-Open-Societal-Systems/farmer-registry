# Disposable local-only check. No kubeconfig, published database, or host port.
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$taskName = 'farmer-location-qa-' + [guid]::NewGuid().ToString('N').Substring(0, 10)
$containerCreated = $false
$networkCreated = $false
try {
    docker network create --internal $taskName | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not create disposable network' }
    $networkCreated = $true
    docker run -d --name $taskName --network $taskName --network-alias farmer-qa-db -e POSTGRES_PASSWORD=fixture postgres:16-alpine | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not create disposable PostgreSQL' }
    $containerCreated = $true
    $ready = $false
    for ($attempt = 0; $attempt -lt 50; $attempt++) {
        docker exec $taskName pg_isready -U postgres *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Milliseconds 200
    }
    if (-not $ready) { throw 'Disposable PostgreSQL did not become ready' }
    docker run --rm --network $taskName -v "${repoRoot}:/repo:ro" -e PYTHONPATH=/repo/farmer-extension/src --entrypoint python openg2p/openg2p-registry-staff-api:1.2.2-rc.544 /repo/tests/integration/check_location_livestock.py
    if ($LASTEXITCODE -ne 0) { throw 'Location/livestock integration failed' }
} finally {
    if ($containerCreated) { docker rm -f $taskName | Out-Null }
    if ($networkCreated) { docker network rm $taskName | Out-Null }
}
