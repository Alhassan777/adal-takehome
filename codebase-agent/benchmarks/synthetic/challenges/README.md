# Synthetic Challenges

Each file in this directory is an independent challenge module. Every module exposes a single `generate(size: SizeTier) -> SyntheticRepo` function that builds a synthetic Python project and a list of ground-truth questions with known-correct answers.

There are **11 challenges × 5 size tiers = 55 repos** in the full matrix. Size tiers range from XS (~5 files) to XL (~200+ files); the same structural patterns and questions scale up with the repo.

---

## Challenge Index

| File | What it tests | Difficulty range |
|---|---|---|
| [`basic_nav.py`](#basic_navpy) | Symbol lookup, text search, file listing | Easy |
| [`import_chains.py`](#import_chainspy) | Re-exports, aliases, relative imports, circular deps | Medium–Hard |
| [`deep_hierarchy.py`](#deep_hierarchypy) | Navigation through deeply nested packages | Medium–Hard |
| [`name_collision.py`](#name_collisionpy) | Disambiguating identically-named symbols | Medium–Hard |
| [`inheritance.py`](#inheritancepy) | MRO, method overrides, mixin patterns | Medium–Hard |
| [`dependency.py`](#dependencypy) | Topological ordering, diamond deps, blast radius | Medium–Hard |
| [`test_mapping.py`](#test_mappingpy) | Mapping source files to their tests, finding gaps | Easy–Hard |
| [`dead_code.py`](#dead_codepy) | Detecting unused and transitively dead symbols | Medium–Hard |
| [`cross_cutting.py`](#cross_cuttingpy) | Decorators, plugin registries, dynamic dispatch | Medium–Hard |
| [`api_surface.py`](#api_surfacepy) | Public vs private API via `__all__` and conventions | Easy–Medium |
| [`route_detection.py`](#route_detectionpy) | HTTP route decorator extraction and counting | Easy–Medium |

---

## `basic_nav.py`

**Skill tested:** The foundational layer — symbol lookup, text search, and file listing. Every other challenge builds on these.

**Repo structure:** A flat order-processing project:
- `models.py` — `Order` and `Product` dataclasses
- `services.py` — business logic that imports from models
- `utils.py` — shared helper functions (`format_currency`, `slugify`, `clamp`)
- `main.py` — entry point importing from all three

Larger tiers add `validators.py`, `auth.py`, `database.py`, `cache.py`, `notifications.py`, and a numbered `extras/module_NNN.py` filler package.

**Questions:**

| ID | Question | Workflow | Difficulty |
|---|---|---|---|
| bn_q1 | Where is the `Order` class defined? | SYMBOL_LOOKUP | Easy |
| bn_q2 | Where is `process_order` defined? | SYMBOL_LOOKUP | Easy |
| bn_q3 | Which files import from `models.py`? | REVERSE_IMPORT_TRACING | Easy |
| bn_q4 | Search for the text "currency" in the codebase | TEXT_SEARCH | Easy |
| bn_q5 | What does `main.py` import? | IMPORT_TRACING | Easy |
| bn_q6 | List all Python files in the project | FILE_LISTING | Easy |
| bn_q7 *(M/L/XL)* | Where is `validate_email` defined? | SYMBOL_LOOKUP | Easy |
| bn_q8 *(M/L/XL)* | Where is the `connect` function for the database? | SYMBOL_LOOKUP | Medium |

---

## `import_chains.py`

**Skill tested:** Tracing imports through layers of indirection that a simple `grep` misses — `__init__.py` re-exports, aliased imports, relative imports, and circular dependencies resolved at function scope.

**Repo structure:**
- `core/` package: `engine.py`, `config.py`, `registry.py` with a `__init__.py` that re-exports all three
- `app.py`: consumes `Engine` and `Config` via the package-level re-export
- `adapters/http_adapter.py`: imports with aliases (`Engine as CoreEngine`, `Config as AppConfig`)
- `plugins/` sub-package with `base.py`, `loader.py`, and `contrib/logging_plugin.py` using `from ..base import`
- `circular/module_a.py` ↔ `circular/module_b.py`: mutual circular dependency broken by deferred function-level imports
- Larger tiers add many `ext_NN/handler_NNN.py` files all importing from `core.config`

**Questions:**

| ID | Question | Workflow | Difficulty |
|---|---|---|---|
| ic_q1 | Where is `Engine` actually defined? (`app.py` imports it from `core`) | GOTO_DEFINITION_HINT | Medium |
| ic_q2 | Trace the import of `Config` in `app.py` back to its source | IMPORT_TRACING | Medium |
| ic_q3 | In `http_adapter.py`, what does `CoreEngine` refer to? | GOTO_DEFINITION_HINT | Medium |
| ic_q4 | `from ..base import BasePlugin` in `logging_plugin.py` — where does it come from? | GOTO_DEFINITION_HINT | Medium |
| ic_q5 | How is the circular import between `module_a` and `module_b` resolved? | FEATURE_EXPLANATION | Hard |
| ic_q6 | Which files directly import from `core/config.py`? | REVERSE_IMPORT_TRACING | Medium |

---

## `deep_hierarchy.py`

**Skill tested:** Navigation through many levels of nested packages to find a symbol buried at maximum depth, plus the ability to describe the overall architecture without getting lost.

**Repo structure:** A progressively deeper package tree: `app/services/auth/providers/backends/drivers/adapters/` (depth 3–7 by tier). The "needle" is `OAuthHandler` in `oauth_handler.py` at the deepest level. Sibling modules (`session.py`, `token_store.py`, `permissions.py`, …) exist at each depth level. `main.py` imports directly from the deepest module.

**Questions:**

| ID | Question | Workflow | Difficulty |
|---|---|---|---|
| dh_q1 | Where is the `OAuthHandler` class defined? | SYMBOL_LOOKUP | Hard |
| dh_q2 | What is the `authenticate` method in `OAuthHandler` and where is it? | GOTO_DEFINITION_NO_FILE | Hard |
| dh_q3 | Describe the architecture — what are the nested package layers? | ARCHITECTURE_MAP | Medium |
| dh_q4 | Give an overview of the `services/` package | MODULE_OVERVIEW | Medium |

---

## `name_collision.py`

**Skill tested:** Symbol disambiguation when many files define identically-named classes and functions. The agent must use import context, package structure, and domain clues to resolve "which `Handler`?" rather than returning an ambiguous list.

**Repo structure:** Up to 25 `handlers/{domain}/handler.py` files each containing a class named `Handler` (domains: `http`, `websocket`, `grpc`, `events`, `queue`, `email`, …). Each domain also has a `validate.py` with a function named `validate`. `server.py` imports specifically from `handlers.http.handler`; `worker.py` imports from `handlers.events.handler` as `EventHandler`.

**Questions:**

| ID | Question | Workflow | Difficulty |
|---|---|---|---|
| nc_q1 | In `server.py`, where is the `Handler` it imports actually defined? | GOTO_DEFINITION_HINT | Hard |
| nc_q2 | Where is the `Handler` that handles WebSocket connections? | GOTO_DEFINITION_NO_FILE | Hard |
| nc_q3 | How many files contain a class named `Handler`? | SYMBOL_LOOKUP | Medium |
| nc_q4 | Where is the `validate` function used in `server.py` defined? | GOTO_DEFINITION_HINT | Hard |
| nc_q5 | In `worker.py`, `EventHandler` is an alias — what does it point to? | GOTO_DEFINITION_HINT | Hard |

---

## `inheritance.py`

**Skill tested:** Following class hierarchies to determine which method implementation actually runs (through `super()` chains), where overrides live, and how Python MRO resolves multiple inheritance with mixins.

**Repo structure:**
- `processors/` package: a linear chain `BaseProcessor → ValidatingProcessor → LoggingProcessor → … → FinalProcessor` (depth 3–7 by tier). Every class overrides `process()` and calls `super()`; `validate()` is only overridden at layer 2.
- `mixins/serializable.py`, `mixins/loggable.py`, `mixins/cacheable.py`: standalone mixin classes
- `composite.py`: `CompositeProcessor(BaseProcessor, SerializableMixin, LoggableMixin, CacheableMixin)` — full multiple inheritance
- Larger tiers add many `extensions/ext_NNN.py` single-level subclasses

**Questions:**

| ID | Question | Workflow | Difficulty |
|---|---|---|---|
| inh_q1 | Calling `process()` on a `FinalProcessor` — which file contains the first `process()` that runs? | CALL_GRAPH | Hard |
| inh_q2 | Where is `validate()` overridden in the `BaseProcessor` hierarchy? | SYMBOL_LOOKUP | Hard |
| inh_q3 | What is the full inheritance chain for `FinalProcessor`? | FEATURE_EXPLANATION | Medium |
| inh_q4 | What is the MRO for `CompositeProcessor`? | FEATURE_EXPLANATION | Hard |
| inh_q5 | Where is `to_dict()` defined when called on a `CompositeProcessor`? | GOTO_DEFINITION_NO_FILE | Medium |

---

## `dependency.py`

**Skill tested:** Dependency graph analysis — correct topological ordering of files, detecting diamond dependencies, identifying a fan-out hub module, and estimating the blast radius of a change.

**Repo structure:**
- `chain/` package: linear `types → validators → services → controllers`, each importing the previous via `from .prev import *`
- `diamond/` package: `foundation.py` ← `branch_left.py` and `branch_right.py` ← `aggregator.py` — classic diamond
- `hub/` package: `core.py` (`CoreService`, `get_core_instance`) imported by N `consumer_NNN.py` files (N = 3–50 by tier)

**Questions:**

| ID | Question | Workflow | Difficulty |
|---|---|---|---|
| dep_q1 | Correct dependency order for `chain/` (leaf first)? | DEPENDENCY_GRAPH | Medium |
| dep_q2 | What is the dependency structure of `diamond/`? Which module is at the bottom? | DEPENDENCY_GRAPH | Medium |
| dep_q3 | If I change `Foundation.create()`, what files are affected? | IMPACT_ANALYSIS | Medium |
| dep_q4 | Which module in `hub/` is the most-imported? How many files depend on it? | REVERSE_IMPORT_TRACING | Medium |
| dep_q5 | What is the impact of changing `CoreService.execute()`? | IMPACT_ANALYSIS | Hard |
| dep_q6 | If I rename `get_core_instance`, what would break? | BREAKING_CHANGE | Hard |

---

## `test_mapping.py`

**Skill tested:** Discovering test coverage — matching source files to their tests across multiple directory conventions, and identifying source files with no test coverage at all.

**Repo structure:**
- `src/` package: `models.py`, `auth.py`, `orders.py` *(intentionally untested)*, `notifications.py` *(intentionally untested)*, `utils.py`, `cache.py`
- Tests in three different layouts simultaneously:
  - **Co-located** — `src/test_utils.py` (test file lives beside the source file)
  - **Separate mirror tree** — `tests/test_models.py`, `tests/test_auth.py`, `tests/test_cache.py`
  - **Shared fixtures** — `tests/conftest.py` with `sample_user` and `admin_user` pytest fixtures
- Larger tiers add more source modules with ~60% getting a corresponding test file

**Questions:**

| ID | Question | Workflow | Difficulty |
|---|---|---|---|
| tm_q1 | Which test files cover `src/models.py`? | TEST_DISCOVERY | Easy |
| tm_q2 | Which test files cover `src/utils.py`? (co-located test) | TEST_DISCOVERY | Medium |
| tm_q3 | Which source files in `src/` have no test coverage? | MISSING_TESTS | Hard |
| tm_q4 | Are there tests for the `Order` class in `src/orders.py`? | TEST_DISCOVERY | Medium |
| tm_q5 | What does `conftest.py` provide and which tests use its fixtures? | FEATURE_EXPLANATION | Medium |

---

## `dead_code.py`

**Skill tested:** Detecting symbols and files that are defined but unreachable from any live import path — including transitively dead code (a symbol is only imported by another dead module).

**Repo structure:**
- **Live path**: `main.py` → `core/processor.py` (`Processor`), `core/config.py` (`get_config`)
- **Directly dead**: `core/legacy_processor.py` (`LegacyProcessor`, `legacy_init`) — never imported; `core/experimental.py` (`experimental_transform`, `ExperimentalCache`) — never imported
- **Transitively dead**: `core/orphan_utils.py` (`format_legacy_output`) — only imported by `legacy_processor.py`, which is itself dead
- **Dead file with a tricky guard**: `utils/deprecated.py` (`old_slugify`, `old_truncate`) — its `if False:` block makes the apparent `Processor` import unreachable
- Larger tiers add filler modules where every 3rd one is dead

**Questions:**

| ID | Question | Workflow | Difficulty |
|---|---|---|---|
| dc_q1 | Is `LegacyProcessor` still used anywhere? | DEAD_CODE | Medium |
| dc_q2 | Is it safe to delete `core/experimental.py`? | SAFE_REFACTORING | Medium |
| dc_q3 | `format_legacy_output` is only imported by `legacy_processor.py`. Is it dead? | DEAD_CODE | Hard |
| dc_q4 | Which symbols in the codebase are never used (dead code)? | DEAD_CODE | Hard |
| dc_q5 | Is the `Processor` class used? What references it? | DEAD_CODE | Easy |

---

## `cross_cutting.py`

**Skill tested:** Following execution paths that bypass static call graphs — decorator-based registration, plugin systems that self-register on import, and string-based dynamic dispatch via `importlib` / `getattr`.

**Repo structure:**
- `framework/router.py`: `@route(path)` decorator that registers handler functions in a `_ROUTES` dict; `dispatch(path)` resolves and calls them at runtime
- `routes/users.py`, `routes/products.py`, `routes/orders.py`: functions decorated with `@route(...)` — never appear in a normal call chain
- `plugins/registry.py`: `@register_plugin(name)` class decorator storing classes in `_PLUGINS`; `get_plugin(name)` instantiates them by name
- `plugins/json_plugin.py`, `plugins/csv_plugin.py`: self-registering plugin classes
- `dispatcher.py`: `COMMAND_MAP` dict + `dynamic_dispatch(module_name, func_name)` using `importlib.import_module` + `getattr`
- `app.py`: imports route and plugin modules purely for their side-effects (triggering decorator registration)
- Larger tiers add many `routes/auto_NNN.py` files

**Questions:**

| ID | Question | Workflow | Difficulty |
|---|---|---|---|
| cc_q1 | Which function handles the route `"/users/create"`? | FEATURE_EXPLANATION | Medium |
| cc_q2 | What routes are registered and where are their handlers? | FEATURE_EXPLANATION | Hard |
| cc_q3 | What class is registered as the `"json"` plugin? | FEATURE_EXPLANATION | Medium |
| cc_q4 | How does the plugin system work — how are plugins registered and retrieved? | FEATURE_EXPLANATION | Medium |
| cc_q5 | When `execute_command("list_users")` is called, which function actually runs? | CALL_GRAPH | Hard |
| cc_q6 | Why does `app.py` import `routes.users` without using any name from it? | FEATURE_EXPLANATION | Hard |

---

## `api_surface.py`

**Skill tested:** Determining the public API boundary of a package using `__all__`, underscore naming conventions, and `__init__.py` re-exports — including tracing a re-exported symbol back to its actual definition file.

**Repo structure:**
- `sdk/` package: `__init__.py` re-exports four public symbols with an explicit `__all__`
  - `client.py`: public `Client`, private `_ClientPool`
  - `models.py`: public `Request`, `Response`, private `_RawResponse`
  - `auth.py`: public `authenticate`, private `_refresh_token`, `_validate_signature`
  - `_internal.py`: entirely private module (`_build_headers`, `_parse_response`, `_retry_request`)
- `helpers/` package: no `__all__` — public/private determined purely by underscore convention; `strings.py` and `numbers.py` each mix public and `_private` functions
- Larger tiers add `sdk/extensions/ext_NNN.py` files with their own `__all__`

**Questions:**

| ID | Question | Workflow | Difficulty |
|---|---|---|---|
| api_q1 | What is the public API of the `sdk/` package? | API_SURFACE | Medium |
| api_q2 | Which symbols in `sdk/client.py` are public vs private? | API_SURFACE | Medium |
| api_q3 | Is `_RawResponse` part of the public SDK API? | API_SURFACE | Easy |
| api_q4 | Where is `authenticate` actually defined? (`sdk/__init__.py` re-exports it) | GOTO_DEFINITION_HINT | Medium |
| api_q5 | What is the public API of `helpers/`? (no `__all__` defined) | API_SURFACE | Medium |
| api_q6 | Give an overview of the `sdk/` module — what does it provide? | MODULE_OVERVIEW | Medium |

---

## `route_detection.py`

**Skill tested:** Detecting and cataloguing HTTP route decorators in FastAPI/Flask-style code — counting endpoints per file, distinguishing route files from plain utility modules, and summarising the full route table.

**Repo structure:**
- `api/users.py`: a `FastAPI()` app with 5 `@app.{get,post,put,delete}` endpoints (full CRUD for `/users`)
- `api/orders.py`: an `APIRouter(prefix="/orders")` with 3 `@router.*` endpoints
- `api/products.py`: an `APIRouter(prefix="/products")` with 2 endpoints plus a `ProductService` class (mixed file)
- `utils/helpers.py`: pure utility functions with **no routes** — the negative case
- Larger tiers add many `api/ext/resource_NNN.py` files with 2 endpoints each

**Questions:**

| ID | Question | Workflow | Difficulty |
|---|---|---|---|
| route_q1 | How many API endpoints does `api/users.py` define? | ROUTE_DETECTION | Easy |
| route_q2 | Which files define HTTP route handlers? | ROUTE_DETECTION | Medium |
| route_q3 | Give an overview of the `api/` directory | MODULE_OVERVIEW | Medium |
| route_q4 | What routes does `api/orders.py` define? | ROUTE_DETECTION | Medium |
| route_q5 | Does `utils/helpers.py` define any API endpoints? | ROUTE_DETECTION | Easy |
