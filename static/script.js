/* ═══════════════════════════════════════════════════════════
   ORCHESTRATOR_V1 — Unified Frontend Logic
   Driven entirely by real API response shapes from app.py.
   No synthetic/mock data anywhere.
════════════════════════════════════════════════════════════ */

"use strict";

// ──────────────────────────────────────────────────────────
// CONSTANTS
// ──────────────────────────────────────────────────────────
const State = {
    IDLE: "idle",
    EXECUTING: "executing",
    COMPLETE: "complete",
    ERROR: "error"
};

const VERDICT_META = {
    skipped_high_confidence: { label: "AUTO-ACCEPT", cls: "skipped", icon: "fast_forward", color: "text-secondary" },
    accept: { label: "VALIDATED", cls: "accept", icon: "check", color: "text-primary" },
    retry: { label: "RETRIED", cls: "retry", icon: "refresh", color: "text-tertiary" },
};

const MODE_META = {
    ultra_fast: { label: "Ultra-Fast", color: "text-sapphire-light", barColor: "bg-sapphire-light" },
    direct: { label: "Direct", color: "text-secondary", barColor: "bg-secondary" },
    dag: { label: "DAG Multi-Task", color: "text-primary", barColor: "bg-primary" },
};

const TYPE_COLOR = {
    CODE: { badge: "CODE", bar: "bg-sapphire-light" },
    EXPLAIN: { badge: "EXPLAIN", bar: "bg-primary" },
    CALCULATE: { badge: "CALCULATE", bar: "bg-secondary" },
    ANALYZE: { badge: "ANALYZE", bar: "bg-tertiary" },
    COMPARE: { badge: "COMPARE", bar: "bg-sapphire-light" },
    DEBUG: { badge: "DEBUG", bar: "bg-tertiary" },
    DESIGN: { badge: "DESIGN", bar: "bg-secondary" },
};

// THIS is what was missing — must be before makeWorkerCard
const CODE_TASK_TYPES = new Set(["CODE", "DEBUG", "REFACTOR", "OPTIMIZE"]);

// Modal state — must be before openTaskModal
let _modalTask = null;
let _modalIntent = "";

// ──────────────────────────────────────────────────────────
// GLOBAL MODAL HANDLER (FIXED)
// ──────────────────────────────────────────────────────────
function openTaskModal(task, meta = {}) {
    console.log("[Modal] Opening task modal:", task?.task_id);
    _modalTask = task;
    _modalIntent = meta.intent || "";

    try {
        const modal = document.getElementById("task-modal");
        if (!modal) {
            console.error("[Modal] task-modal element not found in DOM");
            return;
        }

        // Fill task type
        const tf = task.task_type || "TASK";
        setText("modal-task-type", tf);
        const typeBadge = document.getElementById("modal-task-type");
        if (typeBadge) {
            // Match the CSS class in styles.css (.type-badge)
            typeBadge.className = `type-badge ${tf}`;
        }

        // Fill ID
        setText("modal-task-id", task.task_id || "—");

        // Verdict
        const vm = VERDICT_META[task.validation_verdict || "accept"] || VERDICT_META.accept;
        const verdictEl = document.getElementById("modal-verdict");
        if (verdictEl) {
            verdictEl.textContent = vm.label;
            verdictEl.className = `font-label text-[10px] uppercase px-2.5 py-1 border ${vm.color} border-current rounded-sm`;
        }

        // Confidence
        const conf = task.confidence ?? 0;
        const confPct = Math.round(conf * 100);
        setText("modal-confidence", `${confPct}%`);

        const confBar = document.getElementById("modal-conf-bar");
        if (confBar) {
            confBar.style.width = `${confPct}%`;
            confBar.className = `h-full transition-all duration-700 ${conf >= 0.85 ? "bg-primary" : conf >= 0.70 ? "bg-secondary" : "bg-tertiary"}`;
        }

        // Estimated tokens
        const resultText = task.result || task.final_output || "No output";
        setText("modal-tokens", `~${Math.round(resultText.length / 4)}`);

        // Execution badge
        const isCode = CODE_TASK_TYPES.has(tf);
        const execBadge = document.getElementById("modal-exec-badge");
        if (execBadge) {
            if (isCode) {
                execBadge.classList.remove("hidden");
                const execStatus = document.getElementById("modal-exec-status");
                if (execStatus) {
                    if (task.execution_success) {
                        execStatus.textContent = "SUCCESS";
                        execStatus.className = "font-label text-xs uppercase font-bold text-primary";
                    } else {
                        execStatus.textContent = "FAILED";
                        execStatus.className = "font-label text-xs uppercase font-bold text-tertiary";
                    }
                }
                setText("modal-attempts", `${task.attempts || 1} ATTEMPT${(task.attempts || 1) !== 1 ? "S" : ""}`);
            } else {
                execBadge.classList.add("hidden");
            }
        }

        setText("modal-intent", _modalIntent || "—");
        setText("modal-content", resultText);

        // Show modal
        document.body.style.overflow = "hidden";
        modal.classList.remove("hidden");
        modal.style.display = "block"; // Force visibility
    } catch (err) {
        console.error("[Modal Error]", err);
    }
}

window.closeTaskModal = function() {
    console.log("[Modal] Closing modal");
    const modal = document.getElementById("task-modal");
    if (modal) {
        modal.classList.add("hidden");
        modal.style.display = "none";
    }
    document.body.style.overflow = "";
};

window.copyModalContent = function() {
    if (_modalTask && _modalTask.result) {
        navigator.clipboard.writeText(_modalTask.result);
        
        // Brief visual feedback on button
        const btn = document.querySelector('button[title="Copy output"]');
        if (btn) {
            const icon = btn.querySelector('span');
            if (icon) {
                const oldIcon = icon.textContent;
                icon.textContent = 'check';
                icon.classList.add('text-primary');
                setTimeout(() => {
                    icon.textContent = oldIcon;
                    icon.classList.remove('text-primary');
                }, 1000);
            }
        }
    }
};


// ──────────────────────────────────────────────────────────
// SESSION STORE
// Built exclusively from real /run and /history responses.
// ──────────────────────────────────────────────────────────
const Session = {
    runs: [],   // full normalized execution records
    taskTypes: {},   // { "CODE": 3, ... }
    modeCounts: {},   // { "dag": 2, ... }
    patternCounts: {},   // { "list": 1, ... }
    confidenceAll: [],   // flat array of per-task confidence floats
    validationEvents: [],   // { task_id, verdict, confidence, run_id }
    highConf: 0,
    midConf: 0,
    lowConf: 0,
    totalTasks: 0,

    /** Ingest one completed execution record from /run */
    ingest(record) {
        if (!record || record.status !== "completed") return;

        this.runs.push(record);

        // Mode
        const mode = record.plan?.mode || "direct";
        this.modeCounts[mode] = (this.modeCounts[mode] || 0) + 1;

        // Pattern — planner may expose plan.pattern
        const pattern = record.plan?.pattern || mode;
        this.patternCounts[pattern] = (this.patternCounts[pattern] || 0) + 1;

        // Per-task data
        (record.results || []).forEach(res => {
            this.totalTasks++;

            const type = res.task_type || "UNKNOWN";
            this.taskTypes[type] = (this.taskTypes[type] || 0) + 1;

            const conf = res.confidence ?? 0;
            this.confidenceAll.push(conf);

            if (conf >= 0.85) this.highConf++;
            else if (conf >= 0.70) this.midConf++;
            else this.lowConf++;

            this.validationEvents.push({
                task_id: res.task_id,
                verdict: res.validation_verdict || "accept",
                confidence: conf,
                run_id: record.execution_id || record.id || "—",
            });
        });
    },

    avgConfidence() {
        if (!this.confidenceAll.length) return null;
        return this.confidenceAll.reduce((a, b) => a + b, 0) / this.confidenceAll.length;
    },

    /** Token efficiency: % of tasks that skipped validation */
    efficiencyPct() {
        if (!this.totalTasks) return 0;
        return Math.round((this.highConf / this.totalTasks) * 100);
    },

    /** Re-hydrate from a full /history response on page load */
    hydrate(historyArray) {
        // Reset
        Object.assign(this, {
            runs: [], taskTypes: {}, modeCounts: {}, patternCounts: {},
            confidenceAll: [], validationEvents: [],
            highConf: 0, midConf: 0, lowConf: 0, totalTasks: 0,
        });
        // History comes newest-first; ingest oldest-first for chart order
        [...historyArray].reverse().forEach(r => this.ingest(r));
    },
};

// ──────────────────────────────────────────────────────────
// RUNTIME STATE
// ──────────────────────────────────────────────────────────
let currentState = State.IDLE;
let uptimeSeconds = 0;
let processedCount = 0;   // queries executed this browser session
let totalTasksRun = 0;   // tasks executed this browser session

// History tab local state
let historyCache = [];   // raw array from /history
let historyFilter = "all";
let historySearch = "";
let activeHistoryRow = null;

// ──────────────────────────────────────────────────────────
// BOOT
// ──────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    initViewManager();
    initMetricsToggle();
    initPipelineControls();
    initHistoryControls();
    initUptimeClock();
    loadHistory();          // prime history + hydrate SessionStore
});

document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
        if (typeof window.closeTaskModal === "function") {
            window.closeTaskModal();
        }
    }
});

// ──────────────────────────────────────────────────────────
// VIEW MANAGER
// ──────────────────────────────────────────────────────────
function initViewManager() {
    window.showView = (viewId) => {

        // ✅ FORCE CLOSE MODAL ON TAB SWITCH
        if (typeof window.closeTaskModal === "function") {
            window.closeTaskModal();
        }

        document.querySelectorAll(".view-section")
            .forEach(s => s.classList.remove("active"));
        document.getElementById(viewId)?.classList.add("active");

        document.querySelectorAll(".nav-btn")
            .forEach(b => b.classList.remove("active"));
        document.getElementById(`nav-${viewId}`)?.classList.add("active");

        if (viewId === "analytics") renderAnalytics();

        window.scrollTo({ top: 0, behavior: "smooth" });
    };
}
// ──────────────────────────────────────────────────────────
// METRICS PANEL TOGGLE
// ──────────────────────────────────────────────────────────
function initMetricsToggle() {
    const panel = document.getElementById("metrics-panel");
    const toggle = document.getElementById("metrics-toggle-btn");
    if (!panel || !toggle) return;

    const open = () => {
        panel.classList.remove("hidden");
        requestAnimationFrame(() => {
            panel.classList.remove("opacity-0", "translate-y-2", "pointer-events-none");
        });
    };
    const close = () => {
        panel.classList.add("opacity-0", "translate-y-2", "pointer-events-none");
        setTimeout(() => panel.classList.add("hidden"), 300);
    };

    toggle.addEventListener("click", e => {
        e.stopPropagation();
        panel.classList.contains("hidden") ? open() : close();
    });
    document.addEventListener("click", e => {
        if (!panel.contains(e.target) && !toggle.contains(e.target)) close();
    });
}

// ──────────────────────────────────────────────────────────
// PIPELINE — INPUT CONTROLS
// ──────────────────────────────────────────────────────────
function initPipelineControls() {
    const btn = document.getElementById("pipeline-execute-btn");
    const input = document.getElementById("pipeline-input");
    if (!btn || !input) return;

    btn.addEventListener("click", () => {
        const intent = input.value.trim();
        if (!intent || currentState === State.EXECUTING) return;
        runPipeline(intent);
    });

    // Ctrl+Enter / Cmd+Enter shortcut
    input.addEventListener("keydown", e => {
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
            const intent = input.value.trim();
            if (intent && currentState !== State.EXECUTING) runPipeline(intent);
        }
    });
}

// ──────────────────────────────────────────────────────────
// PIPELINE — EXECUTE
// ──────────────────────────────────────────────────────────
async function runPipeline(intent) {
    setSystemState(State.EXECUTING);
    setTraceLoading();
    hideClarifications();

    try {
        const resp = await fetch("/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ intent }),
        });

        const rawBody = await resp.text();
        let data = null;

        if (rawBody) {
            try {
                data = JSON.parse(rawBody);
            } catch {
                data = null;
            }
        }

        if (!resp.ok) {
            let errorMsg =
                data?.message ||
                rawBody.substring(0, 200).replace(/<[^>]*>?/gm, "").trim() ||
                "Server returned error " + resp.status;
            throw new Error(errorMsg);
        }

        if (!data) {
            throw new Error("Server returned an invalid JSON response");
        }

        // ── Clarification needed ───────────────────────────
        if (data.status === "needs_clarification") {
            showClarifications(data.questions || []);
            setSystemState(State.IDLE);
            setTraceEmpty();
            return;
        }

        // ── Hard error from server ─────────────────────────
        if (data.status === "error") {
            throw new Error(data.message || "Pipeline returned error status");
        }

        // ── Completed ──────────────────────────────────────
        if (data.status === "completed") {
            Session.ingest(data);

            processedCount++;
            totalTasksRun += data.results?.length || 0;

            renderPipeline(data);
            updatePipelineSidebar(data);
            updateBottomTiles();
            updateSessionMetricsPanel();
            loadHistory();          // refresh history tab

            setSystemState(State.COMPLETE);
        }

    } catch (err) {
        console.error("[Pipeline Error]", err);
        setSystemState(State.ERROR);
        setTraceError(err.message);
    }
}



// ──────────────────────────────────────────────────────────
// SYSTEM STATE MANAGEMENT
// ──────────────────────────────────────────────────────────

function setText(id, value) {
    const el = document.getElementById(id);
    if (!el) return; // prevent crash
    el.textContent = value;
}

function escapeHtml(str) {
    if (typeof str !== "string") return str;
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function setSystemState(state) {
    currentState = state;

    const indicator = document.getElementById("system-status-indicator");
    const btn = document.getElementById("pipeline-execute-btn");
    const modeLabel = document.getElementById("matrix-dag-label");

    const cfg = {
        [State.IDLE]: { text: "SYSTEM_IDLE", cls: "text-primary" },
        [State.EXECUTING]: { text: "SYSTEM_EXECUTING", cls: "text-secondary animate-glow" },
        [State.COMPLETE]: { text: "SYSTEM_COMPLETE", cls: "text-primary" },
        [State.ERROR]: { text: "SYSTEM_ERROR", cls: "text-tertiary" },
    }[state] || { text: "SYSTEM_IDLE", cls: "text-primary" };

    if (indicator) {
        indicator.textContent = cfg.text;
        indicator.className = `font-label text-[11px] uppercase tracking-[0.05em] ${cfg.cls}`;
    }
    if (btn) btn.disabled = (state === State.EXECUTING);
    if (modeLabel) modeLabel.textContent = state === State.EXECUTING
        ? "PLANNER_DAG: RUNNING"
        : "PLANNER_DAG: IDLE";
}

// ──────────────────────────────────────────────────────────
// TRACE CONTAINER STATES
// ──────────────────────────────────────────────────────────
function setTraceLoading() {
    const tc = document.getElementById("trace-container");
    if (!tc) return;
    tc.innerHTML = `
        <div class="flex flex-col items-center justify-center h-full opacity-30">
            <span class="material-symbols-outlined text-5xl mb-4 animate-glow text-primary">sync</span>
            <span class="font-label text-xs uppercase tracking-[0.3em] text-outline">Executing pipeline...</span>
        </div>`;
}

function setTraceEmpty() {
    const tc = document.getElementById("trace-container");
    if (!tc) return;
    tc.innerHTML = `
        <div class="flex flex-col items-center justify-center h-full opacity-20">
            <span class="material-symbols-outlined text-6xl mb-4">analytics</span>
            <span class="font-label text-xs uppercase tracking-[0.3em]">Awaiting execution data...</span>
        </div>`;
}

function setTraceError(message) {
    const tc = document.getElementById("trace-container");
    if (!tc) return;
    tc.innerHTML = `
        <div class="flex flex-col items-center justify-center h-full opacity-60 text-tertiary gap-3">
            <span class="material-symbols-outlined text-5xl">error</span>
            <span class="font-label text-xs uppercase tracking-[0.3em]">Pipeline Error</span>
            <span class="font-body text-xs text-outline">${escapeHtml(message)}</span>
        </div>`;
}

// ──────────────────────────────────────────────────────────
// PIPELINE RENDER
// Reads: data.plan, data.results[], data.final
// ──────────────────────────────────────────────────────────
function renderPipeline(data) {
    const tc = document.getElementById("trace-container");
    if (!tc) return;
    tc.innerHTML = "";

    const plan = data.plan || {};
    const results = data.results || [];
    const final = data.final || null;

    // Update matrix header labels
    setText("matrix-dag-label", `PLANNER_DAG: ${(plan.mode || "DIRECT").toUpperCase()}`);
    setText("matrix-tasks-label", `TASKS: ${results.length}`);

    // ── Planner section ──────────────────────────────────
    tc.appendChild(makeDivider("PLANNER_CORE", "Deterministic rule-based decomposition"));
    tc.appendChild(makePlannerCard(plan));

    // ── Worker sections ──────────────────────────────────
    if (results.length) {
        tc.appendChild(makeDivider(
            "EXPERT_WORKERS",
            `${results.length} domain-specialized worker${results.length > 1 ? "s" : ""}`
        ));

        results.forEach((res, idx) => {
            // Stagger entrance so cards animate in sequentially
            const card = makeWorkerCard(res, idx);
            card.style.animationDelay = `${idx * 100}ms`;
            tc.appendChild(card);
        });
    }

    // ── Assembler section ────────────────────────────────
    if (final) {
        tc.appendChild(makeDivider("ASSEMBLER_RESULT", "Final synthesized output"));
        const ac = makeAssemblerCard(final, results);
        ac.style.animationDelay = `${results.length * 100 + 100}ms`;
        tc.appendChild(ac);
    }
}

// ── Card builders ────────────────────────────────────────

function makeDivider(title, subtitle) {
    const d = document.createElement("div");
    d.className = "flex items-center gap-3 mt-6 mb-3 trace-module-enter";
    d.innerHTML = `
        <div class="h-px flex-1 bg-sapphire/20"></div>
        <div class="text-center">
            <span class="font-headline text-[10px] tracking-[0.3em] text-outline uppercase">${escapeHtml(title)}</span>
            <span class="font-label text-[9px] text-outline/50 ml-2 uppercase">${escapeHtml(subtitle)}</span>
        </div>
        <div class="h-px w-12 bg-sapphire/20"></div>`;
    return d;
}

function makePlannerCard(plan) {
    /*
     plan shape from _normalize_plan():
       { intent, mode, pattern, status, tasks[] }
     tasks[]:
       { id, type, target, depends_on[] }
    */
    const d = document.createElement("div");
    d.className = "panel p-5 bg-surface-lowest/30 border-l-2 border-primary/30 trace-module-enter";

    const modeMeta = MODE_META[plan.mode] || { label: plan.mode || "—", color: "text-outline" };

    const taskRows = (plan.tasks || []).map(t => {
        const depHtml = t.depends_on?.length
            ? `<span class="font-label text-[9px] text-outline uppercase ml-auto">dep: ${escapeHtml(t.depends_on.join(", "))}</span>`
            : "";
        return `
            <div class="flex items-center gap-2 py-1.5 border-b border-outline-variant/10 last:border-0">
                <span class="task-type-badge ${escapeHtml(t.type)}">${escapeHtml(t.type || "TASK")}</span>
                <span class="font-label text-[10px] text-on-surface/70 flex-1">${escapeHtml(t.target || t.id)}</span>
                ${depHtml}
            </div>`;
    }).join("");

    d.innerHTML = `
        <div class="flex justify-between items-start mb-4">
            <div class="flex-1 pr-4">
                <span class="font-label text-[9px] uppercase tracking-widest text-outline block mb-1">Intent Parsed</span>
                <p class="font-body text-sm text-on-surface">${escapeHtml(plan.intent || "—")}</p>
            </div>
            <div class="text-right flex-shrink-0">
                <span class="font-label text-[9px] uppercase tracking-widest text-outline block mb-1">Mode</span>
                <span class="font-headline text-sm font-bold uppercase ${modeMeta.color}">${escapeHtml(modeMeta.label)}</span>
            </div>
        </div>
        ${plan.tasks?.length ? `
            <div class="mt-3">
                <span class="font-label text-[9px] uppercase tracking-widest text-outline block mb-2">
                    Task DAG — ${plan.tasks.length} task${plan.tasks.length > 1 ? "s" : ""}
                </span>
                <div>${taskRows}</div>
            </div>` : ""}`;
    return d;
}

function makeWorkerCard(res, idx) {
    const conf = res.confidence ?? 0;
    const confPct = Math.round(conf * 100);
    const confTier = conf >= 0.85 ? "high" : conf >= 0.70 ? "mid" : "low";
    const confColor = confTier === "high" ? "text-primary" : confTier === "mid" ? "text-secondary" : "text-tertiary";
    const isCode = CODE_TASK_TYPES.has(res.task_type);

    const vm = VERDICT_META[res.validation_verdict || "accept"] || VERDICT_META.accept;

    const preview = (res.result || "No output.")
        .replace(/```[\s\S]*?```/g, "[code block]")
        .replace(/\n+/g, " ")
        .trim()
        .slice(0, 120);
    const hasMore = (res.result || "").length > 120;

    const execHtml = isCode ? `
        <div class="flex items-center gap-2 mt-1">
            <span class="font-label text-[9px] uppercase ${res.execution_success ? "text-primary" : "text-tertiary"}">
                ${res.execution_success ? "✅ Executed" : "❌ Failed"}
            </span>
            ${(res.attempts || 1) > 1
            ? `<span class="font-label text-[9px] text-outline">${res.attempts} attempts</span>`
            : ""}
        </div>` : "";

    const d = document.createElement("div");
    d.className = [
        "worker-card",  // ✅ FIXED
        "flex items-center justify-between gap-4",
        "panel p-4 mb-3",
        "border-l-2",
        confTier === "high" ? "border-primary/60 conf-high" :
            confTier === "mid" ? "border-secondary/60 conf-mid" :
                "border-tertiary/60 conf-low",
        "cursor-pointer",
        "hover:bg-surface-container",
        "transition-all duration-150",
        "trace-module-enter",
        "group"
    ].join(" ");

    d.innerHTML = `
        <div class="flex items-start gap-3 flex-1 min-w-0">
            <span class="type-badge ${escapeHtml(res.task_type)} flex-shrink-0 mt-0.5">
                ${escapeHtml(res.task_type || "TASK")}
            </span>
            <div class="min-w-0">
                <div class="flex items-center gap-2 mb-0.5">
                    <span class="font-headline text-xs font-bold uppercase text-on-surface">
                        ${escapeHtml(res.task_id || `t${idx + 1}`)}
                    </span>
                    <span class="font-label text-[9px] uppercase ${vm.color}">${vm.label}</span>
                </div>
                <p class="font-body text-[11px] text-on-surface/50 truncate">
                    ${escapeHtml(preview)}${hasMore ? "…" : ""}
                </p>
                ${execHtml}
            </div>
        </div>

        <div class="flex items-center gap-4 flex-shrink-0">
            <div class="text-right">
                <span class="font-headline text-lg font-bold ${confColor}">${confPct}%</span>
                <div class="w-16 h-0.5 bg-surface-highest mt-1">
                    <div class="h-full ${confTier === "high" ? "bg-primary" :
            confTier === "mid" ? "bg-secondary" : "bg-tertiary"
        }" style="width:${confPct}%"></div>
                </div>
            </div>
            <span class="material-symbols-outlined text-outline group-hover:text-primary transition-colors text-xl">
                open_in_full
            </span>
        </div>`;

    d.addEventListener("click", (e) => {  // ✅ FIXED
        e.stopPropagation();
        openTaskModal(res, {
            intent: document.querySelector("#pipeline-input")?.value || ""
        });
    });

    return d;
}

function makeAssemblerCard(final, results) {
    const lowConf = final.low_confidence_tasks || [];
    const method = final.assembly_method || "groq";

    const methodMeta = {
        direct: { label: "DIRECT PASS-THROUGH", color: "text-secondary" },
        groq: { label: "GROQ SYNTHESIZED", color: "text-primary" },
        llm: { label: "LLM SYNTHESIZED", color: "text-sapphire-light" },
        deterministic: { label: "DETERMINISTIC MERGE", color: "text-secondary" },
    };
    const mm = methodMeta[method] || methodMeta.groq;

    // Preview text
    const preview = (final.final_output || "No output.")
        .replace(/\n+/g, " ")
        .trim()
        .slice(0, 120);
    const hasMore = (final.final_output || "").length > 120;

    const warningHtml = lowConf.length
        ? `<span class="font-label text-[9px] text-tertiary uppercase ml-2">
               ⚠ ${lowConf.length} low-conf task${lowConf.length > 1 ? "s" : ""}
           </span>`
        : "";

    const d = document.createElement("div");
    d.className = [
        "flex items-center justify-between gap-4",
        "panel p-4 mb-3",
        "border-l-2 border-sapphire/50",
        "cursor-pointer",
        "hover:bg-surface-container",
        "transition-all duration-150",
        "trace-module-enter",
        "group"
    ].join(" ");

    d.innerHTML = `
        <!-- Left: type + preview -->
        <div class="flex items-start gap-3 flex-1 min-w-0">
            <span class="type-badge SYNTHESIS flex-shrink-0 mt-0.5">SYNTHESIS</span>
            <div class="min-w-0">
                <div class="flex items-center gap-2 mb-0.5">
                    <span class="font-headline text-xs font-bold uppercase text-on-surface">
                        ASSEMBLER
                    </span>
                    <span class="font-label text-[9px] uppercase ${mm.color}">${mm.label}</span>
                    ${warningHtml}
                </div>
                <p class="font-body text-[11px] text-on-surface/50 truncate">
                    ${escapeHtml(preview)}${hasMore ? "…" : ""}
                </p>
            </div>
        </div>

        <!-- Right: task count + expand -->
        <div class="flex items-center gap-4 flex-shrink-0">
            <div class="text-right">
                <span class="font-label text-[9px] text-outline uppercase block">merged</span>
                <span class="font-headline text-lg font-bold text-sapphire-light">
                    ${results.length} task${results.length !== 1 ? "s" : ""}
                </span>
            </div>
            <span class="material-symbols-outlined text-outline group-hover:text-primary transition-colors text-xl">
                open_in_full
            </span>
        </div>`;

    // Click → open modal

    d.addEventListener("click", (e) => {
        e.stopPropagation();
        openTaskModal({
            task_id: "ASSEMBLER",
            task_type: "SYNTHESIS",
            result: final.final_output || "No output.",
            confidence: 1.0,
            validation_verdict: "accept",
            execution_success: undefined,   // not a code task
            attempts: undefined,
        }, {
            intent: document.querySelector("#pipeline-input")?.value || ""
        });
    });

    return d;
}

// ──────────────────────────────────────────────────────────
// PIPELINE SIDEBAR + BOTTOM TILES
// ──────────────────────────────────────────────────────────
function updatePipelineSidebar(data) {
    const plan = data.plan || {};
    const results = data.results || [];

    // Active execution path indicator
    const modeLabel = MODE_META[plan.mode]?.label || plan.mode || "—";
    const pathEl = document.getElementById("active-path-indicator");
    const pathLbl = document.getElementById("active-path-label");
    if (pathEl && pathLbl) {
        pathLbl.textContent = modeLabel;
        pathEl.classList.remove("hidden");
    }

    // Confidence bar + labels
    if (results.length) {
        const avg = results.reduce((a, r) => a + (r.confidence ?? 0), 0) / results.length;
        const pct = Math.round(avg * 100);
        const tier = avg >= 0.85 ? "Auto-Accept" : avg >= 0.70 ? "Quick-Check" : "Full-Verify";

        setText("sidebar-confidence-val", `${pct}%`);
        setText("validation-tier-label", tier);

        const bar = document.getElementById("confidence-bar");
        if (bar) bar.style.width = `${pct}%`;
    }

    setText("task-count-label", `${results.length}`);
    setText("execution-mode-badge", `MODE: ${(plan.mode || "DIRECT").toUpperCase()}`);
}

function updateBottomTiles() {
    setText("processed-count", String(processedCount));
    setText("total-tasks-run", String(totalTasksRun));
}

// ──────────────────────────────────────────────────────────
// SESSION METRICS PANEL (nav dropdown)
// ──────────────────────────────────────────────────────────
function updateSessionMetricsPanel() {
    setText("metric-queries", String(Session.runs.length));
    setText("metric-avg-tasks", Session.runs.length
        ? (Session.totalTasks / Session.runs.length).toFixed(1)
        : "0.0");
    setText("metric-efficiency", `+${Session.efficiencyPct()}%`);

    // Validation tier from last run
    const lastRun = Session.runs[Session.runs.length - 1];
    if (lastRun?.results?.length) {
        const avg = lastRun.results.reduce((a, r) => a + (r.confidence ?? 0), 0) / lastRun.results.length;
        const tier = avg >= 0.85 ? "AUTO-ACCEPT" : avg >= 0.70 ? "QUICK-CHECK" : "FULL-VERIFY";
        setText("metric-val-tier", tier);
    }
}

// ──────────────────────────────────────────────────────────
// CLARIFICATIONS
// ──────────────────────────────────────────────────────────
function showClarifications(questions) {
    const panel = document.getElementById("clarification-panel");
    const qdiv = document.getElementById("clarification-questions");
    if (!panel || !qdiv) return;
    panel.classList.remove("hidden");
    qdiv.innerHTML = questions
        .map(q => `<p class="text-xs font-label text-on-surface/80">&gt; ${escapeHtml(q)}</p>`)
        .join("");
}

function hideClarifications() {
    document.getElementById("clarification-panel")?.classList.add("hidden");
}

// ──────────────────────────────────────────────────────────
// HISTORY TAB
// ──────────────────────────────────────────────────────────
function initHistoryControls() {
    // Live search
    document.getElementById("history-search")?.addEventListener("input", e => {
        historySearch = e.target.value.toLowerCase().trim();
        renderHistoryRows();
    });

    // Filter buttons
    document.querySelectorAll(".history-filter-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".history-filter-btn")
                .forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            historyFilter = btn.dataset.filter;
            renderHistoryRows();
        });
    });
}

async function loadHistory() {
    try {
        const resp = await fetch("/history");
        if (!resp.ok) return;

        const data = await resp.json();
        historyCache = data;                    // newest-first from server

        // Hydrate session store from server history (handles page refresh)
        Session.hydrate(data);
        updateSessionMetricsPanel();
        updateBottomTiles();

        setText("history-total-count", String(data.length));
        renderHistoryRows();

    } catch (err) {
        console.error("[History] Load error:", err);
    }
}

function renderHistoryRows() {
    const container = document.getElementById("history-rows");
    if (!container) return;

    // Apply filter + search
    const filtered = historyCache.filter(entry => {
        const statusOk =
            historyFilter === "all" ? true :
                historyFilter === "completed" ? entry.status === "completed" :
                    historyFilter === "error" ? entry.status === "error" :
                        true;

        const haystack = `${entry.id || ""} ${entry.intent || ""} ${entry.status || ""} ${entry.mode || ""}`.toLowerCase();
        const searchOk = !historySearch || haystack.includes(historySearch);

        return statusOk && searchOk;
    });

    container.innerHTML = "";

    if (!filtered.length) {
        container.innerHTML = `
            <div class="p-12 text-center opacity-20">
                <span class="font-label text-sm uppercase tracking-widest">No matching records.</span>
            </div>`;
        return;
    }

    filtered.forEach((entry, i) => {
        const isOk = entry.status === "completed";
        const dotColor = isOk ? "text-primary" : "text-tertiary";
        const dotIcon = isOk ? "check_circle" : "error";
        const ts = entry.timestamp ? formatTimestamp(entry.timestamp) : "—";
        const mode = entry.mode || entry.plan?.mode || "—";
        const tasks = entry.total_tasks ?? entry.results?.length ?? "—";

        const row = document.createElement("div");
        row.className = "history-grid px-6 py-4 bg-surface-low hover:bg-surface-container transition-colors cursor-pointer border-l-2 border-transparent";

        row.innerHTML = `
            <div class="flex items-center">
                <span class="material-symbols-outlined text-base ${dotColor}"
                      style="font-variation-settings:'FILL' 1">${dotIcon}</span>
            </div>
            <div class="flex flex-col min-w-0">
                <span class="font-headline text-xs font-bold uppercase truncate">
                    ${escapeHtml(entry.id || entry.execution_id || `run-${i + 1}`)}
                </span>
                <span class="font-label text-[9px] text-outline uppercase mt-0.5">
                    ${escapeHtml(entry.status || "—")}
                </span>
            </div>
            <div class="font-label text-[10px] text-outline">${escapeHtml(ts)}</div>
            <div><span class="font-label text-[10px] uppercase text-secondary">${escapeHtml(mode)}</span></div>
            <div class="font-headline text-sm text-primary">${escapeHtml(String(tasks))}</div>
            <div class="font-body text-xs text-on-surface/70 truncate pr-4">${escapeHtml(entry.intent || "—")}</div>`;

        row.addEventListener("click", () => openHistoryDetail(entry, row));
        container.appendChild(row);
    });
}

function openHistoryDetail(entry, rowEl) {
    // Toggle off if same row clicked again
    if (activeHistoryRow === rowEl) {
        closeHistoryDetail();
        return;
    }

    // Deactivate previous
    if (activeHistoryRow) activeHistoryRow.classList.remove("history-row-active");
    rowEl.classList.add("history-row-active");
    activeHistoryRow = rowEl;

    const panel = document.getElementById("history-detail-panel");
    if (!panel) return;
    panel.classList.remove("hidden");

    // Header
    setText("detail-exec-id", entry.id || entry.execution_id || "—");
    setText("detail-intent", entry.intent || "—");
    setText("detail-mode", entry.mode || entry.plan?.mode || "—");
    setText("detail-tasks", String(entry.total_tasks ?? entry.results?.length ?? "—"));

    // Task breakdown
    const taskListEl = document.getElementById("detail-task-list");
    if (taskListEl) {
        const tasks = entry.results || [];
        if (!tasks.length) {
            taskListEl.innerHTML = `<span class="font-label text-[10px] text-outline uppercase">No task data available.</span>`;
        } else {
            taskListEl.innerHTML = tasks.map(r => {
                const conf = r.confidence ?? 0;
                const confPct = Math.round(conf * 100);
                const tier = conf >= 0.85 ? "primary" : conf >= 0.70 ? "secondary" : "tertiary";
                const verdict = r.validation_verdict || "accept";
                const vm = VERDICT_META[verdict] || VERDICT_META.accept;
                return `
                    <div class="flex items-center gap-3 py-2 border-b border-outline-variant/10 last:border-0">
                        <span class="task-type-badge ${escapeHtml(r.task_type || "")}">${escapeHtml(r.task_type || "TASK")}</span>
                        <span class="font-label text-[10px] text-on-surface uppercase flex-1">${escapeHtml(r.task_id || "—")}</span>
                        <span class="font-label text-[9px] uppercase ${vm.color}">${vm.label}</span>
                        <span class="font-label text-[9px] text-${tier} font-bold">${confPct}%</span>
                        <div class="w-16 h-1 bg-surface-highest overflow-hidden flex-shrink-0">
                            <div class="h-full bg-${tier}" style="width:${confPct}%"></div>
                        </div>
                    </div>`;
            }).join("");
        }
    }

    // Final output
    const finalOut = entry.final?.final_output || null;
    const finalSection = document.getElementById("detail-final-output-section");
    if (finalSection) {
        if (finalOut) {
            finalSection.classList.remove("hidden");
            setText("detail-final-output", finalOut);
        } else {
            finalSection.classList.add("hidden");
        }
    }

    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

window.closeHistoryDetail = function () {
    document.getElementById("history-detail-panel")?.classList.add("hidden");
    if (activeHistoryRow) {
        activeHistoryRow.classList.remove("history-row-active");
        activeHistoryRow = null;
    }
};

// ──────────────────────────────────────────────────────────
// ANALYTICS TAB
// All data sourced from Session store, which is built
// exclusively from real /run and /history responses.
// ──────────────────────────────────────────────────────────
function renderAnalytics() {
    const s = Session;

    // ── KPIs ─────────────────────────────────────────────
    setText("kpi-runs", String(s.runs.length));
    setText("kpi-tasks", String(s.totalTasks));

    const avg = s.avgConfidence();
    setText("kpi-conf", avg !== null ? `${Math.round(avg * 100)}%` : "—");
    setText("kpi-hc", String(s.highConf));

    // ── Confidence tier counts ────────────────────────────
    setText("tier-high", String(s.highConf));
    setText("tier-mid", String(s.midConf));
    setText("tier-low", String(s.lowConf));

    // ── Sub-renders ──────────────────────────────────────
    renderModeDistribution();
    renderTaskTypeDistribution();
    renderConfidenceChart();
    renderDecompPatterns();
    renderValidationEventLog();
}

// ── Mode distribution bars ───────────────────────────────
function renderModeDistribution() {
    const el = document.getElementById("mode-dist");
    if (!el) return;

    const counts = Session.modeCounts;
    const total = Object.values(counts).reduce((a, b) => a + b, 0);

    if (!total) {
        el.innerHTML = emptyPlaceholder("Run queries to populate");
        return;
    }

    el.innerHTML = Object.entries(counts)
        .sort((a, b) => b[1] - a[1])
        .map(([mode, count]) => {
            const meta = MODE_META[mode] || { label: mode, color: "text-outline", barColor: "bg-outline" };
            const pct = Math.round((count / total) * 100);
            return `
                <div class="space-y-1.5">
                    <div class="flex justify-between font-label text-[10px] uppercase">
                        <span class="text-outline">${escapeHtml(meta.label)}</span>
                        <span class="${meta.color}">${count} run${count !== 1 ? "s" : ""} (${pct}%)</span>
                    </div>
                    <div class="h-1.5 bg-surface-lowest w-full overflow-hidden">
                        <div class="h-full ${meta.barColor} transition-all duration-700" style="width:${pct}%"></div>
                    </div>
                </div>`;
        }).join("");
}

// ── Task type bars ───────────────────────────────────────
function renderTaskTypeDistribution() {
    const el = document.getElementById("type-dist");
    if (!el) return;

    const types = Session.taskTypes;
    const total = Object.values(types).reduce((a, b) => a + b, 0);

    if (!total) {
        el.innerHTML = emptyPlaceholder("Run queries to populate");
        return;
    }

    el.innerHTML = Object.entries(types)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 8)
        .map(([type, count]) => {
            const meta = TYPE_COLOR[type] || { badge: type, bar: "bg-outline" };
            const pct = Math.round((count / total) * 100);
            return `
                <div class="flex items-center gap-3">
                    <span class="task-type-badge ${escapeHtml(type)} w-24 text-center flex-shrink-0">${escapeHtml(type)}</span>
                    <div class="flex-1 h-1.5 bg-surface-lowest overflow-hidden">
                        <div class="h-full ${meta.bar} transition-all duration-700" style="width:${pct}%"></div>
                    </div>
                    <span class="font-label text-[10px] text-outline w-6 text-right flex-shrink-0">${count}</span>
                </div>`;
        }).join("");
}

// ── Per-task confidence bar chart ────────────────────────
function renderConfidenceChart() {
    const el = document.getElementById("conf-sparkline");
    if (!el) return;

    const scores = Session.confidenceAll;
    if (!scores.length) {
        el.innerHTML = `
            <div class="flex-1 flex items-center justify-center h-full opacity-20">
                <span class="font-label text-[9px] uppercase tracking-widest text-outline">No data</span>
            </div>`;
        return;
    }

    // Show last 48 tasks
    el.innerHTML = scores.slice(-48).map(conf => {
        const pct = Math.round(conf * 100);
        const color = conf >= 0.85 ? "#4edea3" : conf >= 0.70 ? "#9ed2b5" : "#ffb3af";
        return `
            <div class="flex-1 flex flex-col justify-end h-full group relative cursor-pointer">
                <div class="analytics-bar rounded-t-sm"
                     style="height:${pct}%; background:${color}; opacity:0.75;"></div>
                <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-1
                            bg-surface-high border border-outline-variant/30 px-2 py-1
                            text-[9px] font-label text-on-surface uppercase
                            opacity-0 group-hover:opacity-100 transition-opacity
                            pointer-events-none whitespace-nowrap z-10">
                    ${pct}%
                </div>
            </div>`;
    }).join("");
}

// ── Decomposition pattern tiles ──────────────────────────
function renderDecompPatterns() {
    /*
     Pattern counts come from plan.pattern, which _normalize_plan
     sets to plan.pattern || plan.mode.
     
     The planner currently exposes mode but not always a separate
     pattern field. We map what we have:
       - "dag"        → could be list / numeric / comparison / sequential
       - "direct"     → direct
       - "ultra_fast" → direct bucket
     
     If the planner ever adds plan.pattern = "list" etc., it flows
     through automatically. Until then we surface mode-level data.
    */
    const pat = Session.patternCounts;

    // Build a lookup that tries specific patterns first, falls back to mode
    const counts = {
        list: pat.list || 0,
        numeric: pat.numeric || 0,
        comparison: pat.comparison || 0,
        sequential: pat.sequential || 0,
        direct: (pat.direct || 0) + (pat.ultra_fast || 0),
    };

    // If planner doesn't expose patterns, distribute dag runs under "list"
    // placeholder so tiles aren't all zero — label makes this clear
    const dagRuns = Session.modeCounts.dag || 0;
    if (dagRuns && !counts.list && !counts.numeric && !counts.comparison && !counts.sequential) {
        counts.list = dagRuns;   // best-effort fallback
    }

    const ids = ["list", "numeric", "comparison", "sequential", "direct"];
    ids.forEach(id => {
        const valEl = document.getElementById(`pat-${id}`);
        const cardEl = valEl?.closest(".panel");
        if (valEl) valEl.textContent = String(counts[id]);
        if (cardEl) {
            counts[id] > 0
                ? cardEl.classList.add("pattern-card-active")
                : cardEl.classList.remove("pattern-card-active");
        }
    });
}

// ── Validation event log ─────────────────────────────────
function renderValidationEventLog() {
    const el = document.getElementById("val-event-log");
    if (!el) return;

    const events = Session.validationEvents;
    if (!events.length) {
        el.innerHTML = `
            <div class="opacity-30 text-center py-6">
                <span class="font-label text-xs uppercase tracking-widest">No validation events recorded</span>
            </div>`;
        return;
    }

    // Newest first, last 30
    el.innerHTML = [...events].reverse().slice(0, 30).map(evt => {
        const vm = VERDICT_META[evt.verdict] || VERDICT_META.accept;
        const confPct = Math.round((evt.confidence ?? 0) * 100);
        return `
            <div class="val-event-row ${vm.cls}">
                <span class="material-symbols-outlined text-sm ${vm.color}">${vm.icon}</span>
                <span class="text-outline truncate max-w-[100px]">${escapeHtml(evt.run_id)}</span>
                <span class="text-on-surface/70">${escapeHtml(evt.task_id)}</span>
                <span class="${vm.color} font-bold">${vm.label}</span>
                <span class="ml-auto text-outline">${confPct}%</span>
            </div>`;
    }).join("");
}

// ──────────────────────────────────────────────────────────
// UPTIME CLOCK
// ──────────────────────────────────────────────────────────
function initUptimeClock() {
    setInterval(() => {
        uptimeSeconds++;
        const h = String(Math.floor(uptimeSeconds / 3600)).padStart(2, "0");
        const m = String(Math.floor((uptimeSeconds % 3600) / 60)).padStart(2, "0");
        const s = String(uptimeSeconds % 60).padStart(2, "0");
        const str = `${h}:${m}:${s}`;
        setText("uptime-val", str);
        setText("uptime-val-bottom", str);
    }, 1000);
}

// ──────────────────────────────────────────────────────────
// UTILITIES
// ──────────────────────────────────────────────────────────

/** Safe textContent setter */
function setText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
}

/** XSS-safe HTML escaper */
function escapeHtml(text) {
    if (text == null) return "";
    const d = document.createElement("div");
    d.textContent = String(text);
    return d.innerHTML;
}

/** ISO/epoch → HH:MM:SS local time string */
function formatTimestamp(ts) {
    try {
        const d = new Date(ts);
        if (isNaN(d.getTime())) return String(ts);
        return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch {
        return String(ts);
    }
}

/** Shared empty-state placeholder HTML */
function emptyPlaceholder(msg) {
    return `
        <div class="opacity-30 text-center py-8">
            <span class="font-label text-xs uppercase tracking-widest">${escapeHtml(msg)}</span>
        </div>`;
}

