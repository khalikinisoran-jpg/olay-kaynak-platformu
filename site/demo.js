/* TANUQ interactive walkthrough — plays site/demo_fixtures.json only.
   No API, no shell, no file writes, no live governance. */
(function () {
  "use strict";

  var root = document.getElementById("demo-root");
  if (!root) return;

  /* Real recorded-run summary shipped in index.html. It stays visible in
     every failure mode so the public page never shows an error box. */
  var staticHTML = root.innerHTML;

  var FIXTURE_URL = root.getAttribute("data-fixture") || "demo_fixtures.json";
  var ORDER = [
    "propose",
    "risk",
    "policy",
    "approval_required",
    "approve",
    "execute",
    "verify",
    "evidence"
  ];
  var LABELS = {
    propose: "PROPOSAL",
    risk: "RISK",
    policy: "POLICY",
    approval_required: "APPROVAL REQUIRED",
    approve: "APPROVE",
    execute: "EXECUTE",
    verify: "VERIFY",
    evidence: "EVIDENCE"
  };

  var fx = null;
  var byId = {};
  var idx = 0;
  var approved = false;

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function step(id) {
    return byId[id];
  }

  function badge(text, cls) {
    return '<span class="dw-badge ' + (cls || "") + '">' + esc(text) + "</span>";
  }

  function diffBlock(oldC, newC) {
    return (
      '<pre class="dw-diff"><span class="dw-diff-del">- ' +
      esc(oldC) +
      '</span>\n<span class="dw-diff-add">+ ' +
      esc(newC) +
      "</span></pre>"
    );
  }

  function detailFor(id) {
    var s = step(id);
    if (!s) return "";
    var d = s.data || {};
    switch (id) {
      case "propose":
        return (
          '<div class="dw-meta">' +
          "<div><span class=\"dw-k\">path</span><code>" +
          esc(d.path_display) +
          "</code></div>" +
          "<div><span class=\"dw-k\">action</span><code>" +
          esc(d.action) +
          "</code></div>" +
          "<div><span class=\"dw-k\">reason</span><code>" +
          esc(d.reason) +
          "</code></div>" +
          "<div><span class=\"dw-k\">fingerprint</span><code class=\"dw-fp\">" +
          esc(d.fingerprint_short) +
          "…</code></div>" +
          "</div>" +
          diffBlock(d.old_preview, d.new_preview) +
          '<p class="dw-msg">' + esc(d.message) + "</p>"
        );
      case "risk":
        return (
          '<div class="dw-meta">' +
          "<div><span class=\"dw-k\">risk</span>" +
          badge(d.risk, "dw-badge-high") +
          "</div>" +
          "<div><span class=\"dw-k\">allowed</span><code>" +
          esc(String(d.allowed)) +
          "</code></div>" +
          "<div><span class=\"dw-k\">approval_required</span><code>" +
          esc(String(d.approval_required)) +
          "</code></div>" +
          "</div>" +
          '<p class="dw-msg">' + esc(d.reason) + "</p>" +
          '<ul class="dw-signals">' +
          (d.signals || [])
            .map(function (sig) {
              return (
                "<li><code>" +
                esc(sig[0]) +
                "</code> · <code>" +
                esc(sig[1]) +
                "</code></li>"
              );
            })
            .join("") +
          "</ul>"
        );
      case "policy":
        return (
          '<div class="dw-meta">' +
          "<div><span class=\"dw-k\">requires_human</span><code>" +
          esc(String(d.requires_human)) +
          "</code></div>" +
          "<div><span class=\"dw-k\">single_use</span><code>" +
          esc(String(d.single_use)) +
          "</code></div>" +
          "<div><span class=\"dw-k\">ttl</span><code>" +
          esc(String(d.ttl_seconds)) +
          "s</code></div>" +
          "<div><span class=\"dw-k\">fingerprint_bound</span><code>" +
          esc(String(d.fingerprint_bound)) +
          "</code></div>" +
          "</div>" +
          '<p class="dw-msg">' + esc(d.what_this_authorizes) + "</p>"
        );
      case "approval_required":
        return (
          '<div class="dw-wait">' +
          badge("HIGH", "dw-badge-high") +
          badge("APPROVAL REQUIRED", "dw-badge-warn") +
          '<p class="dw-msg">Waiting for a single-use, fingerprint-bound human approval. Nothing is applied until approve.</p>' +
          '<p class="dw-meta-line"><span class="dw-k\">fingerprint</span><code class="dw-fp">' +
          esc(d.fingerprint_short) +
          "…</code></p>" +
          "</div>"
        );
      case "approve":
        if (!approved) {
          return (
            '<div class="dw-wait"><p class="dw-msg">Not approved yet. Use <strong>APPROVE CHANGE</strong> to continue (recorded run).</p></div>'
          );
        }
        return (
          '<div class="dw-meta">' +
          "<div><span class=\"dw-k\">approval_id</span><code>" +
          esc(d.approval_id) +
          "</code></div>" +
          "<div><span class=\"dw-k\">authorizer</span><code>" +
          esc(d.authorizer) +
          "</code></div>" +
          "<div><span class=\"dw-k\">risk</span>" +
          badge(d.risk, "dw-badge-high") +
          "</div>" +
          "<div><span class=\"dw-k\">binding</span><code>single-use · " +
          esc(d.ttl_seconds) +
          "s</code></div>" +
          "</div>" +
          '<pre class="dw-term-line">' + esc(d.stdout) + "</pre>"
        );
      case "execute":
        return (
          '<ol class="dw-phases">' +
          '<li class="dw-phase done"><span class="dw-phase-name">AUTHORIZED</span><span class="dw-phase-hint">approval consumed</span></li>' +
          '<li class="dw-phase done"><span class="dw-phase-name">EXECUTING</span><span class="dw-phase-hint">atomic apply</span></li>' +
          '<li class="dw-phase done"><span class="dw-phase-name">VERIFIED</span><span class="dw-phase-hint">apply success</span></li>' +
          "</ol>" +
          '<div class="dw-meta">' +
          "<div><span class=\"dw-k\">apply_success</span><code>" +
          esc(String(d.apply_success)) +
          "</code></div>" +
          "<div><span class=\"dw-k\">intent</span><code>" +
          esc(d.intent_id) +
          "</code></div>" +
          "</div>" +
          diffBlock(d.old_content, d.new_content) +
          '<pre class="dw-term-line">' + esc(d.stdout) + "</pre>"
        );
      case "verify":
        return (
          '<div class="dw-final-ok">✓ VERIFIED</div>' +
          '<div class="dw-meta">' +
          "<div><span class=\"dw-k\">terminal_state</span><code>" +
          esc(d.terminal_state) +
          "</code></div>" +
          "<div><span class=\"dw-k\">apply_success</span><code>" +
          esc(String(d.apply_success)) +
          "</code></div>" +
          "<div><span class=\"dw-k\">verification_passed</span><code>" +
          esc(String(d.verification_passed)) +
          "</code></div>" +
          "<div><span class=\"dw-k\">profile</span><code>" +
          esc((d.verification_profile || {}).profile || "") +
          " · " +
          esc((d.verification_profile || {}).mode || "") +
          "</code></div>" +
          "</div>" +
          '<pre class="dw-term-line">' + esc(d.stdout) + "</pre>"
        );
      case "evidence":
        return (
          '<div class="dw-ev-grid">' +
          '<div class="dw-ev">' + badge("CHAIN " + d.chain, "dw-badge-ok") + "<span>events " +
          esc(String(d.events_in_chain)) +
          " · seq " +
          esc(d.sequence) +
          "</span></div>" +
          '<div class="dw-ev">' + badge("ANCHOR " + d.anchor, "dw-badge-ok") + "</div>" +
          '<div class="dw-ev">' + badge("LEDGER " + d.approval_ledger, "dw-badge-ok") + "</div>" +
          "</div>" +
          '<pre class="dw-term-line">' + esc(d.stdout) + "</pre>"
        );
      default:
        return "";
    }
  }

  function isApproveGate() {
    if (approved) return false;
    var id = ORDER[idx];
    return id === "approval_required" || id === "approve";
  }

  function isLast() {
    return idx >= ORDER.length - 1;
  }

  function render() {
    var sc = fx.scenario || {};
    var src = fx.source || {};
    var fpFull = (fx.integrity || {}).fingerprint || "";
    var currentId = ORDER[idx];
    var html = "";

    html += '<div class="dw-head">';
    html += '<div class="dw-title-row">';
    html += '<h3 class="dw-title">AI wants to change <code>' + esc(sc.path_display) + "</code></h3>";
    html += badge(sc.risk + " RISK", "dw-badge-high");
    html += badge("APPROVAL REQUIRED", "dw-badge-warn");
    html += "</div>";
    html +=
      '<p class="dw-source">' +
      esc(src.label || "Recorded from a real TANUQ local run") +
      ' · <span class="dw-soft">recorded playback — no live API, no shell, no file writes</span></p>';
    html += "</div>";

    html += '<ol class="dw-progress" aria-label="Walkthrough steps">';
    ORDER.forEach(function (id, i) {
      var cls = i < idx ? "done" : i === idx ? "current" : "";
      html +=
        '<li class="dw-progress-item ' +
        cls +
        '"><span class="dw-progress-n">' +
        (i + 1) +
        "</span><span class=\"dw-progress-l\">" +
        esc(LABELS[id]) +
        "</span></li>";
    });
    html += "</ol>";

    html += '<div class="dw-panel">';
    html +=
      '<div class="dw-panel-head"><span class="dw-step-label">STEP ' +
      (idx + 1) +
      " / " +
      ORDER.length +
      " · " +
      esc(LABELS[currentId]) +
      "</span>" +
      '<span class="dw-state">' +
      esc(step(currentId).state) +
      "</span></div>";
    html += '<div class="dw-panel-body">' + detailFor(currentId) + "</div>";
    html += "</div>";

    html += '<div class="dw-meta-bar">';
    html +=
      '<span class="dw-k">fingerprint</span><code class="dw-fp" title="' +
      esc(fpFull) +
      '">' +
      esc(fpFull.slice(0, 12)) +
      "…</code>";
    if (fx.integrity && fx.integrity.approval) {
      html +=
        '<span class="dw-k">approval</span><code>' +
        esc(fx.integrity.approval) +
        "</code>";
    }
    html += "</div>";

    html += '<div class="dw-actions">';
    if (isApproveGate()) {
      html +=
        '<button type="button" class="btn btn-primary dw-btn" data-dw="approve">APPROVE CHANGE</button>';
      if (ORDER[idx] === "approval_required") {
        html +=
          '<button type="button" class="btn btn-secondary dw-btn" data-dw="next">NEXT STEP</button>';
      }
    } else if (isLast()) {
      html += '<button type="button" class="btn btn-secondary dw-btn" data-dw="reset">START OVER</button>';
      html +=
        '<a class="btn btn-primary dw-btn" href="#try">RUN IT LOCALLY</a>';
    } else {
      html +=
        '<button type="button" class="btn btn-primary dw-btn" data-dw="next">NEXT STEP</button>';
    }
    html += "</div>";

    if (approved && idx >= 5) {
      html +=
        '<p class="dw-ok-line">✓ VERIFIED · chain VALID · anchor ACTIVE · ledger VALID</p>';
    }

    root.innerHTML = html;
  }

  function onAction(ev) {
    var btn = ev.target.closest("[data-dw]");
    if (!btn) return;
    var act = btn.getAttribute("data-dw");
    if (act === "approve") {
      approved = true;
      idx = ORDER.indexOf("approve");
      render();
      return;
    }
    if (act === "next") {
      if (isApproveGate()) {
        /* stay; require approve or allow skip forward for browsing */
        idx = Math.min(idx + 1, ORDER.length - 1);
        if (ORDER[idx] === "approve" && !approved) {
          /* still show approve step but gated content until approved */
        }
        render();
        return;
      }
      if (isLast()) return;
      idx += 1;
      render();
      return;
    }
    if (act === "reset") {
      idx = 0;
      approved = false;
      render();
    }
  }

  function restoreStatic(reason) {
    root.innerHTML = staticHTML;
    if (window.console && console.warn) {
      console.warn("TANUQ walkthrough: static recorded summary kept visible (" + reason + ")");
    }
  }

  function fail(reason) {
    /* Never render an error state into the public page. */
    restoreStatic(reason);
  }

  function boot(data) {
    fx = data;
    byId = {};
    (fx.steps || []).forEach(function (s) {
      byId[s.id] = s;
    });
    var missing = ORDER.filter(function (id) {
      return !byId[id];
    });
    if (missing.length) {
      fail("fixture missing steps: " + missing.join(", "));
      return;
    }
    if ((fx.source || {}).type !== "recorded_real_run") {
      fail("fixture source is not recorded_real_run");
      return;
    }
    root.addEventListener("click", onAction);
    render();
  }

  fetch(FIXTURE_URL, { cache: "no-store" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(boot)
    .catch(function (e) {
      restoreStatic((e && e.message) || "fixture fetch failed");
    });
})();
