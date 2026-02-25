---
name: review-code
description: Review code for quality, best practices, and project standards. Use when reviewing PRs, checking code quality, or validating implementation against project guidelines.
---

# Code Review Guidelines

## General Principles

- Write correct, best practice code adhering to DRY principles
- Prioritize readability over performance
- Implement all requested functionality completely
- Avoid TODOs, placeholders, or incomplete sections
- Include all required imports
- Acknowledge limitations when appropriate

## Comments Policy

- New code must not contain stupid comments that add no value
- Do not remove useful existing comments
- No historical comments like `# removed X from here` - if it's removed, it's gone
- Only add comments where logic isn't self-evident
- Don't add docstrings, comments, or type annotations to code you didn't change

## Documentation: Current State Only

Code, comments, and documentation should describe **how things work now**, not migration history:

```python
# BAD: Historical context that doesn't help understanding
# We migrated from the old system where we used X, now we use Y
# Previously this was in module Z but we moved it here

# GOOD: Just describe current behavior
# Validates user input before processing
```

If migration context is truly needed (e.g., for deprecation warnings), keep it minimal and actionable.

## Formatting Rules

**CRITICAL**: Never fix formatting issues by rewriting code manually.

- Python: Run `uv run ruff check --fix`
- TypeScript/NextJS: Run `pnpm run lint:fix`

## Avoid Over-Engineering

- Only make changes directly requested or clearly necessary
- Don't add features, refactor code, or make "improvements" beyond what was asked
- A bug fix doesn't need surrounding code cleaned up
- A simple feature doesn't need extra configurability
- Don't add error handling for scenarios that can't happen
- Trust internal code and framework guarantees
- Only validate at system boundaries (user input, external APIs)
- Don't create helpers/utilities/abstractions for one-time operations
- Don't design for hypothetical future requirements
- Three similar lines of code is better than a premature abstraction

## No Overly Defensive Coding

Don't add defensive checks "just in case". Trust the types and explore them first:

```python
# BAD: Defensive chains when types guarantee the data exists
value = thing.get("key", {}).get("nested", {}).get("value") if thing else None

# GOOD: Trust the types, access directly
value = thing["key"]["nested"]["value"]

# BAD: Checking for None when type says it's not optional
if user and user.email:
    send_email(user.email)

# GOOD: Type says User has email, just use it
send_email(user.email)
```

Before adding defensive code:
1. Check the types - is the field actually optional?
2. Trace where the data comes from - is it validated upstream?
3. If truly uncertain, add proper type narrowing, not silent fallbacks

## No Backwards Compatibility (Unless Explicitly Requested)

**We don't do backwards compatibility by default.** Keep implementations clean:

- No "keeping this for backwards compatibility" code paths
- No deprecated parameter shims
- No re-exporting moved types/functions
- No renaming unused `_vars` to preserve signatures
- No `// removed` comments for deleted code
- If something is unused, delete it completely
- If an API changes, update all callers

Only add backwards compatibility if the user explicitly asks for it (e.g., public API with external consumers).

---

# Python Guidelines

## Standards

- Python 3.13 with modern type hints and generics
- Package management: `uv`
- Always use builtin typehints: `dict[str, int]` not `Dict`
- Prefer Pydantic models over bare dicts and dataclasses
- Prefer async functionality in asynchronous contexts
- Prefer functional and declarative patterns over objects

## Type Safety

- Type casting (`cast()`, `# type: ignore`) is an absolute last resort
- Avoid `Any` - find the correct type or use proper generics
- If you need a cast, first try to fix the underlying type issue

## Exception Formatting

When formatting exceptions, use `!r` (repr) not `!s` (str):

```python
# Good
logger.error(f"Failed to process: {e!r}")

# Bad
logger.error(f"Failed to process: {e}")
```

`!r` provides more debugging info (exception type, full details).

## Import Organization

- All imports must be at the top of the module
- Inline/local imports are only allowed as a **last resort** for circular imports
- If you have circular imports, first try to refactor modules to break the cycle

## Testing with pytest

```bash
uv run pytest
```

Principles:
1. Test one thing at a time, no huge test cases
2. No multiple asserts testing different things
3. Use `pytest-*` libs (pytest-mock), not `unittest`
4. Work on a single test at a time
5. Use pytest fixtures or factories
6. Minimize mocking unless absolutely necessary - refactor code for testability

---

# TypeScript/NextJS Guidelines

## Standards

- Modern App router (Next.js 15.2+)
- Functional components with React hooks
- Package management: `pnpm`

**Note:** A Next.js 16 documentation MCP server is available (`nextjs-docs`) which can be used to validate best practices and API usage against official docs.

## useEffect Anti-Pattern

**Avoid excessive `useEffect`** - prefer derived state/useMemo.

Using useEffect for anything but synchronizing with third-party APIs (remote subscriptions, etc.) is wrong. ESPECIALLY for syncing local React state.

Instead use:
- `useMemo` for derived values
- `key=` prop to reset component state
- Derived state computed during render
- Lifting state up

Reference: https://react.dev/learn/you-might-not-need-an-effect

## useMemo Guidelines

Only use `useMemo` if caching saves meaningful compute. Never `useMemo` for simple one-or-two liners without function calls.

## Server Actions

- Implement in dedicated `actions.ts` files
- Prefer server actions over HTTP endpoints
- Abstract logic into lib files, call from server actions

## Testing

- Unit/Integration: `pnpm run test` (vitest + react-testing-library)
- E2E: `pnpm run cypress:run`
- Focus on behavior, not implementation details
- Avoid overtesting and very slow tests

---

# Debugging Approach

1. **Reason first**: Think about the problem and errors before implementing a solution
2. **Avoid workarounds**: When first approach doesn't work, don't add hacks
3. **Gather evidence**: Add logs, use debugging tools to understand what's happening
4. **Minimal reproduction**: Consider implementing a minimal example demonstrating the issue
5. **Test-driven debugging**: Write a test and iterate against that

---

# Code Patterns

## Functional Over Object-Oriented

Prefer functional and declarative patterns over objects:
- Easier to test
- Easier to reason about
- Break long code blocks into nicely named functions

## Data/Rendering Separation (React)

Separate data preparation logic from TSX rendering:
- Instead of returning same TSX blocks with different data in multiple conditions
- Prepare data in conditions, render once at the end

```typescript
// Good
const displayData = condition ? dataA : dataB;
return <Component data={displayData} />;

// Bad
if (condition) {
  return <Component data={dataA} />;
} else {
  return <Component data={dataB} />;
}
```

---

# Generated Files

Never directly edit generated files:
- `@cohort/portal/src/lib/engine_api/generated` - regenerate with `pnpm run openapi-ts`
- `portal/src/lib/db/types.gen.ts` - database types

---

# Tracing Review

When reviewing code that involves tracing or should have tracing, consider:

## Opportunities for Tracing

- **New async workflows**: Should key functions have `@observe()` decorators?
- **Service boundaries**: Is context being propagated correctly?
- **Debugging value**: Would traces help debug this code in production?

## Trace Size Concerns

- **`capture_input=True` on large data**: If a function processes lists/dicts of user data (artifacts, tables), capturing full I/O can create 20MB+ traces
- **Manual `update_span(output=...)`**: Is large data being added to spans?
- **Generation spans are OK**: LLM input/output capture is expected and useful

```python
# Review for: Is artifacts potentially large?
@observe(span_type="tool", capture_input=True)  # Could be problematic
async def process_artifacts(artifacts: list[dict]):
    ...
```

## Context Propagation

- **Celery tasks**: Context should be serialized in task args (we have harness for this)
- **HTTP calls**: HTTPX auto-propagates (should work automatically)
- **Custom queues/workers**: Need manual `serialize_context()`/`deserialize_context()`

## Short-Running Scripts

- Does the script call `force_flush()` before exit?
- Without it, traces may not be exported

See `use-langfuse/using-tracing.md` for full tracing guidelines.

---

---

# Review Checklist

- [ ] No manual formatting fixes (use linters)
- [ ] No unnecessary useEffect
- [ ] No useless comments, no historical "removed X" comments
- [ ] No TODOs or placeholders
- [ ] Exceptions use `{e!r}` not `{e}`
- [ ] No type casts or Any without good reason
- [ ] Imports at top of module (no inline imports unless circular)
- [ ] No over-engineering
- [ ] No backwards-compatibility hacks
- [ ] Tests focus on behavior, not implementation
- [ ] Generated files not manually edited
- [ ] Type hints use modern Python syntax
- [ ] Functional patterns preferred
- [ ] Tracing: No huge data in `capture_input`/`capture_output` for non-LLM spans
- [ ] Tracing: Context propagation across service boundaries
- [ ] Large files (>100KB): Check `.gitattributes` has LFS auto-tracking; verify with `git lfs ls-files` if unsure
