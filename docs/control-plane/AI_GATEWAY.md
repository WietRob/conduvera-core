# AI Gateway — Pi-native FastAPI

## Uebersicht

Der AI Gateway ist ein FastAPI-basierter KI-Proxy, der direkt auf dem Raspberry Pi laeuft. Er routet LLM-Requests von Agenten an lokale oder Cloud-Backends, basierend auf Client-Identitaet und Sensitivitaetsklasse.

**Kein LiteLLM**. LiteLLM ist seit dem Supply-Chain-Vorfall Q1/2026 ausgeschlossen. Der Gateway ist eine Eigenentwicklung auf Basis von FastAPI und httpx.

---

## Architektur

```
Agent-Request
    │
    ▼
┌──────────────────────────┐
│  FastAPI (app.py)        │
│  POST /v1/chat/completions│
│  GET  /v1/models          │
│  GET  /health             │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  Auth (auth.py)          │
│  X-Gateway-Client Header │
│  → ClientRegistry        │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  Router (router.py)      │
│  GatewayRouter           │
│  Profile + SensitiveClass│
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  BackendProxy (backends) │
│  httpx → Local / Cloud   │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  Audit (audit.py)        │
│  Request/Response Log    │
└──────────────────────────┘
```

---

## Endpunkte

### `GET /health`

Health-Check. Liefert Status des Gateways und der verfuegbaren Backends.

**Response**:
```json
{
  "status": "healthy",
  "backends": {
    "local": "available",
    "cloud": "available"
  },
  "uptime_seconds": 3600
}
```

### `GET /v1/models`

Listet verfuegbare Modelle. Filtert basierend auf Client-Berechtigung und Sensitive-Class.

**Header**: `X-Gateway-Client: <client_id>`

**Response**:
```json
{
  "object": "list",
  "data": [
    {
      "id": "local-llama3",
      "object": "model",
      "owned_by": "local"
    },
    {
      "id": "gpt-4o",
      "object": "model",
      "owned_by": "openai"
    }
  ]
}
```

### `POST /v1/chat/completions`

OpenAI-kompatibler Chat-Completions-Endpunkt. Das Herzstueck des Gateways.

**Header**: `X-Gateway-Client: <client_id>`

**Request**: OpenAI-kompatibles Format
```json
{
  "model": "gpt-4o",
  "messages": [
    {"role": "user", "content": "..."}
  ],
  "temperature": 0.7
}
```

**Response**: OpenAI-kompatibles Format
```json
{
  "id": "gw-abc123",
  "object": "chat.completion",
  "model": "gpt-4o",
  "choices": [...]
}
```

---

## Authentifizierung

### Client-Auth via `X-Gateway-Client`

Jeder Request muss einen `X-Gateway-Client`-Header enthalten. Die `ClientRegistry` in `auth.py` ordnet Client-IDs ihren Profilen und Berechtigungen zu.

```python
# auth.py — ClientRegistry
class ClientRegistry:
    def get_client(client_id: str) -> ClientProfile
    def validate_client(client_id: str) -> bool
```

Ein fehlender oder unguelter Header fuehrt zu `401 Unauthorized`.

### Client-Profil

Jeder Client hat:
- `client_id`: Eindeutige Kennung
- `sensitive_class`: Zugeordnete Sensitive-Class
- `allowed_models`: Liste erlaubter Modelle
- `rate_limit`: Optional Rate-Limiting

---

## Sensitive-Class Policies

### Klassendefinition

| Klasse | Beschreibung | Cloud-Zugriff |
|---|---|---|
| `general` | Allgemeine Agenten, keine sensitiven Daten | **Erlaubt** |
| `sensitive` | Agenten mit Zugriff auf sensible Daten/Credentials | **Verboten** |
| `restricted` | Hochgradig eingeschraenkte Agenten | **Verboten** |

### Routing-Regeln

```
Request kommt ein:
│
├─ Client sensitive_class == "general"?
│   ├─ Modell ist Cloud-Modell? ──► Route zu Cloud-Backend
│   └─ Modell ist Lokal-Modell?  ──► Route zu Lokal-Backend
│
└─ Client sensitive_class != "general"?
    └─ Route IMMER zu Lokal-Backend (Cloud verboten)
        └─ Falls nur Cloud-Modell angefordert? ──► 403 Forbidden
```

**Nur `general` darf Cloud-Backends nutzen.** Alle anderen Klassen werden strikt auf lokale Modelle beschraenkt.

---

## Backend-Proxy

### `backends.py` — BackendProxy

Der `BackendProxy` nutzt `httpx` fuer HTTP-Requests an die Backends. Er verwaltet:

- **Verbindungs-Pooling**: Wiederverwendung von HTTP-Verbindungen
- **Timeout-Management**: Pro-Backend konfigurierbare Timeouts
- **Retry-Logik**: Automatische Wiederholung bei transienten Fehlern
- **Streaming**: Support fuer Streaming-Responses

### Lokale Backends

Laufen auf dem Pi selbst (z.B. Ollama, llama.cpp). Konfigurierbar ueber die Profile-Config.

### Cloud-Backends

Externe APIs (z.B. OpenAI). Nur fuer `general`-Clients erreichbar.

---

## Config-Dateien

### Gateway-Konfiguration

Die Konfiguration erfolgt ueber `config.py` mit den Klassen `ProfileConfig` und `SensitiveClass`.

```yaml
# Beispiel-Struktur (Konzept)
gateway:
  host: "0.0.0.0"
  port: 8080

backends:
  local:
    url: "http://localhost:11434"
    timeout: 120
  cloud:
    url: "https://api.openai.com"
    timeout: 60

clients:
  opencode-general:
    sensitive_class: "general"
    allowed_models: ["gpt-4o", "local-llama3"]
  opencode-sensitive:
    sensitive_class: "sensitive"
    allowed_models: ["local-llama3"]
```

---

## Audit-Log

### `audit.py`

Jeder Gateway-Request wird im Audit-Log erfasst:

| Feld | Inhalt |
|---|---|
| `timestamp` | ISO-8601 Zeitstempel |
| `client_id` | Client-Kennung |
| `sensitive_class` | Sensitive-Class des Clients |
| `model` | Angefordertes Modell |
| `backend` | Tatsaechlich genutztes Backend (local/cloud) |
| `status_code` | HTTP-Status der Antwort |
| `latency_ms` | Antwortzeit in Millisekunden |
| `tokens_in` | Input-Token-Anzahl |
| `tokens_out` | Output-Token-Anzahl |

Das Audit-Log dient Compliance, Debugging und Nutzungsanalyse.

---

## MVP-Einschraenkungen

### Keine Cloud-Fallbacks

Im MVP gibt es **keine automatischen Cloud-Fallbacks**. Wenn ein lokales Backend nicht verfuegbar ist, schlaegt der Request fehl. Cloud-Backends werden nur explizit durch `general`-Clients angefordert.

### Kein LiteLLM

LiteLLM ist aufgrund des Supply-Chain-Vorfalls Q1/2026 dauerhaft ausgeschlossen. Der Gateway implementiert das OpenAI-kompatible API nativ.

### Kein Rate-Limiting im MVP

Rate-Limiting ist als Feld im Client-Profil vorbereitet, wird aber im MVP nicht aktiv durchgesetzt.

---

## CLI-Integration

```bash
# Route fuer einen Client anzeigen
curaops-control gateway route --client opencode-general --model gpt-4o

# Smoke-Test des Gateways
curaops-control gateway smoke

# Audit-Log anzeigen
curaops-control gateway audit --last 100

# Gateway starten
curaops-control gateway serve --port 8080
```

---

## Testabdeckung

29 Tests decken Gateway-Funktionalitaet ab:
- Endpunkt-Verfuegbarkeit
- Authentifizierung (gueltig/ungueltig)
- Sensitive-Class Routing
- Backend-Proxy-Verhalten
- Audit-Log-Vollstaendigkeit
