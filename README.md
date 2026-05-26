<!--
  ██████╗ ██╗   ██╗██████╗ ███████╗███╗   ██╗
  ██╔══██╗╚██╗ ██╔╝██╔══██╗██╔════╝████╗  ██║
  ██████╔╝ ╚████╔╝ ██████╔╝█████╗  ██╔██╗ ██║
  ██╔═══╝   ╚██╔╝  ██╔═══╝ ██╔══╝  ██║╚██╗██║
  ██║        ██║   ██║     ███████╗██║ ╚████║
  ╚═╝        ╚═╝   ╚═╝     ╚══════╝╚═╝  ╚═══╝
-->

<div align="center">

<a href="# ">
  <img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=700&size=42&duration=2800&pause=600&color=4F8CC9&center=true&vCenter=true&width=620&lines=Pypen;Run+multiple+Python+apps.;One+container.;Zero+drama." alt="Pypen typing banner" />
</a>

<br/>

<img src="https://raw.githubusercontent.com/catppuccin/catppuccin/main/assets/footers/gray0_ctp_on_line.svg?sanitize=true" width="100%" alt="divider"/>

<p>
  <img alt="Python"   src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img alt="Quart"    src="https://img.shields.io/badge/Quart-async-5A29E4?style=for-the-badge&logo=quart&logoColor=white" />
  <img alt="s6"       src="https://img.shields.io/badge/s6--overlay-init-1f6feb?style=for-the-badge&logo=linuxcontainers&logoColor=white" />
  <img alt="Docker"   src="https://img.shields.io/badge/Docker-ready-2496ED?style=for-the-badge&logo=docker&logoColor=white" />
  <img alt="License"  src="https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge" />
  <a href="https://docs.pypen.xyz"><img alt="Read the full docs" src="https://img.shields.io/badge/📖_Docs-4F8CC9?style=for-the-badge&labelColor=0d1117" /></a>
</p>

<sub>
  <kbd>⚡ async</kbd> &nbsp;•&nbsp;
  <kbd>🧬 per-bot venvs</kbd> &nbsp;•&nbsp;
  <kbd>🛰 live logs</kbd> &nbsp;•&nbsp;
  <kbd>⏱ cron</kbd> &nbsp;•&nbsp;
  <kbd>🩹 self-heal</kbd>
</sub>

</div>

<br/>

## ✨ What is Pypen?

> **Pypen** is a single-container **multi-process runner for Python repositories**.
> Point it at any GitHub repo (or many of them) in one `project.toml`, and Pypen
> clones, builds, runs, watches and restarts each one in its own isolated
> Python environment — with a live web dashboard on top.
>
> If it runs with `python something.py` (or any shell command), Pypen can host it.

<table>
<tr>
<td width="50%" valign="top">

### 🧠 Use it for

- 🐍 Hosting **any Python project** — web apps, scrapers, workers, daemons
- 🤖 Running **bots** (Telegram / Discord / Matrix / …) alongside everything else
- 🧪 Spinning up **many forks of the same repo** with different env vars
- 🛠 Replacing a fleet of tiny VPSes with **one box, many workers**
- 🌙 **Idle / scheduled restarts** to keep long-running scripts fresh


</td>
<td width="50%" valign="top">

### 🧰 Tech stack

| Layer | Tools |
|---|---|
| **Runtime** | Python 3.11+, `pyenv`, `uv` |
| **Web / API** | Quart · Uvicorn · python-socket.io |
| **Process supervision** | s6-overlay · custom `s6_svc` wrapper |
| **Scheduling** | `schedule` · async cron loop |
| **Filesystem / VCS** | GitPython · watchdog · aiofiles |
| **Observability** | Loguru · psutil · live log streaming |

</td>
</tr>
</table>

<br/>

<div align="center">

### 🎛 How it fits together

```mermaid
flowchart LR
    A([project.toml]) --> B{{Pypen Supervisor}}
    B -->|spawns| C[/repo #1 venv/]
    B -->|spawns| D[/repo #2 venv/]
    B -->|spawns| E[/repo #N venv/]
    B --> F[(s6-overlay)]
    F --> G([Quart Dashboard])
    G --> H{{🌐 Live Logs · WebSocket}}
    G --> I{{⏱ Cron · Restarts · Idle}}
```

</div>

<br/>

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12,20,24&height=120&section=footer&text=Pypen&fontSize=42&fontColor=ffffff&animation=twinkling" alt="footer" width="100%"/>

</div>
