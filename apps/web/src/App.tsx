import { type ReactNode, useState } from "react";
import { loadWebConfiguration } from "./config";
import type { DemoPrincipal } from "./types";
import { currentPrincipal, Shell } from "./shared";
import { BriefingPage } from "./pages/BriefingPage";
import { MonthPage } from "./pages/MonthPage";
import { ReportPage } from "./pages/ReportPage";
import { CallPage } from "./pages/CallPage";
import { FailurePage } from "./pages/FailurePage";
import { PlaybookPage } from "./pages/PlaybookPage";
import { UploadPage } from "./pages/UploadPage";
import { OperationsPage } from "./pages/OperationsPage";

function HealthPage(): ReactNode {
  return <section className="page-title"><div className="eyebrow">Operational status</div><h1>System health</h1><p>Use the content-free liveness and readiness endpoints for API and worker health.</p></section>;
}

export function App({ path = window.location.pathname }: { path?: string }): ReactNode {
  loadWebConfiguration();
  const [principal, setPrincipal] = useState<DemoPrincipal>(currentPrincipal);
  let page: ReactNode;
  const callMatch = path.match(/^\/calls\/([A-Za-z0-9._:-]+)$/);
  const callId = callMatch?.[1];
  const reportMatch = path.match(/^\/reports\/(\d{4}-\d{2}-\d{2})$/);
  const monthMatch = path.match(/^\/months\/(\d{4}-\d{2})$/);
  if (callId) page = <CallPage callId={callId} principal={principal} />;
  else if (reportMatch?.[1]) page = <ReportPage principal={principal} initialDate={reportMatch[1]} />;
  else if (monthMatch?.[1]) page = <MonthPage principal={principal} monthKey={monthMatch[1]} />;
  else if (path === "/uploads") page = <UploadPage principal={principal} />;
  else if (path === "/failures") page = <FailurePage principal={principal} />;
  else if (path === "/playbooks") page = <PlaybookPage principal={principal} />;
  else if (path === "/operations") page = <OperationsPage principal={principal} />;
  else if (path === "/health") page = <HealthPage />;
  else page = <BriefingPage principal={principal} selectedDate={path.match(/^\/briefing\/(\d{4}-\d{2}-\d{2})$/)?.[1]} />;
  return <Shell principal={principal} setPrincipal={setPrincipal} path={path}>{page}</Shell>;
}
