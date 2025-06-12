use async_trait::async_trait;
use jsonwebtoken::{decode, decode_header, Algorithm, DecodingKey, Validation};
use serde::Deserialize;
use tokio::sync::Mutex;

#[derive(Deserialize, Clone, Debug)]
pub struct Claims {
    pub sub: String,
    #[serde(default)]
    pub agent: Option<String>,
}

#[async_trait]
pub trait TokenVerifier: Send + Sync {
    async fn verify(&self, token: &str) -> Option<Claims>;
}

pub struct Hs256Verifier {
    key: DecodingKey,
}

impl Hs256Verifier {
    pub fn new(secret: String) -> Self {
        Self {
            key: DecodingKey::from_secret(secret.as_bytes()),
        }
    }
}

#[async_trait]
impl TokenVerifier for Hs256Verifier {
    async fn verify(&self, token: &str) -> Option<Claims> {
        let mut validation = Validation::new(Algorithm::HS256);
        validation.validate_exp = false;
        decode::<Claims>(token, &self.key, &validation)
            .ok()
            .map(|d| d.claims)
    }
}

pub struct AzureEntraIdVerifier {
    jwks_url: String,
    client: reqwest::Client,
    keys: Mutex<Option<Jwks>>,
}

#[derive(Deserialize)]
struct Jwks {
    keys: Vec<Jwk>,
}

#[derive(Deserialize)]
struct Jwk {
    kid: String,
    n: String,
    e: String,
}

impl AzureEntraIdVerifier {
    pub fn new(jwks_url: String) -> Self {
        Self {
            jwks_url,
            client: reqwest::Client::new(),
            keys: Mutex::new(None),
        }
    }

    async fn fetch_keys(&self) -> reqwest::Result<Jwks> {
        self.client.get(&self.jwks_url).send().await?.json().await
    }
}

#[async_trait]
impl TokenVerifier for AzureEntraIdVerifier {
    async fn verify(&self, token: &str) -> Option<Claims> {
        let header = decode_header(token).ok()?;
        let kid = header.kid?;
        let mut guard = self.keys.lock().await;
        if guard.is_none() {
            if let Ok(jwks) = self.fetch_keys().await {
                *guard = Some(jwks);
            } else {
                return None;
            }
        }
        let jwks = guard.as_ref()?;
        let jwk = jwks.keys.iter().find(|k| k.kid == kid)?;
        let key = DecodingKey::from_rsa_components(&jwk.n, &jwk.e).ok()?;
        let mut validation = Validation::new(Algorithm::RS256);
        validation.validate_exp = false;
        decode::<Claims>(token, &key, &validation)
            .ok()
            .map(|d| d.claims)
    }
}
