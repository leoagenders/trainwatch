# Trainwatch

Real-time railroad radio intelligence on a Raspberry Pi. Ingests live freight railroad radio, transcribes with Whisper, parses defect detector announcements into structured data, and sends push notifications when trains approach a designated watch location.

Built by Leo, 2026.

## Status

System running 24/7. Full README and architecture diagram coming after a few weeks of accumulated data.

## Quick overview

- Audio ingestion: Broadcastify Premium feed via ffmpeg
- Speech recognition: whisper.cpp (base.en model)
- Storage: SQLite
- Dashboard: Flask, with inline audio playback
- Alerts: ntfy push notifications
- Remote access: Tailscale VPN
- Services: systemd, auto-restart, daily backup + heartbeat via cron

See `scripts/` for the pipeline and `web/` for the dashboard.
