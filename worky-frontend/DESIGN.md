# Worky — Frontend Design Document

> **Audience:** All developers contributing to the Worky frontend.
> **Purpose:** Define the product vision, design principles, UI guidelines, component architecture, and backend/frontend responsibilities that govern this codebase.
> **Scope:** Frontend only. Backend architecture is documented in `worky-backend/docs/architecture/ARCHITECTURE.md`.
> **Status:** Living document. Update this file when design decisions change.

---

## Table of Contents

1. [Product Vision](#1-product-vision)
2. [Design Principles](#2-design-principles)
3. [UI Guidelines](#3-ui-guidelines)
4. [Widget Behaviour](#4-widget-behaviour)
5. [Frontend Architecture](#5-frontend-architecture)
6. [Backend / Frontend Responsibilities](#6-backend--frontend-responsibilities)
7. [Future Roadmap](#7-future-roadmap)
8. [Non-Goals](#8-non-goals)

---

## 1. Product Vision

### What Worky is

Worky is an intelligent desktop work companion. It sits alongside an employee throughout their workday as a lightweight, always-visible widget that surfaces the most important information from their enterprise tools — meetings, emails, messages, and AI-generated priorities — without requiring them to switch context.

### The problem it solves

Knowledge workers lose significant time and cognitive energy to context switching: opening Outlook to check email, opening Teams or Slack for messages, opening a calendar to review the next meeting, and then trying to remember what the most urgent task was. Each switch costs attention and breaks flow.

Worky eliminates those switches. It presents a unified, pre-prioritised snapshot of the working day, updated automatically, in a single compact widget that never needs to be "opened."

### Why it exists

Enterprise productivity tools are designed to be the centre of attention. Worky is designed to be peripheral — a calm information surface that exists at the edge of awareness. It answers "what should I focus on right now?" without requiring any user action.

IBM Bob provides the intelligence layer: it ingests structured data from every connected enterprise tool and reasons about what matters. Worky presents Bob's output in its simplest possible form.

### Why a desktop widget rather than a traditional application

A web application demands attention. It lives in a browser tab, competes with other tabs, and requires the user to navigate to it. An Electron or Tauri widget lives as a persistent presence on the desktop — visible without a click, ignorable without closing, and always current. This form factor is the correct one for ambient, glanceable productivity information. It is not a dashboard the user visits; it is a companion that is always there.

---

## 2. Design Principles

### 1. Desktop-first

Every design decision must be evaluated from the perspective of a desktop widget, not a web page. Spacing, typography sizes, button dimensions, and interaction patterns should reflect the density and precision of native desktop applications, not the generous whitespace of mobile-first web design.

### 2. Glanceable in under five seconds

A user should be able to read the most important information from the widget in a single glance without scrolling, tapping, or any deliberate interaction. The top of the content area is the most valuable real estate and must always show the highest-priority item.

### 3. Minimal cognitive load

The widget should never make the user think. Labels must be short and unambiguous. Status indicators must be self-evident. Actions must be obvious. If a user needs to read a tooltip to understand what something means, the design has failed.

### 4. Compact information density

Every pixel of vertical space counts. Padding should be functional, not decorative. Section dividers should use subtle colour contrast rather than heavy borders. Text sizes should be small but legible. The goal is to fit as much useful information as possible without feeling cramped.

### 5. Content-first hierarchy

Structure and chrome serve content. Section headers should be muted and small — they are navigational labels, not headings. The actual information (meeting title, email subject, sender name) should be the visually dominant element in each section.

### 6. One-window experience

The widget is a single window. There are no modals, no drawers, no nested navigation, no settings pages. If a piece of information cannot be surfaced within the widget's single scrollable content area, it belongs in the source application, not in Worky.

### 7. Progressive disclosure

Show the most important information first. Additional detail (body preview, join URL, email snippet) is secondary — it should be present but recessive. Phase 3 and beyond may reveal more detail on hover or focus, but the default state is always the summary view.

### 8. Calm, unobtrusive presence

Worky should not draw attention to itself. Colours should be neutral with selective use of accent colour only for actionable or urgent items. No animations should be gratuitous — motion is reserved for state transitions (loading, appearing) and must be brief. The widget should never pulse, bounce, or flash.

### 9. No unnecessary navigation

Screen transitions are state changes, not page navigations. There are no URLs, no back buttons, no breadcrumbs. The widget moves between states (setup, loading, dashboard) using in-memory React state. This is not a simplification — it is correct for this form factor.

---

## 3. UI Guidelines

### Typography

| Context | Size | Weight | Colour |
|---|---|---|---|
| Widget title ("Worky") | `text-sm` (14px) | `font-semibold` | `text-gray-900` |
| Section headers | `text-[11px]` | `font-medium` | `text-gray-400` |
| Primary content (meeting title, email subject) | `text-sm` (14px) | `font-medium` | `text-gray-800` |
| Secondary content (sender, organiser, time) | `text-xs` (12px) | `font-normal` | `text-gray-500` |
| Body preview | `text-xs` (12px) | `font-normal` | `text-gray-400` |
| Footer / captions | `text-[10px]` | `font-medium` | `text-gray-300` |
| User identity in header | `text-xs` (12px) | `font-normal` | `text-gray-400` |

**Rules:**
- Never use `uppercase` + `tracking-wide` for section headers. This is a web dashboard pattern. Use lowercase `font-medium` at reduced colour instead.
- Never use heading tags (`h1`, `h2`) for labels inside the widget. Content labels are `<p>` or `<span>`, not document headings.
- System font stack only: `-apple-system, "Segoe UI", system-ui, sans-serif`. No web fonts, no Google Fonts. The widget must render correctly in an offline Electron environment.

### Spacing

| Location | Value |
|---|---|
| Widget horizontal padding | `px-4` (16px) |
| Section top padding | `pt-3` (12px) |
| Section bottom padding | `pb-2` (8px) |
| Item internal vertical gap | `gap-1` or `gap-1.5` |
| Header vertical padding | `py-2.5` (10px) |
| Footer vertical padding | `py-1.5` (6px) |
| Setup screen vertical padding | `py-8` (32px) |

**Rule:** When in doubt, use less space. Vertical whitespace is not a signal of quality in a widget; it is a signal of poor density.

### Corner Radius

| Element | Value | Reason |
|---|---|---|
| Widget frame | `rounded-xl` (12px) | Desktop-native panel feel; `rounded-2xl` reads as a web card |
| Buttons | `rounded-md` (6px) | Standard interactive element |
| Status badge | `rounded-full` | Pill shape communicates categorical status |
| Status dot | `rounded-full` | Circular indicator |
| Error banner | `rounded-md` (6px) | Matches button radius for visual consistency |

### Cards

Worky does not use material-style lifted cards within sections. Items in a list (meetings, emails) are row-level elements with `hover:bg-gray-50` feedback. There are no card shadows inside the widget content area. The widget frame itself carries the only elevation.

### Section Headers

Section headers are navigation labels, not visual anchors. They must be:
- Lowercase (no uppercase or title case)
- `text-[11px] font-medium text-gray-400`
- Accompanied by a subtle `border-b border-gray-50` separator below the section content, not above the header
- Never bold, never large, never prominent

### Status Indicators

| State | Colour | Usage |
|---|---|---|
| Not connected | `bg-amber-400` | Header status dot — awaiting first authentication |
| Connected / success | `bg-green-400` | Header status dot — Outlook data is fresh |
| Partial / degraded | `bg-yellow-400` | Header status dot — one connector partially failed |
| Error / failed | `bg-red-400` | Header status dot — data unavailable |

`StatusBadge` (chip) uses these same semantics with background tints:
- `SUCCESS` → `bg-green-100 text-green-800`
- `PARTIAL` → `bg-yellow-100 text-yellow-800`
- `FAILED` → `bg-red-100 text-red-800`

### Buttons

**Primary action button** (e.g. "Connect Outlook"):
- `rounded-md bg-blue-600 px-5 py-2 text-sm font-medium text-white`
- Not full-width. Centred with natural content width. Full-width buttons are a web form convention.
- Disabled state: `opacity-40 cursor-not-allowed`
- Hover state: `hover:bg-blue-700`

**Icon button** (e.g. refresh):
- `rounded p-1`
- Icon size: `h-3.5 w-3.5`
- Colour: `text-gray-400`, hover `text-gray-600`
- No visible border. No background. Subtle hover feedback only.

### Hover Behaviour

- List items (meetings, emails): `hover:bg-gray-50` transition `duration-100`
- Icon buttons: `hover:text-gray-600` transition `duration-100`
- No shadows added on hover — Worky does not lift content on hover
- No underlines on hover unless an element is a genuine hyperlink

### Animations

- Loading spinner: `animate-spin` — the only continuous animation permitted
- State transitions: `transition-opacity duration-150` for appearing/disappearing content
- No bounce, pulse, ping, or decorative motion
- Animations that persist beyond 300ms must have a clear functional justification

### Scrolling

The content area scrolls vertically when content exceeds `max-h-[560px]`. Rules:
- No horizontal scrolling, ever
- No custom scrollbar styling in development — the OS scrollbar is appropriate
- Scroll position resets to top when the active screen changes

### Colour Philosophy

Worky uses a near-monochromatic palette. The goal is a calm, unobtrusive background presence. Colour is used sparingly as a signal, never as decoration.

| Purpose | Colour |
|---|---|
| Background | `white` (`#ffffff`) |
| Section dividers | `gray-50` / `gray-100` |
| Secondary text | `gray-400` / `gray-500` |
| Primary text | `gray-800` / `gray-900` |
| Ambient chrome (borders, dots) | `gray-100` / `gray-200` |
| Interactive blue | `blue-600` (buttons, spinner) |
| Success green | `green-400` / `green-100` |
| Warning amber | `amber-400` / `yellow-100` |
| Error red | `red-400` / `red-100` |
| IBM Bob brand accent | Used in footer caption only |

**Rules:**
- No gradients
- No background images
- No coloured section backgrounds — the content area is always white
- Accent blue appears only on actionable elements (buttons, active spinner)

---

## 4. Widget Behaviour

The widget communicates its state through three surfaces: the status dot in the header, the content area, and the footer timestamp.

### Disconnected

The user has not authenticated. The widget shows `SetupScreen` with a single call-to-action to connect Outlook. The header status dot is **amber**. The footer shows `—`.

The widget is intentionally minimal in this state. It does not explain the full product, list features, or show marketing copy. The single prompt to connect is sufficient.

### Connecting

The user has clicked "Connect Outlook" and the Microsoft OAuth flow is in progress. The browser is navigated to the Microsoft login page. The widget does not display an intermediate loading state for this transition — the browser naturally shows progress.

After the backend completes the OAuth exchange and redirects back to `/auth/success`, the widget reads the query parameters and transitions to the Loading state.

### Ready

Authentication is complete and Outlook data has been fetched successfully. The header status dot is **green**. The content area shows real meeting and email data. The footer shows the last-refreshed timestamp formatted as "Updated N min ago".

### Refreshing

The user has pressed the refresh button, or an automatic background refresh is in progress. The header status dot remains green. A subtle loading indicator appears within the section being refreshed rather than replacing the entire content area. Stale data remains visible during the refresh — the widget never shows an empty state while refreshing.

### Offline / Backend Unreachable

The widget cannot reach the backend. The header status dot is **amber**. The last-fetched data remains visible (if any). The footer timestamp continues to show when data was last successfully retrieved. No aggressive error messaging — a calm amber dot and a stale timestamp communicate the situation without alarming the user.

### Error

The connector returned a `FAILED` status or an unrecoverable error occurred. The header status dot is **red**. An `ErrorBanner` appears at the top of the affected section with a brief, plain-language message. Other sections that succeeded are unaffected and continue to display their data.

### Loading (first fetch)

The user has just authenticated and no data has been fetched yet. Sections that will receive data show a `LoadingSpinner`. Sections that are future-phase placeholders show "Coming soon." The header status dot is **amber** until the first successful fetch, then transitions to green.

---

## 5. Frontend Architecture

### Overview

```
src/
├── api/            Transport layer — all HTTP communication
├── components/     UI components organised by concern
│   ├── shell/      Widget frame and chrome
│   ├── setup/      Onboarding screens
│   ├── dashboard/  Data display screens and sections
│   └── shared/     Reusable primitives
├── hooks/          React hooks — async state and data fetching
├── services/       Domain logic wrappers over the API layer
├── types/          TypeScript mirrors of backend Pydantic models
├── utils/          Pure utility functions
└── assets/         Static assets
```

### `App.tsx`

**Responsibility:** Mount `WidgetShell`. Render `ScreenManager` inside it.

This file is intentionally minimal and permanently stable. It does not own screen state, auth state, or data fetching. It will not change across future phases. Its only job is to compose the two top-level structural pieces.

### `WidgetShell`

**Responsibility:** Provide the widget's visual frame — width, background, border radius, shadow, header, scrollable content area, and footer.

`WidgetShell` is display-only. It never fetches data, never reads auth state, and never conditionally renders based on application state. Its only input is `children`. Phase 2 will pass `display_name` as a prop for the header; otherwise this component is permanently stable.

**The widget dimensions are declared here.** `w-[380px]` and `max-h-[560px]` define the widget's visual footprint. These values must match the `BrowserWindow` dimensions set in the future Electron configuration.

### `ScreenManager`

**Responsibility:** Decide which screen is active and render it.

This is the single file that changes when authentication state or data-loading state affects which screen is shown. In Phase 1 it unconditionally renders `SetupScreen`. In Phase 2 it reads `useAuth` and renders `SetupScreen` or `DashboardScreen` conditionally. In Phase 3 it passes Outlook context data into `DashboardScreen` as props.

All phase-to-phase evolution of screen transitions happens in `ScreenManager` only. `App.tsx` and `WidgetShell` are unaffected.

### Components

**`setup/SetupScreen`** — The onboarding panel. Shown when the user is unauthenticated. Contains the "Connect Outlook" call-to-action. Has no data dependencies.

**`dashboard/DashboardScreen`** — The main content view. Shown when authenticated. Composed of section components for meetings, emails, and future features. Phase 3 will receive Outlook data as props and replace placeholder sections with live content.

**`shared/LoadingSpinner`** — Compact inline spinner. Used inside data sections during fetch operations. Must never be full-screen.

**`shared/ErrorBanner`** — Inline error message. Used when a connector returns FAILED status or a network error occurs. Scoped to the affected section.

**`shared/StatusBadge`** — Chip component for `SUCCESS`, `PARTIAL`, `FAILED` connector states. Mirrors the `ConnectorStatus` enum from the backend.

### Hooks (`src/hooks/`)

Hooks own all async state management. They use the API layer and expose typed state to components. Components never call `apiClient` directly.

| Hook | Phase | Responsibility |
|---|---|---|
| `useAuth` | Phase 2 | Auth state: `{ user, isAuthenticated, login, logout }` |
| `useOutlookContext` | Phase 3 | Outlook data: `{ data, status, error, refresh, loading }` |

### Services (`src/services/`)

Services contain domain logic that is too complex for a hook but too specific for the API layer. They are plain TypeScript functions — not React.

| Service | Phase | Responsibility |
|---|---|---|
| `authService` | Phase 2 | `handleAuthSuccess(params)` — reads query params from the `/auth/success` redirect, persists `user_id`/`display_name`/`email` to `localStorage` |
| `outlookService` | Phase 3 | `getOutlookContext(userId)` — typed wrapper around the context endpoint call |

### API Layer (`src/api/`)

**`client.ts`** — The single Axios instance. The only file in the codebase that imports `axios`. All other modules use this client through the services layer. When porting to Electron, only `client.ts` changes — Axios calls become IPC messages to the Electron main process.

**Interceptors:**
- Request interceptor (Phase 2): attaches `user_id` to requests that require it.
- Response interceptor (Phase 2): handles `401` responses by clearing auth state and returning the user to `SetupScreen`.

**Future API modules** follow this pattern: `src/api/auth.ts`, `src/api/outlook.ts`, etc. Each module exports plain async functions. No module imports from components or hooks.

### Types (`src/types/`)

TypeScript mirrors of backend Pydantic models. Defined once and used everywhere. Rules:
- Every type must have a corresponding backend model.
- Do not invent types that have no backend equivalent.
- Field names must exactly match the backend's `model_dump()` output (snake_case).
- Phase 2 will add: `AuthorizationResponse`, `ConnectorResult`, `ConnectorStatus`, `OutlookContext`, `CalendarEvent`, `Email`.

### Utilities (`src/utils/`)

Pure functions with no side effects and no React dependency. Examples:
- `formatRelativeTime(isoString)` — converts `collected_at` ISO 8601 to "Updated 3 min ago"
- `formatMeetingTime(start, end)` — formats meeting time range for display

---

## 6. Backend / Frontend Responsibilities

This boundary must never be crossed. The frontend should not reimplement backend logic. The backend should not make presentation decisions.

### Backend owns

| Concern | Implementation |
|---|---|
| OAuth 2.0 PKCE flow | `app/auth/service.py` — full PKCE mechanics, code exchange, state validation |
| Token storage | `InMemoryTokenRepository` / future `RedisTokenRepository` — never exposed to frontend |
| Token refresh | `AuthService.get_valid_token()` — silent refresh before every Graph call |
| Token encryption | Fernet encryption in `AuthService` — frontend never sees a refresh token |
| Microsoft Graph communication | `GraphAPIClient` — all HTTP calls to `graph.microsoft.com` |
| Data normalisation | `OutlookNormalizer` — raw Graph JSON → typed domain models |
| Business logic | `OutlookConnector`, future `SlackConnector`, `ContextBuilder` |
| AI reasoning | IBM Bob via `BobService` |
| Recommendation generation | `RecommendationService` (Phase 9+) |

### Frontend owns

| Concern | Implementation |
|---|---|
| Presenting data | Components receive typed props and render them |
| Widget state | `ScreenManager` — which screen is active |
| Auth session awareness | `useAuth` — reads `user_id`/`display_name`/`email` from `localStorage` |
| User interaction | Button clicks, hover feedback, manual refresh trigger |
| Data freshness display | Formatted `collected_at` timestamp from `ConnectorResult` |
| Error communication | `ErrorBanner`, status dot, `StatusBadge` |
| Loading states | `LoadingSpinner` within affected sections |

### Critical rules

**The frontend never constructs OAuth URLs.** Navigating to `/api/v1/auth/login` is sufficient — the backend builds the full Microsoft authorization URL including PKCE parameters.

**The frontend never stores or transmits tokens.** The backend redirect to `/auth/success` passes only `user_id`, `display_name`, and `email`. No `access_token`, no `refresh_token`, no `expires_at`.

**The frontend never calls Microsoft Graph directly.** All enterprise API communication flows through the backend.

**The frontend never makes decisions about data priority.** IBM Bob and the backend determine which items are most important. The frontend renders them in the order the backend provides.

---

## 7. Future Roadmap

### Phase 2 — Authentication

Activate the "Connect Outlook" button. Implement `useAuth`, `authService`, and the `/auth/success` callback handler. After this phase: a user can authenticate with Microsoft and the widget transitions from `SetupScreen` to `DashboardScreen`.

**Key constraint:** The frontend receives only `user_id`, `display_name`, and `email` from the backend redirect. No tokens are stored on the frontend.

### Phase 3 — Outlook Integration

Implement `useOutlookContext` and `outlookService`. Wire real calendar and email data into `DashboardScreen`. Replace `PlaceholderSection` components for Meetings and Emails with live `MeetingList`, `MeetingCard`, `EmailList`, and `EmailCard` components. Add manual refresh, loading states, partial/failed error handling, and the data freshness timestamp in the footer.

**Backend endpoint:** `GET /api/v1/connectors/outlook/context?user_id=<id>`

### Phase 4 — Slack Integration

Add a Slack messages section to `DashboardScreen`. Implement `useSlackContext` and `slackService`. Requires the backend Slack connector to be complete.

**Note:** This phase depends entirely on the backend Slack connector, which is a teammate's responsibility.

### Phase 5 — GitHub Integration

Add GitHub pull requests and review requests section. Follow the same pattern as Outlook and Slack connector integration.

### Phase 6 — IBM Bob Recommendations

Replace the "Today's Priorities" section with real IBM Bob recommendations from `GET /api/v1/recommendations`. This is the core product value — Bob synthesises data from all connected sources into a prioritised action list. The frontend's job is to render Bob's output faithfully, not to interpret or reorder it.

### Phase 7 — Electron / Tauri Packaging

Package the React application as a native desktop widget. Key steps:
- Replace `src/api/client.ts` HTTP calls with Electron IPC messages (or retain HTTP to a local backend process)
- Set `BrowserWindow` dimensions to match `w-[380px]` and `max-h-[560px]`
- Remove the `#root` centering styles from `index.css` (unnecessary in a native window)
- Configure the window to be always-on-top, frameless, and positioned at a user-preferred screen location
- Remove `rounded-xl` and `shadow-lg` from `WidgetShell` if the OS provides window chrome

No component code changes are required for the Electron port. The architecture was designed with this transition in mind from Phase 1.

---

## 8. Non-Goals

### No sidebar

Sidebars are a navigation pattern for multi-section applications. Worky has one content area and one scrollable list of items. A sidebar would add navigation complexity that serves no user need.

### No dashboard layout

Grid dashboards with resizable panels are designed for data analysts who configure their own view. Worky's view is curated by IBM Bob. The user does not choose what to see or how to arrange it. The layout is fixed by design.

### No multiple pages or URL-based routing

Pages imply a mental model of distinct locations to navigate between. Worky has states, not pages — setup, loading, ready. These transitions are managed in memory with no URL changes. Adding a routing library would introduce browser-native navigation patterns that are incompatible with the Electron window model.

### No complex settings

Configuration should be minimal and self-contained. Connecting a new source (Outlook, Slack) is a single OAuth flow triggered from within the widget. There is no settings page, no account management, no notification preferences in the initial product.

### No notifications

Desktop notifications are an operating system concern, not a widget concern. Worky's value is passive and glanceable — it does not interrupt the user. Push notifications would undermine the calm, ambient character of the product.

### No feature overload

Every feature added to the widget increases cognitive load. If a piece of information is not immediately actionable or decision-relevant, it should not appear in the widget. Worky should always feel like it contains less than users expect — the discipline of exclusion is the product.

### No web-application patterns inside the widget

This specifically excludes: full-width form buttons, uppercase section headers with wide letter-spacing, card shadows within the content area, multi-column layouts, tab navigation, modal dialogs, and decorative colour fills on section backgrounds. These patterns are correct in web applications and incorrect in a compact desktop widget.

---

*This document is the design contract for all future Worky frontend development. Proposals that contradict these principles require explicit discussion and an update to this document before implementation begins.*
