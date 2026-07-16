import json

cache_file = "cache.json"
try:
    with open(cache_file, "r") as f:
        cache = json.load(f)
    if "analysis_results" in cache:
        cache["analysis_results"] = {}
        with open(cache_file, "w") as f:
            json.dump(cache, f)
        print("Cleared analysis_results from cache.")
except Exception as e:
    print(e)
