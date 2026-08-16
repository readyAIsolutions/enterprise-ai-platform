# Demiurge 3D — frontend contract

## Build & verify
- `cd /home/hunter/Desktop/demiurge-3d/frontend && npm run build` → `tsc && vite build`.
  Output `dist/`. The backend serves it from `STATIC_DIR`.
- TS strict: type API responses; avoid `any`. Fix the recurring errors below before
  declaring done.

## Tab nav (App.tsx)
- `type Tab = 'dashboard' | 'forge' | 'tuning' | 'store' | 'filaments' | 'files' | 'print'
  | 'settings' | 'about'`
- Buttons via `tabBtn(id, label, icon)` (emoji icons). Render:
  `{tab === 'filaments' && <FilamentManager />}` etc.
- New tabs added this session: `filaments` (🧵), `files` (📁), `print` (🎚️).

## Store (usePrinterStore, Zustand)
- `PrinterState.status` union is `'ready' | 'printing' | 'paused' | 'calibrating' | 'error'`
  — **must include `'paused'`** (the websocket handler sets it; omitting it is a TS2554).
- `useJobWebSocket` is exported as a hook and **called with an `activeJobId` arg** in
  `App.tsx` — keep its signature `( _activeJobId?: string | null )`.

## Components
- `components/filaments/FilamentManager.tsx` — spool grid (color swatch, remaining bar,
  temp badges), add/edit form (color picker + print-settings subsection), delete (confirm).
  Calls `/api/spools`.
- `components/files/FileLibrary.tsx` — drag-drop + click upload (POST `/api/files/upload`,
  field `file`), file table from `/api/files`.
- `components/settings/PrintSettings.tsx` — printer `<select>` from `/api/account`,
  load/save via `/api/printer/settings`. **Config only — no print/start buttons.**
- Styling: Tailwind dark (`bg-gray-900/800`, `text-gray-200/400`, `blue-600` buttons).
  Match existing components.

## Known TS pitfalls (this session)
- `PrinterState.status` missing `'paused'` → add to union.
- `useJobWebSocket()` called with 1 arg but defined with 0 → accept optional arg.
