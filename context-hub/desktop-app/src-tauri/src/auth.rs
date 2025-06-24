use keyring::Entry;
use oauth2::{
    basic::BasicClient, AuthUrl, ClientId, ClientSecret, RedirectUrl, TokenUrl,
    AuthorizationCode, CsrfToken, PkceCodeChallenge, Scope,
};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

#[derive(Debug, Serialize, Deserialize)]
pub struct AuthState {
    pub is_authenticated: bool,
    pub user_email: Option<String>,
    pub user_name: Option<String>,
    pub access_token: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct LoginProvider {
    pub name: String,
    pub icon: String,
    pub provider_type: ProviderType,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ProviderType {
    Google,
    Microsoft,
    Email,
}

pub struct AuthManager {
    app_handle: AppHandle,
    keyring_service: String,
}

impl AuthManager {
    pub fn new(app_handle: AppHandle) -> Self {
        Self {
            app_handle,
            keyring_service: "ContextHub".to_string(),
        }
    }

    /// Get available login providers
    pub fn get_providers(&self) -> Vec<LoginProvider> {
        vec![
            LoginProvider {
                name: "Google".to_string(),
                icon: "google".to_string(),
                provider_type: ProviderType::Google,
            },
            LoginProvider {
                name: "Microsoft".to_string(),
                icon: "microsoft".to_string(),
                provider_type: ProviderType::Microsoft,
            },
            LoginProvider {
                name: "Email".to_string(),
                icon: "email".to_string(),
                provider_type: ProviderType::Email,
            },
        ]
    }

    /// Check if user is already authenticated
    pub async fn check_auth(&self) -> Result<AuthState, String> {
        // Try to get token from keychain
        let entry = Entry::new(&self.keyring_service, "access_token")
            .map_err(|e| e.to_string())?;

        match entry.get_password() {
            Ok(token) => {
                // Validate token with server
                if self.validate_token(&token).await? {
                    let user_info = self.get_user_info(&token).await?;
                    Ok(AuthState {
                        is_authenticated: true,
                        user_email: Some(user_info.email),
                        user_name: Some(user_info.name),
                        access_token: Some(token),
                    })
                } else {
                    Ok(AuthState {
                        is_authenticated: false,
                        user_email: None,
                        user_name: None,
                        access_token: None,
                    })
                }
            }
            Err(_) => Ok(AuthState {
                is_authenticated: false,
                user_email: None,
                user_name: None,
                access_token: None,
            }),
        }
    }

    /// Start OAuth flow
    pub async fn login_oauth(&self, provider: ProviderType) -> Result<String, String> {
        let (auth_url, token_url, client_id, client_secret) = match provider {
            ProviderType::Google => (
                "https://accounts.google.com/o/oauth2/v2/auth",
                "https://oauth2.googleapis.com/token",
                std::env::var("GOOGLE_CLIENT_ID").unwrap_or_default(),
                std::env::var("GOOGLE_CLIENT_SECRET").unwrap_or_default(),
            ),
            ProviderType::Microsoft => (
                "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                std::env::var("MICROSOFT_CLIENT_ID").unwrap_or_default(),
                std::env::var("MICROSOFT_CLIENT_SECRET").unwrap_or_default(),
            ),
            _ => return Err("Provider not supported for OAuth".to_string()),
        };

        let client = BasicClient::new(
            ClientId::new(client_id),
            Some(ClientSecret::new(client_secret)),
            AuthUrl::new(auth_url.to_string()).map_err(|e| e.to_string())?,
            Some(TokenUrl::new(token_url.to_string()).map_err(|e| e.to_string())?),
        )
        .set_redirect_uri(
            RedirectUrl::new("http://localhost:9899/callback".to_string())
                .map_err(|e| e.to_string())?,
        );

        // Generate PKCE challenge
        let (pkce_challenge, pkce_verifier) = PkceCodeChallenge::new_random_sha256();

        // Generate authorization URL
        let (auth_url, csrf_token) = client
            .authorize_url(CsrfToken::new_random)
            .add_scope(Scope::new("email".to_string()))
            .add_scope(Scope::new("profile".to_string()))
            .set_pkce_challenge(pkce_challenge)
            .url();

        // Open browser
        open::that(auth_url.as_str()).map_err(|e| e.to_string())?;

        // Start local server to receive callback
        let token = self.wait_for_callback(client, pkce_verifier, csrf_token).await?;

        // Save token to keychain
        self.save_token(&token)?;

        Ok(token)
    }

    /// Email/magic link login
    pub async fn login_email(&self, email: String) -> Result<(), String> {
        // Send magic link request to server
        let client = reqwest::Client::new();
        let response = client
            .post("https://api.contexthub.io/auth/magic-link")
            .json(&serde_json::json!({
                "email": email,
                "client": "desktop"
            }))
            .send()
            .await
            .map_err(|e| e.to_string())?;

        if response.status().is_success() {
            // Show success message in UI
            self.app_handle
                .emit_all("auth:magic-link-sent", &email)
                .map_err(|e| e.to_string())?;
            Ok(())
        } else {
            Err("Failed to send magic link".to_string())
        }
    }

    /// Save token securely
    fn save_token(&self, token: &str) -> Result<(), String> {
        let entry = Entry::new(&self.keyring_service, "access_token")
            .map_err(|e| e.to_string())?;
        entry.set_password(token).map_err(|e| e.to_string())?;
        Ok(())
    }

    /// Logout and clear credentials
    pub fn logout(&self) -> Result<(), String> {
        let entry = Entry::new(&self.keyring_service, "access_token")
            .map_err(|e| e.to_string())?;
        entry.delete_password().map_err(|e| e.to_string())?;
        
        // Emit logout event
        self.app_handle
            .emit_all("auth:logout", ())
            .map_err(|e| e.to_string())?;
        
        Ok(())
    }
}

#[derive(Debug, Deserialize)]
struct UserInfo {
    email: String,
    name: String,
}

// Tauri commands
#[tauri::command]
pub async fn check_auth(app: AppHandle) -> Result<AuthState, String> {
    let auth_manager = AuthManager::new(app);
    auth_manager.check_auth().await
}

#[tauri::command]
pub async fn login(app: AppHandle, provider: ProviderType) -> Result<String, String> {
    let auth_manager = AuthManager::new(app);
    match provider {
        ProviderType::Email => Err("Use login_email command for email login".to_string()),
        _ => auth_manager.login_oauth(provider).await,
    }
}

#[tauri::command]
pub async fn login_email(app: AppHandle, email: String) -> Result<(), String> {
    let auth_manager = AuthManager::new(app);
    auth_manager.login_email(email).await
}

#[tauri::command]
pub fn logout(app: AppHandle) -> Result<(), String> {
    let auth_manager = AuthManager::new(app);
    auth_manager.logout()
}