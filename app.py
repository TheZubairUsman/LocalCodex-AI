from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, scrolledtext

from controller import doctor_system, run_system, scan_system


class AgentApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Local Codex Agent")
        self.root.geometry("900x650")
        self.project_path = tk.StringVar(value=str(Path(__file__).resolve().parent))
        self._build_layout()

    def _build_layout(self) -> None:
        header = tk.Frame(self.root)
        header.pack(fill="x", padx=12, pady=12)

        tk.Label(header, text="Project").pack(side="left")
        tk.Entry(header, textvariable=self.project_path).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(header, text="Browse", command=self.choose_dir).pack(side="left")
        tk.Button(header, text="Scan", command=self.scan_project).pack(side="left", padx=(8, 0))
        tk.Button(header, text="Doctor", command=self.show_doctor).pack(side="left", padx=(8, 0))

        prompt_frame = tk.Frame(self.root)
        prompt_frame.pack(fill="x", padx=12)
        tk.Label(prompt_frame, text="Task").pack(anchor="w")
        self.prompt_input = scrolledtext.ScrolledText(prompt_frame, height=8)
        self.prompt_input.pack(fill="x", pady=(4, 8))

        button_row = tk.Frame(self.root)
        button_row.pack(fill="x", padx=12)
        self.ask_button = tk.Button(button_row, text="Ask Agent", command=self.run_task, bg="#1f7a1f", fg="white")
        self.ask_button.pack(side="left")

        output_frame = tk.Frame(self.root)
        output_frame.pack(fill="both", expand=True, padx=12, pady=12)
        tk.Label(output_frame, text="Output").pack(anchor="w")
        self.output = scrolledtext.ScrolledText(output_frame)
        self.output.pack(fill="both", expand=True, pady=(4, 0))

    def choose_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.project_path.get())
        if selected:
            self.project_path.set(selected)
            self.log(f"Project: {selected}")

    def run_task(self) -> None:
        task = self.prompt_input.get("1.0", tk.END).strip()
        if not task:
            self.log("Enter a task first.")
            return

        self.ask_button.configure(state="disabled")
        self.log("Running agent...")
        thread = threading.Thread(
            target=self._run_task_worker,
            args=(task, self.project_path.get()),
            daemon=True,
        )
        thread.start()

    def _run_task_worker(self, task: str, project_path: str) -> None:
        try:
            result = run_system(task, project_path=project_path)
        except Exception as exc:
            result = f"Error: {exc}"
        self.root.after(0, lambda: self._finish_task(result))

    def _finish_task(self, result: str) -> None:
        self.ask_button.configure(state="normal")
        self.log("")
        self.log(result)
        self.log("")

    def scan_project(self) -> None:
        try:
            report = scan_system(self.project_path.get())
        except Exception as exc:
            report = f"Error: {exc}"
        self.log(report)
        self.log("")

    def show_doctor(self) -> None:
        try:
            report = doctor_system()
        except Exception as exc:
            report = f"Error: {exc}"
        self.log(report)
        self.log("")

    def log(self, message: str) -> None:
        self.output.insert(tk.END, message + "\n")
        self.output.see(tk.END)

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    AgentApp().run()
