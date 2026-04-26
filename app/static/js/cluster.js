let socket;
let socketPollInterval;
let httpPollInterval;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
const POLL_MS = 3000;

let lastKnownProcesses = [];
let hasRenderedOnce = false;
let socketConnected = false;
let lastHttpOkAt = 0;

document.addEventListener('DOMContentLoaded', function () {

    fetchStatusHttp();
    httpPollInterval = setInterval(fetchStatusHttp, POLL_MS);

    if (typeof io !== 'function') {
        setConnectionStatus(false, 'Polling');
        return;
    }

    socket = io({
        transports: ['websocket', 'polling'],
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        reconnectionAttempts: MAX_RECONNECT_ATTEMPTS,
    });

    socket.on('connect', function () {
        socketConnected = true;
        setConnectionStatus(true);
        reconnectAttempts = 0;
        requestStatus();
        if (socketPollInterval) clearInterval(socketPollInterval);
        socketPollInterval = setInterval(requestStatus, POLL_MS);
    });

    socket.on('disconnect', function () {
        socketConnected = false;
        setConnectionStatus(false, 'Polling');
        if (socketPollInterval) clearInterval(socketPollInterval);
    });

    socket.on('connect_error', function () {
        socketConnected = false;
        reconnectAttempts++;
        if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
            setConnectionStatus(false, 'Polling');
        }
    });

    socket.on('status_update', function (data) {
        handleStatusPayload(data);
    });

    document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
            if (socketPollInterval) clearInterval(socketPollInterval);
        } else {
            requestStatus();
            socketPollInterval = setInterval(requestStatus, POLL_MS);
            fetchStatusHttp();
        }
    });

    window.addEventListener('beforeunload', function () {
        if (socket) socket.disconnect();
        if (socketPollInterval) clearInterval(socketPollInterval);
        if (httpPollInterval) clearInterval(httpPollInterval);
    });
});

function handleStatusPayload(data) {
    if (data && Array.isArray(data.processes)) {
        lastKnownProcesses = data.processes;
        renderDashboard(data.processes);
        hasRenderedOnce = true;
    } else if (hasRenderedOnce) {
        renderDashboard(lastKnownProcesses);
    } else {
        renderDashboard([]);
    }
}

function fetchStatusHttp() {
    fetch('/service/status', { headers: { Accept: 'application/json' } })
        .then((r) => r.ok ? r.json() : null)
        .then((data) => {
            if (!data) return;
            lastHttpOkAt = Date.now();

            if (!socketConnected) setConnectionStatus(true, 'Polling');
            handleStatusPayload(data);
        })
        .catch(() => {  });
}

function requestStatus() {
    if (socket && socket.connected) {
        socket.emit('request_status');
    } else if (socket) {
        socket.connect();
    }
}

function setConnectionStatus(online, overrideText) {
    const el = document.getElementById('connection-status');
    if (!el) return;
    el.textContent = overrideText || (online ? 'Live' : 'Disconnected');
    el.classList.toggle('is-online', !!online);
    el.classList.toggle('is-offline', !online);
}

function sortProcesses(processes) {
    return [...processes].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
}

function classify(process) {
    if (process.auto_paused) return 'failed';
    if (process.paused) return 'paused';
    if (process.status === 'RUNNING') return 'running';
    if (process.status === 'PENDING') return 'pending';
    if (process.status === 'BACKOFF' || process.status === 'FATAL') return 'warning';
    return 'offline';
}

const STATUS_META = {
    running: { label: 'RUNNING', dot: 'bg-green-500', badge: 'bg-green-100 text-green-700' },
    warning: { label: 'RETRY', dot: 'bg-yellow-500', badge: 'bg-yellow-100 text-yellow-700' },
    failed: { label: 'FAILED', dot: 'bg-red-500', badge: 'bg-red-100 text-red-700' },
    paused: { label: 'PAUSED', dot: 'bg-slate-400', badge: 'bg-slate-100 text-slate-600' },
    pending: { label: 'PENDING', dot: 'bg-blue-400', badge: 'bg-blue-100 text-blue-700' },
    offline: { label: 'OFFLINE', dot: 'bg-slate-300', badge: 'bg-slate-100 text-slate-500' },
};

function renderDashboard(processes) {
    const sorted = sortProcesses(processes);

    let running = 0, offline = 0, failed = 0, paused = 0;
    for (const p of sorted) {
        const kind = classify(p);
        if (kind === 'running') running++;
        else if (kind === 'failed' || kind === 'warning') failed++;
        else if (kind === 'paused') paused++;
        else offline++;
    }

    setText('metric-projects', sorted.length);
    setText('metric-running', running);
    setText('metric-offline', offline + paused);
    setText('metric-failed', failed);
    setText('project-count-badge', `${sorted.length} project${sorted.length !== 1 ? 's' : ''}`);

    const grid = document.getElementById('worker-grid');
    const empty = document.getElementById('worker-empty');
    if (!grid) return;

    grid.innerHTML = '';
    if (sorted.length === 0) {
        if (empty) empty.classList.remove('hidden');
        return;
    }
    if (empty) empty.classList.add('hidden');

    const tpl = document.getElementById('worker-card-template');
    for (const process of sorted) {
        grid.appendChild(buildCard(tpl, process));
    }
}

function buildCard(tpl, process) {
    const node = tpl.content.firstElementChild.cloneNode(true);
    const kind = classify(process);
    const meta = STATUS_META[kind];

    node.classList.add(`is-${kind}`);
    node.querySelector('[data-role="status-dot"]').className =
        `w-2.5 h-2.5 rounded-full shrink-0 ${meta.dot}`;
    const badge = node.querySelector('[data-role="status-badge"]');
    badge.className = `px-2 py-0.5 text-[10px] font-bold rounded shrink-0 ${meta.badge}`;
    badge.textContent = meta.label;

    node.querySelector('[data-role="name"]').textContent = process.name;
    node.querySelector('[data-role="uptime"]').textContent = process.uptime || '—';
    node.querySelector('[data-role="pid"]').textContent = process.pid || '—';
    node.querySelector('[data-role="raw-status"]').textContent = process.status || '—';
    const cpuEl = node.querySelector('[data-role="cpu"]');
    if (cpuEl) {
        cpuEl.textContent = (process.cpu == null) ? '—' : `${process.cpu.toFixed(1)}%`;
    }
    renderSparkline(node, process.cpu_history || [], kind);

    const controls = node.querySelector('[data-role="controls"]');
    controls.innerHTML = '';
    const name = process.name;
    const isRunning = process.status === 'RUNNING';
    const isPaused = !!process.paused;
    const isAutoPaused = !!process.auto_paused;
    const isDegraded = isAutoPaused || kind === 'warning';

    const topRow = document.createElement('div');
    topRow.className = 'ctrl-row';
    controls.appendChild(topRow);

    if (isAutoPaused) {

        appendButton(topRow, 'Critical Stop', 'ctrl-danger', ICONS.stop,
            () => confirmAction(`Clear failure state for ${name}?`, () => clearFailure(name)));
        appendButton(topRow, 'Restart', '', ICONS.restart,
            () => confirmAction(`Restart ${name}?`, () => action('restart', name)));
    } else if (isRunning && isDegraded) {
        appendButton(topRow, 'Critical Stop', 'ctrl-danger', ICONS.stop,
            () => confirmAction(`Stop ${name}?`, () => action('stop', name)));
        appendButton(topRow, 'Restart', '', ICONS.restart,
            () => confirmAction(`Restart ${name}?`, () => action('restart', name)));
    } else if (isRunning) {
        if (isPaused) {
            appendButton(topRow, 'Resume', 'ctrl-primary', ICONS.play, () => action('resume', name));
        } else {
            appendButton(topRow, 'Pause', '', ICONS.pause, () => action('pause', name));
        }
        appendButton(topRow, 'Restart', '', ICONS.restart,
            () => confirmAction(`Restart ${name}?`, () => action('restart', name)));
    } else {
        appendButton(topRow, 'Start', 'ctrl-primary', ICONS.play, () => action('start', name));
        appendButton(topRow, 'Restart', '', ICONS.restart, null, true);
    }

    const midRow = document.createElement('div');
    midRow.className = 'ctrl-row';
    controls.appendChild(midRow);
    appendButton(midRow, 'ReDeploy', '', ICONS.redeploy,
        () => showConfirm({
            title: `Redeploy ${name}?`,
            message: 'This will stop the service, wipe its workdir + venv cache, '
                + 'git-pull the latest commit, reinstall dependencies from scratch, '
                + 'and bring the service back up.\n\nThis action cannot be undone.',
            okLabel: 'Redeploy',
            variant: 'danger',
            icon: '⟳',
            onConfirm: () => redeploy(name),
        }));
    appendButton(midRow, 'Stream Logs', '', ICONS.stream, () => streamLogs(name));

    const bottomRow = document.createElement('div');
    bottomRow.className = 'ctrl-row';
    controls.appendChild(bottomRow);
    const logsLabel = 'Debug Logs';
    appendButton(bottomRow, logsLabel, 'ctrl-logs', ICONS.logs, () => viewLogs(name));

    return node;
}

const ICONS = {
    pause: '<svg class="ctrl-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>',
    play: '<svg class="ctrl-ico" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>',
    stop: '<svg class="ctrl-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><line x1="9" y1="9" x2="15" y2="15"/><line x1="15" y1="9" x2="9" y2="15"/></svg>',
    restart: '<svg class="ctrl-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7"/><polyline points="3 4 3 10 9 10"/></svg>',
    redeploy: '<svg class="ctrl-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7"/><polyline points="21 3 21 9 15 9"/><path d="M12 8v4l3 2"/></svg>',
    stream: '<svg class="ctrl-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>',
    logs: '<svg class="ctrl-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/></svg>',
};

function appendButton(container, label, extraClass, iconSvg, onClick, disabled = false) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `ctrl-btn ${extraClass || ''}`.trim();
    if (iconSvg) {
        btn.innerHTML = `${iconSvg}<span>${label}</span>`;
    } else {
        btn.textContent = label;
    }
    if (disabled) btn.disabled = true;
    if (onClick) btn.addEventListener('click', onClick);
    container.appendChild(btn);
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

const SPARK_W = 100;
const SPARK_H = 32;
const SPARK_PAD = 2;
function renderSparkline(node, samples, kind) {
    const wrap = node.querySelector('[data-role="cpu-spark"]');
    if (!wrap) return;
    const linePath = wrap.querySelector('[data-role="cpu-line"]');
    const areaPath = wrap.querySelector('[data-role="cpu-area"]');
    const empty = wrap.querySelector('[data-role="cpu-empty"]');

    wrap.classList.remove('is-running', 'is-warning', 'is-failed', 'is-paused', 'is-pending', 'is-offline');
    wrap.classList.add(`is-${kind}`);

    if (!samples || samples.length < 2) {
        if (linePath) linePath.setAttribute('d', '');
        if (areaPath) areaPath.setAttribute('d', '');
        if (empty) empty.style.display = '';
        return;
    }
    if (empty) empty.style.display = 'none';

    const n = samples.length;

    const denom = Math.max(n - 1, 1);
    const yMax = 100;
    const innerH = SPARK_H - SPARK_PAD * 2;
    const points = samples.map((v, i) => {
        const x = (i / denom) * SPARK_W;
        const clamped = Math.max(0, Math.min(yMax, Number(v) || 0));
        const y = SPARK_PAD + (1 - clamped / yMax) * innerH;
        return [x, y];
    });

    const lineD = points.map(([x, y], i) =>
        `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`
    ).join(' ');
    const [firstX] = points[0];
    const [lastX] = points[points.length - 1];
    const areaD = `${lineD} L${lastX.toFixed(2)},${SPARK_H} L${firstX.toFixed(2)},${SPARK_H} Z`;

    if (linePath) linePath.setAttribute('d', lineD);
    if (areaPath) areaPath.setAttribute('d', areaD);
}

function confirmAction(message, onYes, opts) {
    showConfirm(Object.assign({ message, onConfirm: onYes }, opts || {}));
}

function showConfirm(opts) {
    const modal = document.getElementById('confirm-modal');
    if (!modal) {

        if (window.confirm(opts.message || 'Are you sure?')) {
            opts.onConfirm && opts.onConfirm();
        }
        return;
    }
    const titleEl = document.getElementById('confirm-title');
    const messageEl = document.getElementById('confirm-message');
    const iconEl = document.getElementById('confirm-icon');
    const okBtn = document.getElementById('confirm-ok');
    const cancelBtn = document.getElementById('confirm-cancel');

    const variant = opts.variant || 'default';
    modal.setAttribute('data-variant', variant);
    titleEl.textContent = opts.title || 'Confirm action';
    messageEl.textContent = opts.message || 'Are you sure?';
    iconEl.textContent = opts.icon || (variant === 'danger' ? '!' : variant === 'warning' ? '⚠' : '?');
    okBtn.textContent = opts.okLabel || 'Confirm';
    cancelBtn.textContent = opts.cancelLabel || 'Cancel';

    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
    setTimeout(() => okBtn.focus(), 50);

    function close() {
        modal.classList.add('hidden');
        modal.setAttribute('aria-hidden', 'true');
        okBtn.removeEventListener('click', onOk);
        cancelBtn.removeEventListener('click', onCancel);
        modal.removeEventListener('click', onBackdrop);
        document.removeEventListener('keydown', onKey);
    }
    function onOk() { close(); opts.onConfirm && opts.onConfirm(); }
    function onCancel() { close(); opts.onCancel && opts.onCancel(); }
    function onBackdrop(e) { if (e.target === modal) onCancel(); }
    function onKey(e) {
        if (e.key === 'Escape') onCancel();
        else if (e.key === 'Enter') onOk();
    }
    okBtn.addEventListener('click', onOk);
    cancelBtn.addEventListener('click', onCancel);
    modal.addEventListener('click', onBackdrop);
    document.addEventListener('keydown', onKey);
}

function action(verb, processName) {
    fetch(`/service/${verb}/${encodeURIComponent(processName)}`, { method: 'POST' })
        .then((r) => r.json())
        .then((data) => {
            if (data.status === 'success') {
                setTimeout(requestStatus, verb === 'restart' ? 2000 : 1000);
            } else {
                alert(`Error: ${data.message || 'unknown error'}`);
            }
        })
        .catch(() => alert(`Failed to ${verb} the process.`));
}

function clearFailure(processName) {
    fetch(`/service/clear_failure/${encodeURIComponent(processName)}`, { method: 'POST' })
        .then((r) => r.json())
        .then((data) => {
            if (data.status === 'success') setTimeout(requestStatus, 1500);
            else alert(`Error: ${data.message || 'unknown error'}`);
        })
        .catch(() => alert('Failed to clear failure state.'));
}

function viewLogs(processName) {
    fetch(`/service/log/${encodeURIComponent(processName)}`)
        .then((response) => {
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return response.blob();
        })
        .then((blob) => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = `${processName}_log.txt`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        })
        .catch(() => alert('Failed to fetch logs.'));
}

function redeploy(processName) {

    streamLogs(processName);
    fetch(`/service/redeploy/${encodeURIComponent(processName)}`, { method: 'POST' })
        .then((r) => r.json())
        .then((data) => {
            if (data.status === 'success') {
                setTimeout(requestStatus, 1500);
            } else {
                alert(`Redeploy failed: ${data.message || 'unknown error'}`);
            }
        })
        .catch(() => alert('Failed to redeploy the process.'));
}

function streamLogs(processName) {
    const url = `/service/stream-view/${encodeURIComponent(processName)}`;
    window.open(url, `_logs_${processName}`, 'noopener');
}
