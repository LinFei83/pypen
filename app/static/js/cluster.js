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

const STATUS_LABELS = {
    RUNNING: '运行中',
    PENDING: '等待中',
    BACKOFF: '退避重试',
    FATAL: '致命错误',
    STOPPED: '已停止',
    DOWN: '已停止',
    UNKNOWN: '未知',
};

const ACTION_LABELS = {
    start: '启动',
    stop: '停止',
    restart: '重启',
    pause: '暂停',
    resume: '恢复',
};

document.addEventListener('DOMContentLoaded', function () {

    fetchStatusHttp();
    httpPollInterval = setInterval(fetchStatusHttp, POLL_MS);
    initProjectManager();

    if (typeof io !== 'function') {
        setConnectionStatus(false, '轮询中');
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
        setConnectionStatus(false, '轮询中');
        if (socketPollInterval) clearInterval(socketPollInterval);
    });

    socket.on('connect_error', function () {
        socketConnected = false;
        reconnectAttempts++;
        if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
            setConnectionStatus(false, '轮询中');
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

            if (!socketConnected) setConnectionStatus(true, '轮询中');
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
    el.textContent = overrideText || (online ? '已连接' : '已断开');
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

function formatStatus(status) {
    if (!status) return '—';
    return STATUS_LABELS[status] || status;
}

const STATUS_META = {
    running: { label: '运行中', dot: 'bg-green-500', badge: 'bg-green-100 text-green-700' },
    warning: { label: '重试中', dot: 'bg-yellow-500', badge: 'bg-yellow-100 text-yellow-700' },
    failed: { label: '已失败', dot: 'bg-red-500', badge: 'bg-red-100 text-red-700' },
    paused: { label: '已暂停', dot: 'bg-slate-400', badge: 'bg-slate-100 text-slate-600' },
    pending: { label: '等待中', dot: 'bg-blue-400', badge: 'bg-blue-100 text-blue-700' },
    offline: { label: '离线', dot: 'bg-slate-300', badge: 'bg-slate-100 text-slate-500' },
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
    setText('project-count-badge', `${sorted.length} 个项目`);

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
    node.querySelector('[data-role="raw-status"]').textContent = formatStatus(process.status);
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

        appendButton(topRow, '紧急停止', 'ctrl-danger', ICONS.stop,
            () => confirmAction(`清除 ${name} 的失败状态？`, () => clearFailure(name)));
        appendButton(topRow, '重启', '', ICONS.restart,
            () => confirmAction(`重启 ${name}？`, () => action('restart', name)));
    } else if (isRunning && isDegraded) {
        appendButton(topRow, '紧急停止', 'ctrl-danger', ICONS.stop,
            () => confirmAction(`停止 ${name}？`, () => action('stop', name)));
        appendButton(topRow, '重启', '', ICONS.restart,
            () => confirmAction(`重启 ${name}？`, () => action('restart', name)));
    } else if (isRunning) {
        if (isPaused) {
            appendButton(topRow, '恢复', 'ctrl-primary', ICONS.play, () => action('resume', name));
        } else {
            appendButton(topRow, '暂停', '', ICONS.pause, () => action('pause', name));
        }
        appendButton(topRow, '重启', '', ICONS.restart,
            () => confirmAction(`重启 ${name}？`, () => action('restart', name)));
    } else {
        appendButton(topRow, '启动', 'ctrl-primary', ICONS.play, () => action('start', name));
        appendButton(topRow, '重启', '', ICONS.restart, null, true);
    }

    const midRow = document.createElement('div');
    midRow.className = 'ctrl-row';
    controls.appendChild(midRow);
    appendButton(midRow, '重新同步代码', '', ICONS.redeploy,
        () => showConfirm({
            title: `重新同步代码 ${name}？`,
            message: '此操作将停止服务，在项目目录执行 git pull --ff-only，'
                + '然后重新启动服务。\n\n'
                + '不会清空本地目录，也不会重建虚拟环境。',
            okLabel: '重新同步代码',
            variant: 'danger',
            icon: '⟳',
            onConfirm: () => redeploy(name),
        }));
    appendButton(midRow, '实时日志', '', ICONS.stream, () => streamLogs(name));

    const bottomRow = document.createElement('div');
    bottomRow.className = 'ctrl-row';
    controls.appendChild(bottomRow);
    const logsLabel = '调试日志';
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

        if (window.confirm(opts.message || '确定要继续吗？')) {
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
    titleEl.textContent = opts.title || '确认操作';
    messageEl.textContent = opts.message || '确定要继续吗？';
    iconEl.textContent = opts.icon || (variant === 'danger' ? '!' : variant === 'warning' ? '⚠' : '?');
    okBtn.textContent = opts.okLabel || '确认';
    cancelBtn.textContent = opts.cancelLabel || '取消';

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
                alert(`错误：${data.message || '未知错误'}`);
            }
        })
        .catch(() => alert(`无法${ACTION_LABELS[verb] || verb}该进程。`));
}

function clearFailure(processName) {
    fetch(`/service/clear_failure/${encodeURIComponent(processName)}`, { method: 'POST' })
        .then((r) => r.json())
        .then((data) => {
            if (data.status === 'success') setTimeout(requestStatus, 1500);
            else alert(`错误：${data.message || '未知错误'}`);
        })
        .catch(() => alert('无法清除失败状态。'));
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
        .catch(() => alert('无法获取日志。'));
}

function redeploy(processName) {

    streamLogs(processName);
    fetch(`/service/redeploy/${encodeURIComponent(processName)}`, { method: 'POST' })
        .then((r) => r.json())
        .then((data) => {
            if (data.status === 'success') {
                setTimeout(requestStatus, 1500);
            } else {
                alert(`重新同步代码失败：${data.message || '未知错误'}`);
            }
        })
        .catch(() => alert('无法重新同步该进程的代码。'));
}

function streamLogs(processName) {
    const url = `/service/stream-view/${encodeURIComponent(processName)}`;
    window.open(url, `_logs_${processName}`, 'noopener');
}

let cachedProjects = [];

function initProjectManager() {
    const refreshBtn = document.getElementById('btn-refresh-projects');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => loadProjects());
    }
    const form = document.getElementById('project-form');
    const cancel = document.getElementById('project-form-cancel');
    const modal = document.getElementById('project-form-modal');
    if (form) {
        form.addEventListener('submit', onProjectFormSubmit);
    }
    if (cancel) {
        cancel.addEventListener('click', closeProjectForm);
    }
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeProjectForm();
        });
    }
    loadProjects();
}

function loadProjects() {
    const empty = document.getElementById('project-manager-empty');
    fetch('/api/projects', { headers: { Accept: 'application/json' } })
        .then((r) => {
            if (r.status === 401) {
                window.location.href = '/login';
                return null;
            }
            return r.json();
        })
        .then((data) => {
            if (!data || data.status !== 'success') {
                if (empty) empty.textContent = '无法加载项目列表。';
                return;
            }
            cachedProjects = data.projects || [];
            renderProjectManager(cachedProjects);
        })
        .catch(() => {
            if (empty) empty.textContent = '无法加载项目列表。';
        });
}

function renderProjectManager(projects) {
    const empty = document.getElementById('project-manager-empty');
    const table = document.getElementById('project-manager-table');
    const body = document.getElementById('project-manager-body');
    if (!body || !table || !empty) return;

    body.innerHTML = '';
    if (!projects.length) {
        empty.classList.remove('hidden');
        empty.textContent = 'projects/ 下暂无可用目录。请先在宿主机创建 projects/<id>/。';
        table.classList.add('hidden');
        return;
    }
    empty.classList.add('hidden');
    table.classList.remove('hidden');

    projects.forEach((p) => {
        const tr = document.createElement('tr');
        tr.className = 'border-t border-slate-100';

        let badgeClass = 'pm-badge-unregistered';
        let badgeText = '未登记';
        if (!p.has_dir) {
            badgeClass = 'pm-badge-missing';
            badgeText = '缺目录';
        } else if (p.registered) {
            badgeClass = 'pm-badge-registered';
            badgeText = p.service_status || '已登记';
        }

        const cmd = p.run_command || '—';
        tr.innerHTML = `
            <td class="px-4 py-3 font-semibold text-slate-800">${escapeHtml(p.id)}</td>
            <td class="px-4 py-3"><span class="pm-badge ${badgeClass}">${escapeHtml(badgeText)}</span></td>
            <td class="px-4 py-3"><div class="pm-cmd" title="${escapeHtml(cmd)}">${escapeHtml(cmd)}</div></td>
            <td class="px-4 py-3"><div class="pm-actions" data-id="${escapeHtml(p.id)}"></div></td>
        `;
        const actions = tr.querySelector('.pm-actions');
        if (p.has_dir && !p.registered) {
            appendPmButton(actions, '启用', 'pm-btn-primary', () => openProjectForm(p, 'create'));
        }
        if (p.registered && p.has_dir) {
            appendPmButton(actions, '编辑', '', () => openProjectForm(p, 'edit'));
            appendPmButton(actions, '取消登记', 'pm-btn-danger', () => confirmUnregister(p.id));
        }
        if (p.registered && !p.has_dir) {
            appendPmButton(actions, '取消登记', 'pm-btn-danger', () => confirmUnregister(p.id));
        }
        body.appendChild(tr);
    });
}

function appendPmButton(container, label, extra, onClick) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `pm-btn ${extra || ''}`.trim();
    btn.textContent = label;
    btn.addEventListener('click', onClick);
    container.appendChild(btn);
}

function escapeHtml(text) {
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function envObjectToText(env) {
    if (!env || typeof env !== 'object') return '';
    return Object.keys(env).map((k) => `${k}=${env[k]}`).join('\n');
}

function parseEnvText(text) {
    const out = {};
    String(text || '').split('\n').forEach((line) => {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) return;
        const idx = trimmed.indexOf('=');
        if (idx <= 0) return;
        const key = trimmed.slice(0, idx).trim();
        const val = trimmed.slice(idx + 1).trim();
        if (key) out[key] = val;
    });
    return out;
}

function truthyCron(val) {
    if (typeof val === 'boolean') return val;
    return String(val || '').trim().toLowerCase() === 'true';
}

function openProjectForm(project, mode) {
    const modal = document.getElementById('project-form-modal');
    const title = document.getElementById('project-form-title');
    const ok = document.getElementById('project-form-ok');
    if (!modal) return;

    document.getElementById('pf-mode').value = mode;
    document.getElementById('pf-id').value = project.id || '';
    document.getElementById('pf-run').value = project.run_command || '';
    document.getElementById('pf-logs').value = project.logs_size || '10M';
    document.getElementById('pf-env').value = envObjectToText(project.env);
    const cron = project.cron || {};
    document.getElementById('pf-restart').value = cron.restart_on != null ? String(cron.restart_on) : '0';
    document.getElementById('pf-idle').value = cron.idle != null ? String(cron.idle) : '';
    document.getElementById('pf-pull').checked = truthyCron(cron.pull_commits);
    document.getElementById('pf-redeploy').checked = truthyCron(cron.redeploy);

    if (title) title.textContent = mode === 'edit' ? `编辑项目 ${project.id}` : `启用项目 ${project.id}`;
    if (ok) ok.textContent = mode === 'edit' ? '保存更改' : '保存并启用';

    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
    document.getElementById('pf-run').focus();
}

function closeProjectForm() {
    const modal = document.getElementById('project-form-modal');
    if (!modal) return;
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
}

function onProjectFormSubmit(event) {
    event.preventDefault();
    const mode = document.getElementById('pf-mode').value;
    const id = document.getElementById('pf-id').value.trim();
    const payload = {
        id,
        run_command: document.getElementById('pf-run').value.trim(),
        logs_size: document.getElementById('pf-logs').value.trim() || '10M',
        env: parseEnvText(document.getElementById('pf-env').value),
        cron: {
            restart_on: document.getElementById('pf-restart').value.trim() || '0',
            idle: document.getElementById('pf-idle').value.trim(),
            pull_commits: document.getElementById('pf-pull').checked ? 'true' : 'false',
            redeploy: document.getElementById('pf-redeploy').checked ? 'true' : 'false',
        },
    };

    const url = mode === 'edit'
        ? `/api/projects/${encodeURIComponent(id)}`
        : '/api/projects';
    const method = mode === 'edit' ? 'PUT' : 'POST';
    const okBtn = document.getElementById('project-form-ok');
    if (okBtn) okBtn.disabled = true;

    fetch(url, {
        method,
        headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
        },
        body: JSON.stringify(payload),
    })
        .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
        .then(({ ok, data }) => {
            if (!ok || data.status !== 'success') {
                alert(data.message || '保存失败');
                return;
            }
            closeProjectForm();
            loadProjects();
            setTimeout(requestStatus, 800);
            setTimeout(fetchStatusHttp, 800);
        })
        .catch(() => alert('保存失败：网络错误'))
        .finally(() => {
            if (okBtn) okBtn.disabled = false;
        });
}

function confirmUnregister(projectId) {
    showConfirm({
        title: `取消登记 ${projectId}？`,
        message: '将从 project.toml 移除该条目并卸载 s6 服务。\n\n不会删除 projects/ 下的项目文件夹。',
        okLabel: '取消登记',
        variant: 'danger',
        onConfirm: () => unregisterProject(projectId),
    });
}

function unregisterProject(projectId) {
    fetch(`/api/projects/${encodeURIComponent(projectId)}`, {
        method: 'DELETE',
        headers: { Accept: 'application/json' },
    })
        .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
        .then(({ ok, data }) => {
            if (!ok || data.status !== 'success') {
                alert(data.message || '取消登记失败');
                return;
            }
            loadProjects();
            setTimeout(requestStatus, 800);
            setTimeout(fetchStatusHttp, 800);
        })
        .catch(() => alert('取消登记失败：网络错误'));
}
