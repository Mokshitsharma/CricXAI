# CricXAI — App Flow

Status: Draft v1 · Last updated: 2026-08-28

Runtime flows end to end: what calls what, in what order, with the failure
branches. Build-time / offline flows first, then request-time.

---

## 1. Offline: data → features → models

```mermaid
flowchart LR
  MID[match_ids.py\nresolve IDs] --> SCR[scraper.py\nraw JSON]
  MOCK[mock_data.py\nsimulator] --> DP[(deliveries.csv\nmatches.csv)]
  SCR --> NLP[nlp_parser.py] --> DP
  DP --> BF[build_features.py] --> FT[(delivery_features.csv)]
  FT --> TR[train.py]
  TR --> M1[dismissal_prob/<v>/model.pkl]
  TR --> M2[dismissal_type/<v>/model.pkl]
  TR --> M3[expected_runs/<v>/model.pkl]
  TR --> EV[eval.md + meta.json]
  TR --> AP[data/models/active.json]
```

Commands (mock path):
```
py -3.13 -m scripts.mock_data --num-matches 100 --seed 42
py -3.13 -m scripts.build_features
py -3.13 -m scripts.train
```
`make demo` chains these plus starting the API.

## 2. API boot

```mermaid
sequenceDiagram
  participant P as Process start (uvicorn)
  participant R as ml/registry.py
  participant D as data/models or object store
  P->>R: load_active_models()
  R->>D: read active.json / models table
  R->>D: load model.pkl + shap_background for M1,M2,M3
  R-->>P: models in memory, versions recorded
  P->>P: /readyz returns 200
  Note over P: if no active model -> /readyz 503, /healthz 200
```

## 3. Request: `POST /v1/recommendation`

```mermaid
sequenceDiagram
  participant C as Client (console / API)
  participant MW as Middleware (auth, quota, request-id)
  participant H as Router handler
  participant FS as Feature assembly
  participant EN as engine.recommend
  participant ML as Models M1/M3
  participant EX as engine.reasons + SHAP
  participant CA as Redis cache

  C->>MW: POST payload + bearer/session
  MW->>MW: resolve principal, check plan quota
  alt over quota
    MW-->>C: 429 + Retry-After
  end
  MW->>H: validated (Pydantic) situation
  H->>CA: GET rec:{hash(payload)}:{model_version}
  alt hit
    CA-->>H: cached result
    H-->>C: 200 (X-Cache: hit)
  else miss
    H->>FS: batsman rolling + historical features (by batsman_id)
    alt batsman has no history
      FS-->>H: none
      H-->>C: 422 not enough data
    end
    H->>FS: derive situation features (phase, pressure_index, ...)
    H->>EN: candidate grid = lengths x lines (x bowler_type fixed)
    EN->>ML: score each candidate -> P(wicket), E[runs]
    EN->>EN: objective(phase) -> rank -> top_k
    EN->>EX: SHAP(top_k) -> template reasons
    EX-->>EN: reasons[], confidence
    EN-->>H: ranked recommendations
    H->>CA: SET short TTL
    H->>H: sample 5% -> predictions table (async)
    H-->>C: 200 payload (see TRD 5.3)
  end
```

Failure branches: model not loaded → `503`; feature store unreachable →
`503` (cache may still serve); SHAP failure → return recommendation with
`reasons: []` and `confidence: "unknown"` rather than failing the whole call.

## 4. Request: `GET /v1/batsmen/{id}/profile`

```mermaid
sequenceDiagram
  participant C as Client
  participant H as Handler
  participant CA as Redis cache
  participant Q as Aggregation (features/DB)
  C->>H: GET profile
  H->>CA: GET profile:{id}:{feature_build_version}
  alt hit
    CA-->>H: cached
  else miss
    H->>Q: dismissal-type %, length %, line %, phase avg, pressure/normal split
    Q-->>H: aggregates + sample counts
    H->>CA: SET long TTL (changes only on retrain / new data)
  end
  H-->>C: 200 profile + low_sample flag
```

Profiles are cheap to cache hard — they only change when data or the feature
build changes; cache key includes `feature_build_version`.

## 5. Onboarding / auth (Phase 5)

```mermaid
flowchart TD
  A[Visit /console anonymously] --> B[Use up to anon daily cap\ncookie counter]
  B --> C{Cap hit?}
  C -- no --> B
  C -- yes --> D[Modal: sign in / sign up]
  D --> E[Auth.js: email magic link or Google]
  E --> F[users row upserted]
  F --> G[Default free subscription created]
  G --> H[Redirect back to /console with saved situation]
  H --> I[Header shows UsageMeter]
```

## 6. Upgrade / billing (Phase 5)

```mermaid
sequenceDiagram
  participant U as User
  participant W as Web /account
  participant API as billing.py
  participant S as Stripe
  U->>W: Click "Upgrade to Pro"
  W->>API: POST /v1/billing/checkout {plan: pro}
  API->>S: create Checkout Session
  S-->>U: hosted checkout
  U->>S: pays
  S->>API: webhook checkout.session.completed
  API->>API: subscriptions row -> plan=pro, quota updated
  API->>API: reset Redis quota counter for period
  S-->>U: redirect /account?upgraded=1
  Note over API,S: nightly job reconciles usage_events -> Stripe metered usage
```

## 7. API key usage (Phase 5)

```mermaid
sequenceDiagram
  participant Dev as Developer
  participant W as /account
  participant API
  Dev->>W: Create key "prod"
  W->>API: POST /v1/keys
  API->>API: generate secret, store Argon2 hash + prefix
  API-->>W: secret (shown once)
  Dev->>API: POST /v1/recommendation  Authorization: Bearer <secret>
  API->>API: hash -> lookup by prefix -> verify -> load plan
  API->>API: increment quota counter, append usage_event
  API-->>Dev: 200 or 429
```

## 8. Scheduled scrape (Phase 2)

```mermaid
flowchart TD
  CRON[GitHub Action daily] --> RES[match_ids.resolve_match_ids]
  RES --> PEND[filter matches not on disk / not in object store]
  PEND --> LOOP[scrape up to --batch-size, polite delays]
  LOOP --> STORE[(object store raw/<series>/<id>.json)]
  STORE --> PARSE[nlp_parser on new files]
  PARSE --> QG{extraction quality >= floor?}
  QG -- no --> ALERT[open alert, keep last-good feature table]
  QG -- yes --> FEAT[rebuild features incrementally]
  FEAT --> NOTE[write run log to data/logs + metrics]
```

Training is **not** in this loop — it's a manual/monthly job that consumes
whatever the feature table currently holds.
