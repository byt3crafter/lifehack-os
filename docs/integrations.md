# Integrations

LifeHack OS can connect to three external services: Vikunja for task management, Google Calendar for event display, and Firefly III for personal finance. All integrations are optional and independent — you can use none, one, or all of them.

---

## Table of Contents

1. [Vikunja (Task Management)](#vikunja-task-management)
2. [Google Calendar](#google-calendar)
3. [Firefly III (Finance)](#firefly-iii-finance)
4. [Managing Integrations](#managing-integrations)

---

## Vikunja (Task Management)

### What it Does

Vikunja is a self-hosted, open-source task management application. When the Vikunja integration is enabled, the Projects module pulls projects and tasks from your Vikunja instance instead of the local SQLite database. You can view, create, complete, and uncomplete tasks through the LifeHack OS interface, and the changes are written back to Vikunja.

This is useful if Vikunja is already your task manager and you want LifeHack OS to be the single place you work.

### Requirements

- A running Vikunja instance (self-hosted). See [vikunja.io](https://vikunja.io) for installation guides.
- A Vikunja account with a username and password
- Network access from the LifeHack OS server to the Vikunja API URL

### How to Configure

**Option 1: Through the Settings UI**

1. Log in to LifeHack OS
2. Go to **Settings** → **Integrations**
3. In the Vikunja section, enter:
   - **API URL** — your Vikunja base URL followed by `/api/v1` (e.g., `https://tasks.example.com/api/v1`)
   - **Username** — your Vikunja username
   - **Password** — your Vikunja password
4. Click **Connect** — LifeHack OS tests the connection before saving
5. If the connection succeeds, the Projects module now pulls from Vikunja

**Option 2: Via .env**

The integration can also be pre-configured through environment variables:

```dotenv
VIKUNJA_API_URL=https://tasks.example.com/api/v1
VIKUNJA_USERNAME=youruser
VIKUNJA_PASSWORD=yourpassword
```

Note: these `.env` variables are used for pre-seeding only. The active integration configuration is saved in `config/integrations.json` after a successful connection test through the UI.

### What is Synced

| Action | Behavior |
|---|---|
| List projects | Pulled from Vikunja `/projects` |
| List tasks | Pulled from Vikunja, all projects or filtered by project |
| Create task | Written to Vikunja via `PUT /projects/{id}/tasks` |
| Complete task | Sets `done: true` in Vikunja |
| Uncomplete task | Sets `done: false` in Vikunja |

Milestones in LifeHack OS are a local concept and are not synced to Vikunja.

### Fallback Behavior

If Vikunja is enabled but the connection test fails at request time (Vikunja is down or unreachable), LifeHack OS falls back to the native SQLite task provider transparently. No error is shown to the user unless the connection is explicitly tested.

### Troubleshooting

**"Connection test failed" when saving:**
- Verify the API URL ends in `/api/v1`
- Confirm your username and password are correct
- Check that the LifeHack OS server can reach the Vikunja host (test with `curl https://tasks.example.com/api/v1/info`)
- If Vikunja is on the same machine, use `http://localhost:3456/api/v1` (default Vikunja port)

**Projects module showing local tasks after enabling Vikunja:**
- The connection test may have failed silently. Go to Settings → Integrations and check the connected status.
- Disable and re-enable the integration after fixing the URL or credentials.

**Authentication errors after changing your Vikunja password:**
- Go to Settings → Integrations → Vikunja and re-enter your credentials.

---

## Google Calendar

### What it Does

Displays upcoming calendar events in the LifeHack OS dashboard. Events are pulled from Google Calendar via the `gog` CLI tool. LifeHack OS does not use OAuth directly — it delegates the Google authentication to the `gog` tool.

Events are read-only within LifeHack OS (creating events via the API is possible, but no UI exists for it currently).

### Requirements

- The `gog` CLI tool, installed and authenticated with your Google account. See [github.com/nicholasgasior/gog](https://github.com/nicholasgasior/gog) or equivalent documentation for your `gog` version.
- `gog` must be in the `PATH` of the user running the LifeHack OS server process
- `gog` must be authenticated (`gog auth login` or equivalent) before configuring the integration

### Verifying `gog` is Working

Before configuring the integration, confirm `gog` can list your calendars:

```bash
gog calendar calendars --account your@gmail.com
```

If this command returns your calendars, `gog` is working.

### How to Configure

**Through the Settings UI:**

1. Go to **Settings** → **Integrations**
2. In the Google Calendar section, enter:
   - **Account** — your Google account email (e.g., `your@gmail.com`)
3. Click **Connect** — LifeHack OS runs `gog calendar calendars --account your@gmail.com` to verify the connection
4. If successful, events appear on the dashboard

**Via .env:**

```dotenv
GCAL_ACCOUNT=your@gmail.com
```

### How Events are Fetched

LifeHack OS calls `gog` as a subprocess:

```bash
gog calendar events primary --from YYYY-MM-DD --to YYYY-MM-DD --account your@gmail.com --json
```

Events up to 7 days ahead are fetched by default. The event list is returned to the UI as JSON.

### Troubleshooting

**No events appearing after successful connection:**
- Confirm your primary calendar has upcoming events
- Run the `gog` command manually to verify it returns JSON output
- Check that `gog` is in the system PATH accessible by the process user

**"Connection test failed":**
- Run `gog calendar calendars --account your@gmail.com` in the terminal as the same user running the LifeHack OS server
- If `gog` outputs an error about authentication, re-authenticate: `gog auth login`

**Events are stale:**
- Events are fetched on each page load, not cached. If they appear stale, there may be a subprocess timeout (default: 30 seconds). A slow network or Google rate limiting can cause this.

---

## Firefly III (Finance)

### What it Does

Connects LifeHack OS to a Firefly III personal finance instance via a local helper script (`firefly.sh`). Shows your account balance and recent transactions in the LifeHack OS dashboard. You can also add withdrawals and deposits from within LifeHack OS.

### Requirements

- A running Firefly III instance (self-hosted). See [firefly-iii.org](https://firefly-iii.org) for installation.
- A `firefly.sh` helper script that wraps the Firefly III API with the expected command interface (see below)
- The helper script must be executable and in a location accessible to the LifeHack OS server process

### Expected Helper Script Interface

LifeHack OS calls `firefly.sh` as a subprocess with the following command patterns:

```bash
firefly.sh accounts                           # List accounts
firefly.sh accounts --json                    # List accounts as JSON
firefly.sh balance <account_id>               # Get balance for an account
firefly.sh transactions --json --limit <n>    # Recent transactions as JSON
firefly.sh withdraw <amount> <description> <account_id> [category]
firefly.sh deposit <amount> <description> <account_id>
firefly.sh spending --days <n> --json         # Spending by category
firefly.sh budgets --json                     # Budget status
```

The JSON output must follow the Firefly III API structure (the helper is expected to call the Firefly III REST API internally and return the raw JSON).

### How to Configure

**Through the Settings UI:**

1. Go to **Settings** → **Integrations**
2. In the Firefly III section, confirm your helper script is in place
3. Click **Connect** — LifeHack OS runs `firefly.sh accounts` to verify
4. If successful, the balance and recent transactions appear on the dashboard

**Via .env:**

```dotenv
FIREFLY_HELPER_PATH=/path/to/firefly.sh
FIREFLY_ACCOUNT_ID=1
```

`FIREFLY_ACCOUNT_ID` is the default Firefly III account ID for balance lookups and transactions. Find your account ID in the Firefly III URL when viewing an account (e.g., `https://firefly.example.com/accounts/1`).

### Dashboard Display

When Firefly III is connected, the dashboard shows:

- Current balance for the default account
- The 5 most recent transactions (description, amount, type, date, category)

### Adding Transactions

From the Finance section in the dashboard, you can:

- Log a **withdrawal** with amount, description, and optional category
- Log a **deposit** with amount and description

These are passed to `firefly.sh withdraw` or `firefly.sh deposit` as a subprocess call.

### Troubleshooting

**"Connection test failed":**
- Run `firefly.sh accounts` manually as the same user running the LifeHack OS server
- Verify the script is executable: `chmod +x /path/to/firefly.sh`
- Verify `FIREFLY_HELPER_PATH` points to the correct location

**Balance shows as null:**
- Confirm `FIREFLY_ACCOUNT_ID` is set to a valid account ID
- Run `firefly.sh balance <your_account_id>` manually and check the output format

**Transactions not appearing:**
- Run `firefly.sh transactions --json --limit 5` manually and verify it returns well-formed JSON

---

## Managing Integrations

### Integration State File

All integration settings (enabled status, credentials, account names) are stored in `config/integrations.json`. This file is created automatically when you first save an integration through the UI.

Example `config/integrations.json`:

```json
{
  "vikunja": {
    "enabled": true,
    "api_url": "https://tasks.example.com/api/v1",
    "username": "youruser",
    "password": "yourpassword"
  },
  "google_calendar": {
    "enabled": true,
    "account": "your@gmail.com"
  },
  "firefly": {
    "enabled": false
  }
}
```

**Security note:** The `integrations.json` file contains your Vikunja password in plaintext. Ensure the file has appropriate permissions and is not committed to version control.

### Disabling an Integration

Through the Settings UI: toggle the integration off and click Save.

Via the API:

```bash
# Disable Vikunja
curl -X POST http://localhost:8420/api/integrations/vikunja \
  -H "Content-Type: application/json" \
  -b "session=..." \
  -d '{"enabled": false}'
```

Disabling an integration does not delete data — it just stops the connection. Local data (projects, tasks) remains in the SQLite database and the native provider resumes.
