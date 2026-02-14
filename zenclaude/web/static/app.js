(function () {
    "use strict";

    var sessions = [];
    var selectedSessionId = null;
    var logSocket = null;

    var sessionsList = document.getElementById("sessions-list");
    var logPanel = document.getElementById("log-panel");
    var logViewer = document.getElementById("log-viewer");
    var logTitle = document.getElementById("log-title");
    var closeLogsBtn = document.getElementById("close-logs-btn");
    var newTaskBtn = document.getElementById("new-task-btn");
    var modalOverlay = document.getElementById("modal-overlay");
    var cancelTaskBtn = document.getElementById("cancel-task-btn");
    var newTaskForm = document.getElementById("new-task-form");

    function escapeHtml(str) {
        var div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    function formatDuration(startedAt, finishedAt) {
        if (!startedAt) return "";
        var start = new Date(startedAt).getTime();
        var end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
        var seconds = Math.floor((end - start) / 1000);
        if (seconds < 0) return "0s";
        var hours = Math.floor(seconds / 3600);
        var minutes = Math.floor((seconds % 3600) / 60);
        var secs = seconds % 60;
        if (hours > 0) return hours + "h " + minutes + "m";
        if (minutes > 0) return minutes + "m " + secs + "s";
        return secs + "s";
    }

    function shortId(id) {
        if (!id) return "";
        return id.length > 15 ? id.substring(0, 15) : id;
    }

    function truncateTask(task, maxLen) {
        if (!task) return "";
        return task.length > maxLen ? task.substring(0, maxLen) + "..." : task;
    }

    function statusLabel(status) {
        var labels = {
            starting: "Starting",
            running: "Running",
            completed: "Completed",
            failed: "Failed",
            stopped: "Stopped"
        };
        return labels[status] || status;
    }

    function renderSessions() {
        if (sessions.length === 0) {
            sessionsList.innerHTML =
                '<div class="empty-state">' +
                '<div class="empty-state-title">No sessions yet</div>' +
                "Start a new task to get going." +
                "</div>";
            return;
        }

        var html = "";
        for (var i = 0; i < sessions.length; i++) {
            var s = sessions[i];
            var isSelected = s.id === selectedSessionId;
            var isActive = s.status === "running" || s.status === "starting";

            html +=
                '<div class="session-card' + (isSelected ? " selected" : "") + '" data-id="' + escapeHtml(s.id) + '">' +
                '<div class="session-card-header">' +
                '<div class="session-info">' +
                '<div class="session-task">' + escapeHtml(truncateTask(s.task, 80)) + "</div>" +
                '<div class="session-meta">' +
                '<span class="status-badge status-' + escapeHtml(s.status) + '">' +
                '<span class="status-dot"></span>' +
                statusLabel(s.status) +
                "</span>" +
                "<span>" + escapeHtml(formatDuration(s.started_at, s.finished_at)) + "</span>" +
                "<span>" + escapeHtml(shortId(s.id)) + "</span>" +
                (s.exit_code !== null && s.exit_code !== undefined ? "<span>Exit: " + escapeHtml(String(s.exit_code)) + "</span>" : "") +
                "</div>" +
                "</div>" +
                '<div class="session-actions">' +
                (isActive ? '<button class="btn btn-danger btn-sm" data-stop="' + escapeHtml(s.id) + '">Stop</button>' : "") +
                '<button class="btn btn-ghost btn-sm" data-logs="' + escapeHtml(s.id) + '">Logs</button>' +
                "</div>" +
                "</div>" +
                "</div>";
        }
        sessionsList.innerHTML = html;
    }

    function fetchSessions() {
        var xhr = new XMLHttpRequest();
        xhr.open("GET", "/api/sessions");
        xhr.onload = function () {
            if (xhr.status === 200) {
                try {
                    sessions = JSON.parse(xhr.responseText);
                } catch (e) {
                    sessions = [];
                }
                renderSessions();
            }
        };
        xhr.send();
    }

    function selectSession(id) {
        selectedSessionId = id;
        renderSessions();
        logViewer.textContent = "";
        logPanel.classList.remove("hidden");

        var session = null;
        for (var i = 0; i < sessions.length; i++) {
            if (sessions[i].id === id) {
                session = sessions[i];
                break;
            }
        }
        logTitle.textContent = session ? truncateTask(session.task, 50) : "Logs";
        connectLogSocket(id);
    }

    function closeLogPanel() {
        selectedSessionId = null;
        disconnectLogSocket();
        logPanel.classList.add("hidden");
        logViewer.textContent = "";
        renderSessions();
    }

    function connectLogSocket(sessionId) {
        disconnectLogSocket();

        var protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        var url = protocol + "//" + window.location.host + "/api/sessions/" + sessionId + "/logs";
        logSocket = new WebSocket(url);

        logSocket.onmessage = function (event) {
            logViewer.textContent += event.data;
            var isNearBottom = logViewer.scrollHeight - logViewer.scrollTop - logViewer.clientHeight < 100;
            if (isNearBottom) {
                logViewer.scrollTop = logViewer.scrollHeight;
            }
        };

        logSocket.onclose = function (event) {
            if (event.code !== 1000 && selectedSessionId === sessionId) {
                setTimeout(function () {
                    if (selectedSessionId === sessionId) {
                        connectLogSocket(sessionId);
                    }
                }, 2000);
            }
        };

        logSocket.onerror = function () {};
    }

    function disconnectLogSocket() {
        if (logSocket) {
            logSocket.onclose = null;
            logSocket.close();
            logSocket = null;
        }
    }

    function stopSession(id) {
        var xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/sessions/" + id + "/stop");
        xhr.setRequestHeader("Content-Type", "application/json");
        xhr.onload = function () {
            fetchSessions();
        };
        xhr.send();
    }

    function showModal() {
        modalOverlay.classList.remove("hidden");
        document.getElementById("task-input").focus();
    }

    function hideModal() {
        modalOverlay.classList.add("hidden");
        newTaskForm.reset();
    }

    function submitNewTask(event) {
        event.preventDefault();

        var task = document.getElementById("task-input").value.trim();
        var workspace = document.getElementById("workspace-input").value.trim();
        var memory = document.getElementById("memory-select").value;
        var cpus = document.getElementById("cpus-select").value;

        if (!task || !workspace) return;

        var payload = JSON.stringify({
            task: task,
            workspace: workspace,
            memory: memory,
            cpus: cpus
        });

        var xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/run");
        xhr.setRequestHeader("Content-Type", "application/json");
        xhr.onload = function () {
            if (xhr.status === 200) {
                hideModal();
                fetchSessions();
            }
        };
        xhr.send(payload);
    }

    sessionsList.addEventListener("click", function (event) {
        var target = event.target;

        var stopId = target.getAttribute("data-stop");
        if (stopId) {
            event.stopPropagation();
            stopSession(stopId);
            return;
        }

        var logsId = target.getAttribute("data-logs");
        if (logsId) {
            event.stopPropagation();
            selectSession(logsId);
            return;
        }

        var card = target.closest(".session-card");
        if (card) {
            selectSession(card.getAttribute("data-id"));
        }
    });

    closeLogsBtn.addEventListener("click", closeLogPanel);
    newTaskBtn.addEventListener("click", showModal);
    cancelTaskBtn.addEventListener("click", hideModal);
    newTaskForm.addEventListener("submit", submitNewTask);

    modalOverlay.addEventListener("click", function (event) {
        if (event.target === modalOverlay) {
            hideModal();
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            if (!modalOverlay.classList.contains("hidden")) {
                hideModal();
            } else if (!logPanel.classList.contains("hidden")) {
                closeLogPanel();
            }
        }
    });

    fetchSessions();
    setInterval(fetchSessions, 5000);
})();
