import subprocess
import json
import datetime
import os
import asyncio
from health import analyze

# ────────────────────────────────────────────────────────────────────────────
# MongoDB-backed persistent image scan cache
# Survives pod restarts. Falls back to in-memory dict if DB is unavailable.
# ────────────────────────────────────────────────────────────────────────────

# In-memory layer: loaded eagerly from MongoDB at startup (see warm_trivy_cache)
_mem_cache: dict = {}
_cache_warmed: bool = False


async def warm_trivy_cache():
    """Load all existing scan results from MongoDB into memory at startup."""
    global _mem_cache, _cache_warmed
    try:
        from db import db
        if db is None:
            return
        async for doc in db.image_scans.find({}, {"_id": 0}):
            image = doc.get("image")
            if image:
                _mem_cache[image] = doc
        print(f"[TRIVY CACHE] Warmed {len(_mem_cache)} image scan results from MongoDB.")
    except Exception as e:
        print(f"[TRIVY CACHE] Failed to warm from MongoDB: {e}")
    finally:
        _cache_warmed = True


async def _save_to_db(result: dict):
    """Persist a single scan result to MongoDB (upsert by image name)."""
    try:
        from db import db
        if db is None:
            return
        await db.image_scans.update_one(
            {"image": result["image"]},
            {"$set": result},
            upsert=True
        )
    except Exception as e:
        print(f"[TRIVY CACHE] Failed to save to MongoDB: {e}")


def get_unique_images(snapshot: dict) -> list[str]:
    images = set()
    for pod in snapshot.get("pods", []):
        if "images" in pod and pod["images"]:
            for img in pod["images"]:
                images.add(img)
        elif "image" in pod and pod["image"]:
            images.add(pod["image"])
    return list(images)


def _run_trivy(image: str) -> dict:
    """Synchronous trivy scan — runs in a thread pool to avoid blocking."""
    print(f"Scanning {image}... (first run may take 1-2 mins)")
    try:
        result = subprocess.run(
            ["trivy", "image", "--format", "json", "--quiet",
             "--severity", "CRITICAL,HIGH", "--no-progress", image],
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
                "error": f"Trivy failed ({result.returncode}): {result.stderr[:200]}"
            }

        data = json.loads(result.stdout)

        critical_count = 0
        high_count = 0
        cves = []

        for res in data.get("Results", []):
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
            "scanned_at": datetime.datetime.utcnow().isoformat() + "Z",
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


async def scan_image_async(image: str) -> dict:
    """
    Async image scan with a 3-layer cache:
      1. In-memory dict  (fastest — same pod lifetime)
      2. MongoDB         (survives pod restarts)
      3. Run trivy       (only if both caches miss)
    """
    # Layer 1: in-memory
    if image in _mem_cache:
        print(f"Skipping {image} (already in global cache)")
        return _mem_cache[image]

    # Layer 2: MongoDB (handles the pod-restart case)
    try:
        from db import db
        if db is not None:
            doc = await db.image_scans.find_one({"image": image}, {"_id": 0})
            if doc:
                print(f"Skipping {image} (already in global cache)")
                _mem_cache[image] = doc
                return doc
    except Exception:
        pass  # Fall through to actual scan

    # Layer 3: Run the scan in a thread so we don't block the async event loop
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run_trivy, image)

    # Populate both cache layers
    _mem_cache[image] = result
    await _save_to_db(result)

    return result


async def scan_all_images(snapshot: dict) -> dict:
    """Scan all unique images in a snapshot concurrently."""
    images = get_unique_images(snapshot)
    total = len(images)

    for i, image in enumerate(images):
        print(f"Scanning image {i+1}/{total}: {image}")

    # Run all scans concurrently instead of sequentially
    tasks = [scan_image_async(image) for image in images]
    results = await asyncio.gather(*tasks)

    total_critical = sum(r.get("critical", 0) for r in results)
    total_high = sum(r.get("high", 0) for r in results)

    return {
        "scanned_at": datetime.datetime.utcnow().isoformat() + "Z",
        "total_images": total,
        "total_critical": total_critical,
        "total_high": total_high,
        "images": list(results)
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

    async def main():
        print("Building snapshot...")
        clean = sanitize(enrich_with_cost(snapshot()))

        print("\nStarting Trivy scans (first run downloads vulnerability DB)...")
        results = await scan_all_images(clean)

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

    asyncio.run(main())
