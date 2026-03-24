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
    "agent.task.delegate": {"agent": "agent1", "task": "summarize text"},
    "agent.plan.generate": {"objective": "Build a web scraper"},
    "agent.input.route": {"input": "What is machine learning?"},
    "audio.speech.transcribe": {"audio": b"fake audio data"},
    "code.diff.extract": {"code_a": "x = 5", "code_b": "x = 10"},
    "code.snippet.execute": {"code": "x = 5 + 3; print(x)", "language": "python"},
    "code.source.format": {"code": "def foo( x,y ):\n  return x+y", "language": "python"},
    "data.json.parse": {"text": '{"name": "John", "age": 30}'},
    "data.record.deduplicate": {
        "records": [
            {"id": 1, "name": "Alice"},
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"}
        ],
        "key_fields": ["id"]
    },
    "data.schema.validate": {"data": {"name": "John"}, "schema": {"type": "object"}},
    "doc.content.chunk": {"text": "This is a long document. " * 50, "chunk_size": 1000},
    "email.inbox.read": {"mailbox": "inbox"},
    "email.message.send": {"to": "test@example.com", "subject": "Test Subject", "body": "Test message body"},
    "fs.file.read": {"path": str(Path(__file__).resolve()), "mode": "text"},
    "image.caption.generate": {"image": b"fake image data"},
    "image.content.classify": {"image": b"fake image data", "labels": ["cat", "dog", "bird"]},
    "memory.entry.retrieve": {"key": "test_key"},
    "memory.entry.store": {"key": "test_key", "value": "test_value"},
    "message.notification.send": {"message": "Test message", "recipient": "test_user"},
    "ops.budget.estimate": {
        "plan": {"steps": [{"id": "s1"}, {"id": "s2"}]},
        "limits": {"max_cost": 1.0, "max_duration_ms": 5000}
    },
    "ops.trace.monitor": {
        "trace": {"duration_ms": 1200, "error_count": 1},
        "thresholds": {"max_duration_ms": 2000, "max_errors": 2}
    },
    "pdf.document.read": {"path": str(Path(__file__).parent / "artifacts" / "test.pdf")},
    "policy.constraint.validate": {
        "payload": {"title": "Hello", "body": "World"},
        "constraint": {"required_keys": ["title"], "forbidden_keys": ["password"]}
    },
    "provenance.citation.generate": {
        "source": {"url": "https://example.com/article", "title": "Example"},
        "excerpt": "Important fact",
        "locator": "p.10"
    },
    "provenance.claim.verify": {
        "claim": "Alice works at Example",
        "sources": [
            {"text": "Alice works at Example and leads product."},
            {"text": "Unrelated source"}
        ]
    },
    "eval.output.score": {
        "output": {"summary": "Short summary", "confidence": 0.9},
        "rubric": {"dimensions": {"completeness": 0.5, "clarity": 0.5}}
    },
    "security.output.gate": {
        "output": {"text": "Contact me at test@example.com"},
        "policy": {"block_pii": True, "block_secrets": True}
    },
    "security.pii.detect": {"text": "Email me at test@example.com"},
    "security.pii.redact": {"text": "Phone +1 650 555 1234 and email test@example.com"},
    "security.secret.detect": {"text": "token=sk-1234567890ABCDEFGHIJ"},
    "table.row.filter": {"table": [{"name": "Alice", "age": 25}, {"name": "Bob", "age": 30}], "condition": {"age": {"$gt": 26}}},
    "text.content.classify": {"text": "I love this product! It's amazing!", "labels": ["positive", "negative", "neutral"]},
    "text.content.embed": {"text": "This is a test sentence for embedding."},
    "text.content.generate": {"instruction": "Write a one-sentence description of Python.", "context": "Python is a programming language."},
    "text.entity.extract": {"text": "John Smith works at Google in Mountain View."},
    "text.content.extract": {"text": "<html><body><h1>Title</h1><p>This is a test paragraph with important information.</p></body></html>"},
    "text.keyword.extract": {"text": "Python is a great programming language for machine learning and data science applications."},
    "text.language.detect": {"text": "This is English text."},
    "text.response.extract": {"question": "What is Python?", "context": "Python is a high-level programming language created by Guido van Rossum. It emphasizes code readability."},
    "text.content.transform": {"text": "The system is operational and functioning within normal parameters.", "goal": "simplify for a non-technical audience"},
    "text.content.summarize": {"text": "Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience without being explicitly programmed. It focuses on the development of algorithms that can access data and use it to learn for themselves."},
    "text.content.merge": {"items": ["Hello", "World", "Merge test"]},
    "text.content.template": {"template": "Hello {{name}}, welcome to {{place}}!", "variables": {"name": "John", "place": "Agent Skills"}},
    "text.content.translate": {"text": "Hello world", "target_language": "es"},
    "video.frame.extract": {"video": b"fake video data"},
    "web.page.fetch": {"url": "https://www.google.com"},
    "web.page.extract": {"content": "<html><body><h1>Web Page</h1><p>Main content here.</p></body></html>"},
    "web.source.verify": {"url": "https://example.com/news"},
    "web.source.search": {"query": "machine learning"},
    "web.source.normalize": {"results": [{"url": "https://example.com/page", "title": "Example", "snippet": "A sample page."}], "mode": "quick"},
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
            func_name = operation_id.replace('-', '_')
        
        if hasattr(module, func_name):
            return module, func_name
        else:
            return None, None
    except Exception as e:
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


def call_capability(capability_id: str, binding: BindingSpec, test_input: Dict[str, Any]) -> Tuple[bool, str, Any]:
    """
    Call a capability's service function and return (success, reason, result).
    """
    try:
        module, func_name = find_service_function(binding)
        
        if not module or not func_name:
            return False, f"Could not locate {binding.service_id}.{binding.operation_id}", None
        
        # Get the function
        func = getattr(module, func_name)
        
        # Build arguments from request template
        args = {}
        for param_name, value in binding.request_template.items():
            if isinstance(value, str) and value.startswith("input."):
                input_field = value[len("input."):]
                if input_field in test_input:
                    args[param_name] = test_input[input_field]
                else:
                    # Missing required input
                    return False, f"Missing input field: {input_field} (for param: {param_name})", None
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
                return False, f"Placeholder result detected", result
        
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
    
    results = {
        "functional": [],
        "placeholder": [],
        "error": [],
        "skipped": []
    }
    
    for capability_id in sorted(all_capabilities.keys()):
        capability = all_capabilities[capability_id]
        
        # Get binding
        binding = select_binding_for_capability(binding_registry, capability_id)
        if binding is None:
            results["skipped"].append({
                "id": capability_id,
                "reason": "No binding found"
            })
            continue
        
        # Get test data
        test_input = TEST_DATA.get(capability_id)
        if not test_input:
            results["skipped"].append({
                "id": capability_id,
                "reason": "No test data defined"
            })
            continue
        
        # Call capability
        success, reason, result = call_capability(capability_id, binding, test_input)
        
        if success:
            results["functional"].append({
                "id": capability_id,
                "binding": binding.id,
                "service": binding.service_id,
                "status": reason
            })
        elif "Placeholder" in reason:
            results["placeholder"].append({
                "id": capability_id,
                "binding": binding.id,
                "service": binding.service_id,
                "reason": reason
            })
        else:
            results["error"].append({
                "id": capability_id,
                "binding": binding.id,
                "service": binding.service_id,
                "reason": reason
            })
    
    return results


def print_results(results: Dict):
    """Pretty print results."""
    
    print("\n" + "="*80)
    print("CAPABILITY TEST RESULTS")
    print("="*80)
    
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
    total = len(results["functional"]) + len(results["placeholder"]) + len(results["error"]) + len(results["skipped"])
    print("\n" + "="*80)
    print(f"SUMMARY: {len(results['functional'])}/{total} functional | {len(results['placeholder'])} stubs | {len(results['error'])} errors")
    print("="*80 + "\n")
    
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
