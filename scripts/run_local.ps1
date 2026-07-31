<#
.SYNOPSIS
    Lance la pile Ricochet en local : serveur de recommandation + application Streamlit.

.DESCRIPTION
    Équivalent local de la solution Azure, sans les Azure Functions Core Tools :
      1. démarre scripts/serve_local.py (même contrat que /api/recommend) ;
      2. attend qu'il réponde ;
      3. lance app/streamlit_app.py pointé dessus via FUNCTION_URL.

    Le serveur est arrêté automatiquement à la fermeture de Streamlit (Ctrl+C).

.EXAMPLE
    .\scripts\run_local.ps1
    .\scripts\run_local.ps1 -Port 8000
#>
[CmdletBinding()]
param(
    [int]$Port = 7071,
    [string]$ModelsDir = "models"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Interpréteur : environnement virtuel du dépôt si présent, sinon python du PATH.
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

if (-not (Test-Path (Join-Path $ModelsDir "articles_embeddings_pca.npy"))) {
    Write-Error "Artefacts absents de '$ModelsDir'. Lancez d'abord : $py -m src.prepare_model --data-dir data/raw --out-dir $ModelsDir"
}

Write-Host "==> Démarrage du serveur de recommandation (port $Port)…" -ForegroundColor Cyan
$server = Start-Process -FilePath $py `
    -ArgumentList "scripts/serve_local.py", "--port", $Port, "--models-dir", $ModelsDir `
    -WorkingDirectory $root -PassThru

try {
    # Attente de disponibilité : le chargement des artefacts prend quelques secondes.
    $url = "http://127.0.0.1:$Port/api/recommend"
    $ready = $false
    foreach ($attempt in 1..40) {
        if ($server.HasExited) {
            Write-Error "Le serveur s'est arrêté (code $($server.ExitCode)). Relancez-le seul pour voir l'erreur : $py scripts/serve_local.py"
        }
        try {
            Invoke-RestMethod -Uri "http://127.0.0.1:$Port/" -TimeoutSec 2 | Out-Null
            $ready = $true
            break
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $ready) { Write-Error "Le serveur n'a pas répondu sur le port $Port." }

    Write-Host "==> Serveur prêt sur $url" -ForegroundColor Green
    Write-Host "==> Lancement de l'application Streamlit…" -ForegroundColor Cyan
    $env:FUNCTION_URL = $url
    & $py -m streamlit run app/streamlit_app.py
}
finally {
    if ($server -and -not $server.HasExited) {
        Write-Host "==> Arrêt du serveur de recommandation." -ForegroundColor Cyan
        Stop-Process -Id $server.Id -Force
    }
}
