# PodPilot

PodPilot is a modern, AI-powered Kubernetes cluster copilot and dashboard. It provides real-time insights into your cluster's health, costs, performance, and security, allowing you to converse with your cluster state through an intelligent chat interface.


## Features
- **AI Chat Copilot:** Ask questions about your cluster in plain English. The AI analyzes your cluster's current state to diagnose issues, check resource utilization, and answer queries.
- **Cluster Resources Dashboard:** Live-refreshing visual dashboard displaying all your Pods, Deployments, ReplicaSets, Services, and more.
- **Cost Breakdown:** Analyze which namespaces and pods are wasting resources and how much it costs per month.
- **Security Posture:** Proactive scanning of your cluster for missing resource limits, root containers, and exposed services.
- **Drift Detection:** Compare snapshots of your cluster over time to see what changed (e.g., "what happened between yesterday and today?").
- **Impact Report:** Generate concise, AI-driven executive summaries of your cluster's health.

---

## 🚀 Getting Started (Local Development)

To run PodPilot locally from source, you'll need Node.js, Python 3.12+, and access to a Kubernetes cluster (like Minikube or Docker Desktop).

### 1. Clone the repository
```bash
git clone https://github.com/your-username/podpilot.git
cd podpilot
```

### 2. Configure Environment Variables
Copy the example environment file in the backend directory:
```bash
cp backend/.env.example backend/.env
```
Edit `backend/.env` to include your AI API key and (optionally) your MongoDB URI for persistent snapshot history:
```env
AI_API_KEY=your_api_key_here
MODEL=llama-3.1-8b-instant
MONGO_DB_URI=mongodb+srv://...
```

### 3. Start the Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Start the Frontend
In a new terminal window:
```bash
cd frontend
npm install
npm run dev
```
Open your browser to `http://localhost:5173`.

---

## 🐳 Running on Kubernetes (Public Images)

You can easily deploy PodPilot directly into your Kubernetes cluster using our pre-built public Docker images and the provided deployment YAML file.

### 1. Configure the Secrets File
Edit the `k8s/podpilot.yaml` file. Under the `podpilot-secrets` section, replace the placeholder values with your actual API keys:

```yaml
stringData:
  AI_API_KEY: "your_real_api_key_here"
  MODEL: "llama-3.1-8b-instant"
  # Optional: MongoDB URI for history
  MONGO_DB_URI: "mongodb+srv://..." 
```

### 2. Apply the Manifests
Deploy the application and its required RBAC permissions to your cluster:

```bash
kubectl apply -f k8s/podpilot.yaml
```

This will create a `podpilot` namespace and spin up both the frontend and backend services. The backend runs with a service account that has read-only access to cluster resources, allowing it to generate snapshots safely.

### 3. Access the Dashboard
Once the pods are running, port-forward the frontend service to access it locally:

```bash
kubectl port-forward -n podpilot svc/podpilot-frontend 5173:80
```
Then navigate to `http://localhost:5173`.

---

## 🛡️ Architecture & Security
- **Read-Only Access:** PodPilot's backend service account only requests `get` and `list` permissions across the cluster. It does not have permission to modify, delete, or create resources.
- **Context Slicing:** To ensure low latency and low token costs, PodPilot intelligently slices your cluster snapshot before sending it to the AI, filtering out irrelevant data based on the context of your question.
- **Snapshot Caching:** To avoid overwhelming the Kubernetes API server, snapshots are temporarily cached in memory and MongoDB (if configured).

## License
MIT License. See `LICENSE` for more information.
