import { useState, useEffect, useRef, useCallback } from "react";
import type { SkillInfo } from "../types.ts";

interface NewTaskModalProps {
  onClose: () => void;
  onCreated: (sessionId: string) => void;
}

interface DirEntry {
  name: string;
  path: string;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function NewTaskModal({ onClose, onCreated }: NewTaskModalProps) {
  const [task, setTask] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [memory, setMemory] = useState("8g");
  const [cpus, setCpus] = useState("4");
  const [submitting, setSubmitting] = useState(false);
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [selectedSkill, setSelectedSkill] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [dragover, setDragover] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [suggestions, setSuggestions] = useState<DirEntry[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [wsDragover, setWsDragover] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const wsContainerRef = useRef<HTMLDivElement>(null);

  const fetchSuggestions = useCallback(async (prefix: string) => {
    try {
      const res = await fetch(`/api/browse?prefix=${encodeURIComponent(prefix)}`);
      if (res.ok) {
        const data: DirEntry[] = await res.json();
        setSuggestions(data);
        setShowSuggestions(data.length > 0);
        setHighlightedIndex(-1);
      }
    } catch {
      setSuggestions([]);
    }
  }, []);

  useEffect(() => {
    if (!workspace) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    let ignore = false;
    const timer = setTimeout(() => {
      if (!ignore) fetchSuggestions(workspace);
    }, 200);
    return () => { ignore = true; clearTimeout(timer); };
  }, [workspace, fetchSuggestions]);

  useEffect(() => {
    if (!workspace.trim()) {
      setSkills([]);
      setSelectedSkill("");
      return;
    }

    let ignore = false;
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/skills?workspace=${encodeURIComponent(workspace.trim())}`);
        if (res.ok && !ignore) {
          const data: SkillInfo[] = await res.json();
          setSkills(data);
          setSelectedSkill((prev) => {
            const stillExists = data.some((s) => s.name === prev);
            return stillExists ? prev : "";
          });
        }
      } catch {
        if (!ignore) setSkills([]);
      }
    }, 500);

    return () => {
      ignore = true;
      clearTimeout(timer);
    };
  }, [workspace]);

  function selectSuggestion(entry: DirEntry) {
    setWorkspace(entry.path);
    setShowSuggestions(false);
  }

  function handleWsKeyDown(e: React.KeyboardEvent) {
    if (!showSuggestions || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && highlightedIndex >= 0) {
      e.preventDefault();
      selectSuggestion(suggestions[highlightedIndex]!);
    } else if (e.key === "Escape") {
      setShowSuggestions(false);
    } else if (e.key === "Tab") {
      setShowSuggestions(false);
    }
  }

  function handleWsDrop(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setWsDragover(false);
    const items = e.dataTransfer.items;
    if (!items || items.length === 0) return;
    const entry = items[0]?.webkitGetAsEntry?.();
    if (entry?.isDirectory) {
      fetch(`/api/resolve?name=${encodeURIComponent(entry.name)}`)
        .then((res) => res.json())
        .then((results: DirEntry[]) => {
          if (results.length === 1) {
            setWorkspace(results[0]!.path);
          } else if (results.length > 1) {
            setSuggestions(results);
            setShowSuggestions(true);
          }
        })
        .catch(() => {});
    }
  }

  const activeSkill = skills.find((s) => s.name === selectedSkill);
  const taskPlaceholder = activeSkill?.argument_hint || "Build a REST API with Express...";

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files) {
      setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
      e.target.value = "";
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragover(false);
    if (e.dataTransfer.files.length > 0) {
      setFiles((prev) => [...prev, ...Array.from(e.dataTransfer.files)]);
    }
  }

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!task.trim() || !workspace.trim()) return;

    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append("task", task);
      formData.append("workspace", workspace);
      formData.append("memory", memory);
      formData.append("cpus", cpus);
      if (selectedSkill) formData.append("skill", selectedSkill);
      for (const file of files) {
        formData.append("documents", file);
      }

      const res = await fetch("/api/run", { method: "POST", body: formData });
      if (res.ok) {
        const data: { session_id: string } = await res.json();
        onCreated(data.session_id);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <h2 className="modal-title">New Task</h2>
        <form onSubmit={handleSubmit}>
          <label className="form-label" htmlFor="workspace-input">Workspace Path</label>
          <div
            ref={wsContainerRef}
            className={`ws-autocomplete${wsDragover ? " ws-dragover" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setWsDragover(true); }}
            onDragLeave={() => setWsDragover(false)}
            onDrop={handleWsDrop}
          >
            <input
              className="form-input"
              type="text"
              id="workspace-input"
              placeholder="Type a path or drop a folder here"
              value={workspace}
              onChange={(e) => setWorkspace(e.target.value)}
              onFocus={() => { if (suggestions.length > 0) setShowSuggestions(true); }}
              onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
              onKeyDown={handleWsKeyDown}
              autoComplete="off"
              required
            />
            {showSuggestions && suggestions.length > 0 && (
              <div className="ws-suggestions">
                {suggestions.map((entry, i) => (
                  <div
                    key={entry.path}
                    className={`ws-suggestion${i === highlightedIndex ? " highlighted" : ""}`}
                    onMouseDown={() => selectSuggestion(entry)}
                  >
                    <span className="ws-suggestion-name">{entry.name}</span>
                    <span className="ws-suggestion-path">{entry.path}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <label className="form-label" htmlFor="skill-select">Skill</label>
          <select
            className="form-input"
            id="skill-select"
            value={selectedSkill}
            onChange={(e) => setSelectedSkill(e.target.value)}
          >
            <option value="">None</option>
            {skills.map((skill) => (
              <option key={skill.name} value={skill.name}>{skill.name}</option>
            ))}
          </select>
          {activeSkill && (
            <div className="skill-description">{activeSkill.description}</div>
          )}

          <label className="form-label" htmlFor="task-input">Task Description</label>
          <textarea
            className="form-input form-textarea"
            id="task-input"
            rows={3}
            placeholder={taskPlaceholder}
            value={task}
            onChange={(e) => setTask(e.target.value)}
            required
          />

          <div
            className={`upload-zone${dragover ? " dragover" : ""}`}
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragover(true); }}
            onDragLeave={() => setDragover(false)}
            onDrop={handleDrop}
          >
            Drop files here or click to browse
          </div>
          <input
            type="file"
            multiple
            ref={fileInputRef}
            onChange={handleFileSelect}
            style={{ display: "none" }}
          />
          {files.length > 0 && (
            <div className="file-list">
              {files.map((file, i) => (
                <div className="file-item" key={`${file.name}-${i}`}>
                  <span className="file-name">{file.name}</span>
                  <span className="file-size">{formatFileSize(file.size)}</span>
                  <button
                    type="button"
                    className="file-remove"
                    onClick={() => removeFile(i)}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="form-row">
            <div className="form-group">
              <label className="form-label" htmlFor="memory-select">Memory</label>
              <select
                className="form-input"
                id="memory-select"
                value={memory}
                onChange={(e) => setMemory(e.target.value)}
              >
                <option value="4g">4 GB</option>
                <option value="8g">8 GB</option>
                <option value="16g">16 GB</option>
                <option value="32g">32 GB</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="cpus-select">CPUs</label>
              <select
                className="form-input"
                id="cpus-select"
                value={cpus}
                onChange={(e) => setCpus(e.target.value)}
              >
                <option value="2">2</option>
                <option value="4">4</option>
                <option value="8">8</option>
              </select>
            </div>
          </div>

          <div className="modal-actions">
            <button className="btn btn-ghost" type="button" onClick={onClose}>Cancel</button>
            <button className="btn btn-primary" type="submit" disabled={submitting}>
              {submitting ? "Starting..." : "Run Task"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
