// ===== State Management =====
const State = {
    IDLE: 'idle',
    ANALYZING: 'analyzing',
    PLANNING: 'planning',
    EXECUTING: 'executing',
    COMPLETE: 'complete',
    ERROR: 'error'
};

let currentState = State.IDLE;

// ===== API CALL =====
async function callAPI(intent, docText) {
    const response = await fetch("/run", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ intent, docText })
    });

    if (!response.ok) {
        throw new Error("Backend request failed");
    }

    return await response.json();
}

// ===== State Management =====
function setState(newState) {
    currentState = newState;
    updateStateIndicator(newState);
}

function updateStateIndicator(state) {
    const stateDot = document.getElementById('state-dot');
    const stateText = document.getElementById('state-text');

    stateDot.className = `state-dot ${state}`;

    const stateLabels = {
        [State.IDLE]: 'Ready',
        [State.ANALYZING]: 'Analyzing request...',
        [State.PLANNING]: 'Creating plan...',
        [State.EXECUTING]: 'Executing tasks...',
        [State.COMPLETE]: 'Complete',
        [State.ERROR]: 'Error'
    };

    stateText.textContent = stateLabels[state] || state;
}

// ===== MAIN FUNCTION =====
async function runPipeline() {
    const intentInput = document.getElementById('intent');
    const documentInput = document.getElementById('document');
    const submitBtn = document.getElementById('submit-btn');

    const intent = intentInput.value.trim();
    const docText = documentInput.value.trim();

    if (!intent) {
        alert('Please enter your intent');
        return;
    }

    hideAllSections();

    submitBtn.disabled = true;
    submitBtn.textContent = 'Processing...';

    try {
        setState(State.ANALYZING);

        const data = await callAPI(intent, docText);

        processResponse(data);

    } catch (error) {
        handleError(error);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Process Request →';
    }
}

// ===== PROCESS RESPONSE =====
function processResponse(data) {

    if (data.plan) {
        setState(State.PLANNING);
        showPlan(data.plan);
    }

    if (data.results) {
        setState(State.EXECUTING);
        showExecution(data.results);
    }

    if (data.final) {
        setState(State.COMPLETE);
        showFinal(data.final);
        showSummary(data);
    }
}

// ===== DISPLAY FUNCTIONS =====
function showPlan(plan) {
    const section = document.getElementById('planning-section');
    const intentSpan = document.getElementById('plan-intent');
    const tasksDiv = document.getElementById('plan-tasks');

    intentSpan.textContent = plan.intent;

    let html = '<h3>Tasks:</h3>';

    plan.tasks.forEach((task, index) => {
        html += `
            <div class="task-card">
                <h3>Task ${index + 1}</h3>
                <div class="task-meta">
                    <div class="task-meta-item">
                        <strong>ID:</strong> ${task.id}
                    </div>
                    <div class="task-meta-item">
                        <strong>Type:</strong> ${task.type}
                    </div>
                    <div class="task-meta-item">
                        <strong>Target:</strong> ${task.target}
                    </div>
                    ${task.depends_on && task.depends_on.length > 0 ? `
                        <div class="task-meta-item">
                            <strong>Depends on:</strong> ${task.depends_on.join(', ')}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    });

    tasksDiv.innerHTML = html;
    section.style.display = 'block';
}

// 🔴 FIX: results is OBJECT → convert to array
function showExecution(results) {
    const section = document.getElementById('execution-section');
    const tasksDiv = document.getElementById('execution-tasks');

    let html = '';

    Object.values(results).forEach(result => {
        const confidence = result.confidence || 0;
        const confidencePercent = (confidence * 100).toFixed(0);

        let confidenceClass = 'low';
        let confidenceText = 'LOW';

        if (confidence >= 0.85) {
            confidenceClass = 'high';
            confidenceText = 'HIGH';
        } else if (confidence >= 0.70) {
            confidenceClass = 'medium';
            confidenceText = 'MEDIUM';
        }

        html += `
            <div class="execution-task">
                <div class="execution-header">
                    <div>${result.task_id}</div>
                </div>
                
                <div class="confidence-display">
                    <span>Confidence:</span>
                    <div class="confidence-bar">
                        <div class="confidence-fill ${confidenceClass}" style="width: ${confidencePercent}%"></div>
                    </div>
                    <div class="confidence-label ${confidenceClass}">
                        ${confidencePercent}% ${confidenceText}
                    </div>
                </div>
                
                <div class="task-result">${escapeHtml(result.result)}</div>
                
                <div class="validation-status ${result.verdict === 'accept' ? 'accepted' : 'retry'}">
                    ${result.verdict || 'unknown'}
                </div>
            </div>
        `;
    });

    tasksDiv.innerHTML = html;
    section.style.display = 'block';
}

function showFinal(finalData) {
    const section = document.getElementById('final-section');
    const output = document.getElementById('final-output');

    output.textContent = finalData.final_output;

    section.style.display = 'block';
}

function showSummary(data) {
    const section = document.getElementById('summary-section');
    const content = document.getElementById('summary-content');

    const totalTasks = data.final?.total_tasks || 0;
    const lowConfTasks = data.final?.low_confidence_tasks || [];

    let html = `
        <div class="summary-grid">
            <div class="summary-item">
                <h4>Total Tasks</h4>
                <div class="value">${totalTasks}</div>
            </div>
            <div class="summary-item">
                <h4>Low Confidence</h4>
                <div class="value">${lowConfTasks.length}</div>
            </div>
        </div>
    `;

    content.innerHTML = html;
    section.style.display = 'block';
}

// ===== ERROR =====
function handleError(error) {
    setState(State.ERROR);

    const section = document.getElementById('error-section');
    const message = document.getElementById('error-message');

    message.textContent = error.message;

    section.style.display = 'block';
}

// ===== UTIL =====
function hideAllSections() {
    [
        'clarification-section',
        'planning-section',
        'routing-section',
        'execution-section',
        'final-section',
        'summary-section',
        'error-section'
    ].forEach(id => {
        document.getElementById(id).style.display = 'none';
    });
}

function resetPipeline() {
    setState(State.IDLE);
    hideAllSections();

    document.getElementById('intent').value = '';
    document.getElementById('document').value = '';
}

function copyOutput() {
    const output = document.getElementById('final-output').textContent;
    navigator.clipboard.writeText(output);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ===== INIT =====
document.addEventListener('DOMContentLoaded', () => {
    setState(State.IDLE);
});