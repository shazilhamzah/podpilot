#!/bin/bash

NAMESPACE=""
NAMESPACE_FLAG=""

# Check if a namespace argument is provided (e.g., -n podpilot-demo)
if [ "$1" == "-n" ] && [ -n "$2" ]; then
    NAMESPACE="$2"
    NAMESPACE_FLAG="-n $2"
fi

# Get all pod names in the target namespace, filter for nginx[0-9]+, extract the numbers, and find the maximum
CURRENT_MAX=$(kubectl get pods $NAMESPACE_FLAG -o jsonpath='{.items[*].metadata.name}' 2>/dev/null | tr ' ' '\n' | grep -E '^nginx[0-9]+$' | sed 's/nginx//' | sort -n | tail -n 1)

if [ -z "$CURRENT_MAX" ]; then
    NEXT_NUM=1
else
    NEXT_NUM=$((CURRENT_MAX + 1))
fi

echo "🚀 Creating pod nginx$NEXT_NUM..."
kubectl run "nginx$NEXT_NUM" --image=nginx $NAMESPACE_FLAG
