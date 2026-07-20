import { useState } from "react";
import ImpactReport from "./ImpactReport";

// wherever your header/button lives:
const [showReport, setShowReport] = useState(false);

<button onClick={() => setShowReport(true)}>Impact Report</button>

{showReport && <ImpactReport onClose={() => setShowReport(false)} />}