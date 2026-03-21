# Getting Started with LifeHack OS

LifeHack OS is a self-hosted personal operating system for discipline, habit tracking, project execution, and life rebuilding. Created by **Ludovic Micinthe** (dovik@micinthe.com) | Vibe Coder.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Detailed Setup](#detailed-setup)
   - [Clone the Repository](#clone-the-repository)
   - [Create a Virtual Environment](#create-a-virtual-environment)
   - [Install Dependencies](#install-dependencies)
   - [Configure .env](#configure-env)
   - [Run the Server](#run-the-server)
4. [First Login](#first-login)
5. [What You See on First Load](#what-you-see-on-first-load)
6. [Next Steps](#next-steps)

---

## Prerequisites

- **Python 3.11 or newer** — check with `python3 --version`
- **Git** — to clone the repository
- A modern browser (Chrome, Firefox, Safari, Edge)
- No database server required — LifeHack OS uses SQLite, which is built into Python

---

## Quick Start

Get running in under five minutes:

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/lifehack-os.git
cd lifehack-os

# Install
python3 -m venv venv
source venv/bin/activate          # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env — at minimum change SECRET_KEY, USERNAME, and PASSWORD

# Run
cd web
python app.py
```

Open `http://localhost:8420` in your browser.

---

## Detailed Setup

### Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/lifehack-os.git
cd lifehack-os
```

The project root contains:

```
lifehack-os/
├── web/                  # Flask web application (the main application)
├── src/                  # Core domain logic and infrastructure
├── config/               # TOML configuration files (rules, categories)
├── data/                 # SQLite database — created automatically on first run
├── .env.example          # Configuration template — copy to .env
├── requirements.txt      # Python dependencies
└── main.py               # Legacy desktop launcher (not needed for web)
```

### Create a Virtual Environment

Using a virtual environment keeps the project dependencies isolated from your system Python:

```bash
python3 -m venv venv
source venv/bin/activate
```

On Windows:

```bat
python -m venv venv
venv\Scripts\activate
```

You should see `(venv)` at the start of your shell prompt when the environment is active.

### Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:

| Package | Purpose |
|---|---|
| `flask` | Web framework |
| `flask-cors` | Cross-origin request support |
| `requests` | HTTP client for AI/integrations |
| `python-dotenv` | Loads `.env` file |
| `toml` | Reads `config/*.toml` files |
| `customtkinter`, `pillow` | Desktop GUI (optional, only for `main.py`) |

### Configure .env

Copy the example file and edit it:

```bash
cp .env.example .env
```

Open `.env` in any text editor. The three required settings are:

```bash
# Generate a secret key — paste the output into .env
python3 -c "import secrets; print(secrets.token_hex(32))"
```

```dotenv
LIFEHACK_SECRET_KEY=paste-your-generated-key-here
LIFEHACK_USERNAME=yourname
LIFEHACK_PASSWORD=a-strong-password
```

For a full reference of every `.env` variable, see [configuration.md](configuration.md).

### Run the Server

```bash
cd web
python app.py
```

Expected output:

```
 * Running on http://0.0.0.0:8420
 * Debug mode: off
```

The server binds to `0.0.0.0:8420` by default, so it is reachable at both `http://localhost:8420` and your machine's local network IP.

To bind only to localhost (not expose to your local network):

```dotenv
LIFEHACK_HOST=127.0.0.1
```

---

## First Login

Navigate to `http://localhost:8420`. You will see the login page.

Enter the username and password you set in `.env` (defaults are `admin` / `changeme` — change these).

The session lasts 30 days before requiring a re-login.

---

## What You See on First Load

After logging in, you land on the **Dashboard**. On a fresh install:

- **XP counter** shows 0 XP at Level 1 (Initiate)
- **Habits panel** is empty — your first task is adding habits
- **Daily check-in** prompt is visible — click it to complete today's check-in
- **Navigation** on the left shows the modules that are enabled by default: Habits, Check-in, and Analytics

**Modules that are disabled by default** (enable them in Settings): Projects, Movement, Food, Fasting, Deep Work, Challenges, Redirect, and Wishlist.

To enable more modules, click **Settings** in the navigation and toggle the modules you want.

### Add Your First Habit

1. Go to **Habits** in the navigation
2. Click **Add Habit**
3. Enter a name, select a category and frequency (daily or weekly)
4. Save — the habit appears in your list immediately

Complete it by clicking the checkbox. You will see XP added to your total.

---

## Next Steps

- Read [modules.md](modules.md) to understand what each module does and how to configure it
- Read [configuration.md](configuration.md) to customize scoring rules and categories
- Read [ai-providers.md](ai-providers.md) if you want AI-powered food analysis or insights
- Read [integrations.md](integrations.md) for Vikunja, Google Calendar, and Firefly III
