#!/bin/bash

# Define the namespace to snapshot (defaults to validation-env)
NAMESPACE=${1:-validation-env}
OUTPUT_FILE="cluster_snapshot.json"

echo "🔍 Gathering comprehensive K8s snapshot for namespace: $NAMESPACE"

# Comma-separated list of all critical resources the chatbot needs to see
RESOURCES="deployments,statefulsets,daemonsets,jobs,cronjobs,pods,services,ingress,networkpolicies,configmaps,secrets,persistentvolumeclaims,hpa"

# 1. Fetch all resources in JSON format
# 2. Use jq to remove 'managedFields' and 'last-applied-configuration' 
#    to save massive amounts of tokens for the chatbot context window.
if kubectl get $RESOURCES -n $NAMESPACE -o json 2>/dev/null | jq 'del(.items[].metadata.managedFields, .items[].metadata.annotations."kubectl.kubernetes.io/last-applied-configuration")' > $OUTPUT_FILE; then
    echo "✅ Success! Snapshot saved to: $OUTPUT_FILE"
    echo ""
    echo "🤖 Next Steps:"
    echo "Upload or paste the contents of '$OUTPUT_FILE' to your chatbot."
    echo "Because this snapshot includes the full .spec for every resource, the bot will now correctly answer questions about:"
    echo "  - Resource Limits & OOM Issues"
    echo "  - Probes & Healthchecks"
    echo "  - Graceful Shutdowns (preStop hooks)"
    echo "  - Horizontal Pod Autoscaling (HPA)"
    echo "  - Routing (Ingress)"
else
    echo "❌ Error: Failed to generate snapshot. Ensure you are connected to a Kubernetes cluster and have 'jq' installed."
fi
