param(
  [string]$Base = "main",
  [string]$Title = "",
  [string]$Body = ""
)

$ErrorActionPreference = "Stop"

Write-Host "== Git status =="
git status --short

$currentBranch = git branch --show-current
if (-not $currentBranch) { throw "е удалось определить текущую ветку." }
if ($currentBranch -eq $Base) { throw "Ты на '$Base'. ереключись на рабочую ветку (например, work)." }

# роверка: есть ли изменения для коммита
$hasChanges = (git status --porcelain)
if ($hasChanges) {
  Write-Host "== Commit changes =="
  git add .
  if (-not $Title) { $Title = "Update: $currentBranch changes" }
  git commit -m $Title
} else {
  Write-Host "зменений для коммита нет."
}

Write-Host "== Push branch =="
git push -u origin $currentBranch

# роверка наличия gh
$ghExists = Get-Command gh -ErrorAction SilentlyContinue
if (-not $ghExists) {
  Write-Host "GitHub CLI (gh) не найден. Push сделан, PR создай вручную:"
  Write-Host "https://github.com/MaximusB93/directpilot-ai/pull/new/$currentBranch"
  exit 0
}

# сли заголовок пустой — дефолт
if (-not $Title) { $Title = "Update $currentBranch" }
if (-not $Body) { $Body = "Automated publish from local PowerShell script." }

# опробуем создать PR (если уже есть — gh вернёт ошибку, просто покажем ссылку)
Write-Host "== Create PR =="
try {
  gh pr create --base $Base --head $currentBranch --title $Title --body $Body
} catch {
  Write-Host "е удалось создать PR автоматически (возможно, PR уже существует)."
  Write-Host "ткрой вручную:"
  Write-Host "https://github.com/MaximusB93/directpilot-ai/pull/new/$currentBranch"
}
