# LazyLabel local panel

React, TypeScript and shadcn/ui frontend built by Vite. The production output is written directly to `../src/lazylabel/web/static/app/`, where FastAPI serves it from `/static/app/`.

```bash
npm ci
npm run dev
npm run build
```

The Vite dev server is for frontend work only. The local product serves the packaged build through LazyLabel's FastAPI process.
