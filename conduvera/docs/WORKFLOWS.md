# CuraOps Workflows

Concrete workflows combining Matrix OS UI + Hermes Skills.

---

## Workflow 1: Start New Session

**Trigger:** User opens Matrix OS
**Skills:** Session Manager + Safety Guard + Multi-Agent Lock

```python
# Matrix OS (UI Layer)
class NewSessionWorkflow:
    def execute(self, project_path: str):
        # 1. Create session
        session = session_mgr.start_session(
            project_path=project_path,
            agent_id="matrix-os"
        )
        
        # 2. Safety check on project
        safety_result = safety_guard.validate_project(project_path)
        if safety_result.risk_level == "CRITICAL":
            self.show_warning(safety_result.warnings)
        
        # 3. Claim project files
        lock = multi_agent_lock.claim_file(
            project_path,
            agent_id="matrix-os",
            scope=LockScope.DIRECTORY
        )
        
        # 4. Update UI
        self.update_title(f"Matrix OS - {session.name}")
        self.show_session_panel(session)
```

---

## Workflow 2: Create Change Request

**Trigger:** User presses F5 (CR hotkey)
**Skills:** Change Request + Safety Guard + ASPICE Link Manager

```python
class CreateCRWorkflow:
    def execute(self, file_path: Path):
        # 1. Show CR dialog
        cr_data = self.show_cr_dialog(file_path)
        
        # 2. Create CR
        cr = change_request.create_cr(
            title=cr_data.title,
            description=cr_data.description,
            scope=[str(file_path)],
            session_id=session_mgr.get_current_session().id
        )
        
        # 3. Safety validation
        for file in cr.scope:
            result = safety_guard.validate_change(file)
            if result.blocked:
                cr.add_blocker(result)
        
        # 4. Create ASPICE links
        aspice_links.create_link(
            source=f"cr:{cr.id}",
            target=f"file:{file_path}",
            link_type="modifies"
        )
        
        # 5. Update UI
        self.show_cr_panel(cr)
```

---

## Workflow 3: Safe File Deletion

**Trigger:** User deletes file in File Browser
**Skills:** Safety Guard (P1-Critical)

```python
class SafeDeleteWorkflow:
    def execute(self, path: Path):
        # P1-Critical: ALWAYS validate
        result = safety_guard.validate_delete(path)
        
        if result.blocked:
            # BLOCK operation
            self.show_blocking_modal(
                title="⚠️ SAFETY BLOCKED",
                message=result.reason,
                suggestions=result.suggestions
            )
            return False
        
        if result.warnings:
            # Show warning but allow
            if not self.show_warning_dialog(result.warnings):
                return False
        
        # Safe to delete
        path.unlink()
        pattern_learning.record_action("delete", path, result)
        return True
```

---

## Workflow 4: Multi-Agent Coordination

**Trigger:** External agent (Cursor/Claude) wants to edit files
**Skills:** Multi-Agent Lock + Session Manager

```python
class AgentCoordinationWorkflow:
    def on_agent_request(self, agent_id: str, files: List[str]):
        # 1. Check conflicts
        conflicts = multi_agent_lock.check_conflicts(files, agent_id)
        
        if conflicts:
            suggestions = multi_agent_lock.get_resolution_suggestions(conflicts)
            
            # Show in Matrix OS
            self.show_conflict_panel(
                agent=agent_id,
                conflicts=conflicts,
                suggestions=suggestions
            )
            
            # Ask user
            decision = self.prompt_user(
                f"Agent {agent_id} wants to edit {len(files)} files "
                f"but {len(conflicts)} conflicts exist. Allow?"
            )
            
            if not decision:
                return {"status": "denied", "conflicts": conflicts}
        
        # 2. Grant locks
        locks = []
        for file in files:
            lock = multi_agent_lock.claim_file(file, agent_id)
            locks.append(lock)
        
        # 3. Create agent session
        session = session_mgr.start_agent_session(
            agent_id=agent_id,
            parent_session=session_mgr.get_current_session().id,
            locks=locks
        )
        
        return {"status": "granted", "session_id": session.id, "locks": locks}
```

---

## Workflow 5: ASPICE Compliance Check

**Trigger:** Before commit or on demand
**Skills:** ASPICE Conflict Detector + Link Manager

```python
class ComplianceCheckWorkflow:
    def execute(self):
        session = session_mgr.get_current_session()
        
        # 1. Detect conflicts
        detector = ASPICEConflictDetector(session.project_path)
        conflicts = detector.detect_conflicts()
        
        # 2. Generate report
        report = detector.generate_conflict_report(conflicts)
        
        # 3. Show dashboard
        self.show_compliance_dashboard(report)
        
        # 4. If critical conflicts, block commit
        critical = [c for c in conflicts if c.severity == "CRITICAL"]
        if critical:
            self.show_blocking_warning(
                f"{len(critical)} critical ASPICE conflicts found"
            )
            return False
        
        return True
```

---

## Workflow 6: Pattern Learning Feedback

**Trigger:** User accepts/rejects AI suggestion
**Skills:** Pattern Learning

```python
class PatternFeedbackWorkflow:
    def on_suggestion(self, context: dict, suggestion: str):
        # 1. Record pattern
        pattern_learning.record_pattern(
            context=context,
            action=suggestion,
            outcome="suggested"
        )
        
        # 2. Show suggestion in UI
        user_choice = self.show_suggestion_dialog(suggestion)
        
        # 3. Record feedback
        pattern_learning.record_feedback(
            context=context,
            suggestion=suggestion,
            accepted=user_choice
        )
        
        # 4. Update future suggestions
        if user_choice:
            pattern_learning.reinforce(context, suggestion)
        else:
            pattern_learning.adjust(context, suggestion)
```

---

## Workflow State Transitions

```
All workflows follow:

    [User Action]
         │
         ▼
    [Matrix OS UI]
         │
         ▼
    [Skill Validation]
         │
    ┌────┴────┐
    │         │
 Blocked    Pass
    │         │
    ▼         ▼
[Warning]  [Execute]
    │         │
    └────┬────┘
         │
         ▼
    [Update UI]
         │
         ▼
    [Log/Trace]
```
