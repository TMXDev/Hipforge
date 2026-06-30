# 14_FRONTEND.md

Version: 1.0

Status: Pending

---

# Purpose

This document defines the frontend architecture of HIPForge.

The frontend provides a clean, responsive interface for uploading CUDA projects, monitoring migration progress, viewing logs in real time, and downloading the final migration package.

The frontend is implemented using Next.js.

---

# Goals

The frontend must be:

- Fast
- Responsive
- Professional
- Easy to understand
- Accessible
- Real-time

---

# Design Philosophy

HIPForge is a developer tool.

The interface should emphasize clarity over visual effects.

Users should immediately understand:

- What is happening.
- What stage the migration is in.
- Why something failed.
- What they should do next.

---

# Technology Stack

Framework

- Next.js

Language

- TypeScript

Styling

- Tailwind CSS

Icons

- Lucide React

Real-Time

- WebSockets

State Management

- React Context

Notifications

- Sonner

---

# Folder Structure

```
frontend/

app/

components/

hooks/

services/

types/

utils/

styles/

public/
```

---

# Pages

## Home

```
/
```

Main upload page.

Contains:

- Project upload
- Retry budget selection
- GPU architecture selection
- Start Migration button

---

## Migration

```
/migration/[id]
```

Displays:

- Live progress
- Current workflow stage
- Compiler logs
- AI activity
- Migration Journal
- Download button

---

## Settings

```
/settings
```

Future configuration page.

Not required for Version 1.

---

# Components

## Upload Card

Allows:

- Drag & Drop
- File picker
- Upload validation

---

## Migration Progress

Displays:

```
Initializing

↓

Hipify

↓

Compiling

↓

Analysis

↓

Patching

↓

Research

↓

Report

↓

Complete
```

Current stage is highlighted.

---

## Live Log Viewer

Displays:

- Compiler logs
- Workflow events
- AI events

Supports:

- Auto-scroll
- Pause scrolling
- Search
- Copy

---

## AI Activity Panel

Shows:

Analysis Agent

Patch Agent

Research Agent

Current status only.

It should never expose raw prompts.

---

## Migration Journal Panel

Displays a simplified timeline.

Example

```
Attempt 1

Compilation Failed

↓

Analysis Completed

↓

Patch Applied

↓

Compilation Successful
```

---

## Download Panel

After success:

Displays

Download ZIP

View Report

View Journal

---

# State Management

Global state includes:

- Migration ID
- Workflow status
- Current attempt
- Progress events
- Connection state

Business logic remains in the backend.

---

# Real-Time Updates

The frontend connects using WebSockets.

Receives:

- Progress events
- Compiler logs
- AI activity
- Completion events

The frontend never polls the backend during migration.

---

# Error Handling

The frontend should display clear messages.

Examples

Upload Failed

Compiler Failed

Connection Lost

Migration Cancelled

Internal Error

Messages should explain the problem without exposing internal details.

---

# Loading States

Every long-running action should display progress.

Examples

Uploading...

Creating Workspace...

Running hipify...

Compiling...

Searching Documentation...

Generating Report...

---

# Responsive Design

Desktop is the primary target.

Tablet should remain usable.

Mobile support is limited but functional.

---

# Accessibility

The frontend should:

- Support keyboard navigation.
- Use semantic HTML.
- Maintain sufficient color contrast.
- Provide ARIA labels where appropriate.

---

# Security

The frontend must:

- Validate uploads before submission.
- Never store API keys.
- Never expose internal paths.
- Escape rendered log content.
- Handle unexpected server responses safely.

---

# Responsibilities

The frontend is responsible for:

- User interaction
- Progress visualization
- Log display
- Report download

---

# Non-Responsibilities

The frontend does NOT:

- Compile code.
- Execute AI.
- Manage workflow.
- Access Redis directly.

---

# Dependencies

- `13_BACKEND.md`
- `16_API_SPECIFICATION.md`
- `18_OBSERVABILITY.md`
- `26_JOB_LIFECYCLE.md`

---

# Used By

15_DOCKER_SETUP.md

19_SECURITY.md

---

# Acceptance Criteria

✓ Project upload supported.

✓ Live workflow visualization.

✓ Real-time logs.

✓ Migration Journal displayed.

✓ Download package available.

✓ Responsive layout.

✓ Accessible interface.

---

# Startup Notes

Future versions may introduce:

- User authentication
- Migration history
- Team workspaces
- Usage dashboards
- Subscription management

These additions should integrate without redesigning the core interface.

---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.