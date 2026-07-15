import { useState } from "react"
import Header from "./components/Header"
import Sidebar from "./components/Sidebar"
import Chat from "./components/Chat"
import CostBreakdown from "./components/CostBreakdown"

const App = () => {
  const [activeTab, setActiveTab] = useState("Chat")

  function renderMain() {
    switch (activeTab) {
      case "Cost Breakdown":
        return <CostBreakdown />
      case "Chat":
      default:
        return <Chat />
    }
  }

  return (
    <div className="flex h-screen flex-col">
      <Header activeTab={activeTab} onTabChange={setActiveTab} />
      <div className="flex flex-1 min-h-0">
        <Sidebar />
        {renderMain()}
      </div>
    </div>
  )
}

export default App
