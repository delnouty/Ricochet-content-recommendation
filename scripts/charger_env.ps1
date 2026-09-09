# Charge `.env` dans la session PowerShell courante.
#
# À sourcer, pas à exécuter — sinon les variables mourraient avec le processus
# enfant :
#
#     . ./scripts/charger_env.ps1
#
# Pourquoi un script plutôt que `python-dotenv` : les variables sont utilisées
# aussi par `az`, `gh`, `curl` et `terraform`, pas seulement par Python. Et
# surtout, ajouter une dépendance chargée par le code applicatif entamerait la
# propriété que ce projet revendique — **à l'inférence, numpy seul**. Le
# chargement appartient donc à l'environnement, pas au programme.
#
# Les valeurs ne sont jamais affichées : seuls les noms des variables chargées.

param(
    [string]$Fichier = ".env"
)

if (-not (Test-Path $Fichier)) {
    Write-Host "$Fichier absent. Créez-le à partir du gabarit :" -ForegroundColor Yellow
    Write-Host "    Copy-Item .env.example .env"
    return
}

$charges = @()
$ignores = @()

foreach ($ligne in Get-Content $Fichier) {
    $t = $ligne.Trim()
    if ($t -eq "" -or $t.StartsWith("#")) { continue }

    $separateur = $t.IndexOf("=")
    if ($separateur -lt 1) { continue }

    $nom = $t.Substring(0, $separateur).Trim()
    $valeur = $t.Substring($separateur + 1).Trim()

    # Une valeur vide veut dire « laisser le défaut du programme », et un
    # gabarit non rempli ne doit surtout pas être chargé : `<votre-cle>` comme
    # clé de fonction produirait un 401 déroutant plutôt qu'une erreur claire.
    if ($valeur -eq "" -or $valeur -match '^<.*>$') {
        $ignores += $nom
        continue
    }

    Set-Item -Path "Env:$nom" -Value $valeur
    $charges += $nom
}

if ($charges.Count -gt 0) {
    Write-Host "chargées : $($charges -join ', ')" -ForegroundColor Green
}
if ($ignores.Count -gt 0) {
    Write-Host "ignorées (vides ou gabarits non remplis) : $($ignores -join ', ')" -ForegroundColor DarkGray
}
