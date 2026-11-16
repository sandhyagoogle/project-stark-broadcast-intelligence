# CourtVision AI: GCP Access Guide

CourtVision AI is deployed on **Google Cloud Run** in **project-stark-510823** (**us-west1**) behind an application-level **Access Password** stored in Google Cloud Secret Manager (**COURTVISION_ACCESS_PASSWORD**). Opening the Cloud Run URL in any browser presents the **CourtVision** sign-in screen, and all backend API endpoints return **401 Unauthorized** until unlocked.

* **GCP Project:** **project-stark-510823**
* **Region:** **us-west1**
* **Cloud Run Service:** **courtvision-broadcast-ai**
* **Service URL:** https://courtvision-broadcast-ai-698664266069.us-west1.run.app
* **GitHub Repo:** https://github.com/sandhyagoogle/project-stark-broadcast-intelligence

## 1. Grant Access (Admin Once per User)

The project admin grants each teammate **roles/run.invoker** (to call the app) and **roles/run.viewer** (required for **gcloud run services proxy** to resolve the service URL):

```bash
gcloud run services add-iam-policy-binding courtvision-broadcast-ai \
  --project=project-stark-510823 \
  --region=us-west1 \
  --member="user:TEAMMATE_EMAIL" \
  --role="roles/run.invoker"

gcloud run services add-iam-policy-binding courtvision-broadcast-ai \
  --project=project-stark-510823 \
  --region=us-west1 \
  --member="user:TEAMMATE_EMAIL" \
  --role="roles/run.viewer"
```

## 2. Sign In with gcloud

Install the **Google Cloud CLI (gcloud)** if it is not already installed, then authenticate using the Google account granted access in Step 1:

```bash
gcloud auth login
```

## 3. Launch the App

Start the authenticated local proxy in your terminal:

```bash
gcloud run services proxy courtvision-broadcast-ai \
  --region=us-west1 \
  --project=project-stark-510823
```

Open **http://127.0.0.1:8080** in your browser. Keep the terminal running while using the app, and press **Ctrl+C** when finished.

If port **8080** is already in use, specify another port and open **http://127.0.0.1:8081** instead:

```bash
gcloud run services proxy courtvision-broadcast-ai \
  --region=us-west1 \
  --project=project-stark-510823 \
  --port=8081
```

## 4. Call the API Directly

To query backend endpoints from the terminal, pass an identity token in the **Authorization** header:

```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  https://courtvision-broadcast-ai-698664266069.us-west1.run.app/api/videos
```

## 5. Troubleshooting

* **403 Forbidden or Permission Denied:** Run **gcloud auth list** to confirm the active account matches the email granted access in Step 1, or refresh credentials with **gcloud auth login**.
* **Port Already in Use:** Pass **--port=8081** (or any free local port) to **gcloud run services proxy**.
* **Rotate Gemini API Key (Admin):** Update the **GEMINI_API_KEY** secret in Secret Manager:

```bash
printf '%s' "YOUR_GEMINI_API_KEY" | gcloud secrets versions add GEMINI_API_KEY \
  --project=project-stark-510823 \
  --data-file=-
```

* **Rotate App Access Password (Admin):** Update the **COURTVISION_ACCESS_PASSWORD** secret in Secret Manager:

```bash
printf '%s' "YOUR_NEW_PASSWORD" | gcloud secrets versions add COURTVISION_ACCESS_PASSWORD \
  --project=project-stark-510823 \
  --data-file=-
```
