#!/usr/bin/env python3
"""
Batch test all capabilities to identify which are functional vs stubs.

This tests each capability by:
1. Finding its official binding
2. Identifying the service operation
3. Calling it directly with sensible test data
4. Reporting pass/fail and why
"""

import sys
import inspect
from pathlib import Path
from typing import Any, Dict, Tuple

# Add runtime to path
runtime_root = Path(__file__).parent / "runtime"
sys.path.insert(0, str(runtime_root))

from runtime.binding_registry import BindingRegistry
from runtime.capability_loader import YamlCapabilityLoader
from runtime.binding_models import BindingSpec


# Test data generators - names must match binding input fields
TEST_DATA = {
    "analysis.problem.split": {
        "problem": "Migrate on-premise ERP system to AWS",
        "strategy": "phases",
    },
    "analysis.risk.extract": {
        "target": {
            "type": "proposal",
            "title": "Vendor selection",
            "body": "We recommend Vendor A based on pricing alone.",
        },
        "risk_scope": "strategic",
    },
    "analysis.theme.cluster": {
        "items": [
            {"id": "fb1", "content": "The app crashes when I upload large files."},
            {"id": "fb2", "content": "I love the new dark mode feature."},
            {"id": "fb3", "content": "Upload fails for files over 10 MB."},
        ],
        "hint_labels": ["stability", "ux"],
    },
    "audio.speech.synthesize": {
        "text": "Hello, welcome to the platform.",
        "language": "en-US",
    },
    "code.source.analyze": {
        "code": "def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)\n",
        "language": "python",
    },
    "data.record.transform": {
        "records": [
            {
                "first_name": "Alice",
                "last_name": "Smith",
                "age": 30,
                "internal_id": "x99",
            },
            {
                "first_name": "Bob",
                "last_name": "Jones",
                "age": 25,
                "internal_id": "x42",
            },
        ],
        "mapping": {
            "rename": {"first_name": "name"},
            "select": ["name", "last_name", "age"],
        },
    },
    "fs.file.list": {"path": "."},
    "fs.file.write": {
        "path": "test_results/test_write_output.txt",
        "content": "test write",
        "mode": "overwrite",
    },
    "image.content.extract": {"image": b"fake image data for OCR"},
    "table.column.aggregate": {
        "table": [
            {"dept": "Engineering", "salary": 90000},
            {"dept": "Engineering", "salary": 85000},
            {"dept": "Sales", "salary": 70000},
        ],
        "aggregations": [{"field": "salary", "function": "avg"}],
        "group_by": "dept",
    },
    "table.row.sort": {
        "table": [
            {"name": "Alice", "salary": 85000},
            {"name": "Bob", "salary": 92000},
            {"name": "Carol", "salary": 78000},
        ],
        "sort_by": [{"field": "salary", "order": "desc"}],
    },
    "agent.task.delegate": {
        "agent": "summarizer",
        "task": {"description": "Summarize the Q3 report", "priority": "high"},
    },
    "agent.plan.generate": {
        "objective": "Build a web scraper",
        "context": "Python preferred, target site uses JS rendering",
    },
    "agent.input.route": {
        "query": "Summarize this quarterly earnings report",
        "agents": ["summarizer", "analyst", "translator"],
    },
    "agent.option.generate": {
        "goal": "Choose a deployment strategy for the new microservice",
        "max_options": 3,
    },
    "agent.plan.create": {
        "intent_description": "Receive a PDF invoice, extract the text, classify if overdue, store summary"
    },
    "audio.speech.transcribe": {"audio": b"fake audio data"},
    "code.diff.extract": {"code_a": "x = 5", "code_b": "x = 10"},
    "code.snippet.execute": {"code": "x = 5 + 3; print(x)", "language": "python"},
    "code.source.format": {
        "code": "def foo( x,y ):\n  return x+y",
        "language": "python",
    },
    "data.json.parse": {"text": '{"name": "John", "age": 30}'},
    "data.record.deduplicate": {
        "records": [
            {"id": 1, "name": "Alice"},
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ],
        "key_fields": ["id"],
    },
    "data.schema.validate": {"data": {"name": "John"}, "schema": {"type": "object"}},
    "doc.content.chunk": {"text": "This is a long document. " * 50, "chunk_size": 1000},
    "email.inbox.read": {"mailbox": "inbox"},
    "email.message.send": {
        "to": "test@example.com",
        "subject": "Test Subject",
        "body": "Test message body",
    },
    "fs.file.read": {"path": str(Path(__file__).resolve()), "mode": "text"},
    "image.caption.generate": {"image": b"fake image data"},
    "image.content.classify": {
        "image": b"fake image data",
        "labels": ["cat", "dog", "bird"],
    },
    "memory.entry.retrieve": {"key": "test_key"},
    "memory.entry.store": {"key": "test_key", "value": "test_value"},
    "message.notification.send": {"message": "Test message", "recipient": "test_user"},
    "ops.budget.estimate": {
        "plan": {"steps": [{"id": "s1"}, {"id": "s2"}]},
        "limits": {"max_cost": 1.0, "max_duration_ms": 5000},
    },
    "ops.trace.monitor": {
        "trace": {"duration_ms": 1200, "error_count": 1},
        "thresholds": {"max_duration_ms": 2000, "max_errors": 2},
    },
    "pdf.document.read": {
        "path": str(Path(__file__).parent / "artifacts" / "test.pdf")
    },
    "policy.constraint.validate": {
        "payload": {"title": "Hello", "body": "World"},
        "constraint": {"required_keys": ["title"], "forbidden_keys": ["password"]},
    },
    "provenance.citation.generate": {
        "source": {"url": "https://example.com/article", "title": "Example"},
        "excerpt": "Important fact",
        "locator": "p.10",
    },
    "provenance.claim.verify": {
        "claim": "Alice works at Example",
        "sources": [
            {"text": "Alice works at Example and leads product."},
            {"text": "Unrelated source"},
        ],
    },
    "eval.output.score": {
        "output": {"summary": "Short summary", "confidence": 0.9},
        "rubric": {"dimensions": {"completeness": 0.5, "clarity": 0.5}},
    },
    "eval.option.analyze": {
        "options": [
            {
                "id": "opt-a",
                "label": "Option A",
                "description": "Conservative approach",
            },
            {"id": "opt-b", "label": "Option B", "description": "Aggressive approach"},
        ],
        "goal": "Choose deployment strategy for new service",
    },
    "eval.option.score": {
        "options": [
            {
                "id": "opt-a",
                "label": "Option A",
                "description": "Conservative approach",
            },
            {"id": "opt-b", "label": "Option B", "description": "Aggressive approach"},
        ],
        "goal": "Choose deployment strategy for new service",
    },
    "security.output.gate": {
        "output": {"text": "Contact me at test@example.com"},
        "policy": {"block_pii": True, "block_secrets": True},
    },
    "security.pii.detect": {"text": "Email me at test@example.com"},
    "security.pii.redact": {"text": "Phone +1 650 555 1234 and email test@example.com"},
    "security.secret.detect": {"text": "token=sk-1234567890ABCDEFGHIJ"},
    "table.row.filter": {
        "table": [{"name": "Alice", "age": 25}, {"name": "Bob", "age": 30}],
        "condition": {"age": {"$gt": 26}},
    },
    "text.content.classify": {
        "text": "I love this product! It's amazing!",
        "labels": ["positive", "negative", "neutral"],
    },
    "text.content.embed": {"text": "This is a test sentence for embedding."},
    "text.content.generate": {
        "instruction": "Write a one-sentence description of Python.",
        "context": "Python is a programming language.",
    },
    "text.entity.extract": {"text": "John Smith works at Google in Mountain View."},
    "text.content.extract": {
        "text": "<html><body><h1>Title</h1><p>This is a test paragraph with important information.</p></body></html>"
    },
    "text.keyword.extract": {
        "text": "Python is a great programming language for machine learning and data science applications."
    },
    "text.language.detect": {"text": "This is English text."},
    "text.response.extract": {
        "question": "What is Python?",
        "context": "Python is a high-level programming language created by Guido van Rossum. It emphasizes code readability.",
    },
    "text.content.transform": {
        "text": "The system is operational and functioning within normal parameters.",
        "goal": "simplify for a non-technical audience",
    },
    "text.content.summarize": {
        "text": "Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience without being explicitly programmed. It focuses on the development of algorithms that can access data and use it to learn for themselves."
    },
    "text.content.merge": {"items": ["Hello", "World", "Merge test"]},
    "text.content.template": {
        "template": "Hello {{name}}, welcome to {{place}}!",
        "variables": {"name": "John", "place": "Agent Skills"},
    },
    "text.content.translate": {"text": "Hello world", "target_language": "es"},
    "video.frame.extract": {"video": b"fake video data"},
    "web.page.fetch": {"url": "https://www.google.com"},
    "web.page.extract": {
        "content": "<html><body><h1>Web Page</h1><p>Main content here.</p></body></html>"
    },
    "web.source.verify": {"url": "https://example.com/news"},
    "web.source.search": {"query": "machine learning"},
    "web.source.normalize": {
        "results": [
            {
                "url": "https://example.com/page",
                "title": "Example",
                "snippet": "A sample page.",
            }
        ],
        "mode": "quick",
    },
    # ── model.* domain ──
    "model.embedding.generate": {
        "text": "The quick brown fox jumps over the lazy dog."
    },
    "model.output.classify": {
        "output": {
            "summary": "Revenue increased by 15% in Q3.",
            "items": ["sales up", "costs stable"],
        },
        "categories": ["financial", "technical", "operational"],
    },
    "model.output.generate": {
        "instruction": "Produce a risk assessment from the meeting notes.",
        "context_items": [
            {"id": "1", "content": "Budget overrun likely in Q3.", "type": "note"}
        ],
        "output_schema": {
            "type": "object",
            "properties": {"risks": {"type": "array"}, "severity": {"type": "string"}},
        },
    },
    "model.output.sanitize": {
        "output": {"text": "Contact admin at admin@corp.com, password=s3cret!"},
        "policy": {"remove_pii": True, "remove_harmful": True},
    },
    "model.output.score": {
        "output": "The product launch was successful with strong user adoption.",
        "instruction": "Evaluate the product launch summary.",
    },
    "model.prompt.template": {
        "template": "Hello ${name}, your project ${project} is ready.",
        "variables": {"name": "Alice", "project": "Alpha"},
    },
    "model.response.validate": {
        "output": {"summary": "Q3 results were positive.", "confidence": 0.85},
    },
    "model.risk.score": {
        "output": "The system performed within normal parameters.",
    },
    # ── remaining gaps ──
    "ops.trace.analyze": {
        "goal": "Detect latency bottleneck in pipeline",
        "events": [
            {"step": "fetch", "duration_ms": 200, "status": "ok"},
            {"step": "process", "duration_ms": 3500, "status": "slow"},
        ],
    },
    "research.source.retrieve": {
        "items": [
            {
                "content": "Machine learning is a subset of AI.",
                "source_ref": {"url": "https://example.com/ml"},
            },
        ],
    },
    "decision.option.justify": {
        "scored_options": [
            {"id": "opt-a", "label": "Option A", "score": 0.9},
            {"id": "opt-b", "label": "Option B", "score": 0.6},
        ],
        "analyzed_options": [
            {"id": "opt-a", "label": "Option A", "pros": ["fast"], "cons": ["costly"]},
            {"id": "opt-b", "label": "Option B", "pros": ["cheap"], "cons": ["slow"]},
        ],
        "goal": "Choose the best deployment strategy",
    },
    # ── Block B: newly-built capabilities ──
    "policy.constraint.gate": {
        "payload": {"title": "Report", "body": "Content here"},
        "gate": {
            "rules": {"required_keys": ["title"], "forbidden_keys": ["password"]},
            "action": "block",
        },
    },
    "policy.decision.justify": {
        "decision": "approved",
        "rules": [
            {"id": "R1", "description": "Budget under 10k", "outcome": "approved"},
            {"id": "R2", "description": "Requires VP sign-off", "outcome": "denied"},
        ],
    },
    "policy.risk.classify": {
        "action": {"type": "deploy", "destructive": False, "external": True},
    },
    "policy.risk.score": {
        "action": {"type": "data_export", "involves_pii": True, "external": True},
    },
    "memory.record.store": {
        "namespace": "test",
        "record": {"id": "rec-1", "content": "Test data for record store"},
    },
    "memory.vector.search": {
        "query": "test search query",
        "namespace": None,
        "top_k": 3,
    },
    "message.priority.classify": {
        "message": "URGENT: production outage on main API gateway",
    },
    "ops.event.acknowledge": {
        "event_id": "evt-001",
        "handler": "on-call-bot",
    },
    "ops.event.monitor": {
        "events": [
            {
                "type": "request",
                "severity": "info",
                "timestamp": "2026-01-01T00:00:00Z",
            },
            {
                "type": "error",
                "severity": "critical",
                "timestamp": "2026-01-01T00:01:00Z",
            },
        ],
        "thresholds": {"max_error_count": 0},
    },
    # ── identity domain ──
    "identity.assignee.identify": {
        "task": {"type": "code_review", "required_skills": ["python", "security"]},
        "candidates": [
            {"id": "alice", "skills": ["python", "security", "aws"], "load": 3},
            {"id": "bob", "skills": ["java", "security"], "load": 1},
        ],
    },
    "identity.decision.justify": {
        "decision": "granted",
        "subject": {"id": "alice", "role": "admin"},
        "policies": [{"id": "default", "description": "Default identity policy"}],
    },
    "identity.permission.gate": {
        "principal_id": "alice",
        "permission": "resource:read",
    },
    "identity.permission.get": {
        "permission_id": "resource:read",
    },
    "identity.permission.list": {
        "principal_id": "alice",
    },
    "identity.permission.verify": {
        "principal_id": "alice",
        "permission": "resource:read",
    },
    "identity.risk.score": {
        "principal_id": "alice",
        "signals": {"login_failures": 5, "unusual_hours": True},
    },
    "identity.role.assign": {
        "principal_id": "alice",
        "role_id": "editor",
    },
    "identity.role.get": {
        "role_id": "admin",
    },
    "identity.role.list": {
        "scope": "access",
    },
    # ── integration domain ──
    "integration.connector.get": {
        "connector_id": "crm-rest",
    },
    "integration.connector.list": {
        "status_filter": "active",
    },
    "integration.connector.sync": {
        "connector_id": "crm-rest",
    },
    "integration.event.acknowledge": {
        "event_id": "evt-int-001",
        "handler": "sync-worker",
    },
    "integration.mapping.transform": {
        "record": {"first_name": "Alice", "last_name": "Smith", "age": 30},
        "mapping": {"rename": {"first_name": "name"}},
    },
    "integration.mapping.validate": {
        "mapping": {"rename": {"first_name": "name"}, "select": ["name", "age"]},
        "source_schema": {"fields": ["first_name", "last_name", "age"]},
    },
    "integration.record.compare": {
        "record_a": {"id": "1", "name": "Alice", "email": "alice@old.com"},
        "record_b": {"id": "1", "name": "Alice", "email": "alice@new.com"},
        "key_fields": ["id"],
    },
    "integration.record.create": {
        "connector_id": "crm-rest",
        "record": {"name": "New Contact", "email": "new@example.com"},
    },
    "integration.record.delete": {
        "connector_id": "crm-rest",
        "record_id": "rec-to-delete",
    },
    "integration.record.reconcile": {
        "records_a": [
            {"id": "1", "name": "Alice"},
            {"id": "2", "name": "Bob"},
        ],
        "records_b": [
            {"id": "1", "name": "Alice"},
            {"id": "3", "name": "Carol"},
        ],
        "key_field": "id",
    },
    "integration.record.update": {
        "connector_id": "crm-rest",
        "record_id": "rec-001",
        "fields": {"email": "updated@example.com"},
    },
    "integration.record.upsert": {
        "connector_id": "crm-rest",
        "record": {"id": "rec-001", "name": "Alice Updated", "email": "alice@new.com"},
        "key_fields": ["id"],
    },
    # ── task domain ──
    "task.approval.approve": {
        "approval_id": "apr-001",
        "approver": "manager-1",
        "notes": "Looks good, approved.",
    },
    "task.approval.reject": {
        "approval_id": "apr-002",
        "rejector": "manager-2",
        "reason": "Missing justification.",
    },
    "task.assignee.assign": {
        "task_id": "CASE-1",
        "assignee_id": "alice",
    },
    "task.case.close": {
        "case_id": "CASE-1",
        "resolution": "Fixed in release v2.1",
    },
    "task.case.create": {
        "title": "Bug in login page",
        "description": "Users cannot log in with SSO.",
        "priority": "high",
    },
    "task.case.get": {
        "case_id": "CASE-1",
    },
    "task.case.list": {
        "status_filter": "open",
    },
    "task.case.search": {
        "query": "login",
    },
    "task.case.update": {
        "case_id": "CASE-1",
        "fields": {"priority": "critical"},
    },
    "task.event.acknowledge": {
        "event_id": "task-evt-001",
        "handler": "escalation-bot",
    },
    "task.incident.create": {
        "title": "API gateway 503 errors",
        "severity": "high",
        "affected_system": "api-gateway",
        "description": "Intermittent 503 errors on /v2 endpoints.",
    },
    "task.milestone.schedule": {
        "milestone_name": "Beta Release",
        "target_date": "2026-03-15",
        "deliverables": ["feature-x", "feature-y"],
    },
    "task.priority.classify": {
        "task": {
            "title": "Production database running out of disk space",
            "type": "incident",
        },
        "context": {"environment": "production", "users_affected": 5000},
    },
    "task.sla.monitor": {
        "tasks": [
            {
                "id": "CASE-1",
                "priority": "high",
                "created": "2026-01-01T00:00:00Z",
                "state": "open",
            },
            {
                "id": "CASE-2",
                "priority": "low",
                "created": "2026-01-10T00:00:00Z",
                "state": "in_progress",
            },
        ],
        "sla_rules": [
            {"priority": "high", "max_resolution_hours": 4},
            {"priority": "low", "max_resolution_hours": 72},
        ],
    },
    "task.state.transition": {
        "task_id": "CASE-1",
        "target_state": "in_progress",
    },
    # ── 19 new capabilities — composability & coverage wave ──
    "agent.flow.branch": {
        "condition": "priority == 'critical'",
        "context": {"priority": "critical", "source": "monitoring"},
        "branches": [
            {"label": "escalate", "match": "priority == 'critical'"},
            {"label": "log", "match": "priority == 'low'"},
        ],
        "default_branch": "log",
    },
    "agent.flow.iterate": {
        "items": [
            {"id": "doc-1", "text": "First document."},
            {"id": "doc-2", "text": "Second document."},
        ],
        "capability": "text.content.summarize",
        "input_mapping": {"text": "$.text"},
    },
    "agent.flow.wait": {
        "condition": "approval_received",
        "timeout_seconds": 5,
    },
    "agent.flow.catch": {
        "error": {"type": "TimeoutError", "message": "Service unavailable"},
        "fallback_strategy": "default_value",
        "default_value": {"status": "degraded", "result": None},
    },
    "data.array.map": {
        "items": [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ],
        "expression": "item.name.upper()",
    },
    "data.field.map": {
        "record": {"first_name": "Alice", "last_name": "Smith", "age": 30},
        "mapping": {"first_name": "name", "last_name": "surname"},
        "drop_unmapped": False,
    },
    "data.record.join": {
        "records_a": [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ],
        "records_b": [
            {"id": 1, "dept": "Engineering"},
            {"id": 3, "dept": "Sales"},
        ],
        "key_field": "id",
        "join_type": "inner",
    },
    "data.record.merge": {
        "records": [
            {"name": "Alice", "role": "engineer"},
            {"name": "Alice", "dept": "platform", "level": "senior"},
        ],
        "strategy": "deep",
    },
    "message.content.format": {
        "data": {"user": "Alice", "action": "deployed", "service": "api-gateway"},
        "instruction": "Format a Slack notification summarizing the deployment.",
        "format": "markdown",
    },
    "web.request.send": {
        "url": "https://httpbin.org/get",
        "method": "GET",
    },
    "doc.content.generate": {
        "instruction": "Write a short project kickoff summary.",
        "context": "Project Alpha aims to migrate legacy services to Kubernetes.",
        "format": "markdown",
    },
    "task.event.schedule": {
        "title": "Weekly standup",
        "scheduled_time": "2026-04-01T09:00:00Z",
        "recurrence": "weekly",
    },
    "image.content.generate": {
        "prompt": "A simple blue rectangle on white background",
        "style": "minimal",
        "size": "256x256",
    },
    "table.sheet.read": {
        "path": "artifacts/sample.csv",
    },
    "table.sheet.write": {
        "path": "test_results/test_sheet_output.csv",
        "table": [
            {"name": "Alice", "score": 95},
            {"name": "Bob", "score": 87},
        ],
    },
    "agent.input.collect": {
        "fields": [
            {"name": "project_name", "type": "string", "required": True},
            {"name": "priority", "type": "string", "required": False},
        ],
        "instruction": "Collect project intake information.",
    },
    "text.content.compare": {
        "text_a": "The system is operational and running normally.",
        "text_b": "The system is functioning within expected parameters.",
    },
    "text.sentiment.analyze": {
        "text": "I absolutely love this new feature! It makes everything so much easier.",
    },
    "audio.speaker.diarize": {
        "audio": "artifacts/sample_audio.wav",
        "max_speakers": 3,
    },
}


def find_service_function(binding: BindingSpec) -> Tuple[Any, str]:
    """
    Find the actual Python function to call based on binding info.

    Returns: (module_object, function_name)
    """
    service_id = binding.service_id
    operation_id = binding.operation_id

    # Convert service ID to module name (e.g., text_baseline -> text_baseline)
    module_name = f"official_services.{service_id}"

    try:
        module = __import__(module_name, fromlist=[service_id])

        # Find the function - try operation_id as-is first, then with underscores
        func_name = operation_id
        if not hasattr(module, func_name):
            # Try with snake_case conversion
            func_name = operation_id.replace("-", "_")

        if hasattr(module, func_name):
            return module, func_name
        else:
            return None, None
    except Exception:
        return None, None


def select_binding_for_capability(
    binding_registry: BindingRegistry,
    capability_id: str,
) -> BindingSpec | None:
    """
    Select the execution binding using runtime semantics.

    Priority:
    1) official default binding id from policy
    2) first available binding as fallback (legacy behavior)

    For local testing we prefer bindings whose service module
    exists as a locally importable Python module.  If the default
    binding points to an external service (e.g. OpenAPI), we fall
    through to the next binding that resolves locally.
    """
    bindings = binding_registry.get_bindings_for_capability(capability_id)
    if not bindings:
        return None

    # Try official default first
    default_binding_id = binding_registry.get_official_default_binding_id(capability_id)
    if default_binding_id:
        try:
            default = binding_registry.get_binding(default_binding_id)
            if _binding_is_local(default):
                return default
        except Exception:
            pass

    # Fallback: first binding whose service resolves locally
    for b in bindings:
        if _binding_is_local(b):
            return b

    # Last resort: return whatever we have (will likely fail)
    return bindings[0]


def _binding_is_local(binding: BindingSpec) -> bool:
    """Return True if the binding's service module is importable locally."""
    module_name = f"official_services.{binding.service_id}"
    try:
        __import__(module_name, fromlist=[binding.service_id])
        return True
    except Exception:
        return False


def call_capability(
    capability_id: str, binding: BindingSpec, test_input: Dict[str, Any]
) -> Tuple[bool, str, Any]:
    """
    Call a capability's service function and return (success, reason, result).
    """
    try:
        module, func_name = find_service_function(binding)

        if not module or not func_name:
            return (
                False,
                f"Could not locate {binding.service_id}.{binding.operation_id}",
                None,
            )

        # Get the function
        func = getattr(module, func_name)

        # Build arguments from request template
        args = {}
        sig = inspect.signature(func)
        for param_name, value in binding.request_template.items():
            if isinstance(value, str) and value.startswith("input."):
                input_field = value[len("input.") :]
                if input_field in test_input:
                    args[param_name] = test_input[input_field]
                elif (
                    param_name in sig.parameters
                    and sig.parameters[param_name].default
                    is not inspect.Parameter.empty
                ):
                    continue  # skip optional params with defaults
                else:
                    return (
                        False,
                        f"Missing input field: {input_field} (for param: {param_name})",
                        None,
                    )
            else:
                args[param_name] = value

        # Call the function
        result = func(**args)

        # Check if result looks like a placeholder
        if isinstance(result, dict):
            has_placeholder = False
            for v in result.values():
                if isinstance(v, str) and "[" in v and "]" in v and len(str(v)) < 100:
                    # Looks like "[Placeholder text]"
                    has_placeholder = True
                    break
            if has_placeholder:
                return False, "Placeholder result detected", result

        return True, "OK", result

    except TypeError as e:
        error_msg = str(e)
        if "missing" in error_msg.lower():
            return False, f"Missing required argument: {error_msg[:60]}", None
        else:
            return False, f"Function signature mismatch: {error_msg[:60]}", None
    except Exception as e:
        return False, f"Error: {str(e)[:100]}", None


def test_all_capabilities():
    """Test all 33 capabilities."""

    # Initialize
    registry_root = Path(__file__).parent.parent / "agent-skill-registry"
    runtime_root = Path(__file__).parent

    capability_loader = YamlCapabilityLoader(registry_root)
    binding_registry = BindingRegistry(runtime_root, registry_root)

    # Get all capabilities
    all_capabilities = capability_loader.get_all_capabilities()
    print(f"Testing {len(all_capabilities)} capabilities...\n")

    results = {"functional": [], "placeholder": [], "error": [], "skipped": []}

    for capability_id in sorted(all_capabilities.keys()):
        all_capabilities[capability_id]

        # Get binding
        binding = select_binding_for_capability(binding_registry, capability_id)
        if binding is None:
            results["skipped"].append(
                {"id": capability_id, "reason": "No binding found"}
            )
            continue

        # Get test data
        test_input = TEST_DATA.get(capability_id)
        if not test_input:
            results["skipped"].append(
                {"id": capability_id, "reason": "No test data defined"}
            )
            continue

        # Call capability
        success, reason, result = call_capability(capability_id, binding, test_input)

        if success:
            results["functional"].append(
                {
                    "id": capability_id,
                    "binding": binding.id,
                    "service": binding.service_id,
                    "status": reason,
                }
            )
        elif "Placeholder" in reason:
            results["placeholder"].append(
                {
                    "id": capability_id,
                    "binding": binding.id,
                    "service": binding.service_id,
                    "reason": reason,
                }
            )
        else:
            results["error"].append(
                {
                    "id": capability_id,
                    "binding": binding.id,
                    "service": binding.service_id,
                    "reason": reason,
                }
            )

    # Report summary (informational — external network calls may flake)
    total = sum(len(v) for v in results.values())
    functional = len(results["functional"])
    print(f"\n{'=' * 60}")
    print(f"Capabilities tested: {total}")
    print(f"  Functional:   {functional}")
    print(f"  Placeholder:  {len(results['placeholder'])}")
    print(f"  Skipped:      {len(results['skipped'])}")
    print(f"  Errors:       {len(results['error'])}")
    if results["error"]:
        for e in results["error"]:
            print(f"    ⚠ {e['id']}: {e['reason'][:80]}")
    print(f"{'=' * 60}")
    # At least 50% of tested capabilities should be functional
    tested = functional + len(results["placeholder"]) + len(results["error"])
    assert tested > 0, "No capabilities were tested"
    assert functional / tested >= 0.5, (
        f"Only {functional}/{tested} capabilities functional"
    )


def print_results(results: Dict):
    """Pretty print results."""

    print("\n" + "=" * 80)
    print("CAPABILITY TEST RESULTS")
    print("=" * 80)

    # Functional
    print(f"\n✅ FUNCTIONAL ({len(results['functional'])})")
    print("-" * 80)
    for item in results["functional"]:
        print(f"  {item['id']:30} | {item['binding']:30} | {item['service']}")

    # Placeholders
    print(f"\n⚠️  PLACEHOLDER/STUB ({len(results['placeholder'])})")
    print("-" * 80)
    for item in results["placeholder"]:
        print(f"  {item['id']:30} | {item['reason'][:48]}")

    # Errors
    print(f"\n❌ ERROR ({len(results['error'])})")
    print("-" * 80)
    for item in results["error"]:
        print(f"  {item['id']:30} | {item['reason'][:48]}")

    # Skipped
    if results["skipped"]:
        print(f"\n⏭️  SKIPPED ({len(results['skipped'])})")
        print("-" * 80)
        for item in results["skipped"]:
            print(f"  {item['id']:30} | {item['reason']}")

    # Summary
    total = (
        len(results["functional"])
        + len(results["placeholder"])
        + len(results["error"])
        + len(results["skipped"])
    )
    print("\n" + "=" * 80)
    print(
        f"SUMMARY: {len(results['functional'])}/{total} functional | {len(results['placeholder'])} stubs | {len(results['error'])} errors"
    )
    print("=" * 80 + "\n")

    return len(results["error"]) == 0


def main():
    try:
        results = test_all_capabilities()
        success = print_results(results)
        return 0 if success else 1
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
