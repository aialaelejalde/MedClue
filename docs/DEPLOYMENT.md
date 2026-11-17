# MedClue deployment

## Pre-built APK

The Android APK will be available in GitHub Releases. Users can download, install and test the personal medicine cabinet without setting up a backend. AI identification and CIMA verification will not be available in the public demo because they require an active backend with a paid OpenAI API.

## 1. Prerequisites

- Windows, PowerShell, Git and Python 3.12 with the `py` launcher.
- Flet CLI 1.0.5 and the [Android build tools](https://flet.dev/docs/publish/android/). Flet can install missing tools during the first build.
- Google Cloud CLI, a Google Cloud project with billing enabled, and an OpenAI API key with access to the selected model.

All commands use PowerShell. Start from the repository root unless stated otherwise.

## 2. Configuration

| Variable | Required or default | Where configured |
| --- | --- | --- |
| `OPENAI_API_KEY` | Required. | Secret Manager, linked to a Cloud Run environment variable. |
| `RETRY_TOKEN_SECRET` | Required; at least 32 characters after trimming spaces. | Secret Manager, linked to a Cloud Run environment variable. |
| `OPENAI_MODEL` | Optional; defaults to `gpt-6.1-terra`. Cannot be empty. | Cloud Run environment variable. |
| `MEDCLUE_BACKEND_URL` | Optional; uses `DEFAULT_BACKEND_URL` when unset. Requires HTTPS. | App runtime environment. |

Create the two backend secrets in Secret Manager. The Cloud Run service account must have access to their selected versions. Follow the [Cloud Run secrets guide](https://docs.cloud.google.com/run/docs/configuring/services/secrets); secret names, versions and IAM settings depend on your project.

For Android, check `DEFAULT_BACKEND_URL` in [app.py](../frontend/src/medclue_mobile/app.py) before building. Setting `MEDCLUE_BACKEND_URL` in Windows does not include it in the APK. Changing the APK's default URL requires a rebuild.

## 3. Backend deployment

### First deployment

Complete the API and permission setup in the [Cloud Run source deployment guide](https://docs.cloud.google.com/run/docs/deploying-source-code). Configure Secret Manager as described above.

From the repository root, replace the placeholders with your project values and existing secret names and versions:

```powershell
$projectId = "YOUR_PROJECT_ID"
$region = "YOUR_REGION"
$service = "YOUR_SERVICE_NAME"
$openaiSecret = "YOUR_OPENAI_SECRET_NAME:YOUR_VERSION"
$retrySecret = "YOUR_RETRY_SECRET_NAME:YOUR_VERSION"

gcloud auth login
Set-Location backend
gcloud run deploy $service --source . --project $projectId --region $region `
    --update-secrets "OPENAI_API_KEY=$openaiSecret,RETRY_TOKEN_SECRET=$retrySecret" `
    --allow-unauthenticated
```

The Android client does not send Google IAM credentials. Public access to this backend allows others to trigger paid OpenAI requests, with a risk of abuse and unexpected costs.

### Existing service

From the repository root, set the values for the existing service:

```powershell
$projectId = "YOUR_PROJECT_ID"
$region = "YOUR_REGION"
$service = "YOUR_SERVICE_NAME"

Set-Location backend
gcloud run deploy $service --source . --project $projectId --region $region
```

This keeps the existing runtime configuration. To change secret versions, include `--update-secrets` with the new references.

### Verification

From [backend/](../backend/), request the deployed API schema:

```powershell
$backendUrl = gcloud run services describe $service --project $projectId --region $region --format "value(status.url)"
Invoke-RestMethod -Uri "$backendUrl/openapi.json" | Select-Object openapi,info
```

Then identify a photo in the app to check the OpenAI and CIMA connections.

## 4. Android build and installation

### Initial environment setup

From the repository root, create the environment once and install Flet CLI. Reuse this environment for later builds.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install "flet-cli==1.0.5"
```

### Build the APK

From the repository root, enter [frontend/](../frontend/) and build:

```powershell
Set-Location frontend
$buildNumber = 1
..\.venv\Scripts\flet.exe build apk --build-number $buildNumber
```

For later builds, reuse the environment and increase the build number. The output is `frontend/build/apk/medclue.apk`. Copy it to the phone, open it and allow installation from that source if asked.

To keep saved medicines during an update:

- Install over the existing app, without uninstalling or clearing its data.
- Keep the same application ID and signing key, and use a higher build number.
- Keep the database location and existing data compatible with the new code.

No release keystore is configured in the repository. Flet uses the debug key unless signing is configured. Keep the original key; see [Flet Android signing](https://flet.dev/docs/publish/android/).

## 5. Updating MedClue

| Change | Required action |
| --- | --- |
| Backend code, dependencies or Dockerfile | Deploy a new Cloud Run revision. |
| Backend model, API key or signing secret | Update Cloud Run configuration or secret references. No new APK is needed. Changing the signing secret invalidates existing retry tokens. |
| Android code, assets or dependencies | Build and install a new APK with a higher build number. |
| Backend URL used by the APK | Change the app's default URL, then rebuild and install the APK. |
| API contract affecting the client | Deploy the backend and build a matching APK. Keep the API compatible with installed app versions during the update. |
