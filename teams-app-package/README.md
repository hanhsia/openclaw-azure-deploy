# Teams App Package Template

This folder contains a local Teams app package template for the Azure deployment in this repository.

## Files

- `manifest.template.json`: tokenized Teams manifest template.
- `manifest.quickstart.template.json`: ready-to-use template with most metadata fixed.
- `manifest.import-test.template.json`: import-friendly personal-scope test template for sideloading.
- `build-app-package.ps1`: generates `manifest.json`, placeholder icons, and a zip package.

## Quick Start

Run this from PowerShell on Windows:

```powershell
./teams-app-package/build-app-package.ps1 \
  -AppId "<Azure Bot App ID>" \
  -BotDomain "<your-domain-or-fqdn>"
```

By default the script uses the `import-test` template, which is the safest option for Teams sideload import testing.

The `import-test` template intentionally:

- keeps only `personal` scope
- removes team and group chat scopes
- removes resource-specific permissions that often trigger admin approval flows

That makes it a better fit for `Upload a custom app` testing in Teams.

If your tenant still blocks custom app upload, you will still need tenant policy changes or admin approval.

To use the fully customizable template instead:

```powershell
./teams-app-package/build-app-package.ps1 \
  -TemplateName standard \
  -AppId "<Azure Bot App ID>" \
  -BotDomain "<your-domain-or-fqdn>" \
  -DeveloperName "Your Org"
```

To generate the broader quickstart package that includes team and group chat scopes:

```powershell
./teams-app-package/build-app-package.ps1 \
  -TemplateName quickstart \
  -AppId "<Azure Bot App ID>" \
  -BotDomain "<your-domain-or-fqdn>"
```

If the repository root contains `.env`, the script can also read these defaults automatically:

- `TEST_MSTEAMS_APP_ID`
- `TEST_MSTEAMS_BOT_DOMAIN` or `TEST_OPENCLAW_PUBLIC_URL`
- `TEST_MSTEAMS_PACKAGE_ID`
- `TEST_MSTEAMS_PACKAGE_VERSION`
- `TEST_MSTEAMS_APP_NAME`
- `TEST_MSTEAMS_DEVELOPER_NAME`
- `TEST_MSTEAMS_DEVELOPER_WEBSITE_URL`
- `TEST_MSTEAMS_PRIVACY_URL`
- `TEST_MSTEAMS_TERMS_URL`

That means the shortest command can be:

```powershell
./teams-app-package/build-app-package.ps1
```

as long as `.env` already has the required Teams values.

Required value resolution is strict:

- `AppId` comes from `-AppId` first, then `TEST_MSTEAMS_APP_ID` in `.env`
- `BotDomain` comes from `-BotDomain` first, then `TEST_MSTEAMS_BOT_DOMAIN`, then `TEST_OPENCLAW_PUBLIC_URL`
- If either required value is still missing, the script exits with a clear error instead of continuing with blanks

Examples for `-BotDomain`:

- `openclawtestvm.eastasia.cloudapp.azure.com`
- `https://openclaw.example.com`

The script writes these outputs under `teams-app-package/dist/`:

- `manifest.json`
- `outline.png`
- `color.png`
- `<app-name>.zip`

## Notes

- The generated zip is intended for Teams upload or import into Developer Portal.
- `bots[].botId` and `webApplicationInfo.id` are both set to the Azure Bot App ID.
- `manifest.id` is the Teams app package ID. If you omit `-PackageId`, the script creates one automatically.
- The generated icons are placeholders. Replace them later if you need final branding.
- For repository-level test configuration, see `.env.example` in the repo root.