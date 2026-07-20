from fastapi import Response
from report import list_snapshots, build_impact_report, render_report_html
from weasyprint import HTML


@app.get("/report/snapshots")
def report_snapshots():
    """Powers the from/to dropdowns in the frontend."""
    return list_snapshots()


@app.get("/report/impact")
def report_impact(from_id: str, to_id: str):
    """JSON version -- used to render the in-app report view."""
    return build_impact_report(from_id, to_id)


@app.get("/report/pdf")
def report_pdf(from_id: str, to_id: str):
    """Downloadable PDF version -- what you'd actually share with Amjad bhai."""
    report = build_impact_report(from_id, to_id)
    html = render_report_html(report)
    pdf_bytes = HTML(string=html).write_pdf()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=podpilot-impact-report.pdf"},
    )