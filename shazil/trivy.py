import subprocess
import json
import datetime
from health import analyze

def get_unique_images(snapshot: dict) -> list[str]:
    images = set()
    for pod in snapshot.get("pods", []):
        if "image" in pod and pod["image"]:
            images.add(pod["image"])
    
    if not images:
        images = set([
            "nginx:1.25",
            "redis:latest",
            "registry.k8s.io/metrics-server/metrics-server:v0.7.2"
        ])
    return list(images)

def scan_image(image: str) -> dict:
    print(f"Scanning {image}... (first run may take 1-2 mins)")
    try:
        result = subprocess.run(
            ["trivy", "image", "--format", "json", "--quiet", "--severity", "CRITICAL,HIGH", "--no-progress", image],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode != 0 and not result.stdout.strip():
            return {
                "image": image,
                "status": "error",
                "critical": 0,
                "high": 0,
                "cves": [],
                "error": f"Trivy failed with return code {result.returncode}: {result.stderr}"
            }
            
        data = json.loads(result.stdout)
        
        critical_count = 0
        high_count = 0
        cves = []
        
        results_array = data.get("Results", [])
        for res in results_array:
            for vuln in res.get("Vulnerabilities", []):
                severity = vuln.get("Severity", "")
                if severity == "CRITICAL":
                    critical_count += 1
                elif severity == "HIGH":
                    high_count += 1
                else:
                    continue
                    
                cves.append({
                    "id": vuln.get("VulnerabilityID", ""),
                    "package": vuln.get("PkgName", ""),
                    "installed_version": vuln.get("InstalledVersion", ""),
                    "fixed_version": vuln.get("FixedVersion", ""),
                    "severity": severity,
                    "title": vuln.get("Title", "")
                })
                
        return {
            "image": image,
            "status": "scanned",
            "critical": critical_count,
            "high": high_count,
            "cves": cves,
            "error": None
        }
    except subprocess.TimeoutExpired:
        return {
            "image": image,
            "status": "timeout",
            "critical": 0,
            "high": 0,
            "cves": [],
            "error": "Scan timed out after 120 seconds"
        }
    except Exception as e:
        return {
            "image": image,
            "status": "error",
            "critical": 0,
            "high": 0,
            "cves": [],
            "error": str(e)
        }

def scan_all_images(snapshot: dict) -> dict:
    images = get_unique_images(snapshot)
    total_critical = 0
    total_high = 0
    scanned_images = []
    
    total = len(images)
    for i, image in enumerate(images):
        print(f"Scanning image {i+1}/{total}: {image}")
        res = scan_image(image)
        scanned_images.append(res)
        total_critical += res.get("critical", 0)
        total_high += res.get("high", 0)
        
    return {
        "scanned_at": datetime.datetime.utcnow().isoformat() + "Z",
        "total_images": total,
        "total_critical": total_critical,
        "total_high": total_high,
        "images": scanned_images
    }

def trivy_ai_summary(scan_results: dict) -> str:
    summary_text = ""
    for image in scan_results.get("images", []):
        if image.get("critical", 0) > 0 or image.get("high", 0) > 0:
            summary_text += f"Image {image['image']}: "
            summary_text += f"{image['critical']} CRITICAL, "
            summary_text += f"{image['high']} HIGH CVEs. "
            
            top_cves = image.get("cves", [])[:3]
            for cve in top_cves:
                summary_text += f"{cve['id']} affects {cve['package']}. "
                
    if not summary_text:
        return "No critical or high severity CVEs found in scanned images."
        
    prompt = f"""You are analyzing container image vulnerability scan results
for a Kubernetes cluster. Here are the findings from Trivy:

{summary_text}

Summarize the security risk in 3-5 sentences. Name specific images and
CVE IDs. Indicate which findings are most urgent to patch and why.
If fixed versions are available mention that patches exist."""
    
    return analyze(prompt, {})

def trivy_to_issues(scan_results: dict) -> list[dict]:
    issues = []
    for image in scan_results.get("images", []):
        crit_count = image.get("critical", 0)
        high_count = image.get("high", 0)
        if crit_count > 0 or high_count > 0:
            severity = "critical" if crit_count > 0 else "warning"
            image_name = image["image"]
            image_short_name = image_name.split("/")[-1]
            
            issues.append({
                "severity": severity,
                "title": f"CVE vulnerabilities in {image_short_name}",
                "description": f"{crit_count} critical, {high_count} high severity CVEs detected",
                "affected_resource": image_name,
                "category": "security"
            })
    return issues

if __name__ == "__main__":
    from snapshot import snapshot
    from cost import enrich_with_cost
    from sanitize import sanitize

    print("Building snapshot...")
    clean = sanitize(enrich_with_cost(snapshot()))

    print("\nStarting Trivy scans (first run downloads vulnerability DB)...")
    results = scan_all_images(clean)

    print(f"\nScan complete.")
    print(f"Images scanned: {results['total_images']}")
    print(f"Total CRITICAL CVEs: {results['total_critical']}")
    print(f"Total HIGH CVEs:     {results['total_high']}")

    print("\nPer-image results:")
    for img in results["images"]:
        status = img["status"]
        if status == "scanned":
            print(f"  {img['image']}: "
                  f"{img['critical']} critical, {img['high']} high")
        else:
            print(f"  {img['image']}: {status} — {img.get('error','')}")

    print("\nGenerating AI summary...")
    summary = trivy_ai_summary(results)
    print("\nAI SUMMARY:")
    print(summary)

    print("\nStructured issues:")
    issues = trivy_to_issues(results)
    for issue in issues:
        print(f"  [{issue['severity'].upper()}] {issue['title']}")
