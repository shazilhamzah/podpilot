const cache = new Map();

export const cachedFetch = async (url, options = {}) => {
  // We only cache GET requests
  const isGet = !options.method || options.method.toUpperCase() === 'GET';
  
  if (isGet) {
    // Determine if URL contains snapshot_id or snap_a/snap_b
    // Create a dummy URL object to parse search params easily
    let urlObj;
    try {
      urlObj = new URL(url, window.location.origin);
    } catch (e) {
      // If parsing fails, just use normal fetch
      return fetch(url, options);
    }

    const hasSnapshotId = urlObj.searchParams.has('snapshot_id') || 
                          (urlObj.searchParams.has('snap_a') && urlObj.searchParams.has('snap_b'));
    
    // We only cache if a specific snapshot is requested (because they are immutable)
    if (hasSnapshotId) {
      if (cache.has(url)) {
        // Return a cloned response so the body can be consumed multiple times
        return cache.get(url).clone();
      }
      
      const res = await fetch(url, options);
      if (res.ok) {
        cache.set(url, res.clone());
      }
      return res;
    }
  }

  // Fallback to normal fetch
  return fetch(url, options);
};
