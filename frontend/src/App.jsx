import { useState, useEffect } from "react"
import { flushSync } from "react-dom"
import Header from "./components/Header"
import Sidebar from "./components/Sidebar"
import Chat from "./components/Chat"
import CostBreakdown from "./components/CostBreakdown"
import DriftDetection from "./components/DriftDetection"
import Security from "./components/Security"
import ImpactReport from "./components/ImpactReport"
import ClusterResources from "./components/ClusterResources"

const App = () => {
  const [showReport, setShowReport] = useState(false)
  const [activeTab, setActiveTab] = useState("Chat")
  const [snapshots, setSnapshots] = useState([])
  const [selectedSnapshotId, setSelectedSnapshotId] = useState("")
  const [hideSystemK8s, setHideSystemK8s] = useState(true)

  async function fetchHistory(selectLatest = false) {
    try {
      const backendUrl = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;
      const res = await fetch(`${backendUrl}/history`);
      if (res.ok) {
        const data = await res.json();
        const list = data.snapshots || [];
        setSnapshots(list);
        if (list.length > 0) {
          if (selectLatest || !selectedSnapshotId || !list.some(s => s.id === selectedSnapshotId)) {
            setSelectedSnapshotId(list[0].id);
          }
        }
      }
    } catch (e) {
      console.error("Failed to fetch history", e);
    }
  }

  useEffect(() => {
    fetchHistory();
  }, []);

  const navigateToTab = (newTab) => {
    if (newTab === activeTab) return;
    if (!document.startViewTransition) {
      setActiveTab(newTab);
      return;
    }
    document.startViewTransition(() => {
      flushSync(() => {
        setActiveTab(newTab);
      });
    });
  };

  // We remove renderMain so we can keep Chat mounted but hidden.
  // This prevents Chat from losing its state when changing tabs.

  return (
    <div className="flex h-screen flex-col">
      <Header 
        activeTab={activeTab} 
        onTabChange={navigateToTab} 
        snapshots={snapshots}
        selectedSnapshotId={selectedSnapshotId}
        setSelectedSnapshotId={setSelectedSnapshotId}
        onSnapshotCreated={() => fetchHistory(true)}
        hideSystemK8s={hideSystemK8s}
        setHideSystemK8s={setHideSystemK8s}
        onImpactReport={() => setShowReport(true)}
      />
      <div className="flex flex-1 min-h-0">
        <Sidebar selectedSnapshotId={selectedSnapshotId} activeTab={activeTab} hideSystemK8s={hideSystemK8s} />
        <main className="main-content flex-1 min-w-0 flex flex-col">
          <div className={activeTab === "Chat" ? "flex flex-col h-full" : "hidden"}>
            <Chat key={selectedSnapshotId} selectedSnapshotId={selectedSnapshotId} hideSystemK8s={hideSystemK8s} />
          </div>
          {activeTab === "Cost Breakdown" && <CostBreakdown selectedSnapshotId={selectedSnapshotId} hideSystemK8s={hideSystemK8s} />}
          {activeTab === "Drift Detection" && (
            <DriftDetection 
              snapshots={snapshots} 
              selectedSnapshotId={selectedSnapshotId} 
              setSelectedSnapshotId={setSelectedSnapshotId} 
              hideSystemK8s={hideSystemK8s}
            />
          )}
          {activeTab === "Security" && <Security selectedSnapshotId={selectedSnapshotId} snapshots={snapshots} hideSystemK8s={hideSystemK8s} />}
          {activeTab === "Cluster Resources" && <ClusterResources selectedSnapshotId={selectedSnapshotId} hideSystemK8s={hideSystemK8s} />}
        </main>
      </div>
      {showReport && <ImpactReport onClose={() => setShowReport(false)} selectedSnapshotId={selectedSnapshotId} />}
    </div>
  )
}

export default App
