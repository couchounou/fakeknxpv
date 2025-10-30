param(
    [string]$NewVersion = "1.0.0"
)

# Chemins des fichiers
$versionFile = "VERSION"
$pyprojectFile = "pyproject.toml"
$setupFile = "setup.py"

# 1. Met à jour le fichier VERSION
Set-Content -Path $versionFile -Value $NewVersion

# 2. Met à jour la version dans pyproject.toml
(Get-Content $pyprojectFile) -replace 'version\s*=\s*["''][^"'']+["'']', "version = `"$NewVersion`"" | Set-Content $pyprojectFile

# 3. Met à jour la version dans setup.py
(Get-Content $setupFile) -replace 'version\s*=\s*["''][^"'']+["'']', "version='$NewVersion'" | Set-Content $setupFile

# 4. Lance le build
python -m build --wheel