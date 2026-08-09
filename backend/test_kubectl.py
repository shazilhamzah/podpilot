from kubernetes import client, config
try:
    config.load_kube_config()
    v1 = client.CoreV1Api()
    print("Deleting pod greedy-ml-job in default namespace...")
    v1.delete_namespaced_pod(name="greedy-ml-job", namespace="default")
    print("Pod deleted.")
except Exception as e:
    print(f"Error: {e}")
