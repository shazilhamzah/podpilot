# PodPilot

You know how frustrating it is when a Kubernetes deployment fails at 2am and you have to dig through endless `kubectl get events` output just to figure out what crashed. PodPilot fixes that by letting you talk to your cluster. 

Instead of writing complex JSONPath queries, you can just ask what went wrong with the payment pod. The app grabs the current state of your cluster and feeds it to an LLM to give you a straight answer.

It also comes with a dashboard. You can see your live resources and figure out which namespaces are burning your AWS bill. The security scanner catches basic misconfigurations like containers running as root. If things break, the drift detection tool compares cluster snapshots so you can spot exactly what changed since yesterday. There is a built-in report generator for when you just need a high-level summary of your cluster health.

## Running locally

You need Node.js, Python 3.12 or newer, and a cluster. Minikube or Docker Desktop works fine.

### 1. Clone the repository

```bash
git clone https://github.com/shazilhamzah/podpilot.git
cd podpilot
```

### 2. Set up the backend

Copy the environment file:
```bash
cp backend/.env.example backend/.env
```

You have to add your API key. If you want to keep your snapshot history across restarts, drop a MongoDB URI in there too.

```env
AI_API_KEY=your_key
MODEL=your_model
MONGO_DB_URI=mongodb+srv://...
```

Start the Python server:
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Start the frontend

Open a second terminal.
```bash
cd frontend
npm install
npm run dev
```
The UI lives at `http://localhost:5173`.

## Deploying to Kubernetes

If you want this running in your actual cluster, we ship a public Docker image. 

First, add your API key to `k8s/podpilot.yaml` under the `podpilot-secrets` section.

```yaml
stringData:
  AI_API_KEY: "your_real_key"
  MODEL: "your_model"
```

Apply the manifest:
```bash
kubectl apply -f k8s/podpilot.yaml
```

This creates a dedicated namespace and spins up the app. We strictly limit the service account to read-only access. It can fetch pods and read events but it can't create or delete anything. 

Port-forward to view the dashboard:
```bash
kubectl port-forward -n podpilot svc/podpilot 8000:80
```
Then open `http://localhost:8000`.

## Architecture details

We don't just dump your entire cluster state into the LLM context window. The backend slices the data based on your specific question to keep latency down and avoid wasting tokens. Snapshots sit in memory temporarily so we aren't hammering the Kubernetes API server with constant requests.

## Troubleshooting

**`ModuleNotFoundError: No module named 'app'` (or similar) when starting the backend**
Make sure you're running `uvicorn` from inside the `backend/` folder, not the repo root. The command is `uvicorn main:app --reload`, run from wherever `main.py` actually lives.

**Actual CPU/memory usage always shows as 0**
This means `metrics-server` isn't installed in your cluster. On Minikube: `minikube addons enable metrics-server`. Give it a minute to start reporting, then confirm with `kubectl top pods`.

**Chat or drift explanations come back empty or rate-limited**
Check that your API key is actually loaded in the environment the backend is running in (`echo $AI_API_KEY` should print something). If it's set and you're still hitting limits, you may be on a free tier with a low tokens-per-minute cap — check your provider's dashboard for the exact limit.