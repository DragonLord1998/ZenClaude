from __future__ import annotations

import subprocess


def notify(title: str, message: str, sound: bool = True) -> None:
    script = f'display notification "{_escape(message)}" with title "{_escape(title)}"'
    if sound:
        script += ' sound name "Glass"'
    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass


def notify_session_complete(session_id: str, status: str, task: str) -> None:
    short_task = task[:80] + "..." if len(task) > 80 else task
    if status == "completed":
        title = "ZenClaude - Task Completed"
        message = f"Session {session_id[:15]} finished successfully.\n{short_task}"
    else:
        title = "ZenClaude - Task Failed"
        message = f"Session {session_id[:15]} failed.\n{short_task}"
    notify(title, message)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')
