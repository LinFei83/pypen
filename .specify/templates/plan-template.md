# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]

**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Python 3.11+ (MUST retain unless Constitution amended)

**Primary Dependencies**: Quart · Uvicorn · python-socket.io · s6-overlay · GitPython · loguru · schedule · psutil · watchdog · aiofiles · uv (install)

**Storage**: Filesystem + `project.toml` (+ s6 service dirs under `/etc/s6/services`)

**Testing**: pytest under `tests/` (introduce scaffold if missing; Constitution V)

**Target Platform**: Linux container (Docker / s6-overlay); PaaS via `heroku.yml` as applicable

**Project Type**: Single-container multi-process runner + Quart dashboard

**Performance Goals**: [domain-specific, or N/A for this feature]

**Constraints**: Preserve stack/layout (Constitution I); no unrelated refactors (II); secrets via toml/env only (VII)

**Scale/Scope**: [domain-specific for this feature]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Derived from `.specify/memory/constitution.md` (Pypen Constitution v1.0.0):

- [ ] **I. 技术栈与目录结构保留**: Plan stays within `app/` · `worker/` · `ping/` · root entry scripts; no stack swap without amendment
- [ ] **II. 需求驱动的最小变更**: Scope limited to this feature; no drive-by refactors
- [ ] **III. 命名与编码规范一致性**: Follow existing `snake_case`, loguru logging, async patterns
- [ ] **IV. 公共 API 向后兼容**: HTTP `/service/*`, Socket.IO events, `project.toml` fields, exported Python APIs remain compatible or have migration plan
- [ ] **V. 新增功能必须可测**: Each user story has corresponding automated tests
- [ ] **VI. 使用既有工具链**: Validate via `requirements.txt` / Dockerfile / `python3 start.py` / project test commands only
- [ ] **VII. 密钥与配置外置**: No hardcoded tokens/passwords; use `project.toml` or env vars
- [ ] **VIII. 实现前先阅读相似模块**: Plan names the existing modules that will be read/reused before coding

Any unchecked gate after design MUST be justified in Complexity Tracking below.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
app/                     # Quart dashboard, routes, cron, static, templates
├── routes/
├── utils/
├── static/
└── templates/
worker/                  # project.toml load, clone/venv, s6 service mgmt
ping/                    # keep-alive pinger
tests/                   # automated tests (create as needed)
start.py · run.py · update.py
requirements.txt · Dockerfile · project.toml.example
```

**Structure Decision**: [Document which packages this feature touches; do not invent parallel top-level layouts]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
