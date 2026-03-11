param(
    [string]$AppId = "",

    [string]$BotDomain = "",

    [ValidateSet("quickstart", "standard", "import-test")]
    [string]$TemplateName = "import-test",

    [string]$AppName = "",
    [string]$PackageId = "",
    [string]$Version = "",
    [string]$DeveloperName = "",
    [string]$DeveloperWebsiteUrl = "",
    [string]$PrivacyUrl = "",
    [string]$TermsUrl = "",
    [string]$ShortDescription = "",
    [string]$FullDescription = "",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

function Get-NormalizedHttpsUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    if ($Value -match "^https://") {
        return $Value.TrimEnd('/')
    }

    if ($Value -match "^http://") {
        throw "Only https URLs are supported: $Value"
    }

    return "https://$($Value.Trim('/'))"
}

function Load-EnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $values = @{}

    if (-not (Test-Path -LiteralPath $Path)) {
        return $values
    }

    foreach ($rawLine in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            continue
        }

        $key, $value = $line.Split("=", 2)
        $values[$key.Trim()] = $value.Trim()
    }

    return $values
}

function Select-NonEmptyValue {
    param(
        [AllowNull()]
        [object[]]$Values = @()
    )

    foreach ($value in $Values) {
        $text = [string]$value
        if (-not [string]::IsNullOrWhiteSpace($text)) {
            return $text
        }
    }

    return ""
}

function New-PlaceholderIcon {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [int]$Size,

        [Parameter(Mandatory = $true)]
        [string]$Mode,

        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    Add-Type -AssemblyName System.Drawing

    $bitmap = New-Object System.Drawing.Bitmap($Size, $Size)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

    if ($Mode -eq "outline") {
        $graphics.Clear([System.Drawing.Color]::Transparent)
        $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::Black, [Math]::Max(2, [int]($Size / 12)))
        $padding = [Math]::Max(3, [int]($Size / 8))
        $graphics.DrawRectangle($pen, $padding, $padding, $Size - (2 * $padding) - 1, $Size - (2 * $padding) - 1)
        $pen.Dispose()
    }
    else {
        $background = [System.Drawing.ColorTranslator]::FromHtml("#2563EB")
        $foreground = [System.Drawing.Color]::White
        $graphics.Clear($background)

        $fontSize = [Math]::Max(16, [int]($Size / 2.8))
        $font = New-Object System.Drawing.Font("Segoe UI", $fontSize, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
        $brush = New-Object System.Drawing.SolidBrush($foreground)
        $stringFormat = New-Object System.Drawing.StringFormat
        $stringFormat.Alignment = [System.Drawing.StringAlignment]::Center
        $stringFormat.LineAlignment = [System.Drawing.StringAlignment]::Center
        $graphics.DrawString($Label, $font, $brush, (New-Object System.Drawing.RectangleF(0, 0, $Size, $Size)), $stringFormat)
        $stringFormat.Dispose()
        $brush.Dispose()
        $font.Dispose()
    }

    $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose()
    $bitmap.Dispose()
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$envValues = Load-EnvFile -Path (Join-Path $repoRoot ".env")

$templatePath = switch ($TemplateName) {
    "quickstart" { Join-Path $scriptRoot "manifest.quickstart.template.json" }
    "import-test" { Join-Path $scriptRoot "manifest.import-test.template.json" }
    default { Join-Path $scriptRoot "manifest.template.json" }
}

if (-not (Test-Path -LiteralPath $templatePath)) {
    throw "manifest template not found: $templatePath"
}

$AppId = Select-NonEmptyValue @(
    $AppId,
    $envValues["TEST_MSTEAMS_APP_ID"]
)

$BotDomain = Select-NonEmptyValue @(
    $BotDomain,
    $envValues["TEST_MSTEAMS_BOT_DOMAIN"],
    $envValues["TEST_OPENCLAW_PUBLIC_URL"]
)

if ([string]::IsNullOrWhiteSpace($AppId)) {
    throw "AppId is required. Pass -AppId or set TEST_MSTEAMS_APP_ID in .env."
}

if ([string]::IsNullOrWhiteSpace($BotDomain)) {
    throw "BotDomain is required. Pass -BotDomain or set TEST_MSTEAMS_BOT_DOMAIN or TEST_OPENCLAW_PUBLIC_URL in .env."
}

$baseUrl = Get-NormalizedHttpsUrl -Value $BotDomain
$domain = ([Uri]$baseUrl).Host

$AppName = Select-NonEmptyValue @(
    $AppName,
    $envValues["TEST_MSTEAMS_APP_NAME"],
    "OpenClaw"
)

$Version = Select-NonEmptyValue @(
    $Version,
    $envValues["TEST_MSTEAMS_PACKAGE_VERSION"],
    "1.0.0"
)

$DeveloperName = Select-NonEmptyValue @(
    $DeveloperName,
    $envValues["TEST_MSTEAMS_DEVELOPER_NAME"],
    "OpenClaw Azure Deploy"
)

$ShortDescription = Select-NonEmptyValue @(
    $ShortDescription,
    "OpenClaw in Teams"
)

$FullDescription = Select-NonEmptyValue @(
    $FullDescription,
    "OpenClaw assistant for Microsoft Teams"
)

if ([string]::IsNullOrWhiteSpace($PackageId)) {
    $PackageId = Select-NonEmptyValue @(
        $envValues["TEST_MSTEAMS_PACKAGE_ID"],
        ([guid]::NewGuid()).Guid
    )
}

if ([string]::IsNullOrWhiteSpace($DeveloperWebsiteUrl)) {
    $DeveloperWebsiteUrl = Select-NonEmptyValue @(
        $envValues["TEST_MSTEAMS_DEVELOPER_WEBSITE_URL"],
        $baseUrl
    )
}

if ([string]::IsNullOrWhiteSpace($PrivacyUrl)) {
    $PrivacyUrl = Select-NonEmptyValue @(
        $envValues["TEST_MSTEAMS_PRIVACY_URL"],
        "$baseUrl/privacy"
    )
}

if ([string]::IsNullOrWhiteSpace($TermsUrl)) {
    $TermsUrl = Select-NonEmptyValue @(
        $envValues["TEST_MSTEAMS_TERMS_URL"],
        "$baseUrl/terms"
    )
}

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $scriptRoot "dist"
}

$safeAppName = ($AppName -replace '[^A-Za-z0-9._-]+', '-')
$workDir = Join-Path $OutputDir $safeAppName
$manifestPath = Join-Path $workDir "manifest.json"
$outlinePath = Join-Path $workDir "outline.png"
$colorPath = Join-Path $workDir "color.png"
$zipPath = Join-Path $OutputDir "$safeAppName.zip"

New-Item -ItemType Directory -Force -Path $workDir | Out-Null
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$manifestTemplate = Get-Content -LiteralPath $templatePath -Raw -Encoding UTF8
$replacements = @{
    "__APP_VERSION__" = $Version
    "__PACKAGE_ID__" = $PackageId
    "__APP_NAME__" = $AppName
    "__DEVELOPER_NAME__" = $DeveloperName
    "__DEVELOPER_WEBSITE_URL__" = $DeveloperWebsiteUrl
    "__PRIVACY_URL__" = $PrivacyUrl
    "__TERMS_URL__" = $TermsUrl
    "__SHORT_DESCRIPTION__" = $ShortDescription
    "__FULL_DESCRIPTION__" = $FullDescription
    "__APP_ID__" = $AppId
    "__BOT_DOMAIN__" = $domain
}

$manifest = $manifestTemplate
foreach ($entry in $replacements.GetEnumerator()) {
    $manifest = $manifest.Replace($entry.Key, $entry.Value)
}

Set-Content -LiteralPath $manifestPath -Value $manifest -Encoding UTF8

$labelSource = ($AppName -replace '[^A-Za-z0-9]', '').ToUpper()
if ([string]::IsNullOrWhiteSpace($labelSource)) {
    $labelSource = "OC"
}
$label = ($labelSource + "OC").Substring(0, [Math]::Min(2, ($labelSource + "OC").Length))

New-PlaceholderIcon -Path $outlinePath -Size 32 -Mode "outline" -Label $label
New-PlaceholderIcon -Path $colorPath -Size 192 -Mode "color" -Label $label

if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

Compress-Archive -Path $manifestPath, $outlinePath, $colorPath -DestinationPath $zipPath

Write-Host "Created Teams app package: $zipPath"
Write-Host "App ID: $AppId"
Write-Host "Package ID: $PackageId"
Write-Host "Bot domain: $domain"
Write-Host "Template: $TemplateName"