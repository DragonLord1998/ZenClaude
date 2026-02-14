from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterator, Optional

import docker
import docker.errors
from docker.models.containers import Container

from zenclaude.models import ResourceLimits


IMAGE_TAG = "zenclaude:latest"


class DockerError(Exception):
    pass


class DockerNotAvailableError(DockerError):
    pass


class ImageBuildError(DockerError):
    pass


class ContainerError(DockerError):
    pass


def _locate_dockerfile_dir() -> Path:
    try:
        from importlib.resources import files
        pkg_path = files("zenclaude.docker")
        resolved = Path(str(pkg_path))
        if resolved.is_dir() and (resolved / "Dockerfile").exists():
            return resolved
    except (TypeError, FileNotFoundError):
        pass

    fallback = Path(__file__).parent / "docker"
    if fallback.is_dir() and (fallback / "Dockerfile").exists():
        return fallback

    raise ImageBuildError(
        "Cannot locate Dockerfile. Expected at zenclaude/docker/Dockerfile"
    )


class DockerManager:

    def __init__(self) -> None:
        try:
            self._client = docker.from_env()
            self._client.ping()
        except docker.errors.DockerException as exc:
            raise DockerNotAvailableError(
                "Docker is not available. Is Docker Desktop installed and running? "
                f"Detail: {exc}"
            ) from exc

    def build_image(self, force: bool = False) -> str:
        if not force:
            try:
                self._client.images.get(IMAGE_TAG)
                return IMAGE_TAG
            except docker.errors.ImageNotFound:
                pass

        dockerfile_dir = _locate_dockerfile_dir()

        try:
            self._client.images.build(
                path=str(dockerfile_dir),
                tag=IMAGE_TAG,
                rm=True,
                pull=False,
            )
        except docker.errors.BuildError as exc:
            log_lines = [chunk.get("stream", "") for chunk in exc.build_log]
            raise ImageBuildError(
                f"Image build failed:\n{''.join(log_lines)}"
            ) from exc
        except docker.errors.APIError as exc:
            raise ImageBuildError(f"Docker API error during build: {exc}") from exc

        return IMAGE_TAG

    def run_container(
        self,
        image: str,
        workspace: Path,
        task: str,
        claude_config: Path,
        limits: ResourceLimits,
        api_key: Optional[str] = None,
        oauth_creds: Optional[str] = None,
    ) -> str:
        workspace = workspace.resolve()
        claude_config = claude_config.resolve()

        if not workspace.is_dir():
            raise ContainerError(f"Workspace does not exist: {workspace}")
        if not claude_config.is_dir():
            raise ContainerError(f"Claude config directory does not exist: {claude_config}")

        name_hash = hashlib.sha256(
            f"{workspace}{task}".encode()
        ).hexdigest()[:8]
        container_name = f"zenclaude-{name_hash}"

        try:
            old = self._client.containers.get(container_name)
            old.remove(force=True)
        except docker.errors.NotFound:
            pass

        volumes = {
            str(workspace): {"bind": "/workspace", "mode": "rw"},
            str(claude_config): {"bind": "/home/claude/.claude-host", "mode": "ro"},
        }

        env = {"TASK": task}
        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key
        if oauth_creds:
            env["CLAUDE_OAUTH_CREDENTIALS"] = oauth_creds

        try:
            container: Container = self._client.containers.run(
                image=image,
                name=container_name,
                environment=env,
                volumes=volumes,
                mem_limit=limits.memory,
                nano_cpus=int(float(limits.cpus) * 1e9),
                pids_limit=limits.pids,
                detach=True,
                stdin_open=False,
                tty=False,
            )
        except docker.errors.APIError as exc:
            raise ContainerError(f"Failed to start container: {exc}") from exc

        return container.id

    def stop_container(self, container_id: str) -> None:
        container = self._get_container(container_id)
        try:
            container.stop(timeout=10)
        except docker.errors.APIError as exc:
            raise ContainerError(f"Failed to stop container {container_id}: {exc}") from exc

    def get_status(self, container_id: str) -> str:
        try:
            container = self._client.containers.get(container_id)
            container.reload()
        except docker.errors.NotFound:
            return "not_found"
        except docker.errors.APIError:
            return "not_found"

        status = container.status
        if status in ("running", "restarting", "paused"):
            return "running"
        return "exited"

    def get_exit_code(self, container_id: str) -> Optional[int]:
        try:
            container = self._client.containers.get(container_id)
            container.reload()
        except docker.errors.NotFound:
            return None

        if container.status == "running":
            return None

        return container.attrs["State"]["ExitCode"]

    def stream_logs(self, container_id: str, follow: bool = True) -> Iterator[str]:
        container = self._get_container(container_id)
        try:
            log_stream = container.logs(stream=True, follow=follow, timestamps=False)
            for chunk in log_stream:
                yield chunk.decode("utf-8", errors="replace")
        except docker.errors.APIError:
            return

    def remove_container(self, container_id: str) -> None:
        container = self._get_container(container_id)
        try:
            container.remove(force=True)
        except docker.errors.APIError as exc:
            raise ContainerError(
                f"Failed to remove container {container_id}: {exc}"
            ) from exc

    def _get_container(self, container_id: str) -> Container:
        try:
            return self._client.containers.get(container_id)
        except docker.errors.NotFound:
            raise ContainerError(f"Container not found: {container_id}")
        except docker.errors.APIError as exc:
            raise ContainerError(
                f"Docker API error for container {container_id}: {exc}"
            ) from exc
