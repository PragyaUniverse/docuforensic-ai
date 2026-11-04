# DocuForensic AI reviewer UI

React, Vite, TypeScript, Tailwind, shadcn-style Radix components, Framer Motion, Lucide, React Flow.

```bash
npm install
npm run dev        # http://localhost:5173, proxies /api to http://localhost:8000
npm run build
npm run lint
```

`VITE_PROXY_TARGET` changes the dev proxy target. `VITE_API_BASE` sets an absolute API origin for a
built bundle, which otherwise calls `/api` on its own origin.

`npm run dev:mock` serves invented fixtures with a visible MOCK DATA banner, for UI work without the
backend. The mock is imported only when `VITE_USE_MOCK=1`, so it isn't in the default build. Without
that flag, the UI shows real API data or an honest error, never fixtures.
