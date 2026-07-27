---

description: "Task list template for feature implementation"
---

# Tasks: [FEATURE NAME]

**Input**: Design documents from `/specs/[###-feature-name]/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: REQUIRED by Pypen Constitution V. Every user story MUST include automated test tasks. Do not omit the Tests subsection.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Pypen layout**: `app/`, `worker/`, `ping/` at repository root; tests under `tests/`
- Prefer extending existing modules over creating parallel packages
- Paths shown below use this layout — adjust only per plan.md within these trees

<!--
  ============================================================================
  IMPORTANT: The tasks below are SAMPLE TASKS for illustration purposes only.

  The /speckit-tasks command MUST replace these with actual tasks based on:
  - User stories from spec.md (with their priorities P1, P2, P3...)
  - Feature requirements from plan.md
  - Entities from data-model.md
  - Endpoints from contracts/

  Tasks MUST be organized by user story so each story can be:
  - Implemented independently
  - Tested independently
  - Delivered as an MVP increment

  DO NOT keep these sample tasks in the generated tasks.md file.
  ============================================================================
-->

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Align with existing repo; do not reinvent project layout

- [ ] T001 Confirm touch points under `app/` / `worker/` / `ping/` per plan (Constitution I, VIII)
- [ ] T002 [P] Ensure `tests/` scaffold exists if missing (pytest-discoverable)
- [ ] T003 [P] Use existing `requirements.txt` / Dockerfile toolchain only (Constitution VI)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared prerequisites that MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until this phase is complete

Examples of foundational tasks (adjust to this feature; omit unused):

- [ ] T004 Read similar modules named in plan Constitution Check (Constitution VIII)
- [ ] T005 [P] Extend shared config helpers in `worker/config_loader.py` if needed
- [ ] T006 [P] Extend shared logging via `app.utils.logging_config` if needed
- [ ] T007 Ensure secrets/env still load from `project.toml` / env only (Constitution VII)
- [ ] T008 Document any public API compatibility strategy (Constitution IV)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - [Title] (Priority: P1) MVP

**Goal**: [Brief description of what this story delivers]

**Independent Test**: [How to verify this story works on its own]

### Tests for User Story 1 (REQUIRED — Constitution V)

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T010 [P] [US1] Unit/contract test for [behavior] in tests/unit/test_[name].py
- [ ] T011 [P] [US1] Integration test for [user journey] in tests/integration/test_[name].py

### Implementation for User Story 1

- [ ] T012 [P] [US1] Extend or add module under app|worker|ping as planned
- [ ] T013 [US1] Implement core behavior (depends on T012)
- [ ] T014 [US1] Wire routes/Socket.IO/config without breaking existing contracts
- [ ] T015 [US1] Add validation and error handling consistent with neighbors
- [ ] T016 [US1] Add loguru logging for user story 1 operations

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - [Title] (Priority: P2)

**Goal**: [Brief description of what this story delivers]

**Independent Test**: [How to verify this story works on its own]

### Tests for User Story 2 (REQUIRED — Constitution V)

- [ ] T018 [P] [US2] Unit/contract test for [behavior] in tests/unit/test_[name].py
- [ ] T019 [P] [US2] Integration test for [user journey] in tests/integration/test_[name].py

### Implementation for User Story 2

- [ ] T020 [P] [US2] Extend or add module under app|worker|ping as planned
- [ ] T021 [US2] Implement core behavior
- [ ] T022 [US2] Wire into existing surfaces without unrelated refactors
- [ ] T023 [US2] Integrate with User Story 1 components (if needed)

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - [Title] (Priority: P3)

**Goal**: [Brief description of what this story delivers]

**Independent Test**: [How to verify this story works on its own]

### Tests for User Story 3 (REQUIRED — Constitution V)

- [ ] T024 [P] [US3] Unit/contract test for [behavior] in tests/unit/test_[name].py
- [ ] T025 [P] [US3] Integration test for [user journey] in tests/integration/test_[name].py

### Implementation for User Story 3

- [ ] T026 [P] [US3] Extend or add module under app|worker|ping as planned
- [ ] T027 [US3] Implement core behavior
- [ ] T028 [US3] Wire into existing surfaces without unrelated refactors

**Checkpoint**: All user stories should now be independently functional

---

[Add more user story phases as needed, following the same pattern]

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] TXXX [P] Update `project.toml.example` if new config keys were added
- [ ] TXXX Verify no hardcoded secrets (Constitution VII)
- [ ] TXXX Confirm public API compatibility (Constitution IV)
- [ ] TXXX [P] Fill remaining unit tests in tests/unit/
- [ ] TXXX Run project test/build commands only (Constitution VI)
- [ ] TXXX Run quickstart.md validation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - May integrate with US1 but should be independently testable
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - May integrate with US1/US2 but should be independently testable

### Within Each User Story

- Tests MUST be written and FAIL before implementation (Constitution V)
- Read similar modules before coding (Constitution VIII)
- Shared helpers before route/worker wiring
- Core implementation before integration
- Story complete before moving to next priority
- No unrelated refactors (Constitution II)

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, all user stories can start in parallel (if team capacity allows)
- All tests for a user story marked [P] can run in parallel
- Independent module edits marked [P] can run in parallel when files do not conflict
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Unit/contract test for [behavior] in tests/unit/test_[name].py"
Task: "Integration test for [user journey] in tests/integration/test_[name].py"

# Launch independent module work together when files differ:
Task: "Extend helper in worker/[module].py"
Task: "Extend helper in app/utils/[module].py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1
   - Developer B: User Story 2
   - Developer C: User Story 3
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
