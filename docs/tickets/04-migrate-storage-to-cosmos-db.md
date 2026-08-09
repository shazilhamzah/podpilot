# 04 — Migrate Persistent Storage to Azure Cosmos DB

**What to build:** Point the app's database connection at Azure Cosmos DB for MongoDB instead of MongoDB Atlas. Cosmos DB exposes the MongoDB wire protocol, so `motor` (the existing async driver) requires zero code changes — only the connection string changes. The old `MONGO_DB_USER` and `MONGO_DB_PWD` fields are retired; a single `MONGO_DB_URI` containing the Cosmos DB primary connection string replaces them. When done, snapshot history persists correctly across pod restarts and survives a full redeployment to AKS.

**Blocked by:** 01 — Provision Core Azure Infrastructure (the Cosmos DB account and `podpilot` database must exist before the connection string can be retrieved).

**Status:** done

- [x] `MONGO_DB_URI` in the Kubernetes secret (`podpilot.yaml`) points to the Cosmos DB connection string and includes `retrywrites=false`
- [x] `MONGO_DB_USER` and `MONGO_DB_PWD` fields removed from the Kubernetes secret
- [x] Local `backend/.env` updated with the Cosmos DB URI (same string, works identically locally)
- [x] `.env.example` removes `MONGO_DB_USER` / `MONGO_DB_PWD`; `MONGO_DB_URI` example shows the Cosmos DB format
- [x] App starts successfully and the `/api/status` endpoint returns healthy when `MONGO_DB_URI` points to Cosmos DB
- [x] Snapshots written during one pod lifecycle are readable after a pod restart (persistence verified)
