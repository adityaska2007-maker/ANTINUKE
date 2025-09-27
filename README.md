# Antinuke Discord Bot (starter)
This is a starter **Antinuke** bot (Python) meant to be a secure, modern foundation you can extend.

## Key features
- Monitors audit logs for destructive actions (channel/role create/delete, bans).
- Uses a threshold (actions within a short window) to identify malicious actors.
- Whitelisting for safe users/roles (guild owner added by default).
- Auto-ban or demotion options.
- Simple JSON persistence (`data.json`).

## Setup
1. Install Python 3.11+.
2. Create a bot in the Discord Developer Portal. Enable needed gateway intents:
   - Server Members (Privileged) if you need member details.
   - (Message Content not required)
3. Give your bot appropriate permissions in the OAuth invite:
   - Manage Roles, Ban Members, View Audit Log, Manage Channels.
4. Install requirements:
