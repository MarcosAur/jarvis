---
name: Autonomous Engineering Nexus
colors:
  surface: '#051424'
  surface-dim: '#051424'
  surface-bright: '#2c3a4c'
  surface-container-lowest: '#010f1f'
  surface-container-low: '#0d1c2d'
  surface-container: '#122131'
  surface-container-high: '#1c2b3c'
  surface-container-highest: '#273647'
  on-surface: '#d4e4fa'
  on-surface-variant: '#c2c6d6'
  inverse-surface: '#d4e4fa'
  inverse-on-surface: '#233143'
  outline: '#8c909f'
  outline-variant: '#424754'
  surface-tint: '#adc6ff'
  primary: '#adc6ff'
  on-primary: '#002e6a'
  primary-container: '#4d8eff'
  on-primary-container: '#00285d'
  inverse-primary: '#005ac2'
  secondary: '#d0bcff'
  on-secondary: '#3c0091'
  secondary-container: '#571bc1'
  on-secondary-container: '#c4abff'
  tertiary: '#4edea3'
  on-tertiary: '#003824'
  tertiary-container: '#00a572'
  on-tertiary-container: '#00311f'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#d8e2ff'
  primary-fixed-dim: '#adc6ff'
  on-primary-fixed: '#001a42'
  on-primary-fixed-variant: '#004395'
  secondary-fixed: '#e9ddff'
  secondary-fixed-dim: '#d0bcff'
  on-secondary-fixed: '#23005c'
  on-secondary-fixed-variant: '#5516be'
  tertiary-fixed: '#6ffbbe'
  tertiary-fixed-dim: '#4edea3'
  on-tertiary-fixed: '#002113'
  on-tertiary-fixed-variant: '#005236'
  background: '#051424'
  on-background: '#d4e4fa'
  surface-variant: '#273647'
typography:
  headline-xl:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.025em
  headline-xl-mobile:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '500'
    lineHeight: 26px
    letterSpacing: -0.015em
  headline-sm:
    fontFamily: Geist
    fontSize: 15px
    fontWeight: '500'
    lineHeight: 22px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Geist
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
  label-code-lg:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
  label-code-md:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-code-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.04em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-desktop: 1.25rem
  margin: 1rem
  margin-desktop: 1.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1.25rem
  space-xl: 2rem
---

## Brand & Style

This design system establishes an ultra-refined, high-precision technical cockpit built for mission-critical autonomous AI software orchestration. The aesthetic fuses Modern Developer Minimalism with a high-density, command-center precision inspired by modern productivity benchmarks. 

The visual tone communicates unwavering technical rigour, low-latency responsiveness, and dependable intelligence. It balances deep cosmic navy foundations with luminous, semantically charged accents (violet for autonomous AI cognition, emerald for live runtime execution, and electric sapphire for core system controls). The emotional state evoked is one of commanding leverage—engineers and technical leads should feel as if they are orchestrating a hyper-competent, invisible software engineering fleet with zero cognitive friction.

## Colors

The palette operates in a deeply immersive dark mode designed to minimize eye fatigue during sustained architectural review and real-time trace telemetry.

### Core Canvas & Layering
- **Canvas Base (`#090d16`):** The primary root application background. Deep, grounded, and free of murky gray haze.
- **Sub-Surface Canvas (`#0d121f`):** Used for nested panels, side rails, and high-density viewport wrappers.
- **Card / Surface Default (`#131b2e`):** Standard container background for Kanban cards, metrics widgets, and logs.
- **Surface Hover / Highlight (`#1a233b`):** Activated and hovering states across cards and list items.
- **Structural Border (`#222f4c`):** Precision boundary stroke for high-definition card separation without visually cluttering dense layouts.

### Semantic & Agent Accents
- **System Primary (`#3b82f6`):** Electric Blue designated for primary calls to action, sync actions, links, and system selections.
- **Agent Intelligence (`#8b5cf6`):** Deep Electric Violet reserved strictly for autonomous AI entities, model identifiers (Claude 3.5 Sonnet, Gemini Flash, Codex), and generative branch planning.
- **Live Execution & Health (`#10b981`):** Vivid Emerald used to signify active running pipelines, successful build jobs, healthy test suites, and green operational statuses.
- **Warning & Rework (`#f59e0b`):** Amber accent dedicated to test failure loops, model hallucination retries, approval bottlenecks, and manual overrides.
- **Error / Interruption (`#ef4444`):** Crisp Crimson for fatal runtime breaks, pipeline cancellations, or rejected PR validations.

### Typography & Content Neutrals
- **High-Contrast Value (`#f8fafc`):** Primary headings, critical pipeline metrics, and current ticket titles.
- **Secondary Medium (`#94a3b8`):** Body typography, provider attributes, and standard meta-labels.
- **Muted Subordinate (`#64748b`):** Timestamps, micro-hashes, and subtle grid lines.

## Typography

Typography prioritizes micro-density, spatial economy, and unambiguous optical tracking.

- **Primary Interface (Geist):** Handles standard user interface controls, Kanban column headers, dialog overlays, and conversational agent instructions. Tight letter tracking (`-0.02em` on titles) imparts a crisp, precision feel.
- **Machine & Data Layer (JetBrains Mono):** Mandated for all pipeline hashes (`commit-8f4b1`), execution runtimes (`124ms`), terminal log output streams, CLI flags, JSON payloads, and token consumption statistics.

Always display model variants (e.g., `claude-3-5-sonnet`, `gemini-1.5-flash`) in `label-code-md` or `label-code-sm` to maintain visual distinction from human ticket descriptions.

## Layout & Spacing

The layout model uses a fluid, high-density operational workbench designed to adapt from expansive 4K command centers down to on-call mobile monitors.

### Grid & Structure
- **Desktop (>= 1280px):** Multi-column Kanban or side-by-side terminal inspector layout. Columns use a fluid flex structure with `gutter-desktop` (20px) gutters and `margin-desktop` (24px) container margins. Kanban boards utilize horizontal scroll with sticky column headers when column counts exceed the visible viewport.
- **Tablet (768px - 1279px):** Modular dual-pane system. The primary pipeline or Kanban takes 65% width while execution telemetry collapses into a secondary contextual drawer or bottom sheet.
- **Mobile (< 768px):** Single-column stacked execution view with a sticky bottom action bar containing essential pipeline triggers ('Run', 'Pause', 'Sync').

### Spacing Principles
Padding follows an 8pt base with a dense 4pt sub-scale. Data rows within audit logs and execution matrices must default to `space-sm` (8px) vertical gap to maximize information visibility above the fold.

## Elevation & Depth

Visual hierarchy uses calibrated surface contrast, directional light boundaries, and semantic luminance rather than heavy drop shadows.

### Surface Tiers
- **Tier 0 (Root Canvas):** `#090d16`. Ground floor for all toolbars and foundational grids.
- **Tier 1 (Panels & Swimlanes):** `#0d121f` with a hairline border `1px solid #222f4c`.
- **Tier 2 (Cards & Data Rows):** `#131b2e` with `1px solid #222f4c`. Top edge features an optical highlight: an internal gradient border simulating overhead lighting (`linear-gradient(180deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.00) 100%)`).
- **Tier 3 (Floating Menus & Overlays):** `#1a233b` with 8px backdrop blur (`backdrop-filter: blur(12px)`) and subtle ambient dispersion: `0 8px 32px -4px rgba(0, 0, 0, 0.60)`.

### Semantic Radiant Glow
Active states do not cast standard black shadows; they project subtle, color-matched ambient auras:
- **Active Execution Glow:** `0 0 16px -2px rgba(16, 185, 129, 0.25)` applied to live pipeline badges.
- **AI Synthesis Glow:** `0 0 16px -2px rgba(139, 92, 246, 0.30)` applied to active AI agents generating code or resolving tickets.

## Shapes

The design system implements a refined, low-radius geometric framework (`roundedness: 1`) to preserve the technical, razor-sharp character of modern development environments:

- **Base Components (0.25rem / 4px):** Used for micro-badges, status pills, code snippets, nested tooltips, and table cell tags.
- **Cards & Inputs (0.5rem / 8px):** Standard curvature for Kanban task cards, form inputs, modal headers, and code inspection blocks.
- **Major Panels & Drawers (0.75rem / 12px):** Applied exclusively to floating modal dialogs, flyout run-inspectors, and system alert drawers.

Pills and circular avatars are strictly restricted to model avatar chips and pulsing status indicators.

## Components

### 1. Action Controls (Buttons & Triggers)
- **Primary ('Rodar Pipeline'):** Background `#3b82f6` with an inner top highlight border (`rgba(255,255,255,0.2)`). Text in white Geist Medium. Hover state lifts with brightness scale `1.08` and a focused blue ambient glow.
- **AI Action ('Orquestrar com Agente'):** Gradient surface from `#8b5cf6` to `#6366f1`. Accompanied by a spark/intelligence icon.
- **Secondary / Ghost ('Sincronizar', 'Pausar'):** Surface transparent or `#131b2e` with border `#222f4c`. Hover background shifts to `#1a233b` with border transitioning to `#3b82f6` at 50% opacity.

### 2. Status Pills & Pulse Glow
- **Live / Running:** Pill container using `rgba(16, 185, 129, 0.12)` background with `#10b981` text. Features a 6px circular dot possessing an infinite CSS ping/pulse glow animation (`@keyframes pulse-ring { 0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); } 70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); } 100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); } }`).
- **Rework / Alert:** Pill with `rgba(245, 158, 11, 0.12)` background, `#f59e0b` text, displaying cycle count: e.g., `⚡ Retrabalho (3x)`.

### 3. Provider & Model Badges
- **Integration Badges:** Compact 20px height capsules. Dark slate fill (`#1a233b`), border `#222f4c`. Includes mono-color SVG icons for GitHub, Jira, or Trello, followed by ticket IDs in `JetBrains Mono` (`GH-#1042`, `PROJ-89`).
- **AI Model Badges:** High-contrast tags with an intelligence violet accent dot:
  - Claude Sonnet: `#8b5cf6` text on `rgba(139, 92, 246, 0.1)` base.
  - Gemini Flash: Electric cyan/blue variant on dark navy base.

### 4. Kanban Pipeline Cards
- **Structure:** Card surface `#131b2e`, border `#222f4c`, internal padding `space-md`.
- **Header:** Top row houses the integration tag (e.g., Jira `ENG-402`) and time elapsed or rework counter (`JetBrains Mono`).
- **Body:** Task narrative in `headline-sm` with Geist font, capped at 2 lines.
- **Footer:** Bottom row pairs the assigned AI Agent badge on the left with execution status (e.g., `Testing`, `PR Open`) on the right. Card turns border to `#3b82f6` on hover with a smooth 150ms ease.

### 5. High-Density Telemetry Tables
- Header uses `#0d121f` with uppercase `label-code-sm` text in `#64748b`.
- Row height fixed at 36px. Border bottom `1px solid #1a233b`.
- Columns support tabular numbers (`font-variant-numeric: tabular-nums`) for microsecond durations, commit SHAs, and token counts.

### 6. Pipeline Run Inspector (Drawer / Terminal)
- An expandable side console styled as an IDE terminal. Background `#090d16`, code rendering in `JetBrains Mono` with syntax-highlighted agent outputs, execution logs, and live step-by-step validation checks.