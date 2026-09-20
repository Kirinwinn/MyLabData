# MyLabData Frontend

This directory contains the complete MyLabData React and TypeScript frontend:
Dashboard, Catalog, Molecules, Search, Import workflow, Jobs/SSE Activity, and
mutable Property editing.

The Dashboard reads health, database statistics, recent imports, and jobs from
the real `/api/v1` endpoints. Catalog displays Attribute definitions, Entries,
readable conditions, and statistics. Molecules provides paginated Lab ID/SMILES
lookup and a detail view whose typed Annotations are grouped by Attribute.
Import uses only backend-scanned Package IDs. It supports Incoming Packages,
Molecules and Annotation previews, conflict/error review, preview-token
confirmation, background import progress, and persistent import history.

Search builds type-safe Attribute/Entry conditions with AND/OR logic, restricts
operators and controls by Attribute value type, persists submitted requests and
pagination in the URL, and displays paginated Molecule summaries with backend
query timing.

The Activity page reads persistent Jobs and Imports, follows unfinished Jobs by
SSE, falls back to polling when streaming is unavailable, supports cancellation,
and retains complete failure details. The global Job tracker restores unfinished
work from the backend after refresh and invalidates the affected TanStack Query
caches when work reaches a terminal state.

Molecule Detail exposes an editor only for Entries whose catalog metadata is
`annotation_kind=property` and `is_mutable=true`. The editor chooses a typed
control from the Attribute value type, requires a change source, and follows
the accepted background job until completion or failure.

## Commands

The project uses the existing `MyLabData` Conda environment for both Python and
Node.js tooling. Activate it before installing or running the frontend:

```powershell
conda activate MyLabData
npm ci
npm run dev
npm run lint
npm run format:check
npm run typecheck
npm run test
npm run build
npm run openapi:generate
```

During development, Vite listens on `127.0.0.1:5173` and proxies requests whose
path begins with `/api` to FastAPI at `http://127.0.0.1:8000`.

## Production local run

Build the frontend first, then point FastAPI at the generated `dist` directory:

```powershell
conda run -n MyLabData npm run build --prefix frontend
$env:MLD_FRONTEND_DIST_DIRECTORY = "C:/Users/cenking/Documents/SwissTools/MyLabData/frontend/dist"
conda run -n MyLabData python -m uvicorn main:app --app-dir backend/src --host 127.0.0.1 --port 8000
```

With this optional setting, FastAPI serves the React application, its assets,
and SPA routes at `http://127.0.0.1:8000`, while `/api/v1` stays on the same
origin. Omitting the setting leaves the backend API-only, which is useful for
Vite development.

## API contract

`npm run openapi:generate` exports FastAPI's OpenAPI document and generates
TypeScript definitions in `src/api/generated`. Generated files are committed but
must not be edited by hand. `src/api/client.ts`, `errors.ts`, `queryKeys.ts`, and
`jobResults.ts` are the handwritten boundary around that contract.

The shared client always uses relative `/api/v1` paths, converts HTTP, FastAPI
`detail`, validation, network, abort, and invalid-response failures into
`ApiError`, and accepts `AbortSignal`. Query keys always begin with
`["mylabdata"]`, followed by resource, scope, and stable parameters.

Display conventions live in `src/lib/format.ts`: Chinese locale, browser-local
dates, at most six decimal places by default, a non-breaking space before units,
`是`/`否` for booleans, and `—` for missing or invalid values.

## Source layout

- `app`: application root, providers, router, and query client.
- `api`: generated OpenAPI types and the handwritten API boundary.
- `layouts`: shared page layouts.
- `features`: Dashboard, Catalog, Molecules, Search, and Jobs/Activity features.
- `components`: reusable UI components.
- `hooks`: reusable React hooks.
- `lib`: framework-independent frontend helpers.
- `styles`: global styles and future design tokens.
- `types`: handwritten types not generated from OpenAPI.
- `tests`: shared test setup.
