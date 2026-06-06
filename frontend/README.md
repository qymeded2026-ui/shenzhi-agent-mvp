
# Shenzhi Agent Frontend

This frontend is the Figma Make UI bundle copied into the main project as the
React/Vite shell. The left-side chat history, central chat stream, right
score/supervisor/case panel, clinician scale forms, and tongue image previews
are now connected to the local Python API. The chat header also supports model
selection and case selection before a conversation starts. New chat creation can
preselect case/model settings, and failed patient-generation requests can be
retried from the composer.

Original Figma source:
https://www.figma.com/design/c1m4UYqWTDqOUHQZ6zrMpz/Image-to-Figma-Design

## Run

From the project root:

```bash
scripts/start_api.sh
scripts/start_frontend.sh
```

Or, if your shell already has npm/pnpm:

```bash
cd frontend
pnpm install
pnpm dev
```

The dev server defaults to:

```text
http://localhost:5173/
```

The API server defaults to:

```text
http://127.0.0.1:8765/
```
