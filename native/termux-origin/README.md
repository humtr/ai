# Existing-terminal origin candidate

Pinned Termux app: 8629e632fcb95da272221be327db653fb24befe9 (installed Github build).
This source candidate extends the existing authenticated AM socket; no extra
service/socket listener, persistent terminal index or window constructor is added.

Protocol: termux-am-socket 'termux-terminal-v1 capabilities|origin'
and 'termux-terminal-v1 validate|focus HANDLE PID START'. Replies use the existing
AM framing, exit status and bounded JSON schema termux-terminal-origin-v1.
Origin resolution follows the authenticated socket peer's live same-UID ancestry
against Termux's session table. References bind native handle plus PID/start.
Validate/focus require the exact live reference; focus sets the existing session
and Activity's existing-handle guard refuses closed targets instead of creating.

The candidate retains the installed package ID, variant, version code and upstream
Github debug signing config. Its certificate must match the installed Github APK
before any installation. Build/source tests do not constitute Android device
acceptance. No live APK installation is performed by this build workflow.
