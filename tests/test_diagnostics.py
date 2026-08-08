from quayshell.diagnostics import DiagnosticItem, DiagnosticReport


def test_diagnostic_report_fails_only_required_errors():
    report = DiagnosticReport(
        (
            DiagnosticItem("platform", "ok", "Linux", required=True),
            DiagnosticItem("compositor", "warning", "generic"),
        )
    )

    assert report.supported is True
    assert "[warning] compositor: generic" in report.render()


def test_required_diagnostic_error_fails_report():
    report = DiagnosticReport(
        (DiagnosticItem("Wayland", "error", "not set", required=True),)
    )

    assert report.supported is False
