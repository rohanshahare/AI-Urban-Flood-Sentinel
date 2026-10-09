// alerts.js

// Alert banner. Only a triggered alert with a real level is styled as a risk;
// inconclusive and error outcomes use neutral styling, never green.
function renderAlert(result) {
    const box = document.getElementById("alert-box");
    box.replaceChildren();
    if (result.processing_status === "error") {
        box.append(el("div", "alert alert-error", `Error: ${result.error.message}`));
        return;
    }
    const alert = result.alert;
    const kind = result.processing_status === "inconclusive" ? "alert-neutral" : alert.triggered ? "alert-triggered" : "alert-info";
    const banner = el("div", `alert ${kind}`);
    banner.append(el("strong", "", alert.title || ""), el("div", "", alert.message || ""), el("div", "", alert.recommendation || ""));
    box.append(banner);
}
