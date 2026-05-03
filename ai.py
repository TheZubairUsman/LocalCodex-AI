#!/usr/bin/env python3
"""
AI Agent v4.0 — Clean, Claude-style local coding assistant
Works with Ollama (Mistral · CodeLlama · Phi3)
"""

import os, sys, json, re, shutil, subprocess, tempfile, time, threading
import textwrap, glob as globmod
from pathlib import Path
from datetime import datetime

# ─── readline (optional — gracefully skip on Windows if missing) ──────────────
try:
    import readline
    HAS_READLINE = True
except ImportError:
    HAS_READLINE = False

# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
CONFIG_FILE = Path.home() / ".ai_agent_config.json"
DEFAULT_CFG = {
    "model":       "auto",
    "directory":   str(Path.home()),
    "timeout":     540,
    "ram_limit":   78,
    "auto_save":   True,
    "stream_feel": True,
    "history_max": 20,
}

def load_config():
    if CONFIG_FILE.exists():
        try:
            d = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return {**DEFAULT_CFG, **d}
        except: pass
    return DEFAULT_CFG.copy()

def save_config(cfg):
    try:
        CONFIG_FILE.write_text(
            json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except: pass

CFG = load_config()

# ═══════════════════════════════════════════════════════════════════════════════
#  MODELS
# ═══════════════════════════════════════════════════════════════════════════════
MODELS = {
    "code": "codellama:7b", "debug": "codellama:7b",
    "fix":  "codellama:7b", "refactor": "codellama:7b",
    "test": "codellama:7b", "design": "mistral",
    "research": "mistral",  "explain": "mistral",
    "write": "mistral",     "analyze": "mistral",
    "general": "phi3",      "light": "phi3", "chat": "phi3",
}

# ═══════════════════════════════════════════════════════════════════════════════
#  COLORS
# ═══════════════════════════════════════════════════════════════════════════════
R = "\033[0m"
C = {
    "cyan":    "\033[96m",
    "green":   "\033[92m",
    "yellow":  "\033[93m",
    "red":     "\033[91m",
    "blue":    "\033[94m",
    "dim":     "\033[2m",
    "bold":    "\033[1m",
    "magenta": "\033[95m",
    "white":   "\033[97m",
}

def col(name, text): return f"{C.get(name,'')}{text}{R}"
def bold(x):         return f"{C['bold']}{x}{R}"
def dim(x):          return f"{C['dim']}{x}{R}"

# ═══════════════════════════════════════════════════════════════════════════════
#  SYSTEM  (RAM / model picker)
# ═══════════════════════════════════════════════════════════════════════════════
def get_ram():
    try:
        import psutil
        return psutil.virtual_memory().percent
    except:
        try:
            r = subprocess.run(
                ["powershell","-Command",
                 "(Get-Process|Measure-Object WorkingSet -Sum).Sum/1GB"],
                capture_output=True, text=True, timeout=5)
            used = float(r.stdout.strip())
            return round((used / 16) * 100, 1)
        except:
            return 50

def pick_model(task):
    forced = CFG.get("model", "auto")
    if forced != "auto":
        return forced
    ram = get_ram()
    if ram > CFG.get("ram_limit", 78):
        print(col("yellow", f"  ⚡ RAM {ram:.0f}% — switching to phi3"))
        return MODELS["light"]
    return MODELS.get(task, MODELS["general"])

# ═══════════════════════════════════════════════════════════════════════════════
#  SPINNER
# ═══════════════════════════════════════════════════════════════════════════════
FRAMES = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

def spinner_start(msg="Thinking"):
    ev = threading.Event()
    def _run():
        i = 0
        while not ev.is_set():
            sys.stdout.write(f"\r  {col('magenta', FRAMES[i%len(FRAMES)])} "
                             f"{dim(msg + '...')}   ")
            sys.stdout.flush()
            time.sleep(0.1); i += 1
        sys.stdout.write("\r" + " "*55 + "\r")
        sys.stdout.flush()
    threading.Thread(target=_run, daemon=True).start()
    return ev

def spinner_stop(ev):
    ev.set(); time.sleep(0.15)

# ═══════════════════════════════════════════════════════════════════════════════
#  OLLAMA  (fixed stdin pipe — solves "Enter not working" issue)
# ═══════════════════════════════════════════════════════════════════════════════
SPIN_MSG = {
    "code":"Writing code","debug":"Finding bugs","fix":"Fixing code",
    "refactor":"Refactoring","test":"Writing tests","design":"Designing",
    "research":"Researching","explain":"Explaining","analyze":"Analyzing",
    "write":"Writing",
}

def run_ollama(model, prompt, task="general"):
    timeout = CFG.get("timeout", 540)

    # Write prompt to temp file — avoids all stdin pipe issues on Windows
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.txt', encoding='utf-8', delete=False)
    tmp.write(prompt)
    tmp.close()

    ev = spinner_start(SPIN_MSG.get(task, "Thinking"))
    try:
        if sys.platform == "win32":
            # Use cmd /c so the pipe works properly in Windows terminal
            cmd = f'cmd /c type "{tmp.name}" | ollama run {model}'
            r = subprocess.run(
                cmd, shell=True, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=timeout)
        else:
            with open(tmp.name, 'r', encoding='utf-8') as f:
                r = subprocess.run(
                    ["ollama", "run", model], stdin=f,
                    capture_output=True, text=True,
                    encoding='utf-8', errors='replace', timeout=timeout)

        spinner_stop(ev)

        if r.returncode != 0 and r.stderr:
            e = r.stderr.strip()
            if "not found" in e.lower() or "unknown model" in e.lower():
                return (f"❌  Model '{model}' not found.\n"
                        f"    Run: ollama pull {model}")
            return f"❌  {e[:300]}"

        out = r.stdout.strip()
        return out if out else "⚠️  No response from model."

    except subprocess.TimeoutExpired:
        spinner_stop(ev)
        return (f"⏱  Timeout ({timeout}s).\n"
                f"    Try: /set timeout 900  or  /set model phi3")
    except FileNotFoundError:
        spinner_stop(ev)
        return "❌  'ollama' not found. Install: https://ollama.com/download"
    except Exception as ex:
        spinner_stop(ev)
        return f"❌  {type(ex).__name__}: {ex}"
    finally:
        try: os.unlink(tmp.name)
        except: pass

# ═══════════════════════════════════════════════════════════════════════════════
#  FILE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
SKIP_DIRS  = {'.git','__pycache__','node_modules','.venv','venv',
              'dist','build','.idea','.next','.nuxt','coverage'}
TEXT_EXTS  = {'.py','.js','.ts','.jsx','.tsx','.java','.c','.cpp',
              '.cs','.go','.rs','.rb','.php','.swift','.kt','.html',
              '.css','.scss','.json','.yaml','.yml','.toml','.ini',
              '.cfg','.txt','.md','.rst','.xml','.sql','.sh','.bat','.env'}
FILE_ICONS = {"py":"🐍","js":"📜","ts":"📘","json":"📋","md":"📝",
              "html":"🌐","css":"🎨","sql":"🗄️"}

def dir_tree(path, max_f=60):
    p = Path(path)
    if not p.exists(): return f"[Not found: {path}]"
    lines = [f"📁 {path}"]
    n = 0
    for item in sorted(p.rglob("*")):
        if item.is_file() and not any(s in item.parts for s in SKIP_DIRS):
            rel  = item.relative_to(p)
            sz   = item.stat().st_size
            icon = FILE_ICONS.get(item.suffix.lstrip("."), "📄")
            lines.append(f"  {icon} {rel}  {dim(f'({sz:,}B)')}")
            n += 1
            if n >= max_f:
                lines.append(f"  {dim('... and more')}"); break
    return "\n".join(lines)

def read_file(fp, max_chars=4000):
    try:
        p = Path(fp)
        if not p.exists(): return f"[File not found: {fp}]"
        if p.suffix.lower() not in TEXT_EXTS and p.stat().st_size > 60_000:
            return f"[Binary/large file skipped]"
        with open(fp, 'r', encoding='utf-8', errors='replace') as f:
            d = f.read(max_chars)
        return d + (f"\n{dim('... [truncated]')}" if len(d) == max_chars else "")
    except Exception as e:
        return f"[Read error: {e}]"

def write_file(path, content):
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        print(col("red", f"  ✗ Write error: {e}")); return False

def backup_file(fp):
    src = Path(fp)
    if src.exists():
        bak = str(fp) + f".bak_{datetime.now().strftime('%H%M%S')}"
        shutil.copy(fp, bak)
        print(dim(f"  📋 Backup → {bak}"))

def project_ctx(directory, max_files=10, max_chars=1600):
    p = Path(directory)
    if not p.exists(): return "[Dir not found]"
    prio = []
    for pat in ['README*','main.*','app.*','index.*','*.json',
                '*.yaml','*.toml','*.py','*.js','*.ts','*.md']:
        for f in sorted(p.glob(pat)):
            if f.is_file() and f not in prio: prio.append(f)
        for f in sorted(p.rglob(pat)):
            if f.is_file() and f not in prio:
                if not any(s in f.parts for s in SKIP_DIRS): prio.append(f)
    parts, seen, n = [], set(), 0
    for f in prio:
        if n >= max_files: break
        k = str(f)
        if k in seen: continue
        seen.add(k); n += 1
        parts.append(f"=== {f.relative_to(p)} ===\n{read_file(f, max_chars)}")
    return "\n\n".join(parts)

# ═══════════════════════════════════════════════════════════════════════════════
#  CODE SAVE
# ═══════════════════════════════════════════════════════════════════════════════
def extract_code(text):
    return re.findall(r'```(?:\w+)?\n(.*?)```', text, re.DOTALL)

def smart_filename(code, index, lang_hint="py"):
    """
    Derive a meaningful filename from code content.
    Priority:
      1. Explicit  # filename: xyz.py  comment anywhere in file
      2. Class/module name  (e.g. class MuseumApp → museum_app.py)
      3. Framework / pattern fingerprints
      4. First top-level def name
      5. Short descriptive fallback — never generic output_N
    """
    # ── 1. Explicit comment ──────────────────────────────────────────────────
    for line in code.splitlines():
        m = re.search(r'#\s*(?:filename?|file|save\s*as)\s*[:\-]?\s*(\S+\.\w+)',
                      line, re.IGNORECASE)
        if m:
            return m.group(1).strip()

    # Detect language from shebang / content
    ext = ".py"
    if code.lstrip().startswith("<!DOCTYPE") or "<html" in code[:200].lower():
        ext = ".html"
    elif code.lstrip().startswith("{") or code.lstrip().startswith("["):
        ext = ".json"
    elif re.search(r'^(SELECT|INSERT|UPDATE|CREATE|DROP)\b', code, re.I | re.M):
        ext = ".sql"
    elif re.search(r'^(#!/bin/bash|#!/bin/sh)', code):
        ext = ".sh"

    # ── 2. Top-level class name → snake_case filename ───────────────────────
    cls = re.search(r'^class\s+([A-Z][A-Za-z0-9]+)', code, re.M)
    if cls:
        name = re.sub(r'(?<!^)(?=[A-Z])', '_', cls.group(1)).lower()
        return f"{name}{ext}"

    # ── 3. Framework / pattern fingerprints ─────────────────────────────────
    c = code.lower()
    if "qmainwindow" in code or "pyqt5" in code or "pyqt6" in code:
        return f"gui_pyqt{ext}"
    if re.search(r'tk\.tk\b|from tkinter|import tkinter', c):
        return f"gui_tkinter{ext}"
    if "flask" in c and ("@app.route" in c or "Flask(__name__)" in c):
        return f"server_flask{ext}"
    if "fastapi" in c:
        return f"server_fastapi{ext}"
    if "django" in c:
        return f"django_app{ext}"
    if "pytest" in c or ("import unittest" in c and "def test_" in c):
        # Try to find what is being tested
        m = re.search(r'(?:test_|Test)([A-Za-z0-9_]+)', code)
        subject = f"_{m.group(1).lower()}" if m else ""
        return f"test{subject}{ext}"
    if "argparse" in c and "def main" in c:
        return f"cli_tool{ext}"
    if re.search(r'pandas|numpy|matplotlib|seaborn|sklearn', c):
        return f"data_analysis{ext}"
    if re.search(r'socket\.socket|asyncio\.start_server', c):
        return f"network_server{ext}"
    if "sqlite3" in c or "sqlalchemy" in c:
        return f"database{ext}"
    if re.search(r'requests\.|httpx\.|aiohttp', c):
        return f"api_client{ext}"
    if re.search(r'setup\(|setuptools|pyproject', c):
        return f"setup{ext}"
    if "__init__" in code and "self." in code and ext == ".py":
        pass  # fall through to def-name detection

    # ── 4. First meaningful top-level function name ──────────────────────────
    for line in code.splitlines():
        m = re.match(r'^def\s+([a-z][a-z0-9_]+)\s*\(', line)
        if m and m.group(1) not in ("main", "run", "start", "init"):
            name = m.group(1).rstrip("_")
            return f"{name}{ext}"

    # ── 5. Last resort: short descriptive name (never output_N) ─────────────
    # Count what kind of code it is
    has_class  = bool(re.search(r'^class\s+', code, re.M))
    has_def    = bool(re.search(r'^def\s+',   code, re.M))
    line_count = len(code.splitlines())

    if has_class and has_def:
        return f"module_{index}{ext}"
    if has_def:
        return f"functions_{index}{ext}"
    return f"script_{index}{ext}"

def save_code(text, save_dir, verbose=True):
    """
    Extract all code blocks from AI response and save each as a
    meaningful, content-named file.  Skips shell snippets and
    incomplete fragments automatically.
    """
    blocks  = extract_code(text)
    saved   = []
    skipped = []

    for i, code in enumerate(blocks, 1):
        code       = code.strip()
        first_line = code.splitlines()[0].strip() if code else ""

        # ── Detect language hint from fence (```python, ```bash, etc.) ───────
        # extract_code strips the fence tag — re-scan original text
        fence_langs = re.findall(r'```(\w+)\n', text)
        lang_hint   = fence_langs[i - 1] if i - 1 < len(fence_langs) else "py"

        # ── Skip: too short to be a real file ────────────────────────────────
        if len(code) < 80:
            skipped.append(f"block #{i} (too short: {len(code)} chars)")
            continue

        # ── Skip: shell / command blocks ─────────────────────────────────────
        SHELL_STARTS = ("pip ", "pip3 ", "pyinstaller", "npm ", "yarn ",
                        "cd ", "mkdir ", "$ ", "# install", "python -m",
                        "python3 -m", "conda ", "brew ", "apt ", "apt-get ")
        if any(first_line.lower().startswith(s) for s in SHELL_STARTS):
            skipped.append(f"block #{i} (shell commands — not a source file)")
            continue

        # ── Detect extension from fence lang ─────────────────────────────────
        LANG_EXT = {
            "python":"py","py":"py","javascript":"js","js":"js",
            "typescript":"ts","ts":"ts","html":"html","css":"css",
            "json":"json","sql":"sql","bash":"sh","shell":"sh",
            "sh":"sh","yaml":"yml","yml":"yml","toml":"toml",
            "java":"java","go":"go","rust":"rs","cpp":"cpp","c":"c",
        }
        ext = LANG_EXT.get(lang_hint.lower(), "py")

        fname = smart_filename(code, i, ext)
        fpath = Path(save_dir) / fname

        if write_file(fpath, code):
            saved.append(str(fpath))
            if verbose:
                lines = len(code.splitlines())
                size  = len(code.encode())
                print(col("green",
                    f"  ✅ Saved → {fname}  "
                    f"{dim(f'({lines} lines, {size:,} bytes)')}"))

    # ── Summary of skipped blocks ─────────────────────────────────────────────
    if skipped and verbose:
        for s in skipped:
            print(dim(f"  ⏭  Skipped {s}"))

    # ── If nothing was saved, preserve full response as .txt ──────────────────
    if not saved:
        ref = Path(save_dir) / f"ai_response_{datetime.now().strftime('%H%M%S')}.txt"
        write_file(ref, text)
        if verbose:
            print(col("yellow",
                f"  💾 No code blocks found — full response saved → {ref.name}"))
        saved.append(str(ref))

    return saved

# ═══════════════════════════════════════════════════════════════════════════════
#  SYSTEM PROMPTS  (AI ko clean instructions — better responses)
# ═══════════════════════════════════════════════════════════════════════════════
SYS = {
"code": """\
You are an expert software engineer.
- Write COMPLETE, RUNNABLE code. No placeholders. No TODOs.
- The VERY FIRST LINE must be: # filename: meaningful_name.py
  (Use a descriptive name based on what the code does, not "main.py" or "output.py")
- Include ALL imports at the top.
- Add brief comments for complex logic.
- Prefer standard library unless asked otherwise.
- Wrap code in ```python ... ``` fences.""",

"debug": """\
You are an expert debugger.
- State ROOT CAUSE first (1-2 sentences).
- Show exact fix with line numbers and context.
- Explain WHY it was broken.
- Provide complete corrected code block.""",

"fix": """\
You are an expert code fixer.
- Fix ALL bugs you find.
- Start fixed file with: # filename: <same name>
- Return COMPLETE fixed file — not just changed lines.
- List what you fixed at the end.""",

"refactor": """\
You are a senior code reviewer.
- Improve: readability, performance, structure, naming.
- Apply SOLID principles where sensible.
- Show what changed and why.
- Return COMPLETE refactored file starting with: # filename: <n>""",

"test": """\
You are a QA engineer.
- Write comprehensive pytest unit tests.
- Cover: happy path, edge cases, exceptions.
- Each test has a clear docstring.
- Start file with: # filename: test_<n>.py
- Mock external dependencies.""",

"design": """\
You are a senior software architect. You MUST produce COMPLETE, RUNNABLE code.

STRICT RULES — follow exactly:
- Do NOT write partial snippets, stubs, or "# rest of code here"
- Do NOT use TODOs or placeholders
- Every code block must be a complete, working file
- The VERY FIRST LINE of every code block must be: # filename: descriptive_name.py
  Use a meaningful name e.g. museum_ticket_system.py, not main.py or output.py
- All imports at the top of each file
- Wrap ALL code in triple-backtick fences with language tag: ```python

STEPS:
1. Project summary (3 sentences max).
2. Framework choice with reason (prefer Tkinter — zero pip install).
3. Complete implementation — one full working file, no shortcuts.
4. Exact run commands.
5. Exact PyInstaller .exe packaging commands.""",

"explain": """\
You are a patient, expert teacher.
- Explain clearly, as if to a smart beginner.
- Use analogies and real examples.
- Show code examples where helpful.
- Structure: concept → example → when to use → pitfalls.""",

"research": """\
You are a research analyst.
- Summarize key findings clearly.
- Use bullet points for facts.
- Note conflicting information if any.
- Give a 1-sentence conclusion at the end.""",

"write": """\
You are a professional technical writer.
- Write clearly and concisely.
- Use headers and structure where helpful.
- Be accurate, complete, and professional.""",

"analyze": """\
You are a senior software architect doing code review.
- Summarize what the project does (3-5 sentences).
- List main components and their roles.
- Identify issues, missing parts, and improvements.
- Suggest the best approach to complete/fix it.""",
}

# ═══════════════════════════════════════════════════════════════════════════════
#  TASK DETECTION
# ═══════════════════════════════════════════════════════════════════════════════
TASK_MAP = {
    "debug":    ["debug","error","traceback","exception","crash","not working",
                 "fails","broken","wrong output","kyu nahi","kaam nahi"],
    "fix":      ["fix","repair","correct","resolve","patch","theek karo"],
    "refactor": ["refactor","improve","clean","optimize","restructure",
                 "rewrite","simplify","behtar karo"],
    "code":     ["write","create","build","implement","make","generate",
                 "code karo","bana","script","function","class","program"],
    "test":     ["test","unittest","pytest","coverage","testing"],
    "design":   ["design","architect","system","structure","plan","schema"],
    "analyze":  ["analyze","analyse","review","examine","inspect",
                 "summarize","what does","kya karta"],
    "research": ["research","search","find","latest","what is","how does",
                 "compare","vs","best","recommend","dhundo"],
    "explain":  ["explain","how","why","understand","teach","learn",
                 "difference","samjhao","kya hota","kaise"],
    "write":    ["write doc","readme","report","documentation","draft"],
}

def detect_task(text):
    p = text.lower()
    scores = {task: sum(1 for kw in kws if kw in p)
              for task, kws in TASK_MAP.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"

# ═══════════════════════════════════════════════════════════════════════════════
#  WEB SEARCH
# ═══════════════════════════════════════════════════════════════════════════════
def web_search(query, n=5):
    try:
        from urllib.request import urlopen, Request
        from urllib.parse   import quote_plus
        import html as h
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        req = Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urlopen(req, timeout=12) as resp:
            ct = resp.read().decode('utf-8', errors='replace')
        snips  = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', ct, re.DOTALL)
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', ct, re.DOTALL)
        links  = re.findall(r'class="result__url"[^>]*>(.*?)</span>', ct, re.DOTALL)
        out = []
        for i in range(min(n, len(snips))):
            ti = h.unescape(re.sub(r'<[^>]+>','', titles[i] if i<len(titles) else "")).strip()
            sn = h.unescape(re.sub(r'<[^>]+>','', snips[i])).strip()
            li = links[i].strip() if i < len(links) else ""
            if sn: out.append(f"• {ti}\n  {sn}\n  {li}")
        return "\n\n".join(out) if out else "No results found."
    except Exception as e:
        return f"[Search error: {e}]"

# ═══════════════════════════════════════════════════════════════════════════════
#  PROMPT BUILDER
# ═══════════════════════════════════════════════════════════════════════════════
def is_detailed_prompt(text):
    """
    Detect if the user wrote a detailed custom prompt.
    If yes, trust the user's prompt as-is — don't prepend agent system prompt.
    """
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if len(lines) >= 4:
        return True
    keywords = ["step","task","rule","requirement","format","output","implement",
                "STEP","TASK","RULE","REQUIREMENT","FORMAT","OUTPUT","IMPLEMENT"]
    return sum(1 for k in keywords if k in text) >= 2

def build_prompt(task, user_msg, cdir, hist, file_ctx="", dir_ctx=""):
    hist_t = ""
    if hist:
        hist_t = "Conversation so far:\n"
        for h in hist[-6:]:
            role = "User" if h["role"] == "user" else "Agent"
            hist_t += f"{role}: {h['content'][:300]}\n"
        hist_t += "\n"

    if is_detailed_prompt(user_msg):
        # User wrote a full custom prompt — inject context but keep their instructions
        context_block = ""
        if dir_ctx:
            context_block += dir_ctx
        if file_ctx:
            context_block += file_ctx
        return f"{hist_t}{context_block}\n{user_msg}\n\nRespond directly and completely."
    else:
        # Short/natural message — prepend agent system prompt
        sys_p = SYS.get(task, "You are a helpful AI assistant. Be specific and accurate.")
        return f"{sys_p}\n\n{hist_t}{dir_ctx}{file_ctx}User: {user_msg}\n\nRespond directly and completely."

def extract_paths(text):
    r"""
    Extract all file/directory paths from a prompt.
    Handles:
      - Windows absolute paths  e.g.  E:\study\MSDT\Assignment_1
      - Unix absolute paths     e.g.  /home/user/project
      - Quoted paths            e.g.  "C:\My Folder"
      - Relative paths          e.g.  myproject/
    """
    found = []

    # 1. Quoted paths (may contain spaces)
    for m in re.finditer(r'["\']([A-Za-z]:[\\\/][^"\']+|\/[^"\']+)["\']', text):
        found.append(m.group(1))

    # 2. Windows absolute  e.g.  E:\study\MSDT\Assignment_1
    for m in re.finditer(r'\b([A-Za-z]:[/\\][^ \t,;"\']+)', text):
        p = m.group(1).rstrip(r'\/.,;')
        if p not in found:
            found.append(p)

    # 3. Unix absolute  e.g.  /home/user/project
    for m in re.finditer(r'(?<!\w)(\/[^ \t,;"\'\n]+)', text):
        p = m.group(1).rstrip('/.,;')
        if p not in found:
            found.append(p)

    # 4. Unquoted tokens that look like relative paths
    for tok in text.split():
        tok = tok.strip('"\'.,;')
        if ('/' in tok or '\\' in tok) and tok not in found:
            found.append(tok)

    return found

def auto_context(user_msg, cdir):
    """
    Scan the user's prompt for any real file or directory paths.
    Load and inject their content so the AI has full context.
    """
    file_ctx = dir_ctx = ""

    candidates = extract_paths(user_msg)

    for raw in candidates:
        # Try as-is first, then relative to cdir
        for p in [Path(raw), Path(cdir) / raw]:
            try:
                if p.is_file() and p.suffix in TEXT_EXTS:
                    print(dim(f"  📄 Auto-loading file : {p}"))
                    file_ctx += f"\n=== File: {p.name} ===\n```\n{read_file(str(p), 3500)}\n```\n"
                    break
                if p.is_dir():
                    print(dim(f"  📂 Auto-loading dir  : {p}"))
                    dir_ctx = (f"\n=== Project Directory: {p} ===\n"
                               f"{dir_tree(str(p))}\n\n"
                               f"=== Key File Contents ===\n"
                               f"{project_ctx(str(p))}\n")
                    break
            except Exception:
                continue

    # Keyword fallback — "this project / mera folder" etc.
    if not dir_ctx and not file_ctx:
        kws = ["this project","my project","this folder","this code",
               "is project","mera project","is folder","current dir"]
        if any(k in user_msg.lower() for k in kws):
            print(dim(f"  📂 Auto-loading current dir: {cdir}"))
            dir_ctx = (f"\n=== Project Directory: {cdir} ===\n"
                       f"{dir_tree(cdir)}\n\n"
                       f"=== Key File Contents ===\n"
                       f"{project_ctx(cdir)}\n")

    return file_ctx, dir_ctx

# ═══════════════════════════════════════════════════════════════════════════════
#  WORKFLOWS
# ═══════════════════════════════════════════════════════════════════════════════
def wf_build(path, extra, cdir):
    model = pick_model("design")
    print(col("cyan", f"\n  🔨 Building: {path}"))
    tree  = dir_tree(path)
    ctx   = project_ctx(path)
    instr = extra or """\
You are a senior software engineer and architect. Complete ALL steps:

STEP 1 — ANALYSIS (5 lines max)
What does this project do? What components exist? What's missing?

STEP 2 — DESIGN (5 lines max)
Framework choice (prefer Tkinter — zero install). Architecture layers.

STEP 3 — COMPLETE CODE
Write full, runnable implementation.
- Start with: # filename: main_gui.py
- All imports included
- No placeholders or TODOs

STEP 4 — RUN INSTRUCTIONS
Exact pip installs + run command.

STEP 5 — EXE PACKAGING
pip install pyinstaller
pyinstaller --onefile --windowed main_gui.py"""
    prompt = f"{instr}\n\n=== STRUCTURE ===\n{tree}\n\n=== FILES ===\n{ctx}\n\nComplete all steps."
    resp   = run_ollama(model, prompt, "design")
    if CFG.get("auto_save") and "```" in resp:
        save_code(resp, path)
    return resp

def wf_fix(fp, issue, cdir):
    model   = pick_model("fix")
    content = read_file(fp, 5000)
    fname   = Path(fp).name
    prompt  = (f"{SYS['fix']}\n\nFile: {fp}\n"
               f"Issue: {issue or 'Find and fix ALL bugs'}\n\n"
               f"Code:\n```python\n{content}\n```\n\n"
               f"Return COMPLETE fixed file starting with: # filename: {fname}")
    resp   = run_ollama(model, prompt, "fix")
    blocks = extract_code(resp)
    if blocks:
        backup_file(fp)
        write_file(fp, blocks[0].strip())
        print(col("green", f"  ✅ Fixed and saved: {fp}"))
    return resp

def wf_add(fp, feature, cdir):
    model   = pick_model("code")
    content = read_file(fp, 4000)
    fname   = Path(fp).name
    prompt  = (f"{SYS['code']}\n\nExisting file ({fp}):\n```python\n{content}\n```\n\n"
               f"Add this feature: {feature}\n\n"
               f"Return COMPLETE updated file starting with: # filename: {fname}\n"
               f"Keep ALL existing functionality.")
    resp   = run_ollama(model, prompt, "code")
    blocks = extract_code(resp)
    if blocks:
        backup_file(fp)
        write_file(fp, blocks[0].strip())
        print(col("green", f"  ✅ Feature added: {fp}"))
    return resp

def wf_refactor(fp, cdir):
    model   = pick_model("refactor")
    content = read_file(fp, 4000)
    fname   = Path(fp).name
    prompt  = (f"{SYS['refactor']}\n\nFile:\n```python\n{content}\n```\n\n"
               f"Return COMPLETE refactored file: # filename: {fname}")
    resp   = run_ollama(model, prompt, "refactor")
    blocks = extract_code(resp)
    if blocks:
        backup_file(fp)
        write_file(fp, blocks[0].strip())
        print(col("green", f"  ✅ Refactored: {fp}"))
    return resp

def wf_test(fp, cdir):
    model   = pick_model("test")
    content = read_file(fp, 4000)
    tname   = f"test_{Path(fp).stem}.py"
    tpath   = Path(fp).parent / tname
    prompt  = (f"{SYS['test']}\n\nCode:\n```python\n{content}\n```\n\n"
               f"# filename: {tname}")
    resp   = run_ollama(model, prompt, "test")
    blocks = extract_code(resp)
    if blocks:
        write_file(tpath, blocks[0].strip())
        print(col("green", f"  ✅ Tests saved: {tpath}"))
    return resp

def wf_explain(fp, cdir):
    model   = pick_model("explain")
    content = read_file(fp, 4000)
    prompt  = f"{SYS['explain']}\n\nExplain this code:\n```\n{content}\n```"
    return run_ollama(model, prompt, "explain")

def wf_research(query):
    model   = pick_model("research")
    print(dim(f"  🔍 Searching: {query}"))
    results = web_search(query)
    prompt  = (f"{SYS['research']}\n\nQuery: {query}\n\n"
               f"Search results:\n{results}\n\nProvide a clear summary.")
    return run_ollama(model, prompt, "research")

def wf_run(fp, cdir):
    fp = str(Path(cdir)/fp) if not Path(fp).is_absolute() else fp
    print(col("blue", f"  ▶ Running: {fp}"))
    try:
        r = subprocess.run(
            [sys.executable, fp], capture_output=True,
            text=True, timeout=60, cwd=str(Path(fp).parent))
        if r.stdout.strip(): print(col("green", r.stdout.strip()))
        if r.stderr.strip(): print(col("red",   r.stderr.strip()))
        if not r.stdout.strip() and not r.stderr.strip():
            print(dim("  (no output)"))
    except subprocess.TimeoutExpired:
        print(col("red","  Timeout (60s)"))
    except Exception as e:
        print(col("red", f"  Error: {e}"))

# ═══════════════════════════════════════════════════════════════════════════════
#  RESPONSE PRINTER  (syntax-aware, clean)
# ═══════════════════════════════════════════════════════════════════════════════
def print_response(resp):
    print()
    print(col("cyan", "  ┌─ AI ─────────────────────────────────────────────────────────┐"))

    in_code = False
    for line in resp.split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
            print(dim("  │  " + line))
            continue
        if in_code:
            # Light syntax highlighting
            c_line = line
            c_line = re.sub(
                r'\b(def|class|return|import|from|if|else|elif|for|while|'
                r'try|except|with|as|in|not|and|or|True|False|None|pass|'
                r'break|continue|yield|lambda|async|await)\b',
                lambda m: col("blue", m.group()), c_line)
            c_line = re.sub(r'(""".*?"""|\'\'\'.*?\'\'\'|".*?"|\'.*?\')',
                            lambda m: col("yellow", m.group()), c_line)
            if "#" in c_line:
                idx = c_line.index("#")
                c_line = c_line[:idx] + dim(c_line[idx:])
            print("  │  " + c_line)
        else:
            if re.match(r'^#{1,3}\s', line):
                print(col("cyan", "  │  " + bold(line)))
            elif re.match(r'^\s*[-•*]\s', line):
                print(col("green", "  │  " + line))
            elif re.match(r'^\s*\d+\.\s', line):
                print(col("magenta", "  │  " + line))
            elif not line.strip():
                print("  │")
            else:
                wrapped = textwrap.fill(line, width=70,
                                        initial_indent="  │  ",
                                        subsequent_indent="  │    ")
                print(wrapped)

    print(col("cyan", "  └──────────────────────────────────────────────────────────────┘"))
    print()

# ═══════════════════════════════════════════════════════════════════════════════
#  TAB COMPLETION
# ═══════════════════════════════════════════════════════════════════════════════
COMMANDS = [
    "/build","/analyze","/ask","/fix","/add","/refactor",
    "/test","/explain","/run","/read","/research",
    "/dir","/model","/set","/models","/status",
    "/save","/clear","/help","/exit",
]

def completer(text, state):
    options = []
    if text.startswith("/"):
        options = [c for c in COMMANDS if c.startswith(text)]
    else:
        try:
            cdir    = CFG.get("directory",".")
            pattern = os.path.join(cdir, text + "*")
            options = [os.path.basename(o) for o in globmod.glob(pattern)]
        except: pass
    try: return options[state]
    except IndexError: return None

if HAS_READLINE:
    try:
        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")
        readline.set_completer_delims(" \t\n")
    except: pass

# ═══════════════════════════════════════════════════════════════════════════════
#  INPUT  — fixed for Windows (no readline dependency for basic Enter)
# ═══════════════════════════════════════════════════════════════════════════════
def _read_one_line(prompt_str):
    """Write prompt then read exactly one raw line from stdin."""
    sys.stdout.write(prompt_str)
    sys.stdout.flush()
    try:
        line = sys.stdin.readline()
        if line == "":          # EOF / Ctrl-Z on Windows
            return None
        return line.rstrip("\r\n")
    except (KeyboardInterrupt, EOFError):
        return None

def _drain_stdin_lines():
    """
    Drain any lines already buffered in stdin (happens on Windows paste).
    Works on both Windows and Unix without select/msvcrt tricks.

    Strategy: after reading the first line we set a very short non-blocking
    read window. If more data arrives within ~80 ms we collect it; otherwise
    we stop. This perfectly catches paste (all lines arrive instantly) while
    not blocking normal single-line typing.
    """
    lines = []
    import threading

    def _try_read(result_holder):
        try:
            line = sys.stdin.readline()
            result_holder.append(line)
        except Exception:
            result_holder.append(None)

    while True:
        holder = []
        t = threading.Thread(target=_try_read, args=(holder,), daemon=True)
        t.start()
        t.join(timeout=0.08)       # 80 ms window — paste fills instantly
        if not t.is_alive() and holder:
            line = holder[0]
            if line is None or line == "":
                break
            lines.append(line.rstrip("\r\n"))
        else:
            # Nothing arrived within window → user is typing normally → stop
            break
    return lines

def smart_input(prompt_str):
    """
    Robust multiline input that handles:
    1. Normal single-line typing  → press Enter → sends
    2. Windows CMD paste          → all lines arrive at once → captured automatically
    3. /paste command             → explicit multiline mode (double-Enter to send)

    TIP shown once at startup.
    """
    if not getattr(smart_input, "_hinted", False):
        print(dim(
            "  Tip: For a single question just type and press Enter.\n"
            "       To paste a multi-line prompt, paste it then press Enter once.\n"
        ))
        smart_input._hinted = True

    first = _read_one_line(prompt_str)
    if first is None:
        return None

    first_stripped = first.strip()

    # Explicit paste/multiline mode — collect until double blank Enter
    if first_stripped in ("/paste", "/multi"):
        print(col("yellow",
            "  📋 Paste mode — paste your full prompt, then press Enter on a blank line:"))
        collected = []
        blank_count = 0
        while True:
            line = _read_one_line("  │ ")
            if line is None:
                break
            if line.strip() == "":
                blank_count += 1
                if blank_count >= 1:   # single blank Enter = done in paste mode
                    break
                collected.append("")
            else:
                blank_count = 0
                collected.append(line)
        return "\n".join(collected).strip()

    # Try to drain any buffered lines (catches Windows paste of multi-line text)
    extra = _drain_stdin_lines()

    if extra:
        # Paste detected — combine all lines
        all_lines = [first] + extra
        result = "\n".join(all_lines).strip()
        # Show a compact preview so user knows what was captured
        preview_lines = result.splitlines()
        n = len(preview_lines)
        print(dim(f"  ✓ Captured {n} lines."))
        return result
    else:
        # Normal single-line input
        return first_stripped

# ═══════════════════════════════════════════════════════════════════════════════
#  STATUS  &  HELP
# ═══════════════════════════════════════════════════════════════════════════════
def print_status(cdir, hist):
    ram     = get_ram()
    filled  = int(ram / 100 * 20)
    bar_col = "red" if ram > 80 else ("yellow" if ram > 60 else "green")
    bar     = col(bar_col, "█"*filled) + dim("░"*(20-filled))
    print(f"""
  {col("cyan","┌─ Status ──────────────────────────────────────┐")}
  {col("cyan","│")}  RAM      {bar} {ram:.0f}%
  {col("cyan","│")}  Dir      {col("blue", cdir)}
  {col("cyan","│")}  Model    {col("magenta", CFG.get("model","auto"))}
  {col("cyan","│")}  History  {len(hist)//2} exchanges
  {col("cyan","└───────────────────────────────────────────────┘")}""")

HELP_TEXT = f"""
  {col("cyan","┌─ Commands ─────────────────────────────────────────────────┐")}
  {col("cyan","│")}
  {col("cyan","│")}  {bold("Just type naturally")} — the AI understands plain language.
  {col("cyan","│")}
  {col("cyan","│")}  {col("yellow","PROJECT")}
  {col("cyan","│")}    /build  [path]           full analyze + code + save
  {col("cyan","│")}    /analyze [path]           analyze a project/folder
  {col("cyan","│")}    /ask [path] <question>    ask about a project
  {col("cyan","│")}
  {col("cyan","│")}  {col("yellow","FILES")}
  {col("cyan","│")}    /fix <file> [issue]       fix bugs and auto-save
  {col("cyan","│")}    /add <file> <feature>     add a feature and save
  {col("cyan","│")}    /refactor <file>          clean up code and save
  {col("cyan","│")}    /test <file>              generate unit tests
  {col("cyan","│")}    /explain <file>           explain what it does
  {col("cyan","│")}    /read <file>              show file contents
  {col("cyan","│")}    /run <file>               execute Python file
  {col("cyan","│")}
  {col("cyan","│")}  {col("yellow","RESEARCH")}
  {col("cyan","│")}    /research <query>         web search + AI analysis
  {col("cyan","│")}
  {col("cyan","│")}  {col("yellow","SETTINGS")}
  {col("cyan","│")}    /dir [path]               show or change directory
  {col("cyan","│")}    /model [name]             show or force model
  {col("cyan","│")}    /models                   list all model mappings
  {col("cyan","│")}    /set <key> <value>        change any setting
  {col("cyan","│")}    /status                   RAM / dir / model info
  {col("cyan","│")}    /save [file]              save last response to file
  {col("cyan","│")}    /clear                    clear chat history
  {col("cyan","│")}    /exit                     quit
  {col("cyan","│")}
  {col("cyan","│")}  {col("yellow","TIPS")}
  {col("cyan","│")}    • End line with \\  to continue on next line
  {col("cyan","│")}    • /multi for pasting long prompts
  {col("cyan","│")}    • Tab autocompletes commands and filenames
  {col("cyan","│")}    • Files mentioned in chat are auto-loaded as context
  {col("cyan","│")}
  {col("cyan","└────────────────────────────────────────────────────────────┘")}
"""

# ═══════════════════════════════════════════════════════════════════════════════
#  GUIDED MENU  (no commands needed — just pick a number)
# ═══════════════════════════════════════════════════════════════════════════════
MENU_ITEMS = [
    ("1", "💬", "Chat / Koi bhi sawaal poochho"),
    ("2", "🔨", "Project build karo (folder se)"),
    ("3", "🔍", "Project / Folder analyze karo"),
    ("4", "🐛", "File ki bugs fix karo"),
    ("5", "✨", "File mein feature add karo"),
    ("6", "📖", "File explain karwao"),
    ("7", "🧪", "File ke liye tests banao"),
    ("8", "🌐", "Research / Web search"),
    ("9", "⚙️ ", "Settings"),
    ("0", "🚪", "Bahar jaao (Exit)"),
]

def _cls():
    os.system("cls" if sys.platform == "win32" else "clear")

def print_menu(cdir, model):
    _cls()
    print(col("cyan", """
  ╔══════════════════════════════════════════════════════════╗
  ║         AI Agent  v4.0  —  Your Local Codex             ║
  ║    Coding · Debug · Refactor · Research · Build         ║
  ║    Powered by Ollama  (Mistral · CodeLlama · Phi3)      ║
  ╚══════════════════════════════════════════════════════════╝"""))
    print()
    print(col("cyan","  ┌─ Kya karna chahte ho? ─────────────────────────────────────┐"))
    for num, icon, label in MENU_ITEMS:
        print(col("cyan","  │") + f"   {col('yellow', num + '.')}  {icon}  {label}")
    print(col("cyan","  └─────────────────────────────────────────────────────────────┘"))
    print()
    print(dim(f"  📂 Folder : {cdir}"))
    print(dim(f"  🤖 Model  : {model}"))
    print()

def _ask(label):
    v = (_read_one_line(f"  {col('yellow','>')} {label}: ") or "").strip().strip('"\'')
    return v

def _wait():
    _read_one_line(dim("\n  [Enter dabao wapis menu par jaane ke liye...]"))

def guided_settings(cdir):
    _cls()
    print(col("cyan","  ┌─ Settings ──────────────────────────────────────────────────┐"))
    print(col("cyan","  │") + f"   1. Folder badlo       (abhi: {cdir})")
    print(col("cyan","  │") + f"   2. Model badlo        (abhi: {CFG.get('model','auto')})")
    print(col("cyan","  │") + f"   3. Auto-save toggle   (abhi: {CFG.get('auto_save',True)})")
    print(col("cyan","  │") + f"   4. Wapis jaao")
    print(col("cyan","  └─────────────────────────────────────────────────────────────┘"))
    print()
    ch = _ask("1-4 chunno")
    if ch == "1":
        p = _ask("Naya folder path")
        if p and Path(p).exists():
            CFG["directory"] = p; save_config(CFG)
            print(col("green", f"  OK! Folder: {p}")); return p
        else:
            print(col("red","  Folder nahi mila."))
    elif ch == "2":
        print(dim("  Options: auto  mistral  codellama:7b  phi3"))
        m = _ask("Model naam")
        if m: CFG["model"] = m; save_config(CFG); print(col("green",f"  Model: {m}"))
    elif ch == "3":
        CFG["auto_save"] = not CFG.get("auto_save", True); save_config(CFG)
        print(col("green",f"  Auto-save: {CFG['auto_save']}"))
    return cdir

# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN LOOP
# ═══════════════════════════════════════════════════════════════════════════════
def run():
    cdir  = CFG.get("directory", str(Path.home()))
    hist  = []
    last_resp = ""

    while True:
        print_menu(cdir, CFG.get("model","auto"))
        choice = (_read_one_line(f"  {col('cyan','Number chunno')} {bold('>')} ") or "").strip()

        # ── 1. CHAT ─────────────────────────────────────────────────────────
        if choice in ("1", ""):
            _cls()
            print(col("cyan","  ┌─ Chat ──────────────────────────────────────────────────────┐"))
            print(col("cyan","  │") + dim("  Koi bhi sawaal poochho. Folder path mention karo to auto-load."))
            print(col("cyan","  │") + dim("  Example: E:\\mera_project ko analyze karo aur GUI banao"))
            print(col("cyan","  │") + dim("  Lambi prompt paste karo — sab capture ho jayega."))
            print(col("cyan","  └─────────────────────────────────────────────────────────────┘"))
            print()
            inp = smart_input(f"  {col('cyan','Aap')} {bold('>')} ")
            if not inp:
                continue

            task  = detect_task(inp)
            model = pick_model(task)
            print(dim(f"\n  [{task}]  {model}"))
            file_ctx, dir_ctx = auto_context(inp, cdir)

            if task == "research":
                q    = re.sub(r'^(research|search|dhundo)\s*:?\s*','', inp, flags=re.I).strip() or inp
                resp = wf_research(q)
            else:
                prompt = build_prompt(task, inp, cdir, hist, file_ctx, dir_ctx)
                resp   = run_ollama(model, prompt, task)
                if CFG.get("auto_save") and "```" in resp and (file_ctx or dir_ctx):
                    save_code(resp, cdir)

            last_resp = resp
            print_response(resp)
            hist += [{"role":"user","content":inp}, {"role":"assistant","content":resp[:400]}]
            if len(hist) > CFG.get("history_max",20)*2:
                hist = hist[-CFG.get("history_max",20)*2:]
            _wait()

        # ── 2. BUILD ────────────────────────────────────────────────────────
        elif choice == "2":
            _cls()
            print(col("cyan","  ┌─ Project Build ─────────────────────────────────────────────┐"))
            print(col("cyan","  │") + dim(f"  Abhi ka folder: {cdir}"))
            print(col("cyan","  └─────────────────────────────────────────────────────────────┘"))
            print()
            bpath = _ask("Project folder path (Enter = abhi wala folder)")
            if not bpath: bpath = cdir
            if not Path(bpath).is_absolute(): bpath = str(Path(cdir)/bpath)
            if not Path(bpath).exists():
                print(col("red",f"  Folder nahi mila: {bpath}")); _wait(); continue
            print()
            print(dim("  Koi khaas instructions hain? (Enter dabao agar nahi)"))
            extra = _ask("Instructions")
            resp  = wf_build(bpath, extra or None, cdir)
            last_resp = resp; print_response(resp); _wait()

        # ── 3. ANALYZE ──────────────────────────────────────────────────────
        elif choice == "3":
            _cls()
            print(col("cyan","  ┌─ Analyze ───────────────────────────────────────────────────┐"))
            print(col("cyan","  │") + dim(f"  Abhi ka folder: {cdir}"))
            print(col("cyan","  └─────────────────────────────────────────────────────────────┘"))
            print()
            apath = _ask("Konsa folder analyze karna hai? (Enter = abhi wala)")
            if not apath: apath = cdir
            if not Path(apath).is_absolute(): apath = str(Path(cdir)/apath)
            print(col("cyan", f"\n  Analyzing: {apath}"))
            model  = pick_model("analyze")
            prompt = f"{SYS['analyze']}\n\n{dir_tree(apath)}\n\n{project_ctx(apath)}\n\nAnalyze completely."
            resp   = run_ollama(model, prompt, "analyze")
            last_resp = resp; print_response(resp); _wait()

        # ── 4. FIX ──────────────────────────────────────────────────────────
        elif choice == "4":
            _cls()
            print(col("cyan","  ┌─ Bug Fix ───────────────────────────────────────────────────┐"))
            print(col("cyan","  └─────────────────────────────────────────────────────────────┘"))
            print()
            fp = _ask("File ka path (jisko fix karna hai)")
            if not fp: continue
            if not Path(fp).is_absolute(): fp = str(Path(cdir)/fp)
            if not Path(fp).exists():
                print(col("red",f"  File nahi mili: {fp}")); _wait(); continue
            issue = _ask("Bug describe karo (Enter = sab bugs auto dhundo)")
            resp  = wf_fix(fp, issue, cdir)
            last_resp = resp; print_response(resp); _wait()

        # ── 5. ADD FEATURE ──────────────────────────────────────────────────
        elif choice == "5":
            _cls()
            print(col("cyan","  ┌─ Feature Add ───────────────────────────────────────────────┐"))
            print(col("cyan","  └─────────────────────────────────────────────────────────────┘"))
            print()
            fp = _ask("File ka path")
            if not fp: continue
            if not Path(fp).is_absolute(): fp = str(Path(cdir)/fp)
            if not Path(fp).exists():
                print(col("red",f"  File nahi mili: {fp}")); _wait(); continue
            feature = _ask("Konsa feature add karna hai?")
            if not feature: continue
            resp = wf_add(fp, feature, cdir)
            last_resp = resp; print_response(resp); _wait()

        # ── 6. EXPLAIN ──────────────────────────────────────────────────────
        elif choice == "6":
            _cls()
            print(col("cyan","  ┌─ File Explain ──────────────────────────────────────────────┐"))
            print(col("cyan","  └─────────────────────────────────────────────────────────────┘"))
            print()
            fp = _ask("File ka path")
            if not fp: continue
            if not Path(fp).is_absolute(): fp = str(Path(cdir)/fp)
            if not Path(fp).exists():
                print(col("red",f"  File nahi mili: {fp}")); _wait(); continue
            resp = wf_explain(fp, cdir)
            last_resp = resp; print_response(resp); _wait()

        # ── 7. TEST ─────────────────────────────────────────────────────────
        elif choice == "7":
            _cls()
            print(col("cyan","  ┌─ Tests Generate ────────────────────────────────────────────┐"))
            print(col("cyan","  └─────────────────────────────────────────────────────────────┘"))
            print()
            fp = _ask("File ka path")
            if not fp: continue
            if not Path(fp).is_absolute(): fp = str(Path(cdir)/fp)
            if not Path(fp).exists():
                print(col("red",f"  File nahi mili: {fp}")); _wait(); continue
            resp = wf_test(fp, cdir)
            last_resp = resp; print_response(resp); _wait()

        # ── 8. RESEARCH ─────────────────────────────────────────────────────
        elif choice == "8":
            _cls()
            print(col("cyan","  ┌─ Research / Web Search ─────────────────────────────────────┐"))
            print(col("cyan","  └─────────────────────────────────────────────────────────────┘"))
            print()
            query = _ask("Kya dhundhna hai?")
            if not query: continue
            resp  = wf_research(query)
            last_resp = resp; print_response(resp); _wait()

        # ── 9. SETTINGS ─────────────────────────────────────────────────────
        elif choice == "9":
            new_cdir = guided_settings(cdir)
            if new_cdir and new_cdir != cdir:
                cdir = new_cdir
            _wait()

        # ── 0. EXIT ─────────────────────────────────────────────────────────
        elif choice == "0":
            _cls()
            print(col("yellow","\n  Allah Hafiz! 👋\n")); break

        else:
            print(col("red","  Galat number. 0-9 mein se chunno."))
            time.sleep(1)


# ═══════════════════════════════════════════════════════════════════════════════
#  SINGLE-SHOT MODE
# ═══════════════════════════════════════════════════════════════════════════════
def run_single(prompt_text, model_force=None):
    task = detect_task(prompt_text)
    if model_force:
        CFG["model"] = model_force
    model = pick_model(task)
    print(dim(f"  [{task}] {model}"))
    if task == "research":
        resp = wf_research(prompt_text)
    else:
        resp = run_ollama(model, f"{SYS.get(task,'')}\n\n{prompt_text}", task)
    print_response(resp)

# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="AI Agent v4.0 — Local Coding Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ai.py
  python ai.py -d "E:\\MyProject"
  python ai.py -m mistral
  python ai.py -p "write a binary search in python"
  python ai.py --setup
""")
    ap.add_argument("-d","--directory", help="Set working directory")
    ap.add_argument("-m","--model",     help="Force model: mistral/codellama:7b/phi3")
    ap.add_argument("-p","--prompt",    help="Single prompt (non-interactive)")
    ap.add_argument("--setup",  action="store_true", help="Check Ollama setup")
    args = ap.parse_args()

    if args.setup:
        print(col("cyan", "\n  ── Setup Check ──"))
        ok = bool(shutil.which("ollama"))
        print(col("green" if ok else "red",
                  f"  Ollama binary : {'✅ Found' if ok else '❌ Not found'}"))
        if ok:
            r = subprocess.run(["ollama","list"], capture_output=True, text=True)
            for m in ["phi3","mistral","codellama:7b"]:
                found = m in r.stdout
                print(col("green" if found else "yellow",
                           f"  {m:18} {'✅ Installed' if found else '⚠️  Run: ollama pull ' + m}"))
        sys.exit(0)

    if not shutil.which("ollama"):
        print(col("red", "\n  ❌ Ollama not found."))
        print(dim("     Install : https://ollama.com/download"))
        print(dim("     Then    : ollama pull phi3 && ollama pull mistral && ollama pull codellama:7b"))
        sys.exit(1)

    if args.directory:
        CFG["directory"] = args.directory
        save_config(CFG)

    if args.prompt:
        run_single(args.prompt, args.model)
    else:
        if args.model:
            CFG["model"] = args.model
        run()

if __name__ == "__main__":
    main()