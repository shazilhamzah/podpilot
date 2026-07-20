import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Download,
  FileChartColumn,
  Loader2,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
  CheckCircle2,
  X,
} from "lucide-react";
const api = () =>
  import.meta.env.VITE_API_BASE_URL ||
  "http://" + window.location.hostname + ":8000";
const money = (v) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(v || 0);
const date = (v) =>
  v
    ? new Date(v).toLocaleString([], {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "—";
const delta = (v) => (v > 0 ? "+" : v < 0 ? "−" : "") + money(Math.abs(v));
const color = (v) => (v < 0 ? "#50e3c2" : v > 0 ? "#ff9d9d" : "#9099ab");
function Card({ label, value, sub, accent = "#6f7bff" }) {
  return (
    <div className="rounded-2xl border border-[#2a2e40] bg-[#171c2a] p-4">
      <p className="m-0 text-[11px] font-bold uppercase tracking-[.15em] text-[#7f879b]">
        {label}
      </p>
      <p className="m-0 mt-2 text-2xl font-bold text-white">{value}</p>
      {sub && (
        <p className="m-0 mt-1 text-xs" style={{ color: accent }}>
          {sub}
        </p>
      )}
    </div>
  );
}
function Section({ n, title, icon: Icon, children }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-[#2a2e40] bg-[#111624]">
      <div className="flex items-center gap-3 border-b border-[#2a2e40] bg-[#171c2a] px-5 py-4">
        <b className="rounded-lg bg-[#4f6df5]/15 px-2.5 py-1 text-xs text-[#aab4ff]">
          {n}
        </b>
        <Icon size={17} className="text-[#6f7bff]" />
        <h3 className="m-0 text-sm font-bold uppercase tracking-[.12em] text-white">
          {title}
        </h3>
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}
function Items({ items, empty, good = false }) {
  return items?.length ? (
    <div className="space-y-2">
      {items.map((x, i) => (
        <div
          key={i}
          className="flex gap-2 rounded-xl border border-[#2a2e40] bg-[#0d0f18] px-3 py-2 text-xs text-[#c8ccd6]"
        >
          <span style={{ color: good ? "#50e3c2" : "#ff9d9d" }}>
            {good ? <CheckCircle2 size={14} /> : <ShieldAlert size={14} />}
          </span>
          <span>
            {x.resource || x.name || x}
            <small className="ml-2 text-[#7f879b]">{x.check || ""}</small>
          </span>
        </div>
      ))}
    </div>
  ) : (
    <p className="m-0 text-sm text-[#7f879b]">{empty}</p>
  );
}
function Bar({ before, after }) {
  const max = Math.max(before, after, 1);
  return (
    <div className="mt-3 space-y-2 text-xs">
      <div className="flex items-center gap-3">
        <span className="w-12 text-[#7f879b]">Before</span>
        <div className="h-2 flex-1 rounded-full bg-[#252b40]">
          <div
            className="h-2 rounded-full bg-[#69758d]"
            style={{ width: (before / max) * 100 + "%" }}
          />
        </div>
        <b className="w-16 text-right text-white">{money(before)}</b>
      </div>
      <div className="flex items-center gap-3">
        <span className="w-12 text-[#7f879b]">After</span>
        <div className="h-2 flex-1 rounded-full bg-[#252b40]">
          <div
            className="h-2 rounded-full bg-[#50e3c2]"
            style={{ width: (after / max) * 100 + "%" }}
          />
        </div>
        <b className="w-16 text-right text-white">{money(after)}</b>
      </div>
    </div>
  );
}
export default function ImpactReport({ onClose, selectedSnapshotId }) {
  const [snapshots, setSnapshots] = useState([]),
    [fromId, setFromId] = useState(""),
    [toId, setToId] = useState(selectedSnapshotId || ""),
    [report, setReport] = useState(null),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [exporting, setExporting] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    const c = new AbortController();
    (async () => {
      try {
        const r = await fetch(api() + "/report/snapshots", {
          signal: c.signal,
        });
        const list = (await r.json()).snapshots || [];
        setSnapshots(list);
        setToId((x) => (list.some((s) => s.id === x) ? x : list[0]?.id || ""));
        setFromId((x) =>
          list.some((s) => s.id === x) ? x : list[1]?.id || "",
        );
      } catch (e) {
        if (e.name !== "AbortError") setError(e.message);
      } finally {
        if (!c.signal.aborted) setLoading(false);
      }
    })();
    return () => c.abort();
  }, []);
  const request = async (path) => {
    const r = await fetch(
      api() +
        path +
        "?" +
        new URLSearchParams({ from_id: fromId, to_id: toId }),
    );
    if (!r.ok)
      throw Error(
        (await r.json().catch(() => ({}))).detail ||
          "Unable to generate report.",
      );
    return r;
  };
  const generate = async () => {
    setBusy(true);
    setError("");
    try {
      setReport(await (await request("/report/impact")).json());
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const download = async () => {
    setExporting(true);
    try {
      const response = await fetch(api() + "/report/pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(report),
      });

      if (!response.ok) {
        throw Error(
          (await response.json().catch(() => ({}))).detail ||
            "Unable to export report.",
        );
      }

      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "podpilot-impact-report.pdf";
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e.message);
    } finally {
      setExporting(false);
    }
  };
  const choose = (setter, e) => {
    setter(e.target.value);
    setReport(null);
  };
  const can = fromId && toId && fromId !== toId && !loading;
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <section
        role="dialog"
        aria-modal="true"
        className="flex max-h-[94vh] w-full max-w-6xl flex-col overflow-hidden rounded-3xl border border-[#303750] bg-[#0d0f18] shadow-2xl"
      >
        <header className="flex items-center gap-3 border-b border-[#2a2e40] bg-[#111624] px-5 py-4">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#4f6df5]/15 text-[#7d8cff]">
            <FileChartColumn size={21} />
          </div>
          <div className="flex-1">
            <p className="m-0 text-[11px] font-bold uppercase tracking-[.18em] text-[#6f7bff]">
              PodPilot / Analytics
            </p>
            <h2 className="m-0 text-xl font-bold text-white">Impact report</h2>
          </div>
          {report && (
            <button
              onClick={download}
              disabled={exporting}
              className="flex items-center gap-2 rounded-xl border border-[#4f6df5]/50 px-3 py-2 text-xs font-bold text-[#aab4ff]"
            >
              {exporting ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Download size={14} />
              )}
              Export PDF
            </button>
          )}
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-[#7f879b] hover:bg-white/10"
          >
            <X size={20} />
          </button>
        </header>
        <div className="overflow-y-auto p-5">
          <div className="rounded-2xl border border-[#2a2e40] bg-[#111624] p-4">
            <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
              <label className="text-[11px] font-bold uppercase tracking-wider text-[#7f879b]">
                From
                <select
                  value={fromId}
                  onChange={(e) => choose(setFromId, e)}
                  className="mt-2 block w-full rounded-xl border border-[#2a2e40] bg-[#0d0f18] p-2.5 text-sm normal-case tracking-normal text-white"
                >
                  {snapshots.map((s) => (
                    <option key={s.id} value={s.id} disabled={s.id === toId}>
                      {s.name} · {date(s.captured_at)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-[11px] font-bold uppercase tracking-wider text-[#7f879b]">
                To
                <select
                  value={toId}
                  onChange={(e) => choose(setToId, e)}
                  className="mt-2 block w-full rounded-xl border border-[#2a2e40] bg-[#0d0f18] p-2.5 text-sm normal-case tracking-normal text-white"
                >
                  {snapshots.map((s) => (
                    <option key={s.id} value={s.id} disabled={s.id === fromId}>
                      {s.name} · {date(s.captured_at)}
                    </option>
                  ))}
                </select>
              </label>
              <button
                onClick={generate}
                disabled={!can || busy}
                className="h-11 rounded-xl bg-[#586ef5] px-5 text-sm font-bold text-white disabled:opacity-40"
              >
                {busy ? (
                  <Loader2 size={16} className="mx-auto animate-spin" />
                ) : (
                  "Generate report"
                )}
              </button>
            </div>
          </div>
          {error && (
            <p className="mt-4 flex gap-2 rounded-xl border border-[#ff6b6b]/30 bg-[#ff6b6b]/10 p-3 text-sm text-[#ffaaaa]">
              <AlertTriangle size={16} />
              {error}
            </p>
          )}
          {report && (
            <div className="mt-6 space-y-5">
              <div className="rounded-2xl border border-[#4f6df5]/30 bg-gradient-to-br from-[#182046] to-[#111624] p-5">
                <p className="m-0 text-[11px] font-bold uppercase tracking-[.17em] text-[#8d9aff]">
                  Executive summary
                </p>
                <p className="m-0 mt-2 max-w-4xl text-base leading-relaxed text-[#eef0ff]">
                  {report.executive_summary}
                </p>
                <p className="m-0 mt-4 border-t border-white/10 pt-3 text-xs text-[#9099ab]">
                  {report.from_snapshot.cluster_name} ·{" "}
                  {report.from_snapshot.node_count} nodes ·{" "}
                  {date(report.from_snapshot.captured_at)} →{" "}
                  {date(report.to_snapshot.captured_at)}
                </p>
              </div>
              <Section n="01" title="Cost impact" icon={TrendingDown}>
                <div className="grid gap-3 sm:grid-cols-3">
                  <Card
                    label="Monthly cost"
                    value={money(report.cost.total.after)}
                    sub={delta(report.cost.total.change) + " vs baseline"}
                  />
                  <Card
                    label="Monthly waste"
                    value={money(report.cost.waste.after)}
                    sub={delta(report.cost.waste.change) + " vs baseline"}
                    accent={color(report.cost.waste.change)}
                  />
                  <Card
                    label="Proof of impact"
                    value={report.cost.fixed.length}
                    sub="workloads improved or removed"
                    accent="#50e3c2"
                  />
                </div>
                <div className="mt-5 grid gap-5 lg:grid-cols-2">
                  <div>
                    <p className="m-0 text-xs font-bold uppercase tracking-wider text-[#7f879b]">
                      Waste comparison
                    </p>
                    <Bar
                      before={report.cost.waste.before}
                      after={report.cost.waste.after}
                    />
                  </div>
                  <div>
                    <p className="m-0 text-xs font-bold uppercase tracking-wider text-[#7f879b]">
                      Top offenders at target
                    </p>
                    <Items
                      items={report.cost.offenders.map((p) => ({
                        resource: p.namespace + "/" + p.name,
                        check: money(p.waste) + "/mo",
                      }))}
                      empty="No offenders found."
                    />
                  </div>
                </div>
                <div className="mt-5">
                  <p className="m-0 mb-2 text-xs font-bold uppercase tracking-wider text-[#7f879b]">
                    Fixed since baseline
                  </p>
                  <Items
                    items={report.cost.fixed.map((x) => ({
                      resource: x.namespace + "/" + x.name,
                      check: money(x.saved) + "/mo saved · " + x.status,
                    }))}
                    empty="No measurable cost improvements found."
                    good
                  />
                </div>
              </Section>
              <Section
                n="02"
                title="Security posture change"
                icon={ShieldAlert}
              >
                <div className="grid gap-3 sm:grid-cols-3">
                  <Card
                    label="Critical"
                    value={
                      report.security.before.critical +
                      " → " +
                      report.security.after.critical
                    }
                    sub="checks"
                    accent="#ff9d9d"
                  />
                  <Card
                    label="Warnings"
                    value={
                      report.security.before.warning +
                      " → " +
                      report.security.after.warning
                    }
                    sub="checks"
                    accent="#f5c15d"
                  />
                  <Card
                    label="Current score"
                    value={report.security.after.score + "/100"}
                    sub={
                      delta(
                        report.security.after.score -
                          report.security.before.score,
                      ) + " points"
                    }
                    accent="#50e3c2"
                  />
                </div>
                <div className="mt-5 grid gap-5 lg:grid-cols-2">
                  <div>
                    <p className="m-0 mb-2 text-xs font-bold uppercase tracking-wider text-[#7f879b]">
                      New issues
                    </p>
                    <Items
                      items={report.security.new_issues}
                      empty="No new issues since baseline."
                    />
                  </div>
                  <div>
                    <p className="m-0 mb-2 text-xs font-bold uppercase tracking-wider text-[#7f879b]">
                      Resolved issues
                    </p>
                    <Items
                      items={report.security.resolved_issues}
                      empty="No issues resolved."
                      good
                    />
                  </div>
                </div>
              </Section>
              <Section n="03" title="Drift & reliability" icon={TrendingUp}>
                <div className="grid gap-3 sm:grid-cols-4">
                  <Card
                    label="Restarts"
                    value={
                      report.drift.restart_total.before +
                      " → " +
                      report.drift.restart_total.after
                    }
                  />
                  <Card
                    label="Desired replicas"
                    value={
                      report.drift.replica_totals.before +
                      " → " +
                      report.drift.replica_totals.after
                    }
                  />
                  <Card label="New pods" value={report.drift.new_pods.length} />
                  <Card
                    label="Removed pods"
                    value={report.drift.removed_pods.length}
                  />
                </div>
                <div className="mt-5">
                  <p className="m-0 mb-2 text-xs font-bold uppercase tracking-wider text-[#7f879b]">
                    Snapshot diff
                  </p>
                  <Items
                    items={report.drift.changes.map((x) => ({ resource: x }))}
                    empty="No drift detected."
                    good
                  />
                </div>
              </Section>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
