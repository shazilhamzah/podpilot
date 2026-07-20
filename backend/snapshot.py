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
        # Try in-cluster config first (running inside K8s pod with ServiceAccount)
        config.load_incluster_config()
        cluster_name = os.environ.get("CLUSTER_NAME", "kubernetes")
        print("[snapshot] Using in-cluster ServiceAccount config")
    except config.ConfigException:
        # Fall back to local kubeconfig (local dev / minikube)
        try:
            config.load_kube_config()
            cluster_name = "minikube"
        except Exception as e:
            print(f"Error loading kube config: {e}")
            return {}

    core_v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    custom_api = client.CustomObjectsApi()
    batch_v1 = client.BatchV1Api()
    networking_v1 = client.NetworkingV1Api()
    autoscaling_v2 = client.AutoscalingV2Api()

    captured_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    # Refine cluster name from local kubeconfig context if available
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
    statefulsets_data = []
    daemonsets_data = []
    jobs_data = []
    cronjobs_data = []
    ingresses_data = []
    networkpolicies_data = []
    configmaps_data = []
    secrets_data = []
    hpas_data = []

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

    active_pvcs = set()
    try:
        pods = core_v1.list_pod_for_all_namespaces().items
        for pod in pods:
            name = pod.metadata.name
            namespace = pod.metadata.namespace
            status = pod.status.phase
            
            pod_non_root = False
            if pod.spec.security_context and pod.spec.security_context.run_as_non_root:
                pod_non_root = True
            
            runs_as_root = not pod_non_root
            
            if pod.spec.volumes:
                for vol in pod.spec.volumes:
                    if vol.persistent_volume_claim:
                        active_pvcs.add(vol.persistent_volume_claim.claim_name)
            
            restart_count = 0
            if pod.status.container_statuses:
                restart_count = sum(cs.restart_count for cs in pod.status.container_statuses if cs.restart_count)
                
            cpu_req = 0.0
            mem_req = 0.0
            has_cpu_limit = False
            has_mem_limit = False
            images = []
            probes = []
            lifecycle_hooks = []
            
            if pod.spec.containers:
                for container in pod.spec.containers:
                    if container.image and container.image not in images:
                        images.append(container.image)
                        
                    if getattr(container, 'liveness_probe', None):
                        probes.append({"container": container.name, "type": "liveness", "details": str(container.liveness_probe)})
                    if getattr(container, 'readiness_probe', None):
                        probes.append({"container": container.name, "type": "readiness", "details": str(container.readiness_probe)})
                    if getattr(container, 'lifecycle', None):
                        lifecycle_hooks.append({"container": container.name, "details": str(container.lifecycle)})
                        
                    if container.security_context and container.security_context.run_as_non_root is not None:
                        if container.security_context.run_as_non_root is False:
                            runs_as_root = True
                    elif not pod_non_root:
                        runs_as_root = True
                    
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
                "has_mem_limit": has_mem_limit,
                "images": images,
                "probes": probes,
                "lifecycle_hooks": lifecycle_hooks,
                "runs_as_root": runs_as_root
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
                "storage_class": pvc.spec.storage_class_name or "",
                "is_attached": pvc.metadata.name in active_pvcs
            })
    except Exception:
        pass

    try:
        for s in apps_v1.list_stateful_set_for_all_namespaces().items:
            statefulsets_data.append({"name": s.metadata.name, "namespace": s.metadata.namespace, "desired_replicas": getattr(s.spec, 'replicas', 0), "ready_replicas": getattr(s.status, 'ready_replicas', 0)})
        for ds in apps_v1.list_daemon_set_for_all_namespaces().items:
            daemonsets_data.append({"name": ds.metadata.name, "namespace": ds.metadata.namespace, "desired_number_scheduled": getattr(ds.status, 'desired_number_scheduled', 0), "number_ready": getattr(ds.status, 'number_ready', 0)})
        for j in batch_v1.list_job_for_all_namespaces().items:
            jobs_data.append({"name": j.metadata.name, "namespace": j.metadata.namespace, "active": getattr(j.status, 'active', 0), "succeeded": getattr(j.status, 'succeeded', 0), "failed": getattr(j.status, 'failed', 0)})
        for cj in batch_v1.list_cron_job_for_all_namespaces().items:
            cronjobs_data.append({"name": cj.metadata.name, "namespace": cj.metadata.namespace, "schedule": cj.spec.schedule, "concurrency_policy": getattr(cj.spec, 'concurrency_policy', 'Allow')})
        for i in networking_v1.list_ingress_for_all_namespaces().items:
            ingresses_data.append({"name": i.metadata.name, "namespace": i.metadata.namespace, "rules": str(i.spec.rules)})
        for np in networking_v1.list_network_policy_for_all_namespaces().items:
            networkpolicies_data.append({"name": np.metadata.name, "namespace": np.metadata.namespace, "pod_selector": str(np.spec.pod_selector), "policy_types": str(np.spec.policy_types)})
        for cm in core_v1.list_config_map_for_all_namespaces().items:
            configmaps_data.append({"name": cm.metadata.name, "namespace": cm.metadata.namespace, "keys": list(cm.data.keys()) if cm.data else []})
        for sec in core_v1.list_secret_for_all_namespaces().items:
            secrets_data.append({"name": sec.metadata.name, "namespace": sec.metadata.namespace, "type": sec.type, "keys": list(sec.data.keys()) if sec.data else []})
        for hpa in autoscaling_v2.list_horizontal_pod_autoscaler_for_all_namespaces().items:
            hpas_data.append({"name": hpa.metadata.name, "namespace": hpa.metadata.namespace, "min_replicas": hpa.spec.min_replicas, "max_replicas": hpa.spec.max_replicas, "metrics": str(hpa.spec.metrics)})
    except Exception as e:
        print(f"Error fetching extended resources: {e}")

    return {
        "captured_at": captured_at,
        "cluster_name": cluster_name,
        "nodes": nodes_data,
        "pods": pods_data,
        "deployments": deployments_data,
        "statefulsets": statefulsets_data,
        "daemonsets": daemonsets_data,
        "jobs": jobs_data,
        "cronjobs": cronjobs_data,
        "services": services_data,
        "ingresses": ingresses_data,
        "networkpolicies": networkpolicies_data,
        "configmaps": configmaps_data,
        "secrets": secrets_data,
        "pvcs": pvcs_data,
        "hpas": hpas_data
    }

if __name__ == "__main__":
    import json
    result = snapshot()
    print(json.dumps(result, indent=2, default=str))
