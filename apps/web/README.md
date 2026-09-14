English edition of apps/web/README.md, translated for the hackathon submission (2026).

# CampusPath Student Web App (WP7)

D1's 14 pages. Next.js 16 + Tailwind 4 + motion, managed with bun.
All data comes from `/v1` — the frontend has **zero hardcoded business data**.

## Running it

```bash
make api                       # from the repo root: FastAPI starts on :8000
cd apps/web && bun install && bun run dev --port 3100
```

Open `http://127.0.0.1:3100` in a browser. The frontend proxies `/api/*` to `:8000` via a rewrite in
`next.config.ts`, so it's **same-origin and needs no CORS** — the API side doesn't have to open up cross-origin
access just for a demo frontend, which is one less relaxation someone would have to remember to revoke.

## Design direction: "Soft Clay × Verifiable" (v2, refactored 2026-08-01)

Claymorphism (soft variant) × Claude's warm palette: oat-cream base (`--color-oat-*`),
embossed white cards (soft outer shadow + inner highlight), terracotta-orange accent (`--color-terra-*`).
Design follows the `ui-ux-pro-max` skill; the full token table is in
`docs/CampusPath_Design_Tokens_v2.0_Clay_2026-08-01.md`.

Three gates are enforced with each batch (`apps/web/scripts/`): `check-contrast.mjs`
(80 combinations × both themes, real WCAG computation), `check-alignment.mjs` (pixel-level comparison of the
skeleton across pages — page transitions must not jump), `run-pages-must.mjs` (`data-*` structural regression).

Sandstone ochre (`--color-ochre-*`) remains the exclusive vocabulary of UNKNOWN, spent only on two
**signature elements**:

| Signature element | Where | Why it's this |
|---|---|---|
| **Tri-state indicator** `TriState` | `components/ui.tsx` | UNKNOWN uses a **hatched pattern**, neither green nor red. The whole product is built on "couldn't be parsed ≠ you're not eligible," and the color system has to acknowledge the third state |
| **Credential chip** `CredentialChip` | same as above | Any conclusion coming from Rules carries a chip with a real `validation_id`. A visible audit trail is worth more than a claim of "we're being rigorous" |

Interaction physics follow the `ui-ux-pro-max` UX rules: default spring `bounce 0`,
`duration 0.3–0.4`; feedback on press (<100ms) rather than waiting for `click`; press scale 0.97
with a 260ms light overshoot on release; `prefers-reduced-motion` / `reduced-transparency` / `contrast: more`
each have their own degradation path.

## Bilingual support

`src/i18n/en.ts` is the dictionary's **type source**; `zh-Hans.ts` is declared as
`Record<keyof Dict, string>`, so **a missing key or a misspelled key fails `tsc`**.
i18n completeness is therefore a type-level fact, not a matter of discipline.

The language choice is persisted in `localStorage` and also synced to `<html lang>`; `layout.tsx` has an
inline script that sets lang/theme before hydration to avoid a first-paint flash.

⚠️ **Known gap**: the reasoning text produced by the Rules / Wellbeing services is currently monolingual
Chinese prose; when it's placed into `LocalizedText`, both sides get filled with the same string, so in English
mode the "why wasn't this recommended" drawer's reasoning still shows Chinese. See task U7.

## Browser verification

`verify/pages.mjs` is the machine-checkable checklist for D1's "page completeness." Assertions are always based on
`data-*` attributes, **never on copy text** — assertions based on wording would fail across the board the moment
the language switches, and bilingual testing would become theater.

The last item on the checklist is a **deliberately unmatchable selector**: it must fail, otherwise it proves the
whole assertion suite isn't actually asserting anything (Plan §10 H5).

Screenshots are stored under `docs/verification/wp7/`.

## Three issues found through hands-on testing

1. **Next 16's root layout cannot hand-write `<head>`** (`node_modules/next/dist/docs/…/layout.md:141`).
   The failure mode isn't an error — it's that **the whole page silently fails to hydrate**: the SSR HTML renders
   as normal and looks completely fine, but effects don't run, `onClick` doesn't work, and there isn't a single red
   line in the console.
2. **The dev server only recognizes `localhost` by default** — accessing it via `127.0.0.1` gets `/_next/*`
   blocked as cross-origin, with symptoms identical to the issue above. Fixed by adding it to `allowedDevOrigins`.
3. **A component that doesn't forward `...rest` silently swallows `data-*`** attributes, so the test assertions
   find nothing, and you can't tell "the page is broken" apart from "the attribute got eaten by a component."
   `Card` has been changed to forward its rest props.

All three were found by actually clicking through the app by hand — reading the code, running `tsc`, and running
`bun run build` were all green.
