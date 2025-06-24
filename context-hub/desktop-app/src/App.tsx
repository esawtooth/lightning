import React, { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/tauri';
import { listen } from '@tauri-apps/api/event';
import { LoginScreen } from './components/LoginScreen';
import { MainInterface } from './components/MainInterface';
import { OnboardingFlow } from './components/OnboardingFlow';
import { SystemTray } from './components/SystemTray';

interface AuthState {
  is_authenticated: boolean;
  user_email?: string;
  user_name?: string;
}

interface AppState {
  authState: AuthState | null;
  isFirstRun: boolean;
  syncStatus: 'idle' | 'syncing' | 'error' | 'paused';
  mountPath: string;
}

function App() {
  const [state, setState] = useState<AppState>({
    authState: null,
    isFirstRun: false,
    syncStatus: 'idle',
    mountPath: '',
  });

  useEffect(() => {
    // Check authentication on startup
    checkAuth();

    // Listen for auth events
    const unlistenAuth = listen('auth:logout', () => {
      setState(prev => ({
        ...prev,
        authState: { is_authenticated: false }
      }));
    });

    // Listen for sync events
    const unlistenSync = listen('sync:status', (event) => {
      setState(prev => ({
        ...prev,
        syncStatus: event.payload as any
      }));
    });

    return () => {
      unlistenAuth.then(fn => fn());
      unlistenSync.then(fn => fn());
    };
  }, []);

  const checkAuth = async () => {
    try {
      const authState = await invoke<AuthState>('check_auth');
      const isFirstRun = await invoke<boolean>('is_first_run');
      const mountPath = await invoke<string>('get_mount_path');
      
      setState({
        authState,
        isFirstRun,
        syncStatus: 'idle',
        mountPath,
      });
    } catch (error) {
      console.error('Failed to check auth:', error);
    }
  };

  // Show loading while checking auth
  if (!state.authState) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  // Show login screen if not authenticated
  if (!state.authState.is_authenticated) {
    return <LoginScreen onLogin={checkAuth} />;
  }

  // Show onboarding for first-time users
  if (state.isFirstRun) {
    return (
      <OnboardingFlow
        onComplete={async () => {
          await invoke('complete_onboarding');
          setState(prev => ({ ...prev, isFirstRun: false }));
        }}
      />
    );
  }

  // Main app interface
  return (
    <>
      <MainInterface
        userEmail={state.authState.user_email!}
        userName={state.authState.user_name!}
        syncStatus={state.syncStatus}
        mountPath={state.mountPath}
      />
      <SystemTray />
    </>
  );
}

export default App;