import { useState, useEffect } from "react"
import Header from "./components/Header"
import Sidebar from "./components/Sidebar"
import Chat from "./components/Chat"
import CostBreakdown from "./components/CostBreakdown"
import DriftDetection from "./components/DriftDetection"
import Security from "./components/Security"

const App = () => {
  const [activeTab, setActiveTab] = useState("Chat")
  const [snapshots, setSnapshots] = useState([])
  const [selectedSnapshotId, setSelectedSnapshotId] = useState("")

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

  function renderMain() {
    switch (activeTab) {
      case "Cost Breakdown":
        return <CostBreakdown selectedSnapshotId={selectedSnapshotId} />
      case "Drift Detection":
        return (
          <DriftDetection 
            snapshots={snapshots} 
            selectedSnapshotId={selectedSnapshotId} 
            setSelectedSnapshotId={setSelectedSnapshotId} 
          />
        )
      case "Security":
        return <Security selectedSnapshotId={selectedSnapshotId} snapshots={snapshots} />
      case "Chat":
      default:
        return <Chat key={selectedSnapshotId} selectedSnapshotId={selectedSnapshotId} />
    }
  }

  return (
    <div className="flex h-screen flex-col">
      <Header 
        activeTab={activeTab} 
        onTabChange={setActiveTab} 
        snapshots={snapshots}
        selectedSnapshotId={selectedSnapshotId}
        setSelectedSnapshotId={setSelectedSnapshotId}
        onSnapshotCreated={() => fetchHistory(true)}
      />
      <div className="flex flex-1 min-h-0">
        <Sidebar selectedSnapshotId={selectedSnapshotId} activeTab={activeTab} />
        {renderMain()}
      </div>
    </div>
  )
}

export default App
