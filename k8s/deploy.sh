#!/bin/bash

set -e

echo "🚀 Applying Kubernetes manifest..."
kubectl apply -f k8s/podpilot.yaml

echo "🔄 Restarting deployment to ensure latest image is pulled..."
kubectl rollout restart deployment podpilot -n podpilot

echo "⏳ Waiting for the deployment to roll out..."
kubectl rollout status deployment/podpilot -n podpilot

echo "================================================================"
echo "✅ PodPilot is deployed!"
echo ""
echo "Starting port-forwarding so you can access it from your Windows browser."
echo "👉 Go to: http://localhost:8000"
echo "================================================================"

echo "📋 Streaming logs in the background... (Port forward running in foreground, Ctrl+C to stop)"
# Tail logs in the background so we can see them
kubectl logs -f deployment/podpilot -n podpilot --all-containers=true &

# Start port forwarding in the foreground to keep the script alive
kubectl port-forward svc/podpilot 8000:80 -n podpilot --address 0.0.0.0
