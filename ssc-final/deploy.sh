#!/bin/bash
# ── SSC Exam Scheduler — Google Cloud Run Deployment (ADK + Gemini) ────────────
set -e

PROJECT_ID="your-gcp-project-id"        # ← edit
REGION="asia-south1"                     # Mumbai
SERVICE_NAME="ssc-exam-scheduler"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"
GOOGLE_API_KEY="your-google-api-key"    # ← from aistudio.google.com

echo "🚀 Deploying SSC Exam Scheduler (Google ADK) to Cloud Run..."

gcloud config set project $PROJECT_ID

echo "📌 Enabling APIs..."
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  containerregistry.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com

echo "📌 Storing API key in Secret Manager..."
echo -n "$GOOGLE_API_KEY" | gcloud secrets create google-api-key \
  --data-file=- 2>/dev/null || \
  echo -n "$GOOGLE_API_KEY" | gcloud secrets versions add google-api-key --data-file=-

PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding google-api-key \
  --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

echo "📌 Building Docker image..."
gcloud builds submit --tag $IMAGE_NAME .

echo "📌 Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --port 8080 \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 5 \
  --set-secrets="GOOGLE_API_KEY=google-api-key:latest" \
  --set-env-vars="DB_PATH=/tmp/ssc_scheduler.db,GEMINI_MODEL=gemini-2.0-flash"

SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
  --platform managed --region $REGION --format 'value(status.url)')

echo ""
echo "✅ Done!  🌐 $SERVICE_URL"
echo "   Docs   → $SERVICE_URL/docs"
echo "   Health → $SERVICE_URL/health"
