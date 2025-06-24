# Context Hub Desktop App

A user-friendly desktop application that makes Context Hub work like Dropbox/Google Drive.

## Features for Non-Technical Users

### 1. One-Click Installer
- **macOS**: `.dmg` with drag-to-Applications
- **Windows**: `.msi` installer with Start Menu shortcuts
- **Linux**: `.deb`/`.rpm` packages + AppImage

### 2. Simple Setup Flow
```
1. Download installer from contexthub.io
2. Run installer (no terminal required)
3. Sign in with email/password or Google/Microsoft
4. Choose folder location (default: ~/Context Hub)
5. Start syncing!
```

### 3. System Tray App
- Shows sync status
- Recent activity
- Quick access to files
- Pause/resume sync
- Settings

### 4. Automatic Filesystem Mount
- No manual mounting required
- Appears as regular folder in Finder/Explorer
- Works with all applications
- Offline support

### 5. Smart Permissions
- Personal workspace by default
- Simple sharing: right-click → "Share with Context Hub"
- Email-based invites
- Read/Write permissions only (no complex ACLs)

## Implementation Plan

### Phase 1: Desktop App Shell (Week 1)
- Electron or Tauri app
- System tray integration
- Auto-start on login
- Update mechanism

### Phase 2: Easy Auth (Week 2)
- OAuth with Google/Microsoft
- Magic link email auth
- Secure token storage
- No API keys for users

### Phase 3: Filesystem Integration (Week 3-4)
- Bundle FUSE/WinFsp with installer
- Auto-mount on startup
- Handle mount failures gracefully
- Progress indicators

### Phase 4: Sync Engine (Week 5-6)
- Efficient file watching
- Smart sync (download on-demand)
- Conflict resolution UI
- Bandwidth controls

### Phase 5: Polish (Week 7-8)
- Onboarding tutorial
- File icons/previews
- Context menu integration
- Notifications

## Technical Architecture

```
┌─────────────────────────────────────┐
│         Desktop App (Tauri)         │
│  ┌─────────────┬─────────────────┐  │
│  │   UI (React)│  Rust Backend   │  │
│  │             │                  │  │
│  │  Settings   │  Auth Manager    │  │
│  │  Status     │  Mount Manager   │  │
│  │  Sharing    │  Sync Engine     │  │
│  └─────────────┴─────────────────┘  │
└──────────────┬──────────────────────┘
               │
        ┌──────┴──────┐
        │             │
   ┌────▼───┐    ┌───▼────┐
   │  FUSE  │    │ WinFsp │
   │ Mount  │    │  Mount │
   └────────┘    └────────┘
        │             │
        └──────┬──────┘
               │
         ┌─────▼─────┐
         │ Local FS  │
         │ ~/Context │
         │    Hub    │
         └───────────┘
```

## User Experience Goals

1. **Zero Configuration**: Works out of the box
2. **Familiar Interface**: Looks like Dropbox/Google Drive
3. **No Terminal**: Everything through GUI
4. **Smart Defaults**: Sensible settings pre-configured
5. **Clear Status**: Always know what's happening
6. **Fast**: Instant file access, background sync

## Security for Regular Users

- Encrypted connection (automatic)
- Secure credential storage (OS keychain)
- Optional 2FA
- Private by default
- Clear sharing permissions

## Distribution

- Website with prominent download button
- Auto-detect OS and suggest correct installer
- Homebrew (Mac), Chocolatey (Windows), Snap (Linux)
- App stores (Microsoft Store, Mac App Store)

This would make Context Hub as easy to use as any consumer cloud storage service.