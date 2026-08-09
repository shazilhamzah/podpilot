"""Impact-report data builders based on saved cluster snapshots."""

from datetime import datetime
from html import escape
import asyncio
import os

from bson import ObjectId
from fastapi import HTTPException

from db import db
from drift_detection import diff_snapshots
from security import run_all_checks


def _report_cost(s):
    c=s.get('cost_summary') or {}
    return {'total': float(c.get('total_cost_per_hour',0) or 0)*730, 'waste': float(c.get('total_wasted_per_month',0) or 0)}

def _security_report(s):
    checks=run_all_checks(s); critical_names={'Root containers','Open NodePorts'}
    out=[{'name':c['name'],'passed':c['passed'],'severity':'critical' if c['name'] in critical_names else 'warning','resources':c.get('affected',[])} for c in checks]
    critical=sum(not c['passed'] and c['severity']=='critical' for c in out); warning=sum(not c['passed'] and c['severity']=='warning' for c in out)
    return {'checks':out,'critical':critical,'warning':warning,'score':max(0,100-critical*20-warning*10)}

def _security_report_diff(a,b):
    old,new=_security_report(a),_security_report(b)
    oi={(c['name'],r) for c in old['checks'] if not c['passed'] for r in c['resources']}; ni={(c['name'],r) for c in new['checks'] if not c['passed'] for r in c['resources']}
    def fmt(keys,current): return [{'check':k[0],'resource':k[1],'severity':next(c['severity'] for c in current['checks'] if c['name']==k[0])} for k in sorted(keys)]
    return {'before':{k:old[k] for k in ('critical','warning','score')},'after':{k:new[k] for k in ('critical','warning','score')},'new_issues':fmt(ni-oi,new),'resolved_issues':fmt(oi-ni,old)}

def _fixed_cost(a,b):
    new={(p.get('namespace','default'),p.get('name','Unknown')):p for p in b.get('pods',[])}; out=[]
    for p in a.get('pods',[]):
        old=float(p.get('wasted_cost_per_month',0) or 0); q=new.get((p.get('namespace','default'),p.get('name','Unknown'))); after=float(q.get('wasted_cost_per_month',0) or 0) if q else 0
        if old>.01 and (q is None or after<old-.01): out.append({'name':p.get('name','Unknown'),'namespace':p.get('namespace','default'),'before':old,'after':after,'saved':old-after,'status':'removed' if q is None else 'improved'})
    return sorted(out,key=lambda x:x['saved'],reverse=True)[:8]

def _report_summary(r):
    d=r['cost']['waste']['change']; word='fell' if d<0 else 'rose' if d>0 else 'held steady'
    fallback='Monthly waste %s from %0.0f to %0.0f; %d workload improvements were identified, and the current security score is %d/100.' % (word,r['cost']['waste']['before'],r['cost']['waste']['after'],len(r['cost']['fixed']),r['security']['after']['score'])
    client = get_ai_client()
    if not client:
        return fallback
    try:
        facts={'cost':r['cost'],'security':r['security'],'drift_changes':len(r['drift']['changes'])}
        x=client.chat.completions.create(model=get_model_name(),temperature=.2,max_tokens=140,messages=[{'role':'system','content':'Write one concise executive summary paragraph for a Kubernetes impact report.'},{'role':'user','content':'Use only these facts; mention cost/waste, security score, and reliability: '+str(facts)}])
        return x.choices[0].message.content.strip()
    except Exception: return fallback


def _resource_counts(snapshot: dict) -> dict:
    return {key: len(snapshot.get(key, [])) for key in ("pods", "deployments", "services", "pvcs", "nodes")}


def _cost_summary(snapshot: dict) -> dict:
    costs = snapshot.get("cost_summary") or {}
    return {
        "monthly_cost": float(costs.get("total_cost_per_hour", 0) or 0) * 730,
        "monthly_waste": float(costs.get("total_wasted_per_month", 0) or 0),
    }


def _unhealthy_pods(snapshot: dict) -> list[dict]:
    healthy_states = {"running", "succeeded", "completed"}
    unhealthy = []
    for pod in snapshot.get("pods", []):
        status = pod.get("status") or pod.get("status_phase") or "Unknown"
        if str(status).lower() not in healthy_states or pod.get("restart_count", 0) > 0:
            unhealthy.append({
                "name": pod.get("name", "Unknown pod"),
                "namespace": pod.get("namespace", "default"),
                "status": status,
                "restarts": pod.get("restart_count", 0),
            })
    return unhealthy


def _serialize_snapshot(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc.get("name") or "Snapshot",
        "captured_at": doc.get("captured_at"),
        "comments": doc.get("comments") or "",
    }


async def list_report_snapshots() -> dict:
    if db is None:
        raise HTTPException(status_code=503, detail="Snapshot storage is unavailable.")
    cursor = db.snapshots.find({}, {"_id": 1, "name": 1, "comments": 1, "captured_at": 1})
    results = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
        results.append(doc)
    results.sort(key=lambda x: x.get("captured_at", ""), reverse=True)
    return {"snapshots": results}


async def build_impact_report(from_id: str, to_id: str) -> dict:
    if db is None:
        raise HTTPException(status_code=503, detail="Snapshot storage is unavailable.")
    if from_id == to_id:
        raise HTTPException(status_code=422, detail="Choose two different snapshots to compare.")
    try:
        from_object_id, to_object_id = ObjectId(from_id), ObjectId(to_id)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="An invalid snapshot ID was supplied.") from exc

    from_doc = await db.snapshots.find_one({"_id": from_object_id})
    to_doc = await db.snapshots.find_one({"_id": to_object_id})
    if not from_doc or not to_doc:
        raise HTTPException(status_code=404, detail="One or both snapshots could not be found.")

    before, after = from_doc.get("snapshot") or {}, to_doc.get("snapshot") or {}
    before_counts, after_counts = _resource_counts(before), _resource_counts(after)
    before_costs, after_costs = _cost_summary(before), _cost_summary(after)
    changes = diff_snapshots(before, after)
    resources = {
        name: {"before": before_counts[name], "after": after_counts[name], "change": after_counts[name] - before_counts[name]}
        for name in before_counts
    }
    before, after = from_doc.get('snapshot') or {}, to_doc.get('snapshot') or {}
    old_cost, new_cost = _report_cost(before), _report_cost(after)
    changes = diff_snapshots(before, after)
    old_pods = {(p.get('namespace','default'),p.get('name','Unknown')):p for p in before.get('pods',[])}
    new_pods = {(p.get('namespace','default'),p.get('name','Unknown')):p for p in after.get('pods',[])}
    report = {
        'from_snapshot': {**_serialize_snapshot(from_doc), 'cluster_name': before.get('cluster_name','Unknown cluster'), 'node_count': len(before.get('nodes',[]))},
        'to_snapshot': {**_serialize_snapshot(to_doc), 'cluster_name': after.get('cluster_name','Unknown cluster'), 'node_count': len(after.get('nodes',[]))},
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'cost': {'total': {'before':old_cost['total'],'after':new_cost['total'],'change':new_cost['total']-old_cost['total']}, 'waste': {'before':old_cost['waste'],'after':new_cost['waste'],'change':new_cost['waste']-old_cost['waste']}, 'offenders': sorted([{'name':p.get('name','Unknown'),'namespace':p.get('namespace','default'),'waste':float(p.get('wasted_cost_per_month',0) or 0),'cost':float(p.get('cost_per_hour',0) or 0)*730} for p in after.get('pods',[])], key=lambda x:x['waste'], reverse=True)[:3], 'fixed':_fixed_cost(before,after)},
        'security': _security_report_diff(before,after),
        'drift': {'changes':changes,'new_pods':[{'name':k[1],'namespace':k[0]} for k in new_pods.keys()-old_pods.keys()],'removed_pods':[{'name':k[1],'namespace':k[0]} for k in old_pods.keys()-new_pods.keys()],'restart_total':{'before':sum(p.get('restart_count',0) or 0 for p in before.get('pods',[])),'after':sum(p.get('restart_count',0) or 0 for p in after.get('pods',[]))},'replica_totals':{'before':sum(d.get('desired_replicas',0) or 0 for d in before.get('deployments',[])),'after':sum(d.get('desired_replicas',0) or 0 for d in after.get('deployments',[]))}},
    }
    report['executive_summary'] = await asyncio.get_running_loop().run_in_executor(None, _report_summary, report)
    report['summary'] = {'changes_detected':len(changes),'monthly_cost':report['cost']['total'],'monthly_waste':report['cost']['waste']}
    return report


def render_report_html(report: dict) -> str:
    """Render a polished executive PDF from the already-generated report payload."""
    def money(value):
        return "$" + format(value or 0, ",.2f")

    def signed(value):
        prefix = "+" if value > 0 else "−" if value < 0 else ""
        return prefix + money(abs(value))

    def issue_list(items, empty, positive=False):
        if not items:
            return '<div class="empty">%s</div>' % empty
        cls = "positive" if positive else "negative"
        return "".join(
            '<div class="issue %s"><span class="issue-icon">%s</span><div><b>%s</b><small>%s</small></div></div>'
            % (cls, "✓" if positive else "!", escape(item.get("resource", "")), escape(item.get("check", "")))
            for item in items
        )

    def pills(items, cls):
        return "".join(
            '<span class="pill %s">%s / %s</span>' % (cls, escape(item["namespace"]), escape(item["name"]))
            for item in items
        ) or '<span class="empty">None</span>'

    cost = report["cost"]
    security = report["security"]
    drift = report["drift"]
    score = security["after"]["score"]
    score_color = "#18a982" if score >= 80 else "#d28a18" if score >= 55 else "#d04a4a"
    maximum = max(cost["waste"]["before"], cost["waste"]["after"], 1)
    before_width = cost["waste"]["before"] / maximum * 100
    after_width = cost["waste"]["after"] / maximum * 100

    offenders = "".join(
        '<tr><td class="rank">%02d</td><td><b>%s</b><small>%s</small></td><td class="amount">%s<span>/mo</span></td></tr>'
        % (i, escape(item["name"]), escape(item["namespace"]), money(item["waste"]))
        for i, item in enumerate(cost["offenders"], 1)
    ) or '<tr><td colspan="3" class="empty">No cost offenders found.</td></tr>'

    fixed = "".join(
        '<tr><td><b>%s</b><small>%s</small></td><td>%s</td><td>%s</td><td class="success">%s</td></tr>'
        % (escape(item["name"]), escape(item["namespace"]), money(item["before"]), money(item["after"]), money(item["saved"]))
        for item in cost["fixed"]
    ) or '<tr><td colspan="4" class="empty">No measurable improvements found.</td></tr>'

    changes = "".join('<li>%s</li>' % escape(item) for item in drift["changes"]) or "<li>No drift detected.</li>"
    score_dash = 263.89 * score / 100

    html = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; background: #f4f6fb; color: #17233d; font-family: Arial, Helvetica, sans-serif; font-size: 10px; line-height: 1.45; }
.page { padding: 34px 42px 30px; page-break-after: always; }
.page:last-child { page-break-after: auto; }
 
/* ---- COVER PAGE (fixed) ---- */
.cover {
  height: 297mm;
  width: 210mm;
  padding: 48px 50px;
  color: #fff;
  background: #101a36;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  page-break-after: always;
}
.cover:after { content: ""; position: absolute; width: 420px; height: 420px; right: -130px; top: 160px; border: 1px solid rgba(116,139,255,.25); border-radius: 50%; box-shadow: 0 0 0 35px rgba(116,139,255,.04), 0 0 0 70px rgba(116,139,255,.03); }
.brand { color: #9eabff; font-size: 11px; font-weight: bold; letter-spacing: 2px; text-transform: uppercase; position: relative; z-index: 1; }
.cover-main { flex: 1; display: flex; flex-direction: column; justify-content: center; position: relative; z-index: 1; }
.cover h1 { margin: 0 0 14px; max-width: 520px; font-size: 42px; line-height: 1.05; letter-spacing: -1.5px; }
.cover .subtitle { color: #b7c0dc; font-size: 14px; max-width: 480px; }
.cover-meta {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  margin-top: 40px;
  padding-top: 18px;
  border-top: 1px solid rgba(255,255,255,.18);
  color: #b7c0dc;
}
.cover-meta b { display: block; margin-bottom: 3px; color: #fff; font-size: 12px; }
.cover-meta span { font-size: 10px; }
/* ---- end cover page ---- */
 
.topline { display: flex; justify-content: space-between; align-items: flex-start; padding-bottom: 18px; border-bottom: 3px solid #4f6df5; }
.eyebrow { color: #4f6df5; font-weight: bold; letter-spacing: 1.4px; text-transform: uppercase; font-size: 8px; }
h2 { margin: 24px 0 12px; font-size: 19px; letter-spacing: -.3px; }
h2 span { display: inline-block; width: 27px; height: 27px; margin-right: 8px; border-radius: 7px; color: #fff; background: #4f6df5; text-align: center; font-size: 10px; line-height: 27px; vertical-align: 2px; }
h3 { margin: 0 0 10px; color: #52617b; font-size: 9px; letter-spacing: 1px; text-transform: uppercase; }
.summary { margin: 20px 0; padding: 17px 20px; border-left: 4px solid #4f6df5; border-radius: 0 9px 9px 0; background: #edf0ff; }
.summary p { margin: 5px 0 0; color: #33405c; font-size: 12px; }
.cards { display: flex; gap: 10px; }
.card { flex: 1; padding: 13px 14px; border: 1px solid #e0e5ef; border-radius: 9px; background: #fff; }
.card-label { color: #7b879d; font-size: 8px; font-weight: bold; letter-spacing: 1px; text-transform: uppercase; }
.card-value { margin-top: 7px; color: #17233d; font-size: 20px; font-weight: bold; }
.card-detail { margin-top: 4px; color: #18a982; font-size: 9px; }
.grid { display: flex; gap: 12px; margin-top: 12px; }
.panel { flex: 1; padding: 14px; border: 1px solid #e0e5ef; border-radius: 9px; background: #fff; }
.chart-row { display: flex; align-items: center; gap: 8px; margin: 12px 0; }
.chart-label { width: 44px; color: #7b879d; font-size: 9px; }
.chart-track { height: 10px; flex: 1; overflow: hidden; border-radius: 8px; background: #edf0f5; }
.chart-bar { height: 100%; border-radius: 8px; }
.chart-value { width: 62px; text-align: right; font-size: 9px; font-weight: bold; }
.before-bar { background: #8995aa; }
.after-bar { background: #18a982; }
table { width: 100%; border-collapse: collapse; }
th { padding: 7px 5px; border-bottom: 1px solid #dfe4ed; color: #7b879d; font-size: 8px; letter-spacing: .7px; text-align: left; text-transform: uppercase; }
td { padding: 8px 5px; border-bottom: 1px solid #edf0f5; }
td small { display: block; color: #8994a8; font-size: 8px; }
.rank { width: 27px; color: #4f6df5; font-weight: bold; }
.amount { color: #ba7815; font-weight: bold; text-align: right; }
.amount span { margin-left: 2px; color: #8994a8; font-size: 8px; font-weight: normal; }
.success { color: #16866f; font-weight: bold; }
.empty { padding: 8px 0; color: #8994a8; }
.score-card { text-align: center; }
.score-ring { position: relative; width: 112px; height: 112px; margin: 0 auto; }
.score-ring svg { display: block; }
.score-number { position: absolute; top: 0; left: 0; width: 112px; height: 112px; display: flex; align-items: center; justify-content: center; color: #17233d; font-size: 25px; font-weight: bold; }
.score-caption { margin-top: 10px; color: #8994a8; font-size: 9px; }
.issue { display: flex; gap: 8px; margin: 6px 0; padding: 8px; border-radius: 6px; background: #f7f8fb; }
.issue-icon { display: inline-block; width: 15px; height: 15px; border-radius: 50%; color: #fff; text-align: center; font-size: 10px; line-height: 15px; }
.issue b { display: block; font-size: 9px; }
.issue small { color: #8994a8; font-size: 8px; }
.issue.negative .issue-icon { background: #d04a4a; }
.issue.positive .issue-icon { background: #18a982; }
.pill { display: inline-block; margin: 2px 3px 2px 0; padding: 5px 8px; border-radius: 12px; font-size: 8px; }
.pill.blue { color: #3153bf; background: #e7edff; }
.pill.amber { color: #9d6c17; background: #fff1d4; }
ul { margin: 4px 0; padding-left: 17px; }
li { margin: 5px 0; }
.footer { margin-top: 22px; padding-top: 8px; border-top: 1px solid #dfe4ed; color: #98a2b4; font-size: 8px; }
</style>
</head>
<body>
<section class="cover">
  <div class="brand">PodPilot · Cluster intelligence</div>
  <div class="cover-main">
    <h1>Impact<br>Report</h1>
    <div class="subtitle">A before-and-after view of cost, security, and reliability.</div>
  </div>
  <div class="cover-meta"><div><b>@@CLUSTER@@</b><span>@@NODES@@ nodes</span></div><div><b>@@FROM@@ → @@TO@@</b><span>@@FROM_DATE@@ → @@TO_DATE@@</span></div></div>
</section>
<section class="page">
  <div class="topline"><div><div class="eyebrow">Impact report</div><h2 style="margin-top:5px">Executive overview</h2></div><div style="text-align:right;color:#7b879d;font-size:9px">Generated<br>@@GENERATED@@</div></div>
  <div class="summary"><div class="eyebrow">Executive summary</div><p>@@SUMMARY@@</p></div>
  <h2><span>01</span>Cost impact</h2>
  <div class="cards"><div class="card"><div class="card-label">Monthly cost</div><div class="card-value">@@COST_AFTER@@</div><div class="card-detail">@@COST_DELTA@@ vs baseline</div></div><div class="card"><div class="card-label">Monthly waste</div><div class="card-value">@@WASTE_AFTER@@</div><div class="card-detail">@@WASTE_DELTA@@ vs baseline</div></div><div class="card"><div class="card-label">Proof of impact</div><div class="card-value">@@FIXED_COUNT@@</div><div class="card-detail">workloads improved or removed</div></div></div>
  <div class="grid"><div class="panel"><h3>Waste trend</h3><div class="chart-row"><span class="chart-label">Before</span><div class="chart-track"><div class="chart-bar before-bar" style="width:@@BEFORE_WIDTH@@%"></div></div><span class="chart-value">@@WASTE_BEFORE@@</span></div><div class="chart-row"><span class="chart-label">After</span><div class="chart-track"><div class="chart-bar after-bar" style="width:@@AFTER_WIDTH@@%"></div></div><span class="chart-value">@@WASTE_AFTER@@</span></div><p class="empty">Lower is better · monthly waste</p></div><div class="panel"><h3>Top offenders at target</h3><table><thead><tr><th>#</th><th>Workload</th><th>Waste</th></tr></thead><tbody>@@OFFENDERS@@</tbody></table></div></div>
  <div class="panel" style="margin-top:12px"><h3>Fixed since baseline</h3><table><thead><tr><th>Workload</th><th>Before</th><th>After</th><th>Saved / month</th></tr></thead><tbody>@@FIXED@@</tbody></table></div>
  <div class="footer">PodPilot · Cost analysis from selected saved snapshots</div>
</section>
<section class="page">
  <div class="eyebrow">Security & reliability</div><h2 style="margin-top:5px">Posture and operational movement</h2>
  <h2><span>02</span>Security posture</h2>
  <div class="grid"><div class="panel"><h3>Before → after</h3><div class="cards"><div class="card"><div class="card-label">Critical</div><div class="card-value">@@CRIT_BEFORE@@ → @@CRIT_AFTER@@</div></div><div class="card"><div class="card-label">Warnings</div><div class="card-value">@@WARN_BEFORE@@ → @@WARN_AFTER@@</div></div></div><div class="issue positive" style="margin-top:12px"><span class="issue-icon">✓</span><div><b>Current security score: @@SCORE@@ / 100</b><small>Baseline score: @@OLD_SCORE@@ / 100</small></div></div></div><div class="panel score-card"><h3>Security score</h3><div class="score-ring"><svg width="112" height="112" viewBox="0 0 112 112"><circle cx="56" cy="56" r="42" fill="none" stroke="#e9edf4" stroke-width="10"/><circle cx="56" cy="56" r="42" fill="none" stroke="@@SCORE_COLOR@@" stroke-width="10" stroke-linecap="round" stroke-dasharray="@@SCORE_DASH@@ 263.89" transform="rotate(-90 56 56)"/></svg><div class="score-number" style="color:@@SCORE_COLOR@@">@@SCORE@@</div></div><div class="score-caption">out of 100</div></div></div>
  <div class="grid"><div class="panel"><h3>New issues</h3>@@NEW_ISSUES@@</div><div class="panel"><h3>Resolved issues</h3>@@RESOLVED_ISSUES@@</div></div>
  <h2><span>03</span>Drift & reliability</h2>
  <div class="cards"><div class="card"><div class="card-label">Restarts</div><div class="card-value">@@RESTART_BEFORE@@ → @@RESTART_AFTER@@</div></div><div class="card"><div class="card-label">Desired replicas</div><div class="card-value">@@REPLICA_BEFORE@@ → @@REPLICA_AFTER@@</div></div><div class="card"><div class="card-label">New pods</div><div class="card-value">@@NEW_COUNT@@</div></div><div class="card"><div class="card-label">Removed pods</div><div class="card-value">@@REMOVED_COUNT@@</div></div></div>
  <div class="grid"><div class="panel"><h3>New pods</h3>@@NEW_PODS@@</div><div class="panel"><h3>Removed pods</h3>@@REMOVED_PODS@@</div></div>
  <div class="panel" style="margin-top:12px"><h3>Snapshot diff · @@CHANGE_COUNT@@ changes</h3><ul>@@CHANGES@@</ul></div>
  <div class="footer">PodPilot · Security checks and drift detection from selected saved snapshots</div>
</section>
</body></html>"""
    values = {
        "@@CLUSTER@@": escape(report["to_snapshot"]["cluster_name"]), "@@NODES@@": str(report["to_snapshot"]["node_count"]),
        "@@FROM@@": escape(report["from_snapshot"]["name"]), "@@TO@@": escape(report["to_snapshot"]["name"]),
        "@@FROM_DATE@@": escape(str(report["from_snapshot"].get("captured_at", "—"))), "@@TO_DATE@@": escape(str(report["to_snapshot"].get("captured_at", "—"))),
        "@@GENERATED@@": escape(str(report.get("generated_at", ""))), "@@SUMMARY@@": escape(report["executive_summary"]),
        "@@COST_AFTER@@": money(cost["total"]["after"]), "@@COST_DELTA@@": signed(cost["total"]["change"]), "@@WASTE_AFTER@@": money(cost["waste"]["after"]),
        "@@WASTE_DELTA@@": signed(cost["waste"]["change"]), "@@FIXED_COUNT@@": str(len(cost["fixed"])), "@@WASTE_BEFORE@@": money(cost["waste"]["before"]),
        "@@BEFORE_WIDTH@@": str(before_width), "@@AFTER_WIDTH@@": str(after_width), "@@OFFENDERS@@": offenders, "@@FIXED@@": fixed,
        "@@CRIT_BEFORE@@": str(security["before"]["critical"]), "@@CRIT_AFTER@@": str(security["after"]["critical"]), "@@WARN_BEFORE@@": str(security["before"]["warning"]), "@@WARN_AFTER@@": str(security["after"]["warning"]),
        "@@SCORE@@": str(score), "@@OLD_SCORE@@": str(security["before"]["score"]), "@@SCORE_COLOR@@": score_color, "@@SCORE_DASH@@": str(263.89 * score / 100),
        "@@NEW_ISSUES@@": issue_list(security["new_issues"], "No new issues since baseline."), "@@RESOLVED_ISSUES@@": issue_list(security["resolved_issues"], "No issues resolved.", True),
        "@@RESTART_BEFORE@@": str(drift["restart_total"]["before"]), "@@RESTART_AFTER@@": str(drift["restart_total"]["after"]), "@@REPLICA_BEFORE@@": str(drift["replica_totals"]["before"]), "@@REPLICA_AFTER@@": str(drift["replica_totals"]["after"]),
        "@@NEW_COUNT@@": str(len(drift["new_pods"])), "@@REMOVED_COUNT@@": str(len(drift["removed_pods"])), "@@NEW_PODS@@": pills(drift["new_pods"], "blue"), "@@REMOVED_PODS@@": pills(drift["removed_pods"], "amber"),
        "@@CHANGE_COUNT@@": str(len(drift["changes"])), "@@CHANGES@@": changes,
    }
    for token, value in values.items(): html = html.replace(token, value)
    return html