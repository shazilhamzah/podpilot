"""
PodPilot Phase 1: Cluster State Snapshot Tool.

This module provides functionality to capture real-time state and metrics
from a running Kubernetes cluster. It connects via the Python Kubernetes client
and aggregates pod, node, deployment, service, and PVC information along with
actual resource consumption retrieved from the metrics-server.
"""
import os
import datetime
from kubernetes import client, config

def parse_cpu(cpu_str):
    """
    Parses a Kubernetes CPU resource string and returns the value in float cores.
    
    Args:
        cpu_str (str|int|float): The CPU string from the Kubernetes API (e.g., "125m", "1", "1000000n").
        
    Returns:
        float: The CPU value in raw cores (e.g., 0.125 for "125m").
    """
    if not cpu_str:
        return 0.0
    if isinstance(cpu_str, (int, float)):
        return float(cpu_str)
    
    cpu_str = str(cpu_str)
    if cpu_str.endswith("m"):
        return float(cpu_str[:-1]) / 1000.0
    elif cpu_str.endswith("u"):
        return float(cpu_str[:-1]) / 1000000.0
    elif cpu_str.endswith("n"):
        return float(cpu_str[:-1]) / 1000000000.0
    else:
        try:
            return float(cpu_str)
        except ValueError:
            return 0.0

def parse_memory(mem_str):
    """
    Parses a Kubernetes Memory resource string and returns the value in float Gigabytes (GB).
    
    Args:
        mem_str (str|int|float): The memory string from the Kubernetes API (e.g., "256Mi", "1Gi", "1024").
        
    Returns:
        float: The memory value converted to Gigabytes. (1 Gi = 1 GB, 1 Mi = 1/1024 GB).
    """
    if not mem_str:
        return 0.0
    if isinstance(mem_str, (int, float)):
        return float(mem_str) / (1024**3)
        
    mem_str = str(mem_str)
    try:
        if mem_str.endswith("Ki"):
            return float(mem_str[:-2]) / (1024 ** 2)
        elif mem_str.endswith("Mi"):
            return float(mem_str[:-2]) / 1024.0
        elif mem_str.endswith("Gi"):
            return float(mem_str[:-2])
        elif mem_str.endswith("Ti"):
            return float(mem_str[:-2]) * 1024.0
        elif mem_str.endswith("Pi"):
            return float(mem_str[:-2]) * (1024 ** 2)
        elif mem_str.endswith("Ei"):
            return float(mem_str[:-2]) * (1024 ** 3)
        elif mem_str.endswith("K"):
            return float(mem_str[:-1]) * 1000 / (1024 ** 3)
        elif mem_str.endswith("M"):
            return float(mem_str[:-1]) * (1000 ** 2) / (1024 ** 3)
        elif mem_str.endswith("G"):
            return float(mem_str[:-1]) * (1000 ** 3) / (1024 ** 3)
        elif mem_str.endswith("T"):
            return float(mem_str[:-1]) * (1000 ** 4) / (1024 ** 3)
        else:
            return float(mem_str) / (1024 ** 3) # Assume bytes
    except ValueError:
        return 0.0

def snapshot():
    """
    Connects to the active Kubernetes cluster and compiles a comprehensive dictionary
    snapshot of the current resources and their actual real-time usages.
    
    The function hits both the Core APIs (for static configurations, limits, requests)
    and the CustomMetrics API (for live CPU and RAM consumption). It defaults missing
    metrics gracefully.
    
    Returns:
        dict: A structured JSON-serializable dictionary containing the cluster's state
              (nodes, pods, deployments, services, pvcs) and actual metrics.
    """
    try:
        config.load_kube_config()
    except Exception as e:
        print(f"Error loading kube config: {e}")
        return {}

    core_v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    custom_api = client.CustomObjectsApi()

    captured_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    cluster_name = "minikube"

    try:
        contexts, active_context = config.list_kube_config_contexts()
        if active_context and 'cluster' in active_context.get('context', {}):
            cluster_name = active_context['context']['cluster']
    except Exception:
        pass

    nodes_data = []
    pods_data = []
    deployments_data = []
    services_data = []
    pvcs_data = []

    node_metrics_dict = {}
    pod_metrics_dict = {}

    try:
        nodes_metrics = custom_api.list_cluster_custom_object('metrics.k8s.io', 'v1beta1', 'nodes')
        if nodes_metrics and 'items' in nodes_metrics:
            for item in nodes_metrics['items']:
                name = item['metadata']['name']
                usage = item.get('usage', {})
                node_metrics_dict[name] = {
                    'cpu': parse_cpu(usage.get('cpu', '0')),
                    'mem': parse_memory(usage.get('memory', '0'))
                }
    except Exception:
        pass

    try:
        pods_metrics = custom_api.list_cluster_custom_object('metrics.k8s.io', 'v1beta1', 'pods')
        if pods_metrics and 'items' in pods_metrics:
            for item in pods_metrics['items']:
                namespace = item['metadata']['namespace']
                name = item['metadata']['name']
                
                cpu_total = 0.0
                mem_total = 0.0
                
                for container in item.get('containers', []):
                    usage = container.get('usage', {})
                    cpu_total += parse_cpu(usage.get('cpu', '0'))
                    mem_total += parse_memory(usage.get('memory', '0'))
                    
                pod_metrics_dict[f"{namespace}/{name}"] = {
                    'cpu': cpu_total,
                    'mem': mem_total
                }
    except Exception:
        pass

    try:
        nodes = core_v1.list_node().items
        for node in nodes:
            name = node.metadata.name
            capacity = node.status.capacity
            
            cpu_cap = parse_cpu(capacity.get('cpu', '0'))
            mem_cap = parse_memory(capacity.get('memory', '0'))
            
            n_metrics = node_metrics_dict.get(name, {'cpu': 0.0, 'mem': 0.0})
            
            nodes_data.append({
                "name": name,
                "cpu_capacity": cpu_cap,
                "mem_capacity_gb": mem_cap,
                "cpu_usage": n_metrics['cpu'],
                "mem_usage_gb": n_metrics['mem']
            })
    except Exception:
        pass

    try:
        pods = core_v1.list_pod_for_all_namespaces().items
        for pod in pods:
            name = pod.metadata.name
            namespace = pod.metadata.namespace
            status = pod.status.phase
            
            restart_count = 0
            if pod.status.container_statuses:
                restart_count = sum(cs.restart_count for cs in pod.status.container_statuses if cs.restart_count)
                
            cpu_req = 0.0
            mem_req = 0.0
            has_cpu_limit = False
            has_mem_limit = False
            
            if pod.spec.containers:
                for container in pod.spec.containers:
                    if container.resources:
                        requests = container.resources.requests or {}
                        limits = container.resources.limits or {}
                        
                        cpu_req += parse_cpu(requests.get('cpu', '0'))
                        mem_req += parse_memory(requests.get('memory', '0'))
                        
                        if 'cpu' in limits:
                            has_cpu_limit = True
                        if 'memory' in limits:
                            has_mem_limit = True

            p_metrics = pod_metrics_dict.get(f"{namespace}/{name}", {'cpu': 0.0, 'mem': 0.0})
            
            pods_data.append({
                "name": name,
                "namespace": namespace,
                "status": status,
                "restart_count": restart_count,
                "cpu_requested": cpu_req,
                "mem_requested_gb": mem_req,
                "cpu_actual": p_metrics['cpu'],
                "mem_actual_gb": p_metrics['mem'],
                "has_cpu_limit": has_cpu_limit,
                "has_mem_limit": has_mem_limit
            })
    except Exception:
        pass

    try:
        deployments = apps_v1.list_deployment_for_all_namespaces().items
        for dep in deployments:
            deployments_data.append({
                "name": dep.metadata.name,
                "namespace": dep.metadata.namespace,
                "desired_replicas": dep.spec.replicas or 0,
                "ready_replicas": dep.status.ready_replicas or 0
            })
    except Exception:
        pass

    try:
        services = core_v1.list_service_for_all_namespaces().items
        for svc in services:
            port = 0
            if svc.spec.ports and len(svc.spec.ports) > 0:
                port = svc.spec.ports[0].port
                
            services_data.append({
                "name": svc.metadata.name,
                "namespace": svc.metadata.namespace,
                "type": svc.spec.type,
                "port": port
            })
    except Exception:
        pass

    try:
        pvcs = core_v1.list_persistent_volume_claim_for_all_namespaces().items
        for pvc in pvcs:
            capacity_str = "0"
            if pvc.status.capacity and 'storage' in pvc.status.capacity:
                capacity_str = pvc.status.capacity['storage']
            elif pvc.spec.resources and pvc.spec.resources.requests and 'storage' in pvc.spec.resources.requests:
                capacity_str = pvc.spec.resources.requests['storage']
                
            pvcs_data.append({
                "name": pvc.metadata.name,
                "namespace": pvc.metadata.namespace,
                "status": pvc.status.phase,
                "capacity_gb": parse_memory(capacity_str),
                "storage_class": pvc.spec.storage_class_name or ""
            })
    except Exception:
        pass

    return {
        "captured_at": captured_at,
        "cluster_name": cluster_name,
        "nodes": nodes_data,
        "pods": pods_data,
        "deployments": deployments_data,
        "services": services_data,
        "pvcs": pvcs_data
    }

if __name__ == "__main__":
    import json
    result = snapshot()
    print(json.dumps(result, indent=2, default=str))
